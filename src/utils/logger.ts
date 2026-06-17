/**
 * Structured logger for Mei.
 *
 * Uses the build-time `__DEV__` constant (injected by esbuild) to
 * control verbosity.  In production builds `__DEV__` is `false` and
 * esbuild tree-shakes all DEBUG/INFO paths away — zero runtime cost.
 *
 * Log format:  [Mei:LEVEL] [Tag] message
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

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

const LEVEL_LABELS: Record<LogLevel, string> = {
    [LogLevel.DEBUG]: 'DEBUG',
    [LogLevel.INFO]:  'INFO',
    [LogLevel.WARN]:  'WARN',
    [LogLevel.ERROR]: 'ERROR',
};

/** Truncate a string to `max` chars, appending `…` if clipped. */
function truncate(s: string, max: number): string {
    if (s.length <= max) return s;
    return s.slice(0, max) + '…';
}

/** Mask an API key, showing only the last 4 characters. */
export function maskKey(key: string | undefined): string {
    if (!key || key.length <= 4) return '***';
    return '***' + key.slice(-4);
}

/* ── Logger ───────────────────────────────────────── */

export class Logger {
    /**
     * Minimum level that will be printed.
     * - Dev  builds: DEBUG (show everything)
     * - Prod builds: WARN  (errors and warnings only)
     *
     * Can be overridden at runtime for ad-hoc debugging, but the
     * `__DEV__` guard means DEBUG/INFO call-sites are stripped in prod.
     */
    static minLevel: LogLevel = __DEV__ ? LogLevel.DEBUG : LogLevel.WARN;

    /* ── Timing (dev-only) ────────────────────────── */

    private static _timers: Map<string, number> = new Map();

    /** Start a named timer (dev-only). */
    static time(tag: TagName, label: string): void {
        if (!__DEV__) return;
        this._timers.set(`${tag}:${label}`, Date.now());
    }

    /**
     * End a named timer and log the elapsed time at DEBUG level.
     * Returns the elapsed ms (or -1 if no matching timer).
     */
    static timeEnd(tag: TagName, label: string): number {
        if (!__DEV__) return -1;
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
        if (!__DEV__) return;
        if (this.minLevel > LogLevel.DEBUG) return;
        console.log(`[Mei:DEBUG] [${tag}] ${msg}`);
    }

    static info(tag: TagName, msg: string): void {
        if (!__DEV__) return;
        if (this.minLevel > LogLevel.INFO) return;
        console.log(`[Mei:INFO]  [${tag}] ${msg}`);
    }

    static warn(tag: TagName, msg: string): void {
        if (this.minLevel > LogLevel.WARN) return;
        console.warn(`[Mei:WARN]  [${tag}] ${msg}`);
    }

    static error(tag: TagName, msg: string, err?: unknown): void {
        if (this.minLevel > LogLevel.ERROR) return;
        const suffix = err instanceof Error ? `: ${err.message}` : '';
        console.error(`[Mei:ERROR] [${tag}] ${msg}${suffix}`);
        if (__DEV__ && err instanceof Error && err.stack) {
            console.error(err.stack);
        }
    }

    /* ── Convenience ──────────────────────────────── */

    /** Truncate a string for log output (e.g. response bodies). */
    static truncate = truncate;
}
