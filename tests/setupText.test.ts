import assert from 'node:assert/strict';
import test from 'node:test';

import {
    APPROVAL_FLOOR,
    APPROVAL_PRESETS,
    CLOUD_FILES,
    doneText,
    formatBytes,
    homeRelative,
    modelsText,
    retentionLabel,
    retentionOptions,
    retentionShrinks,
    SETUP_STEPS,
    storageText,
    testText,
} from '../src/prefs/setupText.js';
import type { ModelsStep, ServiceStep } from '../src/runtime/protocol.js';

test('setup steps: the service step comes first and is the only one that cannot be skipped', () => {
    assert.deepEqual(SETUP_STEPS.map(s => s.id), ['service', 'models', 'approvals', 'memory', 'voice', 'privacy', 'shortcuts']);
    assert.deepEqual(SETUP_STEPS.filter(s => !s.skippable).map(s => s.id), ['service']);
});

test('retention choices default to keeping everything and keep a custom value visible', () => {
    assert.equal(retentionLabel(null), 'Keep until I delete them');
    assert.equal(retentionLabel(7), 'After a week');
    assert.equal(retentionLabel(45), 'After 45 days');
    assert.equal(retentionLabel(1), 'After a day');
    assert.deepEqual(retentionOptions(null), [null, 7, 30, 90, 365]);
    assert.deepEqual(retentionOptions(45), [null, 7, 30, 45, 90, 365]);
    assert.deepEqual(retentionOptions(1000), [null, 7, 30, 90, 365, 1000]);
});

test('only a shorter retention asks before deleting', () => {
    assert.equal(retentionShrinks(null, 30), true);
    assert.equal(retentionShrinks(90, 30), true);
    assert.equal(retentionShrinks(30, 90), false);
    assert.equal(retentionShrinks(30, null), false);
    assert.equal(retentionShrinks(30, 30), false);
});

test('sizes and paths read naturally', () => {
    assert.equal(formatBytes(0), '0 B');
    assert.equal(formatBytes(999), '999 B');
    assert.equal(formatBytes(1_234_567), '1.2 MB');
    assert.equal(formatBytes(80_000_000_000), '80 GB');
    assert.equal(homeRelative('/home/u/.local/share/mei', '/home/u'), '~/.local/share/mei');
    assert.equal(homeRelative('/home/user2/mei', '/home/u'), '/home/user2/mei');
    const service: ServiceStep = { id: 'service', state: 'done', runtime_version: '0.1.0', keyring: 'unlocked',
        data_dir: '/home/u/.local/share/mei', data_bytes: 12_300_000, free_bytes: 80_000_000_000 };
    assert.equal(storageText(service, '/home/u'), '~/.local/share/mei · 12 MB used · 80 GB free');
});

test('the models step says what is missing', () => {
    const base: ModelsStep = { id: 'models', state: 'todo', provider: '', label: '', model: '', requires_key: false, has_key: null };
    assert.equal(modelsText(base), 'No model chosen yet');
    assert.equal(modelsText({ ...base, provider: 'gemini', label: 'Gemini' }), 'Gemini · choose a model');
    assert.equal(modelsText({ ...base, provider: 'gemini', label: 'Gemini', model: 'g-1', requires_key: true, has_key: false }),
        'Gemini · g-1 · needs an API key');
    assert.equal(modelsText({ ...base, provider: 'ollama', label: 'Ollama', model: 'llama3', state: 'done' }), 'Ollama · llama3');
});

test('test results and the summary', () => {
    assert.equal(testText({ ok: true, reply: 'OK', ms: 1234 }), 'Answered in 1.2 s: “OK”');
    assert.equal(testText({ ok: false, error: 'Gemini: HTTP 401', ms: 300 }), "Didn't work: Gemini: HTTP 401");
    assert.equal(doneText([], 'Super+Alt+M'),
        'Open Mei from the top bar or with Super+Alt+M. You can change any of this later in Settings.');
    assert.equal(doneText(['shortcuts', 'models'], ''),
        'Open Mei from the top bar. You skipped Models and Shortcuts; set them up any time in Settings.');
});

test('approval presets and cloud-file choices: every option explained, labels short enough for a combo row', () => {
    assert.deepEqual(APPROVAL_PRESETS.map(p => p.id), ['cautious', 'balanced', 'hands_off']);
    assert.deepEqual(CLOUD_FILES.map(c => c.id), ['pointed', 'always', 'never']);
    for (const option of [...APPROVAL_PRESETS, ...CLOUD_FILES]) {
        assert.ok(option.label.length <= 17, option.label);
        assert.ok(option.description.endsWith('.'), option.description);
    }
    assert.match(APPROVAL_FLOOR, /always asks/);
});

test('voice: cloud choices say where the voice goes, and models and the microphone are described plainly', async () => {
    const { STT_CHOICES, TTS_CHOICES, micText, modelLine, voiceStatusText } = await import('../src/prefs/setupText.js');
    assert.equal(STT_CHOICES[0].id, 'local');
    for (const c of STT_CHOICES.slice(1)) assert.match(c.description, /What you say is sent to/);
    for (const c of TTS_CHOICES.filter(t => t.id === 'openai' || t.id === 'gemini')) assert.match(c.description, /sent to/);
    const m = { id: 'kroko', part: 'speech to text', size: 57_267_600, have: false, needed: true, offered: false };
    assert.equal(modelLine(m), '57 MB · needed');
    assert.equal(modelLine({ ...m, got: 28_633_800, total: 57_267_600 }), '57 MB · downloading 50%');
    assert.equal(modelLine({ ...m, have: true }), '57 MB · downloaded');
    assert.match(modelLine({ ...m, error: 'checksum' }), /couldn’t download: checksum/);
    const gpu = { ...m, id: 'gpu-engine', part: 'graphics card engine', size: 1_883_526_067, needed: false, offered: true };
    assert.equal(modelLine(gpu), '1.9 GB · optional');
    assert.match(micText({ db: -3.4, peak_db: 0, clipped_pct: 19.5, overdriven: true }), /^Too loud even in silence \(-3 dB, 19.5% clipped\)/);
    assert.equal(micText({ db: -29.5, peak_db: -12, clipped_pct: 0, overdriven: false }), 'Sounds right (-30 dB in silence)');
    assert.equal(voiceStatusText('unavailable', 'download the voice models first'), 'Not ready: download the voice models first');
});

test('voice: devices list the system default first and keep a chosen one that is unplugged', async () => {
    const { deviceOptions, voiceIdOf } = await import('../src/prefs/setupText.js');
    const mics = [{ name: 'alsa_input.usb', label: 'USB Microphone' }];
    assert.deepEqual(deviceOptions(mics, ''), [{ id: '', label: 'System default' }, { id: 'alsa_input.usb', label: 'USB Microphone' }]);
    assert.deepEqual(deviceOptions(mics, 'bluez_input.headset').at(-1), { id: 'bluez_input.headset', label: 'bluez_input.headset (not connected)' });
    const v = { tts: 'piper' as const, voice: 'lessac', kokoro_speaker: 7, cloud_voice: 'nova' };
    assert.equal(voiceIdOf(v), 'lessac');
    assert.equal(voiceIdOf({ ...v, tts: 'kokoro' }), '7');
    assert.equal(voiceIdOf({ ...v, tts: 'openai' }), 'nova');
});
