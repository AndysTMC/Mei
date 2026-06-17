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
}

/** Configuration for initializing a provider. */
export interface ProviderConfig {
    url: string;
    model: string;
    apiKey?: string;
}

/** Interface that all AI providers must implement. */
export interface Provider {
    /** Human-readable name of this provider. */
    readonly name: string;

    /** Default API endpoint URL. */
    readonly defaultUrl: string;

    /**
     * Send a list of messages to the AI and return the assistant's reply.
     * The returned promise resolves with the text content of the response.
     */
    sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable
    ): Promise<string>;
}

/** Supported provider identifiers. */
export type ProviderId = 'ollama' | 'llamacpp' | 'openai' | 'anthropic' | 'gemini';
