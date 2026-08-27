import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { PROVIDER_LABELS } from '../src/providers/catalog.js';

test('extension metadata and schema target the same extension identity', () => {
    const metadata = JSON.parse(readFileSync('metadata.json', 'utf8')) as {
        uuid?: string;
        ['shell-version']?: string[];
    };
    const schema = readFileSync('schemas/org.gnome.shell.extensions.mei.gschema.xml', 'utf8');

    assert.equal(metadata.uuid, 'mei@andystmc.com');
    assert.ok(metadata['shell-version']?.includes('50'));
    assert.match(schema, /id="org\.gnome\.shell\.extensions\.mei"/);
    assert.match(schema, /<default>'ollama'<\/default>/);
});

test('schema provider documentation matches the selectable provider catalog', () => {
    const schema = readFileSync('schemas/org.gnome.shell.extensions.mei.gschema.xml', 'utf8');
    const description = schema.match(/<description>The AI provider to use: ([^<]+)<\/description>/)?.[1];
    assert.ok(description);
    assert.deepEqual(new Set(description.split(/,\s*/)), new Set(Object.keys(PROVIDER_LABELS)));
    assert.match(description, /deepseek/i);
    assert.match(description, /fireworks/i);
    assert.match(description, /nvidia/i);
});

test('sensitive local environment files are ignored while the template is committed', () => {
    const gitignore = readFileSync('.gitignore', 'utf8');
    const example = readFileSync('.env.example', 'utf8');
    assert.match(gitignore, /^\.env$/m);
    assert.match(gitignore, /^\.env\.\*$/m);
    assert.match(gitignore, /^!\.env\.example$/m);
    assert.match(example, /^MEI_LIVE_CHAT=0$/m);
    assert.doesNotMatch(example, /(?:sk-|AIza)[A-Za-z0-9_-]{12,}/);
});
