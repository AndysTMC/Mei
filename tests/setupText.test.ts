import assert from 'node:assert/strict';
import test from 'node:test';

import {
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
    assert.deepEqual(SETUP_STEPS.map(s => s.id), ['service', 'models', 'privacy', 'shortcuts']);
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
