/**
 * Provider settings backed by the runtime (protocol 2), shaped like the `Gio.Settings` keys the
 * popup and preferences used before: `provider`, `provider-type`, and `provider-configs`.
 *
 * Reads are synchronous from a local copy. A write records only the fields it changes, applies
 * them to the copy, notifies listeners, and is sent to the runtime with compare-and-set; on a
 * conflict the same field changes are replayed onto the runtime's newer copy, so a concurrent
 * change to another field survives. If the runtime can't be reached, unsaved changes stay queued
 * (and visible) and are sent after the next successful load; listeners of `save-failed` are told.
 * Writes are refused until the first load, so a view rendering defaults can't overwrite real
 * settings. API keys never pass through here: they go to the keyring directly.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { getProviderType } from '../providers/catalog.js';
import { getProviderProfile, resolveProviderId } from '../providers/profiles.js';
import { parseProviderConfigs, type StoredProviderConfig } from '../providers/configStore.js';
import type { ProviderId } from '../providers/types.js';
import { Logger, Tag } from '../utils/logger.js';
import type { ConfigDoc, ConfigReply, LogEntry, ModelsReply, ProviderSettings } from './protocol.js';

export type Call = <T>(method: string, args?: object) => Promise<T>;
/** `detail` is the changed key for `changed`/`changed::<key>`, the error message for `save-failed`. */
type Listener = (settings: RuntimeSettings, detail: string) => void;
type Mutation = (doc: ConfigDoc) => void;

const PROVIDER_FIELDS = ['model', 'url', 'mode', 'thinking', 'reasoning_effort'] as const;
type ProviderField = (typeof PROVIDER_FIELDS)[number];

interface FieldEdit {
    provider: string;
    field: ProviderField;
    value: string;
}

const MAX_CONFLICT_RETRIES = 3;

export interface ModelListResult {
    models: string[];
    requiresApiKey: boolean;
}

const KEYS = ['provider', 'provider-type', 'provider-configs'] as const;

export class RuntimeSettings {
    private _doc: ConfigDoc = emptyDoc();
    private _revision = -1;
    private _providerType: string | null = null;
    private _listeners = new Map<number, { signal: string; fn: Listener }>();
    private _nextId = 1;
    private _pending: Mutation[] = [];
    /** Changes being sent right now (not in the runtime's copy until it answers). */
    private _sending: Mutation[] = [];
    private _flushing: Promise<void> | null = null;
    /** A save failed for a reason other than a conflict; wait for the next load before retrying. */
    private _held = false;

    constructor(private readonly _call: Call) {}

    get loaded(): boolean {
        return this._revision >= 0;
    }

    /** Adopt the runtime's copy (initial load, reconnect, or `config.changed`), then send anything unsaved. */
    async reload(): Promise<void> {
        const reply = await this._call<ConfigReply>('GetConfig');
        this.applyRemote(reply);
        if (this._held) {
            this._held = false;
            void this._flush();
        }
    }

    applyRemote(reply: ConfigReply): void {
        if (reply.revision <= this._revision && this.loaded) return;
        const before = KEYS.map(k => this.get_string(k));
        const retention = this.retentionDays;
        this._doc = normalize(reply.config);
        this._revision = reply.revision;
        for (const change of [...this._sending, ...this._pending]) change(this._doc); // not saved yet: keep showing them
        KEYS.forEach((k, i) => {
            if (this.get_string(k) !== before[i]) this._emit(k);
        });
        if (this.retentionDays !== retention) this._emit('privacy');
    }

    /** Resolves once every change made so far has been sent (or has failed to send). */
    async flushed(): Promise<void> {
        while (this._flushing) await this._flushing;
    }

    /** The model chosen for a provider, or '' when none is. */
    modelFor(provider: string): string {
        return this._doc.providers[provider]?.model ?? '';
    }

    /** Days after which untouched conversations are deleted; null keeps them until the user deletes them. */
    get retentionDays(): number | null {
        return this._doc.privacy.conversation_retention_days;
    }

    setRetentionDays(days: number | null): void {
        if (!this.loaded) throw new Error('settings are not loaded yet');
        if (days === this.retentionDays) return;
        this._mutate(doc => {
            doc.privacy = { ...doc.privacy, conversation_retention_days: days };
        }, 'privacy');
    }

    get_string(key: string): string {
        if (key === 'provider') return this._doc.active;
        if (key === 'provider-type') {
            if (this._providerType) return this._providerType;
            const id = resolveProviderId(this._doc.active);
            return id ? getProviderProfile(id).type : 'local';
        }
        if (key === 'provider-configs') return JSON.stringify(toStored(this._doc.providers));
        return '';
    }

    set_string(key: string, value: string): boolean {
        if (!this.loaded) {
            Logger.warn(Tag.Extension, `Ignoring ${key} change before settings have loaded from the runtime`);
            return false;
        }
        if (this.get_string(key) === value) return true;
        if (key === 'provider-type') {
            this._providerType = getProviderType(value); // a view filter, not a stored setting
            this._emit(key);
            return true;
        }
        if (key === 'provider') {
            const id = resolveProviderId(value);
            if (!id || !getProviderProfile(id).selectable) return false;
            this._mutate(doc => {
                doc.active = id;
            }, key);
            return true;
        }
        if (key === 'provider-configs') {
            // Callers pass the whole document; keep only what they changed, so replaying it after
            // a conflict can't undo someone else's change to another field.
            const edits = diffProviders(this._doc.providers, parseProviderConfigs(value));
            if (edits.length) this._mutate(doc => applyEdits(doc, edits), key);
            return true;
        }
        return false;
    }

