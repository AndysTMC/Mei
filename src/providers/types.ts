/**
 * Type definitions for AI chat providers.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type Gio from 'gi://Gio';

/** A single message in a chat conversation. */
export interface ChatMessage {
    role: 'user' | 'assistant' | 'system';
    content: string;
    thinking?: string;
    metadata?: ChatMessageMetadata;
}

export interface ChatResponse {
    content: string;
    thinking?: string;
    usage?: TokenUsage;
}

export interface StreamUpdate {
    contentDelta?: string;
    thinkingDelta?: string;
}

export interface SendMessageOptions {
    stream?: boolean;
    onUpdate?: (update: StreamUpdate) => void;
}

export interface TokenUsage {
    inputTokens?: number;
    outputTokens?: number;
    totalTokens?: number;
}

export interface ChatMessageMetadata {
    providerId?: ProviderId;
    providerLabel?: string;
    providerType?: string;
    model?: string;
    endpoint?: string;
    durationMs?: number;
    tokens?: TokenUsage;
}

/** Configuration for initializing a provider. */
export interface ProviderConfig {
    url: string;
    model: string;
    apiKey?: string;
    mode?: string;
    thinking?: string;
    reasoningEffort?: string;
}

export type JsonObject = Record<string, unknown>;

/** Interface that all AI providers must implement. */
export interface Provider {
    /** Human-readable name of this provider. */
    readonly name: string;

    /** Default API endpoint URL. */
    readonly defaultUrl: string;

    /**
     * Send a list of messages to the AI and return the assistant's reply.
     */
    sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options?: SendMessageOptions
    ): Promise<ChatResponse>;
}

/** Supported provider identifiers. */
export type ProviderId = 'ollama' | 'llamacpp' | 'lmstudio' | 'openai' | 'anthropic' | 'gemini' | 'groq' | 'mistral' | 'openrouter' | 'custom' | 'opencode' | 'githubcopilot';

export function getStringAtPath(
    root: unknown,
    path: readonly (string | number)[]
): string | null {
    let current = root;

    for (const segment of path) {
        if (typeof segment === 'number') {
            if (!Array.isArray(current)) return null;
            current = current[segment];
        } else {
            if (typeof current !== 'object' || current === null || Array.isArray(current)) return null;
            current = (current as Record<string, unknown>)[segment];
        }
    }

    return typeof current === 'string' ? current : null;
}

export function getNumberAtPath(
    root: unknown,
    path: readonly (string | number)[]
): number | null {
    let current = root;

    for (const segment of path) {
        if (typeof segment === 'number') {
            if (!Array.isArray(current)) return null;
            current = current[segment];
        } else {
            if (typeof current !== 'object' || current === null || Array.isArray(current)) return null;
            current = (current as Record<string, unknown>)[segment];
        }
    }

    return typeof current === 'number' && Number.isFinite(current) ? current : null;
}

export function toApiMessages(messages: ChatMessage[]): Array<{ role: ChatMessage['role']; content: string }> {
    return messages.map(({ role, content }) => ({ role, content }));
}

export function createTokenUsage(
    inputTokens?: number | null,
    outputTokens?: number | null,
    totalTokens?: number | null
): TokenUsage | undefined {
    const input = normalizeTokenCount(inputTokens);
    const output = normalizeTokenCount(outputTokens);
    const total = normalizeTokenCount(totalTokens);
    const usage: TokenUsage = {};
    if (input !== null) usage.inputTokens = input;
    if (output !== null) usage.outputTokens = output;
    if (total !== null) {
        usage.totalTokens = total;
    } else if (input !== null && output !== null) {
        usage.totalTokens = input + output;
    }

    return Object.keys(usage).length > 0 ? usage : undefined;
}

function normalizeTokenCount(value: number | null | undefined): number | null {
    return typeof value === 'number' && Number.isFinite(value) && value >= 0
        ? Math.trunc(value)
        : null;
}

export function mergeTokenUsage(
    current: TokenUsage | undefined,
    update: TokenUsage | undefined
): TokenUsage | undefined {
    if (!current) return update;
    if (!update) return current;

    return createTokenUsage(
        update.inputTokens ?? current.inputTokens,
        update.outputTokens ?? current.outputTokens,
        update.totalTokens ?? current.totalTokens
    );
}

export function parseJsonObject(text: string): JsonObject | null {
    try {
        const parsed = JSON.parse(text) as unknown;
        if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
            return parsed as JsonObject;
        }
    } catch {
        // Streaming endpoints may send keepalive or partial frames; callers can ignore them.
    }
    return null;
}
