/**
 * Settings → Model provider: which provider answers, its model and endpoint, and its API key.
 *
 * Nothing here saves by itself: a setting changes only when the user picks a row, presses Enter
 * or ✓ in a text field, or saves a key. Keys go straight to the keyring; this page only learns
 * whether one is saved. Cloud providers list their models through the runtime, which uses the
 * saved key itself.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {
    DEEPSEEK_REASONING_EFFORT_LABELS,
    DEEPSEEK_THINKING_LABELS,
    getDeepSeekReasoningEffort,
    getDeepSeekThinking,
    getProviderIdsForType,
    getProviderLabel,
    PROVIDER_TYPE_IDS,
    PROVIDER_TYPE_LABELS,
    type DeepSeekReasoningEffort,
    type DeepSeekThinking,
    type ProviderType,
} from '../providers/catalog.js';
import { getProviderProfile, resolveProviderId } from '../providers/profiles.js';
import type { ProviderId } from '../providers/types.js';
import type { RuntimeSettings } from '../runtime/settings.js';
import { SourceSet } from '../ui/sources.js';
import { hasProviderApiKey, saveProviderApiKey } from '../utils/secretStore.js';

const MODEL_FETCH_DELAY_MS = 300;
const THINKING_IDS: DeepSeekThinking[] = ['default', 'enabled', 'disabled'];
const EFFORT_IDS: DeepSeekReasoningEffort[] = ['low', 'high', 'max'];

export class ProviderPage {
    readonly page: Adw.NavigationPage;
    private readonly _sources = new SourceSet();
    private readonly _signals: number[] = [];
    private _type: ProviderType;
    /** What the provider and model rows list; null is the "Choose…" entry shown while nothing is chosen. */
    private _listed: (ProviderId | null)[] = [];
    private _models: string[] = [];
    private _modelChoices: (string | null)[] = [];
    private _fetchSeq = 0;
    private _fetchId = 0;
    /** Repopulating rows reselects them; that isn't the user choosing. */
    private _rendering = false;

    private readonly _typeRow = comboRow('Type', PROVIDER_TYPE_IDS.map(id => PROVIDER_TYPE_LABELS[id]));
    private readonly _providerGroup = new Adw.PreferencesGroup({ title: 'Provider', description: 'The service that answers.' });
    private readonly _providerRow = comboRow('Provider', []);
    private readonly _optionsGroup = new Adw.PreferencesGroup({ title: 'DeepSeek' });
    private readonly _connection = new Adw.PreferencesGroup({ title: 'Connection' });
    private readonly _thinkingRow = comboRow('Thinking', THINKING_IDS.map(id => DEEPSEEK_THINKING_LABELS[id]),
        'Default follows the model; On and Off ask for it explicitly.');
    private readonly _effortRow = comboRow('Reasoning effort', EFFORT_IDS.map(id => DEEPSEEK_REASONING_EFFORT_LABELS[id]),
        'DeepSeek may map the requested effort differently by model.');
    private readonly _modelEntry = new Adw.EntryRow({ title: 'Model', show_apply_button: true });
    private readonly _modelRow = comboRow('Model', []);
    private readonly _modelStatus = new Adw.ActionRow({ title: 'Models' });
    private readonly _spinner = new Adw.Spinner({ visible: false });
    private readonly _urlEntry = new Adw.EntryRow({ title: 'Endpoint URL', show_apply_button: true });
    private readonly _keyRow = new Adw.ActionRow({ title: 'API key', subtitle: 'Checking…' });
    private readonly _keyEntry = new Adw.PasswordEntryRow({ title: 'New API key', show_apply_button: true, visible: false });

    constructor(private readonly _settings: RuntimeSettings) {
        this._type = typeOf(_settings.active);
        const prefs = new Adw.PreferencesPage();
        const typeGroup = new Adw.PreferencesGroup({
            title: 'Kind',
            description: 'A model on this computer, a cloud service, or your own endpoint.',
        });
        typeGroup.add(this._typeRow);
        prefs.add(typeGroup);
        this._providerGroup.add(this._providerRow);
        prefs.add(this._providerGroup);
        this._optionsGroup.add(this._thinkingRow);
        this._optionsGroup.add(this._effortRow);
        prefs.add(this._optionsGroup);

        this._modelStatus.add_suffix(this._spinner);
        const enterKey = new Gtk.Button({ label: 'Enter new key…', valign: Gtk.Align.CENTER });
        this._keyRow.add_suffix(enterKey);
        for (const row of [this._modelEntry, this._modelRow, this._modelStatus, this._urlEntry, this._keyRow, this._keyEntry])
            this._connection.add(row);
        prefs.add(this._connection);

        const view = new Adw.ToolbarView({ content: prefs });
        view.add_top_bar(new Adw.HeaderBar());
        this.page = new Adw.NavigationPage({ title: 'Model provider', child: view, tag: 'providers' });

        this._typeRow.connect('notify::selected', () => this._onTypePicked());
        this._providerRow.connect('notify::selected', () => this._onProviderPicked());
        this._thinkingRow.connect('notify::selected', () => this._onPicked(this._thinkingRow, THINKING_IDS, 'thinking'));
        this._effortRow.connect('notify::selected', () => this._onPicked(this._effortRow, EFFORT_IDS, 'reasoning_effort'));
        this._modelRow.connect('notify::selected', () => {
            const model = this._modelChoices[this._modelRow.get_selected()];
            if (!this._rendering && model) this._save('model', model);
        });
        this._modelEntry.connect('apply', () => this._save('model', this._modelEntry.get_text().trim()));
        this._urlEntry.connect('apply', () => this._save('url', this._urlEntry.get_text().trim()));
        enterKey.connect('clicked', () => {
            this._keyEntry.set_text('');
            this._keyEntry.set_visible(true);
            this._keyEntry.grab_focus();
        });
        this._keyEntry.connect('apply', () => void this._saveKey(this._keyEntry.get_text()));

        // Another window (or the setup assistant) may change these; show it.
        this._signals.push(_settings.connect('changed::active', () => {
            this._type = typeOf(_settings.active);
            this._render(true);
        }));
        this._signals.push(_settings.connect('changed::providers', () => this._render(false)));
        this.page.connect('shown', () => this._render(true));
        this._render(true);
    }

    destroy(): void {
        this._sources.destroy();
        this._fetchSeq++;
        this._signals.forEach(id => this._settings.disconnect(id));
    }

    // ── User actions ─────────────────────────────────────────────────────────

    private _onTypePicked(): void {
        const type = PROVIDER_TYPE_IDS[this._typeRow.get_selected()];
        if (this._rendering || !type || type === this._type) return;
        this._type = type;
        // A kind with a single provider (Custom) has no list to pick from: choosing it is the choice.
        const providers = getProviderIdsForType(type);
        if (providers.length === 1) this._settings.setActive(providers[0]);
        this._render(true);
    }

    private _onProviderPicked(): void {
        const id = this._listed[this._providerRow.get_selected()];
        if (!this._rendering && id) this._settings.setActive(id);
    }

    private _onPicked(row: Adw.ComboRow, values: readonly string[], field: 'thinking' | 'reasoning_effort'): void {
        const value = values[row.get_selected()];
        if (!this._rendering && value !== undefined) this._save(field, value);
    }

    private _save(field: 'model' | 'url' | 'thinking' | 'reasoning_effort', value: string): void {
        const provider = this._provider();
        if (!provider) return;
        this._settings.setProviderField(provider, field, value);
        if (field === 'url') this._queueModels();
    }

    private async _saveKey(key: string): Promise<void> {
        const provider = this._provider();
        if (!provider || !key.trim()) return;
        try {
            await saveProviderApiKey(provider, key);
        } catch (e) {
            this._keyRow.set_subtitle(`Not saved: ${e instanceof Error ? e.message : String(e)}`);
            return;
        }
        this._keyEntry.set_text('');
        this._keyEntry.set_visible(false);
        this._keyRow.set_subtitle('Saved in your keyring.');
        this._queueModels();
    }

    // ── Showing the settings ─────────────────────────────────────────────────

    /** The active provider if it belongs to the kind being shown. */
    private _provider(): ProviderId | null {
        const id = resolveProviderId(this._settings.active);
        return id && getProviderProfile(id).type === this._type ? id : null;
    }

    /** Fill every row from settings. `fresh` also resets what the user may have typed but not applied. */
    private _render(fresh: boolean): void {
        const provider = this._provider();
        const saved = provider ? this._settings.provider(provider) : null;
        this._rendering = true;
        try {
            this._typeRow.set_selected(PROVIDER_TYPE_IDS.indexOf(this._type));
            const ids = getProviderIdsForType(this._type);
            this._listed = provider ? ids : [null, ...ids];
            setItems(this._providerRow, this._listed.map(id => (id ? getProviderLabel(id) : 'Choose a provider…')));
            this._providerRow.set_selected(this._listed.indexOf(provider));
            this._providerGroup.set_visible(ids.length > 1);
            this._connection.set_visible(Boolean(provider));

            const thinking = getDeepSeekThinking(saved?.thinking);
            this._optionsGroup.set_visible(provider === 'deepseek');
            this._thinkingRow.set_selected(THINKING_IDS.indexOf(thinking));
            this._effortRow.set_selected(EFFORT_IDS.indexOf(getDeepSeekReasoningEffort(saved?.reasoning_effort)));
            this._effortRow.set_visible(thinking === 'enabled');

            const typed = this._type !== 'cloud'; // local and custom models are typed in, cloud ones listed
            this._modelEntry.set_visible(Boolean(provider) && typed);
            this._modelRow.set_visible(Boolean(provider) && !typed && this._models.length > 0);
            this._modelStatus.set_visible(Boolean(provider) && !typed);
            this._urlEntry.set_visible(Boolean(provider) && typed);
            this._urlEntry.set_title(this._type === 'custom' ? 'Endpoint URL' : 'Endpoint URL (optional)');
            this._keyRow.set_visible(Boolean(provider));
            if (fresh || !provider) this._keyEntry.set_visible(false);
            if (fresh) {
                this._modelEntry.set_text(saved?.model ?? '');
                this._urlEntry.set_text(saved?.url ?? '');
            }
            if (!typed && saved) this._selectModel(saved.model);
        } finally {
            this._rendering = false;
        }
        if (!provider) return;
        if (fresh) {
            void this._showKeyState(provider);
            if (this._type === 'cloud') this._queueModels();
        }
    }

    private async _showKeyState(provider: ProviderId): Promise<void> {
        const has = await hasProviderApiKey(provider);
        if (provider !== this._provider()) return;
        const needed = getProviderProfile(provider).authType !== 'none';
        this._keyRow.set_subtitle(has === null
            ? 'The keyring can’t be reached.'
            : has ? 'Saved in your keyring.' : needed ? 'Needed for this provider.' : 'Optional for this provider.');
    }

    // ── Model list (cloud providers) ─────────────────────────────────────────

    private _queueModels(): void {
        this._sources.remove(this._fetchId);
        this._fetchId = this._sources.timeout(MODEL_FETCH_DELAY_MS, () => {
            this._fetchId = 0;
            void this._loadModels();
            return GLib.SOURCE_REMOVE;
        });
    }

    private async _loadModels(): Promise<void> {
        const provider = this._provider();
        if (!provider || this._type !== 'cloud') return;
        const seq = ++this._fetchSeq;
        this._spinner.set_visible(true);
        this._modelStatus.set_subtitle('Loading models…');
        try {
            const result = await this._settings.listModels(provider);
            if (seq !== this._fetchSeq) return;
            this._models = result.models;
            this._modelStatus.set_subtitle(result.requiresApiKey
                ? 'Add your API key to see every model; these are suggestions.'
                : `${result.models.length} models available.`);
        } catch (e) {
            if (seq !== this._fetchSeq) return;
            this._models = [];
            this._modelStatus.set_subtitle(`Model list unavailable: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
            if (seq === this._fetchSeq) this._spinner.set_visible(false);
        }
        this._rendering = true;
        try {
            this._selectModel(this._settings.provider(provider).model);
            this._modelRow.set_visible(this._models.length > 0);
        } finally {
            this._rendering = false;
        }
    }

    /** Show the list with the saved model selected; a saved model the list lacks is kept, at the top. */
    private _selectModel(model: string): void {
        if (model && !this._models.includes(model)) this._models = [model, ...this._models];
        this._modelChoices = model ? this._models : [null, ...this._models];
        setItems(this._modelRow, this._modelChoices.map(m => m ?? 'Choose a model…'));
        this._modelRow.set_selected(this._modelChoices.indexOf(model || null));
    }
}

function typeOf(provider: string): ProviderType {
    const id = resolveProviderId(provider);
    return id ? getProviderProfile(id).type : 'local';
}

function comboRow(title: string, items: string[], subtitle = ''): Adw.ComboRow {
    return new Adw.ComboRow({ title, subtitle, model: Gtk.StringList.new(items) });
}

function setItems(row: Adw.ComboRow, items: string[]): void {
    const list = row.get_model() as Gtk.StringList;
    list.splice(0, list.get_n_items(), items);
}
