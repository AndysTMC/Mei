/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

export interface LinkTarget {
    label: string;
    url: string;
}

export type UrlValidator = (url: string) => boolean;

const URL_PROTOCOL_RE = /^(https?:|mailto:)/i;
const MARKDOWN_LINK_RE = /\[([^\]\n]+)\]\(((?:\\.|[^()\\\n]|\([^)\n]*\))+)\)/g;
const NON_IMAGE_MARKDOWN_LINK_RE = /(?<!!)\[([^\]\n]+)\]\(((?:\\.|[^()\\\n]|\([^)\n]*\))+)\)/g;

export function inlineMarkup(text: string, sanitize: (url: string) => string | null = sanitizeUrl): string {
    let result = escapePangoText(decodeEntities(text));
    const inlineCodes: string[] = [];
    const escapedCharacters: string[] = [];

    result = result.replace(/`([^`]+)`/g, (_match, code: string) => {
        inlineCodes.push(`<tt>${code}</tt>`);
        return makeInlineCodeToken(inlineCodes.length - 1);
    });

    result = result.replace(/\\([\\`*_[\]()#+\-.!|>~])/g, (_match, character: string) => {
        escapedCharacters.push(character);
        return makeEscapedCharacterToken(escapedCharacters.length - 1);
    });

    result = result.replace(/\*\*([^\n]+?)\*\*/g, '<b>$1</b>');
    result = result.replace(/~~([^\n]+?)~~/g, '<s>$1</s>');
    result = result.replace(/\*([^*\n]+)\*/g, '<i>$1</i>');
    result = result.replace(/_([^_\n]+)_/g, '<i>$1</i>');

    result = result.replace(MARKDOWN_LINK_RE, (_match, label: string, url: string) => {
        const sanitized = sanitize(url);
        const safeLabel = label.trim() || sanitized || 'link';
        if (!sanitized) return safeLabel;
        return `<span underline="single">${safeLabel}</span>`;
    });

    result = result.replace(/&lt;(https?:\/\/[^&\s]+)&gt;/g, '<span underline="single">$1</span>');
    result = result.replace(/&lt;(mailto:[^&\s]+)&gt;/gi, '<span underline="single">$1</span>');

    return result
        .replace(/@@MEIESC(\d+)@@/g, (_match, index: string) => escapedCharacters[Number.parseInt(index, 10)] ?? '')
        .replace(/@@MEIINLINE(\d+)@@/g, (_match, index: string) => inlineCodes[Number.parseInt(index, 10)] ?? '');
}

export function extractLinks(text: string, sanitize: (url: string) => string | null = sanitizeUrl): LinkTarget[] {
    const links = new Map<string, LinkTarget>();
    const addLink = (label: string, url: string): void => {
        const sanitized = sanitize(url);
        if (!sanitized || links.has(sanitized)) return;
        links.set(sanitized, {
            label: label.trim() || sanitized,
            url: sanitized,
        });
    };

    for (const match of text.matchAll(NON_IMAGE_MARKDOWN_LINK_RE)) {
        addLink(match[1], match[2]);
    }
    for (const match of text.matchAll(/<((?:https?:\/\/|mailto:)[^>\s]+)>/gi)) {
        addLink(match[1], match[1]);
    }
    for (const match of text.matchAll(/\bhttps?:\/\/[^\s<>)\]]+/gi)) {
        if (typeof match.index === 'number' && isMarkdownLinkUrl(text, match.index)) continue;
        addLink(match[0], match[0]);
    }

    return [...links.values()];
}

function isMarkdownLinkUrl(text: string, urlIndex: number): boolean {
    return /!?\[[^\]\n]*\]\($/.test(text.slice(0, urlIndex));
}

export function sanitizeUrl(url: string, validator: UrlValidator = isValidStandardUrl): string | null {
    const trimmed = decodeEntities(url).trim();
    if (!URL_PROTOCOL_RE.test(trimmed)) return null;
    if (!validator(trimmed)) return null;
    return trimmed;
}

export function decodeEntities(text: string): string {
    return text
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'");
}

export function escapePangoText(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

export function stripPangoTags(markup: string): string {
    return markup.replace(/<[^>]+>/g, '');
}

function isValidStandardUrl(url: string): boolean {
    const UrlCtor = (globalThis as unknown as {
        URL?: new (input: string) => { protocol: string };
    }).URL;
    if (UrlCtor) {
        try {
            const parsed = new UrlCtor(url);
            return parsed.protocol === 'http:' || parsed.protocol === 'https:' || parsed.protocol === 'mailto:';
        } catch {
            return false;
        }
    }
    return /^https?:\/\/[^\s/?#]+(?:[/?#][^\s]*)?$/i.test(url) ||
        /^mailto:[^\s@]+@[^\s@]+$/i.test(url);
}

function makeInlineCodeToken(index: number): string {
    return `@@MEIINLINE${index}@@`;
}

function makeEscapedCharacterToken(index: number): string {
    return `@@MEIESC${index}@@`;
}
