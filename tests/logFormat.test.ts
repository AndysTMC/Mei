import assert from 'node:assert/strict';
import test from 'node:test';

import { formatLogEntry } from '../src/runtime/logFormat.js';

test('log entries read as time, level, logger, message', () => {
    const line = formatLogEntry({ id: 1, t: 1_792_498_073.987, level: 'warning', logger: 'mei.app', msg: 'keyring locked' });
    assert.match(line, /^\d\d:\d\d:\d\d \[WARNING\] \[mei\.app\] keyring locked$/);
});
