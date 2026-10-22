/**
 * Settings → Voice (§11, decision 0017): talk to Mei, which models are on this computer, how it
 * listens and speaks, and checks for the microphone and speakers. The setup assistant's Voice step
 * uses the same rows (`voiceBasics`).
 *
 * Choosing a cloud provider for listening sends what the person says to that provider; the choice
 * says so where it is made (§11.5).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Adw from 'gi://Adw';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import type { SttChoice, TtsChoice, VoiceModelsReply } from '../runtime/protocol.js';
import type { RuntimeSettings } from '../runtime/settings.js';
import { micText, modelLine, STT_CHOICES, TTS_CHOICES, voiceStatusText } from './setupText.js';
import { choiceRow, switchRow, type Row } from './rows.js';

const POLL_MS = 500;

/** The rows setup and Settings share: on/off, the models it needs, and the checks. */
export function voiceBasics(window: Gtk.Window, settings: RuntimeSettings): { groups: Adw.PreferencesGroup[]; destroy(): void } {
    const voice = new Adw.PreferencesGroup({ title: 'Voice' });
    const enabled = new Adw.SwitchRow({ title: 'Talk to Mei',
        subtitle: 'Press Super+Alt+Space (or the mic button) and speak; Mei answers out loud' });
    const status = new Adw.ActionRow({ title: 'Status', subtitle: 'Checking…' });
    voice.add(enabled);
    voice.add(status);

    const models = new Adw.PreferencesGroup({ title: 'On this computer',
        description: 'Voice runs on this computer. These are downloaded once, from the models’ publisher, and checked.' });
    const getAll = new Gtk.Button({ label: 'Download', valign: Gtk.Align.CENTER, css_classes: ['suggested-action'] });
    models.set_header_suffix(getAll);
    const modelRows = new Map<string, Adw.ActionRow>();

    const checks = new Adw.PreferencesGroup({ title: 'Check' });
    const mic = new Adw.ActionRow({ title: 'Microphone', subtitle: 'Stay quiet for three seconds while Mei listens' });
    const checkMic = new Gtk.Button({ label: 'Check', valign: Gtk.Align.CENTER });
    const fixMic = new Gtk.Button({ label: 'Fix', valign: Gtk.Align.CENTER, visible: false, css_classes: ['suggested-action'] });
    mic.add_suffix(fixMic);
    mic.add_suffix(checkMic);
    const speaker = new Adw.ActionRow({ title: 'Speaker', subtitle: 'Hear how Mei sounds' });
    const play = new Gtk.Button({ label: 'Play', valign: Gtk.Align.CENTER });
    speaker.add_suffix(play);
    checks.add(mic);
    checks.add(speaker);

    let destroyed = false;
    let pollId = 0;
    let updating = false;
    const fail = (e: unknown) => window instanceof Adw.PreferencesWindow
        ? window.add_toast(new Adw.Toast({ title: e instanceof Error ? e.message : String(e) })) : undefined;

    const show = (reply: VoiceModelsReply) => {
        status.set_subtitle(voiceStatusText(reply.state, reply.note));
        for (const m of reply.models) {
            if (!m.needed && !m.have && !modelRows.has(m.id)) continue;
            let row = modelRows.get(m.id);
            if (!row) {
                row = new Adw.ActionRow({ title: m.part.charAt(0).toUpperCase() + m.part.slice(1) });
                modelRows.set(m.id, row);
                models.add(row);
            }
            row.set_subtitle(modelLine(m));
        }
        const missing = reply.models.filter(m => m.needed && !m.have).map(m => m.id);
        getAll.set_sensitive(missing.length > 0 && !reply.downloading);
        getAll.set_label(reply.downloading ? 'Downloading…' : missing.length ? 'Download' : 'Downloaded');
        const ready = reply.state === 'idle' || reply.state === 'speaking';
        checkMic.set_sensitive(ready);
        play.set_sensitive(ready);
        return reply.downloading || reply.state === 'starting';
    };

    const refresh = async () => {
        let busy = false;
        try {
            busy = show(await settings.voiceModels());
        } catch (e) {
            status.set_subtitle(`Not available: ${e instanceof Error ? e.message : String(e)}`);
        }
        if (destroyed) return;
        if (busy && !pollId) {
            pollId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POLL_MS, () => {
                pollId = 0;
                void refresh();
                return GLib.SOURCE_REMOVE;
            });
        }
    };

    const render = () => {
        updating = true;
        enabled.set_active(settings.voice.enabled);
        updating = false;
        void refresh();
    };
    enabled.connect('notify::active', () => {
        if (!updating) settings.setVoice('enabled', enabled.get_active());
    });
    getAll.connect('clicked', () => {
        settings.voiceModels()
            .then(r => settings.downloadVoiceModels(r.models.filter(m => m.needed && !m.have).map(m => m.id)))
            .then(() => refresh()).catch(fail);
    });
    checkMic.connect('clicked', () => {
        checkMic.set_sensitive(false);
        mic.set_subtitle('Listening… stay quiet');
        settings.checkMic().then(level => {
            mic.set_subtitle(micText(level));
            fixMic.set_visible(level.overdriven);
        }).catch(e => mic.set_subtitle(`Couldn’t check: ${e instanceof Error ? e.message : String(e)}`))
            .finally(() => checkMic.set_sensitive(true));
    });
    fixMic.connect('clicked', () => {
        fixMic.set_sensitive(false);
        settings.fixMic().then(level => {
            mic.set_subtitle(micText(level));
            fixMic.set_visible(level.overdriven);
        }).catch(fail).finally(() => fixMic.set_sensitive(true));
    });
    play.connect('clicked', () => void settings.testSpeaker().catch(fail));
    const signal = settings.connect('changed::voice', render);
    render();
    return {
        groups: [voice, models, checks],
        destroy: () => {
            destroyed = true;
            if (pollId) GLib.source_remove(pollId);
            settings.disconnect(signal);
        },
    };
}

