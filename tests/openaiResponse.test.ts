import assert from 'node:assert/strict';
import test from 'node:test';

import {
    extractOpenAIResponseParts,
    OpenAIStreamNormalizer,
    separateGluedReasoningBlocks,
} from '../src/providers/openaiResponse.js';

test('extractOpenAIResponseParts normalizes typed content and reasoning details', () => {
    assert.deepEqual(extractOpenAIResponseParts({
        choices: [{
            message: {
                content: [
                    { type: 'thinking', thinking: 'typed thought' },
                    { type: 'text', text: 'Final ' },
                    { type: 'output_text', text: 'answer' },
                ],
                reasoning: 'structured thought',
                reasoning_details: [
                    { type: 'reasoning.summary', summary: 'summary thought' },
                    { type: 'reasoning.summary', summary: 'structured thought' },
                ],
            },
        }],
    }), {
        content: 'Final answer',
        thinking: 'structured thought\n\nsummary thought\n\ntyped thought',
    });
});

test('extractOpenAIResponseParts removes inline reasoning from the visible answer', () => {
    assert.deepEqual(extractOpenAIResponseParts({
        choices: [{ message: { content: '<think>private</think>\nVisible' } }],
    }), {
        content: '\nVisible',
        thinking: 'private',
    });
    assert.deepEqual(extractOpenAIResponseParts({
        choices: [{ text: 'legacy text fallback' }],
    }), {
        content: 'legacy text fallback',
        thinking: '',
    });
});

test('extractOpenAIResponseParts handles malformed, unclosed, and orphan tag shapes', () => {
    assert.deepEqual(extractOpenAIResponseParts(null), { content: '', thinking: '' });
    assert.deepEqual(extractOpenAIResponseParts({ choices: [null] }), { content: '', thinking: '' });
    assert.deepEqual(extractOpenAIResponseParts({
        choices: [{ message: { content: 'Visible\n  <THOUGHT>unfinished private' } }],
    }), {
        content: 'Visible\n',
        thinking: 'unfinished private',
    });
    assert.deepEqual(extractOpenAIResponseParts({
        choices: [{ message: { content: 'Visible</thinking>\nanswer' } }],
    }), {
        content: 'Visibleanswer',
        thinking: '',
    });
});

test('OpenAIStreamNormalizer separates split inline reasoning tags', () => {
    const normalizer = new OpenAIStreamNormalizer();
    const updates = [
        normalizer.consume({ choices: [{ delta: { content: '<thi' } }] }),
        normalizer.consume({ choices: [{ delta: { content: 'nk>private' } }] }),
        normalizer.consume({ choices: [{ delta: { content: '</think>\nVisible' } }] }),
        normalizer.flush(),
    ];

    assert.equal(updates.map(update => update.contentDelta ?? '').join(''), '\nVisible');
    assert.equal(updates.map(update => update.thinkingDelta ?? '').join(''), 'private');
});

test('OpenAIStreamNormalizer preserves literal tag mentions and flushes partial prose', () => {
    const normalizer = new OpenAIStreamNormalizer();
    const first = normalizer.consume({ choices: [{ delta: { content: 'Use <think> tags and x <' } }] });
    const tail = normalizer.flush();

    assert.equal((first.contentDelta ?? '') + (tail.contentDelta ?? ''), 'Use <think> tags and x <');
    assert.equal(first.thinkingDelta ?? '', '');
});

test('OpenAIStreamNormalizer removes a bounded inline reasoning pair mid-sentence', () => {
    const normalizer = new OpenAIStreamNormalizer();
    const update = normalizer.consume({
        choices: [{ delta: { content: 'Before <reasoning>private</reasoning> after' } }],
    });

    assert.equal(update.contentDelta, 'Before  after');
    assert.equal(update.thinkingDelta, 'private');
});

test('OpenAIStreamNormalizer handles typed blocks and reasoning details', () => {
    const normalizer = new OpenAIStreamNormalizer();
    const update = normalizer.consume({ choices: [{ delta: {
        content: [
            null,
            { type: 'thinking', text: 'typed thought' },
            { type: 'output_text', output_text: 'answer' },
        ],
        reasoning_details: [{ summary: 'summary thought' }, null],
    } }] });

    assert.equal(update.contentDelta, 'answer');
    assert.equal(update.thinkingDelta, 'summary thought\n\ntyped thought');
});

test('OpenAIStreamNormalizer handles split closing tags and resets after an unclosed block', () => {
    const normalizer = new OpenAIStreamNormalizer();
    const updates = [
        normalizer.consume({ choices: [{ delta: { content: '<reasoning>private</reas' } }] }),
        normalizer.consume({ choices: [{ delta: { content: 'oning>visible' } }] }),
        normalizer.flush(),
        normalizer.consume({ choices: [{ delta: { content: ' next' } }] }),
    ];
    assert.equal(updates.map(update => update.contentDelta).join(''), 'visible next');
    assert.equal(updates.map(update => update.thinkingDelta).join(''), 'private');

    const unclosed = new OpenAIStreamNormalizer();
    const thought = unclosed.consume({ choices: [{ delta: { content: '<think>private' } }] });
    const discardedTail = unclosed.flush();
    const visible = unclosed.consume({ choices: [{ delta: { content: 'answer' } }] });
    assert.equal(thought.thinkingDelta, 'private');
    assert.equal(discardedTail.contentDelta, '');
    assert.equal(visible.contentDelta, 'answer');
});

test('OpenAIStreamNormalizer joins structured summary blocks readably', () => {
    const normalizer = new OpenAIStreamNormalizer();
    const first = normalizer.consume({ choices: [{ delta: { reasoning_content: '**First**body' } }] });
    const second = normalizer.consume({ choices: [{ delta: { reasoning_content: '**Second**body' } }] });

    assert.equal(first.thinkingDelta, '**First**body');
    assert.equal(second.thinkingDelta, '\n\n**Second**body');
    assert.equal(separateGluedReasoningBlocks('token ', '**fragment'), '**fragment');
});

test('OpenAIStreamNormalizer preserves whitespace-only reasoning deltas', () => {
    const normalizer = new OpenAIStreamNormalizer();
    const updates = ['first', ' ', 'second'].map(reasoning_content => normalizer.consume({
        choices: [{ delta: { reasoning_content } }],
    }));
    assert.equal(updates.map(update => update.thinkingDelta).join(''), 'first second');
});
