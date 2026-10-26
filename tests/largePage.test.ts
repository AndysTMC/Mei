import assert from 'node:assert/strict';
import test from 'node:test';

import { attachmentTitle, canOpen } from '../src/runtime/attachment.js';
import type { LoadedConversation } from '../src/runtime/projection.js';
import type { ActionView, Attachment, TaskView } from '../src/runtime/protocol.js';
import { buildTimeline, workingTask, workView } from '../src/runtime/timeline.js';
import { largePageSize } from '../src/ui/popup/pageSize.js';
import { fitted } from '../src/ui/viewers/common.js';
import { cappedNote, fileKind, looksLikeText, MAX_TEXT_BYTES } from '../src/ui/viewers/kind.js';

test('the large page is about 65% of the monitor at 16:10, inside the work area', () => {
    const fullHd = { width: 1920, height: 1080 };
    assert.deepEqual(largePageSize(fullHd, { x: 0, y: 32, width: 1920, height: 1048 }), { width: 1248, height: 780 });
    assert.deepEqual(largePageSize({ width: 1280, height: 800 }, { x: 0, y: 32, width: 1280, height: 768 }),
        { width: 832, height: 520 });
    // A short, wide screen: the height gives way, never past the bottom.
    const wide = largePageSize({ width: 2560, height: 800 }, { x: 0, y: 32, width: 2560, height: 768 });
    assert.equal(wide.width, 1664);
    assert.equal(wide.height, 768 - 16 - 24);
    // A narrow portrait screen: the width keeps clear of the sides.
    const tall = largePageSize({ width: 600, height: 1600 }, { x: 0, y: 32, width: 600, height: 1568 });
    assert.ok(tall.width <= 600 - 48 && tall.height === Math.round(tall.width / 1.6));
});

test('a picture fits its room in its own shape, and is never enlarged', () => {
    assert.deepEqual(fitted({ width: 512, height: 384 }, { width: 1280, height: 800 }), { width: 512, height: 320 });
    assert.deepEqual(fitted({ width: 808, height: 460 }, { width: 1600, height: 1000 }), { width: 736, height: 460 });
    assert.deepEqual(fitted({ width: 808, height: 460 }, { width: 200, height: 100 }), { width: 200, height: 100 });
    assert.equal(fitted({ width: 808, height: 460 }, null), null);
    assert.equal(fitted({ width: 808, height: 460 }, { width: 0, height: 10 }), null);
});

test('a file is shown by its kind: name first, then what the system guessed', () => {
    assert.equal(fileKind('/home/me/notes.txt'), 'text');
    assert.equal(fileKind('/home/me/build.LOG'), 'text');
    assert.equal(fileKind('/home/me/sales.csv'), 'text');
    assert.equal(fileKind('/home/me/main.rs'), 'text');
    assert.equal(fileKind('/home/me/README.md'), 'markdown');
    assert.equal(fileKind('/home/me/photo.JPG'), 'image');
    assert.equal(fileKind('/home/me/paper.pdf'), 'pdf');
    assert.equal(fileKind('/home/me/archive.zip'), 'other');
    assert.equal(fileKind('/home/me/Makefile'), 'text');
    assert.equal(fileKind('/home/me/.bashrc', 'application/x-shellscript'), 'text');
    assert.equal(fileKind('/home/me/notes', 'text/plain'), 'text');
    assert.equal(fileKind('/home/me/scan', 'application/pdf'), 'pdf');
    assert.equal(fileKind('/home/me/blob', 'application/octet-stream'), 'other');
    assert.equal(fileKind('/home/me/Folder', 'inode/directory'), 'other');
});

test('large text shows its start with a note; binary is not text', () => {
    assert.ok(looksLikeText(new TextEncoder().encode('héllo, wörld\n')));
    assert.ok(!looksLikeText(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 13])));
    const size = (n: number) => `${n} B`;
    assert.equal(cappedNote(100, 100, size), null);
    assert.equal(cappedNote(MAX_TEXT_BYTES, MAX_TEXT_BYTES * 4, size),
        `Showing the first ${MAX_TEXT_BYTES} B of ${MAX_TEXT_BYTES * 4} B. Open it in its app for the rest.`);
});

