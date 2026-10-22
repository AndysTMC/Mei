/**
 * The bar above the message box while voice is doing something: what Mei is doing ("Listening…"),
 * what it has heard so far, and Stop. Plain text: the transcript is the person's words as heard.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import type { VoiceLine } from '../../runtime/voice.js';
import { iconButton, wrapLabel } from '../effects.js';

export class VoiceBar {
    readonly actor = new St.BoxLayout({ x_expand: true, visible: false, style_class: 'mei-voice-bar' });
    private readonly _status = new St.Label({ style_class: 'mei-voice-status' });
    private readonly _heard = wrapLabel(new St.Label({ style_class: 'mei-voice-heard', x_expand: true }));
    private readonly _stop: St.Button;

    constructor(onStop: () => void) {
        const icon = new St.Icon({ icon_name: 'audio-input-microphone-symbolic', icon_size: 14,
            y_align: Clutter.ActorAlign.CENTER, style_class: 'mei-voice-icon' });
        const text = new St.BoxLayout({ vertical: true, x_expand: true, y_align: Clutter.ActorAlign.CENTER });
        text.add_child(this._status);
        text.add_child(this._heard);
        this._stop = iconButton('media-playback-stop-symbolic', 'Stop');
        this._stop.connect('clicked', () => onStop());
        this.actor.add_child(icon);
        this.actor.add_child(text);
        this.actor.add_child(this._stop);
    }

    show(line: VoiceLine): void {
        this.actor.visible = line.visible;
        this._status.text = line.status;
        this._heard.text = line.transcript;
        this._heard.visible = Boolean(line.transcript);
        this._stop.visible = line.stoppable;
        this.actor.set_style_class_name(`mei-voice-bar${line.status === 'Listening…' ? ' listening' : ''}`);
    }
}
