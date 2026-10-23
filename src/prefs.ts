/**
 * Mei's Settings window (GTK 4 / libadwaita), run by GNOME's extension preferences process.
 *
 * The main page holds the service status, setup, links to the provider and log pages, and the
 * approval, privacy, and shortcut settings. Settings live in the Mei runtime (ADR 0002), reached over D-Bus;
 * the keyboard shortcuts are the only GSettings keys, because keybindings must be GSettings keys.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import { ExtensionPreferences } from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

import { GrantsPage } from './prefs/grantsPage.js';
import { LogsPage } from './prefs/logsPage.js';
import { MemoryPage } from './prefs/memoryPage.js';
import { VoicePage } from './prefs/voicePage.js';
import { ProviderPage } from './prefs/providerPage.js';
import { buildApprovalRow, buildCloudFilesRow, buildRetentionRow, buildShortcutRow } from './prefs/rows.js';
import { buildSetupAssistant, type Call } from './prefs/setupAssistant.js';
import { RuntimeClient } from './runtime/client.js';
import type { SetupStatusReply } from './runtime/protocol.js';
import { RuntimeSettings } from './runtime/settings.js';
import { APPROVAL_FLOOR } from './prefs/setupText.js';
import { SourceSet } from './ui/sources.js';
import { Logger, Tag } from './utils/logger.js';

/** How often this window retries loading settings while a change waits to be saved. */
const SAVE_RETRY_MS = 5000;

export default class MeiPreferences extends ExtensionPreferences {
    override async fillPreferencesWindow(window: Adw.PreferencesWindow): Promise<void> {
        window.set_title('Mei');
        monochrome(window);
        const client = new RuntimeClient(() => 0); // calls start the runtime if it isn't running
        const call: Call = (method, args, opts) => client.call(method, args, opts);
        const settings = new RuntimeSettings((method, args) => client.call(method, args));
        try {
            await settings.reload();
        } catch (e) {
            window.add(unavailablePage(e));
            return;
        }

        const sources = new SourceSet();
        const providers = new ProviderPage(settings);
        const logs = new LogsPage(window, settings);
        const grants = new GrantsPage(window, settings);
        const memory = new MemoryPage(window, settings);
        const voice = new VoicePage(window, settings);
        const preset = buildApprovalRow(settings);
        const retention = buildRetentionRow(window, settings);
        const cloudFiles = buildCloudFilesRow(settings);
        const shortcut = buildShortcutRow(window, this.getSettings(), 'open-shortcut', 'Open Mei');
        const askShortcut = buildShortcutRow(window, this.getSettings(), 'ask-shortcut', 'Ask about this');
        const voiceShortcut = buildShortcutRow(window, this.getSettings(), 'voice-shortcut', 'Talk to Mei');

        const page = new Adw.PreferencesPage({ title: 'Mei', icon_name: 'preferences-system-symbolic' });
        const mei = new Adw.PreferencesGroup({ title: 'Mei' });
        const service = new Adw.ActionRow({ title: 'Mei service', subtitle: 'Checking…', icon_name: 'emblem-system-symbolic' });
        const rerun = navRow('Run setup again', 'Go through the setup steps; nothing changes unless you change it',
            'view-refresh-symbolic');
        mei.add(service);
        mei.add(rerun);
        page.add(mei);

        const more = new Adw.PreferencesGroup({ title: 'Settings' });
        const providerRow = navRow('Model provider', 'Ollama, OpenAI, Anthropic, Gemini, and more', 'network-server-symbolic');
        const logsRow = navRow('Logs', 'What the Mei service has been doing', 'format-justify-left-symbolic');
        const memoryRow = navRow('Memory', 'What Mei remembers about you', 'user-bookmarks-symbolic');
        const voiceRow = navRow('Voice', 'Talk to Mei and hear it answer', 'audio-input-microphone-symbolic');
        more.add(providerRow);
        more.add(memoryRow);
        more.add(voiceRow);
        more.add(logsRow);
        page.add(more);
        const approvals = new Adw.PreferencesGroup({ title: 'Approvals', description: APPROVAL_FLOOR });
        const grantsRow = navRow('Always allowed', 'Things you told Mei it may always do', 'emblem-ok-symbolic');
        approvals.add(preset.row);
        approvals.add(grantsRow);
        page.add(approvals);
        const privacy = new Adw.PreferencesGroup({ title: 'Privacy' });
        privacy.add(retention.row);
        privacy.add(cloudFiles.row);
        page.add(privacy);
        const shortcuts = group('Shortcuts', shortcut.row);
        shortcuts.add(askShortcut.row);
        shortcuts.add(voiceShortcut.row);
        page.add(shortcuts);
        window.add(page);

        // This window isn't subscribed to the runtime's events (they include every streamed reply),
        // so it reloads whenever it comes back into use; changes made elsewhere then show up.
        const refresh = () => settings.reload().catch(e => Logger.debug(Tag.Prefs, `Reloading settings: ${(e as Error).message}`));
        window.connect('notify::is-active', () => {
            if (window.is_active) void refresh();
        });
        providerRow.connect('activated', () => {
            window.push_subpage(providers.page);
            void refresh();
        });
        logsRow.connect('activated', () => window.push_subpage(logs.page));
        grantsRow.connect('activated', () => window.push_subpage(grants.page));
        memoryRow.connect('activated', () => window.push_subpage(memory.page));
        voiceRow.connect('activated', () => window.push_subpage(voice.page));

        const setup = buildSetupAssistant({
            window, call, settings, gsettings: this.getSettings(),
            openProviders: () => window.push_subpage(providers.page),
            onStatus: status => service.set_subtitle(serviceSummary(status)),
        });
        rerun.connect('activated', () => {
            setup.restart();
            window.push_subpage(setup.page);
        });
        // Until setup is finished, Settings opens on it (the extension opens Settings once, at the
        // first login after installing).
        void setup.refresh().then(status => {
            if (!status || status.completed) return;
            window.push_subpage(setup.page);
            if (!status.offered) {
                call('SetupApply', { step: 'offered' }).catch(e =>
                    Logger.warn(Tag.Prefs, `Couldn't record that setup was offered: ${(e as Error).message}`));
            }
        });

        // The popup's connection reloads settings when the runtime comes back; this window has no
        // such connection, so it retries the load itself until an unsaved change goes through.
        let retryId = 0;
        const saveFailed = settings.connect('save-failed', (_s, message) => {
            window.add_toast(new Adw.Toast({ title: `Not saved yet; Mei will retry when it reconnects (${message})`, timeout: 6 }));
            retryId ||= sources.timeout(SAVE_RETRY_MS, () => {
                settings.reload().then(() => {
                    retryId = sources.remove(retryId);
                }).catch(e => Logger.debug(Tag.Prefs, `Runtime still unavailable: ${(e as Error).message}`));
                return GLib.SOURCE_CONTINUE;
            });
        });

        window.connect('destroy', () => {
            sources.destroy();
            settings.disconnect(saveFailed);
            for (const part of [providers, logs, setup, preset, retention, cloudFiles, shortcut, askShortcut, voiceShortcut,
                memory, voice]) part.destroy();
        });
    }
}

