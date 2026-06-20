import Gio from 'gi://Gio';
import St from 'gi://St';

import { Logger, Tag } from './logger.js';

export interface ThemedWidgets {
    menuBox?: St.Widget;
    popupItem?: St.Widget;
    container?: St.Widget;
    entry?: St.Entry;
    askBtn?: St.Button;
    copyBtn?: St.Button;
}

/**
 * Monitors the system color scheme and applies dark/light styles
 * to the chat popup widgets.
 */
export class ThemeManager {
    private _settings: Gio.Settings;
    private _signalId: number;
    private _callbackSignalIds: Set<number> = new Set();
    private _isDark: boolean;

    constructor() {
        this._settings = new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' });
        this._isDark = this._settings.get_string('color-scheme') === 'prefer-dark';
        Logger.debug(Tag.Theme, `Initial theme: ${this._isDark ? 'dark' : 'light'}`);
        this._signalId = this._settings.connect('changed::color-scheme', () => {
            const wasDark = this._isDark;
            this._isDark = this._settings.get_string('color-scheme') === 'prefer-dark';
            if (wasDark !== this._isDark) {
                Logger.debug(Tag.Theme, `Theme changed: ${this._isDark ? 'dark' : 'light'}`);
            }
        });
    }

    get isDark(): boolean {
        return this._isDark;
    }

    /**
     * Apply theme colors to the given set of widgets.
     */
    applyTheme(widgets: ThemedWidgets): void {
        const bg = this._isDark ? '#000000' : '#ffffff';
        const fg = this._isDark ? '#ffffff' : '#000000';
        const hintFg = this._isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.35)';
        const askBg = this._isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';

        if (widgets.menuBox)
            widgets.menuBox.set_style(
                `padding: 0; margin: 0; background-color: ${bg}; border-radius: 12px;`
            );
        if (widgets.popupItem)
            widgets.popupItem.set_style(
                `padding: 0; margin: 0; background-color: ${bg};`
            );
        if (widgets.container)
            widgets.container.set_style(
                `background-color: ${bg}; color: ${fg}; padding: 10px; border-radius: 12px;`
            );
        if (widgets.entry)
            widgets.entry.set_style(
                `color: ${fg}; caret-color: ${fg}; -st-hint-color: ${hintFg};`
            );
        if (widgets.askBtn)
            widgets.askBtn.set_style(
                `background-color: ${askBg}; color: ${fg};`
            );
        if (widgets.copyBtn) {
            widgets.copyBtn.set_style(
                `background-color: ${askBg}; color: ${fg};`
            );
        }
    }

    /**
     * Connect a callback to be invoked whenever the theme changes.
     */
    onThemeChanged(callback: () => void): number {
        const signalId = this._settings.connect('changed::color-scheme', callback);
        this._callbackSignalIds.add(signalId);
        return signalId;
    }

    disconnect(signalId: number): void {
        if (signalId === 0 || !this._callbackSignalIds.delete(signalId)) return;
        this._settings.disconnect(signalId);
    }

    destroy(): void {
        if (this._signalId && this._settings) {
            this._settings.disconnect(this._signalId);
            this._signalId = 0;
        }

        for (const signalId of this._callbackSignalIds) {
            this._settings.disconnect(signalId);
        }
        this._callbackSignalIds.clear();
    }
}
