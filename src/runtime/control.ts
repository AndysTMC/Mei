/**
 * Computer use's controls in the Shell (§10.3, decision 0022): the chip in the top bar while Mei uses
 * the computer, and the kill switch.
 *
 * Stopping does three things at once. The chip goes away. The desktop worker hears `ControlRevoked`
 * straight from the Shell, a broadcast it is allowed to receive through its bus filter, with no hop
 * through the runtime, which may be frozen. And the runtime is told to kill the worker. The worker
 * trusts the signal only from the Shell's own bus name.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

import { Logger, Tag } from '../utils/logger.js';

const CONTROL_PATH = '/com/andystmc/Mei1/Control';
const CONTROL_IFACE = 'com.andystmc.Mei1.Control';
const ACTIVATE_KEYS = [Clutter.KEY_Return, Clutter.KEY_KP_Enter, Clutter.KEY_space];

export class ComputerControl {
    private _chip: PanelMenu.Button | null;

    /** `_tellRuntime(reason)`: ask the runtime to kill the desktop worker (it may not answer). */
    constructor(private readonly _tellRuntime: (reason: string) => void) {
        const chip = new PanelMenu.Button(0.5, 'Stop Mei using the computer', true);
        chip.add_style_class_name('mei-computer-chip');
        const box = new St.BoxLayout({ y_align: Clutter.ActorAlign.CENTER });
        box.add_child(new St.Icon({ icon_name: 'media-playback-stop-symbolic', style_class: 'system-status-icon' }));
        box.add_child(new St.Label({ text: 'Using the computer', y_align: Clutter.ActorAlign.CENTER }));
        chip.add_child(box);
        chip.connect('button-release-event', () => {
            this.stop('Stopped from the top bar');
            return Clutter.EVENT_STOP;
        });
        chip.connect('key-release-event', (_actor, event: Clutter.Event) => {
            if (!ACTIVATE_KEYS.includes(event.get_key_symbol())) return Clutter.EVENT_PROPAGATE;
            this.stop('Stopped from the top bar');
            return Clutter.EVENT_STOP;
        });
        chip.visible = false;
        Main.panel.addToStatusArea('mei-computer', chip, 0, 'right');
        this._chip = chip;
    }

    /** The runtime's ShowOverlay: a period of computer use began or ended. */
    show(active: boolean): void {
        if (this._chip) this._chip.visible = active;
    }

    /** The kill switch: the shortcut, or the chip. */
    stop(reason: string): void {
        this.show(false);
        this._revoke(reason);
        this._tellRuntime(reason);
    }

    destroy(): void {
        const reason = "Mei's Shell extension was turned off";
        if (this._chip?.visible) this.stop(reason);
        else this._revoke(reason); // nothing is in use: no need to wake the runtime
        this._chip?.destroy();
        this._chip = null;
    }

    private _revoke(reason: string): void {
        try {
            // A broadcast (no destination): the worker's bus filter lets exactly this one through.
            Gio.DBus.session.emit_signal(null, CONTROL_PATH, CONTROL_IFACE, 'ControlRevoked',
                new GLib.Variant('(s)', [reason]));
        } catch (e) {
            Logger.warn(Tag.Extension, `Couldn't signal the desktop worker: ${(e as Error).message}`);
        }
    }
}
