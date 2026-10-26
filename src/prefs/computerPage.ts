/**
 * Settings → Using the computer (§10, decision 0022): whether Mei may look at app windows and use them,
 * accessibility (how apps show Mei their buttons and fields), and the one-time screen permission (GNOME's
 * own dialog). The setup assistant's step uses the same rows (`computerBasics`).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import type { CallOptions } from '../runtime/client.js';
import type { ComputerAllowReply, ComputerStatusReply } from '../runtime/protocol.js';
import type { RuntimeSettings } from '../runtime/settings.js';
import { COMPUTER_ABOUT, computerText } from './setupText.js';

type Call = <T>(method: string, args?: object, opts?: CallOptions) => Promise<T>;

/** GNOME's dialog waits on the person choosing. */
const ALLOW_TIMEOUT_MS = 240_000;

export function computerBasics(window: Gtk.Window, settings: RuntimeSettings, call: Call):
    { groups: Adw.PreferencesGroup[]; refresh(): Promise<void>; destroy(): void } {
    const group = new Adw.PreferencesGroup({ title: 'Using the computer', description: COMPUTER_ABOUT });
    const enabled = new Adw.SwitchRow({ title: 'Let Mei use the computer' });
    const accessibility = new Adw.ActionRow({ title: 'Accessibility', subtitle: 'Checking…' });
    const turnOn = new Gtk.Button({ label: 'Turn On', valign: Gtk.Align.CENTER, visible: false });
    accessibility.add_suffix(turnOn);
    const screen = new Adw.ActionRow({ title: 'Screen', subtitle: 'Checking…' });
    const allow = new Gtk.Button({ label: 'Allow…', valign: Gtk.Align.CENTER, visible: false });
    screen.add_suffix(allow);
    // Asked in chat, Mei asks before it looks; in Live it looks (decision 0029).
    const look = new Adw.SwitchRow({ title: 'Look at the screen without asking',
        subtitle: 'When you ask in a chat, Mei asks before it looks at your screen. In Live, it looks when you ask.' });
    for (const row of [enabled, look, accessibility, screen]) group.add(row);

    let updating = false;
    const fail = (e: unknown) => window instanceof Adw.PreferencesWindow
        ? window.add_toast(new Adw.Toast({ title: e instanceof Error ? e.message : String(e) })) : undefined;

    const show = (status: ComputerStatusReply) => {
        const text = computerText(status);
        accessibility.set_subtitle(text.accessibility);
        screen.set_subtitle(text.screen);
        turnOn.set_visible(status.available && !status.accessibility);
        allow.set_visible(status.available && !status.screen);
        enabled.set_sensitive(status.available);
    };
    const refresh = async () => {
        try {
            show(await settings.computerStatus());
        } catch (e) {
            show({ available: false, reason: e instanceof Error ? e.message : String(e), accessibility: false, screen: false });
        }
    };
    const render = () => {
        updating = true;
        enabled.set_active(settings.computerEnabled);
        look.set_active(settings.seeWithoutAsking);
        look.set_sensitive(settings.computerEnabled);
        updating = false;
    };

    enabled.connect('notify::active', () => {
        if (!updating) settings.setComputerEnabled(enabled.get_active());
    });
    look.connect('notify::active', () => {
        if (!updating) settings.setSeeWithoutAsking(look.get_active());
    });
    // A system setting, changed only when the person presses this.
    turnOn.connect('clicked', () => {
        new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' }).set_boolean('toolkit-accessibility', true);
        void refresh();
    });
    allow.connect('clicked', () => {
        allow.set_sensitive(false);
        screen.set_subtitle('Choose your screens in GNOME’s dialog, turn on “Allow Remote Interaction”, then Share');
        call<ComputerAllowReply>('ComputerAllowScreen', {}, { timeoutMs: ALLOW_TIMEOUT_MS })
            .then(reply => {
                if (!reply.ok) fail(new Error(reply.error));
            })
            .catch(fail)
            .finally(() => {
                allow.set_sensitive(true);
                void refresh();
            });
    });
    const signal = settings.connect('changed::computer', render);
    render();
    void refresh();
    return {
        groups: [group],
        refresh,
        destroy: () => settings.disconnect(signal),
    };
}

export class ComputerPage {
    readonly page: Adw.NavigationPage;
    private readonly _basics: { refresh(): Promise<void>; destroy(): void };

    constructor(window: Adw.PreferencesWindow, settings: RuntimeSettings, call: Call) {
        const prefs = new Adw.PreferencesPage();
        const basics = computerBasics(window, settings, call);
        for (const group of basics.groups) prefs.add(group);
        this._basics = basics;
        const view = new Adw.ToolbarView({ content: prefs });
        view.add_top_bar(new Adw.HeaderBar());
        this.page = new Adw.NavigationPage({ title: 'Using the computer', child: view, tag: 'computer' });
        this.page.connect('showing', () => void basics.refresh());
    }

    destroy(): void {
        this._basics.destroy();
    }
}
