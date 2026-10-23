import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { Projection } from '../src/runtime/projection.js';
import type { ActionView, AttachReply, Envelope, Outcome } from '../src/runtime/protocol.js';
import { activityRow, buildTimeline, latestReply, outcomeLine, pendingInteraction, type TimelineItem } from '../src/runtime/timeline.js';

interface Fixture {
    attach: AttachReply;
    events: Envelope[];
    expect: { conversation_id: string; state: string; outcome: string; task_id: string };
}

const fx = JSON.parse(readFileSync('protocol/fixtures/agent_with_approval.json', 'utf8')) as Fixture;

function replay(until?: (e: Envelope) => boolean): Projection {
    const p = new Projection();
    p.applyAttach(fx.attach);
    for (const e of fx.events) {
        assert.notEqual(p.applyEvent(e), 'gap');
        if (until?.(e)) break;
    }
    return p;
}

test('an agent task: one reply, its steps as progress while it runs, the approval in the input area', () => {
    const waiting = replay(e => e.type === 'approval.requested');
    const id = fx.expect.conversation_id;
    const task = waiting.waitingTask(id);
    assert.ok(task?.approval);
    assert.equal(task.approval.card.capability, 'fs.trash');
    assert.equal(task.approval.card.resources[0].provenance, 'model');
    assert.deepEqual(waiting.needsAttention(), [id]);
    const conv = waiting.loaded.get(id)!;
    const items = buildTimeline(conv);
    // The request and Mei's reply so far ("I'll tidy that."). The step waiting on the person isn't
    // repeated as progress, and the approval isn't in the conversation: it takes over the input area.
    assert.deepEqual(items.map(i => i.kind), ['message', 'message']);
    assert.equal(pendingInteraction(conv)?.kind, 'approval');

    const done = replay();
    const finished = done.loaded.get(id)!.tasks.get(fx.expect.task_id)!;
    assert.equal(finished.state, 'COMPLETED');
    assert.equal(finished.outcome?.kind, 'outcome_verified');
    assert.equal(finished.approval, null);
    assert.deepEqual(done.needsAttention(), []);
    assert.deepEqual(finished.actions?.map(a => [a.capability, a.execution]),
        [['plan.update', 'SUCCEEDED'], ['fs.trash', 'SUCCEEDED'], ['task.finish', 'SUCCEEDED']]);
    const after = buildTimeline(done.loaded.get(id)!);
    // Done: a request and one reply. What Mei said on the way, its steps and its checks are the
    // reply's details, not more messages.
    assert.deepEqual(after.map(i => i.kind), ['message', 'message']);
    const reply = after[1];
    assert.ok(reply.kind === 'message' && reply.details);
    assert.equal(reply.message.role, 'assistant');
    assert.deepEqual(reply.details.steps.map(r => [r.text, r.state]), [['Trashed old.txt', 'done']]);
    assert.equal(reply.details.notes.length, 1); // "I'll tidy that.", said on the way
    assert.equal(outcomeLine(reply.details.outcome!).tone, 'checked');
    assert.equal(pendingInteraction(done.loaded.get(id)!), null);
});

test('the small popup shows the latest reply, or the progress of the request still being worked on', () => {
    const msg = (role: 'user' | 'assistant', content: string): TimelineItem => ({ kind: 'message', message: {
        id: content, conversation_id: 'c', task_id: null, role, content, thinking: null, metadata: {}, created_at: 0 } });
    const progress: TimelineItem = { kind: 'progress', taskId: 't', rows: [] };
    const items = [msg('user', 'q1'), msg('assistant', 'a1'), msg('user', 'q2')];
    assert.deepEqual(latestReply([...items, progress]), [progress]);
    assert.deepEqual(latestReply([...items, msg('assistant', 'a2')]).map(i => i.kind === 'message' && i.message.content), ['a2']);
    assert.deepEqual(latestReply([]), []);
});

function action(over: Partial<ActionView>): ActionView {
    return {
        id: 'a', task_id: 't', batch_id: 'b', message_id: 'm', position: 0, tool: 'fs_move', capability: 'fs.move',
        description: 'Move a to b', execution: 'SUCCEEDED', verification: 'passed', disposition: 'confirmed',
        decision: 'allow', decision_reason: 'user_anchored', error: null, summary: 'Moved a to ~/b', resources: [],
        undo_recorded: true, created_at: 1, finished_at: 2, ...over,
    };
}

test('activity rows say what happened, never more', () => {
    assert.deepEqual(activityRow(action({})), { id: 'a', text: 'Moved a to ~/b', state: 'done', detail: undefined });
    assert.equal(activityRow(action({ verification: 'failed' })).detail, "Mei checked: it didn't take effect");
    assert.deepEqual([activityRow(action({ execution: 'FAILED', error: 'exists' }))].map(r => [r.text, r.state, r.detail]),
        [['Move a to b', 'failed', 'exists']]);
    assert.equal(activityRow(action({ execution: 'DENIED' })).state, 'refused');
    assert.equal(activityRow(action({ execution: 'POLICY_DENIED' })).detail, "Mei's safety rules don't allow this");
    assert.equal(activityRow(action({ execution: 'AWAITING_APPROVAL' })).state, 'waiting');
    assert.equal(activityRow(action({ execution: 'IN_DOUBT' })).state, 'unclear');
    assert.equal(activityRow(action({ execution: 'SUPERSEDED' })).state, 'skipped');
});

test('the outcome line claims only what checks established, in one quiet line', () => {
    const base: Outcome = { kind: 'reported', summary: '', criteria: [], open_issues: [], note: '' };
    const criteria = [{ index: 0, text: 'Dark mode is on', check: 'setting_equals', status: 'passed', detail: '' },
        { index: 1, text: 'Files is open', check: 'window_present', status: 'passed', detail: '' },
        { index: 2, text: 'Renamed', check: null, status: 'reported', detail: '' },
        { index: 3, text: 'Filed', check: 'dir_contains', status: 'failed', detail: 'not in Taxes' }];
    assert.deepEqual(outcomeLine({ ...base, kind: 'outcome_verified', criteria: criteria.slice(0, 2) }),
        { tone: 'checked', text: 'Checked: Dark mode is on · Files is open' });
    assert.deepEqual(outcomeLine({ ...base, kind: 'partially_verified', criteria: criteria.slice(0, 3) }),
        { tone: 'unchecked', text: 'Checked: Dark mode is on · Files is open. Not checked: Renamed' });
    assert.deepEqual(outcomeLine({ ...base, kind: 'partially_verified', criteria, open_issues: ['one left'] }), {
        tone: 'problem',
        text: 'Checked: Dark mode is on · Files is open. Didn’t work: Filed (not in Taxes). Not checked: Renamed. Still open: one left',
    });
    assert.deepEqual(outcomeLine({ ...base, note: "the model didn't report" }),
        { tone: 'unchecked', text: "Not checked by Mei: the model didn't report" });
});
