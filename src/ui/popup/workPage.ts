/**
 * "What Mei is doing" (decision 0029): the latest picture of the screen computer use took, large and
 * updated after each act; beside it the task's steps and what Mei waits for; under it Pause / Go on,
 * Stop (the kill switch's path) and Take over, which a later hidden session brings.
 *
 *   ┌───────────────────────────────┬──────────┐
 *   │ the picture                   │ Steps    │
 *   │                               │ Waiting  │
 *   ├───────────────────────────────┴──────────┤
 *   │ Pause · Stop · Take over                 │
 *   └──────────────────────────────────────────┘
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import type { Picture } from '../../runtime/protocol.js';
import type { WorkView } from '../../runtime/timeline.js';
import { activityBlock, cardButton, muted } from '../conversation/cards.js';
import { centeredNote, loadPicture, scrolling } from '../viewers/common.js';
import type { PageContent } from './largePage.js';
import type { Size } from './pageSize.js';

export interface WorkActions {
    onPause(taskId: string): void;
    onGoOn(taskId: string): void;
    /** The kill switch: stop Mei using the computer, and this task with it. */
    onStop(taskId: string): void;
}

/** The steps column's width, in CSS pixels. */
const COLUMN_WIDTH = 280;
/** Room under the picture for the buttons, in CSS pixels. */
const BUTTONS_HEIGHT = 52;

export class WorkPage implements PageContent {
    readonly title = 'What Mei is doing';
    readonly actions: St.Widget[] = [];
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true, y_expand: true, style_class: 'mei-work' });
    private readonly _picture = new St.Bin({ x_expand: true, y_expand: true, style_class: 'mei-work-picture' });
    private readonly _caption = new St.Label({ text: '', style_class: 'mei-card-muted mei-work-caption' });
    private readonly _steps = new St.BoxLayout({ vertical: true, x_expand: true });
    private readonly _waiting = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-work-waiting' });
    private readonly _pause: St.Button;
    private readonly _stop: St.Button;
    private readonly _pictureSize: Size;
    private _view: WorkView;
    private _shown: string | null = null;
    /** Pause was pressed and the task hasn't reached a point where it waits yet. */
    private _pausing = false;

    constructor(view: WorkView, body: Size, private readonly _actions: WorkActions) {
        this._view = view;
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        this._pictureSize = { width: Math.max(1, body.width - (COLUMN_WIDTH + 16) * scale),
            height: Math.max(1, body.height - (BUTTONS_HEIGHT + 24) * scale) };

        const main = new St.BoxLayout({ x_expand: true, y_expand: true, style_class: 'mei-work-main' });
        const left = new St.BoxLayout({ vertical: true, x_expand: true, y_expand: true });
        left.add_child(this._picture);
        left.add_child(this._caption);
        main.add_child(left);
        const column = new St.BoxLayout({ vertical: true, y_expand: true, style_class: 'mei-work-column', width: COLUMN_WIDTH * scale });
        column.add_child(new St.Label({ text: 'Steps', style_class: 'mei-work-heading' }));
        column.add_child(scrolling(this._steps));
        column.add_child(this._waiting);
        main.add_child(column);
        this.actor.add_child(main);

        const buttons = new St.BoxLayout({ x_expand: true, style_class: 'mei-card-buttons mei-work-buttons' });
        this._pause = cardButton('Pause', 'Pause Mei before its next step');
        this._pause.connect('clicked', () => {
            if (this._view.phase === 'paused') {
                this._actions.onGoOn(this._view.taskId);
            } else {
                this._pausing = true;
                this._actions.onPause(this._view.taskId);
            }
            this._sync();
        });
        this._stop = cardButton('Stop', 'Stop Mei using the computer');
        this._stop.connect('clicked', () => this._actions.onStop(this._view.taskId));
        const takeOver = cardButton('Take over', 'Take over (comes later)');
        takeOver.reactive = false;
        takeOver.can_focus = false;
        takeOver.add_style_class_name('insensitive');
        for (const b of [this._pause, this._stop, takeOver]) buttons.add_child(b);
        this.actor.add_child(buttons);

        this._picture.set_child(centeredNote('No picture of the screen yet'));
        this.update(view);
    }

    get taskId(): string {
        return this._view.taskId;
    }

    /** The action whose picture shows, if one does (for the controller and the dev hooks). */
    get shownPicture(): string | null {
        return this._shown;
    }

    get debugState(): Record<string, unknown> {
        return { taskId: this._view.taskId, phase: this._view.phase, picture: this._shown, steps: this._view.steps.length,
            pause: this._pause.label, waiting: this._view.waiting };
    }

    update(view: WorkView): void {
        this._view = view;
        if (view.phase !== 'running') this._pausing = false;
        this._steps.destroy_all_children();
        if (view.steps.length) this._steps.add_child(activityBlock(view.steps));
        else this._steps.add_child(muted('Nothing yet'));
        this._waiting.destroy_all_children();
        if (view.waiting) {
            this._waiting.add_child(new St.Label({ text: 'Waiting for', style_class: 'mei-work-heading' }));
            this._waiting.add_child(muted(view.waiting));
        }
        this._sync();
    }

    /** The picture as Mei last saw the screen. */
    showPicture(picture: Picture): void {
        if (picture.action_id === this._shown) return;
        this._shown = picture.action_id;
        const actor = loadPicture(picture.path, this._pictureSize, picture);
        actor.x_align = actor.y_align = Clutter.ActorAlign.CENTER;
        this._picture.set_child(actor);
        const when = picture.taken_at ? GLib.DateTime.new_from_unix_local(Math.floor(picture.taken_at / 1000)) : null;
        this._caption.text = when ? `As Mei saw the screen at ${when.format('%X')}` : '';
    }

    private _sync(): void {
        const ended = this._view.phase === 'ended';
        this._pause.label = this._view.phase === 'paused' ? 'Go on' : this._pausing ? 'Pausing…' : 'Pause';
        this._pause.accessible_name = this._view.phase === 'paused' ? 'Let Mei go on' : 'Pause Mei before its next step';
        this._pause.reactive = !ended && !this._pausing;
        this._stop.reactive = !ended;
        for (const b of [this._pause, this._stop]) {
            if (b.reactive) b.remove_style_class_name('insensitive');
            else b.add_style_class_name('insensitive');
        }
        if (ended) this._caption.text = this._shown ? 'Mei is done. This is the screen as it last saw it.' : 'Mei is done.';
    }

    destroy(): void {
        this.actor.destroy();
    }
}
