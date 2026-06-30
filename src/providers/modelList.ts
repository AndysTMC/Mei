/**
 * Provider model-list fetching utilities.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {
    getOpenCodeMode,
    getOpenCodeModelsUrl,
    isOpenCodeChatCompletionsModel,
    type OpenCodeMode,
} from './catalog.js';
import type { ProviderId } from './types.js';

export interface ModelListConfig {
    url: string;
    apiKey: string;
    mode: string;
}

export interface ModelListResult {
    models: string[];
    requiresApiKey: boolean;
}

export async function fetchProviderModels(
    session: Soup.Session,
    provider: ProviderId,
    config: ModelListConfig,
    cancellable: Gio.Cancellable
): Promise<ModelListResult> {
    const apiKey = config.apiKey || '';
    const endpoint = getModelEndpoint(provider, config);
    if (!endpoint) return { models: [], requiresApiKey: false };

    if (endpoint.requiresApiKey && !apiKey) {
        return { models: [], requiresApiKey: true };
    }

    const msg = Soup.Message.new('GET', endpoint.url);
    if (!msg) throw new Error('Invalid URL');

    for (const [key, value] of Object.entries(endpoint.headers)) {
        msg.get_request_headers().append(key, value);
    }

    const bytes = await session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, cancellable);
    const data = bytes.get_data();
    const text = data ? new TextDecoder().decode(data) : '';
    if (msg.get_status() >= 400) {
        throw new Error(`HTTP ${msg.get_status()}`);
    }

    return {
        models: parseModelList(text, endpoint.kind, endpoint.openCodeMode),
        requiresApiKey: endpoint.requiresApiKey,
    };
}

type ModelEndpointKind = 'openai' | 'gemini' | 'ollama' | 'github';

interface ModelEndpoint {
    url: string;
    headers: Record<string, string>;
    requiresApiKey: boolean;
    kind: ModelEndpointKind;
    openCodeMode: OpenCodeMode | null;
}

function getModelEndpoint(provider: ProviderId, config: ModelListConfig): ModelEndpoint | null {
    const apiKey = config.apiKey || '';
    switch (provider) {
        case 'ollama':
            return {
                url: replacePath(config.url || 'http://127.0.0.1:11434/api/chat', '/api/tags'),
                headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
                requiresApiKey: false,
                kind: 'ollama',
                openCodeMode: null,
            };
        case 'llamacpp':
            return {
                url: replacePath(config.url || 'http://127.0.0.1:8080/v1/chat/completions', '/v1/models'),
                headers: {},
                requiresApiKey: false,
                kind: 'openai',
                openCodeMode: null,
            };
        case 'lmstudio':
            return {
                url: replacePath(config.url || 'http://127.0.0.1:1234/v1/chat/completions', '/v1/models'),
                headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
                requiresApiKey: false,
                kind: 'openai',
                openCodeMode: null,
            };
        case 'openai':
            return bearerEndpoint('https://api.openai.com/v1/models', apiKey);
        case 'groq':
            return bearerEndpoint('https://api.groq.com/openai/v1/models', apiKey);
        case 'mistral':
            return bearerEndpoint('https://api.mistral.ai/v1/models', apiKey);
        case 'openrouter':
            return bearerEndpoint('https://openrouter.ai/api/v1/models', apiKey);
        case 'deepseek':
            return bearerEndpoint('https://api.deepseek.com/models', apiKey);
        case 'opencode': {
            const mode = getOpenCodeMode(config.mode);
            return {
                ...bearerEndpoint(getOpenCodeModelsUrl(mode), apiKey),
                openCodeMode: mode,
            };
        }
        case 'githubcopilot':
            return {
                url: 'https://models.github.ai/catalog/models',
                headers: {
                    Authorization: `Bearer ${apiKey}`,
                    Accept: 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2026-03-10',
                },
                requiresApiKey: true,
                kind: 'github',
                openCodeMode: null,
            };
        case 'anthropic':
            return {
                url: 'https://api.anthropic.com/v1/models',
                headers: {
                    'x-api-key': apiKey,
                    'anthropic-version': '2023-06-01',
                },
                requiresApiKey: true,
                kind: 'openai',
                openCodeMode: null,
            };
        case 'gemini':
            return {
                url: `https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`,
                headers: {},
                requiresApiKey: true,
                kind: 'gemini',
                openCodeMode: null,
            };
        case 'custom':
            if (!config.url.trim()) {
                throw new Error('Enter an endpoint URL to fetch models.');
            }
            return {
                url: replacePath(config.url, '/v1/models'),
                headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
                requiresApiKey: false,
                kind: 'openai',
                openCodeMode: null,
            };
        default:
            return null;
    }
}

function bearerEndpoint(url: string, apiKey: string): ModelEndpoint {
    return {
        url,
        headers: { Authorization: `Bearer ${apiKey}` },
        requiresApiKey: true,
        kind: 'openai',
        openCodeMode: null,
    };
}

function parseModelList(text: string, kind: ModelEndpointKind, openCodeMode: OpenCodeMode | null): string[] {
    const parsed = JSON.parse(text) as unknown;
    if (typeof parsed !== 'object' || parsed === null || (Array.isArray(parsed) && kind !== 'github')) {
        return [];
    }

    const root = Array.isArray(parsed) ? {} : parsed as Record<string, unknown>;
    const items = kind === 'github'
        ? Array.isArray(parsed) ? parsed : root.models ?? root.data
        : kind === 'gemini'
            ? root.models
            : kind === 'ollama'
                ? root.models
                : root.data;
    if (!Array.isArray(items)) return [];

    return items.flatMap(item => {
        if (typeof item !== 'object' || item === null || Array.isArray(item)) return [];
        const model = item as Record<string, unknown>;
        const value = getModelName(model, kind);
        if (!value) return [];

        if (openCodeMode) {
            const endpoint = typeof model.endpoint === 'string' ? model.endpoint : '';
            if (endpoint && !endpoint.endsWith('/chat/completions')) return [];
            if (!endpoint && !isOpenCodeChatCompletionsModel(value, openCodeMode)) return [];
        }

        return value;
    });
}

function getModelName(model: Record<string, unknown>, kind: ModelEndpointKind): string | null {
    const value = kind === 'gemini'
        ? model.name
        : kind === 'ollama'
            ? model.name ?? model.model
            : model.id ?? model.display_name;
    if (typeof value !== 'string' || value.length === 0) return null;
    return kind === 'gemini' ? value.replace('models/', '') : value;
}

function replacePath(url: string, path: string): string {
    const match = url.match(/^(https?:\/\/[^/]+)(?:\/.*)?$/);
    if (!match) {
        return url;
    }
    return `${match[1]}${path}`;
}
