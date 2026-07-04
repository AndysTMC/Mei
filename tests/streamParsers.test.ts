import assert from 'node:assert/strict';
import test from 'node:test';

import {
    extractJsonLines,
    findSseSeparator,
    getSseSeparatorLength,
    parseSseDataBlock,
} from '../src/utils/streamParsers.js';

test('findSseSeparator handles LF, CRLF, and incomplete blocks', () => {
    assert.equal(findSseSeparator('data: one\n\nrest'), 9);
    assert.equal(getSseSeparatorLength('data: one\n\nrest', 9), 2);
    assert.equal(findSseSeparator('data: one\r\n\r\nrest'), 9);
    assert.equal(getSseSeparatorLength('data: one\r\n\r\nrest', 9), 4);
    assert.equal(findSseSeparator('data: one\nstill open'), -1);
});

test('parseSseDataBlock joins multi-line data and ignores non-data fields', () => {
    assert.deepEqual(
        parseSseDataBlock('event: message\ndata: {"a":1}\ndata: {"b":2}\nid: 4'),
        ['{"a":1}\n{"b":2}']
    );
    assert.deepEqual(parseSseDataBlock('data: {"final":true}'), ['{"final":true}']);
    assert.deepEqual(parseSseDataBlock(': keepalive\nevent: ping'), []);
});

test('extractJsonLines emits complete lines and preserves trailing partial data', () => {
    assert.deepEqual(
        extractJsonLines(' {"a":1}\r\n\n{"b":2}\n{"partial"'),
        {
            lines: ['{"a":1}', '{"b":2}'],
            rest: '{"partial"',
        }
    );
});
