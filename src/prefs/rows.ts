/**
 * Settings rows shared by the setup assistant and the Settings pages, so a choice made in setup
 * is the same control (and the same setting) afterwards.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import Gdk from 'gi://Gdk';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import type { RuntimeSettings } from '../runtime/settings.js';
import { APPROVAL_PRESETS, CLOUD_FILES, periodText, retentionLabel, retentionOptions, retentionShrinks } from './setupText.js';

export interface Row<T extends Gtk.Widget = Gtk.Widget> {
    row: T;
    destroy(): void;
}

/** Conversation retention (§14.4). Choosing a shorter period asks first: it deletes at once. */
export function buildRetentionRow(window: Gtk.Window, settings: RuntimeSettings): Row<Adw.ComboRow> {
    const labels = new Gtk.StringList();
    const row = new Adw.ComboRow({
        title: 'Delete old conversations',
        subtitle: 'Conversations you haven’t used for this long are deleted',
        model: labels,
    });
    let options: (number | null)[] = [];
    let updating = false;

    const render = () => {
        updating = true;
        options = retentionOptions(settings.retentionDays);
        labels.splice(0, labels.get_n_items(), options.map(retentionLabel));
        row.set_selected(options.indexOf(settings.retentionDays));
        updating = false;
    };

    row.connect('notify::selected', () => {
        const index = row.get_selected();
        if (updating || index >= options.length) return; // no selection (GTK_INVALID_LIST_POSITION)
        const next = options[index];
        const current = settings.retentionDays;
        if (next === current) return;
        if (!retentionShrinks(current, next)) {
            settings.setRetentionDays(next);
            return;
        }
        const dialog = new Adw.AlertDialog({
            heading: 'Delete old conversations?',
            body: `Conversations you haven’t used for ${periodText(next as number)} are deleted now, ` +
                'and from then on automatically. This can’t be undone.',
        });
        dialog.add_response('cancel', 'Cancel');
        dialog.add_response('delete', 'Delete');
        dialog.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE);
        dialog.set_default_response('cancel');
        dialog.set_close_response('cancel');
        dialog.connect('response', (_d: Adw.AlertDialog, response: string) => {
            if (response === 'delete') settings.setRetentionDays(next);
            else render();
        });
        dialog.present(window);
    });

    const signal = settings.connect('changed::privacy', render);
    render();
    return { row, destroy: () => settings.disconnect(signal) };
}

/** One choice out of a few, shown with the chosen option's description as the subtitle. Re-renders
 * whenever `signal` fires on `settings`. */
function choiceRow<T extends string>(settings: RuntimeSettings, signal: string, title: string,
    options: { id: T; label: string; description: string }[], current: () => T,
    choose: (id: T) => void): Row<Adw.ComboRow> {
    const row = new Adw.ComboRow({ title, model: Gtk.StringList.new(options.map(o => o.label)) });
    let updating = false;
    const render = () => {
        updating = true;
        const index = Math.max(0, options.findIndex(o => o.id === current()));
        row.set_selected(index);
        row.set_subtitle(options[index].description);
        updating = false;
    };
    row.connect('notify::selected', () => {
        const option = options[row.get_selected()];
        if (updating || !option) return;
        row.set_subtitle(option.description);
        choose(option.id);
    });
    const id = settings.connect(signal, render);
    render();
    return { row, destroy: () => settings.disconnect(id) };
}

/** Memory on or off, and whether what Mei infers is kept without review (§17.4). */
export function buildMemoryRows(settings: RuntimeSettings): Row<Adw.SwitchRow>[] {
    return [
        switchRow(settings, 'Remember things about me',
            'Mei recalls what it knows about you in each task, and saves new facts. Everything stays on this computer.',
            () => settings.memoryEnabled, on => settings.setMemoryEnabled(on)),
        switchRow(settings, 'Keep what Mei works out',
            'Facts Mei infers are kept without asking. What you tell it to remember is always kept; anything '
            + 'that came from a file or page waits for you to review it.',
            () => settings.memoryAutoSave, on => settings.setMemoryAutoSave(on)),
    ];
}

