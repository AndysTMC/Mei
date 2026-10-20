import assert from 'node:assert/strict';
import test from 'node:test';

import {
    CLOUD_PROVIDER_IDS,
    CUSTOM_PROVIDER_IDS,
    DEEPSEEK_REASONING_EFFORT_LABELS,
    DEEPSEEK_THINKING_LABELS,
    getDeepSeekReasoningEffort,
    getDeepSeekThinking,
    getProviderIdsForType,
    getProviderLabel,
    getProviderType,
    isProviderId,
    LEGACY_PROVIDER_IDS,
    LOCAL_PROVIDER_IDS,
    PROVIDER_LABELS,
    PROVIDER_TYPE_IDS,
} from '../src/providers/catalog.js';
import { resolveProviderId } from '../src/providers/profiles.js';

test('retired providers remain recognized for legacy settings but are not selectable', () => {
    assert.equal(PROVIDER_LABELS.githubcopilot, 'GitHub Models (retired)');
    assert.equal(PROVIDER_LABELS.opencode, 'OpenCode (unavailable)');
    assert.deepEqual(new Set(LEGACY_PROVIDER_IDS), new Set(['githubcopilot', 'opencode']));
    for (const id of ['githubcopilot', 'opencode'] as const) {
        assert.equal(CLOUD_PROVIDER_IDS.includes(id), false);
        assert.equal(isProviderId(id), true);
    }
});

test('provider catalog partitions every provider exactly once', () => {
    const grouped = [...LOCAL_PROVIDER_IDS, ...CLOUD_PROVIDER_IDS, ...CUSTOM_PROVIDER_IDS];
    const recognized = [...grouped, ...LEGACY_PROVIDER_IDS];
    assert.deepEqual(PROVIDER_TYPE_IDS, ['local', 'cloud', 'custom']);
    assert.equal(new Set(grouped).size, grouped.length);
    assert.deepEqual(new Set(recognized), new Set(Object.keys(PROVIDER_LABELS)));
    assert.deepEqual(getProviderIdsForType('local'), LOCAL_PROVIDER_IDS);
    assert.deepEqual(getProviderIdsForType('cloud'), CLOUD_PROVIDER_IDS);
    assert.deepEqual(getProviderIdsForType('custom'), CUSTOM_PROVIDER_IDS);
    assert.equal(CLOUD_PROVIDER_IDS.includes('deepseek'), true);
    assert.equal(CLOUD_PROVIDER_IDS.includes('fireworks'), true);
    assert.equal(CLOUD_PROVIDER_IDS.includes('nvidia'), true);
});

test('provider catalog normalizes types, ids, and labels', () => {
    assert.equal(getProviderType('local'), 'local');
    assert.equal(getProviderType('custom'), 'custom');
    assert.equal(getProviderType('anything-else'), 'cloud');
    assert.equal(isProviderId('gemini'), true);
    assert.equal(isProviderId('deepseek'), true);
    assert.equal(resolveProviderId('github-models'), 'githubcopilot');
    assert.equal(resolveProviderId('llama.cpp'), 'llamacpp');
    assert.equal(getProviderLabel('fireworks'), 'Fireworks AI');
    assert.equal(getProviderLabel('nvidia'), 'NVIDIA NIM');
    assert.equal(getProviderLabel('gemini'), 'Gemini');
    assert.equal(getProviderLabel('future-provider'), 'future-provider');
    assert.equal(getDeepSeekThinking('enabled'), 'enabled');
    assert.equal(getDeepSeekThinking('invalid'), 'default');
    assert.equal(getDeepSeekReasoningEffort('low'), 'low');
    assert.equal(getDeepSeekReasoningEffort('invalid'), 'high');
    assert.equal(DEEPSEEK_THINKING_LABELS.disabled, 'Off');
    assert.equal(DEEPSEEK_REASONING_EFFORT_LABELS.max, 'Max');
});

