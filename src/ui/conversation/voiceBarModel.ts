/**
 * The Live bar's motion (decision 0040): dots in a bar that follow how loud the person or Mei is.
 * Pure (no Shell imports), so it is tested without the Shell; voiceBar.ts draws what `frame` says.
 *
 * Each state has its own look. Every number is bounded by construction, whatever a look says: a dot
 * never stretches past the bar's inner height, and the row never spreads past its rounded ends.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

export type BarState = 'listening' | 'thinking' | 'speaking';
type Look = 'listening' | 'pausing' | 'thinking' | 'speaking';

export interface BarLook {
    /** Bar height, px. */
    bar: number;
    /** How many dots (even: a pair either side of the middle). */
    dots: number;
    /** Dot diameter, as a share of the bar's height. */
    size: number;
    /** How much of the bar's width the row takes at rest. */
    fill: number;
    /** How loud sound moves the dots: apart (a share of the room to the ends), taller (a share of the
     * room to the bar's inner height), brighter. 0–1 each. */
    spread: number;
    stretch: number;
    glow: number;
    /** The spring each dot rides on: its speed (Hz) and bounce (0 settles, 1 wobbles). */
    speed: number;
    bounce: number;
    /** How long a sound takes to reach the next pair outward, ms. */
    ripple: number;
    /** How fast the dots follow sound getting louder, and quieter, ms. */
    attack: number;
    release: number;
    /** With no sound: a slow wave through the row (0–1), and its speed (Hz). */
    wave: number;
    waveSpeed: number;
    /** Filled (Mei speaking) or outlined. */
    filled: number;
    /** Sound quieter than this (0–1) moves nothing: a room's hum, or Mei's voice at its steady
     * loudness, so the dots stay round and still most of the time and answer only to emphasis. */
    floor: number;
}

export const LOOKS: Record<Look, BarLook> = {
    listening: { bar: 22, dots: 10, size: 0.3, fill: 0.5, spread: 0.45, stretch: 0.35, glow: 0.5, speed: 2.6,
        bounce: 0.2, ripple: 40, attack: 30, release: 220, wave: 0, waveSpeed: 1, filled: 0, floor: 0.25 },
    pausing: { bar: 22, dots: 10, size: 0.28, fill: 0.46, spread: 0.08, stretch: 0.1, glow: 0.2, speed: 1.2,
        bounce: 0.05, ripple: 60, attack: 80, release: 450, wave: 0.25, waveSpeed: 0.5, filled: 0, floor: 0.25 },
    thinking: { bar: 22, dots: 6, size: 0.3, fill: 0.28, spread: 0, stretch: 0, glow: 0.6, speed: 2,
        bounce: 0.1, ripple: 0, attack: 40, release: 200, wave: 0.8, waveSpeed: 1.2, filled: 0, floor: 0 },
    speaking: { bar: 22, dots: 10, size: 0.3, fill: 0.6, spread: 0.3, stretch: 0.15, glow: 0.3, speed: 2.2,
        bounce: 0.15, ripple: 30, attack: 40, release: 260, wave: 0, waveSpeed: 1, filled: 1, floor: 0.45 },
};

/** The tallest bar: the drawing's height, so changing state never moves what's around it. */
export const BAR_MAX = Math.max(...Object.values(LOOKS).map(l => l.bar));
const MAX_DOTS = Math.max(...Object.values(LOOKS).map(l => l.dots));
/** Listening this quiet this long looks like a pause. */
const PAUSE_LEVEL = 0.06;
const PAUSE_MS = 500;
/** How long a look takes to become the next one, ms. */
const BLEND_MS = 160;
/** The microphone's levels play back this far behind at most: more queued means a hiccup, start over. */
const MIC_LAG_MS = 300;

export interface Dot {
    x: number;
    width: number;
    height: number;
    alpha: number;
}

export interface Frame {
    /** The bar: centred vertically in a drawing BAR_MAX tall, the drawing's full width. */
    height: number;
    filled: number;
    dots: Dot[];
}

interface Spring {
    e: number;
    v: number;
    shown: number;
}

export class VoiceBarModel {
    private _state: BarState;
    private _look: BarLook;
    /** Levels to play, each at its time (ms, the caller's clock). */
    private _queue: { at: number; level: number }[] = [];
    private _queuedTo = 0;
    /** The smoothed level over the last second, for the ripple. */
    private _history: { at: number; env: number }[] = [];
    private _env = 0;
    private _quietSince: number | null = null;
    private _last: number | null = null;
    private readonly _springs: Spring[] = Array.from({ length: MAX_DOTS }, () => ({ e: 0, v: 0, shown: 0 }));

    /** `state`: what voice is doing already, so a bar shown mid-reply starts in its look. */
    constructor(private readonly _still = false, state: BarState = 'listening') {
        this._state = state;
        this._look = { ...LOOKS[state] };
    }

    get state(): BarState {
        return this._state;
    }

    setState(state: BarState): void {
        if (state === this._state) return;
        this._state = state;
        this._queue = []; // the other side's sound doesn't carry over
        this._queuedTo = 0;
        this._quietSince = null;
    }

