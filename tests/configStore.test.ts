import assert from 'node:assert/strict';
import test from 'node:test';

import {
    API_KEY_PLACEHOLDER,
    createEmptyProviderConfig,
    isApiKeyPlaceholder,
    isApiKeyPlaceholderLike,
    parseProviderConfigs,
} from '../src/providers/configStore.ts';

test('createEmptyProviderConfig returns all supported fields', () => {
    assert.deepEqual(createEmptyProviderConfig(), {
        url: '',
        modelName: '',
        apiKey: '',
        apiKeyStorage: '',
        mode: '',
        thinking: '',
        reasoningEffort: '',
    });
});

test('API key placeholder is recognizable but distinct from an empty key', () => {
    assert.equal(API_KEY_PLACEHOLDER, '********');
    assert.equal(isApiKeyPlaceholder(API_KEY_PLACEHOLDER), true);
    assert.equal(isApiKeyPlaceholderLike(API_KEY_PLACEHOLDER), true);
    assert.equal(isApiKeyPlaceholderLike('****'), true);
    assert.equal(isApiKeyPlaceholder(''), false);
    assert.equal(isApiKeyPlaceholderLike(''), false);
    assert.equal(isApiKeyPlaceholder('real-key'), false);
    assert.equal(isApiKeyPlaceholderLike('real-key'), false);
});

test('parseProviderConfigs returns normalized provider configs', () => {
    const configs = parseProviderConfigs(JSON.stringify({
        openai: {
            url: 'https://example.test/v1/chat/completions',
            modelName: 'gpt-test',
            apiKey: 'sk-test',
            apiKeyStorage: 'secret',
            mode: 'unused',
            thinking: 'enabled',
            reasoningEffort: 'high',
        },
        gemini: {
            modelName: 'gemini-test',
            apiKey: 123,
            extra: true,
        },
    }));

    assert.deepEqual(configs.openai, {
        url: 'https://example.test/v1/chat/completions',
        modelName: 'gpt-test',
        apiKey: 'sk-test',
        apiKeyStorage: 'secret',
        mode: 'unused',
        thinking: 'enabled',
        reasoningEffort: 'high',
    });
    assert.deepEqual(configs.gemini, {
        url: '',
        modelName: 'gemini-test',
        apiKey: '',
        apiKeyStorage: '',
        mode: '',
        thinking: '',
        reasoningEffort: '',
    });
});

test('parseProviderConfigs ignores invalid top-level and provider values', () => {
    assert.deepEqual(parseProviderConfigs(''), {});
    assert.deepEqual(parseProviderConfigs('not json'), {});
    assert.deepEqual(parseProviderConfigs('[]'), {});

    assert.deepEqual(parseProviderConfigs(JSON.stringify({
        valid: { apiKey: 'secret' },
        nullish: null,
        list: [],
        text: 'bad',
    })), {
        valid: {
            url: '',
            modelName: '',
            apiKey: 'secret',
            apiKeyStorage: '',
            mode: '',
            thinking: '',
            reasoningEffort: '',
        },
    });
});
