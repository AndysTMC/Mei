/**
 * Provider settings backed by the runtime (protocol 2), shaped like the `Gio.Settings` keys the
 * popup and preferences used before: `provider`, `provider-type`, and `provider-configs`.
 *
 * Reads are synchronous from a local copy; writes update the copy, notify listeners, and are sent
 * to the runtime with compare-and-set (retried once on a conflict by replaying the change onto
 * the fresh copy). Writes are refused until the first load, so a view rendering defaults can't
 * overwrite real settings. API keys never pass through here: they go to the keyring directly.
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
type Listener = (settings: RuntimeSettings, key: string) => void;
type Mutation = (doc: ConfigDoc) => void;

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
    private _flushing: Promise<void> | null = null;

    constructor(private readonly _call: Call) {}

    get loaded(): boolean {
        return this._revision >= 0;
    }

    /** Adopt the runtime's copy (initial load, or after `config.changed`). */
    async reload(): Promise<void> {
        const reply = await this._call<ConfigReply>('GetConfig');
        this.applyRemote(reply);
    }

    applyRemote(reply: ConfigReply): void {
        if (reply.revision <= this._revision && this.loaded) return;
        const before = KEYS.map(k => this.get_string(k));
        const retention = this.retentionDays;
        this._doc = normalize(reply.config);
        this._revision = reply.revision;
        KEYS.forEach((k, i) => {
            if (this.get_string(k) !== before[i]) this._emit(k);
        });
        if (this.retentionDays !== retention) this._emit('privacy');
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
            let parsed: Record<string, StoredProviderConfig>;
            try {
                parsed = parseProviderConfigs(value);
            } catch {
                return false;
            }
            this._mutate(doc => {
                for (const [id, stored] of Object.entries(parsed)) {
                    const previous = doc.providers[id];
                    doc.providers[id] = {
                        model: stored.modelName ?? '',
                        url: stored.url ?? '',
                        mode: stored.mode ?? '',
                        thinking: stored.thinking ?? '',
                        reasoning_effort: stored.reasoningEffort ?? '',
                        options: previous?.options ?? {},
                    };
                }
            }, key);
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
        this._flushing ??= this._send().finally(() => {
            this._flushing = null;
            if (this._pending.length) void this._flush();
        });
        return this._flushing;
    }

    private async _send(): Promise<void> {
        const changes = this._pending.splice(0);
        if (!changes.length) return;
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                const reply = await this._call<{ revision: number }>('UpdateConfig', { revision: this._revision, config: this._doc });
                this._revision = reply.revision;
                return;
            } catch (e) {
                if ((e as { code?: string }).code !== 'Conflict') {
                    Logger.warn(Tag.Extension, `Saving settings failed: ${(e as Error).message}`);
                    return;
                }
                // Someone else saved first: take their copy and replay our changes on top.
                const fresh = await this._call<ConfigReply>('GetConfig');
                this._doc = normalize(fresh.config);
                this._revision = fresh.revision;
                changes.forEach(change => change(this._doc));
            }
        }
    }

    private _emit(key: string): void {
        for (const { signal, fn } of [...this._listeners.values()]) {
            if (signal === 'changed' || signal === `changed::${key}`) fn(this, key);
        }
    }
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
