/**
 * Markdown-to-Pango markup converter.
 *
 * Converts a subset of Markdown syntax into Pango markup
 * that can be rendered by ClutterText in GNOME Shell.
 *
 * Supported syntax:
 *   - Headers: #, ##, ###
 *   - Bold: **text**
 *   - Italic: *text*, _text_
 *   - Strikethrough: ~~text~~
 *   - Inline code: `code`
 *   - Fenced code blocks: ```lang\ncode\n```
 *   - Bullet lists: * or -
 *   - Blockquotes: >
 *   - Links: [text](url)
 *   - Images: ![alt](url) (rendered as 🖼 icon + text)
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

/**
 * Convert Markdown text to Pango markup string.
 * Code blocks and inline code are protected from further processing
 * by replacing them with placeholder tokens first.
 */
export function parseMarkdown(text: string): string {
    // 1. Escape XML entities
    let result = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // 2. Protect fenced code blocks (```lang\ncode\n```)
    const codeBlocks: string[] = [];
    result = result.replace(
        /```(\w*)\n?([\s\S]*?)```/g,
        (_match, lang: string, code: string) => {
            codeBlocks.push(code.trim());
            const header = lang ? `<b>[${lang}]</b>\n` : '';
            return `${header}<tt>%%%BLOCK${codeBlocks.length - 1}%%%</tt>`;
        }
    );

    // 3. Protect inline code (`code`)
    const inlineCodes: string[] = [];
    result = result.replace(/`([^`]+)`/g, (_match, code: string) => {
        inlineCodes.push(code);
        return `<tt>%%%INLINE${inlineCodes.length - 1}%%%</tt>`;
    });

    // 4. Bullet lists: * or -
    result = result.replace(/^(\s*)[-*]\s+(.*)$/gm, '$1• $2');

    // 5. Headers (process ### before ## before #)
    result = result.replace(
        /^### (.*)$/gm,
        '<b><span size="large">$1</span></b>'
    );
    result = result.replace(
        /^## (.*)$/gm,
        '<b><span size="x-large">$1</span></b>'
    );
    result = result.replace(
        /^# (.*)$/gm,
        '<b><span size="xx-large">$1</span></b>'
    );

    // 6. Blockquotes
    result = result.replace(
        /^&gt; (.*)$/gm,
        '<span color="#888888"><i>| $1</i></span>'
    );

    // 7. Images: ![alt](url)
    result = result.replace(
        /!\[([^\]]*)\]\(([^)]+)\)/g,
        (_match, alt: string, url: string) =>
            `🖼 <a href="${escapePangoAttribute(url)}">${alt}</a>`
    );

    // 8. Links: [text](url)
    result = result.replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        (_match, label: string, url: string) =>
            `<a href="${escapePangoAttribute(url)}">${label}</a>`
    );

    // 9. Bold: **text**
    result = result.replace(/\*\*([^\n]+?)\*\*/g, '<b>$1</b>');

    // 10. Italic: *text* or _text_
    result = result.replace(/\*([^*\n]+)\*/g, '<i>$1</i>');
    result = result.replace(/_([^_\n]+)_/g, '<i>$1</i>');

    // 11. Strikethrough: ~~text~~
    result = result.replace(/~~([^\n]+?)~~/g, '<s>$1</s>');

    // 12. Restore protected code
    result = result.replace(
        /%%%BLOCK(\d+)%%%/g,
        (_match, i: string) => codeBlocks[parseInt(i)]
    );
    result = result.replace(
        /%%%INLINE(\d+)%%%/g,
        (_match, i: string) => inlineCodes[parseInt(i)]
    );

    return result;
}

function escapePangoAttribute(value: string): string {
    return value
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;');
}
