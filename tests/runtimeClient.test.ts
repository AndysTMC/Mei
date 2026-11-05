import assert from 'node:assert/strict';
import test from 'node:test';

import { RuntimeClient } from '../src/runtime/client.js';
import type { Envelope } from '../src/runtime/protocol.js';

function event(type: string, required: boolean): Envelope {
    return { v: 2, type, event_id: 'e', epoch: 'x', at: '', required, seq: 5, conversation_id: null, task_id: null,
        payload: {} };
}

/** A client whose runtime answers Hello and an Attach that replays `events`. */
async function attach(events: Envelope[]) {
    const client = new RuntimeClient(() => 4);
    const statuses: string[] = [];
    let attached = 0;
    client.call = (async (method: string) => method === 'Hello'
        ? { epoch: 'x', protocol: [2, 2] }
        : { epoch: 'x', seq: 5, mode: 'replay', streams: [], events }) as RuntimeClient['call'];
    client.onStatus = status => statuses.push(status);
    client.onAttached = () => attached++;
    await (client as unknown as { _connect(): Promise<void> })._connect();
    return { statuses, attached };
}

test('a replayed event this extension must know but doesn\'t stops the connection, as a live one does', async () => {
    const { statuses, attached } = await attach([event('task.state', false), event('new.required.event', true)]);
    assert.deepEqual(statuses, ['connecting', 'incompatible']);
    assert.equal(attached, 0); // nothing of the replay was applied
});

test('an unknown event that isn\'t required is replayed like any other', async () => {
    const { statuses, attached } = await attach([event('new.optional.event', false)]);
    assert.deepEqual(statuses, ['connecting', 'connected']);
    assert.equal(attached, 1);
});
