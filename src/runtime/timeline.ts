/**
 * What a conversation shows, in order (§18.2): each request, then one reply to it, the latest thing
 * Mei said for that task. What Mei said on the way, the actions it took, and how the task ended are
 * details of that reply, opened on demand. While a task runs, its steps show under it as progress.
 * A card waiting on the person isn't part of the conversation: it takes over the input area
 * (`pendingInteraction`). Pure: built from the projection, rendered by ui/conversation; no GJS here.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { TERMINAL_STATES } from './protocol.js';
import type { ActionView, ApprovalView, InputRequestView, MemoryView, MessageView, Outcome, TaskView } from './protocol.js';
import type { LoadedConversation } from './projection.js';

/** Tools that steer the task rather than act; their effect shows as the plan, a card, or the outcome. */
const META = new Set(['plan.update', 'ask_user', 'task.finish', 'plan_update', 'task_finish']);

export type ActivityState = 'done' | 'running' | 'waiting' | 'failed' | 'refused' | 'skipped' | 'unclear';

export interface ActivityRow {
    id: string;
    text: string;
    state: ActivityState;
    /** Why it failed or was refused, or that a done action didn't take effect. */
    detail?: string;
}

/** What's behind a reply's icons: what Mei did on the way, and how the task ended. */
export interface ReplyDetails {
    /** What Mei said before its reply, in order. */
    notes: string[];
    steps: ActivityRow[];
    outcome: Outcome | null;
}

export type TimelineItem =
    | { kind: 'message'; message: MessageView; draft?: boolean; details?: ReplyDetails }
    /** `picture`: the latest action that kept a picture of the screen, shown as a thumbnail. */
    | { kind: 'progress'; taskId: string; rows: ActivityRow[]; picture: string | null }
    | { kind: 'memory'; memory: MemoryView };

/** What a task waits on the person for: it replaces the input area until answered. */
export type Interaction =
    | { kind: 'approval'; taskId: string; approval: ApprovalView }
    | { kind: 'question'; taskId: string; request: InputRequestView }
    /** Computer use waits while the person uses the mouse or keyboard (§10.3); it goes on by itself. */
    | { kind: 'paused'; taskId: string; note: string };

export function buildTimeline(conv: LoadedConversation): TimelineItem[] {
    const tasks = [...conv.tasks.values()];
    const byInput = new Map(tasks.map(t => [t.input_message_id, t]));
    const remembered = [...conv.memories.values()].filter(m => m.status !== 'archived')
        .sort((a, b) => a.created_at - b.created_at);
    const items: TimelineItem[] = [];
    for (const message of conv.messages) {
        if (message.role === 'assistant' && message.task_id && conv.tasks.has(message.task_id)) continue; // under its request
        if (message.role !== 'user') {
            if (message.role === 'assistant' && message.content.trim()) items.push({ kind: 'message', message });
            continue;
        }
        items.push({ kind: 'message', message });
        const task = byInput.get(message.id);
        if (task) items.push(...taskItems(conv, task, remembered));
    }
    for (const memory of remembered) if (!memory.source_task_id || !conv.tasks.has(memory.source_task_id)) items.push({ kind: 'memory', memory });
    return items;
}

function taskItems(conv: LoadedConversation, task: TaskView, remembered: MemoryView[]): TimelineItem[] {
    const said = conv.messages.filter(m => m.role === 'assistant' && m.task_id === task.id && m.content.trim());
    const steps = (task.actions ?? []).filter(a => !isMeta(a))
        .sort((a, b) => a.created_at - b.created_at || a.position - b.position).map(activityRow);
    const items: TimelineItem[] = [];
    const reply = said.at(-1);
    if (reply) {
        items.push({ kind: 'message', message: reply,
            details: { notes: said.slice(0, -1).map(m => m.content), steps, outcome: task.outcome ?? null } });
    }
    // While it runs: the steps so far, but not one waiting on the person (the input area asks).
    const progress = steps.filter(r => r.state !== 'waiting');
    const picture = latestPicture(task);
    if (!TERMINAL_STATES.has(task.state) && (progress.length || picture))
        items.push({ kind: 'progress', taskId: task.id, rows: progress, picture });
    for (const memory of remembered) if (memory.source_task_id === task.id) items.push({ kind: 'memory', memory });
    return items;
}

/** What the small popup shows: the latest reply and what follows it, or, while Mei is still working
 * on the latest request, its progress so far. */
export function latestReply(items: TimelineItem[]): TimelineItem[] {
    const reply = items.findLastIndex(i => i.kind === 'message' && i.message.role === 'assistant');
    const request = items.findLastIndex(i => i.kind === 'message' && i.message.role === 'user');
    return reply > request ? items.slice(reply) : items.slice(request + 1);
}

/** The latest card a task in this conversation waits on the person for, if any. */
export function pendingInteraction(conv: LoadedConversation): Interaction | null {
    const waiting = [...conv.tasks.values()].filter(t => !TERMINAL_STATES.has(t.state)
        && (t.approval || t.input_request || t.state === 'WAITING_RESOURCE'))
        .sort((a, b) => a.created_at - b.created_at).at(-1);
    if (!waiting) return null;
    if (waiting.approval) return { kind: 'approval', taskId: waiting.id, approval: waiting.approval };
    if (waiting.input_request) return { kind: 'question', taskId: waiting.id, request: waiting.input_request };
    return { kind: 'paused', taskId: waiting.id, note: waiting.error || 'Paused' };
}

