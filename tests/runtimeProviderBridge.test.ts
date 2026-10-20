import assert from 'node:assert/strict';
import test from 'node:test';

import { toRuntimeProvider } from '../src/runtime/providerBridge.js';

test('OpenAI-compatible providers map to openai_chat with their endpoint and headers', () => {
    const r = toRuntimeProvider('openrouter', { modelName: 'meta/llama-4' });
    assert.equal(r.unsupported, undefined);
    assert.equal(r.config.kind, 'openai_chat');
    assert.equal(r.config.id, 'openrouter');
    assert.equal(r.config.url, 'https://openrouter.ai/api/v1/chat/completions');
    assert.equal(r.config.model, 'meta/llama-4');
    assert.ok(Object.keys(r.config.headers).length > 0);
});

test('a custom URL overrides the profile endpoint', () => {
    const r = toRuntimeProvider('lmstudio', { url: 'http://127.0.0.1:9999/v1/chat/completions', modelName: 'qwen' });
    assert.equal(r.config.url, 'http://127.0.0.1:9999/v1/chat/completions');
});

test('OpenCode model ids are normalized and routed by model', () => {
    const r = toRuntimeProvider('opencode', { modelName: 'opencode-go/glm-5.3', mode: 'go' });
    assert.equal(r.config.model, 'glm-5.3');
    assert.match(r.config.url, /\/chat\/completions$/);
});

test('providers on other transports are reported as unsupported, not silently sent', () => {
    for (const id of ['anthropic', 'gemini', 'ollama', 'githubcopilot'] as const) {
        const r = toRuntimeProvider(id, { modelName: 'x' });
        assert.equal(r.config.kind, 'none', id);
        assert.ok(r.unsupported, id);
    }
});

test('no model selected is reported', () => {
    const r = toRuntimeProvider('openai', {});
    assert.equal(r.config.kind, 'none');
    assert.match(r.unsupported ?? '', /model/);
});

test('nothing secret is ever part of the config', () => {
    const r = toRuntimeProvider('openai', { modelName: 'gpt-x' });
    assert.ok(!JSON.stringify(r.config).toLowerCase().includes('key'));
});
