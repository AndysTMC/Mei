/**
 * How the popup's log panel and the preferences' log page show a runtime log entry.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { LogEntry } from './protocol.js';

/** `HH:MM:SS [LEVEL] [logger] message`, in local time. */
export function formatLogEntry(entry: LogEntry): string {
    const time = new Date(entry.t * 1000).toTimeString().slice(0, 8);
    return `${time} [${entry.level.toUpperCase()}] [${entry.logger}] ${entry.msg}`;
}
