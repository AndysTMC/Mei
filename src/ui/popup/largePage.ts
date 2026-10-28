/**
 * The popup's large page (decision 0034). The popup grows into it the way it goes to History, and
 * Back or Escape take it back to the chat. A top bar with Back, a title and the page's actions sits
 * over one content: what Mei is doing (workPage.ts) or a file (src/ui/viewers/). The page knows
 * nothing about either: a new kind of file is one more small viewer handed to `show`.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import St from 'gi://St';

import { iconButton } from '../effects.js';
import type { Size } from './pageSize.js';

/** What the page shows. When it is replaced or closed, the page calls `destroy` (which destroys `actor`) and
 * destroys the action buttons itself. */
export interface PageContent {
    readonly actor: St.Widget;
    readonly title: string;
    /** Buttons for the top bar, after the title. */
    readonly actions: St.Widget[];
    destroy(): void;
}

/** The top bar's height when the theme can't be asked yet (the page was never shown). */
const TOP_BAR_FALLBACK = 44;
/** The body's padding, as in the stylesheet's `.mei-page-body`. */
const BODY_PADDING = 12;

export class LargePage {
    readonly actor = new St.BoxLayout({ vertical: true, visible: false, style_class: 'mei-page' });
    private readonly _topBar = new St.BoxLayout({ x_expand: true, style_class: 'mei-top-bar mei-page-bar' });
    private readonly _title = new St.Label({ x_expand: true, y_align: Clutter.ActorAlign.CENTER, style_class: 'mei-page-title' });
    private readonly _actions = new St.BoxLayout({ style_class: 'mei-page-actions', y_align: Clutter.ActorAlign.CENTER });
    private readonly _body = new St.Bin({ x_expand: true, y_expand: true, x_align: Clutter.ActorAlign.FILL,
        y_align: Clutter.ActorAlign.FILL, style_class: 'mei-page-body' });
    private readonly _backBtn: St.Button;
    private _content: PageContent | null = null;
    private _size: Size = { width: 0, height: 0 };

    constructor(onBack: () => void) {
        this._backBtn = iconButton('go-previous-symbolic', 'Back to chat');
        this._backBtn.connect('clicked', () => onBack());
        this._title.clutter_text.ellipsize = Pango.EllipsizeMode.MIDDLE;
        this._topBar.add_child(this._backBtn);
        this._topBar.add_child(this._title);
        this._topBar.add_child(this._actions);
        this.actor.add_child(this._topBar);
        this.actor.add_child(this._body);
    }

    get content(): PageContent | null {
        return this._content;
    }

    get size(): Size {
        return this._size;
    }

    /** The page's whole size; the popup eases to it. */
    setSize(size: Size): void {
        this._size = size;
        this.actor.set_size(size.width, size.height);
    }

    /** The room a content has under the top bar, for viewers that fit what they show to it. */
    get bodySize(): Size {
        const [, natural] = this._topBar.get_preferred_height(-1); // margins included
        const bar = natural > 0 ? natural : TOP_BAR_FALLBACK;
        const pad = 2 * BODY_PADDING * St.ThemeContext.get_for_stage(global.stage).scale_factor;
        return { width: Math.max(1, this._size.width - pad), height: Math.max(1, this._size.height - bar - pad) };
    }

    /** Show `content` in place of what was there (which is destroyed). */
    show(content: PageContent): void {
        this._destroyContent();
        this._content = content;
        this._title.text = content.title;
        this._actions.destroy_all_children();
        for (const action of content.actions) this._actions.add_child(action);
        this._body.set_child(content.actor);
    }

    /** The title can change after the content loads (a PDF's page count). */
    setTitle(title: string): void {
        this._title.text = title;
    }

    focus(): void {
        this._backBtn.grab_key_focus();
    }

    clear(): void {
        this._destroyContent();
        this._title.text = '';
        this._actions.destroy_all_children();
    }

    private _destroyContent(): void {
        if (!this._content) return;
        this._body.set_child(null);
        this._content.destroy();
        this._content = null;
    }
}
