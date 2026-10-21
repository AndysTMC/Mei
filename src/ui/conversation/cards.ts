/**
 * The agent's cards in the conversation (§12.5, §13.3): what Mei did, its plan, an approval it
 * needs, a question for the person, and the outcome. A closed set of St widgets: no HTML, no
 * model-chosen styling. Text from the model and from files is shown as plain text.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import type {
    ApprovalScope, ApprovalView, FormField, InputRequestView, MemoryView, Outcome, Plan, Provenance,
} from '../../runtime/protocol.js';
import { outcomeBadge, type ActivityRow, type ActivityState } from '../../runtime/timeline.js';
import { addClickScale, wrapLabel } from '../effects.js';

export type Answer = string | Record<string, string | boolean>;

export interface CardActions {
    onApprove(approvalId: string, scope: ApprovalScope): void;
    onDeny(approvalId: string): void;
    onAnswer(requestId: string, value: Answer): void;
    /** Make a memory waiting for review active. */
    onKeepMemory(memoryId: string): void;
    /** Undo a memory just saved, or discard one waiting for review. */
    onForgetMemory(memoryId: string): void;
}

const ACTIVITY_MARK: Record<ActivityState, string> = {
    done: '✓', running: '…', waiting: '?', failed: '✗', refused: '⊘', skipped: '–', unclear: '!',
};
const STEP_MARK: Record<string, string> = { pending: '○', in_progress: '◐', done: '✓', skipped: '–' };
const CRITERION_MARK: Record<string, string> = { pending: '○', passed: '✓', failed: '✗', unverifiable: '?', reported: '•' };
const PROVENANCE: Record<Provenance, string> = {
    user: 'you named this', untrusted: 'suggested by a file or page', model: 'Mei chose this',
};
const SCOPE_LABEL: Record<ApprovalScope, string> = { once: 'Allow once', task: 'For this task', always: 'Always' };

export function activityBlock(rows: ActivityRow[]): St.BoxLayout {
    const box = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-activity' });
    for (const row of rows) {
        const line = new St.BoxLayout({ x_expand: true, style_class: `mei-activity-row ${row.state}` });
        line.add_child(new St.Label({ text: ACTIVITY_MARK[row.state], style_class: 'mei-activity-mark' }));
        const text = new St.BoxLayout({ vertical: true, x_expand: true });
        text.add_child(wrapLabel(new St.Label({ text: row.text, x_expand: true, style_class: 'mei-activity-text' })));
        if (row.detail) text.add_child(wrapLabel(new St.Label({ text: row.detail, style_class: 'mei-card-muted' })));
        line.add_child(text);
        box.add_child(line);
    }
    return box;
}

export function planCard(plan: Plan): St.BoxLayout {
    const card = cardBox('mei-plan-card');
    if (plan.steps?.length) {
        card.add_child(title('Plan'));
        for (const step of plan.steps) card.add_child(markedLine(STEP_MARK[step.status] ?? '○', step.text));
    }
    if (plan.criteria?.length) {
        card.add_child(title('Done when'));
        for (const c of plan.criteria) {
            const checked = c.check ? '' : ' (Mei can’t check this)';
            card.add_child(markedLine(CRITERION_MARK[c.status] ?? '○', `${c.text}${checked}`));
        }
    }
    return card;
}

export function outcomeCard(outcome: Outcome): St.BoxLayout {
    const badge = outcomeBadge(outcome);
    const card = cardBox(`mei-outcome-card ${badge.tone}`);
    card.add_child(title(badge.title));
    for (const line of badge.lines) card.add_child(wrapLabel(new St.Label({ text: line, style_class: 'mei-card-text' })));
    return card;
}

export function approvalCard(approval: ApprovalView, actions: CardActions): St.BoxLayout {
    const c = approval.card;
    const card = cardBox('mei-approval-card');
    card.accessible_role = Atk.Role.DIALOG;
    card.add_child(title(`Mei wants to: ${c.title}`));
    if (c.reason_text) card.add_child(muted(`Asking because ${c.reason_text}.`));
    if (c.resources.length) {
        for (const r of c.resources) {
            const label = r.role && r.role !== 'path' ? `${r.role}: ${r.value}` : r.value;
            card.add_child(markedLine('•', `${label} — ${PROVENANCE[r.provenance] ?? r.provenance}`));
        }
    }
    for (const effect of c.effects) card.add_child(markedLine('→', effect));
    if (c.why?.trim()) card.add_child(muted(`Mei's reason (from the model): “${c.why.trim()}”`));
    if (c.read_from?.length) card.add_child(muted(`Proposed after reading ${c.read_from.join(', ')}`));

    const row = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-buttons' });
    const buttons: St.Button[] = [];
    const settle = () => buttons.forEach(b => (b.reactive = false));
    for (const scope of c.scopes) {
        const button = cardButton(SCOPE_LABEL[scope], c.scope_text[scope] ?? SCOPE_LABEL[scope],
            scope === c.default_scope ? 'suggested' : '');
        button.connect('clicked', () => {
            settle();
            actions.onApprove(approval.id, scope);
        });
        buttons.push(button);
    }
    const deny = cardButton('Deny', 'Deny this action', 'deny');
    deny.connect('clicked', () => {
        settle();
        actions.onDeny(approval.id);
    });
    buttons.push(deny);
    buttons.forEach(b => row.add_child(b));
    card.add_child(row);
    const scoped = c.scopes.filter(s => s !== 'once').map(s => c.scope_text[s]).filter(Boolean);
    if (scoped.length) card.add_child(muted(scoped.join('. ')));
    return card;
}

