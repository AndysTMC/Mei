/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';

export const LOG_DIR = GLib.get_user_state_dir() + '/mei';
export const LOG_FILE = LOG_DIR + '/logs.txt';

export function ensureLogDir(): void {
    if (!GLib.file_test(LOG_DIR, GLib.FileTest.EXISTS)) {
        GLib.mkdir_with_parents(LOG_DIR, 0o700);
    }
    setPrivateMode(LOG_DIR, 0o700);
}

export function setPrivateMode(path: string | null, mode: number): void {
    if (!path) return;
    try {
        Gio.File.new_for_path(path).set_attribute_uint32(
            Gio.FILE_ATTRIBUTE_UNIX_MODE,
            mode,
            Gio.FileQueryInfoFlags.NONE,
            null
        );
    } catch {
        // Permission tightening is best-effort on non-Unix filesystems.
    }
}

export function replaceLogFileTextAsync(text: string): Promise<void> {
    ensureLogDir();
    const file = Gio.File.new_for_path(LOG_FILE);
    const bytes = new TextEncoder().encode(text);

    return new Promise((resolve, reject) => {
        file.replace_contents_async(
            bytes,
            null,
            false,
            Gio.FileCreateFlags.NONE,
            null,
            (source, result) => {
                try {
                    const sourceFile = source ?? file;
                    sourceFile.replace_contents_finish(result);
                    setPrivateMode(file.get_path(), 0o600);
                    resolve();
                } catch (e) {
                    reject(e);
                }
            }
        );
    });
}
