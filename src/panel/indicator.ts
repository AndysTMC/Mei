/**
 * Panel indicator — the "Mei" button in the GNOME Shell top bar.
 *
 * Handles:
 *   - Rendering the label ("Mei")
 *   - Glint/pulse animation while a hidden popup is waiting for AI response
 *   - Optional hover-to-stop icon swap during active requests
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Atk from 'gi://Atk';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

import { Logger, Tag } from '../utils/logger.js';

const VOICE_MARKS: Record<string, string> = {
    listening: 'audio-input-microphone-symbolic', thinking: 'content-loading-symbolic', speaking: 'audio-volume-high-symbolic',
};

const PANEL_LABEL = __DEV__ ? 'Mei  <span face="sans-serif" size="60%" alpha="80%">(DEV)</span>' : 'Mei';

type PanelWithCenterBox = typeof Main.panel & {
    _centerBox: St.BoxLayout;
};

export class MeiIndicator {
    private _button: St.Button;
    private _content: St.BoxLayout;
    private _label: St.Label;
    private _stopPill: St.Bin;
    /** Beside the label while voice listens (a mic) or speaks (a speaker); hidden otherwise. */
    private _voiceMark = new St.Icon({ style_class: 'mei-panel-voice', visible: false, y_align: Clutter.ActorAlign.CENTER });
    private _activityActive: boolean = false;
    private _stopControlVisible: boolean = false;
    private _centerBox: St.BoxLayout | null = null;
    /** Holds the button when the panel's center box isn't reachable (see _placeInPanel). */
    private _statusArea: PanelMenu.Button | null = null;
    private _stableWidth = 0;
    private _glintTimeoutId = 0;
    private _glintDimmed = false;
    private _destroyed = false;

    /** Called when the panel button is clicked without the stop control active. */
    onClicked: (() => void) | null = null;

    /** Called when the user clicks while the stop control is active. */
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
        this._content.add_child(this._voiceMark);
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
            if (this._stopControlVisible) {
                this.onStopRequested?.();
                return;
            }
            this.onClicked?.();
        });

        this._button.connect('notify::hover', () => {
            if (this._stopControlVisible && this._button.hover) {
                this._button.accessible_name = 'Stop Mei response';
                this._syncHoverStopSize();
                this._showStopPill();
                return;
            }
            this._button.accessible_name = 'Mei assistant';
            this._showLabel();
        });

        this._placeInPanel();
    }

    /**
     * The button sits at the end of the panel's center box, next to the clock. That box is private
     * Shell API; if a Shell release renames it, fall back to the public status area (center), so
     * Mei moves a little but never disappears.
     */
    private _placeInPanel(): void {
        this._centerBox = getPanelCenterBox();
        if (this._centerBox) {
            this._centerBox.insert_child_at_index(this._button, -1);
            return;
        }
        Logger.warn(Tag.Indicator, 'The panel center box is unavailable; adding Mei through the status area instead');
        this._statusArea = new PanelMenu.Button(0.5, 'Mei', true);
        this._statusArea.add_child(this._button);
        Main.panel.addToStatusArea('mei', this._statusArea, -1, 'center');
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
        return this._activityActive;
    }

    /* ── Glint animation ─────────────────────────────── */

    setActivity(active: boolean): void {
        if (this._activityActive === active) return;

        this._activityActive = active;
        if (active) {
            this._button.add_style_class_name('glow');
            this._startGlintTimer();
            Logger.debug(Tag.Indicator, 'Activity animation started');
        } else {
            this._clearGlintTimer();
            this._button.remove_style_class_name('glow');
            this._label.remove_all_transitions();
            this._label.opacity = 255;
            Logger.debug(Tag.Indicator, 'Activity animation stopped');
        }
    }

    /** Listening, thinking and speaking show as a small mark beside the label (§18.2's voice orb, kept
     * quiet): with the shortcut or "Hey Mei", the top bar is all there is until Mei answers. */
    setVoiceState(state: string): void {
        const icon = VOICE_MARKS[state] ?? '';
        this._voiceMark.visible = icon !== '' && !this._stopPill.visible;
        if (icon) this._voiceMark.icon_name = icon;
    }

    setStopControlVisible(visible: boolean): void {
        if (this._stopControlVisible === visible) return;

        this._stopControlVisible = visible;
        if (visible) {
            this._button.add_style_class_name('stop-active');
            this._syncHoverStopSize();
            if (this._button.hover) {
                this._button.accessible_name = 'Stop Mei response';
                this._showStopPill();
                return;
            }
        } else {
            this._button.remove_style_class_name('stop-active');
        }

        this._button.accessible_name = 'Mei assistant';
        this._showLabel();
    }

    startGlint(): void {
        this.setActivity(true);
        this.setStopControlVisible(true);
    }

    stopGlint(): void {
        this.setStopControlVisible(false);
        this.setActivity(false);
        this._button.accessible_name = 'Mei assistant';
        this._setLabelText(PANEL_LABEL);
        this._showLabel();
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
            if (this._destroyed || !this._activityActive) {
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
        if (this._statusArea) {
            this._statusArea.destroy(); // takes the button with it
        } else {
            this._centerBox?.remove_child(this._button);
            this._button.destroy();
        }
        this._centerBox = null;
        this._statusArea = null;
    }
}

function getPanelCenterBox(): St.BoxLayout | null {
    // Dev builds can pretend it's gone, to test the fallback (MEI_DEV_NO_CENTER_BOX=1).
    if (__DEV__ && GLib.getenv('MEI_DEV_NO_CENTER_BOX') === '1') return null;
    const panel = Main.panel as unknown as Partial<PanelWithCenterBox>;
    return panel._centerBox ?? null;
}
