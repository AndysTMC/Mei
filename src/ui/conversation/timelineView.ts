/**
 * Turns the runtime's timeline (src/runtime/timeline.ts) into what the message list draws:
 * messages as before, and the agent's cards as widgets built when the list is drawn.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type St from 'gi://St';

import type { MessageView } from '../../runtime/protocol.js';
import type { TimelineItem } from '../../runtime/timeline.js';
import type { ChatMessageMetadata, ProviderId } from '../../providers/types.js';
import { activityBlock, approvalCard, memoryCard, outcomeLine, planCard, questionCard, type CardActions } from './cards.js';
import { attachmentLabel, attachmentOf } from '../../runtime/attachment.js';
import type { ListedMessage } from './messageList.js';

export type ListedItem =
    /** `index` is the item's place in the timeline, passed back by ↻. */
    | { kind: 'message'; message: ListedMessage; index: number }
    | { kind: 'card'; build: () => St.Widget };

export function listedItems(items: TimelineItem[], actions: CardActions): ListedItem[] {
    return items.map((item, index): ListedItem => {
        if (item.kind === 'message') return { kind: 'message', message: listedMessage(item.message), index };
        return { kind: 'card', build: () => cardFor(item, actions) };
    });
}

/** The card a compact popup shows on its own when the task waits on the person, if any. */
export function waitingCard(items: TimelineItem[], actions: CardActions): (() => St.Widget) | null {
    const card = items.findLast(i => i.kind === 'approval' || i.kind === 'question');
    return card ? () => cardFor(card, actions) : null;
}

function cardFor(item: Exclude<TimelineItem, { kind: 'message' }>, actions: CardActions): St.Widget {
    switch (item.kind) {
    case 'activity':
        return activityBlock(item.rows);
    case 'plan':
        return planCard(item.plan);
    case 'approval':
        return approvalCard(item.approval, actions);
    case 'question':
        return questionCard(item.request, actions);
    case 'outcome':
        return outcomeLine(item.outcome);
    case 'memory':
        return memoryCard(item.memory, actions);
    }
}

export function listedMessage(m: MessageView): ListedMessage {
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
        note: attachment ? attachmentLabel(attachment) : undefined };
}
