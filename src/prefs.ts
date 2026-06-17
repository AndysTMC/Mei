/**
 * Mei — Preferences window (GTK4 / Libadwaita).
 *
 * This runs in a separate process from GNOME Shell.
 * NO access to St, Clutter, or Main — only GTK4 and Adw.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';
import { ExtensionPreferences } from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class MeiPreferences extends ExtensionPreferences {
    async fillPreferencesWindow(window: Adw.PreferencesWindow): Promise<void> {
        const settings = this.getSettings();

        /* ── Provider page ────────────────────────────── */
        const page = new Adw.PreferencesPage({
            title: 'Provider',
            icon_name: 'network-server-symbolic',
        });
        window.add(page);

        /* ── Provider selection group ─────────────────── */
        const providerGroup = new Adw.PreferencesGroup({
            title: 'AI Provider',
            description: 'Select which AI backend Mei should use.',
        });
        page.add(providerGroup);

        // Provider dropdown
        const providerModel = new Gtk.StringList();
        const providerIds = ['ollama', 'llamacpp', 'openai', 'anthropic', 'gemini'];
        const providerLabels = ['Ollama', 'llama.cpp', 'OpenAI', 'Anthropic', 'Gemini'];
        for (const label of providerLabels) {
            providerModel.append(label);
        }

        const providerRow = new Adw.ComboRow({
            title: 'Provider',
            subtitle: 'The AI service to connect to',
            model: providerModel,
        });

        // Set initial selection from settings
        const currentProvider = settings.get_string('provider');
        const currentIdx = providerIds.indexOf(currentProvider);
        if (currentIdx >= 0) {
            providerRow.set_selected(currentIdx);
        }

        // Sync selection → settings
        providerRow.connect('notify::selected', () => {
            const idx = providerRow.get_selected();
            if (idx >= 0 && idx < providerIds.length) {
                settings.set_string('provider', providerIds[idx]);
            }
        });
        providerGroup.add(providerRow);

        /* ── Connection group ─────────────────────────── */
        const connectionGroup = new Adw.PreferencesGroup({
            title: 'Connection',
            description: 'Endpoint and authentication settings.',
        });
        page.add(connectionGroup);

        // Model name
        const modelRow = new Adw.EntryRow({
            title: 'Model',
        });
        settings.bind('model-name', modelRow, 'text', Gio.SettingsBindFlags.DEFAULT);
        connectionGroup.add(modelRow);

        // Custom URL
        const urlRow = new Adw.EntryRow({
            title: 'Endpoint URL (optional)',
        });
        settings.bind('provider-url', urlRow, 'text', Gio.SettingsBindFlags.DEFAULT);
        connectionGroup.add(urlRow);

        // API Key
        const apiKeyRow = new Adw.PasswordEntryRow({
            title: 'API Key',
        });
        settings.bind('api-key', apiKeyRow, 'text', Gio.SettingsBindFlags.DEFAULT);
        connectionGroup.add(apiKeyRow);
    }
}
