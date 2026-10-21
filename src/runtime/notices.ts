/**
 * Background tasks (§18.2, §18.4): what to do when a task finishes or needs the person, and what
 * its notification says. Pure, so it is tested without the Shell.
 *
 * A quick answer to a question just asked pops the popup back open, as it always has. Anything
 * else (a task that ran a while, or one in a conversation the popup isn't showing) arrives as a
 * notification instead: opening a menu in the middle of someone's work would take their keyboard.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import {
    TERMINAL_STATES,
    type ApprovalView,
    type ConversationSummary,
    type Envelope,
    type InputRequestView,
    type Outcome,
    type TaskState,
} from './protocol.js';

/** A task that has run at least this long finishes with a notification, not by opening the popup. */
export const QUICK_MS = 20_000;
const MAX_BODY = 240;

/** Where the person is: the popup's state, and how long the event's task has been running. */
export interface Seen {
    /** The popup is open on this conversation's chat (not the history list or another chat). */
    showing: boolean;
    /** This is the popup's current conversation (it may be closed). */
    current: boolean;
    /** How long the task has run, if known. */
    elapsedMs: number | null;
}

export type Reaction = 'none' | 'open' | 'notify';

export interface Notice {
    conversationId: string;
    title: string;
    body: string;
    /** Approvals and questions: the notification offers "Review" (they aren't answered from it, §18.2). */
    review: boolean;
}

const FINISHED: Partial<Record<TaskState, string>> = {
    COMPLETED: 'Mei finished',
    FAILED: 'Mei couldn’t finish',
    BLOCKED: 'Mei got stuck',
};

/** Whether this event is one the person should hear about wherever they are. */
export function wantsPerson(event: Envelope): boolean {
    if (event.type === 'task.finished') return (event.payload.state as TaskState) in FINISHED;
    return event.type === 'approval.requested' || event.type === 'input.requested';
}

export function reaction(event: Envelope, seen: Seen): Reaction {
    if (!wantsPerson(event) || seen.showing) return 'none';
    const quick = seen.elapsedMs !== null && seen.elapsedMs < QUICK_MS;
    return seen.current && quick ? 'open' : 'notify';
}

export function noticeFor(event: Envelope, conversation: ConversationSummary | undefined): Notice | null {
    if (!wantsPerson(event) || !event.conversation_id) return null;
    const p = event.payload;
    const chat = conversation?.title || 'Mei';
    let title: string;
    let detail = '';
    if (event.type === 'task.finished') {
        title = FINISHED[p.state as TaskState] ?? 'Mei';
        detail = (p.outcome as Outcome | null | undefined)?.summary || (p.error as string | null) || '';
    } else if (event.type === 'approval.requested') {
        title = 'Mei needs your OK';
        detail = (p.approval as ApprovalView | undefined)?.card.title ?? '';
    } else {
        title = 'Mei has a question';
        detail = (p.request as InputRequestView | undefined)?.spec.question ?? '';
    }
    return {
        conversationId: event.conversation_id,
        title,
        body: clip(detail ? `${chat}\n${detail}` : chat),
        review: event.type !== 'task.finished',
    };
}

/** What the history list says about a conversation's task in progress, if it has one. */
export function activeLabel(state: TaskState | null | undefined): string | null {
    if (!state || TERMINAL_STATES.has(state)) return null;
    if (state === 'WAITING_APPROVAL' || state === 'WAITING_INPUT') return 'Needs you';
    if (state === 'INTERRUPTED') return 'Interrupted';
    if (state === 'CANCEL_REQUESTED') return 'Stopping…';
    return 'Working…';
}

function clip(text: string): string {
    return text.length > MAX_BODY ? `${text.slice(0, MAX_BODY - 1).trimEnd()}…` : text;
}
