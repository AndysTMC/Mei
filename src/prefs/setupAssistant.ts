/**
 * The setup assistant (§18.3): a page in the preferences window that walks the steps that exist
 * so far, Mei service, Models, Approvals, Privacy, Shortcuts, then a summary. It can be run again from
 * Settings. Each step shows what is already done and uses the same controls as Settings, so
 * re-running it without changes changes nothing.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import type { CallOptions } from '../runtime/client.js';
import type { ModelsStep, ServiceStep, SetupStatusReply, TestProviderReply } from '../runtime/protocol.js';
import type { RuntimeSettings } from '../runtime/settings.js';
import { buildApprovalRow, buildCloudFilesRow, buildMemoryRows, buildRetentionRow, buildShortcutRow, type Row } from './rows.js';
import { APPROVAL_FLOOR, doneText, keyringText, modelsText, SETUP_STEPS, storageText, testText } from './setupText.js';

export type Call = <T>(method: string, args?: object, opts?: CallOptions) => Promise<T>;

export interface SetupDeps {
    window: Adw.PreferencesWindow;
    call: Call;
    settings: RuntimeSettings;
    gsettings: Gio.Settings;
    /** Opens the provider settings page on top of setup; setup refreshes when it is shown again. */
    openProviders(): void;
    /** Called with fresh status after every refresh, so Settings can show it too. */
    onStatus(status: SetupStatusReply): void;
}

export interface SetupAssistant {
    page: Adw.NavigationPage;
    /** Start from the first step (for "Run setup again"). */
    restart(): void;
    refresh(): Promise<SetupStatusReply | null>;
    destroy(): void;
}

function errorText(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
}

export function shortcutLabel(gsettings: Gio.Settings, key: string): string {
    const accel = gsettings.get_strv(key)[0] ?? '';
    if (!accel) return '';
    const [ok, keyval, mods] = Gtk.accelerator_parse(accel);
    return ok ? Gtk.accelerator_get_label(keyval, mods ?? 0) : accel;
}

