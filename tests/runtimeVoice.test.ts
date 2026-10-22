import assert from 'node:assert/strict';
import test from 'node:test';

import { voiceLine } from '../src/runtime/voice.js';

test('the voice bar shows while Mei listens, thinks, or speaks, and offers Stop when it can', () => {
    assert.deepEqual(voiceLine({ state: 'listening', note: '', transcript: 'turn on dark' }),
        { visible: true, status: 'Listening…', transcript: 'turn on dark', stoppable: true });
    assert.deepEqual(voiceLine({ state: 'thinking', note: '', transcript: 'turn on dark mode' }),
        { visible: true, status: 'Thinking…', transcript: 'turn on dark mode', stoppable: false });
    assert.equal(voiceLine({ state: 'speaking', note: '', transcript: 'x' }).transcript, '');
    assert.equal(voiceLine({ state: 'speaking', note: '', transcript: '' }).stoppable, true);
});

test('idle and off are invisible; unavailable says why', () => {
    assert.equal(voiceLine({ state: 'idle', note: '', transcript: '' }).visible, false);
    assert.equal(voiceLine({ state: 'off', note: '', transcript: '' }).visible, false);
    assert.equal(voiceLine({ state: 'unavailable', note: 'download the voice models first', transcript: '' }).status,
        'Voice isn\'t available: download the voice models first');
});
