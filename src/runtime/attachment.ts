/**
 * What goes with the next message: "Ask about this" (§18.4), the focused window's title and the
 * selected text, or what was dropped on Mei's button (decision 0027), files or text. Pure, so the
 * clipping, the merging and the chip's wording are tested without the Shell.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { Attachment } from './protocol.js';

/** The runtime refuses more (runtime/src/mei/protocol.py). */
export const MAX_ATTACHMENT_CHARS = 8_000;
export const MAX_DROPPED_FILES = 20;
const MAX_PATH_CHARS = 4096;
const MAX_TITLE_CHARS = 500;
const MAX_APP_CHARS = 200;
const PREVIEW_CHARS = 60;

/** What the drop window (src/dropWindow.ts) took from a drag: local files, or text. */
export type Drop = { kind: 'files'; paths: string[] } | { kind: 'text'; text: string };

/** Null when there is nothing to attach: no window title and no selected text. */
export function makeAttachment(appId: string, windowTitle: string, text: string): Attachment | null {
    const title = windowTitle.trim().slice(0, MAX_TITLE_CHARS);
    const selected = text.trim() ? text.slice(0, MAX_ATTACHMENT_CHARS) : '';
    if (!title && !selected) return null;
    return { kind: 'selection', app_id: appId.slice(0, MAX_APP_CHARS), window_title: title, text: selected };
}

/**
 * The attachment after a drop: files join files already attached (each once, up to what the runtime
 * accepts); text, or files after something else, takes its place. A drop with nothing usable in it
 * leaves things as they were.
 */
export function withDrop(current: Attachment | null, drop: Drop): Attachment | null {
    if (drop.kind === 'text') {
        const text = drop.text.trim() ? drop.text.slice(0, MAX_ATTACHMENT_CHARS) : '';
        return text ? { kind: 'text', app_id: '', window_title: '', text } : current;
    }
    const earlier = current?.kind === 'files' ? current.paths ?? [] : [];
    const paths = [...new Set([...earlier, ...drop.paths.filter(isLocalPath)])].slice(0, MAX_DROPPED_FILES);
    if (paths.length === earlier.length) return current;
    return { kind: 'files', app_id: '', window_title: '', text: '', paths };
}

/** What the chip above the message box, and the sent message, say was attached. */
export function attachmentLabel(attachment: Attachment): string {
    if (attachment.kind === 'files') return `Attached: ${filesLabel(attachment.paths ?? [])}`;
    const where = attachment.kind === 'text' ? ''
        : attachment.window_title || attachment.app_id.replace(/\.desktop$/, '') || 'a window';
    const preview = attachment.text.replace(/\s+/g, ' ').trim();
    if (!preview) return `About: ${where}`;
    const clipped = preview.length > PREVIEW_CHARS ? `${preview.slice(0, PREVIEW_CHARS - 1).trimEnd()}…` : preview;
    return where ? `About: ${where} — “${clipped}”` : `About: “${clipped}”`;
}

function filesLabel(paths: string[]): string {
    const names = paths.map(p => p.slice(p.lastIndexOf('/') + 1) || p);
    if (names.length <= 2) return names.join(', ');
    return `${names[0]} and ${names.length - 1} more`;
}

/** Whether there is something to open on the large page: files, or text (not a bare window title). */
export function canOpen(attachment: Attachment): boolean {
    return attachment.kind === 'files' ? (attachment.paths ?? []).length > 0 : attachment.text.trim() !== '';
}

/** The large page's title for attached text: where it came from. */
export function attachmentTitle(attachment: Attachment): string {
    if (attachment.kind === 'text') return 'Dropped text';
    return attachment.window_title || attachment.app_id.replace(/\.desktop$/, '') || 'Selected text';
}

/** The attachment stored with a sent message, if it has one. */
export function attachmentOf(metadata: Record<string, unknown>): Attachment | null {
    const a = metadata.attachment as Attachment | undefined;
    return a && typeof a === 'object' ? a : null;
}

/** One line from the drop window to the Shell: what was dropped. */
export function encodeDrop(drop: Drop): string {
    return JSON.stringify(drop);
}

/** The drop window's line, checked: it is another process, so nothing is taken on trust. */
export function decodeDrop(line: string): Drop | null {
    let value: unknown;
    try {
        value = JSON.parse(line);
    } catch {
        return null;
    }
    if (!value || typeof value !== 'object') return null;
    const { kind, paths, text } = value as Record<string, unknown>;
    if (kind === 'text' && typeof text === 'string') return { kind, text: text.slice(0, MAX_ATTACHMENT_CHARS) };
    if (kind === 'files' && Array.isArray(paths) && paths.every(p => typeof p === 'string'))
        return { kind, paths: paths.filter(isLocalPath).slice(0, MAX_DROPPED_FILES) };
    return null;
}

/** As the runtime accepts them: absolute and normalized (no `.`, `..`, `//` or trailing `/`), no NUL. */
function isLocalPath(path: string): boolean {
    if (!path.startsWith('/') || path.length > MAX_PATH_CHARS || path.includes('\0')) return false;
    return path === '/' || path.split('/').slice(1).every(part => part !== '' && part !== '.' && part !== '..');
}
