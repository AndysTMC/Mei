import assert from 'node:assert/strict';
import test from 'node:test';

import {
    escapePangoText,
    extractLinks,
    inlineMarkup,
    sanitizeUrl,
    stripPangoTags,
} from '../src/ui/messageText.js';

test('sanitizeUrl accepts only http, https, and mailto URLs', () => {
    assert.equal(sanitizeUrl(' https://example.test/path?a=1&amp;b=2 '), 'https://example.test/path?a=1&b=2');
    assert.equal(sanitizeUrl('mailto:user@example.test'), 'mailto:user@example.test');
    assert.equal(sanitizeUrl('javascript:alert(1)'), null);
    assert.equal(sanitizeUrl('file:///etc/passwd'), null);
    assert.equal(sanitizeUrl('https://'), null);
    assert.equal(sanitizeUrl('https://example.test', () => false), null);
});

test('inlineMarkup escapes Pango text while preserving supported inline markup', () => {
    assert.equal(
        inlineMarkup('Use **bold** and `<tag>` [ok](https://example.test) <script>'),
        'Use <b>bold</b> and <tt>&lt;tag&gt;</tt> <span underline="single">ok</span> &lt;script&gt;'
    );
    assert.equal(
        inlineMarkup('[bad](javascript:alert(1))'),
        'bad'
    );
});

test('extractLinks deduplicates links and ignores images or unsafe protocols', () => {
    assert.deepEqual(extractLinks(
        '![img](https://example.test/image.png) [Docs](https://example.test) <mailto:a@example.test> https://example.test'
    ), [
        { label: 'Docs', url: 'https://example.test' },
        { label: 'mailto:a@example.test', url: 'mailto:a@example.test' },
    ]);
});

test('Pango helpers escape text and strip generated tags', () => {
    assert.equal(escapePangoText('a < b & c > d'), 'a &lt; b &amp; c &gt; d');
    assert.equal(stripPangoTags('<b>Hello</b> <span underline="single">link</span>'), 'Hello link');
});
