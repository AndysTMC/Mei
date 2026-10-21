import assert from 'node:assert/strict';
import test from 'node:test';

import { MAX_ATTACHMENT_CHARS, attachmentLabel, attachmentOf, makeAttachment } from '../src/runtime/attachment.js';

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
