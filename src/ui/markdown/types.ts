/**
 * The block model a message is parsed into (see parse.ts), shared by preview and rendering.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

export type MessageRole = 'user' | 'assistant' | 'system';

export type InlineAlignment = 'left' | 'center' | 'right';

export type MessageBlock =
    | ParagraphBlock
    | HeadingBlock
    | CodeBlock
    | BlockquoteBlock
    | ListBlock
    | TableBlock
    | HorizontalRuleBlock
    | FootnoteBlock
    | CitationBlock
    | MathBlock;

export interface MessageModel {
    role: MessageRole;
    originalMarkdown: string;
    stabilizedMarkdown: string;
    plainText: string;
    blocks: MessageBlock[];
    isStreaming: boolean;
}

interface BaseBlock {
    type: MessageBlock['type'];
    source: string;
}

export interface ParagraphBlock extends BaseBlock {
    type: 'paragraph';
    text: string;
}

export interface HeadingBlock extends BaseBlock {
    type: 'heading';
    level: 1 | 2 | 3 | 4 | 5 | 6;
    text: string;
}

export interface CodeBlock extends BaseBlock {
    type: 'codeBlock';
    language: string;
    code: string;
    fullCode?: string;
    originalCharCount?: number;
    isStreaming: boolean;
    isDiagramSource: boolean;
}

export interface BlockquoteBlock extends BaseBlock {
    type: 'blockquote';
    text: string;
}

export interface ListBlock extends BaseBlock {
    type: 'orderedList' | 'unorderedList';
    items: Array<{
        text: string;
        checked?: boolean;
        task: boolean;
        /** The item's own number ("2." stays 2 after a paragraph broke the list); absent for a bullet. */
        number?: number;
        /** How deep it is: 0 at the margin, 1 under an item, and so on. */
        depth?: number;
    }>;
    originalItemCount?: number;
}

export interface TableBlock extends BaseBlock {
    type: 'table';
    headers: string[];
    rows: string[][];
    alignments: InlineAlignment[];
    markdown: string;
    plainText: string;
    csv: string;
    originalRowCount?: number;
    originalColumnCount?: number;
}

export interface HorizontalRuleBlock extends BaseBlock {
    type: 'horizontalRule';
}

export interface FootnoteBlock extends BaseBlock {
    type: 'footnoteDef';
    id: string;
    text: string;
}

export interface CitationBlock extends BaseBlock {
    type: 'citation';
    id: string;
    text: string;
}

export interface MathBlock extends BaseBlock {
    type: 'mathBlock';
    content: string;
    isStreaming: boolean;
}

export interface MessageRendererOptions {
    role: MessageRole;
    compact?: boolean;
    streaming?: boolean;
    allowImages?: boolean;
    enableMath?: boolean;
    showLineNumbers?: boolean;
}