    connect(signal: string, fn: Listener): number {
        const id = this._nextId++;
        this._listeners.set(id, { signal, fn });
        return id;
    }

    disconnect(id: number): void {
        this._listeners.delete(id);
    }

    async listModels(provider: ProviderId, overrides: { url?: string } = {}): Promise<ModelListResult> {
        // The runtime only sends a stored key to the endpoint saved in settings, so save first.
        await this.flushed();
        const reply = await this._call<ModelsReply>('ListModels', { provider, url: overrides.url ?? '' });
        if (reply.error) throw new Error(reply.error);
        return { models: reply.models, requiresApiKey: reply.requires_key && reply.from_fallback };
    }

    async fetchLogs(): Promise<LogEntry[]> {
        return (await this._call<{ entries: LogEntry[] }>('GetLogs', { after: 0 })).entries;
    }

    async clearLogs(): Promise<void> {
        await this._call('ClearLogs');
    }

    private _mutate(change: Mutation, key: string): void {
        change(this._doc);
        this._pending.push(change);
        if (key === 'provider') this._providerType = null; // the type follows the chosen provider again
        this._emit(key);
        void this._flush();
    }

    private _flush(): Promise<void> {
        if (this._held) return Promise.resolve();
        this._flushing ??= this._send().finally(() => {
            this._flushing = null;
            if (this._pending.length && !this._held) void this._flush();
        });
        return this._flushing;
    }

    private async _send(): Promise<void> {
        const changes = this._pending.splice(0);
        if (!changes.length) return;
        this._sending = changes;
        try {
            await this._sendWithRetries(changes);
        } finally {
            this._sending = [];
        }
    }

    private async _sendWithRetries(changes: Mutation[]): Promise<void> {
        for (let attempt = 0; ; attempt++) {
            try {
                const reply = await this._call<{ revision: number }>('UpdateConfig', { revision: this._revision, config: this._doc });
                this._revision = Math.max(this._revision, reply.revision);
                return;
            } catch (e) {
                const conflict = (e as { code?: string }).code === 'Conflict';
                if (!conflict || attempt === MAX_CONFLICT_RETRIES) {
                    this._hold(changes, (e as Error).message);
                    return;
                }
            }
            // Someone else saved first: take their copy and replay our field changes on top.
            try {
                const fresh = await this._call<ConfigReply>('GetConfig');
                this._doc = normalize(fresh.config);
                this._revision = fresh.revision;
                changes.forEach(change => change(this._doc));
            } catch (e) {
                this._hold(changes, (e as Error).message);
                return;
            }
        }
    }

    /** Keep unsaved changes queued until the next successful load, and say so. */
    private _hold(changes: Mutation[], message: string): void {
        this._pending.unshift(...changes);
        this._held = true;
        Logger.warn(Tag.Extension, `Saving settings failed; will retry after reconnecting: ${message}`);
        this._notify('save-failed', message);
    }

    private _emit(key: string): void {
        for (const { signal, fn } of [...this._listeners.values()]) {
            if (signal === 'changed' || signal === `changed::${key}`) fn(this, key);
        }
    }

    private _notify(signal: string, detail: string): void {
        for (const listener of [...this._listeners.values()]) {
            if (listener.signal === signal) listener.fn(this, detail);
        }
    }
}

function diffProviders(current: Record<string, ProviderSettings>,
    next: Record<string, StoredProviderConfig>): FieldEdit[] {
    const edits: FieldEdit[] = [];
    for (const [provider, stored] of Object.entries(next)) {
        const after: Record<ProviderField, string> = {
            model: stored.modelName ?? '', url: stored.url ?? '', mode: stored.mode ?? '',
            thinking: stored.thinking ?? '', reasoning_effort: stored.reasoningEffort ?? '',
        };
        for (const field of PROVIDER_FIELDS) {
            if ((current[provider]?.[field] ?? '') !== after[field]) edits.push({ provider, field, value: after[field] });
        }
    }
    return edits;
}

function applyEdits(doc: ConfigDoc, edits: FieldEdit[]): void {
    for (const { provider, field, value } of edits) {
        doc.providers[provider] = { ...(doc.providers[provider] ?? emptyProvider()), [field]: value };
    }
}

function emptyProvider(): ProviderSettings {
    return { model: '', url: '', mode: '', thinking: '', reasoning_effort: '', options: {} };
}

function emptyDoc(): ConfigDoc {
    return { active: '', providers: {}, privacy: { conversation_retention_days: null } };
}

function normalize(doc: Partial<ConfigDoc> | undefined): ConfigDoc {
    return {
        ...doc,
        active: doc?.active ?? '',
        providers: { ...(doc?.providers ?? {}) },
        privacy: { ...doc?.privacy, conversation_retention_days: doc?.privacy?.conversation_retention_days ?? null },
    };
}

function toStored(providers: Record<string, ProviderSettings>): Record<string, StoredProviderConfig> {
    const out: Record<string, StoredProviderConfig> = {};
    for (const [id, p] of Object.entries(providers)) {
        out[id] = {
            url: p.url, modelName: p.model, apiKey: '', apiKeyStorage: '', mode: p.mode,
            thinking: p.thinking, reasoningEffort: p.reasoning_effort,
        };
    }
    return out;
}