export function questionCard(request: InputRequestView, actions: CardActions): St.BoxLayout {
    const card = cardBox('mei-question-card');
    card.accessible_role = Atk.Role.DIALOG;
    card.add_child(title(request.spec.question));
    const sent = { done: false };
    const answer = (value: Answer) => {
        if (sent.done) return;
        sent.done = true;
        actions.onAnswer(request.id, value);
    };
    if (request.spec.fields.length) {
        const read = request.spec.fields.map(field => formField(card, field));
        const send = cardButton('Send', 'Send the answers', 'suggested');
        send.connect('clicked', () => answer(Object.fromEntries(read.map(r => r()))));
        card.add_child(send);
    } else if (request.spec.choices.length) {
        const row = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-buttons' });
        for (const choice of request.spec.choices) {
            const button = cardButton(choice, choice);
            button.connect('clicked', () => answer(choice));
            row.add_child(button);
        }
        card.add_child(row);
    } else {
        const entry = new St.Entry({ hint_text: 'Your answer…', can_focus: true, x_expand: true, style_class: 'mei-card-entry' });
        entry.clutter_text.connect('activate', () => {
            const text = entry.get_text().trim();
            if (text) answer(text);
        });
        card.add_child(entry);
    }
    return card;
}

/**
 * A memory saved in this task (§17.4): "Remembered … Undo". One that came from something Mei read,
 * or that automatic saving didn't keep, waits for the person: "Keep this? … Keep / Discard".
 */
export function memoryCard(memory: MemoryView, actions: CardActions): St.BoxLayout {
    const pending = memory.status === 'pending_review';
    const card = cardBox(`mei-memory-card${pending ? ' pending' : ''}`);
    card.add_child(title(pending ? 'Keep this in memory?' : 'Remembered'));
    card.add_child(wrapLabel(new St.Label({ text: memory.text, style_class: 'mei-card-text' })));
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
    card.add_child(row);
    return card;
}

/** Adds the field's widgets to `card`; returns how to read its value. */
function formField(card: St.BoxLayout, field: FormField): () => [string, string | boolean] {
    card.add_child(new St.Label({ text: field.label, style_class: 'mei-card-muted' }));
    if (field.kind === 'checkbox') {
        const toggle = new St.Button({ label: '☐ No', toggle_mode: true, style_class: 'mei-card-btn', can_focus: true,
            accessible_name: field.label, x_align: Clutter.ActorAlign.START });
        toggle.connect('notify::checked', () => toggle.set_label(toggle.checked ? '☑ Yes' : '☐ No'));
        card.add_child(toggle);
        return () => [field.name, toggle.checked];
    }
    if (field.kind === 'select' && field.options?.length) {
        let chosen = field.options[0];
        const row = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-buttons' });
        const buttons = field.options.map(option => {
            const b = new St.Button({ label: option, toggle_mode: true, checked: option === chosen,
                style_class: 'mei-card-btn', can_focus: true, accessible_name: `${field.label}: ${option}` });
            b.connect('clicked', () => {
                chosen = option;
                buttons.forEach(other => other.set_checked(other === b));
            });
            row.add_child(b);
            return b;
        });
        card.add_child(row);
        return () => [field.name, chosen];
    }
    const entry = new St.Entry({ hint_text: field.kind === 'date' ? 'YYYY-MM-DD' : '', can_focus: true, x_expand: true,
        style_class: 'mei-card-entry', accessible_name: field.label });
    card.add_child(entry);
    return () => [field.name, entry.get_text().trim()];
}

function cardBox(styleClass: string): St.BoxLayout {
    return new St.BoxLayout({ vertical: true, x_expand: true, style_class: `mei-card ${styleClass}` });
}

function title(text: string): St.Label {
    return wrapLabel(new St.Label({ text, style_class: 'mei-card-title' }));
}

function muted(text: string): St.Label {
    return wrapLabel(new St.Label({ text, style_class: 'mei-card-muted' }));
}

function markedLine(mark: string, text: string): St.BoxLayout {
    const line = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-line' });
    line.add_child(new St.Label({ text: mark, style_class: 'mei-activity-mark' }));
    line.add_child(wrapLabel(new St.Label({ text, x_expand: true, style_class: 'mei-card-text' })));
    return line;
}

function cardButton(label: string, accessibleName: string, extra = ''): St.Button {
    const button = new St.Button({ label, style_class: `mei-card-btn ${extra}`.trim(), can_focus: true, reactive: true,
        track_hover: true, accessible_name: accessibleName, accessible_role: Atk.Role.PUSH_BUTTON });
    addClickScale(button);
    return button;
}
