/**
 * Turns the runtime's timeline (src/runtime/timeline.ts) into what the message list draws: the
 * requests and replies (each reply with its details), a task's live steps while it runs, and what
 * Mei remembered.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type St from 'gi://St';

import type { MessageView } from '../../runtime/protocol.js';
import type { ReplyDetails, TimelineItem } from '../../runtime/timeline.js';
import type { ChatMessageMetadata, ProviderId } from '../../providers/types.js';
import { activityBlock, memoryCard, type CardActions } from './cards.js';
import { attachmentLabel, attachmentOf, canOpen } from '../../runtime/attachment.js';
import type { ListedMessage } from './messageList.js';

export type ListedItem =
    /** `index` is the item's place in the timeline, passed back by regenerate. */
    | { kind: 'message'; message: ListedMessage; index: number }
    | { kind: 'card'; build: () => St.Widget };

/** `thumbnail(taskId, actionId)`: the small picture of the screen at the top of a task's steps. */
export function listedItems(items: TimelineItem[], actions: CardActions,
    thumbnail?: (taskId: string, actionId: string) => St.Widget): ListedItem[] {
    return items.map((item, index): ListedItem => {
        if (item.kind === 'message') {
            return { kind: 'message', message: { ...listedMessage(item.message, item.details), resumable: item.draft }, index };
        }
        if (item.kind === 'progress') {
            const { picture, taskId } = item;
            return { kind: 'card', build: () => activityBlock(item.rows, picture && thumbnail ? thumbnail(taskId, picture) : undefined) };
        }
        return { kind: 'card', build: () => memoryCard(item.memory, actions) };
    });
}

export function listedMessage(m: MessageView, details?: ReplyDetails): ListedMessage {
    const meta = m.metadata as Record<string, unknown>;
    const tokens = meta.tokens as { input?: number | null; output?: number | null } | undefined;
    const metadata: ChatMessageMetadata | undefined = m.role !== 'assistant' ? undefined : {
        providerId: (meta.id as ProviderId) || undefined,
        providerLabel: (meta.label as string) || undefined,
        model: (meta.model as string) || undefined,
        durationMs: typeof meta.duration_ms === 'number' ? meta.duration_ms : undefined,
        tokens: tokens ? { inputTokens: tokens.input ?? undefined, outputTokens: tokens.output ?? undefined } : undefined,
    };
    const attachment = m.role === 'user' ? attachmentOf(meta) : null;
    return { role: m.role, content: m.content, thinking: m.thinking ?? undefined, metadata,
        note: attachment ? attachmentLabel(attachment) : undefined, details,
        attachment: attachment && canOpen(attachment) ? attachment : undefined };
}
