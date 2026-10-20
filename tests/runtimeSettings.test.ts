import assert from 'node:assert/strict';
import test from 'node:test';

import { RuntimeSettings } from '../src/runtime/settings.js';
import type { ConfigDoc } from '../src/runtime/protocol.js';

type Sent = { method: string; args: { revision?: number; config?: ConfigDoc } };

function fakeRuntime(initial: Record<string, unknown>) {
    const sent: Sent[] = [];
    let revision = 1;
    let doc = structuredClone(initial);
    const call = async <T>(method: string, args: object = {}): Promise<T> => {
        sent.push({ method, args: structuredClone(args) as Sent['args'] });
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
        get doc() {
            return doc;
        },
    };
}

const BASE = { active: 'gemini', providers: { gemini: { model: 'g', url: '', mode: '', thinking: '', reasoning_effort: '', options: {} } },
    privacy: { conversation_retention_days: null } };

const flush = () => new Promise(resolve => setTimeout(resolve, 0));

test('writes are refused until the settings are loaded', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    assert.throws(() => settings.setRetentionDays(30));
    await settings.reload();
    assert.equal(settings.retentionDays, null);
});

test('retention changes are sent once and announced to listeners', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    const heard: string[] = [];
    settings.connect('changed::privacy', (_s, key) => heard.push(key));
    settings.setRetentionDays(30);
    settings.setRetentionDays(30);
    await flush();
    assert.deepEqual(heard, ['privacy']);
    assert.equal(rt.sent.filter(s => s.method === 'UpdateConfig').length, 1);
    assert.equal((rt.doc.privacy as { conversation_retention_days: number }).conversation_retention_days, 30);
});

test('fields from a newer runtime survive a write from this client', async () => {
    const rt = fakeRuntime({ ...BASE, memory: { enabled: true }, privacy: { ...BASE.privacy, screenshots_days: 7 } });
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    settings.setRetentionDays(90);
    await flush();
    assert.deepEqual(rt.doc.memory, { enabled: true });
    assert.deepEqual(rt.doc.privacy, { screenshots_days: 7, conversation_retention_days: 90 });
});

test('a remote retention change is announced; a conflicting write is replayed on the fresh copy', async () => {
    const rt = fakeRuntime(BASE);
    const settings = new RuntimeSettings(rt.call);
    await settings.reload();
    const heard: string[] = [];
    settings.connect('changed', (_s, key) => heard.push(key));

    rt.remote(d => {
        (d.privacy as { conversation_retention_days: number | null }).conversation_retention_days = 7;
    });
    await settings.reload();
    assert.equal(settings.retentionDays, 7);
    assert.deepEqual(heard, ['privacy']);

    rt.remote(d => {
        d.active = 'groq';
    });
    settings.setRetentionDays(365); // based on a stale revision: the runtime refuses, we replay
    await flush();
    await flush();
    assert.equal(rt.doc.active, 'groq');
    assert.equal((rt.doc.privacy as { conversation_retention_days: number }).conversation_retention_days, 365);
});
