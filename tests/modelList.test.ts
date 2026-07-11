import assert from 'node:assert/strict';
import test from 'node:test';

import { getModelEndpoint, parseModelList } from '../src/providers/modelList.js';
import type { ProviderId } from '../src/providers/types.js';

const emptyConfig = { url: '', apiKey: '', mode: '' };

test('getModelEndpoint maps every provider to its documented model endpoint', () => {
    const expected: Record<ProviderId, string> = {
        ollama: 'http://127.0.0.1:11434/api/tags',
        llamacpp: 'http://127.0.0.1:8080/v1/models',
        lmstudio: 'http://127.0.0.1:1234/v1/models',
        openai: 'https://api.openai.com/v1/models',
        anthropic: 'https://api.anthropic.com/v1/models?limit=1000',
        gemini: 'https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000',
        groq: 'https://api.groq.com/openai/v1/models',
        mistral: 'https://api.mistral.ai/v1/models',
        openrouter: 'https://openrouter.ai/api/v1/models',
        custom: 'https://custom.test/v1/models',
        opencode: 'https://opencode.ai/zen/go/v1/models',
        githubcopilot: 'https://models.github.ai/catalog/models',
    };

    for (const provider of Object.keys(expected) as ProviderId[]) {
        const config = provider === 'custom'
            ? { ...emptyConfig, url: 'https://custom.test/v1/chat/completions' }
            : emptyConfig;
        assert.equal(getModelEndpoint(provider, config)?.url, expected[provider], provider);
    }
});

test('getModelEndpoint builds authentication and mode-specific requests', () => {
    assert.deepEqual(getModelEndpoint('ollama', {
        url: 'https://host.test/prefix/api/chat?ignored=1',
        apiKey: 'local-token',
        mode: '',
    }), {
        url: 'https://host.test/prefix/api/tags',
        headers: { Authorization: 'Bearer local-token' },
        requiresApiKey: false,
        kind: 'ollama',
        openCodeMode: null,
    });

    assert.deepEqual(getModelEndpoint('gemini', {
        url: 'https://gemini-proxy.test/v1beta/',
        apiKey: 'google-key',
        mode: '',
    }), {
        url: 'https://gemini-proxy.test/v1beta/models?pageSize=1000',
        headers: { 'x-goog-api-key': 'google-key' },
        requiresApiKey: true,
        kind: 'gemini',
        openCodeMode: null,
    });

    assert.equal(
        getModelEndpoint('opencode', { ...emptyConfig, apiKey: 'token', mode: 'zen' })?.url,
        'https://opencode.ai/zen/v1/models'
    );
    assert.throws(
        () => getModelEndpoint('custom', emptyConfig),
        /Enter an endpoint URL/
    );
});

test('parseModelList handles OpenAI, Ollama, Gemini, and GitHub response shapes', () => {
    assert.deepEqual(parseModelList(JSON.stringify({
        data: [{ id: 'a' }, { display_name: 'b' }, { id: 'a' }, null, { id: 4 }],
    }), 'openai', null), ['a', 'b']);

    assert.deepEqual(parseModelList(JSON.stringify({
        models: [{ name: 'llama' }, { model: 'fallback' }, { name: '' }],
    }), 'ollama', null), ['llama', 'fallback']);

    assert.deepEqual(parseModelList(JSON.stringify({
        models: [
            { name: 'models/gemini-chat', supportedGenerationMethods: ['generateContent'] },
            { name: 'models/embed-only', supportedGenerationMethods: ['embedContent'] },
            { name: 'models/legacy-without-capabilities' },
        ],
    }), 'gemini', null), ['gemini-chat', 'legacy-without-capabilities']);

    assert.deepEqual(parseModelList(JSON.stringify([
        { id: 'openai/gpt-test' },
        { display_name: 'Fallback Model' },
    ]), 'github', null), ['openai/gpt-test', 'Fallback Model']);
});

test('parseModelList filters OpenCode models by mode and endpoint capability', () => {
    const response = JSON.stringify({
        data: [
            { id: 'kimi-k2.7-code' },
            { id: 'big-pickle' },
            { id: 'server-chat', endpoint: '/v1/chat/completions' },
            { id: 'server-responses', endpoint: '/v1/responses' },
        ],
    });
    assert.deepEqual(parseModelList(response, 'openai', 'go'), ['kimi-k2.7-code', 'server-chat']);
    assert.deepEqual(parseModelList(response, 'openai', 'zen'), ['kimi-k2.7-code', 'big-pickle', 'server-chat']);
});

test('parseModelList rejects malformed envelopes and invalid JSON', () => {
    assert.deepEqual(parseModelList('{}', 'openai', null), []);
    assert.deepEqual(parseModelList('[]', 'openai', null), []);
    assert.throws(() => parseModelList('not-json', 'openai', null), SyntaxError);
});
