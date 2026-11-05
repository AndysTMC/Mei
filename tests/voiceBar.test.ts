import assert from 'node:assert/strict';
import test from 'node:test';

import { LOOKS, VoiceBarModel, type BarState, type Frame } from '../src/ui/conversation/voiceBarModel.js';

const STEP = 25;

/** Run the model at 60 fps for `ms`, feeding `level` from `source` the way the runtime does. */
function run(model: VoiceBarModel, ms: number, width: number, source: 'mic' | 'mei', level: () => number, from = 0) {
    const frames = [];
    for (let now = from; now < from + ms; now += 1000 / 60) {
        if (Math.round(now) % 100 < 17) model.push(source, [level(), level(), level(), level()], STEP, now);
        frames.push(model.frame(now, width));
    }
    return frames;
}

for (const state of ['listening', 'thinking', 'speaking'] as BarState[]) {
    for (const width of [90, 372, 900]) {
        test(`${state} at ${width}px: dots stay inside the bar whatever the sound`, () => {
            const model = new VoiceBarModel();
            model.setState(state);
            const source = state === 'speaking' ? 'mei' : 'mic';
            // Full scale, silence, then sharp bursts: the springs' hardest overshoot.
            const loud = run(model, 2000, width, source, () => 1);
            const burst = run(model, 3000, width, source, () => (Math.random() < 0.5 ? 1 : 0), 2000);
            for (const frame of [...loud, ...burst]) {
                const inner = frame.height - 2 * Math.max(2, frame.height * 0.14);
                for (const dot of frame.dots) {
                    assert.ok(dot.height <= Math.max(inner, dot.width) + 1e-6, `taller than the bar: ${dot.height}`);
                    assert.ok(dot.x >= frame.height / 2 - 1e-6 && dot.x <= width - frame.height / 2 + 1e-6,
                        `past the rounded end: ${dot.x}`);
                    assert.ok(dot.alpha >= 0 && dot.alpha <= 1);
                }
            }
        });
    }
}

/** How far the outermost dot is from the middle, and the tallest dot. */
const outer = (f: Frame, width: number) => Math.max(...f.dots.map(d => Math.abs(d.x - width / 2)));
const tallest = (f: Frame) => Math.max(...f.dots.map(d => d.height));

test('the person talking moves the dots; what Mei says does not while listening', () => {
    const model = new VoiceBarModel();
    const still = run(model, 1000, 372, 'mei', () => 1).at(-1)!;
    const moved = run(model, 400, 372, 'mic', () => 0.9, 1000).at(-1)!;
    assert.ok(outer(moved, 372) > outer(still, 372) * 1.3, `${outer(moved, 372)} vs ${outer(still, 372)}`);
    assert.ok(tallest(moved) > tallest(still) * 1.2, `${tallest(moved)} vs ${tallest(still)}`);
});

test('a room\'s hum and Mei\'s steady voice leave the dots round and still', () => {
    const quiet = new VoiceBarModel();
    const hum = run(quiet, 2000, 372, 'mic', () => 0.2 + Math.random() * 0.05).slice(-30);
    for (const f of hum) for (const d of f.dots) assert.ok(d.height < d.width * 1.05, `stretched by hum: ${d.height}`);
    const speaking = new VoiceBarModel(false, 'speaking');
    const steady = run(speaking, 2000, 372, 'mei', () => 0.5 + Math.random() * 0.1).slice(-30);
    for (const f of steady) for (const d of f.dots) assert.ok(d.height < d.width * 1.25, `stretched while speaking: ${d.height}`);
});

test('every state draws the same bar height, so nothing around it moves', () => {
    assert.equal(new Set(Object.values(LOOKS).map(l => l.bar)).size, 1);
});

test('thinking and pausing keep their dots round: the wave only brightens them', () => {
    for (const state of ['thinking', 'listening'] as BarState[]) {
        const model = new VoiceBarModel(false, state);
        for (const f of run(model, 3000, 372, 'mic', () => 0).slice(-60))
            for (const d of f.dots) assert.ok(Math.abs(d.height - d.width) < 0.01, `${state}: ${d.height} vs ${d.width}`);
    }
});

test('speaking follows Mei and fills the bar; a pause in listening settles to the pausing look', () => {
    const model = new VoiceBarModel();
    model.setState('speaking');
    const speaking = run(model, 1500, 372, 'mei', () => 0.8).at(-1)!;
    assert.ok(speaking.filled > 0.99 && Math.abs(speaking.height - LOOKS.speaking.bar) < 0.5);
    model.setState('listening');
    const quiet = run(model, 1500, 372, 'mic', () => 0, 1500).at(-1)!;
    assert.ok(quiet.filled < 0.01 && Math.abs(quiet.height - LOOKS.pausing.bar) < 0.5);
});

test('thinking shows its own number of dots, the others fading out', () => {
    const model = new VoiceBarModel();
    model.setState('thinking');
    const frame = run(model, 1500, 372, 'mic', () => 0).at(-1)!;
    assert.equal(frame.dots.length, LOOKS.thinking.dots);
});

test('with animations off, the dots stay where they are', () => {
    const model = new VoiceBarModel(true);
    const frames = run(model, 1500, 372, 'mic', () => (Math.random() < 0.5 ? 1 : 0.2));
    const last = frames.slice(-30);
    for (const f of last) {
        assert.deepEqual(f.dots.map(d => [d.x.toFixed(3), d.height.toFixed(3)]),
            last[0].dots.map(d => [d.x.toFixed(3), d.height.toFixed(3)]));
    }
});

test('a hiccup in the microphone does not leave the bar seconds behind', () => {
    const model = new VoiceBarModel();
    for (let i = 0; i < 20; i++) model.push('mic', [1, 1, 1, 1], STEP, 0); // two seconds' worth at once
    model.push('mic', [0, 0, 0, 0], STEP, 400); // later arrivals play from now, not after the backlog
    model.frame(0, 372);
    run(model, 1200, 372, 'mic', () => 0, 400);
    const settled = model.frame(1700, 372);
    assert.ok(Math.max(...settled.dots.map(d => d.height)) < LOOKS.pausing.bar * 0.6);
});

test('a bar made while Mei is speaking starts in the speaking look and follows Mei', () => {
    const model = new VoiceBarModel(false, 'speaking');
    assert.equal(model.state, 'speaking');
    assert.ok(model.frame(0, 372).filled > 0.99);
    const quiet = outer(model.frame(20, 372), 372);
    const loud = run(model, 400, 372, 'mei', () => 1, 40).at(-1)!;
    assert.ok(outer(loud, 372) > quiet * 1.1, `${outer(loud, 372)} vs ${quiet}`);
});
