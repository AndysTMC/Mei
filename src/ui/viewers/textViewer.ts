/**
 * Text files (code, logs, CSV) in monospace, and Markdown through the conversation's own renderer
 * with a toggle for its plain text. Large files show their start and a note; a file that turns out
 * not to be text shows as "anything else".
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import St from 'gi://St';

import { cardButton } from '../conversation/cards.js';
import { createMessageActor } from '../messageRenderer.js';
import type { PageContent } from '../popup/largePage.js';
import { baseName, centeredNote, fileActions, formatSize, monoText, readHead, scrolling, type ViewerHost } from './common.js';
import { fileInfoContent } from './fileInfo.js';
import { cappedNote, looksLikeText, MAX_TEXT_BYTES } from './kind.js';

export class TextContent implements PageContent {
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true, y_expand: true });
    readonly actions: St.Widget[];
    private readonly _markdown: boolean;
    private _text = '';
    private _plain = false;
    private _toggle: St.Button | null = null;
    /** Why only part of the file shows, if it does. */
    private _note: string | null = null;
    private _destroyed = false;

    /** A file on disk (`path`), or text with no file behind it (what "Ask about this" attached). */
    constructor(readonly title: string, private readonly _host: ViewerHost,
        source: { path: string; markdown: boolean } | { text: string }) {
        this._markdown = 'path' in source && source.markdown;
        this.actions = 'path' in source ? fileActions(source.path, _host) : [];
        if (this._markdown) {
            const toggle = cardButton('Plain text', 'Show the Markdown as plain text');
            toggle.toggle_mode = true;
            toggle.connect('notify::checked', () => {
                this._plain = toggle.checked;
                this._render(null);
            });
            this._toggle = toggle;
            this.actions.unshift(toggle);
        }
        if ('text' in source) {
            this._text = source.text;
            this._render(null);
            return;
        }
        this.actor.add_child(centeredNote('Opening…'));
        readHead(source.path, MAX_TEXT_BYTES).then(({ bytes, size }) => {
            if (this._destroyed) return;
            if (!looksLikeText(bytes)) {
                this._host.replace(fileInfoContent(source.path, this._host));
                return;
            }
            this._text = new TextDecoder('utf-8', { fatal: false }).decode(bytes);
            this._render(cappedNote(bytes.length, size, formatSize));
        }).catch((e: Error) => {
            if (this._destroyed) return;
            this.actor.destroy_all_children();
            this.actor.add_child(centeredNote(`Mei couldn’t read ${baseName(source.path)}: ${e.message}`));
        });
    }

    /** Whether the Markdown is shown as plain text (for the dev hooks' tests). */
    get mode(): string {
        return this._markdown && !this._plain ? 'markdown' : 'text';
    }

    private _render(note: string | null): void {
        if (note !== null) this._note = note;
        this.actor.destroy_all_children();
        if (this._note) this.actor.add_child(new St.Label({ text: this._note, style_class: 'mei-card-muted mei-viewer-note' }));
        if (this._markdown && !this._plain) {
            const rendered = createMessageActor(this._text, { role: 'assistant', compact: false });
            const box = new St.BoxLayout({ vertical: true, x_expand: true });
            box.add_child(rendered.actor);
            this.actor.add_child(scrolling(box));
        } else {
            this.actor.add_child(monoText(this._text));
        }
        if (this._toggle) this._toggle.label = this._plain ? 'Formatted' : 'Plain text';
    }

    destroy(): void {
        this._destroyed = true;
        this.actor.destroy();
    }
}
