import { mkdtempSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { build } from 'esbuild';

const outDir = mkdtempSync(join(tmpdir(), 'mei-tests-'));
const entryPoints = readdirSync('tests')
    .filter(file => file.endsWith('.test.ts'))
    .map(file => join('tests', file));
const outfiles = entryPoints.map(file => join(outDir, file.replace(/^tests\//, '').replace(/\.ts$/, '.js')));

await build({
    entryPoints,
    outdir: outDir,
    bundle: true,
    platform: 'node',
    format: 'esm',
    target: 'node20',
});

const result = spawnSync(process.execPath, ['--test', ...outfiles], {
    stdio: 'inherit',
});

process.exit(result.status ?? 1);
