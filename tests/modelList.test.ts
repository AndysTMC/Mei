import assert from 'node:assert/strict';
import test from 'node:test';

import { getModelEndpoint, getNextPageUrl, parseModelList } from '../src/providers/modelList.js';
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
        deepseek: 'https://api.deepseek.com/models',
        fireworks: 'https://api.fireworks.ai/inference/v1/models',
        nvidia: 'https://integrate.api.nvidia.com/v1/models',
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
    assert.equal(getModelEndpoint('openrouter', emptyConfig)?.requiresApiKey, false);
    assert.equal(
        getModelEndpoint('custom', {
            ...emptyConfig,
            url: 'https://custom.test/provider/v1/chat/completions',
        })?.url,
        'https://custom.test/provider/v1/models'
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

test('parseModelList keeps OpenCode models for runtime API-mode routing', () => {
    const response = JSON.stringify({
        data: [
            { id: 'kimi-k2.7-code' },
            { id: 'big-pickle' },
            { id: 'server-chat', endpoint: '/v1/chat/completions' },
            { id: 'server-responses', endpoint: '/v1/responses' },
        ],
    });
    const expected = ['kimi-k2.7-code', 'big-pickle', 'server-chat', 'server-responses'];
    assert.deepEqual(parseModelList(response, 'openai', 'go'), expected);
    assert.deepEqual(parseModelList(response, 'openai', 'zen'), expected);
});

test('model pagination replaces cursors and accepts only same-origin absolute next URLs', () => {
    assert.equal(
        getNextPageUrl('https://models.test/list?pageSize=10&pageToken=old', '{"nextPageToken":"abc"}', 'gemini'),
        'https://models.test/list?pageSize=10&pageToken=abc'
    );
    assert.equal(
        getNextPageUrl('https://models.test/list?after_id=old', '{"has_more":true,"data":[{"id":"last"}]}', 'openai'),
        'https://models.test/list?after_id=last'
    );
    assert.equal(
        getNextPageUrl('https://models.test/list', '{"next":"https://models.test/page/2"}', 'openai'),
        'https://models.test/page/2'
    );
    assert.equal(
        getNextPageUrl('https://models.test/list', '{"next":"https://attacker.test/collect"}', 'openai'),
        null
    );
    assert.equal(
        getNextPageUrl('https://models.test/list', '{"next":"http://models.test/page/2"}', 'openai'),
        null
    );
});

test('parseModelList rejects malformed envelopes and invalid JSON', () => {
    assert.deepEqual(parseModelList('{}', 'openai', null), []);
    assert.deepEqual(parseModelList('[]', 'openai', null), []);
    assert.throws(() => parseModelList('not-json', 'openai', null), SyntaxError);
});
