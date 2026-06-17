import { build } from 'esbuild';

const common = {
    bundle: true,
    format: 'esm',
    platform: 'neutral',
    target: 'es2023',
    external: [
        'gi://*',
        'resource://*',
    ],
};

// Build extension.js
await build({
    ...common,
    entryPoints: ['src/extension.ts'],
    outfile: 'dist/extension.js',
});

// Build prefs.js
await build({
    ...common,
    entryPoints: ['src/prefs.ts'],
    outfile: 'dist/prefs.js',
});

console.log('Build complete.');
