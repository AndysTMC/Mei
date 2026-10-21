/**
 * Settings → Memory (§17): whether Mei remembers, what waits for review, and everything it
 * remembers, each one searchable, pinnable, local-only, or deletable; and "Forget everything".
 *
 * Keeping a memory from here announces it with a notification ("Mei will now remember"): the
 * runtime can't tell Settings from another program, and a memory goes into every future prompt.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';

import type { MemoryView } from '../runtime/protocol.js';
import type { RuntimeSettings } from '../runtime/settings.js';
import { memorySubtitle } from './setupText.js';
import { buildMemoryRows, type Row } from './rows.js';

export class MemoryPage {
    readonly page: Adw.NavigationPage;
    private readonly _review = new Adw.PreferencesGroup({
        title: 'To review',
        description: 'Mei found these in something it read, or worked them out while automatic saving was off. '
            + 'Nothing here is used until you keep it.',
    });
    private readonly _remembered = new Adw.PreferencesGroup({ title: 'Remembered' });
    private readonly _search = new Gtk.SearchEntry({ placeholder_text: 'Search', valign: Gtk.Align.CENTER });
    private readonly _toggles: Row<Adw.SwitchRow>[];
    private _rows: [Adw.PreferencesGroup, Gtk.Widget][] = [];
    private _loading = 0;

    constructor(private readonly _window: Adw.PreferencesWindow, private readonly _settings: RuntimeSettings) {
        const prefs = new Adw.PreferencesPage();
        const toggles = new Adw.PreferencesGroup();
        this._toggles = buildMemoryRows(_settings);
        for (const t of this._toggles) toggles.add(t.row);
        prefs.add(toggles);
        prefs.add(this._review);
        this._remembered.set_header_suffix(this._search);
        prefs.add(this._remembered);

        const danger = new Adw.PreferencesGroup();
        const forgetAll = new Adw.ButtonRow({ title: 'Forget everything', css_classes: ['destructive-action'] });
        forgetAll.connect('activated', () => this._confirmForgetAll());
        danger.add(forgetAll);
        prefs.add(danger);

        this._search.connect('search-changed', () => void this._load());
        const view = new Adw.ToolbarView({ content: prefs });
        view.add_top_bar(new Adw.HeaderBar());
        this.page = new Adw.NavigationPage({ title: 'Memory', child: view, tag: 'memory' });
        this.page.connect('shown', () => void this._load());
    }

    destroy(): void {
        for (const t of this._toggles) t.destroy();
    }

    private async _load(): Promise<void> {
        const loading = ++this._loading; // a newer search wins over a slower older one
        const query = this._search.get_text().trim();
        try {
            const [pending, listed] = await Promise.all([
                this._settings.memories('', 'pending_review'),
                this._settings.memories(query, 'active'),
            ]);
            if (loading !== this._loading) return;
            this._show(pending.memories, listed.memories, query);
        } catch (e) {
            if (loading !== this._loading) return;
            this._clear();
            this._add(this._remembered, new Adw.ActionRow({ title: `Couldn’t load them: ${errorText(e)}` }));
        }
    }

    private _show(pending: MemoryView[], active: MemoryView[], query: string): void {
        this._clear();
        this._review.set_visible(pending.length > 0);
        for (const memory of pending) this._add(this._review, this._pendingRow(memory));
        if (!active.length) {
            this._add(this._remembered, new Adw.ActionRow({
                title: query ? 'Nothing matches.' : 'Nothing yet. Tell Mei “remember that…”, or let it learn as you work.',
            }));
        }
        for (const memory of active) this._add(this._remembered, this._activeRow(memory));
    }

    private _pendingRow(memory: MemoryView): Adw.ActionRow {
        const row = new Adw.ActionRow({ title: memory.text, subtitle: memorySubtitle(memory), title_lines: 3 });
        const keep = new Gtk.Button({ label: 'Keep', valign: Gtk.Align.CENTER, css_classes: ['suggested-action'] });
        const discard = new Gtk.Button({ label: 'Discard', valign: Gtk.Align.CENTER });
        keep.connect('clicked', () => this._act([keep, discard], () => this._settings.updateMemory(memory.id, { status: 'active' })));
        discard.connect('clicked', () => this._act([keep, discard], () => this._settings.forgetMemory(memory.id)));
        row.add_suffix(keep);
        row.add_suffix(discard);
        return row;
    }

    private _activeRow(memory: MemoryView): Adw.ActionRow {
        const row = new Adw.ActionRow({ title: memory.text, subtitle: memorySubtitle(memory), title_lines: 3 });
        const pin = new Gtk.ToggleButton({
            icon_name: 'view-pin-symbolic', active: memory.pinned, valign: Gtk.Align.CENTER, css_classes: ['flat'],
            tooltip_text: 'Pinned: used in every task, not only when it seems relevant',
        });
        const local = new Gtk.ToggleButton({
            icon_name: 'computer-symbolic', active: memory.sensitivity === 'local_only', valign: Gtk.Align.CENTER,
            css_classes: ['flat'], tooltip_text: 'Local only: never sent to a cloud model',
        });
        const remove = new Gtk.Button({
            icon_name: 'user-trash-symbolic', valign: Gtk.Align.CENTER, css_classes: ['flat'], tooltip_text: 'Forget this',
        });
        pin.connect('toggled', () => this._act([pin], () => this._settings.updateMemory(memory.id, { pinned: pin.get_active() })));
        local.connect('toggled', () => this._act([local], () => this._settings.updateMemory(memory.id,
            { sensitivity: local.get_active() ? 'local_only' : 'normal' })));
        remove.connect('clicked', () => this._act([pin, local, remove], () => this._settings.forgetMemory(memory.id)));
        for (const w of [pin, local, remove]) row.add_suffix(w);
        return row;
    }

    /** Run a change with its controls disabled, then show the list as the runtime has it now. */
    private _act(controls: Gtk.Widget[], change: () => Promise<void>): void {
        for (const c of controls) c.set_sensitive(false);
        change()
            .catch(e => this._window.add_toast(new Adw.Toast({ title: `Couldn’t change it: ${errorText(e)}` })))
            .finally(() => void this._load());
    }

    private _confirmForgetAll(): void {
        const dialog = new Adw.AlertDialog({
            heading: 'Forget everything?',
            body: 'Mei deletes every memory, including those waiting for review. This can’t be undone.',
        });
        dialog.add_response('cancel', 'Cancel');
        dialog.add_response('forget', 'Forget everything');
        dialog.set_response_appearance('forget', Adw.ResponseAppearance.DESTRUCTIVE);
        dialog.set_default_response('cancel');
        dialog.set_close_response('cancel');
        dialog.connect('response', (_d: Adw.AlertDialog, response: string) => {
            if (response !== 'forget') return;
            this._settings.forgetEverything()
                .then(n => this._window.add_toast(new Adw.Toast({ title: `Forgot ${n} ${n === 1 ? 'memory' : 'memories'}` })))
                .catch(e => this._window.add_toast(new Adw.Toast({ title: `Couldn’t forget them: ${errorText(e)}` })))
                .finally(() => void this._load());
        });
        dialog.present(this._window);
    }

    private _clear(): void {
        for (const [group, row] of this._rows) group.remove(row);
        this._rows = [];
    }

    private _add(group: Adw.PreferencesGroup, row: Gtk.Widget): void {
        group.add(row);
        this._rows.push([group, row]);
    }
}

function errorText(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
}
