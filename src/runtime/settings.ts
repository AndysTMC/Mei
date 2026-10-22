/**
 * Mei's settings, owned by the runtime (ADR 0002), as seen by the popup and the Settings window.
 *
 * Reads are synchronous from a local copy. Each write changes one field: it is applied to the
 * copy, announced to listeners, and sent to the runtime with compare-and-set. On a conflict the
 * same field changes are replayed onto the runtime's newer copy, so a concurrent change to another
 * field survives. If the runtime can't be reached, unsaved changes stay queued (and visible) and
 * are sent after the next successful load; `save-failed` listeners are told. Writes are refused
 * until the first load, so a view showing defaults can't overwrite real settings. API keys never
 * pass through here: they go to the keyring directly.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { getProviderProfile, resolveProviderId } from '../providers/profiles.js';
import type { ProviderId } from '../providers/types.js';
import { Logger, Tag } from '../utils/logger.js';
import type {
    ApprovalPreset, CloudFiles, ConfigDoc, ConfigReply, GrantView, LogEntry, MemoriesReply, MemoryPatch, MicLevelReply,
    ModelsReply, ProviderSettings, VoiceDevicesReply, VoiceModelsReply, VoiceSettingsDoc,
} from './protocol.js';

export type Call = <T>(method: string, args?: object) => Promise<T>;
/** What changed, for `changed` and `changed::<key>`. */
export type SettingsKey = 'active' | 'providers' | 'privacy' | 'approvals' | 'memory' | 'voice';
/** `detail` is the changed key for `changed`/`changed::<key>`, the error message for `save-failed`. */
type Listener = (settings: RuntimeSettings, detail: string) => void;
type Mutation = (doc: ConfigDoc) => void;

export type ProviderField = 'model' | 'url' | 'mode' | 'thinking' | 'reasoning_effort';

export interface ModelListResult {
    models: string[];
    /** The provider needs a key and none is saved, so `models` are suggestions. */
    requiresApiKey: boolean;
}

const KEYS: SettingsKey[] = ['active', 'providers', 'privacy', 'approvals', 'memory', 'voice'];
const MAX_CONFLICT_RETRIES = 3;

