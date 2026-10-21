/**
 * What a conversation shows, in order (§18.2): each task's request, its plan in the header, the
 * replies with the actions they took under them, any card waiting on the person, and the outcome
 * badge. Pure: built from the projection, rendered by ui/conversation; no GJS here.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ActionView, ApprovalView, InputRequestView, MessageView, Outcome, Plan, TaskView } from './protocol.js';
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

export type TimelineItem =
    | { kind: 'message'; message: MessageView; draft?: boolean }
    | { kind: 'activity'; taskId: string; rows: ActivityRow[] }
    | { kind: 'plan'; taskId: string; plan: Plan }
    | { kind: 'approval'; taskId: string; approval: ApprovalView }
    | { kind: 'question'; taskId: string; request: InputRequestView }
    | { kind: 'outcome'; taskId: string; outcome: Outcome };

export function buildTimeline(conv: LoadedConversation): TimelineItem[] {
    const tasks = [...conv.tasks.values()];
    const byInput = new Map(tasks.map(t => [t.input_message_id, t]));
    const actionsByMessage = new Map<string, ActionView[]>();
    for (const task of tasks) {
        for (const action of task.actions ?? []) {
            if (isMeta(action)) continue;
            const list = actionsByMessage.get(action.message_id) ?? [];
            list.push(action);
            actionsByMessage.set(action.message_id, list);
        }
    }
    const items: TimelineItem[] = [];
    const ended = new Set<string>();
    const close = (task: TaskView | undefined): void => {
        if (!task || ended.has(task.id)) return;
        ended.add(task.id);
        if (task.approval) items.push({ kind: 'approval', taskId: task.id, approval: task.approval });
        if (task.input_request) items.push({ kind: 'question', taskId: task.id, request: task.input_request });
        if (task.outcome) items.push({ kind: 'outcome', taskId: task.id, outcome: task.outcome });
    };
    let current: TaskView | undefined;
    for (const message of conv.messages) {
        const starts = byInput.get(message.id);
        if (starts) {
            close(current);
            current = starts;
        }
        const actions = actionsByMessage.get(message.id) ?? [];
        if (message.content.trim() || message.role === 'user') items.push({ kind: 'message', message });
        if (starts && hasPlan(starts.plan)) items.push({ kind: 'plan', taskId: starts.id, plan: starts.plan! });
        if (actions.length) {
            actions.sort((a, b) => a.created_at - b.created_at || a.position - b.position);
            items.push({ kind: 'activity', taskId: actions[0].task_id, rows: actions.map(activityRow) });
        }
    }
    close(current);
    for (const task of tasks) close(task); // a task whose input isn't loaded (shouldn't happen) still shows its card
    return items;
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

export interface OutcomeBadge {
    tone: 'verified' | 'partial' | 'reported';
    title: string;
    lines: string[];
}

/** The outcome in words; it claims only what Mei's own checks established (§8.5). */
export function outcomeBadge(outcome: Outcome): OutcomeBadge {
    const marks: Record<string, string> = { passed: '✓', failed: '✗', unverifiable: '?', reported: '•' };
    const lines = outcome.criteria.map(c => `${marks[c.status] ?? '•'} ${c.text}${c.status === 'failed' && c.detail ? ` (${c.detail})` : ''}`);
    for (const issue of outcome.open_issues) lines.push(`Open: ${issue}`);
    if (outcome.kind === 'outcome_verified') return { tone: 'verified', title: 'Verified by Mei', lines };
    if (outcome.kind === 'partially_verified') return { tone: 'partial', title: 'Partly verified', lines };
    const title = outcome.note ? `Reported, not checked: ${outcome.note}` : 'Reported, not checked';
    return { tone: 'reported', title, lines };
}

function isMeta(action: ActionView): boolean {
    return META.has(action.capability ?? action.tool);
}

function hasPlan(plan: Plan | undefined): boolean {
    return Boolean(plan && ((plan.steps?.length ?? 0) > 0 || (plan.criteria?.length ?? 0) > 0));
}
