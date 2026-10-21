import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { QUICK_MS, activeLabel, noticeFor, reaction } from '../src/runtime/notices.js';
import { Projection } from '../src/runtime/projection.js';
import type { AttachReply, ConversationSummary, Envelope } from '../src/runtime/protocol.js';

interface Fixture {
    attach: AttachReply;
    events: Envelope[];
    expect: { conversation_id: string };
}

const fx = JSON.parse(readFileSync('protocol/fixtures/agent_with_approval.json', 'utf8')) as Fixture;
const id = fx.expect.conversation_id;

function replay(until?: (e: Envelope) => boolean): Projection {
    const p = new Projection();
    p.applyAttach(fx.attach);
    for (const e of fx.events) {
        p.applyEvent(e);
        if (until?.(e)) break;
    }
    return p;
}

function event(type: string, payload: Record<string, unknown>, conversation_id: string | null = id): Envelope {
    return { v: 2, type, event_id: 'e', epoch: 'x', at: '', required: false, seq: null, conversation_id, task_id: 't', payload };
}

const finished = (state: string, extra: Record<string, unknown> = {}) => event('task.finished', { state, ...extra });
const chat: ConversationSummary = { id, title: 'Tidy the downloads', created_at: 0, updated_at: 0 };

test('a quick answer reopens the popup; a long task, or another chat, notifies; a chat in view does neither', () => {
    const done = finished('COMPLETED');
    assert.equal(reaction(done, { showing: true, current: true, elapsedMs: 1_000 }), 'none');
    assert.equal(reaction(done, { showing: false, current: true, elapsedMs: 1_000 }), 'open');
    assert.equal(reaction(done, { showing: false, current: true, elapsedMs: QUICK_MS }), 'notify');
    assert.equal(reaction(done, { showing: false, current: false, elapsedMs: null }), 'notify');
    const ask = event('approval.requested', {});
    assert.equal(reaction(ask, { showing: false, current: true, elapsedMs: 5 * 60_000 }), 'notify');
});

test('a stop, a restart, or progress is nothing to notify about', () => {
    const away = { showing: false, current: false, elapsedMs: null };
    for (const e of [finished('CANCELLED'), finished('INTERRUPTED'), event('task.state_changed', { to: 'RUNNING' })]) {
        assert.equal(reaction(e, away), 'none');
        assert.equal(noticeFor(e, chat), null);
    }
});

test('notices name the chat and say what happened or what is asked', () => {
    const done = noticeFor(finished('COMPLETED', { outcome: { summary: 'Moved 3 files to Trash' } }), chat);
    assert.deepEqual(done, { conversationId: id, title: 'Mei finished', body: 'Tidy the downloads\nMoved 3 files to Trash', review: false });
    const failed = noticeFor(finished('FAILED', { error: 'The model provider is unreachable.' }), chat);
    assert.equal(failed?.title, 'Mei couldn’t finish');
    assert.match(failed?.body ?? '', /unreachable/);
    const ask = noticeFor(event('approval.requested', { approval: { card: { title: 'Move old.txt to Trash' } } }), chat);
    assert.equal(ask?.review, true);
    assert.equal(ask?.body, 'Tidy the downloads\nMove old.txt to Trash');
    const question = noticeFor(event('input.requested', { request: { spec: { question: 'Which folder?' } } }), undefined);
    assert.equal(question?.body, 'Mei\nWhich folder?');
    const long = noticeFor(finished('COMPLETED', { outcome: { summary: 'x'.repeat(1000) } }), chat);
    assert.ok((long?.body.length ?? 0) <= 240 && long?.body.endsWith('…'));
});

test('the history list follows each task in progress, loaded or not', () => {
    const waiting = replay(e => e.type === 'task.state_changed' && e.payload.to === 'WAITING_APPROVAL');
    assert.equal(waiting.conversations.get(id)?.active, 'WAITING_APPROVAL');
    assert.equal(activeLabel(waiting.conversations.get(id)?.active), 'Needs you');
    assert.deepEqual(waiting.needsAttention(), [id]);
    assert.equal(waiting.anyWorking(), false);

    const working = replay(e => e.type === 'task.state_changed' && e.payload.to === 'VERIFYING');
    assert.equal(activeLabel(working.conversations.get(id)?.active), 'Working…');
    assert.equal(working.anyWorking(), true);

    const done = replay();
    assert.equal(done.conversations.get(id)?.active, null);
    assert.equal(activeLabel(done.conversations.get(id)?.active), null);
    assert.equal(done.anyWorking(), false);

    // A conversation known only from the snapshot (never opened) is tracked from its events too.
    const p = new Projection();
    p.applyAttach({ ...fx.attach, snapshot: { conversations: [{ ...chat, active: 'INTERRUPTED' }] } });
    assert.equal(activeLabel(p.conversations.get(id)?.active), 'Interrupted');
    p.applyEvent({ ...event('task.state_changed', { to: 'RUNNING' }), seq: fx.attach.seq + 1 });
    assert.equal(p.anyWorking(), true);
    assert.equal(p.loaded.has(id), false);
});
