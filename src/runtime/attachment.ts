/**
 * "Ask about this" (§18.4): the focused window's title and the selected text, attached to the next
 * message. Pure, so the clipping and the chip's wording are tested without the Shell.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { Attachment } from './protocol.js';

/** The runtime refuses more (runtime/src/mei/protocol.py). */
export const MAX_ATTACHMENT_CHARS = 8_000;
const MAX_TITLE_CHARS = 500;
const MAX_APP_CHARS = 200;
const PREVIEW_CHARS = 60;

/** Null when there is nothing to attach: no window title and no selected text. */
export function makeAttachment(appId: string, windowTitle: string, text: string): Attachment | null {
    const title = windowTitle.trim().slice(0, MAX_TITLE_CHARS);
    const selected = text.trim() ? text.slice(0, MAX_ATTACHMENT_CHARS) : '';
    if (!title && !selected) return null;
    return { kind: 'selection', app_id: appId.slice(0, MAX_APP_CHARS), window_title: title, text: selected };
}

/** What the chip above the message box, and the sent message, say was attached. */
export function attachmentLabel(attachment: Attachment): string {
    const where = attachment.window_title || attachment.app_id.replace(/\.desktop$/, '') || 'a window';
    const preview = attachment.text.replace(/\s+/g, ' ').trim();
    if (!preview) return `About: ${where}`;
    const clipped = preview.length > PREVIEW_CHARS ? `${preview.slice(0, PREVIEW_CHARS - 1).trimEnd()}…` : preview;
    return `About: ${where} — “${clipped}”`;
}

/** The attachment stored with a sent message, if it has one. */
export function attachmentOf(metadata: Record<string, unknown>): Attachment | null {
    const a = metadata.attachment as Attachment | undefined;
    return a && typeof a === 'object' ? a : null;
}
