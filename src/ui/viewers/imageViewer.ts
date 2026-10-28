/**
 * Images, fitted to the page; a click shows them at their own size, scrolling, and another click
 * fits them again.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import type { PageContent } from '../popup/largePage.js';
import { baseName, fileActions, loadPicture, scrolling, type ViewerHost } from './common.js';

export class ImageContent implements PageContent {
    readonly actor = new St.Bin({ x_expand: true, y_expand: true, x_align: Clutter.ActorAlign.FILL, y_align: Clutter.ActorAlign.FILL });
    readonly actions: St.Widget[];
    readonly title: string;
    private _zoomed = false;

    constructor(private readonly _path: string, private readonly _host: ViewerHost) {
        this.title = baseName(_path);
        this.actions = fileActions(_path, _host);
        this._show();
    }

    get mode(): string {
        return this._zoomed ? 'zoomed' : 'fitted';
    }

    private _show(): void {
        const picture = loadPicture(this._path, this._zoomed ? null : this._host.bodySize);
        const button = new St.Button({ child: picture, can_focus: true, reactive: true, accessible_role: Atk.Role.PUSH_BUTTON,
            accessible_name: this._zoomed ? 'Fit the image' : 'Zoom the image', style_class: 'mei-viewer-image',
            x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER });
        button.connect('clicked', () => {
            this._zoomed = !this._zoomed;
            this._show();
        });
        if (!this._zoomed) {
            this.actor.set_child(button);
            return;
        }
        const box = new St.BoxLayout({ x_expand: true, y_expand: true });
        box.add_child(button);
        this.actor.set_child(scrolling(box, true));
    }

    destroy(): void {
        this.actor.destroy();
    }
}