function switchRow(settings: RuntimeSettings, title: string, subtitle: string, current: () => boolean,
    choose: (on: boolean) => void): Row<Adw.SwitchRow> {
    const row = new Adw.SwitchRow({ title, subtitle });
    let updating = false;
    const render = () => {
        updating = true;
        row.set_active(current());
        updating = false;
    };
    row.connect('notify::active', () => {
        if (!updating) choose(row.get_active());
    });
    const id = settings.connect('changed::memory', render);
    render();
    return { row, destroy: () => settings.disconnect(id) };
}

/** Which actions Mei takes without asking (§13.2). */
export function buildApprovalRow(settings: RuntimeSettings): Row<Adw.ComboRow> {
    return choiceRow(settings, 'changed::approvals', 'When Mei asks first', APPROVAL_PRESETS,
        () => settings.approvalPreset, id => settings.setApprovalPreset(id));
}

/** Which file contents may go to cloud models (§13.5). Local models are never limited by this. */
export function buildCloudFilesRow(settings: RuntimeSettings): Row<Adw.ComboRow> {
    return choiceRow(settings, 'changed::privacy', 'File contents sent to cloud models', CLOUD_FILES,
        () => settings.cloudFiles, id => settings.setCloudFiles(id));
}

/** A global shortcut stored in the extension's GSettings (keybindings have to live there). */
export function buildShortcutRow(window: Gtk.Window, gsettings: Gio.Settings, key: string,
    title: string): Row<Adw.ActionRow> {
    const row = new Adw.ActionRow({ title });
    const label = new Gtk.ShortcutLabel({ disabled_text: 'Off', valign: Gtk.Align.CENTER });
    const change = new Gtk.Button({ label: 'Change…', valign: Gtk.Align.CENTER });
    const clear = new Gtk.Button({
        icon_name: 'edit-clear-symbolic', valign: Gtk.Align.CENTER, tooltip_text: 'Turn off', css_classes: ['flat'],
    });
    row.add_suffix(label);
    row.add_suffix(change);
    row.add_suffix(clear);

    const render = () => {
        const accel = gsettings.get_strv(key)[0] ?? '';
        label.set_accelerator(accel);
        clear.set_sensitive(Boolean(accel));
    };
    change.connect('clicked', () => captureShortcut(window, title, accel => gsettings.set_strv(key, accel ? [accel] : [])));
    clear.connect('clicked', () => gsettings.set_strv(key, []));
    const signal = gsettings.connect(`changed::${key}`, render);
    render();
    return { row, destroy: () => gsettings.disconnect(signal) };
}

/** Wait for a key combination with at least one modifier. Esc cancels; Backspace turns it off. */
function captureShortcut(parent: Gtk.Window, title: string, done: (accel: string) => void): void {
    const dialog = new Adw.Window({ modal: true, transient_for: parent, default_width: 420, title });
    const status = new Adw.StatusPage({
        icon_name: 'preferences-desktop-keyboard-shortcuts-symbolic',
        title: 'Press the new shortcut',
        description: 'Use at least one of Super, Ctrl, or Alt. Esc cancels; Backspace turns the shortcut off.',
    });
    const view = new Adw.ToolbarView({ content: status });
    view.add_top_bar(new Adw.HeaderBar());
    dialog.set_content(view);

    const keys = new Gtk.EventControllerKey();
    keys.connect('key-pressed', (_c: Gtk.EventControllerKey, keyval: number, keycode: number, state: Gdk.ModifierType) => {
        const mods = state & Gtk.accelerator_get_default_mod_mask();
        const lower = Gdk.keyval_to_lower(keyval);
        if (!mods && lower === Gdk.KEY_Escape) {
            dialog.close();
        } else if (!mods && lower === Gdk.KEY_BackSpace) {
            done('');
            dialog.close();
        } else if (mods && Gtk.accelerator_valid(lower, mods)) {
            done(Gtk.accelerator_name_with_keycode(null, lower, keycode, mods));
            dialog.close();
        }
        return true;
    });
    dialog.add_controller(keys);
    dialog.present();
}
