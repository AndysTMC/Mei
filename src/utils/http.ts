import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import { Logger, Tag } from './logger.js';
import type { JsonObject } from '../providers/types.js';

function redactSensitiveUrl(url: string): string {
    return url.replace(
        /([?&](?:api[_-]?key|access[_-]?token|token|key)=)[^&]+/gi,
        '$1***'
    );
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
            buffer = buffer.slice(buffer.charAt(separatorIndex) === '\r' ? separatorIndex + 4 : separatorIndex + 2);
            for (const data of parseSseDataBlock(block)) {
                if (data === '[DONE]') {
                    done = true;
                    return false;
                }
                onData(data);
            }
            separatorIndex = findSseSeparator(buffer);
        }
        return !done;
    });
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
        let newlineIndex = buffer.indexOf('\n');
        while (newlineIndex !== -1) {
            const line = buffer.slice(0, newlineIndex).trim();
            buffer = buffer.slice(newlineIndex + 1);
            if (line) onLine(line);
            newlineIndex = buffer.indexOf('\n');
        }
    });
    const rest = buffer.trim();
    if (rest) onLine(rest);
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
    Logger.debug(Tag.HTTP, `POST ${logUrl} body=${Logger.truncate(jsonStr, 500)}`);

    const bytes = new GLib.Bytes(new TextEncoder().encode(jsonStr));
    msg.set_request_body_from_bytes('application/json', bytes);

    for (const [key, value] of Object.entries(headers)) {
        msg.get_request_headers().append(key, value);
    }

    Logger.time(Tag.HTTP, logUrl);

    try {
        const respBytes = await session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            cancellable
        );
        const data = respBytes.get_data();
        const text = data ? new TextDecoder().decode(data) : '';
        const elapsed = Logger.timeEnd(Tag.HTTP, logUrl);
        const status = msg.get_status();
        Logger.debug(Tag.HTTP, `POST ${logUrl} → ${status} (${elapsed}ms) body=${Logger.truncate(text, 500)}`);

        if (status >= 400) {
            let errMsg = `HTTP ${status}`;
            try {
                const parsed = JSON.parse(text) as JsonObject;
                const error = parsed.error;
                if (typeof error === 'object' && error !== null && 'message' in error) {
                    const message = (error as JsonObject).message;
                    if (typeof message === 'string') {
                        errMsg = message;
                    }
                } else if (typeof error === 'string') {
                    errMsg = error;
                } else if (typeof parsed.detail === 'string') {
                    errMsg = parsed.detail;
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
        Logger.error(Tag.HTTP, `POST ${logUrl} failed`, e);
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
    Logger.debug(Tag.HTTP, `POST stream ${logUrl} body=${Logger.truncate(jsonStr, 500)}`);

    const bytes = new GLib.Bytes(new TextEncoder().encode(jsonStr));
    msg.set_request_body_from_bytes('application/json', bytes);

    for (const [key, value] of Object.entries(headers)) {
        msg.get_request_headers().append(key, value);
    }

    Logger.time(Tag.HTTP, logUrl);

    try {
        const stream = await sendStreamAsync(session, msg, cancellable);
        const status = msg.get_status();
        const decoder = new TextDecoder();
        let keepReading = true;

        if (status >= 400) {
            const text = await readStreamText(stream, decoder, cancellable);
            throw new Error(parseHttpError(status, text));
        }

        while (keepReading && !cancellable.is_cancelled()) {
            const chunk = await readBytesAsync(stream, cancellable);
            const data = chunk.get_data();
            if (!data || data.length === 0) break;
            keepReading = onChunk(decoder.decode(data)) !== false;
        }

        const tail = decoder.decode();
        if (keepReading && tail) onChunk(tail);

        const elapsed = Logger.timeEnd(Tag.HTTP, logUrl);
        Logger.debug(Tag.HTTP, `POST stream ${logUrl} → ${status} (${elapsed}ms)`);
    } catch (e) {
        Logger.timeEnd(Tag.HTTP, logUrl);
        Logger.error(Tag.HTTP, `POST stream ${logUrl} failed`, e);
        throw e;
    }
}

function sendStreamAsync(
    session: Soup.Session,
    msg: Soup.Message,
    cancellable: Gio.Cancellable
): Promise<Gio.InputStream> {
    return new Promise((resolve, reject) => {
        session.send_async(msg, GLib.PRIORITY_DEFAULT, cancellable, (source, result) => {
            try {
                const sourceSession = source ?? session;
                resolve(sourceSession.send_finish(result) as unknown as Gio.InputStream);
            } catch (e) {
                reject(e);
            }
        });
    });
}

function readBytesAsync(
    stream: Gio.InputStream,
    cancellable: Gio.Cancellable
): Promise<GLib.Bytes> {
    return new Promise((resolve, reject) => {
        stream.read_bytes_async(8192, GLib.PRIORITY_DEFAULT, cancellable, (source, result) => {
            try {
                const sourceStream = source ?? stream;
                resolve(sourceStream.read_bytes_finish(result));
            } catch (e) {
                reject(e);
            }
        });
    });
}

async function readStreamText(
    stream: Gio.InputStream,
    decoder: TextDecoder,
    cancellable: Gio.Cancellable
): Promise<string> {
    let text = '';
    while (!cancellable.is_cancelled()) {
        const chunk = await readBytesAsync(stream, cancellable);
        const data = chunk.get_data();
        if (!data || data.length === 0) break;
        text += decoder.decode(data);
    }
    text += decoder.decode();
    return text;
}

function parseHttpError(status: number, text: string): string {
    let errMsg = `HTTP ${status}`;
    try {
        const parsed = JSON.parse(text) as JsonObject;
        const error = parsed.error;
        if (typeof error === 'object' && error !== null && 'message' in error) {
            const message = (error as JsonObject).message;
            if (typeof message === 'string') {
                errMsg = message;
            }
        } else if (typeof error === 'string') {
            errMsg = error;
        } else if (typeof parsed.detail === 'string') {
            errMsg = parsed.detail;
        }
    } catch {
        if (text.trim()) errMsg += `: ${Logger.truncate(text.trim(), 100)}`;
    }
    return errMsg;
}

function findSseSeparator(text: string): number {
    const lf = text.indexOf('\n\n');
    const crlf = text.indexOf('\r\n\r\n');
    if (lf === -1) return crlf;
    if (crlf === -1) return lf;
    return Math.min(lf, crlf);
}

function parseSseDataBlock(block: string): string[] {
    const lines = block.split(/\r?\n/);
    const dataLines = lines
        .filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).trimStart());
    return dataLines.length > 0 ? [dataLines.join('\n')] : [];
}
