/**
 * The viewer for a file, by its kind (kind.ts): one small viewer per kind, each a page content
 * (decision 0034). A new kind is a new viewer here.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { PageContent } from '../popup/largePage.js';
import { baseName, type ViewerHost } from './common.js';
import { fileInfoContent } from './fileInfo.js';
import { ImageContent } from './imageViewer.js';
import { fileKind } from './kind.js';
import { PdfContent } from './pdfViewer.js';
import { TextContent } from './textViewer.js';

export type { PdfPages, ViewerHost } from './common.js';

export function fileViewer(path: string, host: ViewerHost): PageContent {
    switch (fileKind(path)) {
    case 'text':
        return new TextContent(baseName(path), host, { path, markdown: false });
    case 'markdown':
        return new TextContent(baseName(path), host, { path, markdown: true });
    case 'image':
        return new ImageContent(path, host);
    case 'pdf':
        return host.pdf ? new PdfContent(path, host, host.pdf)
            : fileInfoContent(path, host, 'Mei can’t show this PDF’s pages here.');
    default:
        return fileInfoContent(path, host, '', true);
    }
}

/** Text that came without a file: what "Ask about this" or a drop attached. */
export function textViewer(title: string, text: string, host: ViewerHost): PageContent {
    return new TextContent(title, host, { text });
}
