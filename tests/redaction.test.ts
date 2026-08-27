import assert from 'node:assert/strict';
import test from 'node:test';

import { redactSensitiveText } from '../src/utils/redaction.js';

test('redactSensitiveText removes URL, header, JSON, and userinfo credentials', () => {
    const secret = 'mei-super-secret-token';
    const input = [
        `https://user:${secret}@example.test/chat?api_key=${secret}&safe=yes`,
        `Authorization: Bearer ${secret}`,
        `x-api-key=${secret}`,
        `{"access_token":"${secret}","safe":"visible"}`,
    ].join('\n');

    const output = redactSensitiveText(input);
    assert.doesNotMatch(output, new RegExp(secret));
    assert.match(output, /https:\/\/\*\*\*@example\.test\/chat\?api_key=\*\*\*&safe=yes/);
    assert.match(output, /Authorization: \*\*\*/);
    assert.match(output, /"access_token":"\*\*\*"/);
    assert.match(output, /"safe":"visible"/);
});

test('redactSensitiveText leaves ordinary provider diagnostics intact', () => {
    assert.equal(
        redactSensitiveText('POST https://example.test/v1/chat model=demo status=429'),
        'POST https://example.test/v1/chat model=demo status=429'
    );
});
