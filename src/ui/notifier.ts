/**
 * Mei's notifications in the Shell's message tray: one per conversation at a time (a newer one
 * replaces it), and clicking one opens that conversation. Approvals aren't answered from here
 * (§18.2): "Review" only opens the card.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';

import type { Notice } from '../runtime/notices.js';

const ICON = 'dialog-information-symbolic';

export class TaskNotifier {
    private _source: MessageTray.Source | null = null;
    private readonly _shown = new Map<string, MessageTray.Notification>();

    constructor(private readonly _open: (conversationId: string) => void) {}

    notify(notice: Notice): void {
        this._shown.get(notice.conversationId)?.destroy(MessageTray.NotificationDestroyedReason.REPLACED);
        const source = this._ensureSource();
        const notification = new MessageTray.Notification({ source, title: notice.title, body: notice.body });
        notification.connect('activated', () => this._open(notice.conversationId));
        notification.connect('destroy', () => {
            if (this._shown.get(notice.conversationId) === notification) this._shown.delete(notice.conversationId);
        });
        if (notice.review) notification.addAction('Review', () => this._open(notice.conversationId));
        this._shown.set(notice.conversationId, notification);
        source.addNotification(notification);
    }

    /** The notification shown for this conversation, if any (the dev-build test hooks click it). */
    shownFor(conversationId: string): MessageTray.Notification | null {
        return this._shown.get(conversationId) ?? null;
    }

    /** The person is looking at this conversation now: its notification has done its job. */
    dismiss(conversationId: string): void {
        this._shown.get(conversationId)?.destroy(MessageTray.NotificationDestroyedReason.DISMISSED);
    }

    destroy(): void {
        this._source?.destroy(MessageTray.NotificationDestroyedReason.SOURCE_CLOSED);
        this._source = null;
        this._shown.clear();
    }

    /** The tray destroys a source once its last notification goes, so it is made again when needed. */
    private _ensureSource(): MessageTray.Source {
        if (this._source) return this._source;
        const source = new MessageTray.Source({ title: 'Mei', iconName: ICON });
        source.connect('destroy', () => {
            if (this._source === source) this._source = null;
        });
        Main.messageTray.add(source);
        this._source = source;
        return source;
    }
}
