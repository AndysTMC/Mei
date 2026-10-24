import assert from 'node:assert/strict';
import test from 'node:test';

import {
    MAX_ATTACHMENT_CHARS, MAX_DROPPED_FILES, attachmentLabel, attachmentOf, decodeDrop, encodeDrop, makeAttachment, withDrop,
} from '../src/runtime/attachment.js';

test('nothing focused and nothing selected attaches nothing', () => {
    assert.equal(makeAttachment('', '  ', ''), null);
    assert.equal(makeAttachment('org.gnome.Nautilus.desktop', '', '   \n'), null);
});

test('the selection is clipped to what the runtime accepts, and the chip says where it came from', () => {
    const a = makeAttachment('firefox.desktop', '  Release notes — Mozilla Firefox ', 'x'.repeat(MAX_ATTACHMENT_CHARS + 50));
    assert.ok(a);
    assert.equal(a.text.length, MAX_ATTACHMENT_CHARS);
    assert.equal(a.window_title, 'Release notes — Mozilla Firefox');
    assert.match(attachmentLabel(a), /^About: Release notes — Mozilla Firefox — “x+…”$/);
    assert.equal(attachmentLabel({ kind: 'selection', app_id: 'org.gnome.TextEditor.desktop', window_title: '', text: '' }),
        'About: org.gnome.TextEditor');
    assert.equal(attachmentLabel({ kind: 'selection', app_id: '', window_title: 'Notes', text: 'two\n\nlines' }),
        'About: Notes — “two lines”');
});

test('a sent message carries its attachment in its metadata', () => {
    const a = { kind: 'selection', app_id: 'a', window_title: 'T', text: 'x' };
    assert.deepEqual(attachmentOf({ attachment: a }), a);
    assert.equal(attachmentOf({}), null);
});

test('dropped files join files already attached, each once and up to the runtime limit', () => {
    const one = withDrop(null, { kind: 'files', paths: ['/home/me/notes.txt'] });
    assert.deepEqual(one, { kind: 'files', app_id: '', window_title: '', text: '', paths: ['/home/me/notes.txt'] });
    assert.ok(one);
    assert.equal(attachmentLabel(one), 'Attached: notes.txt');
    const two = withDrop(one, { kind: 'files', paths: ['/home/me/notes.txt', '/home/me/Invoices'] });
    assert.ok(two);
    assert.equal(attachmentLabel(two), 'Attached: notes.txt, Invoices');
    const many = withDrop(two, { kind: 'files', paths: Array.from({ length: 30 }, (_, i) => `/home/me/${i}.txt`) });
    assert.ok(many);
    assert.equal(many.paths?.length, MAX_DROPPED_FILES);
    assert.equal(attachmentLabel(many), `Attached: notes.txt and ${MAX_DROPPED_FILES - 1} more`);
});

test('a drop replaces a selection, and a drop with nothing usable changes nothing', () => {
    const selection = makeAttachment('firefox.desktop', 'Page', 'words');
    const files = withDrop(selection, { kind: 'files', paths: ['/home/me/a.txt'] });
    assert.equal(files?.kind, 'files');
    assert.equal(withDrop(selection, { kind: 'files', paths: ['relative.txt', '/home/me/../etc/passwd', '/a//b'] }), selection);
    assert.equal(withDrop(files, { kind: 'text', text: '   ' }), files);
    const text = withDrop(files, { kind: 'text', text: 'Some words\nfrom a page' });
    assert.ok(text);
    assert.equal(text.kind, 'text');
    assert.equal(attachmentLabel(text), 'About: “Some words from a page”');
});

test('the drop window’s lines are checked, not trusted', () => {
    const drop = { kind: 'files', paths: ['/home/me/a b.txt'] } as const;
    assert.deepEqual(decodeDrop(encodeDrop(drop)), drop);
    assert.deepEqual(decodeDrop(encodeDrop({ kind: 'text', text: 'x'.repeat(MAX_ATTACHMENT_CHARS + 9) }))?.kind, 'text');
    assert.equal((decodeDrop(encodeDrop({ kind: 'text', text: 'x'.repeat(MAX_ATTACHMENT_CHARS + 9) })) as { text: string }).text.length,
        MAX_ATTACHMENT_CHARS);
    assert.deepEqual(decodeDrop('{"kind":"files","paths":["/ok","nope"]}'), { kind: 'files', paths: ['/ok'] });
    for (const bad of ['', 'not json', '42', 'null', '{"kind":"files","paths":[1]}', '{"kind":"run","text":"x"}'])
        assert.equal(decodeDrop(bad), null);
});
