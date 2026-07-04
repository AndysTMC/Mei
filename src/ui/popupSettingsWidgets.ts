/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import type { ProviderConfigKey } from '../providers/configStore.js';

export type SettingsEntryActor = St.Entry | St.PasswordEntry;

export interface SettingsWidgetCallbacks {
    addButtonClickScaleEffect(button: St.Button): void;
}

export function addSettingsSection(listBox: St.BoxLayout, title: string): void {
    const label = new St.Label({
        text: title,
        style_class: 'mei-settings-section-title',
        x_expand: true,
    });
    listBox.add_child(label);
}

export function addSettingsNavRow(
    listBox: St.BoxLayout,
    title: string,
    iconName: string,
    onClick: () => void,
    callbacks: SettingsWidgetCallbacks
): void {
    const button = new St.Button({
        style_class: 'mei-settings-nav-row',
        can_focus: true,
        reactive: true,
        track_hover: true,
        accessible_name: title,
        accessible_role: Atk.Role.PUSH_BUTTON,
    });

    const row = new St.BoxLayout({
        x_expand: true,
        style_class: 'mei-settings-nav-content',
    });
    row.add_child(new St.Icon({ icon_name: iconName, icon_size: 16 }));
    row.add_child(new St.Label({
        text: title,
        x_expand: true,
        y_align: Clutter.ActorAlign.CENTER,
        style_class: 'mei-settings-nav-label',
    }));
    row.add_child(new St.Icon({ icon_name: 'go-next-symbolic', icon_size: 14 }));
    button.set_child(row);
    button.connect('clicked', onClick);
    listBox.add_child(button);
    callbacks.addButtonClickScaleEffect(button);
}

export function addSettingsStatusRow(listBox: St.BoxLayout, text: string): void {
    const label = new St.Label({
        text,
        x_expand: true,
        style_class: 'mei-settings-status',
    });
    label.clutter_text.set_line_wrap(true);
    label.clutter_text.set_line_wrap_mode(0);
    listBox.add_child(label);
}

export function createSettingsRow(labelText: string): St.BoxLayout {
    const row = new St.BoxLayout({
        x_expand: true,
        style_class: 'mei-settings-row',
    });

    const label = new St.Label({
        text: labelText,
        style_class: 'mei-settings-label',
        y_align: Clutter.ActorAlign.CENTER,
    });
    row.add_child(label);

    const spacer = new St.Widget({
        x_expand: true,
    });
    row.add_child(spacer);

    return row;
}

export function addSettingsSegmentRow<T extends string>(
    listBox: St.BoxLayout,
    labelText: string,
    ids: readonly T[],
    activeId: T,
    getLabel: (id: T) => string,
    onSelect: (id: T) => void,
    callbacks: SettingsWidgetCallbacks
): void {
    const row = createSettingsRow(labelText);
    const segments = new St.BoxLayout({
        style_class: 'mei-settings-segment-row',
        x_align: Clutter.ActorAlign.END,
    });

    for (const id of ids) {
        const selected = id === activeId;
        const button = new St.Button({
            label: getLabel(id),
            style_class: selected ? 'mei-settings-chip selected' : 'mei-settings-chip',
            can_focus: true,
            reactive: true,
            track_hover: true,
            accessible_name: `${labelText}: ${getLabel(id)}`,
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        button.connect('clicked', () => onSelect(id));
        segments.add_child(button);
        callbacks.addButtonClickScaleEffect(button);
    }

    row.add_child(segments);
    listBox.add_child(row);
}

export function addSettingsEntryRow(
    listBox: St.BoxLayout,
    labelText: string,
    value: string,
    key: ProviderConfigKey,
    hintText: string,
    isSecret: boolean,
    isRefreshing: () => boolean,
    onSave: (key: ProviderConfigKey, value: string, labelText: string) => void,
    callbacks: SettingsWidgetCallbacks
): SettingsEntryActor {
    const row = createSettingsRow(labelText);
    const initialValue = value;
    const entry = isSecret
        ? new St.PasswordEntry({
            text: value,
            hint_text: hintText,
            show_peek_icon: true,
            can_focus: true,
            x_expand: true,
            style_class: 'mei-settings-entry',
            accessible_name: labelText,
        })
        : new St.Entry({
            text: value,
            hint_text: hintText,
            can_focus: true,
            x_expand: true,
            style_class: 'mei-settings-entry',
            accessible_name: labelText,
        });

    entry.clutter_text.set_single_line_mode(true);
    row.add_child(entry);

    const saveBtn = new St.Button({
        style_class: 'mei-settings-save-field-btn',
        can_focus: true,
        reactive: false,
        track_hover: true,
        accessible_name: `Save ${labelText}`,
        accessible_role: Atk.Role.PUSH_BUTTON,
        child: new St.Icon({
            icon_name: 'object-select-symbolic',
            icon_size: 13,
        }),
    });
    saveBtn.opacity = 90;
    saveBtn.connect('clicked', () => {
        if (!saveBtn.reactive) return;
        onSave(key, entry.get_text(), labelText);
    });
    entry.clutter_text.connect('text-changed', () => {
        if (isRefreshing()) return;
        const dirty = entry.get_text() !== initialValue;
        saveBtn.reactive = dirty;
        saveBtn.opacity = dirty ? 255 : 90;
    });
    row.add_child(saveBtn);
    callbacks.addButtonClickScaleEffect(saveBtn);

    listBox.add_child(row);
    return entry;
}
