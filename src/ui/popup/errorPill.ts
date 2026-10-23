/**
 * The notice under the input area: a warning and the message, with Close always, an action when
 * there's a way forward (Set up, …), and Copy for an error worth reporting. The controller also
 * clears it when its cause is gone.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import { addClickScale, copyToClipboard, iconButton, wrapLabel } from '../effects.js';
import type { SourceSet } from '../sources.js';

const COPIED_FOR_MS = 1500;

export interface NoticeAction {
    label: string;
    run(): void;
}

export class ErrorPill {
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-error-pill', visible: false });
    /** What the notice is about ('voice', 'connection', …), so its cause going away can clear it. */
    source = '';

    constructor(private readonly _sources: SourceSet) {}

    show(message: string, isDark: boolean, options: { action?: NoticeAction; source?: string } = {}): void {
        this.actor.destroy_all_children();
        this.source = options.source ?? '';
        const row = new St.BoxLayout({ x_expand: true, style_class: 'mei-error-row' });
        row.add_child(new St.Icon({ icon_name: 'dialog-warning-symbolic', icon_size: 14, y_align: Clutter.ActorAlign.START }));
        row.add_child(wrapLabel(new St.Label({ text: message, x_expand: true, style_class: 'mei-error-text' })));
        const close = iconButton('window-close-symbolic', 'Dismiss', 12);
        close.y_align = Clutter.ActorAlign.START;
        close.connect('clicked', () => this.hide());
        row.add_child(close);
        this.actor.add_child(row);

        const buttons = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-buttons' });
        if (options.action) {
            const { label, run } = options.action;
            const act = this._button(label, label);
            act.add_style_class_name('suggested');
            act.connect('clicked', () => {
                this.hide();
                run();
            });
            buttons.add_child(act);
        } else {
            const copy = this._button('Copy', 'Copy the error');
            copy.connect('clicked', () => {
                copyToClipboard(message);
                copy.set_label('Copied');
                this._sources.timeout(COPIED_FOR_MS, () => {
                    if (copy.get_parent()) copy.set_label('Copy');
                    return false;
                });
            });
            buttons.add_child(copy);
        }
        this.actor.add_child(buttons);
        this.actor.visible = true;
        this.applyTheme(isDark);
    }

    private _button(label: string, accessibleName: string): St.Button {
        const button = new St.Button({ label, style_class: 'mei-card-btn', can_focus: true, reactive: true,
            track_hover: true, accessible_name: accessibleName, accessible_role: Atk.Role.PUSH_BUTTON });
        addClickScale(button);
        return button;
    }

    hide(): void {
        this.actor.visible = false;
        this.source = '';
        this.actor.destroy_all_children();
    }

    applyTheme(isDark: boolean): void {
        if (!this.actor.visible) return;
        const bg = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
        this.actor.set_style(`background-color: ${bg}; color: ${isDark ? '#ffffff' : '#000000'};`);
    }
}
