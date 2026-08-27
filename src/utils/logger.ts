/**
 * Structured logger for Mei.
 *
 * Uses the build-time `__DEV__` constant (injected by esbuild) to
 * control console verbosity. Production builds retain INFO/WARN/ERROR file
 * logging while omitting development-only console output and stack details.
 *
 * Log format:  [Mei:LEVEL] [Tag] message
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Gio from 'gi://Gio';

import { ensureLogDir, LOG_FILE, setPrivateMode } from './logFile.js';
import { redactSensitiveText } from './redaction.js';

/* ── Log levels ───────────────────────────────────── */

export const enum LogLevel {
    DEBUG = 0,
    INFO  = 1,
    WARN  = 2,
    ERROR = 3,
}

/* ── Tag constants ────────────────────────────────── */

export const Tag = {
    Extension: 'Extension',
    Provider:  'Provider',
    HTTP:      'HTTP',
    UI:        'UI',
    Theme:     'Theme',
    Indicator: 'Indicator',
    Prefs:     'Prefs',
} as const;

export type TagName = (typeof Tag)[keyof typeof Tag];

const MAX_LOG_BYTES = 2 * 1024 * 1024;
const RETAINED_LOG_CHARS = 1024 * 1024;
let approximateLogBytes: number | null = null;

/* ── Helpers ──────────────────────────────────────── */

/** Truncate a string to `max` chars, appending `…` if clipped. */
function truncate(s: string, max: number): string {
    if (s.length <= max) return s;
    return s.slice(0, max) + '…';
}

/** Describe whether an API key is present without exposing any fragment. */
export function maskKey(key: string | undefined): string {
    return key ? 'configured' : 'not set';
}

/* ── File Logging ─────────────────────────────────── */

function writeToFile(level: string, tag: string, msg: string): void {
    try {
        ensureLogDir();
        const file = Gio.File.new_for_path(LOG_FILE);
        rotateLogIfNeeded(file);
        const out = file.append_to(Gio.FileCreateFlags.NONE, null);

        const now = new Date();
        const timestamp = now.toISOString();
        const safeMessage = redactSensitiveText(msg).replace(/[\r\n]+/g, '\\n');
        const line = `[${timestamp}] [${level}] [${tag}] ${safeMessage}\n`;

        const encodedLine = new TextEncoder().encode(line);
        out.write_all(encodedLine, null);
        out.close(null);
        approximateLogBytes = (approximateLogBytes ?? 0) + encodedLine.length;
        setPrivateMode(LOG_FILE, 0o600);
    } catch (e) {
        console.error(`[Mei:ERROR] Failed to write log to file: ${e}`);
    }
}

function rotateLogIfNeeded(file: Gio.File): void {
    if (approximateLogBytes === null) {
        approximateLogBytes = file.query_exists(null)
            ? file.query_info(Gio.FILE_ATTRIBUTE_STANDARD_SIZE, Gio.FileQueryInfoFlags.NONE, null).get_size()
            : 0;
    }
    if (approximateLogBytes <= MAX_LOG_BYTES) return;

    const [ok, contents] = file.load_contents(null);
    if (!ok) return;
    const text = new TextDecoder().decode(contents);
    const retained = text.slice(-RETAINED_LOG_CHARS);
    const firstNewline = retained.indexOf('\n');
    const tail = firstNewline >= 0 ? retained.slice(firstNewline + 1) : retained;
    const rotated = `[${new Date().toISOString()}] [INFO] [Extension] Log rotated\n${tail}`;
    const bytes = new TextEncoder().encode(rotated);
    file.replace_contents(bytes, null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
    approximateLogBytes = bytes.length;
    setPrivateMode(LOG_FILE, 0o600);
}

/* ── Logger ───────────────────────────────────────── */

export class Logger {
    /** Minimum level to log. Set to DEBUG manually when diagnosing locally. */
    static minLevel: LogLevel = LogLevel.INFO;

    /* ── Timing ───────────────────────────────────── */

    private static _timers: Map<string, number> = new Map();

    /** Start a named timer. */
    static time(tag: TagName, label: string): void {
        this._timers.set(`${tag}:${label}`, Date.now());
    }

    /**
     * End a named timer and log the elapsed time at DEBUG level.
     * Returns the elapsed ms (or -1 if no matching timer).
     */
    static timeEnd(tag: TagName, label: string): number {
        const key = `${tag}:${label}`;
        const start = this._timers.get(key);
        if (start === undefined) return -1;
        this._timers.delete(key);
        const elapsed = Date.now() - start;
        this.debug(tag, `${label} completed in ${elapsed}ms`);
        return elapsed;
    }

    /* ── Level methods ────────────────────────────── */

    static debug(tag: TagName, msg: string): void {
        if (this.minLevel > LogLevel.DEBUG) return;
        const safeMessage = redactSensitiveText(msg);
        writeToFile('DEBUG', tag, safeMessage);
        if (__DEV__) console.log(`[Mei:DEBUG] [${tag}] ${safeMessage}`);
    }

    static info(tag: TagName, msg: string): void {
        if (this.minLevel > LogLevel.INFO) return;
        const safeMessage = redactSensitiveText(msg);
        writeToFile('INFO', tag, safeMessage);
        if (__DEV__) console.log(`[Mei:INFO]  [${tag}] ${safeMessage}`);
    }

    static warn(tag: TagName, msg: string): void {
        if (this.minLevel > LogLevel.WARN) return;
        const safeMessage = redactSensitiveText(msg);
        writeToFile('WARN', tag, safeMessage);
        console.warn(`[Mei:WARN]  [${tag}] ${safeMessage}`);
    }

    static error(tag: TagName, msg: string, err?: unknown): void {
        if (this.minLevel > LogLevel.ERROR) return;
        const suffix = err instanceof Error ? `: ${err.message}` : '';
        const fullMsg = redactSensitiveText(`${msg}${suffix}`);
        writeToFile('ERROR', tag, fullMsg);

        console.error(`[Mei:ERROR] [${tag}] ${fullMsg}`);
        if (__DEV__ && err instanceof Error && err.stack) {
            const safeStack = redactSensitiveText(err.stack);
            console.error(safeStack);
            writeToFile('ERROR', tag, `Stack:\n${safeStack}`);
        }
    }

    /* ── Convenience ──────────────────────────────── */

    /** Truncate a string for log output (e.g. response bodies). */
    static truncate = truncate;
}
