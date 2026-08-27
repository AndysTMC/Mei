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

export const MAX_CHAT_SESSIONS = 500;
export const MAX_CHAT_MESSAGES_PER_SESSION = 2000;
export const MAX_CHAT_MESSAGE_CHARS = 2 * 1024 * 1024;
const MAX_CHAT_ID_CHARS = 256;
const MAX_CHAT_TITLE_CHARS = 1024;
const MAX_METADATA_STRING_CHARS = 16384;

export function parseChatSessions(value: unknown): ChatSession[] {
    if (!Array.isArray(value)) return [];

    const sessions: ChatSession[] = [];
    const ids = new Set<string>();
    for (const valueSession of value) {
        if (sessions.length >= MAX_CHAT_SESSIONS) break;
        if (!isChatSession(valueSession) || ids.has(valueSession.id)) continue;
        ids.add(valueSession.id);
        sessions.push(valueSession);
    }
    return sessions;
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
        isBoundedString(candidate.content, MAX_CHAT_MESSAGE_CHARS) &&
        (candidate.thinking === undefined || isBoundedString(candidate.thinking, MAX_CHAT_MESSAGE_CHARS)) &&
        (candidate.metadata === undefined || isChatMetadata(candidate.metadata));
}

function isChatSession(value: unknown): value is ChatSession {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const candidate = value as Record<string, unknown>;
    return isBoundedString(candidate.id, MAX_CHAT_ID_CHARS) && candidate.id.length > 0 &&
        isBoundedString(candidate.title, MAX_CHAT_TITLE_CHARS) &&
        Array.isArray(candidate.messages) &&
        candidate.messages.length <= MAX_CHAT_MESSAGES_PER_SESSION &&
        candidate.messages.every(isChatMessage) &&
        isNonNegativeFiniteNumber(candidate.createdAt) &&
        isNonNegativeFiniteNumber(candidate.updatedAt);
}

function isChatMetadata(value: unknown): boolean {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const metadata = value as Record<string, unknown>;
    return (metadata.providerId === undefined || isBoundedString(metadata.providerId, MAX_METADATA_STRING_CHARS)) &&
        (metadata.providerLabel === undefined || isBoundedString(metadata.providerLabel, MAX_METADATA_STRING_CHARS)) &&
        (metadata.providerType === undefined || isBoundedString(metadata.providerType, MAX_METADATA_STRING_CHARS)) &&
        (metadata.model === undefined || isBoundedString(metadata.model, MAX_METADATA_STRING_CHARS)) &&
        (metadata.endpoint === undefined || isBoundedString(metadata.endpoint, MAX_METADATA_STRING_CHARS)) &&
        (metadata.durationMs === undefined || isNonNegativeFiniteNumber(metadata.durationMs)) &&
        (metadata.tokens === undefined || isTokenUsage(metadata.tokens));
}

function isTokenUsage(value: unknown): boolean {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const tokens = value as Record<string, unknown>;
    return (tokens.inputTokens === undefined || isNonNegativeFiniteNumber(tokens.inputTokens)) &&
        (tokens.outputTokens === undefined || isNonNegativeFiniteNumber(tokens.outputTokens)) &&
        (tokens.totalTokens === undefined || isNonNegativeFiniteNumber(tokens.totalTokens));
}

function isNonNegativeFiniteNumber(value: unknown): value is number {
    return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function isBoundedString(value: unknown, maxChars: number): value is string {
    return typeof value === 'string' && value.length <= maxChars;
}
