/**
 * The Live bar (decision 0040): in Live, under the buttons, dots that follow how loud the person or
 * Mei is. The motion is voiceBarModel's; this draws it, in the popup's own text colour, only while
 * shown. With animations off in GNOME, the dots stay put and only brighten.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Cairo from 'cairo';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import { BAR_MAX, VoiceBarModel, type BarState, type Frame } from './voiceBarModel.js';

/** Room for the outline's 1px stroke, so the bar's edges line up with the buttons above. */
const MARGIN = 0.5;

export class VoiceBar {
    readonly actor: St.DrawingArea;
    private _model: VoiceBarModel;
    private _timeline: Clutter.Timeline | null = null;
    private _frame: Frame | null = null;

    constructor() {
        this.actor = new St.DrawingArea({ style_class: 'mei-voice-bar', x_expand: true, height: BAR_MAX + 2,
            visible: false, accessible_name: 'Listening' });
        this._model = new VoiceBarModel(!St.Settings.get().enable_animations);
        this.actor.connect('repaint', () => this._draw());
        this.actor.connect('notify::mapped', () => this._sync());
        this.actor.connect('destroy', () => this._stop());
    }

    /** What voice is doing; the accessible name says it in words. */
    setState(state: BarState, label: string): void {
        this._model.setState(state);
        this.actor.accessible_name = label;
    }

    show(visible: boolean): void {
        // Shown again: the motion starts over, in the state voice is in now.
        if (visible && !this.actor.visible)
            this._model = new VoiceBarModel(!St.Settings.get().enable_animations, this._model.state);
        this.actor.visible = visible;
        this._sync();
    }

    /** How loud, every `stepMs`, from the runtime (`voice.level`). */
    push(source: 'mic' | 'mei', levels: number[], stepMs: number): void {
        this._model.push(source, levels, stepMs, GLib.get_monotonic_time() / 1000);
    }

    private _sync(): void {
        if (this.actor.visible && this.actor.mapped) this._start();
        else this._stop();
    }

    private _start(): void {
        if (this._timeline) return;
        this._timeline = new Clutter.Timeline({ actor: this.actor, duration: 1000, repeat_count: -1 });
        this._timeline.connect('new-frame', () => {
            // The allocation: the surface's size is only known while painting (0 here).
            this._frame = this._model.frame(GLib.get_monotonic_time() / 1000, Math.max(0, this.actor.width - 2 * MARGIN));
            this.actor.queue_repaint();
        });
        this._timeline.start();
    }

    private _stop(): void {
        this._timeline?.stop();
        this._timeline = null;
    }

    private _draw(): void {
        const frame = this._frame;
        const cr = this.actor.get_context();
        const [width, height] = this.actor.get_surface_size();
        if (frame) {
            const fg = this.actor.get_theme_node().get_foreground_color();
            const [r, g, b] = [fg.red / 255, fg.green / 255, fg.blue / 255];
            // On half pixels, so the 1px outline is crisp rather than spread over two rows.
            const top = Math.round((height - frame.height) / 2) + MARGIN;
            pill(cr, MARGIN, top, width - 2 * MARGIN, frame.height - 2 * MARGIN);
            // Outlined while the person talks or Mei thinks; filled, its dots cut out, while Mei speaks.
            cr.setSourceRGBA(r, g, b, 0.28 * (1 - frame.filled));
            cr.setLineWidth(1);
            cr.strokePreserve();
            cr.setSourceRGBA(r, g, b, 0.92 * frame.filled);
            cr.fill();
            for (const dot of frame.dots) {
                const x = MARGIN + dot.x - dot.width / 2;
                const y = height / 2 - dot.height / 2;
                pill(cr, x, y, dot.width, dot.height);
                cr.setOperator(Cairo.Operator.OVER);
                cr.setSourceRGBA(r, g, b, dot.alpha * (1 - frame.filled));
                cr.fillPreserve();
                cr.setOperator(Cairo.Operator.DEST_OUT);
                cr.setSourceRGBA(0, 0, 0, dot.alpha * frame.filled);
                cr.fill();
            }
        }
        cr.$dispose();
    }
}

/** A capsule: a rectangle whose short sides are half circles. */
function pill(cr: Cairo.Context, x: number, y: number, w: number, h: number): void {
    const r = Math.min(w, h) / 2;
    cr.newPath();
    cr.arc(x + w - r, y + r, r, -Math.PI / 2, 0);
    cr.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
    cr.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
    cr.arc(x + r, y + r, r, Math.PI, 1.5 * Math.PI);
    cr.closePath();
}
