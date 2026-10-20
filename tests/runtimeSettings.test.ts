import assert from 'node:assert/strict';
import test from 'node:test';

import { RuntimeSettings } from '../src/runtime/settings.js';
import type { ConfigDoc } from '../src/runtime/protocol.js';

type Sent = { method: string; args: { revision?: number; config?: ConfigDoc } };

function fakeRuntime(initial: Record<string, unknown>) {
    const sent: Sent[] = [];
    let revision = 1;
    let doc = structuredClone(initial);
    let down = false;
    const call = async <T>(method: string, args: object = {}): Promise<T> => {
        sent.push({ method, args: structuredClone(args) as Sent['args'] });
        if (down) throw Object.assign(new Error('The name com.andystmc.Mei1 was not provided'), { code: 'ServiceUnknown' });
        if (method === 'GetConfig') return { revision, config: structuredClone(doc) } as T;
        if (method === 'UpdateConfig') {
            const a = args as { revision: number; config: Record<string, unknown> };
            if (a.revision !== revision) {
                throw Object.assign(new Error('stale'), { code: 'Conflict' });
            }
            doc = structuredClone(a.config);
            revision += 1;
            return { revision, changed: true } as T;
        }
        throw new Error(`unexpected ${method}`);
    };
    return {
        call, sent,
        remote(change: (d: Record<string, unknown>) => void) {
            change(doc);
            revision += 1;
        },
        setDown(value: boolean) {
            down = value;
        },
        get doc() {
            return doc;
        },
    };
}

type Doc = { providers: Record<string, { model: string; url: string }> };

const BASE = { active: 'gemini', providers: { gemini: { model: 'g', url: '', mode: '', thinking: '', reasoning_effort: '', options: {} } },
    privacy: { conversation_retention_days: null } };

const flush = () => new Promise(resolve => setTimeout(resolve, 0));

test('writes are refused until the settings are loaded', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    assert.throws(() => settings.setRetentionDays(30));
    assert.equal(settings.setActive('groq'), false);
    settings.setProviderField('gemini', 'model', 'x');
    assert.equal(rt.sent.length, 0);
    await settings.reload();
    assert.equal(settings.retentionDays, null);
    assert.equal(settings.active, 'gemini');
    assert.equal(settings.provider('gemini').model, 'g');
    assert.equal(settings.provider('never-set').model, '');
});

test('changes are sent once and announced to listeners of their key', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    const heard: string[] = [];
    settings.connect('changed', (_s, key) => heard.push(key));
    settings.setRetentionDays(30);
    settings.setRetentionDays(30);
    settings.setProviderField('gemini', 'model', 'gemini-2');
    settings.setProviderField('gemini', 'model', 'gemini-2');
    assert.equal(settings.setActive('OR'), true); // an alias, stored as the canonical id
    await settings.flushed();
    assert.deepEqual(heard, ['privacy', 'providers', 'active']);
    assert.equal(rt.doc.active, 'openrouter');
    assert.equal((rt.doc as Doc).providers.gemini.model, 'gemini-2');
});

test('unknown and retired providers cannot be chosen', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    assert.equal(settings.setActive('nope'), false);
    assert.equal(settings.setActive('opencode'), false);
    assert.equal(settings.active, 'gemini');
});

test('fields from a newer runtime survive a write from this client', async () => {
    const rt = fakeRuntime({ ...BASE, memory: { enabled: true }, privacy: { ...BASE.privacy, screenshots_days: 7 } });
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    settings.setRetentionDays(90);
    await settings.flushed();
    assert.deepEqual(rt.doc.memory, { enabled: true });
    assert.deepEqual(rt.doc.privacy, { screenshots_days: 7, conversation_retention_days: 90 });
});

test('a conflict replays only this client\'s field change, keeping another client\'s change', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    // Another client changes the model; this client, still on the older copy, changes only the URL.
    rt.remote(d => {
        (d as Doc).providers.gemini.model = 'changed-elsewhere';
    });
    settings.setProviderField('gemini', 'url', 'https://proxy.test/v1beta');
    await settings.flushed();
    const saved = (rt.doc as Doc).providers.gemini;
    assert.equal(saved.url, 'https://proxy.test/v1beta');
    assert.equal(saved.model, 'changed-elsewhere');
});

test('a remote change is announced by key', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    const heard: string[] = [];
    settings.connect('changed::privacy', (_s, key) => heard.push(key));
    rt.remote(d => {
        (d.privacy as { conversation_retention_days: number | null }).conversation_retention_days = 7;
    });
    await settings.reload();
    assert.equal(settings.retentionDays, 7);
    assert.deepEqual(heard, ['privacy']);
});

test('a save that fails while the runtime is away is kept, reported, and sent after reconnecting', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    const failures: string[] = [];
    settings.connect('save-failed', (_s, message) => failures.push(message));
    rt.setDown(true);
    settings.setRetentionDays(30);
    await settings.flushed();
    await flush();
    assert.equal(failures.length, 1);
    assert.equal(settings.retentionDays, 30); // still shown: it isn't lost
    const attempts = rt.sent.filter(s => s.method === 'UpdateConfig').length;
    await flush();
    assert.equal(rt.sent.filter(s => s.method === 'UpdateConfig').length, attempts); // no retry loop while away
    rt.setDown(false);
    await settings.reload(); // what reconnecting does
    await settings.flushed();
    assert.equal((rt.doc.privacy as { conversation_retention_days: number }).conversation_retention_days, 30);
});

test('listing models waits for a just-saved endpoint', async () => {
    const rt = fakeRuntime(BASE);
    const order: string[] = [];
    const call = async <T>(method: string, args: object = {}): Promise<T> => {
        order.push(method);
        if (method === 'ListModels') return { models: ['m'], requires_key: false, from_fallback: false } as T;
        return rt.call<T>(method, args);
    };
    const settings = new RuntimeSettings(call);
    await settings.reload();
    settings.setProviderField('gemini', 'url', 'https://proxy.test/v1beta');
    assert.deepEqual(await settings.listModels('gemini'), { models: ['m'], requiresApiKey: false });
    assert.deepEqual(order, ['GetConfig', 'UpdateConfig', 'ListModels']);
});
