import assert from 'node:assert/strict';
import test from 'node:test';

import {
    generateChatId,
    generateChatTitle,
    parseChatSessions,
} from '../src/utils/chatSession.js';

test('parseChatSessions keeps valid sessions and filters malformed entries', () => {
    const valid = {
        id: 'chat-1',
        title: 'Hello',
        createdAt: 1,
        updatedAt: 2,
        messages: [{
            role: 'assistant',
            content: 'Hi',
            thinking: 'checking',
            metadata: {
                providerId: 'openai',
                providerLabel: 'OpenAI',
                providerType: 'remote',
                model: 'gpt-test',
                endpoint: 'https://example.test',
                durationMs: 42,
                tokens: { inputTokens: 1, outputTokens: 2, totalTokens: 3 },
            },
        }],
    };

    assert.deepEqual(parseChatSessions([
        valid,
        { ...valid, id: 5 },
        { ...valid, createdAt: Number.NaN },
        { ...valid, messages: [{ ...valid.messages[0], metadata: { durationMs: Number.POSITIVE_INFINITY } }] },
        { ...valid, messages: [{ ...valid.messages[0], metadata: { tokens: { totalTokens: Number.NaN } } }] },
        { ...valid, messages: [{ role: 'tool', content: 'bad' }] },
        { ...valid, messages: [{ role: 'user', content: 'bad', metadata: [] }] },
    ]), [valid]);
});

test('generateChatTitle uses the first user message and truncates long titles', () => {
    assert.equal(generateChatTitle([{ role: 'assistant', content: 'No user' }]), 'New Chat');
    assert.equal(generateChatTitle([{ role: 'user', content: '    ' }]), 'New Chat');
    assert.equal(generateChatTitle([{ role: 'user', content: '  Short title  ' }]), 'Short title');
    assert.equal(
        generateChatTitle([{ role: 'user', content: '1234567890123456789012345678901234567890extra' }]),
        '1234567890123456789012345678901234567890\u2026'
    );
});

test('generateChatId returns timestamp-prefixed random ids', () => {
    assert.match(generateChatId(), /^[a-z0-9]+-[a-z0-9]{6}$/);
});
