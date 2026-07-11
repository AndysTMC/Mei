import assert from 'node:assert/strict';
import test from 'node:test';

import {
    extractJsonLines,
    findSseSeparator,
    getSseSeparatorLength,
    getStreamErrorMessage,
    parseSseDataBlock,
    Utf8StreamDecoder,
} from '../src/utils/streamParsers.js';

test('findSseSeparator handles LF, CRLF, and incomplete blocks', () => {
    assert.equal(findSseSeparator('data: one\n\nrest'), 9);
    assert.equal(getSseSeparatorLength('data: one\n\nrest', 9), 2);
    assert.equal(findSseSeparator('data: one\r\n\r\nrest'), 9);
    assert.equal(getSseSeparatorLength('data: one\r\n\r\nrest', 9), 4);
    assert.equal(findSseSeparator('data: one\nstill open'), -1);
    assert.equal(findSseSeparator('\r\n\r\nthen\n\n'), 0);
});

test('parseSseDataBlock joins multi-line data and ignores non-data fields', () => {
    assert.deepEqual(
        parseSseDataBlock('event: message\ndata: {"a":1}\ndata: {"b":2}\nid: 4'),
        ['{"a":1}\n{"b":2}']
    );
    assert.deepEqual(parseSseDataBlock('data: {"final":true}'), ['{"final":true}']);
    assert.deepEqual(parseSseDataBlock(': keepalive\nevent: ping'), []);
    assert.deepEqual(parseSseDataBlock('data:\ndata: second'), ['\nsecond']);
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

test('getStreamErrorMessage recognizes standard streamed API errors', () => {
    assert.equal(getStreamErrorMessage('{"error":{"type":"overloaded_error","message":"Overloaded"}}'), 'Overloaded');
    assert.equal(getStreamErrorMessage('{"error":"request failed"}'), 'request failed');
    assert.equal(getStreamErrorMessage('{"choices":[]}'), null);
    assert.equal(getStreamErrorMessage('{"error":{"type":"overloaded_error"}}'), 'overloaded_error');
    assert.equal(getStreamErrorMessage('{"error":{}}'), null);
    assert.equal(getStreamErrorMessage('[]'), null);
    assert.equal(getStreamErrorMessage('not json'), null);
});

test('Utf8StreamDecoder preserves characters split across network chunks', () => {
    const bytes = new TextEncoder().encode('Hello 🌸 café');
    const decoder = new Utf8StreamDecoder();
    const parts = [
        decoder.decode(bytes.slice(0, 7)),
        decoder.decode(bytes.slice(7, 9)),
        decoder.decode(bytes.slice(9, 12)),
        decoder.decode(bytes.slice(12)),
        decoder.decode(),
    ];
    assert.equal(parts.join(''), 'Hello 🌸 café');
});

test('Utf8StreamDecoder flushes incomplete and invalid byte sequences safely', () => {
    const decoder = new Utf8StreamDecoder();
    assert.equal(decoder.decode(new Uint8Array([0xf0, 0x9f])), '');
    assert.equal(decoder.decode(new Uint8Array([0x8c, 0xb8])), '🌸');
    assert.equal(decoder.decode(), '');

    const incomplete = new Utf8StreamDecoder();
    incomplete.decode(new Uint8Array([0xe2, 0x82]));
    assert.equal(incomplete.decode(), '�');
});
