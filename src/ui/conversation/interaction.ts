/**
 * What Mei waits on the person for, in place of the input area (§13.3, §8.6): an approval, or a
 * question. While it shows, the message box and Ask are hidden: this is the input.
 *
 *   Approval:  "Mei wants to" · the action · why it asks · Details  →  its choices (Allow once, For
 *              this task, Always, Deny), and "Or tell Mei what to do instead…" (declines, then says it).
 *   Question:  the question  →  its choices and "Something else…" for any other answer, or its form
 *              and Send, or only an answer box. A hand-off (a password field Mei won't type into) takes
 *              only its choices.
 *   Paused:    why (the person is using the computer)  →  Resume, Stop. It goes on by itself too.
 *
 * The same in the small and the large popup. Text from the model and from files is plain text.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import type { ApprovalScope, ApprovalView, FormField, InputRequestView, Provenance } from '../../runtime/protocol.js';
import type { Interaction } from '../../runtime/timeline.js';
import { wrapLabel } from '../effects.js';
import { cardButton, muted, type CardActions } from './cards.js';

const SCOPE_LABEL: Record<ApprovalScope, string> = { once: 'Allow once', task: 'For this task', always: 'Always' };
const PROVENANCE: Record<Provenance, string> = {
    user: 'you named this', untrusted: 'suggested by a file or page', model: 'Mei chose this',
};

export class InteractionPanel {
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true, visible: false, style_class: 'mei-interaction',
        accessible_role: Atk.Role.DIALOG });
    private _shown = ''; // which approval or question, so redrawing the same one keeps what was typed
    private _entry: St.Entry | null = null;
    private _controls: St.Widget[] = [];

    constructor(private readonly _actions: CardActions) {}

    /** Show what Mei waits for, or nothing. True if something shows (the input area then hides). */
    show(interaction: Interaction | null): boolean {
        const key = !interaction ? '' : interaction.kind === 'approval' ? `a:${interaction.approval.id}`
            : interaction.kind === 'question' ? `q:${interaction.request.id}` : `p:${interaction.taskId}:${interaction.note}`;
        if (key === this._shown) return interaction !== null;
        this._shown = key;
        this.actor.destroy_all_children();
        this._entry = null;
        this._controls = [];
        this.actor.visible = interaction !== null;
        if (interaction?.kind === 'approval') this._approval(interaction.approval);
        else if (interaction?.kind === 'question') this._question(interaction.request);
        else if (interaction?.kind === 'paused') this._paused(interaction.taskId, interaction.note);
        return interaction !== null;
    }

    focus(): void {
        this._entry?.grab_key_focus();
    }

    /** The answer didn't reach Mei: let the person try again. */
    retry(): void {
        for (const control of this._controls) control.reactive = true;
    }

    private _approval(approval: ApprovalView): void {
        const c = approval.card;
        this.actor.add_child(new St.Label({ text: 'Mei wants to', style_class: 'mei-interaction-kicker' }));
        this.actor.add_child(wrapLabel(new St.Label({ text: c.title, style_class: 'mei-interaction-title' })));
        if (c.reason_text) this.actor.add_child(muted(`Asking because ${c.reason_text}.`));
        this._details(approval);

        const row = this._row();
        for (const scope of c.scopes) {
            const button = this._button(SCOPE_LABEL[scope], c.scope_text[scope] ?? SCOPE_LABEL[scope],
                scope === c.default_scope ? 'suggested' : '');
            button.connect('clicked', () => this._settle(() => this._actions.onApprove(approval.id, scope)));
            row.add_child(button);
        }
        const deny = this._button('Deny', 'Deny this action');
        deny.connect('clicked', () => this._settle(() => this._actions.onDeny(approval.id)));
        row.add_child(deny);
        this._customEntry('Or tell Mei what to do instead…', text => this._actions.onDenyWith(approval.id, text));
    }

    /** What it touches, its effects, and the model's reason: on demand, under "Details". */
    private _details(approval: ApprovalView): void {
        const c = approval.card;
        const box = new St.BoxLayout({ vertical: true, x_expand: true, visible: false, style_class: 'mei-interaction-details' });
        for (const r of c.resources) {
            const label = r.role && r.role !== 'path' ? `${r.role}: ${r.value}` : r.value;
            box.add_child(wrapLabel(new St.Label({ text: label, style_class: 'mei-card-text' })));
            box.add_child(muted(PROVENANCE[r.provenance] ?? r.provenance));
        }
        for (const effect of c.effects) box.add_child(wrapLabel(new St.Label({ text: effect, style_class: 'mei-card-text' })));
        if (c.why?.trim()) box.add_child(muted(`Mei's reason (from the model): “${c.why.trim()}”`));
        if (c.read_from?.length) box.add_child(muted(`Proposed after reading ${c.read_from.join(', ')}`));
        const scoped = c.scopes.filter(s => s !== 'once').map(s => c.scope_text[s]).filter(Boolean);
        if (scoped.length) box.add_child(muted(scoped.join('. ')));
        if (!box.get_n_children()) return;
        const toggle = new St.Button({ label: 'Details', style_class: 'mei-details-toggle', can_focus: true,
            track_hover: true, x_align: Clutter.ActorAlign.START, accessible_name: 'Show details' });
        toggle.connect('clicked', () => {
            box.visible = !box.visible;
            toggle.set_label(box.visible ? 'Hide details' : 'Details');
        });
        this.actor.add_child(toggle);
        this.actor.add_child(box);
    }

    private _question(request: InputRequestView): void {
        const { question, choices, fields } = request.spec;
        this.actor.add_child(wrapLabel(new St.Label({ text: question, style_class: 'mei-interaction-title' })));
        if (fields.length) {
            const read = fields.map(field => this._field(field));
            const send = this._button('Send', 'Send the answers', 'suggested');
            send.connect('clicked', () => this._settle(() => this._actions.onAnswer(request.id, Object.fromEntries(read.map(r => r())))));
            this._row().add_child(send);
            return;
        }
        if (choices.length) {
            const row = this._row();
            for (const choice of choices) {
                const button = this._button(choice, choice);
                button.connect('clicked', () => this._settle(() => this._actions.onAnswer(request.id, choice)));
                row.add_child(button);
            }
        }
        if (request.kind === 'handoff') return; // only the person can do it: done, or not
        this._customEntry(choices.length ? 'Something else…' : 'Your answer…', text => this._actions.onAnswer(request.id, text));
    }

    private _paused(taskId: string, note: string): void {
        this.actor.add_child(wrapLabel(new St.Label({ text: note, style_class: 'mei-interaction-title' })));
        // Paused by the person (the work page's Pause) or while they used the computer.
        this.actor.add_child(muted(note === 'Paused by you' ? 'Mei waits until you say go on.' : 'Mei goes on when you stop.'));
        const row = this._row();
        const resume = this._button('Resume', 'Go on now', 'suggested');
        resume.connect('clicked', () => this._settle(() => this._actions.onResume(taskId)));
        const stop = this._button('Stop', 'Stop this task');
        stop.connect('clicked', () => this._settle(() => this._actions.onStopTask(taskId)));
        row.add_child(resume);
        row.add_child(stop);
    }

    /** A field of a form; returns how to read its value. */
    private _field(field: FormField): () => [string, string | boolean] {
        this.actor.add_child(muted(field.label));
        if (field.kind === 'checkbox') {
            const toggle = new St.Button({ label: 'No', toggle_mode: true, style_class: 'mei-card-btn', can_focus: true,
                accessible_name: field.label, x_align: Clutter.ActorAlign.START });
            toggle.connect('notify::checked', () => toggle.set_label(toggle.checked ? 'Yes' : 'No'));
            this._controls.push(toggle);
            this.actor.add_child(toggle);
            return () => [field.name, toggle.checked];
        }
        if (field.kind === 'select' && field.options?.length) {
            let chosen = field.options[0];
            const row = this._row();
            const buttons = field.options.map(option => {
                const b = new St.Button({ label: option, toggle_mode: true, checked: option === chosen,
                    style_class: 'mei-card-btn', can_focus: true, accessible_name: `${field.label}: ${option}` });
                b.connect('clicked', () => {
                    chosen = option;
                    buttons.forEach(other => other.set_checked(other === b));
                });
                this._controls.push(b);
                row.add_child(b);
                return b;
            });
            return () => [field.name, chosen];
        }
        const entry = new St.Entry({ hint_text: field.kind === 'date' ? 'YYYY-MM-DD' : '', can_focus: true, x_expand: true,
            style_class: 'mei-interaction-entry', accessible_name: field.label });
        this._controls.push(entry);
        this.actor.add_child(entry);
        return () => [field.name, entry.get_text().trim()];
    }

    /** One line for any other answer; Enter sends it. */
    private _customEntry(hint: string, send: (text: string) => void): void {
        const entry = new St.Entry({ hint_text: hint, can_focus: true, x_expand: true, style_class: 'mei-interaction-entry',
            accessible_name: hint.replace('…', '') });
        entry.clutter_text.connect('activate', () => {
            const text = entry.get_text().trim();
            if (text) this._settle(() => send(text));
        });
        this._controls.push(entry);
        this._entry = entry;
        this.actor.add_child(entry);
    }

    private _row(): St.BoxLayout {
        const row = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-buttons' });
        this.actor.add_child(row);
        return row;
    }

    private _button(label: string, accessibleName: string, extra = ''): St.Button {
        const button = cardButton(label, accessibleName, extra);
        this._controls.push(button);
        return button;
    }

    /** Answered: nothing more can be pressed until the runtime moves on (it then hides this). */
    private _settle(answer: () => void): void {
        for (const control of this._controls) control.reactive = false;
        answer();
    }
}
