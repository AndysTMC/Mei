import assert from 'node:assert/strict';
import test from 'node:test';

import { buildAnthropicMessagesBody } from '../src/providers/anthropicPayload.js';
import { buildGeminiContentBody, buildGeminiGenerateUrl } from '../src/providers/geminiPayload.js';
import { buildDeepSeekChatBody, buildOpenAIChatBody } from '../src/providers/openaiPayload.js';
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

test('buildDeepSeekChatBody uses the documented top-level thinking controls', () => {
    assert.deepEqual(buildDeepSeekChatBody('deepseek-v4-pro', messages, 'default', 'high'), {
        model: 'deepseek-v4-pro',
        messages: [
            { role: 'system', content: 'Be concise' },
            { role: 'system', content: 'Use plain language' },
            { role: 'user', content: 'Hello' },
            { role: 'assistant', content: 'Hi' },
        ],
    });
    assert.deepEqual(buildDeepSeekChatBody('deepseek-v4-pro', messages, 'enabled', 'max'), {
        model: 'deepseek-v4-pro',
        messages: [
            { role: 'system', content: 'Be concise' },
            { role: 'system', content: 'Use plain language' },
            { role: 'user', content: 'Hello' },
            { role: 'assistant', content: 'Hi' },
        ],
        thinking: { type: 'enabled' },
        reasoning_effort: 'max',
    });
    assert.deepEqual(buildDeepSeekChatBody('deepseek-v4-flash', messages, 'disabled', 'low'), {
        model: 'deepseek-v4-flash',
        messages: [
            { role: 'system', content: 'Be concise' },
            { role: 'system', content: 'Use plain language' },
            { role: 'user', content: 'Hello' },
            { role: 'assistant', content: 'Hi' },
        ],
        thinking: { type: 'disabled' },
    });
    assert.deepEqual(
        buildDeepSeekChatBody('deepseek-v3-legacy', messages, 'enabled', 'max'),
        buildOpenAIChatBody('deepseek-v3-legacy', messages)
    );
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

test('buildGeminiGenerateUrl keeps model ids inside the path segment', () => {
    assert.equal(
        buildGeminiGenerateUrl('https://example.test/v1beta/', 'models/demo?key=leak', false),
        'https://example.test/v1beta/models/models%2Fdemo%3Fkey%3Dleak:generateContent'
    );
    assert.equal(
        buildGeminiGenerateUrl('https://example.test/v1beta', 'gemini-3.1-flash', true),
        'https://example.test/v1beta/models/gemini-3.1-flash:streamGenerateContent?alt=sse'
    );
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
