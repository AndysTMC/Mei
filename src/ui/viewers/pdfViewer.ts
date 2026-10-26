/**
 * PDFs, page by page. The Shell has no Poppler, so the runtime draws each page to a PNG with
 * pdftoppm inside its file sandbox (decision 0029), as the person scrolls to it: the pages in view
 * and one either side, two at a time. Without pdftoppm the file shows as "anything else".
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import { Logger, Tag } from '../../utils/logger.js';
import type { PageContent } from '../popup/largePage.js';
import { baseName, centeredNote, fileActions, loadPicture, scrolling, type PdfPages, type ViewerHost } from './common.js';
import { fileInfoContent } from './fileInfo.js';

/** Drawn this wide at most, so a page stays readable without being a screen tall per line. */
const MAX_PAGE_WIDTH = 900;
/** Until the first page says otherwise: A4's height for its width. */
const GUESSED_ASPECT = 1.414;
const AT_ONCE = 2;

interface Slot {
    bin: St.Bin;
    /** drawing: asked of the runtime, or loading; shown: on screen (or why it can't be). */
    state: 'waiting' | 'drawing' | 'shown';
}

export class PdfContent implements PageContent {
    readonly actor = new St.Bin({ x_expand: true, y_expand: true, x_align: Clutter.ActorAlign.FILL, y_align: Clutter.ActorAlign.FILL });
    readonly actions: St.Widget[];
    readonly title: string;
    private readonly _pages = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-viewer-pages' });
    private readonly _scroll: St.ScrollView;
    private readonly _width: number;
    private _slots: Slot[] = [];
    private _aspect = GUESSED_ASPECT;
    private _drawing = 0;
    private _destroyed = false;

    constructor(private readonly _path: string, private readonly _host: ViewerHost, private readonly _pdf: PdfPages) {
        this.title = baseName(_path);
        this.actions = fileActions(_path, _host);
        this._width = Math.min(_host.bodySize.width - 32, MAX_PAGE_WIDTH * St.ThemeContext.get_for_stage(global.stage).scale_factor);
        this._scroll = scrolling(this._pages);
        this._scroll.get_vadjustment().connect('notify::value', () => this._drawVisible());
        this.actor.set_child(centeredNote('Opening…'));
        _pdf.info(_path).then(({ pages }) => {
            if (this._destroyed) return;
            this._host.setTitle(`${this.title} · ${pages === 1 ? '1 page' : `${pages} pages`}`);
            for (let i = 0; i < pages; i++) {
                const bin = new St.Bin({ style_class: 'mei-viewer-page', x_align: Clutter.ActorAlign.CENTER });
                bin.set_size(this._width, Math.round(this._width * this._aspect));
                this._slots.push({ bin, state: 'waiting' });
                this._pages.add_child(bin);
            }
            this.actor.set_child(this._scroll);
            this._drawVisible();
        }).catch((e: Error) => {
            if (this._destroyed) return;
            Logger.info(Tag.UI, `PDF shown as a file: ${e.message}`);
            this._host.replace(fileInfoContent(_path, _host, 'Mei can’t show this PDF’s pages here.'));
        });
    }

    /** Pages drawn so far, and how many there are (for the dev hooks' tests). */
    get mode(): string {
        return `pdf ${this._slots.filter(s => s.state === 'shown').length}/${this._slots.length}`;
    }

    /** The pages in view and one either side, drawn in order, a few at a time. */
    private _drawVisible(): void {
        if (this._destroyed || !this._slots.length) return;
        const adj = this._scroll.get_vadjustment();
        const slotHeight = Math.max(1, adj.upper / this._slots.length);
        const first = Math.max(0, Math.floor(adj.value / slotHeight) - 1);
        const last = Math.min(this._slots.length - 1, Math.ceil((adj.value + Math.max(adj.page_size, slotHeight)) / slotHeight));
        for (let i = first; i <= last && this._drawing < AT_ONCE; i++) {
            if (this._slots[i].state === 'waiting') this._draw(i);
        }
    }

    private _draw(index: number): void {
        const slot = this._slots[index];
        slot.state = 'drawing';
        this._drawing++;
        this._pdf.page(this._path, index + 1, Math.round(this._width)).then(({ path, width, height }) => {
            if (this._destroyed) return;
            // Exactly the page's size: the loader centres a picture in whatever room it is given.
            const size = width > 0 && height > 0 ? { width, height } : { width: this._width, height: this._width * this._aspect };
            slot.bin.set_child(loadPicture(path, size, size));
            this._fit(slot, size);
        }).catch((e: Error) => {
            if (this._destroyed) return;
            slot.bin.set_child(centeredNote(`Page ${index + 1} couldn’t be shown: ${e.message}`));
            slot.state = 'shown';
        }).finally(() => {
            this._drawing--;
            this._drawVisible();
        });
    }

    /** A drawn page sizes its slot; the first one also tells the rest what shape to wait in. */
    private _fit(slot: Slot, size: { width: number; height: number }): void {
        slot.state = 'shown';
        slot.bin.set_size(Math.round(size.width), Math.round(size.height));
        const aspect = size.height / size.width;
        if (Math.abs(aspect - this._aspect) < 0.01) return;
        this._aspect = aspect;
        for (const other of this._slots) if (other.state !== 'shown') other.bin.set_size(this._width, Math.round(this._width * aspect));
    }

    destroy(): void {
        this._destroyed = true;
        this.actor.destroy();
    }
}
