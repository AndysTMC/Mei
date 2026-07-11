import assert from 'node:assert/strict';
import test from 'node:test';

import { renderMessageBlocks } from '../src/ui/messageRenderer.js';

const options = { role: 'assistant' as const, expanded: true, allowImages: false, enableMath: true };

test('renderMessageBlocks parses all supported block-level constructs', () => {
    const markdown = [
        '# Heading',
        '',
        'Paragraph **bold**.',
        '',
        '> quoted',
        '> text',
        '',
        '- [x] done',
        '- [ ] pending',
        '',
        '1. first',
        '2. second',
        '',
        '| A | B |',
        '| :--- | ---: |',
        '| 1 | 2 |',
        '',
        '```ts',
        'const n = 1;',
        '```',
        '',
        '$$',
        'x^2',
        '$$',
        '',
        '[^note]: footnote',
        '[1] citation',
        '---',
    ].join('\n');

    const model = renderMessageBlocks(markdown, options);
    assert.deepEqual(model.blocks.map(block => block.type), [
        'heading', 'paragraph', 'blockquote', 'unorderedList', 'orderedList',
        'table', 'codeBlock', 'mathBlock', 'footnoteDef', 'citation', 'horizontalRule',
    ]);
    assert.equal(model.role, 'assistant');
    assert.match(model.plainText, /const n = 1;/);

    const table = model.blocks.find(block => block.type === 'table');
    assert.ok(table && table.type === 'table');
    assert.deepEqual(table.alignments, ['left', 'right']);
    assert.deepEqual(table.rows, [['1', '2']]);
    assert.equal(table.csv, 'A,B\n1,2');
});

test('renderMessageBlocks marks unfinished streaming code and math blocks', () => {
    const code = renderMessageBlocks('```js\nconst x = 1;', { ...options, streaming: true });
    assert.equal(code.isStreaming, true);
    assert.equal(code.blocks[0].type, 'codeBlock');
    assert.equal(code.blocks[0].type === 'codeBlock' && code.blocks[0].isStreaming, true);

    const math = renderMessageBlocks('$$\nx + y', { ...options, streaming: true });
    assert.equal(math.blocks[0].type, 'mathBlock');
    assert.equal(math.blocks[0].type === 'mathBlock' && math.blocks[0].isStreaming, true);
});

test('renderMessageBlocks normalizes line endings and honors feature switches', () => {
    const model = renderMessageBlocks('hello\r\nworld\rnext', {
        ...options,
        enableMath: false,
        streaming: false,
    });
    assert.equal(model.stabilizedMarkdown, 'hello\nworld\nnext');
    assert.equal(model.isStreaming, false);
    assert.equal(model.blocks[0].type, 'paragraph');
});

test('renderMessageBlocks returns isolated models for streaming updates', () => {
    const first = renderMessageBlocks('same', { ...options, streaming: true });
    const second = renderMessageBlocks('same', { ...options, streaming: true });
    assert.notEqual(first, second);
});
