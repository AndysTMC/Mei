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
import Atk from 'gi://Atk';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import { Logger, Tag } from '../utils/logger.js';

const PANEL_LABEL = __DEV__ ? 'Mei  <span face="sans-serif" size="60%" alpha="80%">(DEV)</span>' : 'Mei';

type PanelWithCenterBox = typeof Main.panel & {
    _centerBox: St.BoxLayout;
};

export class MeiIndicator {
    private _button: St.Button;
    private _content: St.BoxLayout;
    private _label: St.Label;
    private _stopPill: St.Bin;
    private _glintActive: boolean = false;
    private _centerBox: St.BoxLayout | null = null;
    private _stableWidth = 0;
    private _glintTimeoutId = 0;
    private _glintDimmed = false;
    private _destroyed = false;

    /** Called when the panel button is clicked (and not in glint mode). */
    onClicked: (() => void) | null = null;

    /** Called when the user clicks during glint mode (stop request). */
    onStopRequested: (() => void) | null = null;

    constructor() {
        this._label = new St.Label({
            style_class: 'mei-panel-label',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            x_expand: true,
        });

        if (__DEV__) {
            this._label.clutter_text.use_markup = true;
        }
        this._setLabelText(PANEL_LABEL);

        this._stopPill = new St.Bin({
            style_class: 'mei-stop-pill',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            visible: false,
            child: new St.Widget({
                style_class: 'mei-stop-square',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }),
        });

        this._content = new St.BoxLayout({
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            x_expand: true,
        });
        this._content.add_child(this._label);
        this._content.add_child(this._stopPill);

        this._button = new St.Button({
            style_class: 'mei-panel-button',
            child: this._content,
            reactive: true,
            can_focus: true,
            track_hover: true,
            accessible_name: 'Mei assistant',
            accessible_role: Atk.Role.PUSH_BUTTON,
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
                    this._button.accessible_name = 'Stop Mei response';
                    this._syncHoverStopSize();
                    this._showStopPill();
                } else {
                    this._setLabelText(PANEL_LABEL);
                    this._button.accessible_name = 'Mei assistant';
                    this._showLabel();
                }
            }
        });

        this._centerBox = getPanelCenterBox();
        if (this._centerBox) {
            this._centerBox.insert_child_at_index(this._button, -1);
        } else {
            Logger.error(Tag.Indicator, 'Unable to add Mei indicator: panel center box unavailable');
        }
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
        this._syncHoverStopSize();
        if (this._button.hover) {
            this._button.accessible_name = 'Stop Mei response';
            this._showStopPill();
        } else {
            this._showLabel();
        }
        this._startGlintTimer();
        Logger.debug(Tag.Indicator, 'Glint animation started');
    }

    stopGlint(): void {
        this._glintActive = false;
        this._clearGlintTimer();
        this._button.remove_style_class_name('glow');
        this._button.accessible_name = 'Mei assistant';
        this._setLabelText(PANEL_LABEL);
        this._showLabel();
        this._label.remove_all_transitions();
        this._label.opacity = 255;
        Logger.debug(Tag.Indicator, 'Glint animation stopped');
    }

    private _showLabel(): void {
        this._label.visible = true;
        this._stopPill.visible = false;
    }

    private _showStopPill(): void {
        this._label.visible = false;
        this._stopPill.visible = true;
    }

    private _syncHoverStopSize(): void {
        const [, labelWidth] = this._label.get_preferred_width(-1);
        const preferredWidth = Math.ceil(labelWidth) + 16;
        this._stableWidth = Math.max(this._stableWidth, this._button.get_width(), preferredWidth, 46);
        this._button.set_width(this._stableWidth);
        this._stopPill.set_width(Math.max(34, this._stableWidth - 16));
        this._stopPill.set_height(20);
    }

    private _startGlintTimer(): void {
        if (this._glintTimeoutId !== 0) return;

        this._glintDimmed = false;
        this._advanceGlintPulse();
        this._glintTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 700, () => {
            if (this._destroyed || !this._glintActive) {
                this._glintTimeoutId = 0;
                return GLib.SOURCE_REMOVE;
            }
            this._advanceGlintPulse();
            return GLib.SOURCE_CONTINUE;
        });
    }

    private _advanceGlintPulse(): void {
        this._glintDimmed = !this._glintDimmed;
        this._label.remove_all_transitions();

        if (!this._label.visible) {
            this._label.opacity = 255;
            return;
        }

        this._label.ease({
            opacity: this._glintDimmed ? 60 : 255,
            duration: 500,
            mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
        });
    }

    private _clearGlintTimer(): void {
        if (this._glintTimeoutId === 0) return;
        GLib.source_remove(this._glintTimeoutId);
        this._glintTimeoutId = 0;
    }

    /* ── Cleanup ──────────────────────────────────────── */

    destroy(): void {
        if (this._destroyed) return;
        this._destroyed = true;
        this.stopGlint();
        if (this._button) {
            this._centerBox?.remove_child(this._button);
            this._button.destroy();
        }
        this._centerBox = null;
    }
}

function getPanelCenterBox(): St.BoxLayout | null {
    const panel = Main.panel as unknown as Partial<PanelWithCenterBox>;
    return panel._centerBox ?? null;
}
