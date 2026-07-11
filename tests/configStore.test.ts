import assert from 'node:assert/strict';
import test from 'node:test';

import {
    API_KEY_PLACEHOLDER,
    createEmptyProviderConfig,
    isApiKeyPlaceholder,
    isApiKeyPlaceholderLike,
    mergeMigratedApiKeyConfigs,
    parseProviderConfigs,
    withSecretApiKeyFallback,
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

test('mergeMigratedApiKeyConfigs preserves concurrent configuration edits', () => {
    const original = { openai: { ...createEmptyProviderConfig(), apiKey: 'plain' } };
    const migrated = { openai: { ...original.openai, apiKeyStorage: 'secret' as const } };
    const current = { openai: { ...original.openai, modelName: 'new-model' } };

    assert.deepEqual(mergeMigratedApiKeyConfigs(original, migrated, current).openai, {
        ...current.openai,
        apiKey: 'plain',
        apiKeyStorage: 'secret',
    });

    const keyChanged = { openai: { ...current.openai, apiKey: 'new-key' } };
    assert.deepEqual(mergeMigratedApiKeyConfigs(original, migrated, keyChanged), keyChanged);

    assert.deepEqual(mergeMigratedApiKeyConfigs(
        original,
        { openai: original.openai },
        current
    ), current);
    assert.deepEqual(mergeMigratedApiKeyConfigs(original, {}, current), current);
    assert.deepEqual(mergeMigratedApiKeyConfigs(original, migrated, {}), {});
});

test('API key placeholder is recognizable but distinct from an empty key', () => {
    assert.equal(API_KEY_PLACEHOLDER, '********');
    assert.equal(isApiKeyPlaceholder(API_KEY_PLACEHOLDER), true);
    assert.equal(isApiKeyPlaceholderLike(API_KEY_PLACEHOLDER), true);
    assert.equal(isApiKeyPlaceholderLike('****'), true);
    assert.equal(isApiKeyPlaceholderLike('*'), true);
    assert.equal(isApiKeyPlaceholderLike('*********'), false);
    assert.equal(isApiKeyPlaceholderLike(' **** '), false);
    assert.equal(isApiKeyPlaceholder(''), false);
    assert.equal(isApiKeyPlaceholderLike(''), false);
    assert.equal(isApiKeyPlaceholder('real-key'), false);
    assert.equal(isApiKeyPlaceholderLike('real-key'), false);
});

test('secret storage retains a fallback key for keyring outages', () => {
    const config = { ...createEmptyProviderConfig(), modelName: 'gpt-test' };
    assert.deepEqual(withSecretApiKeyFallback(config, 'sk-secret'), {
        ...config,
        apiKey: 'sk-secret',
        apiKeyStorage: 'secret',
    });
    assert.deepEqual(config, { ...createEmptyProviderConfig(), modelName: 'gpt-test' });
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
    assert.deepEqual(parseProviderConfigs('null'), {});
    assert.deepEqual(parseProviderConfigs('42'), {});

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
