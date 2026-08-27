import assert from 'node:assert/strict';
import test from 'node:test';

import { getProviderProfile, resolveProviderId, resolveProviderRuntime } from '../src/providers/profiles.js';
import {
    buildResponsesBody,
    getResponsesFailure,
    getResponsesIncompleteReason,
    parseResponsesResult,
} from '../src/providers/responsesPayload.js';

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

test('Responses payload disables storage and maps system messages to developer input', () => {
    assert.deepEqual(buildResponsesBody('gpt-test', [
        { role: 'system', content: 'Be concise.' },
        { role: 'user', content: 'Hello' },
    ]), {
        model: 'gpt-test',
        store: false,
        input: [
            { role: 'developer', content: 'Be concise.' },
            { role: 'user', content: 'Hello' },
        ],
    });
});

test('Responses parser avoids output_text duplication and preserves refusals and summary arrays', () => {
    assert.deepEqual(parseResponsesResult({
        output_text: 'Direct answer',
        output: [
            { content: [{ type: 'output_text', text: 'Duplicated answer' }] },
            { content: [{ type: 'refusal', refusal: 'Cannot comply.' }] },
            { summary: [{ type: 'summary_text', text: 'Reasoning summary' }] },
        ],
    }), {
        content: 'Direct answer',
        thinking: 'Reasoning summary',
        usage: undefined,
    });
    assert.equal(parseResponsesResult({
        output: [{ content: [{ type: 'refusal', refusal: 'Cannot comply.' }] }],
    }).content, 'Cannot comply.');
});

test('Responses terminal errors are surfaced instead of becoming empty successes', () => {
    const failed = {
        type: 'response.failed',
        response: { status: 'failed', error: { message: 'Upstream rejected the request.' } },
    };
    const incomplete = {
        type: 'response.incomplete',
        response: { status: 'incomplete', incomplete_details: { reason: 'max_output_tokens' } },
    };
    assert.equal(getResponsesFailure(failed), 'Upstream rejected the request.');
    assert.equal(getResponsesIncompleteReason(incomplete), 'Response incomplete: max_output_tokens.');
    assert.throws(() => parseResponsesResult(failed), /Upstream rejected/);
    assert.throws(() => parseResponsesResult(incomplete), /max_output_tokens/);
    assert.equal(parseResponsesResult({
        status: 'incomplete',
        incomplete_details: { reason: 'max_output_tokens' },
        output: [{ content: [{ type: 'output_text', text: 'Partial answer' }] }],
    }).content, 'Partial answer\n\n[Response incomplete: max_output_tokens.]');
});