    /** How loud, every `stepMs`, starting now (the person) or as a sentence starts (Mei). Only the
     * current state's source moves the dots. */
    push(source: 'mic' | 'mei', levels: number[], stepMs: number, now: number): void {
        if ((source === 'mic') !== (this._state === 'listening') || this._state === 'thinking') return;
        let from = Math.max(now, this._queuedTo);
        if (source === 'mic' && from - now > MIC_LAG_MS) from = now;
        levels.forEach((level, i) => this._queue.push({ at: from + i * stepMs, level: clamp01(level) }));
        this._queuedTo = from + levels.length * stepMs;
    }

    /** Where everything is at `now` (ms) in a drawing `width` px wide. */
    frame(now: number, width: number): Frame {
        const dt = this._last === null ? 0 : Math.min(0.05, Math.max(0, (now - this._last) / 1000));
        this._last = now;
        const level = this._levelAt(now);
        const target = LOOKS[this._lookName(level, now)];
        const blend = dt ? 1 - Math.exp(-dt * 1000 / BLEND_MS) : 1;
        const look = this._look;
        for (const key of Object.keys(target) as (keyof BarLook)[]) look[key] += (target[key] - look[key]) * blend;

        const heard = clamp01((level - look.floor) / Math.max(0.05, 1 - look.floor));
        const tau = (heard > this._env ? look.attack : look.release) / 1000;
        this._env += (heard - this._env) * (dt ? 1 - Math.exp(-dt / Math.max(0.005, tau)) : 1);
        this._history.push({ at: now, env: this._env });
        while (this._history.length > 1 && this._history[0].at < now - 1000) this._history.shift();

        return { height: look.bar, filled: clamp01(look.filled), dots: this._dots(now, dt, width, look) };
    }

    private _dots(now: number, dt: number, width: number, look: BarLook): Dot[] {
        const t = now / 1000;
        const h = look.bar;
        const diameter = h * look.size;
        const r = diameter / 2;
        // A dot's inner room: the bar's height less a margin, so a stretched dot never touches its edge.
        const tallest = Math.max(diameter, h - 2 * Math.max(2, h * 0.14));
        const pairs = Math.max(1, look.dots / 2);
        const gap = (width * look.fill) / Math.max(2, look.dots);
        // The row widens evenly: the outer pair goes as far as the bar's rounded end, the others in proportion.
        const outerRest = (pairs - 0.5) * gap;
        const reach = Math.max(0, width / 2 - h / 2 - outerRest) / Math.max(0.5, pairs - 0.5);
        const omega = 2 * Math.PI * look.speed;
        const zeta = 1.15 - look.bounce;
        const shownPairs = Math.round(look.dots / 2);
        const dots: Dot[] = [];
        for (let k = 0; k < MAX_DOTS / 2; k++) {
            const heard = this._envAt(now - k * look.ripple) * (0.6 + 0.4 * Math.sin(((k + 1) / pairs) * Math.PI * 0.85));
            const wave = look.wave * (0.5 + 0.5 * Math.sin(t * look.waveSpeed * 2 * Math.PI - k * 0.8));
            for (const side of [-1, 1]) {
                const s = this._springs[k * 2 + (side > 0 ? 1 : 0)];
                s.shown += ((k < shownPairs ? 1 : 0) - s.shown) * (dt ? 1 - Math.exp(-dt / 0.12) : 1);
                if (this._still) {
                    s.e = heard;
                    s.v = 0;
                } else if (dt) {
                    s.v += (omega * omega * (heard - s.e) - 2 * zeta * omega * s.v) * dt;
                    s.e += s.v * dt;
                }
                if (s.shown < 0.01) continue;
                const moved = soft(s.e);
                const lift = this._still ? 0 : Math.min(1, moved * look.stretch); // the wave only brightens
                const offset = (k + 0.5) * gap + (this._still ? 0 : moved * look.spread * reach * (k + 0.5));
                const lit = Math.min(1, moved * look.glow * 1.6 + wave * 0.6 + (1 - look.glow) * 0.6);
                const alpha = 0.5 + 0.5 * lit;
                dots.push({
                    x: width / 2 + side * Math.min(offset, width / 2 - h / 2),
                    width: diameter,
                    height: diameter + (tallest - diameter) * lift,
                    alpha: (alpha + (1 - alpha) * clamp01(look.filled)) * s.shown,
                });
            }
        }
        return dots.filter(d => r > 0 && d.alpha > 0);
    }

    private _lookName(level: number, now: number): Look {
        if (this._state !== 'listening') return this._state;
        if (level > PAUSE_LEVEL) this._quietSince = null;
        else this._quietSince ??= now;
        return this._quietSince !== null && now - this._quietSince >= PAUSE_MS ? 'pausing' : 'listening';
    }

    private _levelAt(now: number): number {
        while (this._queue.length > 1 && this._queue[1].at <= now) this._queue.shift();
        const head = this._queue[0];
        if (!head || head.at > now) return 0;
        // The last level holds only for its own step: past the end of what was sent, it's quiet.
        return now - head.at <= 60 || this._queue.length > 1 ? head.level : 0;
    }

    private _envAt(at: number): number {
        for (let i = this._history.length - 1; i >= 0; i--)
            if (this._history[i].at <= at) return this._history[i].env;
        return this._history[0]?.env ?? 0;
    }
}

function clamp01(x: number): number {
    return Math.min(1, Math.max(0, x));
}

/** 0 at rest, approaching 1 with a soft knee, so a spring's overshoot nears the limit without passing it. */
function soft(x: number): number {
    return Math.min(1, Math.tanh(2 * Math.max(0, x)) / Math.tanh(2));
}
