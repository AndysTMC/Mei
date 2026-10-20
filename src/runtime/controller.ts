/**
 * Runtime-backed chat for the popup.
 *
 * The popup keeps its current API; this class decides what to show from the projection. All
 * conversation state lives in the runtime, so closing the popup, disabling the extension, or a
 * Shell restart loses nothing: reconnecting re-attaches and redraws.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import GLib from 'gi://GLib';

import { getProviderProfile, resolveProviderId } from '../providers/profiles.js';
import type { ChatMessageMetadata, ProviderId } from '../providers/types.js';
import type { ChatPopup } from '../ui/chatPopup.js';
import { Logger, Tag } from '../utils/logger.js';
import { RuntimeClient, RuntimeError, type ConnectionStatus } from './client.js';
import { Projection } from './projection.js';
import type { ConversationReply, Envelope, MessageView, SetupStatusReply, SubmitReply } from './protocol.js';
import { RuntimeSettings } from './settings.js';

interface PopupMessage {
    role: string;
    content: string;
    thinking?: string;
    metadata?: ChatMessageMetadata;
}

export class RuntimeChatController {
    onStateChanged: (() => void) | null = null;

    private readonly _projection = new Projection();
    private readonly _client = new RuntimeClient(() => this._projection.seq);
    private _current: string | null = null;
    private _status: ConnectionStatus = 'connecting';
    private _statusDetail = '';
    /** Provider settings owned by the runtime; the popup's settings view and prefs read and write these. */
    readonly settings: RuntimeSettings;
    /** Index in the rendered list of the interrupted draft, which ↻ resumes. */
    private _draftIndex = -1;

    private _popup!: ChatPopup;
    private _setupChecked = false;
    /** Called once when setup was never offered (the extension opens Settings). */
    onSetupNeeded: (() => void) | null = null;
    /** Whether this controller asked for setup to open (read by the dev-build test hooks). */
    setupOffered = false;

    constructor() {
        this.settings = new RuntimeSettings((method, args) => this._client.call(method, args));
        this._client.onAttached = reply => {
            this._projection.applyAttach(reply);
            if (reply.mode === 'snapshot' && this._current) void this._loadConversation(this._current);
            this._reloadSettings();
            void this._checkSetup();
            this._render();
        };
        this._client.onEvent = event => this._onEvent(event);
        this._client.onStatus = (status, detail) => {
            this._status = status;
            this._statusDetail = detail ?? '';
            if (status === 'incompatible') this._popup.showError(`⚠ ${detail}`);
            this.onStateChanged?.();
        };
    }

    get isStreaming(): boolean {
        return this._current !== null && this._projection.activeTask(this._current) !== null;
    }

    get draftIndex(): number {
        return this._draftIndex;
    }

    /** Open the most recently updated conversation, as picking it from the history list would. */
    debugLoadLatest(): void {
        const latest = this._projection.summaries()[0];
        if (latest) this.loadChat(latest.id);
    }

    /** What the controller believes; for dev-build test hooks. */
    debugState(): Record<string, unknown> {
        const stream = this._current ? this._projection.streamFor(this._current) : null;
        const conv = this._current ? this._projection.loaded.get(this._current) : undefined;
        return {
            status: this._status, current: this._current, seq: this._projection.seq, streaming: this.isStreaming,
            messages: conv?.messages.map(m => ({ role: m.role, content: m.content })) ?? [],
            stream: stream ? { text: stream.text, chunk: stream.chunk, stale: stream.stale } : null,
            interrupted: this._current ? this._projection.interruptedTask(this._current)?.draft ?? null : null,
            provider: this.settings.get_string('provider'),
            setupOffered: this.setupOffered,
        };
    }

    /** The popup is built with `settings`, so it's bound after construction and before `start()`. */
    bind(popup: ChatPopup): void {
        this._popup = popup;
    }

    start(): void {
        this._client.start();
    }

    destroy(): void {
        this._client.destroy();
    }

    // ── Popup callbacks ─────────────────────────────────────────────────────

    send(text: string): void {
        this._popup.hideError();
        const unusable = this._providerProblem();
        if (unusable) {
            this._popup.showError(`⚠ ${unusable}`);
            return;
        }
        if (this._status === 'unavailable' || this._status === 'incompatible') {
            this._popup.showError(`⚠ Mei's runtime isn't reachable. ${this._statusDetail}`);
            return;
        }
        if (!this._popup.isExpanded) this._popup.close();
        this._client.call<SubmitReply>('SubmitInput', {
            command_id: GLib.uuid_string_random(),
            conversation_id: this._current,
            text,
        }).then(reply => {
            this._current = reply.conversation_id;
            this._render();
        }).catch((e: RuntimeError) => this._showFailure(e));
    }

    cancel(): void {
        const task = this._current ? this._projection.activeTask(this._current) : null;
        if (!task) return;
        this._client.call('Cancel', { command_id: GLib.uuid_string_random(), task_id: task.id })
            .catch((e: RuntimeError) => this._showFailure(e));
    }

    newChat(): void {
        this._current = null;
        this._draftIndex = -1;
        this._popup.setLoading(false);
        this._popup.clearMessages();
        this._popup.hideError();
        this.onStateChanged?.();
    }

    showHistoryList(): void {
        this._popup.showHistoryList(this._projection.summaries().map(s => ({ id: s.id, title: s.title })));
    }

    loadChat(id: string): void {
        this._current = id;
        void this._loadConversation(id);
    }

    deleteChat(id: string): void {
        this._client.call('DeleteConversation', { command_id: GLib.uuid_string_random(), conversation_id: id })
            .then(() => {
                if (this._current === id) this.newChat();
            })
            .catch((e: RuntimeError) => this._showFailure(e));
    }

    reload(index: number): void {
        const interrupted = this._current ? this._projection.interruptedTask(this._current) : null;
        if (interrupted && index === this._draftIndex) {
            this._popup.hideError();
            this._client.call('Resume', { command_id: GLib.uuid_string_random(), task_id: interrupted.id })
                .catch((e: RuntimeError) => this._showFailure(e));
            return;
        }
        this._popup.showError('⚠ Regenerating a reply isn’t available with the Mei runtime yet.');
    }

    toggleExpand(isExpanded: boolean): void {
        if (isExpanded) {
            this._render();
        } else {
            this._popup.showMessage('assistant', this._lastAssistant());
        }
    }

    // ── Events and rendering ────────────────────────────────────────────────

    private _onEvent(event: Envelope): void {
        const result = this._projection.applyEvent(event);
        if (result === 'gap') {
            Logger.warn(Tag.Extension, `Missed runtime events before seq ${event.seq}; re-attaching`);
            this._client.reattach();
            return;
        }
        if (result !== 'applied') return;
        if (event.type === 'config.changed') {
            this._reloadSettings();
            return;
        }
        if (this._current === null || event.conversation_id !== this._current) return;
        if (event.type === 'message.delta') {
            const stream = this._projection.streamFor(this._current);
            if (stream && this._popup.isExpanded) this._popup.showStreamingResponse(stream.text, stream.thinking);
            return;
        }
        if (event.type === 'task.finished') this._onTaskFinished(event);
        else if (event.type === 'message.completed') this._render();
        else this._syncLoading(); // status-only events (task accepted/running, model started)
        this.onStateChanged?.();
    }

    private _onTaskFinished(event: Envelope): void {
        const state = event.payload.state as string;
        const error = event.payload.error as string | null;
        this._render();
        if (state === 'FAILED') {
            this._popup.showError(`⚠ ${error ?? 'Mei could not answer.'}`);
            this._popup.open();
        } else if (state === 'INTERRUPTED') {
            this._popup.showError('⚠ Mei restarted while answering. Use ↻ on the partial reply to continue.');
        } else if (state === 'COMPLETED' && !this._popup.isExpanded) {
            this._popup.showMessage('assistant', this._lastAssistant());
            this._popup.open();
        }
    }

    private _render(): void {
        this.onStateChanged?.();
        if (!this._current) return;
        const conv = this._projection.loaded.get(this._current);
        if (!conv) return;
        const active = this._projection.activeTask(this._current);
        if (!this._popup.isExpanded) {
            if (!active) this._popup.setLoading(false);
            return;
        }
        const messages: PopupMessage[] = conv.messages.map(toPopupMessage);
        const interrupted = this._projection.interruptedTask(this._current);
        this._draftIndex = -1;
        if (interrupted?.draft) {
            this._draftIndex = messages.length;
            messages.push({
                role: 'assistant',
                content: `${interrupted.draft.text}\n\n*(interrupted — ↻ to continue)*`,
                thinking: interrupted.draft.thinking || undefined,
            });
        }
        // showHistory() rebuilds the message list, which takes the loading bubble (and the streamed
        // text inside it) with it. Drop it first and attach a fresh one after, never the reverse.
        this._popup.setLoading(false);
        this._popup.showHistory(messages, !active);
        if (!active) return;
        this._popup.setLoading(true);
        const stream = this._projection.streamFor(this._current);
        if (stream && (stream.text || stream.thinking)) this._popup.showStreamingResponse(stream.text, stream.thinking);
    }

    private _syncLoading(): void {
        if (!this._current) return;
        this._popup.setLoading(this._projection.activeTask(this._current) !== null);
    }

    private async _loadConversation(id: string): Promise<void> {
        try {
            const reply = await this._client.call<ConversationReply>('GetConversation', { conversation_id: id });
            this._projection.applyConversation(reply);
            if (this._current === id) this._render();
        } catch (e) {
            this._showFailure(e as RuntimeError);
        }
    }

    private _lastAssistant(): string {
        const conv = this._current ? this._projection.loaded.get(this._current) : undefined;
        const last = conv?.messages.filter(m => m.role === 'assistant').at(-1);
        return last?.content ?? '';
    }

    private _showFailure(error: RuntimeError): void {
        const message = error.code === 'Busy' ? 'Mei is still answering. Stop it first, or wait.' : error.message;
        this._popup.setLoading(false);
        this._popup.showError(`⚠ ${message}`);
        this._popup.open();
    }

    // ── Setup ───────────────────────────────────────────────────────────────

    /** Asks once per enable whether setup was ever offered; Settings marks it offered when it opens. */
    private async _checkSetup(): Promise<void> {
        if (this._setupChecked) return;
        this._setupChecked = true;
        try {
            const status = await this._client.call<SetupStatusReply>('SetupStatus');
            if (!status.completed && !status.offered && this.onSetupNeeded) {
                this.setupOffered = true;
                this.onSetupNeeded();
            }
        } catch (e) {
            Logger.warn(Tag.Extension, `Checking setup failed: ${(e as Error).message}`);
        }
    }

    // ── Provider settings ───────────────────────────────────────────────────

    private _reloadSettings(): void {
        this.settings.reload().catch(e => Logger.warn(Tag.Extension, `Loading settings failed: ${(e as Error).message}`));
    }

    /** Why sending can't work with the current settings, if it can't. */
    private _providerProblem(): string | null {
        if (!this.settings.loaded) return null; // the runtime will answer for itself
        const id = resolveProviderId(this.settings.get_string('provider'));
        if (!id) return 'Choose a model provider in Mei\'s settings first.';
        const profile = getProviderProfile(id);
        if (!profile.selectable) return `${profile.label} is no longer available. Choose another provider in Mei's settings.`;
        return this.settings.modelFor(id).trim() ? null : `Choose a ${profile.label} model in Mei's settings first.`;
    }
}

function toPopupMessage(m: MessageView): PopupMessage {
    const meta = m.metadata as Record<string, unknown>;
    const tokens = meta.tokens as { input?: number | null; output?: number | null } | undefined;
    return {
        role: m.role,
        content: m.content,
        thinking: m.thinking ?? undefined,
        metadata: m.role !== 'assistant' ? undefined : {
            providerId: (meta.id as ProviderId) || undefined,
            providerLabel: (meta.label as string) || undefined,
            model: (meta.model as string) || undefined,
            durationMs: typeof meta.duration_ms === 'number' ? meta.duration_ms : undefined,
            tokens: tokens ? { inputTokens: tokens.input ?? undefined, outputTokens: tokens.output ?? undefined } : undefined,
        },
    };
}