function unavailablePage(error: unknown): Adw.PreferencesPage {
    const page = new Adw.PreferencesPage({ title: 'Mei', icon_name: 'preferences-system-symbolic' });
    page.add(new Adw.PreferencesGroup({
        title: 'The Mei service can’t be reached',
        description: `Mei’s settings live in its service, which didn’t answer: ${error instanceof Error ? error.message : String(error)}`,
    }));
    return page;
}

function navRow(title: string, subtitle: string, iconName: string): Adw.ActionRow {
    const row = new Adw.ActionRow({ title, subtitle, icon_name: iconName, activatable: true });
    row.add_suffix(new Gtk.Image({ icon_name: 'go-next-symbolic' }));
    return row;
}

function group(title: string, row: Adw.PreferencesRow): Adw.PreferencesGroup {
    const g = new Adw.PreferencesGroup({ title });
    g.add(row);
    return g;
}

function serviceSummary(status: SetupStatusReply): string {
    const service = status.steps.find(step => step.id === 'service');
    if (service?.id !== 'service') return 'Running';
    const keyring = service.keyring === 'missing' ? 'not found' : service.keyring;
    return `Running · version ${service.runtime_version} · keyring ${keyring}`;
}

/**
 * Mei's look is monochrome: in Mei's window only, the system accent becomes the text's own color
 * (the suggested button inverts, as in the popup), and a switch that's on is grey, so its white knob
 * still shows, in light and dark.
 */
const MONOCHROME = {
    light: 'window.mei-prefs { --accent-bg-color: #241f31; --accent-fg-color: #ffffff; --accent-color: #241f31; } '
        + 'window.mei-prefs switch:checked { background-color: #5e5c64; }',
    dark: 'window.mei-prefs { --accent-bg-color: #f6f5f4; --accent-fg-color: #000000; --accent-color: #f6f5f4; } '
        + 'window.mei-prefs switch:checked { background-color: #9a9996; }',
};

function monochrome(window: Adw.PreferencesWindow): void {
    const provider = new Gtk.CssProvider();
    const style = Adw.StyleManager.get_default();
    const load = () => provider.load_from_string(style.dark ? MONOCHROME.dark : MONOCHROME.light);
    load();
    const signal = style.connect('notify::dark', load);
    const display = window.get_display();
    Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
    window.add_css_class('mei-prefs');
    window.connect('destroy', () => {
        style.disconnect(signal);
        Gtk.StyleContext.remove_provider_for_display(display, provider);
    });
}
