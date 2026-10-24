// Asserts the built Shell bundles stay UI only (ADR 0002): no HTTP client and no file writes.
// Providers, conversations, settings, and logs belong to the runtime. Run after `npm run build`.
import { readFileSync } from 'node:fs';

const FORBIDDEN = [
    ['gi://Soup', 'HTTP client (providers are called by the runtime)'],
    ['file_set_contents', 'file write'],
    ['replace_contents', 'file write'],
    ['make_directory_with_parents', 'directory creation'],
    ['mkdir_with_parents', 'directory creation'],
    ['append_to', 'file write'],
    ['create_readwrite', 'file write'],
];

let failures = 0;
for (const bundle of ['dist/extension.js', 'dist/prefs.js', 'dist/dropWindow.js']) {
    const source = readFileSync(bundle, 'utf8');
    for (const [needle, why] of FORBIDDEN) {
        if (source.includes(needle)) {
            console.error(`${bundle}: contains ${needle} (${why})`);
            failures++;
        }
    }
}
if (failures) process.exit(1);
console.log('bundles: UI only (no HTTP client, no file writes)');
