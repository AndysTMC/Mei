/**
 * Small widget helpers shared by the popup's parts.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import St from 'gi://St';

/** Shrink the button slightly while pressed, as feedback that the click landed. */
export function addClickScale(button: St.Button): void {
    const scaleTo = (scale: number) => button.ease({
        scaleX: scale,
        scaleY: scale,
        duration: 80,
        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
    });
    button.connect('button-press-event', () => {
        button.set_pivot_point(0.5, 0.5);
        scaleTo(0.95);
        return Clutter.EVENT_PROPAGATE;
    });
    button.connect('button-release-event', () => {
        scaleTo(1.0);
        return Clutter.EVENT_PROPAGATE;
    });
    button.connect('clicked', () => scaleTo(1.0));
    button.connect('leave-event', () => {
        scaleTo(1.0);
        return Clutter.EVENT_PROPAGATE;
    });
}

/** A small icon button in the popup's style, with click feedback. */
export function iconButton(iconName: string, accessibleName: string, iconSize = 14): St.Button {
    const button = new St.Button({
        style_class: 'mei-icon-btn',
        can_focus: true,
        reactive: true,
        track_hover: true,
        accessible_name: accessibleName,
        accessible_role: Atk.Role.PUSH_BUTTON,
        child: new St.Icon({ icon_name: iconName, icon_size: iconSize }),
    });
    addClickScale(button);
    return button;
}

/** Let a label wrap at word boundaries instead of ellipsizing. */
export function wrapLabel<T extends St.Label>(label: T): T {
    label.clutter_text.set_line_wrap(true);
    label.clutter_text.set_line_wrap_mode(Pango.WrapMode.WORD);
    label.clutter_text.set_ellipsize(Pango.EllipsizeMode.NONE);
    return label;
}

/** Put `text` on the clipboard. */
export function copyToClipboard(text: string): void {
    St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, text);
}