export class RuntimeSettings {
    private _doc: ConfigDoc = emptyDoc();
    private _revision = -1;
    private readonly _listeners = new Map<number, { signal: string; fn: Listener }>();
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
        const before = KEYS.map(key => this._snapshot(key));
        this._doc = normalize(reply.config);
        this._revision = reply.revision;
        for (const change of [...this._sending, ...this._pending]) change(this._doc); // not saved yet: keep showing them
        KEYS.forEach((key, i) => {
            if (this._snapshot(key) !== before[i]) this._emit(key);
        });
    }

    /** Resolves once every change made so far has been sent (or has failed to send). */
    async flushed(): Promise<void> {
        while (this._flushing) await this._flushing;
    }

    // ── Reading ──────────────────────────────────────────────────────────────

    /** The provider new conversations use, or '' when none is chosen yet. */
    get active(): string {
        return this._doc.active;
    }

    /** One provider's settings (empty values if it was never configured). */
    provider(id: string): Readonly<ProviderSettings> {
        return this._doc.providers[id] ?? emptyProvider();
    }

    /** Days after which untouched conversations are deleted; null keeps them until the user deletes them. */
    get retentionDays(): number | null {
        return this._doc.privacy.conversation_retention_days;
    }

    /** Which file contents may go to a cloud model (§13.5). */
    get cloudFiles(): CloudFiles {
        return this._doc.privacy.cloud_files ?? 'pointed';
    }

    /** Which actions go ahead without asking (§13.2); the safety floor holds under every preset. */
    get approvalPreset(): ApprovalPreset {
        return this._doc.approvals?.preset ?? 'balanced';
    }

    /** Whether Mei recalls memories into tasks and saves new ones (§17). */
    get memoryEnabled(): boolean {
        return this._doc.memory?.enabled ?? true;
    }

    /** Whether facts Mei infers are kept without review (what the person states always is). */
    get memoryAutoSave(): boolean {
        return this._doc.memory?.auto_save ?? true;
    }

    /** Voice settings (§11), with the runtime's defaults for what isn't stored yet. */
    get voice(): Readonly<VoiceSettingsDoc> {
        return voiceOf(this._doc);
    }

    // ── Writing ──────────────────────────────────────────────────────────────

    /** Choose the provider for new conversations. Refuses unknown and retired providers. */
    setActive(id: string): boolean {
        const resolved = resolveProviderId(id);
        if (!resolved || !getProviderProfile(resolved).selectable || !this._writable()) return false;
        if (resolved !== this.active) {
            this._mutate(doc => {
                doc.active = resolved;
            }, 'active');
        }
        return true;
    }

    setProviderField(id: string, field: ProviderField, value: string): void {
        if (!this._writable() || this.provider(id)[field] === value) return;
        this._mutate(doc => {
            doc.providers[id] = { ...(doc.providers[id] ?? emptyProvider()), [field]: value };
        }, 'providers');
    }

    setRetentionDays(days: number | null): void {
        if (!this.loaded) throw new Error('settings are not loaded yet');
        if (days === this.retentionDays) return;
        this._mutate(doc => {
            doc.privacy = { ...doc.privacy, conversation_retention_days: days };
        }, 'privacy');
    }

    setCloudFiles(value: CloudFiles): void {
        if (!this._writable() || value === this.cloudFiles) return;
        this._mutate(doc => {
            doc.privacy = { ...doc.privacy, cloud_files: value };
        }, 'privacy');
    }

    setApprovalPreset(preset: ApprovalPreset): void {
        if (!this._writable() || preset === this.approvalPreset) return;
        this._mutate(doc => {
            doc.approvals = { ...doc.approvals, preset };
        }, 'approvals');
    }

    setMemoryEnabled(enabled: boolean): void {
        if (!this._writable() || enabled === this.memoryEnabled) return;
        this._mutate(doc => {
            doc.memory = { ...memoryOf(doc), enabled };
        }, 'memory');
    }

    setMemoryAutoSave(autoSave: boolean): void {
        if (!this._writable() || autoSave === this.memoryAutoSave) return;
        this._mutate(doc => {
            doc.memory = { ...memoryOf(doc), auto_save: autoSave };
        }, 'memory');
    }

    setVoice<K extends VoiceField>(field: K, value: VoiceSettingsDoc[K]): void {
        if (!this._writable() || this.voice[field] === value) return;
        this._mutate(doc => {
            doc.voice = { ...voiceOf(doc), [field]: value };
        }, 'voice');
    }

    // ── Runtime calls that belong with settings ──────────────────────────────

    async voiceModels(): Promise<VoiceModelsReply> {
        return this._call<VoiceModelsReply>('VoiceModels');
    }

    async downloadVoiceModels(ids: string[]): Promise<void> {
        await this._call('VoiceDownload', { models: ids });
    }

    /** Listens a few seconds in silence; returns only the level. */
    async checkMic(): Promise<MicLevelReply> {
        return this._call<MicLevelReply>('VoiceCheckMic');
    }

    async fixMic(): Promise<MicLevelReply> {
        return this._call<MicLevelReply>('VoiceFixMic');
    }

    async testSpeaker(): Promise<void> {
        await this._call('VoiceTestSpeaker');
    }

    /** The microphones and speakers PipeWire knows (listing them opens no audio). */
    async voiceDevices(): Promise<VoiceDevicesReply> {
        return this._call<VoiceDevicesReply>('VoiceDevices');
    }

    /** Memories matching `query` (all when empty), optionally only those with `status`. */
    async memories(query = '', status: '' | 'active' | 'pending_review' | 'archived' = ''): Promise<MemoriesReply> {
        return this._call<MemoriesReply>('Memories', { query, status });
    }

    async updateMemory(id: string, patch: MemoryPatch): Promise<void> {
        await this._call('UpdateMemory', { command_id: uuid(), memory_id: id, patch });
    }

    async forgetMemory(id: string): Promise<void> {
        await this._call('ForgetMemory', { command_id: uuid(), memory_id: id });
    }

    /** Deletes every memory. Returns how many there were. */
    async forgetEverything(): Promise<number> {
        return (await this._call<{ forgotten: number }>('ForgetMemory', { command_id: uuid(), everything: true })).forgotten;
    }

    /** Things the person told Mei it may always do (persistent grants, §13.3). */
    async listGrants(): Promise<GrantView[]> {
        return (await this._call<{ grants: GrantView[] }>('ListGrants')).grants;
    }

    async revokeGrant(id: string): Promise<void> {
        await this._call('RevokeGrant', { command_id: uuid(), grant_id: id });
    }

    async listModels(provider: ProviderId, url = ''): Promise<ModelListResult> {
        // The runtime only sends a stored key to the endpoint saved in settings, so save first.
        await this.flushed();
        const reply = await this._call<ModelsReply>('ListModels', { provider, url });
        if (reply.error) throw new Error(reply.error);
        return { models: reply.models, requiresApiKey: reply.requires_key && reply.from_fallback };
    }

    async fetchLogs(): Promise<LogEntry[]> {
        return (await this._call<{ entries: LogEntry[] }>('GetLogs', { after: 0 })).entries;
    }

    async clearLogs(): Promise<void> {
        await this._call('ClearLogs');
    }

    // ── Signals ──────────────────────────────────────────────────────────────

    /** `changed`, `changed::active|providers|privacy|approvals|memory`, or `save-failed`. */
    connect(signal: string, fn: Listener): number {
        const id = this._nextId++;
        this._listeners.set(id, { signal, fn });
        return id;
    }

    disconnect(id: number): void {
        this._listeners.delete(id);
    }

    // ── Sending ──────────────────────────────────────────────────────────────

    private _writable(): boolean {
        if (!this.loaded) Logger.warn(Tag.Extension, 'Ignoring a settings change before settings have loaded from the runtime');
        return this.loaded;
    }

    private _mutate(change: Mutation, key: SettingsKey): void {
        change(this._doc);
        this._pending.push(change);
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

    private _snapshot(key: SettingsKey): string {
        if (key === 'active') return this._doc.active;
        return JSON.stringify(this._doc[key]);
    }

    private _emit(key: SettingsKey): void {
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

export type VoiceField = 'enabled' | 'speak_replies' | 'stt' | 'tts' | 'voice' | 'cloud_voice' | 'kokoro_speaker'
    | 'speed' | 'device' | 'barge_in' | 'wake_word' | 'end_silence_ms' | 'mic' | 'output';

const VOICE_DEFAULTS: VoiceSettingsDoc = {
    enabled: false, speak_replies: true, stt: 'local', tts: 'piper', voice: 'amy', cloud_voice: '', kokoro_speaker: 0,
    speed: 1.0, device: 'auto', barge_in: false, wake_word: false, end_silence_ms: 500, mic: '', output: '',
};

function voiceOf(doc: ConfigDoc): VoiceSettingsDoc {
    return { ...VOICE_DEFAULTS, ...doc.voice };
}

function memoryOf(doc: ConfigDoc): NonNullable<ConfigDoc['memory']> {
    return { enabled: true, auto_save: true, ...doc.memory };
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
        approvals: { ...doc?.approvals, preset: doc?.approvals?.preset ?? 'balanced' },
        memory: { ...doc?.memory, enabled: doc?.memory?.enabled ?? true, auto_save: doc?.memory?.auto_save ?? true },
    };
}

/** A command id; the runtime only needs it unique (crypto.randomUUID isn't in GJS). */
function uuid(): string {
    const hex = (n: number) => Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join('');
    return `${hex(8)}-${hex(4)}-4${hex(3)}-${hex(4)}-${hex(12)}`;
}