/** What the work page shows of a task (decision 0034): its steps, what it waits for, and its state. */
export interface WorkView {
    taskId: string;
    steps: ActivityRow[];
    /** What Mei waits for from the person, in a line; null when nothing. */
    waiting: string | null;
    /** running: acting or thinking; paused: held (by the person, or while they use the computer); ended. */
    phase: 'running' | 'paused' | 'ended';
    /** The latest action that kept a picture, if any. */
    picture: string | null;
}

export function workView(conv: LoadedConversation, taskId: string): WorkView | null {
    const task = conv.tasks.get(taskId);
    if (!task) return null;
    // A step waiting on the person is said once, as what Mei waits for.
    const steps = (task.actions ?? []).filter(a => !isMeta(a))
        .sort((a, b) => a.created_at - b.created_at || a.position - b.position).map(activityRow)
        .filter(r => r.state !== 'waiting');
    const phase = TERMINAL_STATES.has(task.state) ? 'ended' : task.state === 'WAITING_RESOURCE' ? 'paused' : 'running';
    let waiting: string | null = null;
    if (phase !== 'ended') {
        if (task.approval) waiting = `Your answer: ${task.approval.card.title}`;
        else if (task.input_request) waiting = `Your answer: ${task.input_request.spec.question}`;
        else if (phase === 'paused') waiting = task.error || 'Paused';
    }
    return { taskId, steps, waiting, phase, picture: latestPicture(task) };
}

/** The task this conversation is working on now, the one the work page opens on. */
export function workingTask(conv: LoadedConversation): string | null {
    return [...conv.tasks.values()].filter(t => !TERMINAL_STATES.has(t.state))
        .sort((a, b) => a.created_at - b.created_at).at(-1)?.id ?? null;
}

function latestPicture(task: TaskView): string | null {
    const pictured = (task.actions ?? []).filter(a => (a.pictures ?? 0) > 0)
        .sort((a, b) => (a.finished_at ?? a.created_at) - (b.finished_at ?? b.created_at));
    return pictured.at(-1)?.id ?? null;
}

export function activityRow(action: ActionView): ActivityRow {
    const row = (state: ActivityState, detail?: string): ActivityRow =>
        ({ id: action.id, text: state === 'done' ? action.summary || action.description : action.description || action.tool,
            state, detail });
    switch (action.execution) {
    case 'SUCCEEDED':
        return action.verification === 'failed' ? row('done', "Mei checked: it didn't take effect") : row('done');
    case 'STARTED':
        return row('running');
    case 'AWAITING_APPROVAL':
        return row('waiting', 'Waiting for your answer');
    case 'FAILED':
        return row('failed', action.error ?? undefined);
    case 'DENIED':
        return row('refused', 'You declined');
    case 'POLICY_DENIED':
        return row('refused', "Mei's safety rules don't allow this");
    case 'REJECTED':
        return row('refused', action.error ?? undefined);
    case 'IN_DOUBT':
    case 'ABANDONED':
        return row('unclear', 'Mei restarted while doing this');
    case 'CANCELLED':
        return row('skipped', 'Stopped');
    case 'SKIPPED':
    case 'SUPERSEDED':
    case 'EXPIRED':
        return row('skipped');
    default:
        return row('running'); // proposed or authorized: about to run
    }
}

export interface OutcomeLine {
    /** checked: everything Mei checked passed; problem: something didn't work or is still open;
     * unchecked: Mei couldn't check (some of) it. */
    tone: 'checked' | 'problem' | 'unchecked';
    text: string;
}

/** How a task ended, in one line under the reply. It claims only what Mei's own checks established
 * (§8.5): "Checked" lists only criteria whose check passed. */
export function outcomeLine(outcome: Outcome): OutcomeLine {
    const named = (status: string) => outcome.criteria.filter(c => c.status === status);
    const passed = named('passed').map(c => c.text);
    const failed = named('failed').map(c => (c.detail ? `${c.text} (${c.detail})` : c.text));
    const unverifiable = named('unverifiable').map(c => c.text);
    const reported = named('reported').map(c => c.text);
    const parts: string[] = [];
    if (passed.length) parts.push(`Checked: ${passed.join(' · ')}`);
    if (failed.length) parts.push(`Didn’t work: ${failed.join(' · ')}`);
    if (unverifiable.length) parts.push(`Couldn’t check: ${unverifiable.join(' · ')}`);
    if (reported.length) parts.push(`Not checked: ${reported.join(' · ')}`);
    if (outcome.open_issues.length) parts.push(`Still open: ${outcome.open_issues.join(' · ')}`);
    if (!parts.length) parts.push(outcome.kind === 'outcome_verified' ? 'Checked' : outcome.note ? `Not checked by Mei: ${outcome.note}` : 'Not checked by Mei');
    const tone = failed.length || outcome.open_issues.length ? 'problem'
        : outcome.kind === 'outcome_verified' ? 'checked' : 'unchecked';
    return { tone, text: parts.join('. ') };
}

function isMeta(action: ActionView): boolean {
    return META.has(action.capability ?? action.tool);
}
