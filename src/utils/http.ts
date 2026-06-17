import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import { Logger, Tag } from './logger.js';

/**
 * Sends a POST request with a JSON body and returns the parsed JSON response.
 */
export function postJson(
    session: Soup.Session,
    url: string,
    body: object,
    headers: Record<string, string>,
    cancellable: Gio.Cancellable
): Promise<any> {
    return new Promise((resolve, reject) => {
        const msg = Soup.Message.new('POST', url);
        if (!msg) {
            Logger.error(Tag.HTTP, `Invalid URL: ${url}`);
            reject(new Error(`Invalid URL: ${url}`));
            return;
        }

        const jsonStr = JSON.stringify(body);
        Logger.debug(Tag.HTTP, `POST ${url} body=${Logger.truncate(jsonStr, 500)}`);

        const bytes = new GLib.Bytes(new TextEncoder().encode(jsonStr));
        msg.set_request_body_from_bytes('application/json', bytes);

        for (const [key, value] of Object.entries(headers)) {
            msg.get_request_headers().append(key, value);
        }

        Logger.time(Tag.HTTP, url);

        session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            cancellable,
            ((_session: any, result: any) => {
                try {
                    const respBytes = session.send_and_read_finish(result);
                    const text = new TextDecoder().decode(respBytes.get_data()!);
                    const elapsed = Logger.timeEnd(Tag.HTTP, url);
                    const status = msg.get_status();
                    Logger.debug(Tag.HTTP, `POST ${url} → ${status} (${elapsed}ms) body=${Logger.truncate(text, 500)}`);

                    if (status >= 400) {
                        let errMsg = `HTTP ${status}`;
                        try {
                            const parsed = JSON.parse(text);
                            errMsg = parsed.error?.message || parsed.error || parsed.detail || errMsg;
                        } catch {
                            if (text.trim()) errMsg += `: ${Logger.truncate(text.trim(), 100)}`;
                        }
                        reject(new Error(errMsg));
                        return;
                    }

                    const json = JSON.parse(text);
                    resolve(json);
                } catch (e) {
                    Logger.timeEnd(Tag.HTTP, url);
                    Logger.error(Tag.HTTP, `POST ${url} failed`, e);
                    reject(e);
                }
            }) as any
        );
    });
}
