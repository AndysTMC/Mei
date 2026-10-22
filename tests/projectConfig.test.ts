import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('extension metadata and schema target the same extension identity', () => {
    const metadata = JSON.parse(readFileSync('metadata.json', 'utf8')) as {
        uuid?: string;
        ['shell-version']?: string[];
    };
    const schema = readFileSync('schemas/org.gnome.shell.extensions.mei.gschema.xml', 'utf8');

    assert.equal(metadata.uuid, 'mei@andystmc.com');
    assert.ok(metadata['shell-version']?.includes('50'));
    assert.match(schema, /id="org\.gnome\.shell\.extensions\.mei"/);
});

test('the schema keeps only keybindings: the runtime owns every other setting', () => {
    const schema = readFileSync('schemas/org.gnome.shell.extensions.mei.gschema.xml', 'utf8');
    for (const key of ['provider', 'provider-type', 'provider-configs', 'experimental-runtime'])
        assert.doesNotMatch(schema, new RegExp(`<key name="${key}"`));
    assert.deepEqual([...schema.matchAll(/<key name="([^"]+)"/g)].map(m => m[1]), ['open-shortcut', 'ask-shortcut', 'voice-shortcut']);
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
