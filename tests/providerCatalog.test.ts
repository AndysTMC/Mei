import assert from 'node:assert/strict';
import test from 'node:test';

import {
    CLOUD_PROVIDER_IDS,
    CUSTOM_PROVIDER_IDS,
    getOpenCodeChatCompletionsUrl,
    getOpenCodeModelId,
    getOpenCodeMode,
    getOpenCodeModelsUrl,
    getModelListUrl,
    getProviderIdsForType,
    getProviderLabel,
    getProviderType,
    isProviderId,
    LOCAL_PROVIDER_IDS,
    PROVIDER_LABELS,
    PROVIDER_TYPE_IDS,
} from '../src/providers/catalog.js';
import { getOpenCodeApiMode, resolveProviderId } from '../src/providers/profiles.js';

test('OpenCode model ids strip provider prefixes consistently', () => {
    assert.equal(getOpenCodeModelId('opencode-go/kimi-k2.7-code'), 'kimi-k2.7-code');
    assert.equal(getOpenCodeModelId('opencode/glm-5.2'), 'glm-5.2');
    assert.equal(getOpenCodeModelId('opencode-zen/qwen3.8-max'), 'qwen3.8-max');
    assert.equal(getOpenCodeModelId('deepseek-v4-pro'), 'deepseek-v4-pro');
});

test('model-list URLs preserve reverse-proxy path prefixes', () => {
    assert.equal(
        getModelListUrl('https://example.test/ollama/api/chat?token=hidden', '/api/tags'),
        'https://example.test/ollama/api/tags'
    );
    assert.equal(
        getModelListUrl('https://example.test/ai/v1/chat/completions', '/v1/models'),
        'https://example.test/ai/v1/models'
    );
    assert.equal(getModelListUrl('https://example.test', '/v1/models'), 'https://example.test/v1/models');
});

test('OpenCode routes model families without a finite allowlist', () => {
    assert.equal(getOpenCodeApiMode('opencode-go/kimi-k2.7-code', 'go'), 'chat_completions');
    assert.equal(getOpenCodeApiMode('opencode-go/minimax-m4-future', 'go'), 'anthropic_messages');
    assert.equal(getOpenCodeApiMode('opencode-go/qwen4-future', 'go'), 'anthropic_messages');
    assert.equal(getOpenCodeApiMode('opencode-zen/qwen4-future', 'ZEN'), 'anthropic_messages');
    assert.equal(getOpenCodeApiMode('opencode/grok-5-future', 'zen'), 'responses');
    assert.equal(getOpenCodeApiMode('opencode/claude-5-future', 'zen'), 'anthropic_messages');
    assert.equal(getOpenCodeApiMode('opencode/future-model', 'zen'), 'chat_completions');
});

test('GitHub provider is labelled for the API it uses', () => {
    assert.equal(PROVIDER_LABELS.githubcopilot, 'GitHub Models');
});

test('provider catalog partitions every provider exactly once', () => {
    const grouped = [...LOCAL_PROVIDER_IDS, ...CLOUD_PROVIDER_IDS, ...CUSTOM_PROVIDER_IDS];
    assert.deepEqual(PROVIDER_TYPE_IDS, ['local', 'cloud', 'custom']);
    assert.equal(new Set(grouped).size, grouped.length);
    assert.deepEqual(new Set(grouped), new Set(Object.keys(PROVIDER_LABELS)));
    assert.deepEqual(getProviderIdsForType('local'), LOCAL_PROVIDER_IDS);
    assert.deepEqual(getProviderIdsForType('cloud'), CLOUD_PROVIDER_IDS);
    assert.deepEqual(getProviderIdsForType('custom'), CUSTOM_PROVIDER_IDS);
    assert.equal(CLOUD_PROVIDER_IDS.includes('deepseek' as never), false);
});

test('provider catalog normalizes types, ids, labels, and OpenCode modes', () => {
    assert.equal(getProviderType('local'), 'local');
    assert.equal(getProviderType('custom'), 'custom');
    assert.equal(getProviderType('anything-else'), 'cloud');
    assert.equal(isProviderId('gemini'), true);
    assert.equal(isProviderId('deepseek'), false);
    assert.equal(resolveProviderId('github-models'), 'githubcopilot');
    assert.equal(resolveProviderId('llama.cpp'), 'llamacpp');
    assert.equal(getProviderLabel('gemini'), 'Gemini');
    assert.equal(getProviderLabel('future-provider'), 'future-provider');
    assert.equal(getOpenCodeMode('zen'), 'zen');
    assert.equal(getOpenCodeMode('invalid'), 'go');
    assert.equal(getOpenCodeChatCompletionsUrl('go'), 'https://opencode.ai/zen/go/v1/chat/completions');
    assert.equal(getOpenCodeChatCompletionsUrl('zen'), 'https://opencode.ai/zen/v1/chat/completions');
    assert.equal(getOpenCodeModelsUrl('go'), 'https://opencode.ai/zen/go/v1/models');
    assert.equal(getOpenCodeModelsUrl('zen'), 'https://opencode.ai/zen/v1/models');
});

test('model-list URL handling is safe for malformed and non-chat URLs', () => {
    assert.equal(getModelListUrl('not a url', '/v1/models'), 'not a url');
    assert.equal(getModelListUrl('https://example.test/unrelated', '/v1/models'), 'https://example.test/unrelated/v1/models');
    assert.equal(getModelListUrl(' HTTPS://EXAMPLE.TEST/v1/chat/completions/ ', '/v1/models'), 'HTTPS://EXAMPLE.TEST/v1/models');
});