test('what can be opened from the chip or a sent message, and its title', () => {
    const files: Attachment = { kind: 'files', app_id: '', window_title: '', text: '', paths: ['/home/me/a.txt'] };
    const titleOnly: Attachment = { kind: 'selection', app_id: 'org.gnome.TextEditor.desktop', window_title: 'Notes', text: '' };
    const selected: Attachment = { ...titleOnly, text: 'Version 2 drops the importer.' };
    const dropped: Attachment = { kind: 'text', app_id: '', window_title: '', text: 'Some words' };
    assert.ok(canOpen(files) && canOpen(selected) && canOpen(dropped));
    assert.ok(!canOpen(titleOnly) && !canOpen({ ...files, paths: [] }));
    assert.equal(attachmentTitle(selected), 'Notes');
    assert.equal(attachmentTitle({ ...selected, window_title: '' }), 'org.gnome.TextEditor');
    assert.equal(attachmentTitle(dropped), 'Dropped text');
});

function action(over: Partial<ActionView>): ActionView {
    return {
        id: 'a', task_id: 't', batch_id: 'b', message_id: 'm', position: 0, tool: 'desktop_observe',
        capability: 'desktop.observe', description: 'Look at Login', execution: 'SUCCEEDED', verification: 'not_applicable',
        disposition: 'none', decision: 'allow', decision_reason: null, error: null, summary: 'Looked at Login', resources: [],
        undo_recorded: false, created_at: 1, finished_at: 2, ...over,
    };
}

function conversation(task: Partial<TaskView>): LoadedConversation {
    const full: TaskView = { id: 't', conversation_id: 'c', state: 'RUNNING', input_message_id: 'u', error: null,
        created_at: 1, updated_at: 1, ...task };
    return {
        summary: { id: 'c', title: 'Login', created_at: 1, updated_at: 1 },
        messages: [{ id: 'u', conversation_id: 'c', task_id: null, role: 'user', content: 'sign me in', thinking: null,
            metadata: {}, created_at: 1 }],
        tasks: new Map([[full.id, full]]),
        memories: new Map(),
        loadedSeq: 0,
    };
}

test('a running task shows its latest picture above its steps, and the work page follows it', () => {
    const looks = [action({ id: 'a1', pictures: 1, finished_at: 5 }), action({ id: 'a2', pictures: 1, finished_at: 9, position: 1 }),
        action({ id: 'a3', tool: 'desktop_act', capability: 'desktop.act', description: 'Click Continue',
            execution: 'STARTED', finished_at: null, created_at: 10, position: 2 })];
    const conv = conversation({ actions: looks });
    const progress = buildTimeline(conv).find(i => i.kind === 'progress');
    assert.ok(progress?.kind === 'progress');
    assert.equal(progress.picture, 'a2');
    assert.equal(workingTask(conv), 't');
    const view = workView(conv, 't');
    assert.deepEqual(view && [view.phase, view.picture, view.waiting, view.steps.map(s => s.state)],
        ['running', 'a2', null, ['done', 'done', 'running']]);

    const paused = workView(conversation({ actions: looks, state: 'WAITING_RESOURCE', error: 'Paused by you' }), 't');
    assert.deepEqual(paused && [paused.phase, paused.waiting], ['paused', 'Paused by you']);
    const done = conversation({ actions: looks, state: 'COMPLETED' });
    assert.deepEqual(workView(done, 't')?.phase, 'ended');
    assert.equal(workingTask(done), null);
    assert.equal(workView(done, 'another'), null);
    // No picture yet, and no steps either: nothing above the conversation.
    assert.equal(buildTimeline(conversation({ actions: [] })).some(i => i.kind === 'progress'), false);
});
