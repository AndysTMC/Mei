import assert from 'node:assert/strict';
import test from 'node:test';

import { sameProvider, toRuntimeProvider } from '../src/runtime/providerBridge.js';

test('every selectable provider passes its preferences through untouched', () => {
    for (const id of ['gemini', 'anthropic', 'ollama', 'openrouter', 'opencode', 'lmstudio', 'custom', 'deepseek'] as const) {
        const r = toRuntimeProvider(id, { modelName: ' some-model ', url: ' http://x/ ', mode: 'zen', thinking: 'enabled', reasoningEffort: 'max' });
        assert.equal(r.unsupported, undefined, id);
        assert.deepEqual(r.config, {
            id, model: 'some-model', url: 'http://x/', mode: 'zen', thinking: 'enabled', reasoning_effort: 'max', options: {},
        });
    }
});

test('retired providers and a missing model are reported, not sent', () => {
    assert.match(toRuntimeProvider('githubcopilot', { modelName: 'x' }).unsupported ?? '', /no longer available/);
    const r = toRuntimeProvider('gemini', {});
    assert.equal(r.config.id, '');
    assert.match(r.unsupported ?? '', /model/);
});

test('nothing secret is ever part of the config', () => {
    const r = toRuntimeProvider('openai', { modelName: 'gpt-x' });
    assert.ok(!JSON.stringify(r.config).toLowerCase().includes('key'));
});

test('sameProvider ignores key order and compares every field', () => {
    const a = toRuntimeProvider('gemini', { modelName: 'm' }).config;
    const b = { options: {}, reasoning_effort: '', thinking: '', mode: '', url: '', model: 'm', id: 'gemini' };
    assert.ok(sameProvider(a, b));
    assert.ok(!sameProvider(a, { ...b, model: 'n' }));
});