export class VoicePage {
    readonly page: Adw.NavigationPage;
    private readonly _parts: { destroy(): void }[] = [];

    constructor(window: Adw.PreferencesWindow, settings: RuntimeSettings) {
        const prefs = new Adw.PreferencesPage();
        const basics = voiceBasics(window, settings);
        this._parts.push(basics);
        const [voice, models, checks] = basics.groups;
        prefs.add(voice);

        const listening = new Adw.PreferencesGroup({ title: 'Listening' });
        const stt = choiceRow(settings, 'changed::voice', 'Writing down what you say', STT_CHOICES,
            () => settings.voice.stt, (id: SttChoice) => settings.setVoice('stt', id));
        const wake = toggle(settings, 'Listen for “Hey Mei”',
            'The microphone stays on. Slower to react than the shortcut, and it can wake on similar words.', 'wake_word');
        const bargeIn = toggle(settings, 'Interrupt by talking',
            'Talk over Mei to stop it. Works with earphones; with speakers, press the shortcut instead.', 'barge_in');
        for (const r of [stt, wake, bargeIn]) {
            listening.add(r.row);
            this._parts.push(r);
        }
        prefs.add(listening);

        const speaking = new Adw.PreferencesGroup({ title: 'Speaking' });
        const out = toggle(settings, 'Answer out loud', 'When you talk to Mei, it answers by voice too', 'speak_replies');
        const tts = choiceRow(settings, 'changed::voice', 'Voice', TTS_CHOICES, () => settings.voice.tts,
            (id: TtsChoice) => settings.setVoice('tts', id));
        for (const r of [out, tts]) {
            speaking.add(r.row);
            this._parts.push(r);
        }
        prefs.add(speaking);
        prefs.add(models);
        prefs.add(checks);

        const view = new Adw.ToolbarView({ content: prefs });
        view.add_top_bar(new Adw.HeaderBar());
        this.page = new Adw.NavigationPage({ title: 'Voice', child: view, tag: 'voice' });
    }

    destroy(): void {
        for (const part of this._parts) part.destroy();
    }
}

function toggle(settings: RuntimeSettings, title: string, subtitle: string,
    field: 'speak_replies' | 'barge_in' | 'wake_word'): Row<Adw.SwitchRow> {
    return switchRow(settings, 'changed::voice', title, subtitle, () => settings.voice[field],
        on => settings.setVoice(field, on));
}
