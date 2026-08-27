/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import { Logger, Tag } from './logger.js';
import { redactSensitiveText } from './redaction.js';
import { ResponseSizeGuard } from './responseLimits.js';
import { readBytesAsync, readStreamText, sendMessageText, sendStreamAsync } from './soupText.js';
import { extractJsonLines, findSseSeparator, getSseSeparatorLength, parseSseDataBlock, throwIfStreamError, Utf8StreamDecoder } from './streamParsers.js';
import type { JsonObject } from '../providers/types.js';

function redactSensitiveUrl(url: string): string {
    return redactSensitiveText(url);
}

/**
 * Sends a POST request with a JSON body and returns the parsed JSON response.
 */
export function postJson(
    session: Soup.Session,
    url: string,
    body: object,
    headers: Record<string, string>,
    cancellable: Gio.Cancellable
): Promise<JsonObject> {
    return sendJsonRequest(session, url, body, headers, cancellable);
}

export async function postJsonSse(
    session: Soup.Session,
    url: string,
    body: object,
    headers: Record<string, string>,
    cancellable: Gio.Cancellable,
    onData: (data: string) => void
): Promise<void> {
    let buffer = '';
    let done = false;
    await postJsonTextStream(session, url, body, { Accept: 'text/event-stream', ...headers }, cancellable, chunk => {
        buffer += chunk;
        let separatorIndex = findSseSeparator(buffer);
        while (separatorIndex !== -1) {
            const block = buffer.slice(0, separatorIndex);
            buffer = buffer.slice(separatorIndex + getSseSeparatorLength(buffer, separatorIndex));
            for (const data of parseSseDataBlock(block)) {
                if (data === '[DONE]') {
                    done = true;
                    return false;
                }
                throwIfStreamError(data);
                onData(data);
            }
            separatorIndex = findSseSeparator(buffer);
        }
        return !done;
    });
    if (!done && buffer.trim()) {
        for (const data of parseSseDataBlock(buffer)) {
            if (data === '[DONE]') continue;
            throwIfStreamError(data);
            onData(data);
        }
    }
}

export async function postJsonLines(
    session: Soup.Session,
    url: string,
    body: object,
    headers: Record<string, string>,
    cancellable: Gio.Cancellable,
    onLine: (line: string) => void
): Promise<void> {
    let buffer = '';
    await postJsonTextStream(session, url, body, headers, cancellable, chunk => {
        buffer += chunk;
        const extracted = extractJsonLines(buffer);
        buffer = extracted.rest;
        for (const line of extracted.lines) {
            throwIfStreamError(line);
            onLine(line);
        }
    });
    const rest = buffer.trim();
    if (rest) {
        throwIfStreamError(rest);
        onLine(rest);
    }
}

async function sendJsonRequest(
    session: Soup.Session,
    url: string,
    body: object,
    headers: Record<string, string>,
    cancellable: Gio.Cancellable
): Promise<JsonObject> {
    const logUrl = redactSensitiveUrl(url);
    const msg = Soup.Message.new('POST', url);
    if (!msg) {
        Logger.error(Tag.HTTP, `Invalid URL: ${logUrl}`);
        throw new Error(`Invalid URL: ${logUrl}`);
    }

    const jsonStr = JSON.stringify(body);
    Logger.debug(Tag.HTTP, `POST ${logUrl} bodyBytes=${jsonStr.length}`);

    const bytes = new GLib.Bytes(new TextEncoder().encode(jsonStr));
    msg.set_request_body_from_bytes('application/json', bytes);

    for (const [key, value] of Object.entries(headers)) {
        msg.get_request_headers().append(key, value);
    }

    Logger.time(Tag.HTTP, logUrl);

    try {
        const text = await sendMessageText(session, msg, cancellable);
        const elapsed = Logger.timeEnd(Tag.HTTP, logUrl);
        const status = msg.get_status();
        Logger.debug(Tag.HTTP, `POST ${logUrl} → ${status} (${elapsed}ms) responseBytes=${text.length}`);

        if (status >= 400) {
            let errMsg = `HTTP ${status}`;
            try {
                const parsed = JSON.parse(text) as JsonObject;
                const error = parsed.error;
                if (typeof error === 'object' && error !== null && 'message' in error) {
                    const message = (error as JsonObject).message;
                    if (typeof message === 'string') {
                        errMsg = Logger.truncate(message, 500);
                    }
                } else if (typeof error === 'string') {
                    errMsg = Logger.truncate(error, 500);
                } else if (typeof parsed.detail === 'string') {
                    errMsg = Logger.truncate(parsed.detail, 500);
                }
            } catch {
                if (text.trim()) errMsg += `: ${Logger.truncate(text.trim(), 100)}`;
            }
            throw new Error(errMsg);
        }

        const json = JSON.parse(text) as unknown;
        if (typeof json !== 'object' || json === null || Array.isArray(json)) {
            throw new Error('Response JSON was not an object');
        }
        return json as JsonObject;
    } catch (e) {
        Logger.timeEnd(Tag.HTTP, logUrl);
        if (cancellable.is_cancelled()) {
            Logger.debug(Tag.HTTP, `POST ${logUrl} cancelled`);
        } else {
            Logger.error(Tag.HTTP, `POST ${logUrl} failed`, e);
        }
        throw e;
    }
}

