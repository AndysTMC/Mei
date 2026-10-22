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

import type {
    SttChoice, TtsChoice, VoiceDevicesReply, VoiceModelsReply, VoiceOption,
} from '../runtime/protocol.js';
import type { RuntimeSettings } from '../runtime/settings.js';
import {
    deviceOptions, micText, modelLine, STT_CHOICES, TTS_CHOICES, voiceIdOf, voiceStatusText,
} from './setupText.js';
import { choiceRow, switchRow, type Row } from './rows.js';

const POLL_MS = 500;
const SETTLE_MS = 600;

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
        getAll.set_css_classes(missing.length ? ['suggested-action'] : []);
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

        let voices: Partial<Record<TtsChoice, VoiceOption[]>> = {};
        let devices: VoiceDevicesReply = { mics: [], outputs: [] };
        const v = () => settings.voice;

        const listening = new Adw.PreferencesGroup({ title: 'Listening' });
        const stt = choiceRow(settings, 'changed::voice', 'Writing down what you say', STT_CHOICES,
            () => v().stt, (id: SttChoice) => settings.setVoice('stt', id));
        const mic = listRow(settings, 'Microphone', () => deviceOptions(devices.mics, v().mic), () => v().mic,
            id => settings.setVoice('mic', id));
        const pause = numberRow(settings, 'Pause before Mei answers', 'Seconds of quiet that mean you’ve finished',
            [0.3, 2.0, 0.1], () => v().end_silence_ms / 1000, s => settings.setVoice('end_silence_ms', Math.round(s * 1000)));
        const wake = toggle(settings, 'Listen for “Hey Mei”',
            'The microphone stays on. Slower to react than the shortcut, and it can wake on similar words.', 'wake_word');
        const bargeIn = toggle(settings, 'Interrupt by talking',
            'Talk over Mei to stop it. Works with earphones; with speakers, press the shortcut instead.', 'barge_in');
        for (const r of [stt, mic, pause, wake, bargeIn]) {
            listening.add(r.row);
            this._parts.push(r);
        }
        prefs.add(listening);

        const speaking = new Adw.PreferencesGroup({ title: 'Speaking' });
        const out = toggle(settings, 'Answer out loud', 'When you talk to Mei, it answers by voice too', 'speak_replies');
        const tts = choiceRow(settings, 'changed::voice', 'Speaking with', TTS_CHOICES, () => v().tts,
            (id: TtsChoice) => settings.setVoice('tts', id));
        const who = listRow(settings, 'Voice', () => voices[v().tts] ?? [], () => voiceIdOf(v()),
            id => chooseVoice(settings, id));
        const speed = numberRow(settings, 'Speed', '1 is normal', [0.5, 2.0, 0.1], () => v().speed,
            s => settings.setVoice('speed', s));
        const output = listRow(settings, 'Speaker', () => deviceOptions(devices.outputs, v().output), () => v().output,
            id => settings.setVoice('output', id));
        for (const r of [out, tts, who, speed, output]) {
            speaking.add(r.row);
            this._parts.push(r);
        }
        prefs.add(speaking);
        prefs.add(models);
        prefs.add(checks);

        settings.voiceModels().then(reply => {
            voices = reply.voices;
            who.render();
        }).catch(e => who.row.set_subtitle(`Couldn’t list voices: ${e instanceof Error ? e.message : String(e)}`));
        settings.voiceDevices().then(reply => {
            devices = reply;
            mic.render();
            output.render();
        }).catch(e => {
            const why = `Couldn’t list devices: ${e instanceof Error ? e.message : String(e)}`;
            mic.row.set_subtitle(why);
            output.row.set_subtitle(why);
        });

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

function chooseVoice(settings: RuntimeSettings, id: string): void {
    const tts = settings.voice.tts;
    if (tts === 'piper') settings.setVoice('voice', id);
    else if (tts === 'kokoro') settings.setVoice('kokoro_speaker', Number(id));
    else settings.setVoice('cloud_voice', id);
}

/** A choice whose options can change: the voices of the chosen speech, the devices plugged in. */
function listRow(settings: RuntimeSettings, title: string, options: () => VoiceOption[], current: () => string,
    choose: (id: string) => void): Row<Adw.ComboRow> & { render(): void } {
    const labels = new Gtk.StringList();
    const row = new Adw.ComboRow({ title, model: labels });
    let shown: VoiceOption[] = [];
    let updating = false;
    const render = () => {
        updating = true;
        shown = options();
        labels.splice(0, labels.get_n_items(), shown.map(o => o.label));
        row.set_selected(Math.max(0, shown.findIndex(o => o.id === current())));
        updating = false;
    };
    row.connect('notify::selected', () => {
        const option = shown[row.get_selected()];
        if (!updating && option && option.id !== current()) choose(option.id);
    });
    const id = settings.connect('changed::voice', render);
    render();
    return { row, render, destroy: () => settings.disconnect(id) };
}

/** A number, written back once it stops changing (each change reloads the voice worker). */
function numberRow(settings: RuntimeSettings, title: string, subtitle: string, [min, max, step]: [number, number, number],
    current: () => number, choose: (value: number) => void): Row<Adw.SpinRow> {
    const row = Adw.SpinRow.new_with_range(min, max, step);
    row.set_title(title);
    row.set_subtitle(subtitle);
    row.set_digits(1);
    let updating = false;
    let pending = 0;
    const render = () => {
        updating = true;
        row.set_value(current());
        updating = false;
    };
    row.connect('notify::value', () => {
        if (updating) return;
        if (pending) GLib.source_remove(pending);
        pending = GLib.timeout_add(GLib.PRIORITY_DEFAULT, SETTLE_MS, () => {
            pending = 0;
            choose(Math.round(row.get_value() * 10) / 10);
            return GLib.SOURCE_REMOVE;
        });
    });
    const id = settings.connect('changed::voice', render);
    render();
    return {
        row,
        destroy: () => {
            if (pending) GLib.source_remove(pending);
            settings.disconnect(id);
        },
    };
}
