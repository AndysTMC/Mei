/**
 * Settings → Approvals → Always allowed: what the person told Mei it may always do (persistent
 * grants, §13.3), each revocable. Settings may revoke grants but never create them: only the Shell
 * can approve (§13.7).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import type { GrantView } from '../runtime/protocol.js';
import type { RuntimeSettings } from '../runtime/settings.js';

export class GrantsPage {
    readonly page: Adw.NavigationPage;
    private readonly _group = new Adw.PreferencesGroup({
        description: 'You chose “Always” on these. Revoke one and Mei asks again next time.',
    });
    private _rows: Gtk.Widget[] = [];

    constructor(private readonly _window: Adw.PreferencesWindow, private readonly _settings: RuntimeSettings) {
        const prefs = new Adw.PreferencesPage();
        prefs.add(this._group);
        const view = new Adw.ToolbarView({ content: prefs });
        view.add_top_bar(new Adw.HeaderBar());
        this.page = new Adw.NavigationPage({ title: 'Always allowed', child: view, tag: 'grants' });
        this.page.connect('shown', () => void this._load());
    }

    private async _load(): Promise<void> {
        let grants: GrantView[];
        try {
            grants = await this._settings.listGrants();
        } catch (e) {
            this._show([], `Couldn’t load them: ${e instanceof Error ? e.message : String(e)}`);
            return;
        }
        this._show(grants, grants.length ? '' : 'Nothing yet.');
    }

    private _show(grants: GrantView[], note: string): void {
        for (const row of this._rows) this._group.remove(row);
        this._rows = [];
        if (note) this._add(new Adw.ActionRow({ title: note }));
        for (const grant of grants) {
            const when = GLib.DateTime.new_from_unix_local(Math.floor(grant.created_at / 1000)).format('%x') ?? '';
            const row = new Adw.ActionRow({ title: grant.description, subtitle: `Since ${when}` });
            const revoke = new Gtk.Button({ label: 'Revoke', valign: Gtk.Align.CENTER, css_classes: ['destructive-action'] });
            revoke.connect('clicked', () => {
                revoke.set_sensitive(false);
                this._settings.revokeGrant(grant.id).then(() => this._load()).catch(e => {
                    revoke.set_sensitive(true);
                    this._window.add_toast(new Adw.Toast({ title: `Couldn’t revoke it: ${(e as Error).message}` }));
                });
            });
            row.add_suffix(revoke);
            this._add(row);
        }
    }

    private _add(row: Gtk.Widget): void {
        this._group.add(row);
        this._rows.push(row);
    }
}
