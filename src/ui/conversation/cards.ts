/**
 * What the conversation shows besides messages (§12.5, §18.2): a task's steps while it runs, what Mei
 * remembered, and, behind a reply's icons, its steps and how the task was checked. A closed set of St
 * widgets: no HTML, no model-chosen styling. Text from the model and from files is plain text. Marks
 * are the system's symbolic icons, in the text's own color. A card that waits on the person (an
 * approval, a question) isn't here: it takes over the input area (interaction.ts).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import type { ApprovalScope, MemoryView, Outcome } from '../../runtime/protocol.js';
import { outcomeLine, type ActivityRow, type ActivityState, type ReplyDetails } from '../../runtime/timeline.js';
import { addClickScale, wrapLabel } from '../effects.js';

export type Answer = string | Record<string, string | boolean>;

export interface CardActions {
    onApprove(approvalId: string, scope: ApprovalScope): void;
    onDeny(approvalId: string): void;
    /** Decline, and tell Mei what to do instead. */
    onDenyWith(approvalId: string, text: string): void;
    onAnswer(requestId: string, value: Answer): void;
    /** A paused task: go on now. */
    onResume(taskId: string): void;
    /** A paused task: stop it. */
    onStopTask(taskId: string): void;
    /** Make a memory waiting for review active. */
    onKeepMemory(memoryId: string): void;
    /** Undo a memory just saved, or discard one waiting for review. */
    onForgetMemory(memoryId: string): void;
}

export const DONE = 'object-select-symbolic';
const PENDING = 'radio-symbolic';
const ACTIVITY_MARK: Record<ActivityState, string> = {
    done: DONE, running: 'content-loading-symbolic', waiting: 'dialog-question-symbolic', failed: 'window-close-symbolic',
    refused: 'action-unavailable-symbolic', skipped: 'list-remove-symbolic', unclear: 'dialog-warning-symbolic',
};
const CRITERION_MARK: Record<string, string> = {
    pending: PENDING, passed: DONE, failed: 'window-close-symbolic', unverifiable: 'dialog-question-symbolic', reported: PENDING,
};
const CRITERION_STATUS: Record<string, string> = {
    passed: 'checked', failed: 'didn’t work', unverifiable: 'couldn’t be checked', reported: 'not checked',
};

/** A task's steps; `top`: what goes above them (the latest picture of the screen, decision 0029). */
export function activityBlock(rows: ActivityRow[], top?: St.Widget): St.BoxLayout {
    const box = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-activity' });
    if (top) box.add_child(top);
    for (const row of rows) {
        const line = new St.BoxLayout({ x_expand: true, style_class: `mei-activity-row ${row.state}` });
        line.add_child(mark(ACTIVITY_MARK[row.state]));
        const text = new St.BoxLayout({ vertical: true, x_expand: true });
        text.add_child(wrapLabel(new St.Label({ text: row.text, x_expand: true, style_class: 'mei-activity-text' })));
        if (row.detail) text.add_child(muted(row.detail));
        line.add_child(text);
        box.add_child(line);
    }
    return box;
}

/** Behind a reply's Steps icon: what Mei said on the way, then what it did. */
export function stepsPanel(details: ReplyDetails): St.BoxLayout {
    const panel = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-detail-panel' });
    for (const note of details.notes) panel.add_child(wrapLabel(new St.Label({ text: note, style_class: 'mei-detail-note' })));
    if (details.steps.length) panel.add_child(activityBlock(details.steps));
    return panel;
}

/** Behind a reply's Checks icon: how Mei checked the task, criterion by criterion (§8.5). */
export function checksPanel(outcome: Outcome): St.BoxLayout {
    const panel = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-detail-panel' });
    const { tone } = outcomeLine(outcome);
    panel.add_child(new St.Label({ style_class: 'mei-detail-title',
        text: tone === 'checked' ? 'Checked by Mei' : tone === 'problem' ? 'Something didn’t work' : 'Not all checked by Mei' }));
    for (const c of outcome.criteria) {
        const status = CRITERION_STATUS[c.status] ?? c.status;
        markedLine(panel, CRITERION_MARK[c.status] ?? PENDING, c.text, c.detail ? `${status}: ${c.detail}` : status);
    }
    for (const issue of outcome.open_issues) markedLine(panel, 'dialog-warning-symbolic', issue, 'still open');
    if (!outcome.criteria.length && outcome.note) panel.add_child(muted(`Mei couldn’t check this: ${outcome.note}`));
    else if (!outcome.criteria.length) panel.add_child(muted('There was nothing Mei could check.'));
    return panel;
}

/**
 * A memory saved in this task (§17.4): "Remembered … Undo", one quiet line. One that came from
 * something Mei read, or that automatic saving didn't keep, waits for the person: "Keep this? … Keep
 * / Discard".
 */
export function memoryCard(memory: MemoryView, actions: CardActions): St.BoxLayout {
    const pending = memory.status === 'pending_review';
    const card = new St.BoxLayout({ vertical: true, x_expand: true, style_class: `mei-memory-line${pending ? ' pending' : ''}` });
    const line = new St.BoxLayout({ x_expand: true, style_class: 'mei-memory-row' });
    line.add_child(new St.Label({ text: pending ? 'Keep this in memory?' : 'Remembered', style_class: 'mei-memory-title',
        y_align: Clutter.ActorAlign.START }));
    line.add_child(wrapLabel(new St.Label({ text: memory.text, x_expand: true, style_class: 'mei-memory-text' })));
    card.add_child(line);
    if (pending && memory.provenance === 'untrusted')
        card.add_child(muted('This may have come from something Mei read, not from you.'));
    const row = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-buttons' });
    const buttons: St.Button[] = [];
    const once = (fn: () => void) => () => {
        buttons.forEach(b => b.set_reactive(false));
        fn();
    };
    if (pending) {
        const keep = cardButton('Keep', 'Keep this memory', 'suggested');
        keep.connect('clicked', once(() => actions.onKeepMemory(memory.id)));
        buttons.push(keep);
    }
    const forget = cardButton(pending ? 'Discard' : 'Undo', pending ? 'Discard this memory' : 'Forget this memory');
    forget.connect('clicked', once(() => actions.onForgetMemory(memory.id)));
    buttons.push(forget);
    buttons.forEach(b => row.add_child(b));
    if (pending) card.add_child(row);
    else line.add_child(row);
    return card;
}

export function muted(text: string): St.Label {
    return wrapLabel(new St.Label({ text, style_class: 'mei-card-muted' }));
}

export function cardButton(label: string, accessibleName: string, extra = ''): St.Button {
    const button = new St.Button({ label, style_class: `mei-card-btn ${extra}`.trim(), can_focus: true, reactive: true,
        track_hover: true, accessible_name: accessibleName, accessible_role: Atk.Role.PUSH_BUTTON });
    addClickScale(button);
    return button;
}

function markedLine(box: St.BoxLayout, icon: string, text: string, detail: string): void {
    const line = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-line' });
    line.add_child(mark(icon));
    const words = new St.BoxLayout({ vertical: true, x_expand: true });
    words.add_child(wrapLabel(new St.Label({ text, x_expand: true, style_class: 'mei-card-text' })));
    words.add_child(muted(detail));
    line.add_child(words);
    box.add_child(line);
}

function mark(icon: string): St.Icon {
    return new St.Icon({ icon_name: icon, style_class: 'mei-mark', y_align: Clutter.ActorAlign.START });
}
