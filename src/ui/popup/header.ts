/**
 * The popup's top bar: Copy (compact mode), then the actions. Compact mode shows Clear; expanded
 * mode shows New chat and History instead.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import St from 'gi://St';

import { addClickScale, copyToClipboard, iconButton } from '../effects.js';
import type { SourceSet } from '../sources.js';

export interface HeaderActions {
    onClear(): void;
    onNewChat(): void;
    onHistory(): void;
    onToggleExpand(): void;
    onSettings(): void;
}

const COPIED_FOR_MS = 2000;

export class PopupHeader {
    readonly actor = new St.BoxLayout({ x_expand: true, style_class: 'mei-top-bar' });
    readonly copyButton: St.Button;
    private readonly _clearBtn: St.Button;
    private readonly _newChatBtn: St.Button;
    private readonly _historyBtn: St.Button;
    private readonly _expandBtn: St.Button;
    private readonly _settingsBtn: St.Button;
    private _copyText = '';
    private _copiedId = 0;

    constructor(private readonly _sources: SourceSet, actions: HeaderActions) {
        this.copyButton = new St.Button({
            label: 'Copy',
            style_class: 'mei-copy-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            visible: false,
            accessible_name: 'Copy latest response',
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        this.copyButton.connect('clicked', () => this._copy());
        addClickScale(this.copyButton);
        this.actor.add_child(this.copyButton);
        this.actor.add_child(new St.Widget({ x_expand: true })); // pushes the actions to the right

        this._clearBtn = iconButton('edit-clear-all-symbolic', 'Clear current chat');
        this._clearBtn.connect('clicked', () => actions.onClear());
        this._newChatBtn = iconButton('document-edit-symbolic', 'Start new chat');
        this._newChatBtn.connect('clicked', () => actions.onNewChat());
        this._historyBtn = iconButton('document-open-recent-symbolic', 'Show chat history');
        this._historyBtn.connect('clicked', () => actions.onHistory());
        this._expandBtn = iconButton('chat-symbolic', 'Expand chat');
        this._expandBtn.connect('clicked', () => actions.onToggleExpand());
        this._settingsBtn = iconButton('emblem-system-symbolic', 'Open Mei settings');
        this._settingsBtn.connect('clicked', () => actions.onSettings());
        for (const button of [this._clearBtn, this._newChatBtn, this._historyBtn, this._expandBtn, this._settingsBtn])
            this.actor.add_child(button);
        this.showModeButtons(false);
    }

    /** Which actions the mode offers. Changes at once when the mode toggles. */
    showModeButtons(expanded: boolean): void {
        this._clearBtn.visible = !expanded;
        this._newChatBtn.visible = expanded;
        this._historyBtn.visible = expanded;
    }

    /** The expand button's icon and name, updated once the content has faded out. */
    showExpandState(expanded: boolean): void {
        (this._expandBtn.child as St.Icon).icon_name = expanded ? 'bolt-symbolic' : 'chat-symbolic';
        this._expandBtn.accessible_name = expanded ? 'Collapse chat' : 'Expand chat';
    }

    /** Offer "Copy" for this reply (compact mode), or hide it with ''. */
    setCopyText(text: string): void {
        this._copyText = text;
        this.copyButton.visible = text.length > 0;
    }

    resetCopyState(): void {
        this._copiedId = this._sources.remove(this._copiedId);
        this.copyButton.set_label('Copy');
    }

    applyTheme(isDark: boolean): void {
        // Gray icons: visible, but quieter than the text.
        const style = `color: ${isDark ? '#a0a0a0' : '#666666'};`;
        for (const button of [this._clearBtn, this._newChatBtn, this._historyBtn, this._expandBtn, this._settingsBtn])
            button.set_style(style);
    }

    private _copy(): void {
        if (!this._copyText) return;
        copyToClipboard(this._copyText);
        this._sources.remove(this._copiedId);
        this.copyButton.set_label('Copied');
        this._copiedId = this._sources.timeout(COPIED_FOR_MS, () => {
            this._copiedId = 0;
            this.copyButton.set_label('Copy');
            return false;
        });
    }
}
