/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import type { ChatMessageMetadata, TokenUsage } from '../providers/types.js';

const MESSAGE_INFO_MAX_HEIGHT = 160;

export function createMessageInfoPanel(metadata: ChatMessageMetadata | undefined, isDark: boolean): St.BoxLayout {
    const panel = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        visible: false,
        style_class: 'mei-message-info-panel',
    });
    styleMessageInfoPanel(panel, isDark);
    panel.add_child(new St.Label({
        text: 'Response Information',
        x_expand: true,
        style_class: 'mei-message-info-title',
    }));

    const scrollView = new St.ScrollView({
        style_class: 'mei-message-info-scroll',
        x_expand: true,
        overlay_scrollbars: true,
    });
    scrollView.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
    scrollView.set_style(`max-height: ${MESSAGE_INFO_MAX_HEIGHT}px;`);

    const rows = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style_class: 'mei-message-info-content',
    });
    scrollView.set_child(rows);
    panel.add_child(scrollView);

    if (!metadata) {
        addMessageInfoRow(rows, 'Status', 'Unavailable for this response');
        return panel;
    }

    const provider = [
        metadata.providerLabel || metadata.providerId || 'Unavailable',
        metadata.providerType ? `(${metadata.providerType})` : '',
    ].filter(Boolean).join(' ');

    addMessageInfoRow(rows, 'Provider', provider);
    addMessageInfoRow(rows, 'Model', metadata.model || 'Unavailable');
    addMessageInfoRow(rows, 'Time', formatDuration(metadata.durationMs));
    addMessageInfoRow(rows, 'Tokens', formatTokens(metadata.tokens));

    return panel;
}

export function styleMessageInfoPanel(panel: St.Widget, isDark: boolean): void {
    const fg = isDark ? '#ffffff' : '#000000';
    const bg = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
    panel.set_style(`background-color: ${bg}; color: ${fg};`);
}

function addMessageInfoRow(panel: St.BoxLayout, label: string, value: string): void {
    const row = new St.BoxLayout({
        x_expand: true,
        style_class: 'mei-message-info-row',
    });

    const keyLabel = new St.Label({
        text: label,
        style_class: 'mei-message-info-key',
        y_align: Clutter.ActorAlign.START,
    });
    row.add_child(keyLabel);

    const valueLabel = new St.Label({
        text: value,
        x_expand: true,
        style_class: 'mei-message-info-value',
    });
    valueLabel.clutter_text.set_line_wrap(true);
    valueLabel.clutter_text.set_line_wrap_mode(0);
    valueLabel.clutter_text.set_ellipsize(0);
    row.add_child(valueLabel);

    panel.add_child(row);
}

function formatDuration(durationMs: number | undefined): string {
    if (typeof durationMs !== 'number' || !Number.isFinite(durationMs)) {
        return 'Unavailable';
    }
    if (durationMs < 1000) {
        return `${Math.round(durationMs)} ms`;
    }
    return `${(durationMs / 1000).toFixed(1)} s`;
}

function formatTokens(tokens: TokenUsage | undefined): string {
    if (!tokens) return 'Unavailable';

    const parts: string[] = [];
    if (typeof tokens.totalTokens === 'number') {
        parts.push(`${tokens.totalTokens} total`);
    }
    if (typeof tokens.inputTokens === 'number') {
        parts.push(`${tokens.inputTokens} in`);
    }
    if (typeof tokens.outputTokens === 'number') {
        parts.push(`${tokens.outputTokens} out`);
    }
    return parts.length > 0 ? parts.join(' · ') : 'Unavailable';
}
