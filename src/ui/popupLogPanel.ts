/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import St from 'gi://St';

import { LOG_FILE, replaceLogFileTextAsync } from '../utils/logFile.js';
import { Logger, Tag } from '../utils/logger.js';

type LogFilter = 'All' | 'Info' | 'Debug' | 'Warn' | 'Error';

const LOG_MAX_LINES = 5000;
const LOG_VIEW_HEIGHT = 430;
const LOG_LINE_HEIGHT = 13;
const LOG_LINES_PER_PAGE = 100;

export interface PopupLogPanelCallbacks {
    refresh(): void;
    addButtonClickScaleEffect(button: St.Button): void;
}

export class PopupLogPanel {
    private _filter: LogFilter = 'All';
    private _lines: string[] = [];
    private _page = 0;

    render(listBox: St.BoxLayout, callbacks: PopupLogPanelCallbacks): void {
        const filterRow = new St.BoxLayout({
            x_expand: true,
            style_class: 'mei-settings-segment-row',
        });
        const filters: LogFilter[] = ['All', 'Info', 'Debug', 'Warn', 'Error'];
        for (const filter of filters) {
            const button = new St.Button({
                label: filter,
                style_class: filter === this._filter ? 'mei-settings-chip selected' : 'mei-settings-chip',
                can_focus: true,
                reactive: true,
                track_hover: true,
                accessible_name: `Show ${filter} logs`,
                accessible_role: Atk.Role.PUSH_BUTTON,
            });
            button.connect('clicked', () => {
                this._filter = filter;
                this._page = 0;
                callbacks.refresh();
            });
            filterRow.add_child(button);
            callbacks.addButtonClickScaleEffect(button);
        }
        listBox.add_child(filterRow);

        const actionRow = new St.BoxLayout({
            x_expand: true,
            style_class: 'mei-settings-actions-row',
        });
        this._addActionButton(actionRow, 'view-refresh-symbolic', 'Refresh logs', () => {
            this.load();
            callbacks.refresh();
        }, callbacks);
        this._addActionButton(actionRow, 'edit-copy-symbolic', 'Copy visible logs', () => this.copyVisible(), callbacks);
        this._addActionButton(actionRow, 'user-trash-symbolic', 'Clear visible logs', () => {
            this.clearVisible();
            callbacks.refresh();
        }, callbacks);
        this._addPagerControls(actionRow, callbacks);
        listBox.add_child(actionRow);

        const visibleLines = this._getVisibleLines();
        const pageLines = this._getPagedLines(visibleLines);
        const text = pageLines.length > 0
            ? pageLines.slice().reverse().join('\n')
            : `No ${this._filter === 'All' ? '' : this._filter.toLowerCase() + ' '}logs found`;
        const logHeight = Math.min(
            LOG_VIEW_HEIGHT,
            Math.max(64, (Math.max(pageLines.length, 1) * LOG_LINE_HEIGHT) + 24)
        );
        const logLabel = new St.Label({
            text,
            x_expand: true,
            style_class: 'mei-log-text',
        });
        logLabel.clutter_text.set_line_wrap(true);
        logLabel.clutter_text.set_line_wrap_mode(0);
        logLabel.clutter_text.set_ellipsize(0);

        const logScroll = new St.ScrollView({
            x_expand: true,
            style_class: 'mei-log-scroll',
            overlay_scrollbars: true,
        });
        logScroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        logScroll.set_style(`height: ${logHeight}px; max-height: ${LOG_VIEW_HEIGHT}px;`);
        const logBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'mei-log-box',
        });
        logBox.add_child(logLabel);
        logScroll.set_child(logBox);
        listBox.add_child(logScroll);
    }

    load(): void {
        try {
            const file = Gio.File.new_for_path(LOG_FILE);
            if (!file.query_exists(null)) {
                this._lines = [];
                return;
            }
            const [ok, contents] = file.load_contents(null);
            if (!ok || !contents) {
                this._lines = [];
                return;
            }
            const lines = new TextDecoder().decode(contents).split('\n')
                .map(line => line.trimEnd())
                .filter(line => line.trim().length > 0);
            this._lines = this._trimLines(lines);
            this._page = Math.min(this._page, this._getPageCount(this._getVisibleLines()) - 1);
        } catch (e) {
            this._lines = [`[ERROR] Failed to load logs: ${e}`];
        }
    }

    private _addActionButton(
        row: St.BoxLayout,
        iconName: string,
        accessibleName: string,
        onClick: () => void,
        callbacks: PopupLogPanelCallbacks,
        enabled: boolean = true
    ): void {
        const button = new St.Button({
            style_class: 'mei-icon-btn',
            can_focus: true,
            reactive: enabled,
            track_hover: true,
            accessible_name: accessibleName,
            accessible_role: Atk.Role.PUSH_BUTTON,
            child: new St.Icon({
                icon_name: iconName,
                icon_size: 14,
            }),
        });
        button.opacity = enabled ? 255 : 90;
        button.connect('clicked', onClick);
        row.add_child(button);
        callbacks.addButtonClickScaleEffect(button);
    }

    private _addPagerControls(row: St.BoxLayout, callbacks: PopupLogPanelCallbacks): void {
        const visibleLines = this._getVisibleLines();
        const totalPages = this._getPageCount(visibleLines);
        this._page = Math.min(this._page, totalPages - 1);

        this._addActionButton(row, 'go-previous-symbolic', 'Previous log page', () => {
            this._page = Math.max(0, this._page - 1);
            callbacks.refresh();
        }, callbacks, this._page > 0);

        const label = new St.Label({
            text: `${this._page + 1}/${totalPages}`,
            style_class: 'mei-log-page-label',
            y_align: Clutter.ActorAlign.CENTER,
        });
        row.add_child(label);

        this._addActionButton(row, 'go-next-symbolic', 'Next log page', () => {
            this._page = Math.min(totalPages - 1, this._page + 1);
            callbacks.refresh();
        }, callbacks, this._page < totalPages - 1);
    }

    private _trimLines(lines: string[]): string[] {
        if (lines.length <= LOG_MAX_LINES) return lines;

        const trimmed = lines.slice(-LOG_MAX_LINES);
        const nextText = trimmed.length > 0 ? trimmed.join('\n') + '\n' : '';
        void replaceLogFileTextAsync(nextText).catch(e => {
            Logger.warn(Tag.UI, `Failed to trim logs: ${e}`);
        });
        return trimmed;
    }

    private _getVisibleLines(): string[] {
        if (this._filter === 'All') return this._lines;
        const level = `[${this._filter.toUpperCase()}]`;
        return this._lines.filter(line => line.includes(level));
    }

    private _getVisibleIndexes(): number[] {
        if (this._filter === 'All') return this._lines.map((_line, index) => index);
        const level = `[${this._filter.toUpperCase()}]`;
        return this._lines.flatMap((line, index) => line.includes(level) ? [index] : []);
    }

    private _getPageCount(lines: string[]): number {
        return Math.max(1, Math.ceil(lines.length / LOG_LINES_PER_PAGE));
    }

    private _getPageBounds(length: number): [number, number] {
        const totalPages = Math.max(1, Math.ceil(length / LOG_LINES_PER_PAGE));
        this._page = Math.min(Math.max(0, this._page), totalPages - 1);
        const newestEnd = length - (this._page * LOG_LINES_PER_PAGE);
        const newestStart = Math.max(0, newestEnd - LOG_LINES_PER_PAGE);
        return [newestStart, newestEnd];
    }

    private _getPagedLines(lines: string[]): string[] {
        const [newestStart, newestEnd] = this._getPageBounds(lines.length);
        return lines.slice(newestStart, newestEnd);
    }

    private copyVisible(): void {
        const lines = this._getPagedLines(this._getVisibleLines());
        St.Clipboard.get_default().set_text(
            St.ClipboardType.CLIPBOARD,
            lines.slice().reverse().join('\n')
        );
    }

    private clearVisible(): void {
        try {
            const file = Gio.File.new_for_path(LOG_FILE);
            if (!file.query_exists(null)) return;

            const visibleIndexes = this._getVisibleIndexes();
            const [pageStart, pageEnd] = this._getPageBounds(visibleIndexes.length);
            const pageIndexes = new Set(visibleIndexes.slice(pageStart, pageEnd));
            this._lines = this._lines.filter((_line, index) => !pageIndexes.has(index));
            const nextText = this._lines.join('\n') + (this._lines.length > 0 ? '\n' : '');
            void replaceLogFileTextAsync(nextText).catch(e => {
                Logger.warn(Tag.UI, `Failed to clear logs: ${e}`);
            });
            this._page = Math.min(this._page, this._getPageCount(this._getVisibleLines()) - 1);
        } catch (e) {
            this._lines = [`[ERROR] Failed to clear logs: ${e}`];
        }
    }
}
