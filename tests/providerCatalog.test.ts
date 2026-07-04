import assert from 'node:assert/strict';
import test from 'node:test';

import {
    getOpenCodeModelId,
    isOpenCodeChatCompletionsModel,
    PROVIDER_LABELS,
} from '../src/providers/catalog.js';

test('OpenCode model ids strip provider prefixes consistently', () => {
    assert.equal(getOpenCodeModelId('opencode-go/kimi-k2.7-code'), 'kimi-k2.7-code');
    assert.equal(getOpenCodeModelId('opencode/glm-5.2'), 'glm-5.2');
    assert.equal(getOpenCodeModelId('deepseek-v4-pro'), 'deepseek-v4-pro');
});

test('OpenCode fallback filters include only chat completions models', () => {
    assert.equal(isOpenCodeChatCompletionsModel('opencode-go/kimi-k2.7-code', 'go'), true);
    assert.equal(isOpenCodeChatCompletionsModel('opencode-go/minimax-m3', 'go'), false);
    assert.equal(isOpenCodeChatCompletionsModel('opencode/minimax-m3', 'zen'), true);
    assert.equal(isOpenCodeChatCompletionsModel('opencode/gpt-5.5', 'zen'), false);
});

test('GitHub provider is labelled for the API it uses', () => {
    assert.equal(PROVIDER_LABELS.githubcopilot, 'GitHub Models');
});
