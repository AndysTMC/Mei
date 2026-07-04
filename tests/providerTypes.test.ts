import assert from 'node:assert/strict';
import test from 'node:test';

import {
    createTokenUsage,
    getNumberAtPath,
    getStringAtPath,
    parseJsonObject,
    toApiMessages,
    type ChatMessage,
} from '../src/providers/types.ts';

test('getStringAtPath and getNumberAtPath traverse objects and arrays safely', () => {
    const root = {
        choices: [
            {
                message: {
                    content: 'hello',
                    tokens: 42,
                    invalidNumber: Number.POSITIVE_INFINITY,
                },
            },
        ],
    };

    assert.equal(getStringAtPath(root, ['choices', 0, 'message', 'content']), 'hello');
    assert.equal(getStringAtPath(root, ['choices', 0, 'message', 'tokens']), null);
    assert.equal(getStringAtPath(root, ['choices', 1, 'message', 'content']), null);

    assert.equal(getNumberAtPath(root, ['choices', 0, 'message', 'tokens']), 42);
    assert.equal(getNumberAtPath(root, ['choices', 0, 'message', 'invalidNumber']), null);
    assert.equal(getNumberAtPath(root, ['choices', 'bad', 'message']), null);
});

test('toApiMessages strips local-only metadata fields', () => {
    const messages: ChatMessage[] = [
        {
            role: 'user',
            content: 'hello',
            thinking: 'private',
            metadata: { providerLabel: 'Test' },
        },
        {
            role: 'assistant',
            content: 'hi',
        },
    ];

    assert.deepEqual(toApiMessages(messages), [
        { role: 'user', content: 'hello' },
        { role: 'assistant', content: 'hi' },
    ]);
});

test('createTokenUsage computes totals only when useful', () => {
    assert.deepEqual(createTokenUsage(3, 4, null), {
        inputTokens: 3,
        outputTokens: 4,
        totalTokens: 7,
    });
    assert.deepEqual(createTokenUsage(3, null, 10), {
        inputTokens: 3,
        totalTokens: 10,
    });
    assert.equal(createTokenUsage(null, null, null), undefined);
});

test('parseJsonObject accepts only JSON objects', () => {
    assert.deepEqual(parseJsonObject('{"ok":true}'), { ok: true });
    assert.equal(parseJsonObject('[1,2,3]'), null);
    assert.equal(parseJsonObject('"text"'), null);
    assert.equal(parseJsonObject('not json'), null);
});
