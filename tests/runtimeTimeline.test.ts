import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { Projection } from '../src/runtime/projection.js';
import type { ActionView, AttachReply, Envelope, Outcome } from '../src/runtime/protocol.js';
import { activityRow, buildTimeline, outcomeLine } from '../src/runtime/timeline.js';

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

test('an agent task: actions, the approval card while it waits, and the outcome after', () => {
    const waiting = replay(e => e.type === 'approval.requested');
    const id = fx.expect.conversation_id;
    const task = waiting.waitingTask(id);
    assert.ok(task?.approval);
    assert.equal(task.approval.card.capability, 'fs.trash');
    assert.equal(task.approval.card.resources[0].provenance, 'model');
    assert.deepEqual(waiting.needsAttention(), [id]);
    const kinds = buildTimeline(waiting.loaded.get(id)!).map(i => i.kind);
    assert.deepEqual(kinds, ['message', 'plan', 'message', 'activity', 'approval']);

    const done = replay();
    const finished = done.loaded.get(id)!.tasks.get(fx.expect.task_id)!;
    assert.equal(finished.state, 'COMPLETED');
    assert.equal(finished.outcome?.kind, 'outcome_verified');
    assert.equal(finished.approval, null);
    assert.deepEqual(done.needsAttention(), []);
    assert.deepEqual(finished.actions?.map(a => [a.capability, a.execution]),
        [['plan.update', 'SUCCEEDED'], ['fs.trash', 'SUCCEEDED'], ['task.finish', 'SUCCEEDED']]);
    const items = buildTimeline(done.loaded.get(id)!);
    // Done: the plan gives way to one outcome line (no second "message" restating it).
    assert.deepEqual(items.map(i => i.kind), ['message', 'message', 'activity', 'message', 'outcome']);
    const activity = items.find(i => i.kind === 'activity');
    assert.ok(activity?.kind === 'activity');
    assert.deepEqual(activity.rows.map(r => [r.text, r.state]), [['Trashed old.txt', 'done']]);
    const outcome = items.find(i => i.kind === 'outcome');
    assert.ok(outcome?.kind === 'outcome');
    assert.equal(outcomeLine(outcome.outcome).tone, 'checked');
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
