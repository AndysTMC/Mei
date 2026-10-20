/**
 * The error pill under the composer: a warning, the message, and a button to copy it.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import { addClickScale, copyToClipboard, wrapLabel } from '../effects.js';
import type { SourceSet } from '../sources.js';

const COPIED_FOR_MS = 1500;

export class ErrorPill {
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-error-pill', visible: false });

    constructor(private readonly _sources: SourceSet) {}

    show(message: string, isDark: boolean): void {
        this.actor.destroy_all_children();
        const row = new St.BoxLayout({ x_expand: true, style_class: 'mei-error-row' });
        row.add_child(new St.Icon({ icon_name: 'dialog-warning-symbolic', icon_size: 14, y_align: Clutter.ActorAlign.START }));
        row.add_child(wrapLabel(new St.Label({ text: message, x_expand: true, style_class: 'mei-error-text' })));
        this.actor.add_child(row);

        const copy = new St.Button({
            label: 'Copy Error',
            style_class: 'mei-error-copy-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            accessible_name: 'Copy error details',
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        copy.connect('clicked', () => {
            copyToClipboard(message);
            copy.set_label('Copied');
            this._sources.timeout(COPIED_FOR_MS, () => {
                if (copy.get_parent()) copy.set_label('Copy Error');
                return false;
            });
        });
        addClickScale(copy);
        this.actor.add_child(copy);
        this.actor.visible = true;
        this.applyTheme(isDark);
    }

    hide(): void {
        this.actor.visible = false;
        this.actor.destroy_all_children();
    }

    applyTheme(isDark: boolean): void {
        if (!this.actor.visible) return;
        const bg = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
        this.actor.set_style(`background-color: ${bg}; color: ${isDark ? '#ffffff' : '#000000'};`);
    }
}
