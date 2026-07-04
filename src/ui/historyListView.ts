/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

export interface ChatSummary {
    id: string;
    title: string;
}

export interface HistoryListCallbacks {
    addButtonClickScaleEffect(button: St.Button): void;
    addOneShotTimeout(priority: number, interval: number, callback: () => typeof GLib.SOURCE_REMOVE): number;
    removeSource(sourceId: number): void;
    hideHistoryList(): void;
    onLoadChat(id: string): void;
    onDeleteChat(id: string): void;
}

export function renderHistoryList(
    listBox: St.BoxLayout,
    items: ChatSummary[],
    callbacks: HistoryListCallbacks
): void {
    listBox.destroy_all_children();

    if (items.length === 0) {
        const emptyLabel = new St.Label({
            text: 'No saved chats',
            style_class: 'mei-history-empty',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        listBox.add_child(emptyLabel);
        return;
    }

    for (const item of items) {
        listBox.add_child(createHistoryRow(item, callbacks));
    }
}

export function styleHistoryList(listBox: St.BoxLayout, isDark: boolean): void {
    const fg = isDark ? '#ffffff' : '#000000';
    const bg = 'rgba(128, 128, 128, 0.15)';
    const iconColor = isDark ? '#a0a0a0' : '#666666';

    for (const child of listBox.get_children()) {
        if (child instanceof St.Label) {
            child.set_style(`color: ${iconColor};`);
        } else if (child instanceof St.BoxLayout) {
            const buttons = child.get_children();
            if (buttons.length >= 2) {
                const titleBtn = buttons[0] as St.Button;
                const deleteBtn = buttons[1] as St.Button;
                titleBtn.set_style(`color: ${fg}; background-color: ${bg};`);
                deleteBtn.set_style(`color: ${iconColor}; background-color: ${bg};`);
            }
        }
    }
}

function createHistoryRow(item: ChatSummary, callbacks: HistoryListCallbacks): St.BoxLayout {
    const title = item.title || 'Untitled';
    const row = new St.BoxLayout({
        x_expand: true,
        style_class: 'mei-history-item-row',
    });

    const titleBtn = new St.Button({
        label: title,
        style_class: 'mei-history-title-btn',
        x_expand: true,
        x_align: Clutter.ActorAlign.FILL,
        can_focus: true,
        reactive: true,
        track_hover: true,
        accessible_name: `Load chat: ${title}`,
        accessible_role: Atk.Role.PUSH_BUTTON,
    });
    titleBtn.connect('clicked', () => {
        callbacks.hideHistoryList();
        callbacks.onLoadChat(item.id);
    });
    row.add_child(titleBtn);
    callbacks.addButtonClickScaleEffect(titleBtn);

    const deleteIcon = new St.Icon({
        icon_name: 'user-trash-symbolic',
        icon_size: 14,
    });
    let deleteConfirming = false;
    let deleteConfirmTimeoutId = 0;
    const deleteBtn = new St.Button({
        style_class: 'mei-history-delete-btn',
        can_focus: true,
        reactive: true,
        track_hover: true,
        accessible_name: `Delete chat: ${title}`,
        accessible_role: Atk.Role.PUSH_BUTTON,
        child: deleteIcon,
    });
    const resetDeleteConfirmation = (): void => {
        deleteConfirming = false;
        deleteConfirmTimeoutId = 0;
        if (!deleteBtn.get_parent()) return;
        deleteBtn.accessible_name = `Delete chat: ${title}`;
        deleteBtn.remove_style_class_name('selected');
        deleteIcon.icon_name = 'user-trash-symbolic';
    };

    deleteBtn.connect('clicked', () => {
        if (!deleteConfirming) {
            deleteConfirming = true;
            deleteBtn.accessible_name = `Confirm delete chat: ${title}`;
            deleteBtn.add_style_class_name('selected');
            deleteIcon.icon_name = 'dialog-warning-symbolic';
            deleteConfirmTimeoutId = callbacks.addOneShotTimeout(GLib.PRIORITY_DEFAULT, 3000, () => {
                resetDeleteConfirmation();
                return GLib.SOURCE_REMOVE;
            });
            return;
        }
        if (deleteConfirmTimeoutId !== 0) {
            callbacks.removeSource(deleteConfirmTimeoutId);
            deleteConfirmTimeoutId = 0;
        }
        row.ease({
            opacity: 0,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                row.destroy();
            },
        });
        callbacks.onDeleteChat(item.id);
    });
    row.add_child(deleteBtn);
    callbacks.addButtonClickScaleEffect(deleteBtn);

    return row;
}
