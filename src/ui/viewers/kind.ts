/**
 * Which viewer shows a file (decision 0034), and how much of a text file is shown. Pure, so it's
 * tested without the Shell; the viewers themselves are St widgets beside this file.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

export type FileKind = 'text' | 'markdown' | 'image' | 'pdf' | 'other';

/** Text past this is left out, with a note: a label this long is already slow to lay out. */
export const MAX_TEXT_BYTES = 256 * 1024;

const MARKDOWN = new Set(['md', 'markdown', 'mdown', 'mkd']);
/** What St's image loader (GdkPixbuf) reads everywhere; others show as "anything else". */
const IMAGES = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'tif', 'tiff', 'ico', 'avif', 'heic']);
const TEXT = new Set(['txt', 'text', 'log', 'csv', 'tsv', 'json', 'jsonl', 'xml', 'yaml', 'yml', 'toml', 'ini', 'cfg',
    'conf', 'env', 'sh', 'bash', 'zsh', 'fish', 'py', 'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'c', 'h', 'cc', 'cpp', 'hpp',
    'rs', 'go', 'java', 'kt', 'rb', 'php', 'pl', 'lua', 'sql', 'css', 'scss', 'html', 'htm', 'vue', 'svelte', 'swift',
    'cs', 'r', 'tex', 'rst', 'org', 'diff', 'patch', 'srt', 'vtt', 'properties', 'gradle', 'cmake', 'mk', 'desktop',
    'service', 'gitignore', 'dockerfile', 'makefile']);

/**
 * By the name first (what the person sees), then the content type the system guessed: a file named
 * `notes` whose content type is text/plain is text.
 */
export function fileKind(name: string, contentType = ''): FileKind {
    const base = name.slice(name.lastIndexOf('/') + 1).toLowerCase();
    const dot = base.lastIndexOf('.');
    const ext = dot > 0 ? base.slice(dot + 1) : base;
    if (MARKDOWN.has(ext)) return 'markdown';
    if (ext === 'pdf') return 'pdf';
    if (IMAGES.has(ext)) return 'image';
    if (TEXT.has(ext)) return 'text';
    if (contentType === 'application/pdf') return 'pdf';
    if (contentType === 'text/markdown') return 'markdown';
    if (contentType.startsWith('image/')) return 'image';
    if (contentType.startsWith('text/') || contentType === 'application/json' || contentType === 'application/x-shellscript')
        return 'text';
    return 'other';
}

/** Bytes that are text: no NUL in what was read (a binary file has them early and often). */
export function looksLikeText(bytes: Uint8Array): boolean {
    return !bytes.subarray(0, 8192).includes(0);
}

/** The note under a text file shown only in part. */
export function cappedNote(shownBytes: number, totalBytes: number, size: (bytes: number) => string): string | null {
    if (totalBytes <= shownBytes) return null;
    return `Showing the first ${size(shownBytes)} of ${size(totalBytes)}. Open it in its app for the rest.`;
}
