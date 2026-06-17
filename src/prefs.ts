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
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';
import { ExtensionPreferences } from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

const LOG_DIR = GLib.get_user_state_dir() + '/mei';
const LOG_FILE = LOG_DIR + '/logs.txt';

export default class MeiPreferences extends ExtensionPreferences {
    async fillPreferencesWindow(window: Adw.PreferencesWindow): Promise<void> {
        const settings = this.getSettings();

        // Put main window title
        window.set_title('Manage Mei');

        /* ── Main Page ────────────────────────────────── */
        const mainPage = new Adw.PreferencesPage({
            title: 'Manage Mei',
            icon_name: 'preferences-system-symbolic',
        });
        window.add(mainPage);

        // Replace 'Options' with 'Settings'
        const mainMenuGroup = new Adw.PreferencesGroup({
            title: 'Settings',
        });
        mainPage.add(mainMenuGroup);

        // Row 1: Configure AI Provider
        const providerRow = new Adw.ActionRow({
            title: 'Configure AI Provider',
            subtitle: 'Set up Ollama, OpenAI, Anthropic, Gemini, etc.',
            icon_name: 'network-server-symbolic',
            activatable: true,
        });
        mainMenuGroup.add(providerRow);

        // Row 2: Show Logs
        const logsRow = new Adw.ActionRow({
            title: 'Show Logs',
            subtitle: 'View, copy, and clear system logs',
            icon_name: 'format-justify-left-symbolic',
            activatable: true,
        });
        mainMenuGroup.add(logsRow);

        /* ── Page 1: Provider Subpage ─────────────────── */
        const providerBox = new Gtk.Box({
            orientation: Gtk.Orientation.VERTICAL,
        });

        // Add HeaderBar to subpage
        const providerHeader = new Adw.HeaderBar();
        providerBox.append(providerHeader);

        const providerPrefPage = new Adw.PreferencesPage({
            hexpand: true,
            vexpand: true,
        });
        providerBox.append(providerPrefPage);

        const providerTypeGroup = new Adw.PreferencesGroup({
            title: 'Provider Type',
            description: 'Choose whether to use a local model, a cloud service, or a custom endpoint.',
        });
        providerPrefPage.add(providerTypeGroup);

        const providerTypeModel = new Gtk.StringList();
        const typeIds = ['local', 'cloud', 'custom'];
        const typeLabels = ['Local', 'Cloud', 'Custom'];
        for (const label of typeLabels) {
            providerTypeModel.append(label);
        }

        const providerTypeComboRow = new Adw.ComboRow({
            title: 'Type',
            model: providerTypeModel,
        });

        const currentType = settings.get_string('provider-type') || 'cloud';
        let currentTypeIdx = typeIds.indexOf(currentType);
        if (currentTypeIdx === -1) currentTypeIdx = 1;
        providerTypeComboRow.set_selected(currentTypeIdx);

        providerTypeComboRow.connect('notify::selected', () => {
            const idx = providerTypeComboRow.get_selected();
            if (idx >= 0 && idx < typeIds.length) {
                settings.set_string('provider-type', typeIds[idx]);
            }
        });
        providerTypeGroup.add(providerTypeComboRow);

        const providerGroup = new Adw.PreferencesGroup({
            title: 'AI Provider',
            description: 'Select which AI backend Mei should use.',
        });
        providerPrefPage.add(providerGroup);

        const providerModel = new Gtk.StringList();
        const providerComboRow = new Adw.ComboRow({
            title: 'Provider',
            subtitle: 'The AI service to connect to',
            model: providerModel,
        });
        providerGroup.add(providerComboRow);

        let activeProviderIds: string[] = [];

        function updateProviderList() {
            const pType = settings.get_string('provider-type');
            
            providerModel.splice(0, providerModel.get_n_items(), []); // Clear
            
            if (pType === 'local') {
                activeProviderIds = ['ollama', 'llamacpp'];
                providerModel.splice(0, 0, ['Ollama', 'llama.cpp']);
                providerGroup.set_visible(true);
            } else if (pType === 'cloud') {
                activeProviderIds = ['openai', 'anthropic', 'gemini', 'groq', 'mistral', 'openrouter', 'deepseek', 'opencode'];
                providerModel.splice(0, 0, ['OpenAI', 'Anthropic', 'Gemini', 'Groq', 'Mistral', 'OpenRouter', 'DeepSeek', 'OpenCode']);
                providerGroup.set_visible(true);
            } else {
                activeProviderIds = ['custom'];
                providerGroup.set_visible(false); // Hide the provider selection row entirely for custom
            }

            let currentProvider = settings.get_string('provider');
            if (!activeProviderIds.includes(currentProvider)) {
                currentProvider = activeProviderIds[0];
                settings.set_string('provider', currentProvider);
            }
            
            const idx = activeProviderIds.indexOf(currentProvider);
            if (idx >= 0) {
                providerComboRow.set_selected(idx);
            }
        }

        settings.connect('changed::provider-type', updateProviderList);

        providerComboRow.connect('notify::selected', () => {
            const idx = providerComboRow.get_selected();
            if (idx >= 0 && idx < activeProviderIds.length) {
                settings.set_string('provider', activeProviderIds[idx]);
            }
        });
        
        updateProviderList();

        const connectionGroup = new Adw.PreferencesGroup({
            title: 'Connection',
            description: 'Endpoint and authentication settings.',
        });
        providerPrefPage.add(connectionGroup);

        function getProviderConfigs() {
            const jsonStr = settings.get_string('provider-configs') || '{}';
            try { return JSON.parse(jsonStr); } catch (e) { return {}; }
        }
        function saveProviderConfigs(configs: any) {
            settings.set_string('provider-configs', JSON.stringify(configs));
        }
        function getCurrentProviderConfig() {
            const provider = settings.get_string('provider');
            const configs = getProviderConfigs();
            return configs[provider] || { url: '', modelName: '', apiKey: '' };
        }
        function updateCurrentProviderConfig(key: 'url' | 'modelName' | 'apiKey', value: string) {
            const provider = settings.get_string('provider');
            const configs = getProviderConfigs();
            if (!configs[provider]) configs[provider] = { url: '', modelName: '', apiKey: '' };
            configs[provider][key] = value;
            saveProviderConfigs(configs);
        }

        const modelEntryRow = new Adw.EntryRow({ title: 'Model' });
        modelEntryRow.connect('notify::text', () => {
            updateCurrentProviderConfig('modelName', modelEntryRow.get_text());
        });
        connectionGroup.add(modelEntryRow);

        const modelStringList = new Gtk.StringList();
        const modelComboRow = new Adw.ComboRow({ title: 'Model', model: modelStringList });
        modelComboRow.connect('notify::selected', () => {
            const idx = modelComboRow.get_selected();
            if (idx >= 0 && idx < modelStringList.get_n_items()) {
                updateCurrentProviderConfig('modelName', modelStringList.get_string(idx)!);
            }
        });
        connectionGroup.add(modelComboRow);

        const modelStatusRow = new Adw.ActionRow({ title: 'Model', subtitle: 'Checking...' });
        const spinner = new Gtk.Spinner();
        modelStatusRow.add_suffix(spinner);
        connectionGroup.add(modelStatusRow);

        const urlRow = new Adw.EntryRow({ title: 'Endpoint URL (optional)' });
        urlRow.connect('notify::text', () => {
            updateCurrentProviderConfig('url', urlRow.get_text());
        });
        connectionGroup.add(urlRow);

        const apiKeyRow = new Adw.PasswordEntryRow({ title: 'API Key' });
        apiKeyRow.connect('notify::text', () => {
            updateCurrentProviderConfig('apiKey', apiKeyRow.get_text());
            if (settings.get_string('provider-type') === 'cloud') queueUpdateModels();
        });
        connectionGroup.add(apiKeyRow);

        const session = new Soup.Session({ timeout: 5 });

        async function fetchModels(provider: string, apiKey: string): Promise<string[]> {
            let url = '';
            let headers: Record<string, string> = {};
            let isGemini = false;

            switch (provider) {
                case 'openai': url = 'https://api.openai.com/v1/models'; headers['Authorization'] = `Bearer ${apiKey}`; break;
                case 'groq': url = 'https://api.groq.com/openai/v1/models'; headers['Authorization'] = `Bearer ${apiKey}`; break;
                case 'mistral': url = 'https://api.mistral.ai/v1/models'; headers['Authorization'] = `Bearer ${apiKey}`; break;
                case 'openrouter': url = 'https://openrouter.ai/api/v1/models'; headers['Authorization'] = `Bearer ${apiKey}`; break;
                case 'deepseek': url = 'https://api.deepseek.com/models'; headers['Authorization'] = `Bearer ${apiKey}`; break;
                case 'opencode': url = 'https://opencode.ai/zen/go/v1/models'; headers['Authorization'] = `Bearer ${apiKey}`; break;
                case 'anthropic': 
                    url = 'https://api.anthropic.com/v1/models';
                    headers['x-api-key'] = apiKey;
                    headers['anthropic-version'] = '2023-06-01';
                    break;
                case 'gemini':
                    url = `https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`;
                    isGemini = true;
                    break;
                default:
                    return [];
            }

            return new Promise((resolve, reject) => {
                const msg = Soup.Message.new('GET', url);
                if (!msg) { reject(new Error('Invalid URL')); return; }
                
                for (const [k, v] of Object.entries(headers)) {
                    msg.get_request_headers().append(k, v);
                }

                session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, null, (_sess, res) => {
                    try {
                        const bytes = session.send_and_read_finish(res);
                        const text = new TextDecoder().decode(bytes.get_data()!);
                        if (msg.get_status() >= 400) {
                            reject(new Error(`HTTP ${msg.get_status()}`));
                            return;
                        }
                        const json = JSON.parse(text);
                        if (isGemini) {
                            resolve((json.models || []).map((m: any) => m.name.replace('models/', '')));
                        } else {
                            resolve((json.data || []).map((m: any) => m.id || m.display_name));
                        }
                    } catch (e) {
                        reject(e);
                    }
                });
            });
        }

