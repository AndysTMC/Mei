/**
 * Structured logger for Mei.
 *
 * Uses the build-time `__DEV__` constant (injected by esbuild) to
 * control verbosity.  In production builds `__DEV__` is `false` and
 * esbuild tree-shakes all DEBUG/INFO paths away — zero runtime cost.
 *
 * Log format:  [Mei:LEVEL] [Tag] message
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Gio from 'gi://Gio';

import { ensureLogDir, LOG_FILE, setPrivateMode } from './logFile.js';

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

/* ── Helpers ──────────────────────────────────────── */

/** Truncate a string to `max` chars, appending `…` if clipped. */
function truncate(s: string, max: number): string {
    if (s.length <= max) return s;
    return s.slice(0, max) + '…';
}

/** Mask an API key, showing only the last 4 characters. */
export function maskKey(key: string | undefined): string {
    if (!key || key.length <= 8) return '***';
    return '***' + key.slice(-4);
}

/* ── File Logging ─────────────────────────────────── */

function writeToFile(level: string, tag: string, msg: string): void {
    try {
        ensureLogDir();
        const file = Gio.File.new_for_path(LOG_FILE);
        const out = file.append_to(Gio.FileCreateFlags.NONE, null);

        const now = new Date();
        const timestamp = now.toISOString();
        const line = `[${timestamp}] [${level}] [${tag}] ${msg}\n`;

        out.write_all(new TextEncoder().encode(line), null);
        out.close(null);
        setPrivateMode(LOG_FILE, 0o600);
    } catch (e) {
        console.error(`[Mei:ERROR] Failed to write log to file: ${e}`);
    }
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
        writeToFile('DEBUG', tag, msg);
        if (__DEV__) console.log(`[Mei:DEBUG] [${tag}] ${msg}`);
    }

    static info(tag: TagName, msg: string): void {
        if (this.minLevel > LogLevel.INFO) return;
        writeToFile('INFO', tag, msg);
        if (__DEV__) console.log(`[Mei:INFO]  [${tag}] ${msg}`);
    }

    static warn(tag: TagName, msg: string): void {
        if (this.minLevel > LogLevel.WARN) return;
        writeToFile('WARN', tag, msg);
        console.warn(`[Mei:WARN]  [${tag}] ${msg}`);
    }

    static error(tag: TagName, msg: string, err?: unknown): void {
        if (this.minLevel > LogLevel.ERROR) return;
        const suffix = err instanceof Error ? `: ${err.message}` : '';
        const fullMsg = `${msg}${suffix}`;
        writeToFile('ERROR', tag, fullMsg);

        console.error(`[Mei:ERROR] [${tag}] ${fullMsg}`);
        if (__DEV__ && err instanceof Error && err.stack) {
            console.error(err.stack);
            writeToFile('ERROR', tag, `Stack:\n${err.stack}`);
        }
    }

    /* ── Convenience ──────────────────────────────── */

    /** Truncate a string for log output (e.g. response bodies). */
    static truncate = truncate;
}
