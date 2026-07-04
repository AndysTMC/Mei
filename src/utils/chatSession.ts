/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ChatMessage } from '../providers/types.js';

export interface ChatSession {
    id: string;
    title: string;
    messages: ChatMessage[];
    createdAt: number;
    updatedAt: number;
}

export function parseChatSessions(value: unknown): ChatSession[] {
    if (!Array.isArray(value)) return [];

    return value.filter((session): session is ChatSession => {
        if (typeof session !== 'object' || session === null) return false;
        const candidate = session as Record<string, unknown>;
        return typeof candidate.id === 'string' &&
            typeof candidate.title === 'string' &&
            Array.isArray(candidate.messages) &&
            candidate.messages.every(isChatMessage) &&
            isFiniteNumber(candidate.createdAt) &&
            isFiniteNumber(candidate.updatedAt);
    });
}

export function generateChatId(): string {
    return `${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 8)}`;
}

export function generateChatTitle(messages: ChatMessage[]): string {
    const firstUser = messages.find(m => m.role === 'user');
    if (!firstUser) return 'New Chat';
    const text = firstUser.content.trim();
    if (!text) return 'New Chat';
    return text.length > 40 ? `${text.substring(0, 40)}\u2026` : text;
}

function isChatMessage(value: unknown): value is ChatMessage {
    if (typeof value !== 'object' || value === null) return false;
    const candidate = value as Record<string, unknown>;
    return (candidate.role === 'user' ||
        candidate.role === 'assistant' ||
        candidate.role === 'system') &&
        typeof candidate.content === 'string' &&
        (candidate.thinking === undefined || typeof candidate.thinking === 'string') &&
        (candidate.metadata === undefined || isChatMetadata(candidate.metadata));
}

function isChatMetadata(value: unknown): boolean {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const metadata = value as Record<string, unknown>;
    return (metadata.providerId === undefined || typeof metadata.providerId === 'string') &&
        (metadata.providerLabel === undefined || typeof metadata.providerLabel === 'string') &&
        (metadata.providerType === undefined || typeof metadata.providerType === 'string') &&
        (metadata.model === undefined || typeof metadata.model === 'string') &&
        (metadata.endpoint === undefined || typeof metadata.endpoint === 'string') &&
        (metadata.durationMs === undefined || isFiniteNumber(metadata.durationMs)) &&
        (metadata.tokens === undefined || isTokenUsage(metadata.tokens));
}

function isTokenUsage(value: unknown): boolean {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const tokens = value as Record<string, unknown>;
    return (tokens.inputTokens === undefined || isFiniteNumber(tokens.inputTokens)) &&
        (tokens.outputTokens === undefined || isFiniteNumber(tokens.outputTokens)) &&
        (tokens.totalTokens === undefined || isFiniteNumber(tokens.totalTokens));
}

function isFiniteNumber(value: unknown): value is number {
    return typeof value === 'number' && Number.isFinite(value);
}
