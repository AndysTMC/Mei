/**
 * Mei's URL policy (only well-formed http(s) and mailto links, checked with GLib) applied to
 * the inline-markup and link helpers in ../messageText.ts.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import GLib from 'gi://GLib';

import {
    extractLinks as extractTextLinks,
    inlineMarkup as inlineTextMarkup,
    sanitizeUrl as sanitizeTextUrl,
    type LinkTarget,
} from '../messageText.js';

export type { LinkTarget } from '../messageText.js';

export function inlineMarkup(text: string): string {
    return inlineTextMarkup(text, sanitizeUrl);
}

export function extractLinks(text: string): LinkTarget[] {
    return extractTextLinks(text, sanitizeUrl);
}

export function sanitizeUrl(url: string): string | null {
    return sanitizeTextUrl(url, value => {
        try {
            GLib.Uri.parse(value, GLib.UriFlags.NONE);
            return true;
        } catch {
            return false;
        }
    });
}
