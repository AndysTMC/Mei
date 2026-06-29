/**
 * Type definitions for AI chat providers.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import Gio from 'gi://Gio';

/** A single message in a chat conversation. */
export interface ChatMessage {
    role: 'user' | 'assistant' | 'system';
    content: string;
    thinking?: string;
}

export interface ChatResponse {
    content: string;
    thinking?: string;
}

export interface StreamUpdate {
    contentDelta?: string;
    thinkingDelta?: string;
}

export interface SendMessageOptions {
    stream?: boolean;
    onUpdate?: (update: StreamUpdate) => void;
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
export type ProviderId = 'ollama' | 'llamacpp' | 'openai' | 'anthropic' | 'gemini' | 'groq' | 'mistral' | 'openrouter' | 'deepseek' | 'custom' | 'opencode';

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

export function toApiMessages(messages: ChatMessage[]): Array<{ role: ChatMessage['role']; content: string }> {
    return messages.map(({ role, content }) => ({ role, content }));
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
