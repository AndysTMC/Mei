import assert from 'node:assert/strict';
import test from 'node:test';

import {
    generateChatId,
    generateChatTitle,
    MAX_CHAT_MESSAGE_CHARS,
    MAX_CHAT_MESSAGES_PER_SESSION,
    MAX_CHAT_SESSIONS,
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
        { ...valid, updatedAt: -1 },
        { ...valid, createdAt: Number.NaN },
        { ...valid, messages: [{ ...valid.messages[0], metadata: { durationMs: Number.POSITIVE_INFINITY } }] },
        { ...valid, messages: [{ ...valid.messages[0], metadata: { tokens: { totalTokens: Number.NaN } } }] },
        { ...valid, messages: [{ role: 'tool', content: 'bad' }] },
        { ...valid, messages: [{ role: 'user', content: 'bad', metadata: [] }] },
    ]), [valid]);
    assert.deepEqual(parseChatSessions(null), []);
    assert.deepEqual(parseChatSessions({}), []);
});

test('parseChatSessions accepts every supported message role and optional metadata', () => {
    const session = {
        id: 'all-roles',
        title: '',
        createdAt: 0,
        updatedAt: 1,
        messages: [
            { role: 'system', content: 'system' },
            { role: 'user', content: 'user', thinking: '' },
            { role: 'assistant', content: 'assistant', metadata: {} },
        ],
    };
    assert.deepEqual(parseChatSessions([session]), [session]);
});

test('parseChatSessions deduplicates ids and bounds persisted workloads', () => {
    const makeSession = (id: string) => ({
        id,
        title: id,
        createdAt: 1,
        updatedAt: 2,
        messages: [{ role: 'user', content: 'hello' }],
    });
    const duplicate = { ...makeSession('chat-0'), title: 'duplicate' };
    const sessions = Array.from({ length: MAX_CHAT_SESSIONS + 20 }, (_value, index) =>
        makeSession(`chat-${index}`)
    );

    const parsed = parseChatSessions([sessions[0], duplicate, ...sessions.slice(1)]);
    assert.equal(parsed.length, MAX_CHAT_SESSIONS);
    assert.equal(parsed[0].title, 'chat-0');
    assert.equal(parsed.filter(session => session.id === 'chat-0').length, 1);

    const tooManyMessages = {
        ...makeSession('too-many'),
        messages: Array.from({ length: MAX_CHAT_MESSAGES_PER_SESSION + 1 }, () => ({
            role: 'assistant',
            content: 'x',
        })),
    };
    const tooMuchContent = {
        ...makeSession('too-large'),
        messages: [{ role: 'assistant', content: 'x'.repeat(MAX_CHAT_MESSAGE_CHARS + 1) }],
    };
    assert.deepEqual(parseChatSessions([tooManyMessages, tooMuchContent]), []);
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
