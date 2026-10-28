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
import type { Answer } from '../ui/conversation/cards.js';
import type { ChatPopup, ChatSummary } from '../ui/chatPopup.js';
import { Logger, Tag } from '../utils/logger.js';
import { RuntimeClient, RuntimeError, type ConnectionStatus } from './client.js';
import { activeLabel, noticeFor, reaction, wantsPerson, type Notice, type Reaction } from './notices.js';
import { Projection } from './projection.js';
import { withDrop, type Drop } from './attachment.js';
import type { VoiceView } from './voice.js';
import type {
    ApprovalScope, Attachment, ConversationReply, Envelope, LatestPictureReply, PdfInfoReply, PdfPageReply, Picture,
    SetupStatusReply, SubmitReply, VoiceStateName, VoiceStatusReply,
} from './protocol.js';
import { RuntimeSettings } from './settings.js';
import { buildTimeline, latestReply, pendingInteraction, workView, type TimelineItem } from './timeline.js';

const LOAD_ATTEMPTS = 3;
/** Events that change what a conversation shows besides its messages. */
const AGENT_EVENTS = new Set(['action.proposed', 'policy.decided', 'action.started', 'action.updated', 'action.finished',
    'plan.updated', 'approval.requested', 'approval.resolved', 'input.requested', 'input.answered',
    'memory.saved', 'memory.pending_review', 'memory.updated', 'memory.deleted']);
/** Events that put a card in front of the person. */
const ASKS = new Set(['approval.requested', 'input.requested']);
/** Events that change a conversation's task in progress (the history list and indicator show it). */
const TASK_EVENTS = new Set(['task.accepted', 'task.state_changed', 'task.finished']);

export class RuntimeChatController {
    onStateChanged: (() => void) | null = null;
    /** A task finished or needs the person somewhere the popup isn't showing (§18.4). */
    onNotice: ((notice: Notice) => void) | null = null;

    private readonly _projection = new Projection();
    private readonly _client: RuntimeClient;
    private _current: string | null = null;
    private _status: ConnectionStatus = 'connecting';
    private _statusDetail = '';
    /** Provider settings owned by the runtime; the popup's settings view and prefs read and write these. */
    readonly settings: RuntimeSettings;
    /** Index in the rendered list of the interrupted draft, which ↻ resumes. */
    private _draftIndex = -1;

    private _popup!: ChatPopup;
    private _setupChecked = false;
    /** The last notice sent, for the dev-build test hooks. */
    private _lastNotice: Notice | null = null;
    /** What "Ask about this" attached to the next message, until it is sent or dropped. */
    private _attachment: Attachment | null = null;
    /** Voice (2.4): the runtime's voice state and what it has heard. */
    private _voice: VoiceView = { state: 'off', note: '', transcript: '', dictating: false };
    /** The runtime holds the attachment for the next thing said in a conversation. */
    private _voiceHasAttachment = false;
    /** The reply Read aloud is reading (decision 0030), or none. */
    private _reading: string | null = null;
    /** Pictures of the screen already looked up, by the action that kept them. */
    private readonly _pictures = new Map<string, Picture>();
    /** Dev-build test hooks only: a picture to show as the latest, since the nested Shell's e2e has
     * no screen session to take one. Never set otherwise. */
    debugPicture: Picture | null = null;
    /** Called once when setup was never offered (the extension opens Settings). */
    onSetupNeeded: (() => void) | null = null;
    /** Whether this controller asked for setup to open (read by the dev-build test hooks). */
    setupOffered = false;

    /** `bridgePath`: where the Shell bridge is exported, offered to the runtime in Hello (§12.6). */
    constructor(bridgePath = '') {
        this._client = new RuntimeClient(() => this._projection.seq, bridgePath);
        this.settings = new RuntimeSettings((method, args) => this._client.call(method, args));
        this._client.onAttached = reply => {
            this._projection.applyAttach(reply);
            void this._loadVoiceStatus();
            if (reply.mode === 'snapshot' && this._current) void this._loadConversation(this._current);
            this._reloadSettings();
            void this._checkSetup();
            this._render();
        };
        this._client.onEvent = event => this._onEvent(event);
        this._client.onStatus = (status, detail) => {
            this._status = status;
            this._statusDetail = detail ?? '';
            if (status === 'connected') this._popup.hideError('connection');
            if (status === 'incompatible') this._popup.showError(detail ?? 'This Mei runtime doesn’t match the extension; update Mei.');
            this.onStateChanged?.();
        };
    }

