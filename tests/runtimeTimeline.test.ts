import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { Projection } from '../src/runtime/projection.js';
import type { ActionView, AttachReply, ConversationSummary, Envelope, Outcome, TaskView } from '../src/runtime/protocol.js';
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

test('a task paused for the person shows in the input area until it goes on', () => {
    const p = replay();
    const id = fx.expect.conversation_id;
    const conv = p.loaded.get(id)!;
    const task = conv.tasks.get(fx.expect.task_id)!;
    task.state = 'WAITING_RESOURCE';
    task.error = 'Paused while you use the computer';
    assert.deepEqual(pendingInteraction(conv), { kind: 'paused', taskId: task.id, note: 'Paused while you use the computer' });
    task.state = 'RUNNING';
    task.error = null;
    assert.equal(pendingInteraction(conv), null);
});

/** A conversation built by hand: messages in their order, and one task. */
function conversation(messages: [string, 'user' | 'assistant', string | null, string, number][], task: Partial<TaskView>) {
    const t: TaskView = { id: 't', conversation_id: 'c', state: 'COMPLETED', input_message_id: 'm1', error: null,
        created_at: 1, updated_at: 9, ...task };
    return {
        summary: { id: 'c', title: '', created_at: 1, updated_at: 9, active: null } as unknown as ConversationSummary,
        messages: messages.map(([id, role, taskId, content, at]) => ({ id, conversation_id: 'c', task_id: taskId, role,
            content, thinking: null, metadata: {}, created_at: at })),
        tasks: new Map([[t.id, t]]), memories: new Map(), loadedSeq: 0,
    };
}

const shown = (items: TimelineItem[]) => items.map(i => (i.kind === 'message' ? `${i.message.role}: ${i.message.content}` : i.kind));

test('what the person says while Mei works comes before the reply that follows it, each answered in turn', () => {
    // From the owner's chats: a spoken request, Mei acting, more said by voice while it worked, then its reply.
    const conv = conversation([
        ['m1', 'user', null, 'Open a new tab in Chrome', 1],
        ['m2', 'assistant', 't', "I'll open a tab.", 2],
        ['m3', 'user', 't', 'Just type Antigravity into it', 5],
        ['m4', 'assistant', 't', 'Typing it now.', 6],
        ['m5', 'assistant', 't', "Done: it's open and searching.", 8],
    ], { actions: [action({ id: 'a1', created_at: 3, summary: 'Opened a tab' }),
        action({ id: 'a2', created_at: 7, summary: 'Typed Antigravity' })] });
    const items = buildTimeline(conv);
    assert.deepEqual(shown(items), ['user: Open a new tab in Chrome', "assistant: I'll open a tab.",
        'user: Just type Antigravity into it', "assistant: Done: it's open and searching."]);
    const [, first, , last] = items;
    assert.ok(first.kind === 'message' && last.kind === 'message');
    assert.deepEqual(first.details?.steps.map(s => s.text), ['Opened a tab']); // each reply has what was done for it
    assert.deepEqual(last.details?.steps.map(s => s.text), ['Typed Antigravity']);
    assert.deepEqual(last.details?.notes, ['Typing it now.']);
    // The small popup: the reply to the latest thing the person said, not nothing.
    assert.deepEqual(shown(latestReply(items)), ["assistant: Done: it's open and searching."]);
});

test('while Mei still works after the person spoke again, its progress follows what they said', () => {
    const conv = conversation([
        ['m1', 'user', null, 'Open a new tab in Chrome', 1],
        ['m2', 'assistant', 't', "I'll open a tab.", 2],
        ['m3', 'user', 't', 'Just type Antigravity into it', 5],
    ], { state: 'RUNNING', actions: [action({ id: 'a1', created_at: 3 }), action({ id: 'a2', created_at: 6, execution: 'STARTED' })] });
    assert.deepEqual(shown(buildTimeline(conv)), ['user: Open a new tab in Chrome', "assistant: I'll open a tab.",
        'user: Just type Antigravity into it', 'progress']);
});

test('a running task that has said something shows its reply so far and the steps it is taking', () => {
    const conv = conversation([
        ['m1', 'user', null, 'Tidy my Downloads', 1],
        ['m2', 'assistant', 't', "I'll tidy that.", 2],
    ], { state: 'RUNNING', actions: [action({ id: 'a1', created_at: 3, execution: 'STARTED', description: 'Move a' })] });
    const items = buildTimeline(conv);
    assert.deepEqual(shown(items), ['user: Tidy my Downloads', "assistant: I'll tidy that.", 'progress']);
    const progress = items[2];
    assert.ok(progress.kind === 'progress');
    assert.deepEqual(progress.rows.map(r => [r.text, r.state]), [['Move a', 'running']]);
});
