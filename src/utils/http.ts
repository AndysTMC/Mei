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
