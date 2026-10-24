import assert from 'node:assert/strict';
import test from 'node:test';

import { dictated, voiceLine } from '../src/runtime/voice.js';

test('the voice bar shows while Mei listens, thinks, or speaks, and offers Stop when it can', () => {
    assert.deepEqual(voiceLine({ state: 'listening', note: '', transcript: 'turn on dark' }),
        { visible: true, status: 'Listening…', transcript: 'turn on dark', stoppable: true });
    assert.deepEqual(voiceLine({ state: 'thinking', note: '', transcript: 'turn on dark mode' }),
        { visible: true, status: 'Thinking…', transcript: 'turn on dark mode', stoppable: false });
    assert.equal(voiceLine({ state: 'speaking', note: '', transcript: 'x' }).transcript, '');
    assert.equal(voiceLine({ state: 'speaking', note: '', transcript: '', dictating: false }).stoppable, true);
});

test('idle and off are invisible; unavailable says why', () => {
    assert.equal(voiceLine({ state: 'idle', note: '', transcript: '', dictating: false }).visible, false);
    assert.equal(voiceLine({ state: 'off', note: '', transcript: '', dictating: false }).visible, false);
    assert.equal(voiceLine({ state: 'unavailable', note: 'download the voice models first', transcript: '', dictating: false }).status,
        'Voice isn\'t available: download the voice models first');
});

test('while another app records, the bar says Mei is paused and can still be closed', () => {
    assert.deepEqual(voiceLine({ state: 'paused', note: '', transcript: '', dictating: false }),
        { visible: true, status: 'Paused while another app uses the microphone', transcript: '', stoppable: true });
});

test('dictation adds each utterance after the last, across pauses, and keeps what was typed', () => {
    let base = 'Buy ';
    let step = dictated(base, 'milk', false);
    assert.equal(step.shown, 'Buy milk');
    base = dictated(base, 'milk and eggs', true).base;  // a pause: that utterance is done
    step = dictated(base, 'and bread', false);
    assert.equal(step.shown, 'Buy milk and eggs and bread');
    assert.equal(dictated(base, '', true).base, base);  // a cough: nothing added
});
