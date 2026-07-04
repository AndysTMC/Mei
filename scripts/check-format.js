import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT_FILES = [
    'ambient.d.ts',
    'esbuild.js',
    'IMPLEMENTATION_PLAN.md',
    'metadata.json',
    'package.json',
    'README.md',
    'stylesheet.css',
    'tsconfig.json',
];
const ROOT_DIRS = ['schemas', 'scripts', 'src', 'tests'];
const EXTENSIONS = new Set(['.css', '.js', '.json', '.md', '.ts', '.xml']);

const failures = [];

for (const file of ROOT_FILES) {
    checkFile(file);
}
for (const dir of ROOT_DIRS) {
    walk(dir);
}

if (failures.length > 0) {
    console.error(failures.join('\n'));
    process.exit(1);
}

function walk(path) {
    for (const entry of readdirSync(path)) {
        const child = join(path, entry);
        const stat = statSync(child);
        if (stat.isDirectory()) {
            walk(child);
        } else {
            checkFile(child);
        }
    }
}

function checkFile(path) {
    if (!EXTENSIONS.has(getExtension(path))) return;
    const text = readFileSync(path, 'utf8');
    if (text.length > 0 && !text.endsWith('\n')) {
        failures.push(`${path}: missing final newline`);
    }
    const lines = text.split('\n');
    lines.forEach((line, index) => {
        if (/[ \t]$/.test(line)) {
            failures.push(`${path}:${index + 1}: trailing whitespace`);
        }
    });
}

function getExtension(path) {
    const index = path.lastIndexOf('.');
    return index === -1 ? '' : path.slice(index);
}
