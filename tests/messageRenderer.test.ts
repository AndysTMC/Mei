import assert from 'node:assert/strict';
import test from 'node:test';

import { formatThinkingPreview, renderMessageBlocks } from '../src/ui/messageRenderer.js';

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

test('renderMessageBlocks bounds hostile paragraph and list actor workloads', () => {
    const paragraphs = Array.from({ length: 500 }, (_value, index) => `paragraph ${index}`).join('\n\n');
    const paragraphModel = renderMessageBlocks(paragraphs, options);
    assert.ok(paragraphModel.blocks.length <= 101);
    assert.match(paragraphModel.blocks.at(-1)?.source ?? '', /popup performance/);
    assert.equal(paragraphModel.originalMarkdown, paragraphs);

    const listSource = Array.from({ length: 2000 }, (_value, index) => `- item ${index}`).join('\n');
    const listModel = renderMessageBlocks(listSource, options);
    const list = listModel.blocks.find(block => block.type === 'unorderedList');
    assert.ok(list && list.type === 'unorderedList');
    assert.ok(list.items.length < 500);
    assert.equal(list.originalItemCount, 2000);
    assert.equal(list.source, listSource);
});

test('renderMessageBlocks bounds a single huge paragraph before parsing', () => {
    const markdown = `start ${'x'.repeat(500_000)} end`;
    const model = renderMessageBlocks(markdown, options);

    assert.equal(model.originalMarkdown, markdown);
    assert.ok(model.stabilizedMarkdown.length < 120_000);
    assert.match(model.blocks.at(-1)?.source ?? '', /popup performance/);
});

test('formatThinkingPreview bounds reasoning labels without changing stored text', () => {
    assert.equal(formatThinkingPreview('short thought'), 'short thought');
    const thinking = 'r'.repeat(100_000);
    const preview = formatThinkingPreview(thinking);
    assert.ok(preview.length < thinking.length);
    assert.match(preview, /truncated for popup performance/);
});

test('renderMessageBlocks bounds table cells while retaining full copy formats', () => {
    const headers = Array.from({ length: 30 }, (_value, index) => `H${index}`);
    const separator = headers.map(() => '---');
    const rows = Array.from({ length: 200 }, (_value, row) =>
        headers.map((_header, column) => `R${row}C${column}`)
    );
    const source = [headers, separator, ...rows]
        .map(row => `| ${row.join(' | ')} |`)
        .join('\n');

    const model = renderMessageBlocks(source, options);
    const table = model.blocks.find(block => block.type === 'table');
    assert.ok(table && table.type === 'table');
    assert.ok((table.rows.length + 1) * table.headers.length <= 500);
    assert.equal(table.originalRowCount, 200);
    assert.equal(table.originalColumnCount, 30);
    assert.match(table.markdown, /R199C29/);
    assert.match(table.csv, /R199C29/);
});
