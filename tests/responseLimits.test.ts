import assert from 'node:assert/strict';
import test from 'node:test';

import {
    MAX_HTTP_RESPONSE_BYTES,
    ResponseSizeGuard,
} from '../src/utils/responseLimits.js';

test('ResponseSizeGuard accepts the configured boundary and rejects the next byte', () => {
    const guard = new ResponseSizeGuard(MAX_HTTP_RESPONSE_BYTES);
    guard.add(MAX_HTTP_RESPONSE_BYTES - 1);
    guard.add(1);

    assert.equal(guard.receivedBytes, MAX_HTTP_RESPONSE_BYTES);
    assert.throws(
        () => guard.add(1),
        /Response exceeded 8 MiB safety limit/
    );
});

test('ResponseSizeGuard rejects invalid accounting input', () => {
    const guard = new ResponseSizeGuard(10);
    assert.throws(() => guard.add(-1), /non-negative finite number/);
    assert.throws(() => guard.add(Number.POSITIVE_INFINITY), /non-negative finite number/);
});
