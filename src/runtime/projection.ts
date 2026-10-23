/**
 * Pure reducer from runtime events to view state (architecture §18.1). The only place in the
 * extension that interprets events; views read `Projection` and never the protocol directly.
 *
 * Durable events carry a global `seq`: anything at or below what we've applied is a duplicate.
 * Live, a jump means we missed something, so the caller must re-attach. A replay is different:
 * it is the runtime's own list of the surviving events after our cursor, and events of deleted
 * conversations are gone from it, so its seqs may jump without anything being missing. Deltas
 * are ordered per message by `chunk`; a jump there marks the stream stale until its message
 * completes.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import {
    TERMINAL_STATES,
    type ActionView,
    type ApprovalView,
    type AttachReply,
    type ConversationReply,
    type ConversationSummary,
    type Draft,
    type Envelope,
    type InputRequestView,
    type MemoryView,
    type MessageView,
    type Outcome,
    type Plan,
    type StreamView,
    type TaskState,
    type TaskView,
} from './protocol.js';

export interface LoadedConversation {
    summary: ConversationSummary;
    messages: MessageView[];
    tasks: Map<string, TaskView>;
    /** What Mei remembered in this conversation (2.3), by id. */
    memories: Map<string, MemoryView>;
    /** Events for this conversation at or below this seq are already reflected. */
    loadedSeq: number;
}

export interface LiveStream extends StreamView {
    stale: boolean;
}

export type ApplyResult = 'applied' | 'duplicate' | 'gap' | 'ignored';

const WAITING: ReadonlySet<string> = new Set(['WAITING_APPROVAL', 'WAITING_INPUT', 'WAITING_RESOURCE']);
const MEMORY_EVENTS = new Set(['memory.saved', 'memory.pending_review', 'memory.updated', 'memory.deleted']);
const ACTION_EVENTS = new Set(['action.proposed', 'policy.decided', 'action.started', 'action.updated', 'action.finished']);
/** Events that change a conversation's loaded messages or tasks (skipped while it isn't loaded). */
const NEEDS_LOADED = new Set(['message.completed', 'task.accepted', 'task.state_changed', 'task.finished',
    'plan.updated', 'approval.requested', 'approval.resolved', 'input.requested', 'input.answered', ...ACTION_EVENTS,
    ...MEMORY_EVENTS]);

export class Projection {
    epoch: string | null = null;
    seq = 0;
    readonly conversations = new Map<string, ConversationSummary>();
    readonly loaded = new Map<string, LoadedConversation>();
    readonly streams = new Map<string, LiveStream>();
    /** Per conversation not loaded yet, the newest event we had to skip for it (see applyConversation). */
    private readonly _skipped = new Map<string, number>();

    applyAttach(reply: AttachReply): ApplyResult[] {
        this.epoch = reply.epoch;
        const results: ApplyResult[] = [];
        if (reply.mode === 'snapshot') {
            this.conversations.clear();
            this.loaded.clear();
            this._skipped.clear();
            for (const c of reply.snapshot?.conversations ?? []) this.conversations.set(c.id, c);
            this.seq = reply.seq;
        } else {
            for (const event of reply.events ?? []) results.push(this._applyDurable(event));
            this.seq = Math.max(this.seq, reply.seq);
        }
        this.streams.clear();
        for (const s of reply.streams) this.streams.set(s.message_id, { ...s, stale: false });
        return results;
    }

    /**
     * Adopt a conversation fetched with GetConversation. Returns false, changing nothing, if an
     * event for it arrived after the runtime built this reply: that event was skipped (the
     * conversation wasn't loaded yet) and isn't in the reply, so the caller must fetch again.
     */
    applyConversation(reply: ConversationReply): boolean {
        if ((this._skipped.get(reply.conversation.id) ?? 0) > reply.seq) return false;
        this._skipped.delete(reply.conversation.id);
        const latest = reply.tasks.filter(t => !TERMINAL_STATES.has(t.state)).sort((a, b) => a.created_at - b.created_at).at(-1);
        const summary = { ...reply.conversation, active: latest?.state ?? null };
        this.conversations.set(summary.id, summary);
        this.loaded.set(summary.id, {
            summary,
            messages: [...reply.messages],
            tasks: new Map(reply.tasks.map(t => [t.id, { ...t }])),
            memories: new Map((reply.memories ?? []).map(m => [m.id, m])),
            loadedSeq: reply.seq,
        });
        for (const [id, s] of this.streams) {
            if (s.conversation_id === reply.conversation.id) this.streams.delete(id);
        }
        for (const s of reply.streams) this.streams.set(s.message_id, { ...s, stale: false });
        return true;
    }