export function buildSetupAssistant(deps: SetupDeps): SetupAssistant {
    const { window, call, settings, gsettings } = deps;
    const rows: Row[] = [];
    const skipped = new Set<string>();
    let index = 0;
    let destroyed = false;

    const stack = new Gtk.Stack({ transition_type: Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vexpand: true });
    const step = (id: string, title: string, description: string) => {
        const page = new Adw.PreferencesPage();
        const group = new Adw.PreferencesGroup({ title, description });
        page.add(group);
        stack.add_named(page, id);
        return group;
    };

    /* ── 1. Mei service ── */
    const service = step('service', 'Mei service',
        'Mei runs as a small service on this computer. It keeps your conversations and settings and talks to the models you choose.');
    const runtimeRow = new Adw.ActionRow({ title: 'Service', subtitle: 'Checking…' });
    const keyringRow = new Adw.ActionRow({ title: 'Keyring', subtitle: 'Checking…' });
    const unlock = new Gtk.Button({ label: 'Unlock', valign: Gtk.Align.CENTER, visible: false });
    keyringRow.add_suffix(unlock);
    const storageRow = new Adw.ActionRow({ title: 'Storage', subtitle: 'Checking…' });
    for (const r of [runtimeRow, keyringRow, storageRow]) service.add(r);
    unlock.connect('clicked', () => {
        unlock.set_sensitive(false);
        keyringRow.set_subtitle('Waiting for the keyring…');
        call('SetupApply', { step: 'service', choices: { unlock_keyring: true } }, { timeoutMs: 130_000 })
            .then(() => refresh())
            .catch(e => {
                if (!destroyed) keyringRow.set_subtitle(`Couldn’t unlock the keyring: ${errorText(e)}`);
            })
            .finally(() => {
                if (!destroyed) unlock.set_sensitive(true);
            });
    });

    /* ── 2. Models ── */
    const models = step('models', 'Models',
        'Choose the model that answers. API keys go straight into your keyring, never into Mei’s settings.');
    const providerRow = new Adw.ActionRow({ title: 'Model', subtitle: 'Checking…' });
    const choose = new Gtk.Button({ label: 'Choose…', valign: Gtk.Align.CENTER });
    providerRow.add_suffix(choose);
    choose.connect('clicked', () => deps.openProviders());
    const testRow = new Adw.ActionRow({ title: 'Test', subtitle: 'Send one short message to check that it answers' });
    const testSpinner = new Adw.Spinner({ visible: false });
    const testButton = new Gtk.Button({ label: 'Send test', valign: Gtk.Align.CENTER });
    testRow.add_suffix(testSpinner);
    testRow.add_suffix(testButton);
    models.add(providerRow);
    models.add(testRow);
    testButton.connect('clicked', () => {
        testButton.set_sensitive(false);
        testSpinner.set_visible(true);
        testRow.set_subtitle('Waiting for an answer…');
        call<TestProviderReply>('TestProvider', {}, { timeoutMs: 60_000 })
            .then(reply => {
                if (!destroyed) testRow.set_subtitle(testText(reply));
            })
            .catch(e => {
                if (!destroyed) testRow.set_subtitle(`Didn't work: ${errorText(e)}`);
            })
            .finally(() => {
                if (destroyed) return;
                testButton.set_sensitive(true);
                testSpinner.set_visible(false);
            });
    });

    /* ── 3. Approvals ── */
    const approvals = step('approvals', 'Approvals',
        'Mei can work with your files, apps, and settings. Choose when it asks you first. ' + APPROVAL_FLOOR);
    const preset = buildApprovalRow(settings);
    rows.push(preset);
    approvals.add(preset.row);

    /* ── 4. Memory ── */
    const memory = step('memory', 'Memory',
        'Mei can remember facts about you, such as where your invoices go, and use them without being reminded. '
        + 'You can see, change, and delete everything it remembers in Settings.');
    for (const r of buildMemoryRows(settings)) {
        rows.push(r);
        memory.add(r.row);
    }

    /* ── 5. Privacy ── */
    const privacy = step('privacy', 'Privacy',
        'Mei keeps everything until you delete it. You can have conversations you no longer use deleted automatically, '
        + 'and choose which file contents may go to a cloud model.');
    const retention = buildRetentionRow(window, settings);
    const cloudFiles = buildCloudFilesRow(settings);
    rows.push(retention, cloudFiles);
    privacy.add(retention.row);
    privacy.add(cloudFiles.row);

    /* ── 6. Shortcuts ── */
    const shortcuts = step('shortcuts', 'Shortcuts', 'Open Mei from anywhere, with the message box ready for typing, '
        + 'or ask about what you are looking at: the window and the text you selected go with your question.');
    const shortcut = buildShortcutRow(window, gsettings, 'open-shortcut', 'Open Mei');
    const askShortcut = buildShortcutRow(window, gsettings, 'ask-shortcut', 'Ask about this');
    const voiceShortcut = buildShortcutRow(window, gsettings, 'voice-shortcut', 'Talk to Mei');
    rows.push(shortcut, askShortcut, voiceShortcut);
    shortcuts.add(shortcut.row);
    shortcuts.add(askShortcut.row);
    shortcuts.add(voiceShortcut.row);

    /* ── Summary ── */
    const done = new Adw.StatusPage({ icon_name: 'emblem-ok-symbolic', title: 'Mei is ready' });
    stack.add_named(done, 'done');

    /* ── Navigation ── */
    const title = new Adw.WindowTitle({ title: 'Set up Mei' });
    const header = new Adw.HeaderBar({ title_widget: title });
    const back = new Gtk.Button({ label: 'Back' });
    const skip = new Gtk.Button({ label: 'Skip' });
    const next = new Gtk.Button({ label: 'Next', css_classes: ['suggested-action'] });
    const bar = new Gtk.CenterBox({ margin_start: 12, margin_end: 12, margin_top: 6, margin_bottom: 6 });
    const right = new Gtk.Box({ spacing: 6 });
    right.append(skip);
    right.append(next);
    bar.set_start_widget(back);
    bar.set_end_widget(right);
    const view = new Adw.ToolbarView({ content: stack });
    view.add_top_bar(header);
    view.add_bottom_bar(bar);
    const page = new Adw.NavigationPage({ title: 'Set up Mei', child: view, tag: 'setup' });

    const ids = [...SETUP_STEPS.map(s => s.id), 'done'];
    const show = () => {
        const info = SETUP_STEPS[index];
        stack.set_visible_child_name(ids[index]);
        title.set_subtitle(info ? `Step ${index + 1} of ${SETUP_STEPS.length}` : '');
        back.set_sensitive(index > 0);
        skip.set_visible(Boolean(info?.skippable));
        next.set_label(info ? 'Next' : 'Finish');
        if (!info) done.set_description(doneText(skipped, shortcutLabel(gsettings, 'open-shortcut')));
    };
    back.connect('clicked', () => {
        index = Math.max(0, index - 1);
        show();
    });
    skip.connect('clicked', () => {
        skipped.add(ids[index]);
        index++;
        show();
    });
    next.connect('clicked', () => {
        if (index < SETUP_STEPS.length) {
            skipped.delete(ids[index]);
            index++;
            show();
            return;
        }
        next.set_sensitive(false);
        call('SetupApply', { step: 'finish', choices: { skipped: [...skipped].sort() } })
            .then(() => {
                if (destroyed) return;
                window.pop_subpage();
                void refresh();
            })
            .catch(e => {
                if (!destroyed) done.set_description(`Couldn’t save that setup is finished: ${errorText(e)}`);
            })
            .finally(() => {
                if (!destroyed) next.set_sensitive(true);
            });
    });

    /* ── Status ── */
    const home = GLib.get_home_dir();
    async function refresh(): Promise<SetupStatusReply | null> {
        let status: SetupStatusReply;
        try {
            status = await call<SetupStatusReply>('SetupStatus');
        } catch (e) {
            if (!destroyed) runtimeRow.set_subtitle(`Not reachable: ${errorText(e)}`);
            return null;
        }
        if (destroyed) return status;
        for (const s of status.steps) {
            if (s.id === 'service') renderService(s);
            else if (s.id === 'models') renderModels(s);
        }
        deps.onStatus(status);
        return status;
    }
    function renderService(s: ServiceStep) {
        runtimeRow.set_subtitle(`Running · version ${s.runtime_version}`);
        keyringRow.set_subtitle(keyringText(s.keyring));
        unlock.set_visible(s.keyring === 'locked');
        storageRow.set_subtitle(storageText(s, home));
    }
    function renderModels(s: ModelsStep) {
        providerRow.set_subtitle(modelsText(s));
        testButton.set_sensitive(Boolean(s.provider && s.model));
    }

    page.connect('shown', () => void refresh()); // back from the provider page, or opened again
    const settingsSignal = settings.connect('changed', () => void refresh());
    show();

    return {
        page,
        restart() {
            index = 0;
            skipped.clear();
            show();
        },
        refresh,
        destroy() {
            destroyed = true;
            settings.disconnect(settingsSignal);
            rows.forEach(r => r.destroy());
        },
    };
}
