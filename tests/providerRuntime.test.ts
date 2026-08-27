import assert from 'node:assert/strict';
import test from 'node:test';

import { getProviderProfile, resolveProviderId, resolveProviderRuntime } from '../src/providers/profiles.js';
import { parseResponsesResult } from '../src/providers/responsesPayload.js';

const config = { url: '', model: '', apiKey: '', mode: '' };

test('provider profiles centralize aliases, headers, auth, and fallbacks', () => {
    const openRouter = getProviderProfile('openrouter');
    assert.equal(openRouter.modelAuthRequired, false);
    assert.equal(openRouter.modelsUrl, 'https://openrouter.ai/api/v1/models');
    assert.equal(openRouter.headers?.['X-Title'], 'Mei');
    assert.ok((openRouter.fallbackModels?.length ?? 0) > 0);
    assert.equal(resolveProviderId('or'), 'openrouter');
});

test('OpenCode runtime selects the correct API surface by model family', () => {
    assert.deepEqual(resolveProviderRuntime('opencode', {
        ...config,
        model: 'grok-5-future',
        mode: 'zen',
    }), {
        apiMode: 'responses',
        url: 'https://opencode.ai/zen/v1/responses',
    });
    assert.deepEqual(resolveProviderRuntime('opencode', {
        ...config,
        model: 'qwen4-future',
        mode: 'go',
    }), {
        apiMode: 'anthropic_messages',
        url: 'https://opencode.ai/zen/go/v1/messages',
    });
    assert.deepEqual(resolveProviderRuntime('opencode', {
        ...config,
        model: 'new-chat-model',
        mode: 'go',
    }), {
        apiMode: 'chat_completions',
        url: 'https://opencode.ai/zen/go/v1/chat/completions',
    });
});

test('Responses API parser collects output, reasoning summaries, and usage', () => {
    assert.deepEqual(parseResponsesResult({
        output: [
            { content: [{ type: 'summary_text', text: 'Reasoning' }] },
            { content: [{ type: 'output_text', text: 'Hello' }, { type: 'output_text', text: ' world' }] },
        ],
        usage: { input_tokens: 3, output_tokens: 2, total_tokens: 5 },
    }), {
        content: 'Hello world',
        thinking: 'Reasoning',
        usage: { inputTokens: 3, outputTokens: 2, totalTokens: 5 },
    });
});