async function postJsonTextStream(
    session: Soup.Session,
    url: string,
    body: object,
    headers: Record<string, string>,
    cancellable: Gio.Cancellable,
    onChunk: (chunk: string) => boolean | void
): Promise<void> {
    const logUrl = redactSensitiveUrl(url);
    const msg = Soup.Message.new('POST', url);
    if (!msg) {
        Logger.error(Tag.HTTP, `Invalid URL: ${logUrl}`);
        throw new Error(`Invalid URL: ${logUrl}`);
    }

    const jsonStr = JSON.stringify(body);
    Logger.debug(Tag.HTTP, `POST stream ${logUrl} bodyBytes=${jsonStr.length}`);

    const bytes = new GLib.Bytes(new TextEncoder().encode(jsonStr));
    msg.set_request_body_from_bytes('application/json', bytes);

    for (const [key, value] of Object.entries(headers)) {
        msg.get_request_headers().append(key, value);
    }

    Logger.time(Tag.HTTP, logUrl);

    let stream: Gio.InputStream | null = null;
    try {
        stream = await sendStreamAsync(session, msg, cancellable);
        const status = msg.get_status();
        const decoder = new Utf8StreamDecoder();
        const responseSize = new ResponseSizeGuard();
        let keepReading = true;

        if (status >= 400) {
            const text = await readStreamText(stream, cancellable);
            throw new Error(parseHttpError(status, text));
        }

        while (keepReading && !cancellable.is_cancelled()) {
            const chunk = await readBytesAsync(stream, cancellable);
            const data = chunk.get_data();
            if (!data || data.length === 0) break;
            responseSize.add(data.length);
            keepReading = onChunk(decoder.decode(data)) !== false;
        }

        const tail = decoder.decode();
        if (keepReading && tail) onChunk(tail);

        const elapsed = Logger.timeEnd(Tag.HTTP, logUrl);
        Logger.debug(Tag.HTTP, `POST stream ${logUrl} → ${status} (${elapsed}ms)`);
    } catch (e) {
        Logger.timeEnd(Tag.HTTP, logUrl);
        if (cancellable.is_cancelled()) {
            Logger.debug(Tag.HTTP, `POST stream ${logUrl} cancelled`);
        } else {
            Logger.error(Tag.HTTP, `POST stream ${logUrl} failed`, e);
        }
        throw e;
    } finally {
        if (stream) {
            try {
                stream.close(null);
            } catch {
                // The session may already have closed the stream after cancellation.
            }
        }
    }
}

function parseHttpError(status: number, text: string): string {
    let errMsg = `HTTP ${status}`;
    try {
        const parsed = JSON.parse(text) as JsonObject;
        const error = parsed.error;
        if (typeof error === 'object' && error !== null && 'message' in error) {
            const message = (error as JsonObject).message;
            if (typeof message === 'string') {
                errMsg = Logger.truncate(message, 500);
            }
        } else if (typeof error === 'string') {
            errMsg = Logger.truncate(error, 500);
        } else if (typeof parsed.detail === 'string') {
            errMsg = Logger.truncate(parsed.detail, 500);
        }
    } catch {
        if (text.trim()) errMsg += `: ${Logger.truncate(text.trim(), 100)}`;
    }
    return errMsg;
}