    get isStreaming(): boolean {
        return this._current !== null && this._projection.activeTask(this._current) !== null;
    }

    get draftIndex(): number {
        return this._draftIndex;
    }

    /** Whether any conversation has a card waiting on the person (the indicator shows it). */
    get needsAttention(): boolean {
        return this._projection.needsAttention().length > 0;
    }

    /** Whether a task is working in any conversation, shown or not. */
    get isBusy(): boolean {
        return this._projection.anyWorking();
    }

    get currentConversation(): string | null {
        return this._current;
    }

    /** The kill switch's call to the runtime: kill the desktop worker and stop the task using it. */
    stopComputerUse(reason: string): void {
        this._client.call('KillSwitch', { reason })
            .catch((e: RuntimeError) => Logger.warn(Tag.Extension, `Kill switch: ${e.message}`));
    }

    /** The unique bus name the runtime has now, the only caller the Shell bridge serves. */
    get runtimeOwner(): string | null {
        return this._client.owner;
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
            provider: this.settings.active,
            attachment: this._attachment,
            voice: this._voice,
            setupOffered: this.setupOffered,
            timeline: this._debugTimeline(),
            waiting: this.needsAttention,
            busy: this.isBusy,
            notice: this._lastNotice,
            history: this._historyItems(),
        };
    }

    /** The timeline's kinds, plus what waits on the person and whether the latest reply has its outcome. */
    private _debugTimeline(): string[] {
        const conv = this._current ? this._projection.loaded.get(this._current) : undefined;
        const items = this._timeline();
        const kinds: string[] = items.map(i => i.kind);
        const interaction = conv ? pendingInteraction(conv) : null;
        if (interaction) kinds.push(interaction.kind);
        if (items.some(i => i.kind === 'message' && i.details?.outcome)) kinds.push('outcome');
        return kinds;
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
            this._popup.showError(unusable);
            this._popup.restoreDraft(text);
            return;
        }
        if (this._status === 'unavailable' || this._status === 'incompatible') {
            this._popup.showError(`Mei's runtime isn't reachable. ${this._statusDetail}`, { source: 'connection' });
            this._popup.restoreDraft(text);
            return;
        }
        if (!this._popup.isExpanded) this._popup.close();
        const attachment = this._attachment;
        this._client.call<SubmitReply>('SubmitInput', {
            command_id: GLib.uuid_string_random(),
            conversation_id: this._current,
            text,
            ...(attachment ? { attachment } : {}),
        }).then(reply => {
            this._current = reply.conversation_id;
            if (this._attachment === attachment) this._setAttachment(null);
            this._render();
        }).catch((e: RuntimeError) => {
            this._popup.restoreDraft(text);  // not taken: what they wrote isn't lost
            this._showFailure(e);
        });
    }

    get voiceState(): VoiceStateName {
        return this._voice.state;
    }

    /** The voice shortcut: talk (until 30 s pass with nothing said); while listening, send what's
     * been said, or with nothing said, stop; while Mei speaks, stop it and talk (decision 0026). */
    voiceListen(): void {
        this._listen(false, 'shortcut');
    }

    /** The voice button: talk with Mei until closed; while listening, send what's been said, or
     * with nothing said, close; while Mei thinks or speaks, close. */
    voiceToggle(): void {
        if (['thinking', 'speaking', 'paused'].includes(this._voice.state) && !this._voice.dictating) this.voiceStop();
        else this._listen(false, 'button');
    }

    /** The mic: dictate into the message box, across pauses; again: done. */
    dictate(): void {
        this._listen(true, 'button');
    }

    /** A reply's Read aloud: Mei reads it out; pressed while Mei speaks, it stops. */
    /** A reply's Read aloud (decision 0030): Mei reads it out on its own, not as Live; pressed again
     * while that reply is being read, it stops. */
    readAloud(messageId: string, text: string): void {
        const method = this._reading === messageId ? 'VoiceStopReading' : 'VoiceReadAloud';
        this._client.call(method, method === 'VoiceReadAloud' ? { message_id: messageId, text } : {})
            .catch((e: RuntimeError) => this._showFailure(e));
    }

    voiceStop(): void {
        this._client.call('VoiceStop', {}).catch((e: RuntimeError) => this._showFailure(e));
    }

    private _listen(dictate: boolean, by: 'shortcut' | 'button'): void {
        this._popup.hideError('voice');
        const starting = !['listening', 'paused'].includes(this._voice.state);
        if (starting) this._voice = { ...this._voice, dictating: dictate };
        this._client.call<VoiceStatusReply>('VoiceListen', { conversation_id: this._current, dictate, by })
            .catch((e: RuntimeError) => {
                this._voice = { ...this._voice, dictating: false };
                this._showVoice();
                if (e.code !== 'Unavailable') {
                    this._showFailure(e);
                    return;
                }
                // Not ready (models to download, a setting): a way forward, not an error.
                this._popup.showError(`Voice isn't ready: ${e.message}`, { source: 'voice',
                    action: { label: 'Set up', run: () => this._popup.onOpenSettings?.() } });
                this._popup.open();
            });
    }

    /** "Ask about this" (§18.4): a new chat whose first message carries the window and selection. */
    askAbout(attachment: Attachment | null): void {
        if (this._popup.isShowingHistory) this._popup.hideHistoryList();
        this.newChat();
        this._setAttachment(attachment);
        this._popup.open();
    }

    /** Files or text dropped on Mei's button (0027): they go with the next message in this conversation. */
    attachDrop(drop: Drop): void {
        if (this._popup.isShowingHistory) this._popup.hideHistoryList();
        this._setAttachment(withDrop(this._attachment, drop));
        this._popup.open();
    }

    removeAttachment(): void {
        this._setAttachment(null);
    }

    private _setAttachment(attachment: Attachment | null): void {
        this._attachment = attachment;
        this._popup.showAttachment(attachment);
        if (this._talking()) this._attachToVoice();
    }

    /** In a conversation, what's said goes to Mei from the runtime, not from the message box: the
     * attachment goes there too, with the next thing said (decision 0028). */
    private _attachToVoice(): void {
        this._voiceHasAttachment = this._attachment !== null;
        this._client.call('VoiceAttach', { attachment: this._attachment })
            .catch((e: RuntimeError) => this._showFailure(e));
    }

    /** Talking with Mei (not dictating): listening, thinking, speaking, or paused for another app. */
    private _talking(): boolean {
        return !this._voice.dictating && ['listening', 'thinking', 'speaking', 'paused'].includes(this._voice.state);
    }

    approve(approvalId: string, scope: ApprovalScope): void {
        this._resolve({ approval_id: approvalId, decision: 'allow', scope });
    }

    deny(approvalId: string): void {
        this._resolve({ approval_id: approvalId, decision: 'deny', scope: 'once' });
    }

    /** Decline, then say what to do instead: the words join the task, as a message would. */
    denyWith(approvalId: string, text: string): void {
        this._resolve({ approval_id: approvalId, decision: 'deny', scope: 'once' }, () => this.send(text));
    }

    answer(requestId: string, value: Answer): void {
        this._popup.hideError();
        this._client.call('AnswerInput', { command_id: GLib.uuid_string_random(), request_id: requestId, value })
            .catch((e: RuntimeError) => {
                this._popup.retryInteraction();
                this._showFailure(e);
            });
    }

    /** A task paused while the person used the computer: go on now. */
    resume(taskId: string): void {
        this._popup.hideError();
        this._client.call('Resume', { command_id: GLib.uuid_string_random(), task_id: taskId })
            .catch((e: RuntimeError) => {
                this._popup.retryInteraction();
                this._showFailure(e);
            });
    }

    /** The work page's Pause: no further act until Go on (Resume). */
    pause(taskId: string): void {
        this._client.call('Pause', { command_id: GLib.uuid_string_random(), task_id: taskId })
            .catch((e: RuntimeError) => this._showFailure(e));
    }

    // ── The large page (decision 0034) ──────────────────────────────────────

    /** The work page for this task of the conversation shown, with its latest picture. */
    openWork(taskId: string): void {
        const conv = this._current ? this._projection.loaded.get(this._current) : undefined;
        const view = conv ? workView(conv, taskId) : null;
        if (!view) return;
        this._popup.showWork(this._withDebugPicture(view));
        void this._showWorkPicture();
    }

    /** The newest picture a task kept; looked up once per picture. */
    async findPicture(taskId: string, actionId: string): Promise<Picture | null> {
        if (this.debugPicture) return this.debugPicture;
        const known = this._pictures.get(actionId);
        if (known) return known;
        if (!this._current) return null;
        const reply = await this._client.call<LatestPictureReply>('LatestPicture',
            { conversation_id: this._current, task_id: taskId });
        if (reply.picture) this._pictures.set(reply.picture.action_id, reply.picture);
        return reply.picture;
    }

    /** The runtime draws PDF pages for the viewer: the Shell has no Poppler. */
    readonly pdfPages = {
        info: (path: string) => this._client.call<PdfInfoReply>('PdfInfo', { path }),
        page: (path: string, page: number, width: number) => this._client.call<PdfPageReply>('PdfPage', { path, page, width }),
    };

    /** The work page, if it shows a task of this conversation: its newer state, and a newer picture. */
    private _refreshWork(): void {
        const taskId = this._popup.workTaskId;
        const conv = this._current ? this._projection.loaded.get(this._current) : undefined;
        const view = taskId && conv ? workView(conv, taskId) : null;
        if (!view) return;
        this._popup.showWork(this._withDebugPicture(view));
        if (view.picture !== this._popup.workPicture || this.debugPicture) void this._showWorkPicture();
    }

    private async _showWorkPicture(): Promise<void> {
        const taskId = this._popup.workTaskId;
        const conv = this._current ? this._projection.loaded.get(this._current) : undefined;
        const found = taskId && conv ? workView(conv, taskId) : null;
        const view = found ? this._withDebugPicture(found) : null;
        if (!view?.picture) return;
        try {
            const picture = await this.findPicture(view.taskId, view.picture);
            if (picture && this._popup.workTaskId === view.taskId) this._popup.showWorkPicture(picture);
        } catch (e) {
            Logger.warn(Tag.Extension, `LatestPicture: ${(e as Error).message}`);
        }
    }

    /** In dev-build tests, the test's picture stands for the latest one (see `debugPicture`). */
    private _withDebugPicture<T extends { picture: string | null }>(item: T): T {
        return this.debugPicture && !item.picture ? { ...item, picture: this.debugPicture.action_id } : item;
    }

    stopTask(taskId: string): void {
        this._popup.hideError();
        this._client.call('Cancel', { command_id: GLib.uuid_string_random(), task_id: taskId })
            .catch((e: RuntimeError) => {
                this._popup.retryInteraction();
                this._showFailure(e);
            });
    }

    /** From the popup, which only the Shell process can show: no "Mei will now remember" notification. */
    keepMemory(memoryId: string): void {
        this._popup.hideError();
        this._client.call('UpdateMemory', { command_id: GLib.uuid_string_random(), memory_id: memoryId,
            patch: { status: 'active' } }).catch((e: RuntimeError) => this._showFailure(e));
    }

    forgetMemory(memoryId: string): void {
        this._popup.hideError();
        this._client.call('ForgetMemory', { command_id: GLib.uuid_string_random(), memory_id: memoryId })
            .catch((e: RuntimeError) => this._showFailure(e));
    }

    private _resolve(args: { approval_id: string; decision: 'allow' | 'deny'; scope: ApprovalScope }, then?: () => void): void {
        this._popup.hideError();
        this._client.call('ResolveApproval', { command_id: GLib.uuid_string_random(), ...args })
            .then(() => then?.())
            .catch((e: RuntimeError) => {
                this._popup.retryInteraction();
                this._showFailure(e);
            });
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
        if (this._attachment) this._setAttachment(null);
        this._popup.setLoading(false);
        this._popup.clearMessages();
        this._popup.hideError();
        this.onStateChanged?.();
    }

    showHistoryList(): void {
        this._popup.showHistoryList(this._historyItems());
    }

    loadChat(id: string): void {
        this._current = id;
        void this._loadConversation(id);
    }

    /** From a notification: show this conversation in the popup, in whichever mode it is in. */
    openConversation(id: string): void {
        this._popup.hideHistoryList();
        if (this._current !== id) this.newChat();
        this._current = id;
        this._popup.open();
        void this._loadConversation(id);
    }

    /** Newest first, each with what its task in progress is doing, if it has one. */
    private _historyItems(): ChatSummary[] {
        return this._projection.summaries().map(s => ({ id: s.id, title: s.title, active: activeLabel(s.active) }));
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
        this._popup.showError('Regenerating a reply isn’t available with the Mei runtime yet.');
    }

    toggleExpand(_isExpanded: boolean): void {
        this._render();
    }

    // ── Events and rendering ────────────────────────────────────────────────

    private _onEvent(event: Envelope): void {
        if (event.type === 'voice.state' || event.type === 'voice.partial') {
            this._onVoice(event);
            return;
        }
        if (event.type === 'voice.reading') {
            const id = String(event.payload.message_id ?? '');
            if (event.payload.reading) this._reading = id;
            else if (this._reading === id) this._reading = null;
            this._popup.setReading(this._reading);
            return;
        }
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
        const react = this._react(event);
        if (TASK_EVENTS.has(event.type) && this._popup.isShowingHistory) this._popup.refreshHistoryList(this._historyItems());
        if (this._current === null || event.conversation_id !== this._current) {
            if (TASK_EVENTS.has(event.type)) this.onStateChanged?.();
            return;
        }
        if (event.type === 'message.delta') {
            const stream = this._projection.streamFor(this._current);
            if (stream && this._popup.isExpanded) this._popup.showStreamingResponse(stream.text, stream.thinking);
            return;
        }
        // A spoken request's answer, or what it needs from the person, opens the popup (decision 0026).
        const voice = this._answeringByVoice() && !this._popup.isOpen;
        if (event.type === 'task.finished') this._onTaskFinished(event, react === 'open' || voice);
        else if (ASKS.has(event.type)) this._onAsk(react === 'open' || voice);
        else if (event.type === 'message.completed' || AGENT_EVENTS.has(event.type)) this._render();
        else this._syncLoading(); // status-only events (task accepted/running, model started)
        if (event.task_id && event.task_id === this._popup.workTaskId) this._refreshWork();
        this.onStateChanged?.();
    }

    /**
     * Whether a finished task or a new card reopens the popup, arrives as a notification, or needs
     * nothing more because the person is looking at it (see notices.ts).
     */
    private _react(event: Envelope): Reaction {
        if (!wantsPerson(event) || !event.conversation_id) return 'none';
        const id = event.conversation_id;
        const current = id === this._current;
        const task = current && event.task_id ? this._projection.loaded.get(id)?.tasks.get(event.task_id) : undefined;
        const react = reaction(event, {
            current,
            showing: current && this._popup.isOpen && !this._popup.isShowingHistory,
            elapsedMs: task ? Date.now() - task.created_at : null,
        });
        if (react === 'notify') {
            const notice = noticeFor(event, this._projection.conversations.get(id));
            if (notice) {
                this._lastNotice = notice;
                this.onNotice?.(notice);
            }
        }
        return react;
    }

    // ── Voice ───────────────────────────────────────────────────────────────

    private _onVoice(event: Envelope): void {
        const p = event.payload;
        if (event.type === 'voice.partial') {
            if (p.dictation) {  // into the message box; the words as heard, before the tidy-up, go along
                const text = String(p.text ?? '');
                this._popup.dictate(text, Boolean(p.final), typeof p.raw === 'string' ? p.raw : text);
            }
            else this._voice = { ...this._voice, transcript: String(p.text ?? '') };
        } else {
            const state = p.state as VoiceStateName;
            const conversation = (p.conversation_id as string | null) ?? null;
            if (state === 'listening' && this._voice.state !== 'listening') this._voice.transcript = '';
            // Mei answers out loud: show the answer too (the shortcut and "Hey Mei" don't open the popup).
            if (state === 'speaking' && this._voice.state === 'thinking' && !this._popup.isOpen) this._popup.open();
            // Dictating or talking: as the runtime says (a reload mid-dictation mustn't lose it).
            const dictating = typeof p.dictating === 'boolean' ? p.dictating : this._voice.dictating;
            const wasTalking = this._talking();
            this._voice = { ...this._voice, state, note: String(p.note ?? ''), dictating };
            // An attachment waiting in the box joins a conversation that starts; once something is
            // said (thinking), it went with that request.
            if (this._talking() && !wasTalking && this._attachment && !this._voiceHasAttachment) this._attachToVoice();
            if (state === 'thinking' && this._voiceHasAttachment) {
                this._voiceHasAttachment = false;
                this._attachment = null;
                this._popup.showAttachment(null);
            }
            // A spoken request starts or continues a conversation: show it, as sending one would.
            if (state === 'thinking' && conversation && conversation !== this._current) this.loadChat(conversation);
            if (state === 'idle' || state === 'off' || state === 'unavailable')
                this._voice = { ...this._voice, transcript: '' };
            if (state === 'idle' || state === 'listening') this._popup.hideError('voice');  // ready now
        }
        this._showVoice();
        this.onStateChanged?.();
    }

    /** Mei is working on something the person asked out loud (not dictation). */
    private _answeringByVoice(): boolean {
        return !this._voice.dictating && ['thinking', 'speaking'].includes(this._voice.state);
    }

    private _showVoice(): void {
        this._popup.showVoice(this._voice);
    }

    private async _loadVoiceStatus(): Promise<void> {
        try {
            const status = await this._client.call<VoiceStatusReply>('VoiceStatus');
            this._voice = { state: status.state, note: status.note, transcript: '', dictating: false };
        } catch (e) {
            Logger.debug(Tag.Extension, `VoiceStatus: ${(e as Error).message}`);  // an older runtime: no voice
            this._voice = { state: 'off', note: '', transcript: '', dictating: false };
        }
        this._showVoice();
    }

    /** Something now waits on the person: it takes the input area, in either mode. */
    private _onAsk(open: boolean): void {
        this._render();
        if (open) this._popup.open();
    }

    private _onTaskFinished(event: Envelope, open: boolean): void {
        const state = event.payload.state as string;
        const error = event.payload.error as string | null;
        this._render();
        if (state === 'FAILED') this._popup.showError(`${error ?? 'Mei could not answer.'}`);
        else if (state === 'INTERRUPTED') this._popup.showError('Mei restarted while answering. Regenerate the partial reply to continue.');
        if (open) this._popup.open();
    }

    /** The conversation (expanded) or its latest reply (compact), and what waits on the person. */
    private _render(): void {
        this.onStateChanged?.();
        if (!this._current) return;
        const conv = this._projection.loaded.get(this._current);
        if (!conv) return;
        const active = this._projection.activeTask(this._current);
        const all = this._timeline();
        const items = this._popup.isExpanded ? all : latestReply(all);
        // showTimeline() rebuilds the message list, which takes the loading bubble (and the streamed
        // text inside it) with it. Drop it first and attach a fresh one after, never the reverse.
        this._popup.setLoading(false);
        this._popup.showTimeline(items, !active);
        this._popup.showInteraction(pendingInteraction(conv));
        if (!active || this._projection.waitingTask(this._current)) return; // waiting on the person: no spinner
        this._popup.setLoading(true);
        const stream = this._projection.streamFor(this._current);
        if (stream && (stream.text || stream.thinking)) this._popup.showStreamingResponse(stream.text, stream.thinking);
    }

    /** The current conversation as the popup shows it, with an interrupted reply's draft at the end. */
    private _timeline(): TimelineItem[] {
        const conv = this._current ? this._projection.loaded.get(this._current) : undefined;
        if (!conv || !this._current) return [];
        const items = buildTimeline(conv).map(i => (i.kind === 'progress' ? this._withDebugPicture(i) : i));
        const interrupted = this._projection.interruptedTask(this._current);
        this._draftIndex = -1;
        if (interrupted?.draft) {
            this._draftIndex = items.length;
            items.push({
                kind: 'message', draft: true, message: {
                    id: `draft-${interrupted.id}`, conversation_id: this._current, task_id: interrupted.id,
                    role: 'assistant', content: `${interrupted.draft.text}\n\n*(interrupted: regenerate to continue)*`,
                    thinking: interrupted.draft.thinking || null, metadata: {}, created_at: interrupted.updated_at,
                },
            });
        }
        return items;
    }

    private _syncLoading(): void {
        if (!this._current) return;
        const active = this._projection.activeTask(this._current);
        this._popup.setLoading(active !== null && this._projection.waitingTask(this._current) === null);
    }

    private async _loadConversation(id: string): Promise<void> {
        try {
            // A reply can be overtaken by events for the same conversation; then fetch again.
            for (let attempt = 0; attempt < LOAD_ATTEMPTS; attempt++) {
                const reply = await this._client.call<ConversationReply>('GetConversation', { conversation_id: id });
                if (this._projection.applyConversation(reply)) {
                    if (this._current === id) this._render();
                    return;
                }
            }
            Logger.warn(Tag.Extension, `Gave up loading conversation ${id}: it changed during each of ${LOAD_ATTEMPTS} attempts`);
        } catch (e) {
            this._showFailure(e as RuntimeError);
        }
    }

    private _showFailure(error: RuntimeError): void {
        const message = error.code === 'Busy' ? 'Mei is still answering. Stop it first, or wait.' : error.message;
        this._popup.setLoading(false);
        this._popup.showError(`${message}`);
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
        if (this.settings.active === 'fake') return null; // the runtime's scripted provider (tests, offline work)
        const id = resolveProviderId(this.settings.active);
        if (!id) return 'Choose a model provider in Mei\'s settings first.';
        const profile = getProviderProfile(id);
        if (!profile.selectable) return `${profile.label} is no longer available. Choose another provider in Mei's settings.`;
        return this.settings.provider(id).model.trim() ? null : `Choose a ${profile.label} model in Mei's settings first.`;
    }
}
