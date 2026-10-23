import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { memorySubtitle } from '../src/prefs/setupText.js';
import { Projection } from '../src/runtime/projection.js';
import type { AttachReply, Envelope, MemoryView } from '../src/runtime/protocol.js';
import { buildTimeline } from '../src/runtime/timeline.js';

interface Fixture {
    attach: AttachReply;
    events: Envelope[];
    expect: { conversation_id: string; task_id: string };
}

const fx = JSON.parse(readFileSync('protocol/fixtures/agent_with_approval.json', 'utf8')) as Fixture;
const conv = fx.expect.conversation_id;
const task = fx.expect.task_id;

function memory(id: string, extra: Partial<MemoryView> = {}): MemoryView {
    return {
        id, kind: 'profile', text: `fact ${id}`, provenance: 'user_stated', status: 'active', sensitivity: 'normal',
        pinned: false, source_task_id: task, source_conversation_id: conv, use_count: 0, created_at: 1, updated_at: 1,
        last_used_at: null, ...extra,
    };
}

function replayWith(extra: { type: string; payload: Record<string, unknown> }[]): Projection {
    const p = new Projection();
    p.applyAttach(fx.attach);
    const events = [...fx.events];
    const last = events.findIndex(e => e.type === 'task.finished');
    let seq = Math.max(...events.map(e => e.seq ?? 0));
    const added = extra.map(e => ({ ...events[last], ...e, event_id: `m${seq}`, seq: ++seq, task_id: task }));
    for (const e of [...events, ...added]) p.applyEvent(e);
    return p;
}

test('memories a task saved show under its reply (whose details hold the outcome); review ones wait for Keep or Discard', () => {
    const p = replayWith([
        { type: 'memory.saved', payload: { memory: memory('a') } },
        { type: 'memory.pending_review', payload: { memory: memory('b', { status: 'pending_review', provenance: 'untrusted' }) } },
    ]);
    const items = buildTimeline(p.loaded.get(conv)!);
    const kinds = items.map(i => i.kind);
    assert.deepEqual(kinds.slice(-3), ['message', 'memory', 'memory']);
    const reply = items.at(-3);
    assert.ok(reply?.kind === 'message' && reply.details?.outcome);
    const shown = items.filter(i => i.kind === 'memory').map(i => i.kind === 'memory' && i.memory.status);
    assert.deepEqual(shown, ['active', 'pending_review']);
});

test('undo and discard remove the item; archiving hides it; keeping updates it in place', () => {
    const p = replayWith([
        { type: 'memory.saved', payload: { memory: memory('a') } },
        { type: 'memory.pending_review', payload: { memory: memory('b', { status: 'pending_review' }) } },
        { type: 'memory.saved', payload: { memory: memory('c') } },
        { type: 'memory.deleted', payload: { memory_id: 'a' } },
        { type: 'memory.updated', payload: { memory: memory('b') } },
        { type: 'memory.updated', payload: { memory: memory('c', { status: 'archived' }) } },
    ]);
    const items = buildTimeline(p.loaded.get(conv)!).filter(i => i.kind === 'memory');
    assert.deepEqual(items.map(i => i.kind === 'memory' && [i.memory.id, i.memory.status]), [['b', 'active']]);
});

test('a conversation fetched later brings its memories with it', () => {
    const p = new Projection();
    p.applyAttach({ ...fx.attach, seq: 100 });
    const ok = p.applyConversation({
        epoch: fx.attach.epoch, seq: 100, conversation: { id: conv, title: 't', created_at: 0, updated_at: 0 },
        messages: [], tasks: [], streams: [], memories: [memory('x', { source_task_id: null })],
    });
    assert.ok(ok);
    assert.deepEqual(buildTimeline(p.loaded.get(conv)!).map(i => i.kind), ['memory']);
});

test('Settings says where a memory came from and how it is kept', () => {
    assert.equal(memorySubtitle(memory('a')), 'You said this · not used yet');
    assert.equal(memorySubtitle(memory('a', { provenance: 'inferred', use_count: 3, pinned: true, sensitivity: 'local_only' })),
        'Mei worked this out · used 3 times · pinned · local only');
    assert.equal(memorySubtitle(memory('a', { provenance: 'untrusted', use_count: 1 })), 'From something Mei read · used 1 time');
});

test('a real save from the runtime shows as "Remembered", and its undo removes it', () => {
    const real = JSON.parse(readFileSync('protocol/fixtures/agent_remembers.json', 'utf8')) as Fixture & {
        undone_at: number; expect: { conversation_id: string; memory_id: string; text: string; provenance: string };
    };
    const play = (count: number) => {
        const p = new Projection();
        p.applyAttach(real.attach);
        for (const e of real.events.slice(0, count)) assert.notEqual(p.applyEvent(e), 'gap');
        return buildTimeline(p.loaded.get(real.expect.conversation_id)!);
    };
    const saved = play(real.undone_at).filter(i => i.kind === 'memory');
    assert.equal(saved.length, 1);
    assert.ok(saved[0].kind === 'memory' && saved[0].memory.text === real.expect.text
        && saved[0].memory.provenance === real.expect.provenance && saved[0].memory.status === 'active');
    assert.equal(play(real.events.length).filter(i => i.kind === 'memory').length, 0);
});
