/**
 * The history view (expanded mode): Back, a title, and one row per saved chat, with chats whose
 * task is still in progress listed first under their own heading. Deleting asks for a second click
 * within a few seconds.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import { addClickScale, iconButton } from '../effects.js';
import type { SourceSet } from '../sources.js';

export interface ChatSummary {
    id: string;
    title: string;
    /** What its task in progress is doing ("Working…", "Needs you"), if it has one. */
    active?: string | null;
}

export interface HistoryActions {
    onBack(): void;
    onLoadChat(id: string): void;
    onDeleteChat(id: string): void;
}

const CONFIRM_DELETE_FOR_MS = 3000;

export class HistoryPanel {
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true, y_expand: true, visible: false });
    private readonly _backBtn: St.Button;
    private readonly _title: St.Label;
    private readonly _list = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-history-list' });
    private _isDark = true;

    constructor(private readonly _sources: SourceSet, maxHeight: number, private readonly _actions: HistoryActions) {
        const topBar = new St.BoxLayout({ x_expand: true, style_class: 'mei-top-bar' });
        this._backBtn = iconButton('go-previous-symbolic', 'Back to chat');
        this._backBtn.connect('clicked', () => this._actions.onBack());
        topBar.add_child(this._backBtn);
        this._title = new St.Label({
            text: 'History',
            style_class: 'mei-history-header-title',
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        topBar.add_child(this._title);
        topBar.add_child(new St.Widget({ width: 22 })); // matches the Back button, so the title centers
        this.actor.add_child(topBar);

        const scroll = new St.ScrollView({ style_class: 'mei-scroll', x_expand: true, y_expand: true, overlay_scrollbars: true });
        scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        scroll.set_style(`max-height: ${maxHeight}px;`);
        scroll.set_child(this._list);
        this.actor.add_child(scroll);
    }

    show(items: ChatSummary[]): void {
        this._list.destroy_all_children();
        if (items.length === 0) {
            this._list.add_child(new St.Label({
                text: 'No saved chats',
                style_class: 'mei-history-empty',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }));
        }
        const inProgress = items.filter(i => i.active);
        const rest = items.filter(i => !i.active);
        if (inProgress.length) {
            this._list.add_child(this._heading('In progress'));
            for (const item of inProgress) this._list.add_child(this._row(item));
            if (rest.length) this._list.add_child(this._heading('Earlier'));
        }
        for (const item of rest) this._list.add_child(this._row(item));
        this.applyTheme(this._isDark);
    }

    applyTheme(isDark: boolean): void {
        this._isDark = isDark;
        const fg = isDark ? '#ffffff' : '#000000';
        const muted = isDark ? '#a0a0a0' : '#666666';
        const bg = 'rgba(128, 128, 128, 0.15)';
        this._backBtn.set_style(`color: ${muted};`);
        this._title.set_style(`color: ${fg}; font-weight: bold; font-size: 14px;`);
        for (const child of this._list.get_children()) {
            if (child instanceof St.Label) {
                child.set_style(`color: ${muted};`);
            } else if (child instanceof St.BoxLayout) {
                const [open, remove] = child.get_children();
                if (open instanceof St.Widget) open.set_style(`color: ${fg}; background-color: ${bg};`);
                if (remove instanceof St.Widget) remove.set_style(`color: ${muted}; background-color: ${bg};`);
            }
        }
    }

    private _heading(text: string): St.Label {
        return new St.Label({ text, style_class: 'mei-history-heading' });
    }

    private _row(item: ChatSummary): St.BoxLayout {
        const title = item.title || 'Untitled';
        const row = new St.BoxLayout({ x_expand: true, style_class: 'mei-history-item-row' });

        const label = new St.BoxLayout({ x_expand: true });
        label.add_child(new St.Label({ text: title, x_expand: true, y_align: Clutter.ActorAlign.CENTER }));
        if (item.active) {
            label.add_child(new St.Label({ text: item.active, style_class: 'mei-history-badge', y_align: Clutter.ActorAlign.CENTER }));
        }
        const open = new St.Button({
            child: label,
            style_class: 'mei-history-title-btn',
            x_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            can_focus: true,
            reactive: true,
            track_hover: true,
            accessible_name: `Load chat: ${title}${item.active ? ` (${item.active})` : ''}`,
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        open.connect('clicked', () => {
            this._actions.onBack();
            this._actions.onLoadChat(item.id);
        });
        addClickScale(open);
        row.add_child(open);

        const icon = new St.Icon({ icon_name: 'user-trash-symbolic', icon_size: 14 });
        const remove = new St.Button({
            style_class: 'mei-history-delete-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            accessible_name: `Delete chat: ${title}`,
            accessible_role: Atk.Role.PUSH_BUTTON,
            child: icon,
        });
        let confirmId = 0;
        const stopConfirming = (): void => {
            confirmId = 0;
            if (!remove.get_parent()) return;
            remove.accessible_name = `Delete chat: ${title}`;
            remove.remove_style_class_name('selected');
            icon.icon_name = 'user-trash-symbolic';
        };
        remove.connect('clicked', () => {
            if (!confirmId) {
                remove.accessible_name = `Confirm delete chat: ${title}`;
                remove.add_style_class_name('selected');
                icon.icon_name = 'dialog-warning-symbolic';
                confirmId = this._sources.timeout(CONFIRM_DELETE_FOR_MS, () => {
                    stopConfirming();
                    return false;
                });
                return;
            }
            confirmId = this._sources.remove(confirmId);
            row.ease({ opacity: 0, duration: 150, mode: Clutter.AnimationMode.EASE_OUT_QUAD, onComplete: () => row.destroy() });
            this._actions.onDeleteChat(item.id);
        });
        addClickScale(remove);
        row.add_child(remove);
        return row;
    }
}
