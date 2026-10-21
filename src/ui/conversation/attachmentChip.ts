/**
 * The chip above the message box that shows what "Ask about this" attached, with ✕ to drop it
 * before sending. Plain text: the window title and selection were written by others.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import St from 'gi://St';

import { iconButton } from '../effects.js';

export class AttachmentChip {
    readonly actor = new St.BoxLayout({ x_expand: true, visible: false, style_class: 'mei-attachment-chip' });
    private readonly _label = new St.Label({ x_expand: true, y_align: Clutter.ActorAlign.CENTER });

    constructor(onRemove: () => void) {
        this._label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        this.actor.add_child(this._label);
        const remove = iconButton('window-close-symbolic', 'Remove the attachment');
        remove.connect('clicked', () => onRemove());
        this.actor.add_child(remove);
    }

    show(text: string | null): void {
        this._label.text = text ?? '';
        this.actor.visible = text !== null;
    }
}
