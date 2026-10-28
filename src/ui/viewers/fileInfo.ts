/**
 * "Anything else": the file's icon, name, size and kind, with the page's usual actions. Also what a
 * PDF shows when the runtime can't draw it (no pdftoppm).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import { wrapLabel } from '../effects.js';
import type { PageContent } from '../popup/largePage.js';
import { baseName, fileActions, formatSize, type ViewerHost } from './common.js';
import { TextContent } from './textViewer.js';
import { fileKind } from './kind.js';

const ATTRIBUTES = 'standard::icon,standard::size,standard::content-type,standard::type';

class FileInfoContent implements PageContent {
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true, y_expand: true, y_align: Clutter.ActorAlign.CENTER,
        style_class: 'mei-viewer-info' });
    readonly actions: St.Widget[];
    readonly title: string;
    readonly mode = 'other';
    private readonly _icon = new St.Icon({ icon_name: 'text-x-generic-symbolic', icon_size: 96, x_align: Clutter.ActorAlign.CENTER });
    private readonly _detail = new St.Label({ text: '', style_class: 'mei-card-muted', x_align: Clutter.ActorAlign.CENTER });
    private _destroyed = false;

    constructor(path: string, host: ViewerHost, note: string, upgrade: boolean) {
        this.title = baseName(path);
        this.actions = fileActions(path, host);
        this.actor.add_child(this._icon);
        this.actor.add_child(wrapLabel(new St.Label({ text: this.title, style_class: 'mei-viewer-info-name',
            x_align: Clutter.ActorAlign.CENTER })));
        this.actor.add_child(this._detail);
        if (note) this.actor.add_child(wrapLabel(new St.Label({ text: note, style_class: 'mei-card-muted', x_align: Clutter.ActorAlign.CENTER })));
        const file = Gio.File.new_for_path(path);
        file.query_info_async(ATTRIBUTES, Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, null, (_f, result) => {
            if (this._destroyed) return;
            try {
                const info = file.query_info_finish(result);
                const type = info.get_content_type() ?? '';
                // Named oddly but text all the same (a `README`, a `.conf` we don't list): show it as text.
                if (upgrade && info.get_file_type() === Gio.FileType.REGULAR) {
                    const kind = fileKind('', type);
                    if (kind === 'text' || kind === 'markdown') {
                        host.replace(new TextContent(this.title, host, { path, markdown: kind === 'markdown' }));
                        return;
                    }
                }
                const icon = info.get_icon();
                if (icon) this._icon.gicon = icon;
                // "Unknown" says nothing: leave it out.
                const what = type && !Gio.content_type_is_unknown(type) ? Gio.content_type_get_description(type) : '';
                const folder = info.get_file_type() === Gio.FileType.DIRECTORY;
                this._detail.text = [folder ? 'Folder' : formatSize(info.get_size()), what].filter(Boolean).join(' · ');
            } catch (e) {
                this._detail.text = `Mei couldn’t read it: ${(e as Error).message}`;
            }
        });
    }

    destroy(): void {
        this._destroyed = true;
        this.actor.destroy();
    }
}

/** `upgrade`: a file whose name says nothing may still be text, by its content type. */
export function fileInfoContent(path: string, host: ViewerHost, note = '', upgrade = false): PageContent {
    return new FileInfoContent(path, host, note, upgrade);
}
