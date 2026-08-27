import assert from 'node:assert/strict';
import test from 'node:test';

import {
    createTokenUsage,
    getNumberAtPath,
    getStringAtPath,
    getTextContentAtPath,
    mergeTokenUsage,
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
    assert.equal(getStringAtPath(null, ['anything']), null);
    assert.equal(getStringAtPath(root, []), null);

    assert.equal(getNumberAtPath(root, ['choices', 0, 'message', 'tokens']), 42);
    assert.equal(getNumberAtPath(root, ['choices', 0, 'message', 'invalidNumber']), null);
    assert.equal(getNumberAtPath(root, ['choices', 'bad', 'message']), null);
    assert.equal(getNumberAtPath(root, ['choices', -1]), null);
});

test('getTextContentAtPath accepts string and typed text-part responses', () => {
    assert.equal(
        getTextContentAtPath({ message: { content: 'plain' } }, ['message', 'content']),
        'plain'
    );
    assert.equal(
        getTextContentAtPath({
            message: {
                content: [
                    { type: 'text', text: 'hello ' },
                    { type: 'citation', sources: [] },
                    { type: 'text', text: 'world' },
                ],
            },
        }, ['message', 'content']),
        'hello world'
    );
    assert.equal(getTextContentAtPath({ message: { content: [] } }, ['message', 'content']), null);
    assert.equal(getTextContentAtPath({ message: { content: [{ text: 42 }] } }, ['message', 'content']), null);
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
    assert.deepEqual(createTokenUsage(0, 0, 0), { inputTokens: 0, outputTokens: 0, totalTokens: 0 });
    assert.deepEqual(createTokenUsage(-1, 4.9, Number.NaN), {
        outputTokens: 4,
    });
});

test('mergeTokenUsage preserves counters reported in separate stream events', () => {
    assert.deepEqual(
        mergeTokenUsage(
            { inputTokens: 3 },
            { outputTokens: 4 }
        ),
        { inputTokens: 3, outputTokens: 4, totalTokens: 7 }
    );
    assert.equal(mergeTokenUsage(undefined, undefined), undefined);
    assert.deepEqual(mergeTokenUsage({ inputTokens: 1 }, undefined), { inputTokens: 1 });
    assert.deepEqual(mergeTokenUsage(undefined, { outputTokens: 2 }), { outputTokens: 2 });
    assert.deepEqual(
        mergeTokenUsage({ inputTokens: 1, totalTokens: 9 }, { outputTokens: 2 }),
        { inputTokens: 1, outputTokens: 2, totalTokens: 9 }
    );
});

test('parseJsonObject accepts only JSON objects', () => {
    assert.deepEqual(parseJsonObject('{"ok":true}'), { ok: true });
    assert.equal(parseJsonObject('[1,2,3]'), null);
    assert.equal(parseJsonObject('"text"'), null);
    assert.equal(parseJsonObject('null'), null);
    assert.equal(parseJsonObject('42'), null);
    assert.equal(parseJsonObject('not json'), null);
});
