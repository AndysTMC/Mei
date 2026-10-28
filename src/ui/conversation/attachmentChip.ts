/**
 * The chip above the message box that shows what "Ask about this" or a drop attached, with ✕ to drop
 * it before sending. Clicking it opens what it names on the large page (decision 0034). Plain text:
 * the window title and selection were written by others.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import St from 'gi://St';

import { iconButton } from '../effects.js';

export class AttachmentChip {
    readonly actor = new St.BoxLayout({ x_expand: true, visible: false, style_class: 'mei-attachment-chip' });
    private readonly _label = new St.Label({ x_expand: true, y_align: Clutter.ActorAlign.CENTER });
    private readonly _open: St.Button;

    constructor(onRemove: () => void, onOpen: () => void) {
        this._label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        this._open = new St.Button({ child: this._label, x_expand: true, x_align: Clutter.ActorAlign.FILL, can_focus: true,
            reactive: true, track_hover: true, style_class: 'mei-attachment-open', accessible_name: 'Open the attachment',
            accessible_role: Atk.Role.LINK });
        this._open.connect('clicked', () => onOpen());
        this.actor.add_child(this._open);
        const remove = iconButton('window-close-symbolic', 'Remove the attachment');
        remove.connect('clicked', () => onRemove());
        this.actor.add_child(remove);
    }

    /** `openable`: whether there is something to open (a bare window title isn't). */
    show(text: string | null, openable = false): void {
        this._label.text = text ?? '';
        this._open.reactive = openable;
        this.actor.visible = text !== null;
    }
}
