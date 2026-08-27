/**
 * Bounded Soup response readers shared by chat and model-list requests.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';

import { ResponseSizeGuard } from './responseLimits.js';
import { Utf8StreamDecoder } from './streamParsers.js';

export async function sendMessageText(
    session: Soup.Session,
    msg: Soup.Message,
    cancellable: Gio.Cancellable
): Promise<string> {
    const stream = await sendStreamAsync(session, msg, cancellable);
    try {
        return await readStreamText(stream, cancellable);
    } finally {
        try {
            stream.close(null);
        } catch {
            // The session may already have closed the stream after cancellation.
        }
    }
}

export function sendStreamAsync(
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

export function readBytesAsync(
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

export async function readStreamText(
    stream: Gio.InputStream,
    cancellable: Gio.Cancellable
): Promise<string> {
    const decoder = new Utf8StreamDecoder();
    const responseSize = new ResponseSizeGuard();
    let text = '';

    while (!cancellable.is_cancelled()) {
        const chunk = await readBytesAsync(stream, cancellable);
        const data = chunk.get_data();
        if (!data || data.length === 0) break;
        responseSize.add(data.length);
        text += decoder.decode(data);
    }
    text += decoder.decode();
    return text;
}
