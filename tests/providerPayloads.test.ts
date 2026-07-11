import assert from 'node:assert/strict';
import test from 'node:test';

import { buildAnthropicMessagesBody } from '../src/providers/anthropicPayload.js';
import { buildGeminiContentBody } from '../src/providers/geminiPayload.js';
import { buildOpenAIChatBody } from '../src/providers/openaiPayload.js';
import type { ChatMessage } from '../src/providers/types.js';

const messages: ChatMessage[] = [
    { role: 'system', content: 'Be concise' },
    { role: 'system', content: 'Use plain language' },
    { role: 'user', content: 'Hello' },
    { role: 'assistant', content: 'Hi', thinking: 'hidden' },
];

test('buildOpenAIChatBody keeps chat roles and strips local-only fields', () => {
    assert.deepEqual(buildOpenAIChatBody('gpt-test', messages), {
        model: 'gpt-test',
        messages: [
            { role: 'system', content: 'Be concise' },
            { role: 'system', content: 'Use plain language' },
            { role: 'user', content: 'Hello' },
            { role: 'assistant', content: 'Hi' },
        ],
    });
});

test('buildGeminiContentBody maps assistant to model and separates system instructions', () => {
    assert.deepEqual(buildGeminiContentBody(messages), {
        contents: [
            { role: 'user', parts: [{ text: 'Hello' }] },
            { role: 'model', parts: [{ text: 'Hi' }] },
        ],
        systemInstruction: {
            parts: [{ text: 'Be concise' }, { text: 'Use plain language' }],
        },
    });
    assert.deepEqual(buildGeminiContentBody(messages, true).generationConfig, {
        thinkingConfig: { includeThoughts: true },
    });
});

test('buildAnthropicMessagesBody separates system prompt from messages', () => {
    assert.deepEqual(buildAnthropicMessagesBody('claude-test', messages), {
        model: 'claude-test',
        messages: [
            { role: 'user', content: 'Hello' },
            { role: 'assistant', content: 'Hi' },
        ],
        max_tokens: 4096,
        system: 'Be concise\n\nUse plain language',
    });
    assert.deepEqual(buildAnthropicMessagesBody('claude-test', messages, 4096, true).thinking, {
        type: 'adaptive',
        display: 'summarized',
    });
});

test('payload builders handle empty conversations and optional settings', () => {
    assert.deepEqual(buildOpenAIChatBody('', []), { model: '', messages: [] });
    assert.deepEqual(buildGeminiContentBody([], true), {
        contents: [],
        generationConfig: { thinkingConfig: { includeThoughts: true } },
    });
    assert.deepEqual(buildAnthropicMessagesBody('claude-test', [], 123), {
        model: 'claude-test',
        messages: [],
        max_tokens: 123,
    });
});
