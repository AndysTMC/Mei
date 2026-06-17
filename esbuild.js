import { build } from 'esbuild';

const isDev = process.argv.includes('--dev');

const common = {
    bundle: true,
    format: 'esm',
    platform: 'neutral',
    target: 'es2023',
    external: [
        'gi://*',
        'resource://*',
    ],
    define: {
        '__DEV__': String(isDev),
    },
    // Dev: readable output + inline sourcemaps for stack traces
    // Prod: minified whitespace, no sourcemaps
    minify: !isDev,
    sourcemap: isDev ? 'inline' : false,
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

const mode = isDev ? 'dev' : 'prod';
console.log(`Build complete (${mode}).`);
