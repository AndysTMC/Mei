import { existsSync, mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { build } from 'esbuild';

const outDir = mkdtempSync(join(tmpdir(), 'mei-tests-'));
const testPattern = process.env.MEI_TEST_PATTERN || '';
const entryPoints = readdirSync('tests')
    .filter(file => file.endsWith('.test.ts'))
    .filter(file => !testPattern || file.includes(testPattern))
    .map(file => join('tests', file));
const outfiles = entryPoints.map(file => join(outDir, file.replace(/^tests\//, '').replace(/\.ts$/, '.js')));

let exitCode = 1;
try {
    await build({
        entryPoints,
        outdir: outDir,
        bundle: true,
        platform: 'node',
        format: 'esm',
        target: 'node20',
        plugins: [{
            name: 'gnome-test-stubs',
            setup(build) {
                build.onResolve({ filter: /^(?:gi|resource):\/\// }, args => ({
                    path: args.path,
                    namespace: 'gnome-test-stub',
                }));
                build.onLoad({ filter: /.*/, namespace: 'gnome-test-stub' }, args => ({
                    loader: 'js',
                    contents: args.path.startsWith('gi://Cogl')
                        ? 'export default { Color: { from_string: () => [false, null] } };'
                        : 'const stub = new Proxy(function () {}, { get: () => stub, apply: () => stub, construct: () => stub }); export default stub; export const Extension = stub; export const ExtensionPreferences = stub;',
                }));
            },
        }],
    });

    const nodeArgs = process.env.MEI_TEST_DIRECT === '1' ? [] : ['--test'];
    if (process.env.MEI_TEST_COVERAGE === '1') nodeArgs.push('--experimental-test-coverage');
    const nodeExecutable = process.execPath.includes('/snap/') && existsSync('/usr/bin/node')
        ? '/usr/bin/node'
        : process.execPath;
    const result = spawnSync(nodeExecutable, [...nodeArgs, ...outfiles], {
        stdio: 'inherit',
    });
    exitCode = result.status ?? 1;
} finally {
    rmSync(outDir, { recursive: true, force: true });
}

process.exitCode = exitCode;
