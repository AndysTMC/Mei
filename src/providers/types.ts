/**
 * Message and provider types shared by the UI. Talking to providers is the runtime's job.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

/** A single message in a chat conversation, as the popup renders it. */
export interface ChatMessage {
    role: 'user' | 'assistant' | 'system';
    content: string;
    thinking?: string;
    metadata?: ChatMessageMetadata;
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

export type ProviderId = 'ollama' | 'llamacpp' | 'lmstudio' | 'openai' | 'anthropic' | 'gemini' | 'groq' | 'mistral' | 'openrouter' | 'deepseek' | 'fireworks' | 'nvidia' | 'custom' | 'opencode' | 'githubcopilot';
