import assert from 'node:assert/strict';
import test from 'node:test';

import {
    decodeEntities,
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
    assert.equal(inlineMarkup('~~gone~~ *italic* _also_ \\*literal*'), '<s>gone</s> <i>italic</i> <i>also</i> *literal*');
    assert.equal(inlineMarkup('<https://example.test> <mailto:a@example.test>'), '<span underline="single">https://example.test</span> <span underline="single">mailto:a@example.test</span>');
});

test('extractLinks deduplicates links and ignores images or unsafe protocols', () => {
    assert.deepEqual(extractLinks(
        '![img](https://example.test/image.png) [Docs](https://example.test) <mailto:a@example.test> https://example.test'
    ), [
        { label: 'Docs', url: 'https://example.test' },
        { label: 'mailto:a@example.test', url: 'mailto:a@example.test' },
    ]);
    assert.deepEqual(extractLinks('[Nested](https://example.test/a_(b)) https://second.test/path.'), [
        { label: 'Nested', url: 'https://example.test/a_(b)' },
        { label: 'https://second.test/path.', url: 'https://second.test/path.' },
    ]);
});

test('Pango helpers escape text and strip generated tags', () => {
    assert.equal(decodeEntities('&amp;&lt;&gt;&quot;&#39;'), '&<>"\'');
    assert.equal(escapePangoText('a < b & c > d'), 'a &lt; b &amp; c &gt; d');
    assert.equal(stripPangoTags('<b>Hello</b> <span underline="single">link</span>'), 'Hello link');
});