        let fetchTimeout = 0;
        let currentFetchProvider = '';
        let currentFetchKey = '';

        function queueUpdateModels() {
            if (fetchTimeout) {
                GLib.Source.remove(fetchTimeout);
            }
            fetchTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                fetchTimeout = 0;
                doUpdateModels();
                return GLib.SOURCE_REMOVE;
            });
        }

        async function doUpdateModels() {
            const provider = settings.get_string('provider');
            const config = getCurrentProviderConfig();
            const apiKey = config.apiKey || '';

            if (provider === currentFetchProvider && apiKey === currentFetchKey && modelStringList.get_n_items() > 0) {
                modelStatusRow.set_visible(false);
                modelComboRow.set_visible(true);
                return;
            }

            modelComboRow.set_visible(false);
            modelStatusRow.set_visible(true);
            modelStatusRow.set_subtitle('Loading models...');
            spinner.start();
            spinner.set_visible(true);

            try {
                const models = await fetchModels(provider, apiKey);
                if (models.length === 0) {
                    throw new Error('No models returned.');
                }
                currentFetchProvider = provider;
                currentFetchKey = apiKey;

                modelStringList.splice(0, modelStringList.get_n_items(), models);
                
                const currentModel = config.modelName || '';
                let idx = models.indexOf(currentModel);
                if (idx === -1) {
                    idx = 0;
                    updateCurrentProviderConfig('modelName', models[0]);
                }
                modelComboRow.set_selected(idx);

                modelStatusRow.set_visible(false);
                modelComboRow.set_visible(true);
            } catch (e) {
                modelComboRow.set_visible(false);
                modelStatusRow.set_visible(true);
                modelStatusRow.set_subtitle('API Key required or network error.');
                spinner.stop();
                spinner.set_visible(false);
            }
        }

        function updateVisibility() {
            const pType = settings.get_string('provider-type');
            const provider = settings.get_string('provider');
            
            const config = getCurrentProviderConfig();
            if (modelEntryRow.get_text() !== (config.modelName || '')) modelEntryRow.set_text(config.modelName || '');
            if (urlRow.get_text() !== (config.url || '')) urlRow.set_text(config.url || '');
            if (apiKeyRow.get_text() !== (config.apiKey || '')) apiKeyRow.set_text(config.apiKey || '');
            
            urlRow.set_visible(pType === 'custom');

            if (pType === 'local' || pType === 'custom') {
                modelEntryRow.set_visible(true);
                modelComboRow.set_visible(false);
                modelStatusRow.set_visible(false);
                if (fetchTimeout) {
                    GLib.Source.remove(fetchTimeout);
                    fetchTimeout = 0;
                }
            } else {
                modelEntryRow.set_visible(false);
                if (provider === currentFetchProvider && getCurrentProviderConfig().apiKey === currentFetchKey && modelStringList.get_n_items() > 0) {
                    modelComboRow.set_visible(true);
                    modelStatusRow.set_visible(false);
                } else {
                    queueUpdateModels();
                }
            }
        }

        settings.connect('changed::provider', updateVisibility);
        settings.connect('changed::provider-type', updateVisibility);
        updateVisibility();

        const providerSubpage = new Adw.NavigationPage({
            title: 'AI Provider Configurations',
            child: providerBox,
        });

        providerRow.connect('activated', () => {
            window.push_subpage(providerSubpage);
        });

        /* ── Page 2: Logs Subpage ─────────────────────── */
        const logsBox = new Gtk.Box({
            orientation: Gtk.Orientation.VERTICAL,
            spacing: 10,
        });

        // Add HeaderBar to subpage
        const logsHeader = new Adw.HeaderBar();
        logsBox.append(logsHeader);

        // Filter Bar (Top)
        const filterBox = new Gtk.Box({
            orientation: Gtk.Orientation.HORIZONTAL,
            spacing: 10,
            margin_start: 15,
            margin_end: 15,
        });
        logsBox.append(filterBox);

        let logLines: string[] = [];
        let currentFilter = 'All';

        const filters = ['All', 'Info', 'Debug', 'Error', 'Warn'];
        let firstButton: Gtk.ToggleButton | null = null;
        for (const f of filters) {
            const btn = new Gtk.ToggleButton({ label: f });
            if (firstButton) {
                btn.set_group(firstButton);
            } else {
                firstButton = btn;
                btn.set_active(true);
            }
            btn.connect('toggled', () => {
                if (btn.get_active()) {
                    currentFilter = f;
                    updateView();
                }
            });
            filterBox.append(btn);
        }

        const spacer = new Gtk.Box({ hexpand: true });
        filterBox.append(spacer);

        // Refresh button
        const refreshBtn = new Gtk.Button({
            icon_name: 'view-refresh-symbolic',
            tooltip_text: 'Refresh Logs',
        });
        refreshBtn.connect('clicked', () => {
            loadLogs();
        });
        filterBox.append(refreshBtn);

        // Clear button
        const clearBtn = new Gtk.Button({
            icon_name: 'user-trash-symbolic',
            tooltip_text: 'Clear Logs',
            css_classes: ['destructive-action'],
        });
        clearBtn.connect('clicked', () => {
            clearLogs();
        });
        filterBox.append(clearBtn);

        // Copy button
        const copyBtn = new Gtk.Button({
            label: 'Copy',
            icon_name: 'edit-copy-symbolic',
            css_classes: ['suggested-action'],
        });
        filterBox.append(copyBtn);

        // Scrolled Window for Logs
        const scrolled = new Gtk.ScrolledWindow({
            hexpand: true,
            vexpand: true,
            min_content_height: 400,
            margin_start: 15,
            margin_end: 15,
            margin_bottom: 15,
        });
        scrolled.add_css_class('card');

        const textView = new Gtk.TextView({
            editable: false,
            monospace: true,
            wrap_mode: Gtk.WrapMode.WORD_CHAR,
            left_margin: 8,
            right_margin: 8,
            top_margin: 8,
            bottom_margin: 8,
        });
        const buffer = textView.get_buffer();
        scrolled.set_child(textView);
        logsBox.append(scrolled);

        copyBtn.connect('clicked', () => {
            const text = buffer.get_text(
                buffer.get_start_iter(),
                buffer.get_end_iter(),
                false
            );
            const clipboard = window.get_clipboard();
            clipboard.set(text);
        });

        const logsSubpage = new Adw.NavigationPage({
            title: 'Logs',
            child: logsBox,
        });

        logsRow.connect('activated', () => {
            window.push_subpage(logsSubpage);
        });

        /* ── Load/Clear/Update View Logic ──────────────── */
        function loadLogs() {
            try {
                const file = Gio.File.new_for_path(LOG_FILE);
                if (file.query_exists(null)) {
                    const [success, contents] = file.load_contents(null);
                    if (success) {
                        const text = new TextDecoder().decode(contents);
                        logLines = text.split('\n').filter(l => l.trim().length > 0);
                        updateView();
                    }
                } else {
                    buffer.set_text('No logs found at ' + LOG_FILE, -1);
                }
            } catch (e) {
                buffer.set_text(`Failed to load logs: ${e}`, -1);
            }
        }

        function clearLogs() {
            try {
                const file = Gio.File.new_for_path(LOG_FILE);
                if (!file.query_exists(null)) return;
                
                if (currentFilter === 'All') {
                    const out = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
                    out.close(null);
                    logLines = [];
                } else {
                    const levelStr = `[${currentFilter.toUpperCase()}]`;
                    logLines = logLines.filter(line => !line.includes(levelStr));
                    const newText = logLines.join('\n') + (logLines.length ? '\n' : '');
                    if (newText.length === 0) {
                        const out = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
                        out.close(null);
                    } else {
                        file.replace_contents(new TextEncoder().encode(newText), null, false, Gio.FileCreateFlags.NONE, null);
                    }
                }
                updateView();
            } catch (e) {
                console.error(`Failed to clear logs: ${e}`);
            }
        }

        function updateView() {
            let visibleLines = logLines;
            if (currentFilter !== 'All') {
                const levelStr = `[${currentFilter.toUpperCase()}]`;
                visibleLines = logLines.filter(line => line.includes(levelStr));
            }
            
            const reversedLines = [...visibleLines].reverse();
            const newText = reversedLines.join('\n');
            
            const currentText = buffer.get_text(
                buffer.get_start_iter(),
                buffer.get_end_iter(),
                false
            );
            
            if (newText === currentText) {
                return; // No change
            }

            buffer.set_text(newText, -1);
        }

        // Initial load
        loadLogs();

        // Auto-refresh every 5 seconds while preferences window is alive
        let timeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            loadLogs();
            return GLib.SOURCE_CONTINUE;
        });

        window.connect('destroy', () => {
            if (timeoutId) {
                GLib.Source.remove(timeoutId);
                timeoutId = 0;
            }
        });
    }
}
