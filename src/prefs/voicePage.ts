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
        subtitle: 'Press Live and talk; Mei answers out loud and keeps listening until you end it. Started with ' +
            'Super+Alt+Space, Live ends after 30 seconds of quiet. The mic button types what you say until you press it again.' });
    const status = new Adw.ActionRow({ title: 'Status', subtitle: 'Checking…' });
    voice.add(enabled);
    voice.add(status);

    const models = new Adw.PreferencesGroup({ title: 'On this computer',
        description: 'Voice runs on this computer. These are downloaded once, from the models’ publisher, and checked.' });
    const getAll = new Gtk.Button({ label: 'Download', valign: Gtk.Align.CENTER, css_classes: ['suggested-action'] });
    models.set_header_suffix(getAll);
    // Each model's row, with Download (needed or offered) or Remove (not needed) on it.
    const modelRows = new Map<string, { row: Adw.ActionRow; action: Gtk.Button; act: 'download' | 'remove' | '' }>();

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

    const modelRow = (id: string, part: string) => {
        const row = new Adw.ActionRow({ title: part.charAt(0).toUpperCase() + part.slice(1) });
        const action = new Gtk.Button({ valign: Gtk.Align.CENTER, visible: false });
        row.add_suffix(action);
        const entry = { row, action, act: '' as 'download' | 'remove' | '' };
        action.connect('clicked', () => {
            action.set_sensitive(false);
            const done = entry.act === 'remove' ? settings.removeVoiceModels([id]) : settings.downloadVoiceModels([id]);
            done.then(() => refresh()).catch(fail).finally(() => action.set_sensitive(true));
        });
        modelRows.set(id, entry);
        models.add(row);
        return entry;
    };

    const show = (reply: VoiceModelsReply) => {
        status.set_subtitle(voiceStatusText(reply.state, reply.note));
        for (const m of reply.models) {
            const entry = modelRows.get(m.id) ?? (m.needed || m.have || m.offered ? modelRow(m.id, m.part) : null);
            if (!entry) continue;
            entry.row.set_visible(m.needed || m.have || m.offered);
            entry.row.set_subtitle(modelLine(m));
            entry.act = !m.have && !reply.downloading ? 'download' : m.have && !m.needed ? 'remove' : '';
            entry.action.set_label(entry.act === 'remove' ? 'Remove' : 'Download');
            entry.action.set_visible(entry.act !== '');
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
        // 0.8 s by default, as voice assistants do; longer by itself after "and…", "um…" (decision 0028).
        const pause = numberRow(settings, 'Pause before Mei answers',
            'Seconds of quiet before what you said is sent. Mei waits longer when you stop mid-sentence. '
            + 'Press the shortcut or Live again to send at once.',
            [0.3, 10.0, 0.1, 1], () => v().end_pause_ms / 1000, s => settings.setVoice('end_pause_ms', Math.round(s * 1000)));
        const wake = toggle(settings, 'Listen for “Hey Mei”',
            'The microphone stays on. Slower to react than the shortcut, and it can wake on similar words.', 'wake_word');
        // Another app recording (a call, a recorder) has the microphone to itself (decisions 0025, 0026).
        const appsPause = toggle(settings, 'Pause while another app records',
            'During calls and recordings Mei lets go of the microphone, and listens again after. The shortcut still ' +
            'works.', 'pause_for_apps');
        const bargeIn = toggle(settings, 'Interrupt by talking', 'Talk over Mei to stop it. Quickest with earphones.',
            'barge_in');
        // With speakers, PipeWire's echo canceller while Mei talks (decision 0024); not used with earphones.
        const echo = toggle(settings, 'Cancel echo from speakers',
            'While Mei talks through speakers, its voice is taken out of what the microphone hears, using a little ' +
            'processor time. Slower to react than earphones, and an echoey room can still stop Mei.', 'echo_cancel');
        for (const r of [stt, mic, pause, wake, appsPause, bargeIn, echo]) {
            listening.add(r.row);
            this._parts.push(r);
        }
        prefs.add(listening);

        // Names the recognizer has never heard, put back where something close was (decision 0029).
        const words = new Adw.PreferencesGroup({ title: 'Words Mei listens for',
            description: 'Names Mei might mishear. Where it hears something close, it writes the name instead.' });
        const yours = new Adw.EntryRow({ title: 'Your words, separated by commas', show_apply_button: true });
        const known = new Adw.ActionRow({ title: 'Also listens for', subtitle: 'Checking…', subtitle_lines: 3 });
        const showYours = () => yours.set_text(v().boost_words.join(', '));
        yours.connect('apply', () => settings.setVoice('boost_words',
            [...new Set(yours.get_text().split(',').map(w => w.trim()).filter(Boolean))].slice(0, 200)));
        words.add(yours);
        words.add(known);
        prefs.add(words);
        showYours();
        const wordsSignal = settings.connect('changed::voice', showYours);
        this._parts.push({ destroy: () => settings.disconnect(wordsSignal) });
        const showDependent = () => echo.row.set_visible(v().barge_in);
        const dependentSignal = settings.connect('changed::voice', showDependent);
        this._parts.push({ destroy: () => settings.disconnect(dependentSignal) });
        showDependent();

        const speaking = new Adw.PreferencesGroup({ title: 'Speaking' });
        const out = toggle(settings, 'Answer out loud', 'When you talk to Mei, it answers by voice too', 'speak_replies');
        const tts = choiceRow(settings, 'changed::voice', 'Speaking with', TTS_CHOICES, () => v().tts,
            (id: TtsChoice) => settings.setVoice('tts', id));
        const who = listRow(settings, 'Voice', () => voices[v().tts] ?? [], () => voiceIdOf(v()),
            id => chooseVoice(settings, id));
        const speed = numberRow(settings, 'Speed', '1 is normal', [0.5, 2.0, 0.1, 1], () => v().speed,
            s => settings.setVoice('speed', s));
        // The natural voice on the GPU, on demand (decision 0019): only with an NVIDIA GPU.
        const gpu = switchRow(settings, 'changed::voice', 'Use the graphics card',
            'Starts speaking about a second sooner. The card wakes while you talk to Mei and sleeps when it’s unused.',
            () => v().device !== 'cpu', on => settings.setVoice('device', on ? 'auto' : 'cpu'));
        const sleep = numberRow(settings, 'Let it sleep after', 'Minutes unused', [1, 60, 1, 0], () => v().gpu_idle_min,
            m => settings.setVoice('gpu_idle_min', m));
        const output = listRow(settings, 'Speaker', () => deviceOptions(devices.outputs, v().output), () => v().output,
            id => settings.setVoice('output', id));
        for (const r of [out, tts, who, speed, gpu, sleep, output]) {
            speaking.add(r.row);
            this._parts.push(r);
        }
        prefs.add(speaking);
        prefs.add(models);
        prefs.add(checks);

        let hasGpu = false;
        const showGpu = () => {
            gpu.row.set_visible(hasGpu && v().tts === 'kokoro');
            sleep.row.set_visible(hasGpu && v().tts === 'kokoro' && v().device !== 'cpu');
        };
        const gpuSignal = settings.connect('changed::voice', showGpu);
        this._parts.push({ destroy: () => settings.disconnect(gpuSignal) });
        showGpu();
        settings.voiceModels().then(reply => {
            known.set_subtitle(boostText(reply.boost));
            voices = reply.voices;
            hasGpu = reply.gpu;
            who.render();
            showGpu();
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
    field: 'speak_replies' | 'barge_in' | 'echo_cancel' | 'wake_word' | 'pause_for_apps'): Row<Adw.SwitchRow> {
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
function numberRow(settings: RuntimeSettings, title: string, subtitle: string,
    [min, max, step, digits]: [number, number, number, number], current: () => number,
    choose: (value: number) => void): Row<Adw.SpinRow> {
    const row = Adw.SpinRow.new_with_range(min, max, step);
    row.set_title(title);
    row.set_subtitle(subtitle);
    row.set_digits(digits);
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


/** "Names from your chats: Mukesh, Anjali · 42 app names" */
export function boostText(boost: { apps: string[]; learned: string[] } | undefined): string {
    if (!boost) return 'Nothing yet';
    const parts = [];
    if (boost.learned.length) {
        const shown = boost.learned.slice(0, 8).join(', ');
        parts.push(`Names from your chats and memories: ${shown}${boost.learned.length > 8 ? '…' : ''}`);
    }
    if (boost.apps.length) parts.push(`${boost.apps.length} app ${boost.apps.length === 1 ? 'name' : 'names'}`);
    return parts.join(' · ') || 'Nothing yet';
}
