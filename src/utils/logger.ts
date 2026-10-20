/**
 * Structured logger for Mei's Shell and preferences code.
 *
 * Writes to the journal through console only: the extension keeps no files of its own (the
 * runtime keeps the logs the popup shows). `__DEV__` (injected by esbuild) enables DEBUG output
 * and stack traces. Everything is redacted first.
 *
 * Log format:  [Mei:LEVEL] [Tag] message
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

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

/* ── Helpers ──────────────────────────────────────── */

/** Truncate a string to `max` chars, appending `…` if clipped. */
function truncate(s: string, max: number): string {
    if (s.length <= max) return s;
    return s.slice(0, max) + '…';
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
        if (this.minLevel > LogLevel.DEBUG || !__DEV__) return;
        console.log(`[Mei:DEBUG] [${tag}] ${redactSensitiveText(msg)}`);
    }

    static info(tag: TagName, msg: string): void {
        if (this.minLevel > LogLevel.INFO) return;
        console.log(`[Mei:INFO]  [${tag}] ${redactSensitiveText(msg)}`);
    }

    static warn(tag: TagName, msg: string): void {
        if (this.minLevel > LogLevel.WARN) return;
        console.warn(`[Mei:WARN]  [${tag}] ${redactSensitiveText(msg)}`);
    }

    static error(tag: TagName, msg: string, err?: unknown): void {
        if (this.minLevel > LogLevel.ERROR) return;
        const suffix = err instanceof Error ? `: ${err.message}` : '';
        console.error(`[Mei:ERROR] [${tag}] ${redactSensitiveText(`${msg}${suffix}`)}`);
        if (__DEV__ && err instanceof Error && err.stack) console.error(redactSensitiveText(err.stack));
    }

    /* ── Convenience ──────────────────────────────── */

    /** Truncate a string for log output (e.g. response bodies). */
    static truncate = truncate;
}
