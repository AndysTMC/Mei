/**
 * Settings → Logs: the runtime's recent log entries (already redacted), newest first, filterable by
 * level. Refreshes every few seconds while the page is on screen.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import { formatLogEntry } from '../runtime/logFormat.js';
import type { RuntimeSettings } from '../runtime/settings.js';
import { SourceSet } from '../ui/sources.js';

const REFRESH_MS = 5000;
const FILTERS = ['All', 'Debug', 'Info', 'Warning', 'Error'] as const;

export class LogsPage {
    readonly page: Adw.NavigationPage;
    private readonly _sources = new SourceSet();
    private readonly _buffer: Gtk.TextBuffer;
    private _lines: string[] = [];
    private _filter: (typeof FILTERS)[number] = 'All';
    private _refreshId = 0;

    constructor(window: Gtk.Window, private readonly _settings: RuntimeSettings) {
        const bar = new Gtk.Box({ spacing: 6, margin_start: 12, margin_end: 12, margin_top: 6 });
        let first: Gtk.ToggleButton | null = null;
        for (const filter of FILTERS) {
            const button = new Gtk.ToggleButton({ label: filter, active: filter === 'All' });
            if (first) button.set_group(first);
            first ??= button;
            button.connect('toggled', () => {
                if (!button.get_active()) return;
                this._filter = filter;
                this._show();
            });
            bar.append(button);
        }
        bar.append(new Gtk.Box({ hexpand: true }));
        const refresh = new Gtk.Button({ icon_name: 'view-refresh-symbolic', tooltip_text: 'Refresh' });
        refresh.connect('clicked', () => void this._load());
        const clear = new Gtk.Button({ icon_name: 'user-trash-symbolic', tooltip_text: 'Clear', css_classes: ['destructive-action'] });
        clear.connect('clicked', () => void this._clear());
        const copy = new Gtk.Button({ icon_name: 'edit-copy-symbolic', tooltip_text: 'Copy what is shown' });
        for (const button of [refresh, clear, copy]) bar.append(button);

        const text = new Gtk.TextView({
            editable: false, monospace: true, wrap_mode: Gtk.WrapMode.WORD_CHAR,
            left_margin: 8, right_margin: 8, top_margin: 8, bottom_margin: 8,
        });
        this._buffer = text.get_buffer();
        copy.connect('clicked', () => window.get_clipboard().set(this._text()));
        const scroll = new Gtk.ScrolledWindow({
            hexpand: true, vexpand: true, min_content_height: 400, margin_start: 12, margin_end: 12, margin_bottom: 12,
            css_classes: ['card'], child: text,
        });

        const content = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL, spacing: 10 });
        content.append(bar);
        content.append(scroll);
        const view = new Adw.ToolbarView({ content });
        view.add_top_bar(new Adw.HeaderBar());
        this.page = new Adw.NavigationPage({ title: 'Logs', child: view, tag: 'logs' });
        this.page.connect('shown', () => {
            void this._load();
            this._refreshId ||= this._sources.timeout(REFRESH_MS, () => {
                void this._load();
                return GLib.SOURCE_CONTINUE;
            });
        });
        this.page.connect('hidden', () => {
            this._refreshId = this._sources.remove(this._refreshId);
        });
    }

    destroy(): void {
        this._sources.destroy();
    }

    private async _load(): Promise<void> {
        try {
            this._lines = (await this._settings.fetchLogs()).map(formatLogEntry);
            this._show();
        } catch (e) {
            this._buffer.set_text(`Couldn’t load the logs: ${e instanceof Error ? e.message : String(e)}`, -1);
        }
    }

    private async _clear(): Promise<void> {
        try {
            await this._settings.clearLogs();
            this._lines = [];
            this._show();
        } catch (e) {
            this._buffer.set_text(`Couldn’t clear the logs: ${e instanceof Error ? e.message : String(e)}`, -1);
        }
    }

    private _show(): void {
        const level = `[${this._filter.toUpperCase()}]`;
        const shown = this._filter === 'All' ? this._lines : this._lines.filter(line => line.includes(level));
        const text = [...shown].reverse().join('\n');
        if (text !== this._text()) this._buffer.set_text(text, -1);
    }

    private _text(): string {
        return this._buffer.get_text(this._buffer.get_start_iter(), this._buffer.get_end_iter(), false);
    }
}
