/**
 * Mei — Preferences window (GTK4 / Libadwaita).
 *
 * This runs in a separate process from GNOME Shell.
 * NO access to St, Clutter, or Main — only GTK4 and Adw.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';
import { ExtensionPreferences } from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';
import {
    DEEPSEEK_REASONING_EFFORT_LABELS,
    DEEPSEEK_THINKING_LABELS,
    getDeepSeekReasoningEffort,
    getDeepSeekThinking,
    getOpenCodeMode,
    getProviderIdsForType,
    getProviderLabel,
    getProviderType,
    OPEN_CODE_MODE_LABELS,
    PROVIDER_TYPE_IDS,
    PROVIDER_TYPE_LABELS,
    type DeepSeekReasoningEffort,
    type DeepSeekThinking,
    type OpenCodeMode,
} from './providers/catalog.js';
import { fetchProviderModels } from './providers/modelList.js';
import type { ProviderId } from './providers/types.js';
import {
    API_KEY_PLACEHOLDER,
    createEmptyProviderConfig,
    isApiKeyPlaceholderLike,
    parseProviderConfigs,
    type ProviderConfigKey,
    type ProviderConfigs,
    type StoredProviderConfig,
} from './providers/configStore.js';
import {
    migratePlaintextApiKeys,
    resolveStoredProviderConfig,
    updateStoredProviderApiKey,
} from './providers/apiKeys.js';
import { lookupProviderApiKey } from './utils/secretStore.js';
import { Logger, Tag } from './utils/logger.js';
import { LOG_FILE, replaceLogFileTextAsync } from './utils/logFile.js';

export default class MeiPreferences extends ExtensionPreferences {
    async fillPreferencesWindow(window: Adw.PreferencesWindow): Promise<void> {
        const settings = this.getSettings();
        const settingsSignalIds: number[] = [];
        let destroyed = false;

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
        const typeIds = PROVIDER_TYPE_IDS;
        const typeLabels = typeIds.map(id => PROVIDER_TYPE_LABELS[id]);
        for (const label of typeLabels) {
            providerTypeModel.append(label);
        }

        const providerTypeComboRow = new Adw.ComboRow({
            title: 'Type',
            model: providerTypeModel,
        });

        const currentType = getProviderType(settings.get_string('provider-type'));
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
            const pType = getProviderType(settings.get_string('provider-type'));

            providerModel.splice(0, providerModel.get_n_items(), []); // Clear

            activeProviderIds = getProviderIdsForType(pType);
            providerModel.splice(0, 0, activeProviderIds.map(id => getProviderLabel(id)));
            providerGroup.set_visible(pType !== 'custom');

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

        settingsSignalIds.push(settings.connect('changed::provider-type', updateProviderList));

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

        let providerConfigSaveTimeout = 0;
        let pendingProviderConfigs: ProviderConfigs | null = null;
        const apiKeyCache = new Map<string, string>();
        let refreshingProviderUi = false;

        function getProviderConfigs(): ProviderConfigs {
            if (pendingProviderConfigs) return pendingProviderConfigs;
            const jsonStr = settings.get_string('provider-configs') || '{}';
            return parseProviderConfigs(jsonStr);
        }

        function saveProviderConfigsNow(configs: ProviderConfigs): void {
            settings.set_string('provider-configs', JSON.stringify(configs));
            pendingProviderConfigs = null;
        }

        function queueSaveProviderConfigs(configs: ProviderConfigs): void {
            pendingProviderConfigs = configs;
            if (providerConfigSaveTimeout) {
                GLib.source_remove(providerConfigSaveTimeout);
            }
            providerConfigSaveTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
                providerConfigSaveTimeout = 0;
                if (pendingProviderConfigs && !destroyed) {
                    saveProviderConfigsNow(pendingProviderConfigs);
                }
                return GLib.SOURCE_REMOVE;
            });
        }

        function flushProviderConfigSave(): void {
            if (providerConfigSaveTimeout) {
                GLib.source_remove(providerConfigSaveTimeout);
                providerConfigSaveTimeout = 0;
            }
            if (pendingProviderConfigs) {
                saveProviderConfigsNow(pendingProviderConfigs);
            }
        }

        function getCurrentProviderConfig(): StoredProviderConfig {
            const provider = settings.get_string('provider');
            const configs = getProviderConfigs();
            return configs[provider] || createEmptyProviderConfig();
        }

        function getCurrentApiKeySnapshot(provider: string): string {
            const config = getProviderConfigs()[provider] || createEmptyProviderConfig();
            return isApiKeyPlaceholderLike(config.apiKey) ? apiKeyCache.get(provider) || '' : config.apiKey || apiKeyCache.get(provider) || '';
        }
        async function migrateProviderConfigsToSecret(): Promise<void> {
            const configs = getProviderConfigs();
            const result = await migratePlaintextApiKeys(configs);
            if (destroyed) return;
            if (result.changed) {
                saveProviderConfigsNow(result.configs);
            }

            // Pre-warm apiKeyCache
            const finalConfigs = result.changed ? result.configs : configs;
            for (const [provider, config] of Object.entries(finalConfigs)) {
                if (config.apiKeyStorage === 'secret') {
                    try {
                        const key = await lookupProviderApiKey(provider);
                        if (key && !destroyed) {
                            apiKeyCache.set(provider, key);
                        }
                    } catch (e) {
                        Logger.warn(Tag.Extension, `Failed to pre-warm ${provider} API key: ${e}`);
                    }
                }
            }
        }

        async function getResolvedProviderConfig(provider: string, config: StoredProviderConfig): Promise<StoredProviderConfig> {
            if (config.apiKey && !isApiKeyPlaceholderLike(config.apiKey)) return config;
            const cachedKey = apiKeyCache.get(provider);
            if (cachedKey) return { ...config, apiKey: cachedKey };

            const resolved = await resolveStoredProviderConfig(provider, config);
            if (resolved.apiKey) apiKeyCache.set(provider, resolved.apiKey);
            return resolved;
        }

        async function updateCurrentProviderConfig(key: ProviderConfigKey, value: string): Promise<void> {
            if (refreshingProviderUi) return;
            const provider = settings.get_string('provider');
            const configs = getProviderConfigs();
            if (!configs[provider]) configs[provider] = createEmptyProviderConfig();
            if (key === 'apiKey' && isApiKeyPlaceholderLike(value.trim())) return;
            if (key === 'apiKey') {
                configs[provider] = await updateStoredProviderApiKey(provider, configs[provider], value);
                if (value.trim()) {
                    apiKeyCache.set(provider, value.trim());
                } else {
                    apiKeyCache.delete(provider);
                }
            } else {
                configs[provider][key] = value;
            }
            if (destroyed) return;
            queueSaveProviderConfigs(configs);
        }

        void migrateProviderConfigsToSecret();

        const providerModeGroup = new Adw.PreferencesGroup({
            title: 'Provider Options',
        });
        providerPrefPage.add(providerModeGroup);

        const openCodeModeModel = new Gtk.StringList();
        const openCodeModeIds: OpenCodeMode[] = ['go', 'zen'];
        openCodeModeModel.splice(0, 0, openCodeModeIds.map(id => OPEN_CODE_MODE_LABELS[id]));
        const openCodeModeRow = new Adw.ComboRow({
            title: 'OpenCode Mode',
            subtitle: 'Go uses the OpenCode subscription model pool; Zen uses the Zen API model pool.',
            model: openCodeModeModel,
        });
        openCodeModeRow.connect('notify::selected', () => {
            const idx = openCodeModeRow.get_selected();
            if (idx >= 0 && idx < openCodeModeIds.length) {
                void updateCurrentProviderConfig('mode', openCodeModeIds[idx]);
                currentFetchProvider = '';
                currentFetchKey = '';
                currentFetchMode = '';
                queueUpdateModels();
            }
        });
        providerModeGroup.add(openCodeModeRow);

        const deepSeekThinkingModel = new Gtk.StringList();
        const deepSeekThinkingIds: DeepSeekThinking[] = ['default', 'enabled', 'disabled'];
        deepSeekThinkingModel.splice(0, 0, deepSeekThinkingIds.map(id => DEEPSEEK_THINKING_LABELS[id]));
        const deepSeekThinkingRow = new Adw.ComboRow({
            title: 'DeepSeek Thinking',
            subtitle: 'Controls the documented DeepSeek thinking mode for supported models.',
            model: deepSeekThinkingModel,
        });
        deepSeekThinkingRow.connect('notify::selected', () => {
            const idx = deepSeekThinkingRow.get_selected();
            if (idx >= 0 && idx < deepSeekThinkingIds.length) {
                void updateCurrentProviderConfig('thinking', deepSeekThinkingIds[idx]);
            }
        });
        providerModeGroup.add(deepSeekThinkingRow);

        const deepSeekEffortModel = new Gtk.StringList();
        const deepSeekEffortIds: DeepSeekReasoningEffort[] = ['high', 'max'];
        deepSeekEffortModel.splice(0, 0, deepSeekEffortIds.map(id => DEEPSEEK_REASONING_EFFORT_LABELS[id]));
        const deepSeekEffortRow = new Adw.ComboRow({
            title: 'DeepSeek Reasoning Effort',
            model: deepSeekEffortModel,
        });
        deepSeekEffortRow.connect('notify::selected', () => {
            const idx = deepSeekEffortRow.get_selected();
            if (idx >= 0 && idx < deepSeekEffortIds.length) {
                void updateCurrentProviderConfig('reasoningEffort', deepSeekEffortIds[idx]);
            }
        });
        providerModeGroup.add(deepSeekEffortRow);

        let modelEntryTimeout = 0;
        const modelEntryRow = new Adw.EntryRow({ title: 'Model' });
        modelEntryRow.connect('notify::text', () => {
            if (refreshingProviderUi) return;
            if (modelEntryTimeout) GLib.source_remove(modelEntryTimeout);
            modelEntryTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
                modelEntryTimeout = 0;
                void updateCurrentProviderConfig('modelName', modelEntryRow.get_text());
                return GLib.SOURCE_REMOVE;
            });
        });
        connectionGroup.add(modelEntryRow);

        const modelStringList = new Gtk.StringList();
        const modelComboRow = new Adw.ComboRow({ title: 'Model', model: modelStringList });
        modelComboRow.connect('notify::selected', () => {
            const idx = modelComboRow.get_selected();
            if (idx >= 0 && idx < modelStringList.get_n_items()) {
                void updateCurrentProviderConfig('modelName', modelStringList.get_string(idx)!);
            }
        });
        connectionGroup.add(modelComboRow);

        const modelStatusRow = new Adw.ActionRow({ title: 'Model', subtitle: 'Checking...' });
        const spinner = new Gtk.Spinner();
        modelStatusRow.add_suffix(spinner);
        connectionGroup.add(modelStatusRow);

        let urlTimeout = 0;
        const urlRow = new Adw.EntryRow({ title: 'Endpoint URL (optional)' });
        urlRow.connect('notify::text', () => {
            if (refreshingProviderUi) return;
            if (urlTimeout) GLib.source_remove(urlTimeout);
            urlTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
                urlTimeout = 0;
                void updateCurrentProviderConfig('url', urlRow.get_text());
                return GLib.SOURCE_REMOVE;
            });
        });
        connectionGroup.add(urlRow);

        let apiKeyTimeout = 0;
        const apiKeyRow = new Adw.PasswordEntryRow({ title: 'API Key' });
        apiKeyRow.connect('notify::text', () => {
            if (refreshingProviderUi) return;
            const text = apiKeyRow.get_text();
            if (isApiKeyPlaceholderLike(text.trim())) return;

            if (apiKeyTimeout) GLib.source_remove(apiKeyTimeout);
            apiKeyTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                apiKeyTimeout = 0;
                void (async () => {
                    await updateCurrentProviderConfig('apiKey', text);
                    if (getProviderType(settings.get_string('provider-type')) === 'cloud') {
                        queueUpdateModels();
                    }
                })();
                return GLib.SOURCE_REMOVE;
            });
        });
        connectionGroup.add(apiKeyRow);

        const session = new Soup.Session({ timeout: 15 });
        let modelFetchCancellable: Gio.Cancellable | null = null;

        async function fetchModels(provider: string, config: StoredProviderConfig, cancellable: Gio.Cancellable): Promise<string[]> {
            const result = await fetchProviderModels(
                session,
                provider as ProviderId,
                {
                    url: config.url || '',
                    apiKey: config.apiKey || '',
                    mode: config.mode || '',
                },
                cancellable
            );
            return result.models;
        }

        let fetchTimeout = 0;
        let currentFetchProvider = '';
        let currentFetchKey = '';
        let currentFetchMode = '';
        let modelFetchSeq = 0;

        function queueUpdateModels() {
            if (destroyed) return;
            if (fetchTimeout) {
                GLib.source_remove(fetchTimeout);
            }
            fetchTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                fetchTimeout = 0;
                doUpdateModels();
                return GLib.SOURCE_REMOVE;
            });
        }

        async function doUpdateModels() {
            if (destroyed) return;
            const provider = settings.get_string('provider');
            const config = getCurrentProviderConfig();
            const resolvedConfig = await getResolvedProviderConfig(provider, config);
            if (destroyed || provider !== settings.get_string('provider')) return;
            const apiKey = resolvedConfig.apiKey || '';

            if (apiKey.length === 0) {
                modelComboRow.set_visible(false);
                modelStatusRow.set_visible(true);
                modelStatusRow.set_subtitle(config.apiKeyStorage === 'secret'
                    ? 'Stored API key could not be read. Enter and save it again.'
                    : 'API key required.');
                spinner.stop();
                spinner.set_visible(false);
                currentFetchProvider = '';
                currentFetchKey = '';
                currentFetchMode = '';
                return;
            }

            const providerMode = config.mode || '';
            if (
                provider === currentFetchProvider &&
                apiKey === currentFetchKey &&
                providerMode === currentFetchMode &&
                modelStringList.get_n_items() > 0
            ) {
                modelStatusRow.set_visible(false);
                modelComboRow.set_visible(true);
                return;
            }

            const fetchSeq = ++modelFetchSeq;
            modelFetchCancellable?.cancel();
            modelFetchCancellable = new Gio.Cancellable();
            modelComboRow.set_visible(false);
            modelStatusRow.set_visible(true);
            modelStatusRow.set_subtitle('Loading models...');
            spinner.start();
            spinner.set_visible(true);

            try {
                const models = await fetchModels(provider, resolvedConfig, modelFetchCancellable);
                if (
                    destroyed ||
                    fetchSeq !== modelFetchSeq ||
                    provider !== settings.get_string('provider') ||
                    apiKey !== getCurrentApiKeySnapshot(provider) ||
                    settings.get_string('provider-type') !== 'cloud'
                ) {
                    return;
                }

                if (models.length === 0) {
                    throw new Error('No models returned.');
                }
                currentFetchProvider = provider;
                currentFetchKey = apiKey;
                currentFetchMode = providerMode;

                modelStringList.splice(0, modelStringList.get_n_items(), models);

                const currentModel = config.modelName || '';
                let idx = models.indexOf(currentModel);
                if (idx === -1) {
                    idx = 0;
                    void updateCurrentProviderConfig('modelName', models[0]);
                }
                modelComboRow.set_selected(idx);

                modelStatusRow.set_visible(false);
                modelComboRow.set_visible(true);
                spinner.stop();
                spinner.set_visible(false);
            } catch (e) {
                if (
                    destroyed ||
                    fetchSeq !== modelFetchSeq ||
                    provider !== settings.get_string('provider') ||
                    apiKey !== getCurrentApiKeySnapshot(provider) ||
                    settings.get_string('provider-type') !== 'cloud'
                ) {
                    return;
                }

                modelComboRow.set_visible(false);
                modelStatusRow.set_visible(true);
                modelStatusRow.set_subtitle('API Key required or network error.');
                currentFetchProvider = '';
                currentFetchKey = '';
                currentFetchMode = '';
                spinner.stop();
                spinner.set_visible(false);
            }
        }

        function updateVisibility() {
            const pType = getProviderType(settings.get_string('provider-type'));
            const provider = settings.get_string('provider');

            const config = getCurrentProviderConfig();
            refreshingProviderUi = true;
            try {
                if (modelEntryRow.get_text() !== (config.modelName || '')) modelEntryRow.set_text(config.modelName || '');
                if (urlRow.get_text() !== (config.url || '')) urlRow.set_text(config.url || '');
                const apiKeyText = getApiKeyFieldText(config);
                if (apiKeyRow.get_text() !== apiKeyText) apiKeyRow.set_text(apiKeyText);

                const openCodeModeIdx = openCodeModeIds.indexOf(getOpenCodeMode(config.mode));
                if (openCodeModeRow.get_selected() !== openCodeModeIdx) openCodeModeRow.set_selected(openCodeModeIdx);

                const deepSeekThinkingIdx = deepSeekThinkingIds.indexOf(getDeepSeekThinking(config.thinking));
                if (deepSeekThinkingRow.get_selected() !== deepSeekThinkingIdx) deepSeekThinkingRow.set_selected(deepSeekThinkingIdx);

                const deepSeekEffortIdx = deepSeekEffortIds.indexOf(getDeepSeekReasoningEffort(config.reasoningEffort));
                if (deepSeekEffortRow.get_selected() !== deepSeekEffortIdx) deepSeekEffortRow.set_selected(deepSeekEffortIdx);
            } finally {
                refreshingProviderUi = false;
            }

            urlRow.set_visible(pType === 'custom');
            providerModeGroup.set_visible(provider === 'opencode' || provider === 'deepseek');
            openCodeModeRow.set_visible(provider === 'opencode');
            deepSeekThinkingRow.set_visible(provider === 'deepseek');
            deepSeekEffortRow.set_visible(provider === 'deepseek' && getDeepSeekThinking(config.thinking) === 'enabled');

            if (pType === 'local' || pType === 'custom') {
                modelEntryRow.set_visible(true);
                modelComboRow.set_visible(false);
                modelStatusRow.set_visible(false);
                if (fetchTimeout) {
                    GLib.source_remove(fetchTimeout);
                    fetchTimeout = 0;
                }
                modelFetchCancellable?.cancel();
                modelFetchCancellable = null;
                modelFetchSeq++;
                spinner.stop();
                spinner.set_visible(false);
            } else {
                modelEntryRow.set_visible(false);
                if (
                    provider === currentFetchProvider &&
                    getCurrentApiKeySnapshot(provider) === currentFetchKey &&
                    (getCurrentProviderConfig().mode || '') === currentFetchMode &&
                    modelStringList.get_n_items() > 0
                ) {
                    modelComboRow.set_visible(true);
                    modelStatusRow.set_visible(false);
                } else {
                    queueUpdateModels();
                }
            }
        }

        settingsSignalIds.push(settings.connect('changed::provider', updateVisibility));
        settingsSignalIds.push(settings.connect('changed::provider-type', updateVisibility));
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
                    void replaceLogFileTextAsync('').catch(e => {
                        buffer.set_text(`Failed to clear logs: ${e}`, -1);
                    });
                    logLines = [];
                } else {
                    const levelStr = `[${currentFilter.toUpperCase()}]`;
                    logLines = logLines.filter(line => !line.includes(levelStr));
                    const newText = logLines.join('\n') + (logLines.length ? '\n' : '');
                    void replaceLogFileTextAsync(newText).catch(e => {
                        buffer.set_text(`Failed to clear logs: ${e}`, -1);
                    });
                }
                updateView();
            } catch (e) {
                buffer.set_text(`Failed to clear logs: ${e}`, -1);
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
            if (modelEntryTimeout) {
                GLib.source_remove(modelEntryTimeout);
                modelEntryTimeout = 0;
            }
            if (urlTimeout) {
                GLib.source_remove(urlTimeout);
                urlTimeout = 0;
            }
            if (apiKeyTimeout) {
                GLib.source_remove(apiKeyTimeout);
                apiKeyTimeout = 0;
            }
            if (fetchTimeout) {
                GLib.source_remove(fetchTimeout);
                fetchTimeout = 0;
            }
            flushProviderConfigSave();
            destroyed = true;
            modelFetchSeq++;
            modelFetchCancellable?.cancel();
            modelFetchCancellable = null;
            session.abort();

            if (timeoutId) {
                GLib.source_remove(timeoutId);
                timeoutId = 0;
            }
            for (const signalId of settingsSignalIds) {
                settings.disconnect(signalId);
            }
            settingsSignalIds.length = 0;
        });
    }
}

function getApiKeyFieldText(config: StoredProviderConfig): string {
    if (config.apiKey && !isApiKeyPlaceholderLike(config.apiKey)) return config.apiKey;
    return config.apiKeyStorage === 'secret' ? API_KEY_PLACEHOLDER : '';
}