    /** A live event. */
    applyEvent(event: Envelope): ApplyResult {
        if (event.seq === null) return this._applyEphemeral(event);
        // A jump means events are missing. Don't apply or advance: the caller re-attaches from
        // `seq`, and the replay brings back the missing events and this one in order.
        if (this.seq > 0 && event.seq > this.seq + 1) return 'gap';
        return this._applyDurable(event);
    }

    private _applyDurable(event: Envelope): ApplyResult {
        if (event.seq === null || event.seq <= this.seq) return 'duplicate';
        this.seq = event.seq;
        this._reduce(event);
        return 'applied';
    }

    /** The task currently blocking input in a conversation, if any. */
    activeTask(conversationId: string): TaskView | null {
        const conv = this.loaded.get(conversationId);
        if (!conv) return null;
        let latest: TaskView | null = null;
        for (const task of conv.tasks.values()) {
            if (TERMINAL_STATES.has(task.state) || task.state === 'INTERRUPTED') continue;
            if (!latest || task.created_at >= latest.created_at) latest = task;
        }
        return latest;
    }

    interruptedTask(conversationId: string): TaskView | null {
        const conv = this.loaded.get(conversationId);
        if (!conv) return null;
        for (const task of conv.tasks.values()) if (task.state === 'INTERRUPTED') return task;
        return null;
    }

    /** The task in this conversation waiting on the person (an approval card or a question), if any. */
    waitingTask(conversationId: string): TaskView | null {
        const task = this.activeTask(conversationId);
        return task && (task.approval || task.input_request) ? task : null;
    }

    /** Conversations with a card waiting on the person, for the indicator. */
    needsAttention(): string[] {
        return this.summaries().filter(s => WAITING.has(s.active ?? '') || this.waitingTask(s.id) !== null).map(s => s.id);
    }

    /** Whether a task is working in any conversation (not waiting on the person, not interrupted). */
    anyWorking(): boolean {
        return this.summaries().some(s => s.active && !WAITING.has(s.active) && s.active !== 'INTERRUPTED');
    }

    streamFor(conversationId: string): LiveStream | null {
        for (const s of this.streams.values()) if (s.conversation_id === conversationId) return s;
        return null;
    }

    summaries(): ConversationSummary[] {
        return [...this.conversations.values()].sort((a, b) => b.updated_at - a.updated_at);
    }

