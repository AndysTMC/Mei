/**
 * Panel indicator — the "Mei" button in the GNOME Shell top bar.
 *
 * Handles:
 *   - Rendering the label ("Mei")
 *   - Glint/pulse animation while waiting for AI response
 *   - Hover-to-stop icon swap during active requests
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import { Logger, Tag } from '../utils/logger.js';

const PANEL_LABEL = __DEV__ ? 'Mei  <span face="sans-serif" size="60%" alpha="80%">(DEV)</span>' : 'Mei';

export class MeiIndicator {
    private _button: St.Button;
    private _label: St.Label;
    private _glintActive: boolean = false;

    /** Called when the panel button is clicked (and not in glint mode). */
    onClicked: (() => void) | null = null;

    /** Called when the user clicks during glint mode (stop request). */
    onStopRequested: (() => void) | null = null;

    constructor() {
        this._label = new St.Label({
            style_class: 'mei-panel-label',
            y_align: Clutter.ActorAlign.CENTER,
        });

        if (__DEV__) {
            this._label.clutter_text.use_markup = true;
        }
        this._setLabelText(PANEL_LABEL);

        this._button = new St.Button({
            style_class: 'mei-panel-button',
            child: this._label,
            reactive: true,
            can_focus: true,
            track_hover: true,
        });

        this._button.connect('clicked', () => {
            if (this._glintActive) {
                this.onStopRequested?.();
                return;
            }
            this.onClicked?.();
        });

        this._button.connect('notify::hover', () => {
            if (this._glintActive) {
                if (this._button.hover) {
                    this._setLabelText('⏹');
                    this._label.remove_style_class_name('mei-panel-label');
                    this._label.add_style_class_name('mei-stop-hover-text');
                } else {
                    this._setLabelText(PANEL_LABEL);
                    this._label.remove_style_class_name('mei-stop-hover-text');
                    this._label.add_style_class_name('mei-panel-label');
                }
            }
        });

        (Main.panel as any)._centerBox.insert_child_at_index(this._button, -1);
    }

    private _setLabelText(text: string): void {
        if (__DEV__) {
            try {
                this._label.clutter_text.set_markup(text);
            } catch (e) {
                Logger.error(Tag.Indicator, `Failed to parse markup: ${text}`, e);
                this._label.set_text(text);
            }
        } else {
            this._label.set_text(text);
        }
    }

    /** The underlying St.Button actor (used as popup menu anchor). */
    get actor(): St.Button {
        return this._button;
    }

    /** Whether the glint animation is currently active. */
    get isGlinting(): boolean {
        return this._glintActive;
    }

    /* ── Glint animation ─────────────────────────────── */

    startGlint(): void {
        this._glintActive = true;
        this._button.add_style_class_name('glow');
        this._pulseGlint();
        Logger.debug(Tag.Indicator, 'Glint animation started');
    }

    stopGlint(): void {
        this._glintActive = false;
        this._button.remove_style_class_name('glow');
        this._setLabelText(PANEL_LABEL);
        this._label.remove_style_class_name('mei-stop-hover-text');
        this._label.add_style_class_name('mei-panel-label');
        this._label.remove_all_transitions();
        this._label.opacity = 255;
        Logger.debug(Tag.Indicator, 'Glint animation stopped');
    }

    private _pulseGlint(): void {
        if (!this._glintActive || !this._label) return;
        this._label.ease({
            opacity: 60,
            duration: 700,
            mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
            onComplete: () => {
                if (!this._glintActive || !this._label) return;
                this._label.ease({
                    opacity: 255,
                    duration: 700,
                    mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
                    onComplete: () => this._pulseGlint(),
                });
            },
        });
    }

    /* ── Cleanup ──────────────────────────────────────── */

    destroy(): void {
        this.stopGlint();
        if (this._button) {
            (Main.panel as any)._centerBox.remove_child(this._button);
            this._button.destroy();
        }
    }
}
