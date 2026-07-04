import assert from 'node:assert/strict';
import test from 'node:test';

import { buildAnthropicMessagesBody } from '../src/providers/anthropicPayload.js';
import { buildGeminiContentBody } from '../src/providers/geminiPayload.js';
import { buildDeepSeekChatBody, buildOpenAIChatBody } from '../src/providers/openaiPayload.js';
import type { ChatMessage } from '../src/providers/types.js';

const messages: ChatMessage[] = [
    { role: 'system', content: 'Be concise' },
    { role: 'user', content: 'Hello' },
    { role: 'assistant', content: 'Hi', thinking: 'hidden' },
];

test('buildOpenAIChatBody keeps chat roles and strips local-only fields', () => {
    assert.deepEqual(buildOpenAIChatBody('gpt-test', messages), {
        model: 'gpt-test',
        messages: [
            { role: 'system', content: 'Be concise' },
            { role: 'user', content: 'Hello' },
            { role: 'assistant', content: 'Hi' },
        ],
    });
});

test('buildDeepSeekChatBody adds thinking settings only when configured', () => {
    assert.deepEqual(buildDeepSeekChatBody('deepseek-test', messages, 'default', 'medium'), {
        model: 'deepseek-test',
        messages: [
            { role: 'system', content: 'Be concise' },
            { role: 'user', content: 'Hello' },
            { role: 'assistant', content: 'Hi' },
        ],
    });
    assert.deepEqual(buildDeepSeekChatBody('deepseek-test', messages, 'enabled', 'high').thinking, {
        type: 'enabled',
        reasoning_effort: 'high',
    });
    assert.deepEqual(buildDeepSeekChatBody('deepseek-test', messages, 'disabled', 'low').thinking, {
        type: 'disabled',
    });
});

test('buildGeminiContentBody maps assistant to model and separates system instructions', () => {
    assert.deepEqual(buildGeminiContentBody(messages), {
        contents: [
            { role: 'user', parts: [{ text: 'Hello' }] },
            { role: 'model', parts: [{ text: 'Hi' }] },
        ],
        systemInstruction: { parts: [{ text: 'Be concise' }] },
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
        system: 'Be concise',
    });
});