    private _reduce(event: Envelope): void {
        const p = event.payload;
        const convId = event.conversation_id;
        const conv = convId ? this.loaded.get(convId) : undefined;
        const fresh = conv !== undefined && (event.seq ?? 0) > conv.loadedSeq;
        if (convId && !conv && event.seq !== null && NEEDS_LOADED.has(event.type)) this._skipped.set(convId, event.seq);
        this._trackActive(event);
        switch (event.type) {
        case 'conversation.created': {
            const summary = p.conversation as ConversationSummary;
            this.conversations.set(summary.id, summary);
            // A conversation's first event: everything after it arrives as events, so track it now.
            this.loaded.set(summary.id, { summary, messages: [], tasks: new Map(), memories: new Map(), loadedSeq: event.seq ?? 0 });
            break;
        }
        case 'conversation.deleted': {
            const id = p.conversation_id as string;
            this.conversations.delete(id);
            this.loaded.delete(id);
            this._skipped.delete(id);
            for (const [mid, s] of this.streams) if (s.conversation_id === id) this.streams.delete(mid);
            break;
        }
        case 'message.completed': {
            const message = p.message as MessageView;
            const summary = this.conversations.get(message.conversation_id);
            if (summary) summary.updated_at = Math.max(summary.updated_at, message.created_at);
            this.streams.delete(message.id);
            if (fresh && !conv.messages.some(m => m.id === message.id)) conv.messages.push(message);
            break;
        }
        case 'task.accepted':
            if (fresh) {
                const task = p.task as TaskView;
                conv.tasks.set(task.id, { ...task });
            }
            break;
        case 'task.state_changed':
            if (fresh) {
                const task = conv.tasks.get(p.task_id as string);
                if (task) {
                    task.state = p.to as TaskState;
                    task.error = (p.error as string | null) ?? null;
                    if (task.state === 'RUNNING') delete task.draft;
                }
            }
            break;
        case 'model.started': {
            const messageId = p.message_id as string;
            if (convId && event.task_id) {
                this.streams.set(messageId, {
                    conversation_id: convId, task_id: event.task_id, message_id: messageId,
                    text: '', thinking: '', chunk: 0, stale: false,
                });
            }
            break;
        }
        case 'task.finished': {
            for (const [mid, s] of this.streams) if (s.task_id === event.task_id) this.streams.delete(mid);
            if (fresh) {
                const task = conv.tasks.get(p.task_id as string);
                if (task) {
                    task.state = p.state as TaskState;
                    task.error = (p.error as string | null) ?? null;
                    if (p.draft) task.draft = p.draft as Draft;
                    if (p.outcome) task.outcome = p.outcome as Outcome;
                    task.approval = null;
                    task.input_request = null;
                }
            }
            break;
        }
        default:
            if (fresh) this._reduceAgent(event, conv);
            break; // other unknown durable events are skippable unless `required` (checked by the client)
        }
    }

    /** Keep each summary's `active` current, loaded or not: the history list and indicator read it. */
    private _trackActive(event: Envelope): void {
        const summary = event.conversation_id ? this.conversations.get(event.conversation_id) : undefined;
        if (!summary) return;
        const p = event.payload;
        let state: TaskState | undefined;
        if (event.type === 'task.accepted') state = (p.task as TaskView).state;
        else if (event.type === 'task.state_changed') state = p.to as TaskState;
        else if (event.type === 'task.finished') state = p.state as TaskState;
        if (state !== undefined) summary.active = TERMINAL_STATES.has(state) ? null : state;
    }

    /** Actions, approvals, questions, and the plan (protocol 2.2); memories (2.3). */
    private _reduceAgent(event: Envelope, conv: LoadedConversation): void {
        if (MEMORY_EVENTS.has(event.type)) {
            if (event.type === 'memory.deleted') conv.memories.delete(event.payload.memory_id as string);
            else conv.memories.set((event.payload.memory as MemoryView).id, event.payload.memory as MemoryView);
            return;
        }
        const task = event.task_id ? conv.tasks.get(event.task_id) : undefined;
        if (!task) return;
        const p = event.payload;
        if (ACTION_EVENTS.has(event.type)) {
            const action = p.action as ActionView;
            const actions = (task.actions ??= []);
            const at = actions.findIndex(a => a.id === action.id);
            if (at >= 0) actions[at] = action;
            else actions.push(action);
            return;
        }
        switch (event.type) {
        case 'plan.updated':
            task.plan = p.plan as Plan;
            break;
        case 'approval.requested':
            task.approval = p.approval as ApprovalView;
            break;
        case 'approval.resolved':
            if (task.approval?.id === p.approval_id) task.approval = null;
            break;
        case 'input.requested':
            task.input_request = p.request as InputRequestView;
            break;
        case 'input.answered':
            if (task.input_request?.id === p.request_id) task.input_request = null;
            break;
        default:
            break;
        }
    }

    private _applyEphemeral(event: Envelope): ApplyResult {
        if (event.type !== 'message.delta') return 'ignored';
        const p = event.payload;
        const stream = this.streams.get(p.message_id as string);
        if (!stream) return 'ignored';
        const chunk = p.chunk as number;
        if (chunk <= stream.chunk) return 'duplicate';
        if (chunk !== stream.chunk + 1) stream.stale = true; // missed deltas; message.completed fixes it
        stream.chunk = chunk;
        stream.text += (p.text as string) ?? '';
        stream.thinking += (p.thinking as string) ?? '';
        return stream.stale ? 'gap' : 'applied';
    }
}
