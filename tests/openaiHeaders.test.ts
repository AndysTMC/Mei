import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildBearerHeaders,
    buildFireworksHeaders,
    buildNvidiaHeaders,
} from '../src/providers/openaiHeaders.js';

test('OpenAI-compatible provider headers preserve auth and reference attribution', () => {
    assert.deepEqual(buildBearerHeaders('secret'), {
        Authorization: 'Bearer secret',
    });
    assert.deepEqual(buildBearerHeaders(''), {});
    assert.deepEqual(buildFireworksHeaders('secret'), {
        Authorization: 'Bearer secret',
        'HTTP-Referer': 'https://github.com/AndysTMC/Mei',
        'X-Title': 'Mei',
    });
    assert.deepEqual(buildNvidiaHeaders('secret'), {
        Authorization: 'Bearer secret',
        'X-BILLING-INVOKE-ORIGIN': 'Mei',
    });
});
