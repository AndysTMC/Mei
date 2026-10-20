import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { Projection } from '../src/runtime/projection.js';
import type { AttachReply, Envelope } from '../src/runtime/protocol.js';

interface Fixture {
    attach: AttachReply;
    before?: Envelope[];
    events: Envelope[];
    interrupted_at?: number;
    expect: { conversation_id: string; reply?: string; state: string };
}

function load(name: string): Fixture {
    return JSON.parse(readFileSync(`protocol/v1/fixtures/${name}.json`, 'utf8')) as Fixture;
}

function replay(fx: Fixture): Projection {
    const p = new Projection();
    p.applyAttach(fx.attach);
    for (const e of fx.events) p.applyEvent(e);
    return p;
}

test('completed turn: messages, task state, and no leftover stream', () => {
    const fx = load('turn_completed');
    const p = replay(fx);
    const conv = p.loaded.get(fx.expect.conversation_id);
    assert.ok(conv);
    assert.deepEqual(conv.messages.map(m => m.role), ['user', 'assistant']);
    assert.equal(conv.messages[1].content, fx.expect.reply);
    assert.equal(conv.messages[1].thinking, 'Let me think.');
    assert.equal([...conv.tasks.values()][0].state, 'COMPLETED');
    assert.equal(p.activeTask(fx.expect.conversation_id), null);
    assert.equal(p.streams.size, 0);
    assert.deepEqual(p.summaries().map(s => s.id), [fx.expect.conversation_id]);
});

test('streaming text grows as a prefix of the final reply, and the task blocks input meanwhile', () => {
    const fx = load('turn_completed');
    const p = new Projection();
    p.applyAttach(fx.attach);
    let sawStream = false;
    for (const e of fx.events) {
        assert.notEqual(p.applyEvent(e), 'gap');
        const s = p.streamFor(fx.expect.conversation_id);
        if (s && s.text) {
            sawStream = true;
            assert.ok(fx.expect.reply!.startsWith(s.text));
            assert.ok(p.activeTask(fx.expect.conversation_id));
        }
    }
    assert.ok(sawStream);
});

test('cancelled turn keeps the draft and no assistant message', () => {
    const fx = load('turn_cancelled');
    const p = replay(fx);
    const conv = p.loaded.get(fx.expect.conversation_id)!;
    const task = [...conv.tasks.values()][0];
    assert.equal(task.state, 'CANCELLED');
    assert.ok(task.draft && task.draft.text.length > 0);
    assert.deepEqual(conv.messages.map(m => m.role), ['user']);
});

test('interrupted turn shows its draft, then resumes to completion', () => {
    const fx = load('interrupted_then_resumed');
    const p = new Projection();
    p.applyAttach(fx.attach);
    fx.events.slice(0, fx.interrupted_at).forEach(e => p.applyEvent(e));
    const interrupted = p.interruptedTask(fx.expect.conversation_id);
    assert.ok(interrupted && interrupted.draft && fx.expect.reply!.startsWith(interrupted.draft.text));
    assert.equal(p.activeTask(fx.expect.conversation_id), null); // interrupted doesn't block new input
    fx.events.slice(fx.interrupted_at).forEach(e => p.applyEvent(e));
    const conv = p.loaded.get(fx.expect.conversation_id)!;
    assert.equal(p.interruptedTask(fx.expect.conversation_id), null);
    assert.equal(conv.messages.at(-1)!.content, fx.expect.reply);
    assert.equal([...conv.tasks.values()][0].draft, undefined);
});

test('re-attaching mid-stream shows the partial reply at once and finishes it without gaps', () => {
    const fx = load('reattach_mid_stream');
    const p = new Projection();
    p.applyAttach({ epoch: fx.attach.epoch, seq: 0, mode: 'snapshot', snapshot: { conversations: [] }, streams: [] });
    for (const e of fx.before!) p.applyEvent(e);
    const before = p.streamFor(fx.expect.conversation_id)!.text;
    const results = p.applyAttach(fx.attach);
    assert.ok(!results.includes('gap'));
    const atAttach = p.streamFor(fx.expect.conversation_id)!;
    assert.ok(atAttach.text.length > before.length && fx.expect.reply!.startsWith(atAttach.text));
    let lastStreamText = '';
    for (const e of fx.events) {
        assert.notEqual(p.applyEvent(e), 'gap');
        const s = p.streamFor(fx.expect.conversation_id);
        if (s) lastStreamText = s.text;
    }
    assert.equal(lastStreamText, fx.expect.reply);
    assert.equal(p.loaded.get(fx.expect.conversation_id)!.messages.at(-1)!.content, fx.expect.reply);
});

test('duplicates are dropped and missing events are reported as gaps', () => {
    const fx = load('turn_completed');
    const durable = fx.events.filter(e => e.seq !== null);
    const p = new Projection();
    p.applyAttach(fx.attach);
    assert.equal(p.applyEvent(durable[0]), 'applied');
    assert.equal(p.applyEvent(durable[0]), 'duplicate');
    assert.equal(p.applyEvent(durable[2]), 'gap');
});

test('after a gap the cursor stays put, so a replay from it restores everything in order', () => {
    const fx = load('turn_completed');
    const durable = fx.events.filter(e => e.seq !== null);
    const p = new Projection();
    p.applyAttach(fx.attach);
    p.applyEvent(durable[0]);
    const cursor = p.seq;
    assert.equal(p.applyEvent(durable[3]), 'gap');
    assert.equal(p.seq, cursor);
    const replayed = durable.filter(e => e.seq! > cursor);
    const results = p.applyAttach({ epoch: fx.attach.epoch, seq: durable.at(-1)!.seq!, mode: 'replay', events: replayed, streams: [] });
    assert.ok(results.every(r => r === 'applied'));
    const conv = p.loaded.get(fx.expect.conversation_id)!;
    assert.equal(conv.messages.at(-1)!.content, fx.expect.reply);
});

test('a delta that skips a chunk marks the stream stale', () => {
    const fx = load('turn_completed');
    const p = new Projection();
    p.applyAttach(fx.attach);
    const deltas = fx.events.filter(e => e.type === 'message.delta');
    for (const e of fx.events) {
        if (e === deltas[1]) continue; // drop the second delta
        if (e.type === 'message.completed' && (e.payload.message as { role: string }).role === 'assistant') break;
        p.applyEvent(e);
    }
    assert.equal(p.streamFor(fx.expect.conversation_id)?.stale, true);
});

test('deleting a conversation removes it everywhere', () => {
    const fx = load('turn_completed');
    const p = replay(fx);
    p.applyEvent({ ...fx.events[0], seq: p.seq + 1, type: 'conversation.deleted', payload: { conversation_id: fx.expect.conversation_id } });
    assert.equal(p.conversations.size, 0);
    assert.equal(p.loaded.size, 0);
});
