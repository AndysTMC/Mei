/**
 * Provider model-list fetching utilities.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {
    getOpenCodeMode,
    getOpenCodeModelsUrl,
    getModelListUrl,
    type OpenCodeMode,
} from './catalog.js';
import { getProviderProfile, type ModelEndpointKind } from './profiles.js';
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
        return {
            models: [...(getProviderProfile(provider).fallbackModels ?? [])],
            requiresApiKey: true,
        };
    }

    const models: string[] = [];
    let pageUrl: string | null = endpoint.url;
    for (let page = 0; page < 10 && pageUrl; page++) {
        const msg = createModelRequest(pageUrl, endpoint.headers);
        const text = await readModelPage(session, msg, cancellable);
        models.push(...parseModelList(text, endpoint.kind, endpoint.openCodeMode));
        pageUrl = getNextPageUrl(pageUrl, text, endpoint.kind);
    }
    const fallbackModels = getProviderProfile(provider).fallbackModels ?? [];

    return {
        models: models.length > 0 ? [...new Set(models)] : [...fallbackModels],
        requiresApiKey: endpoint.requiresApiKey,
    };
}

export type { ModelEndpointKind } from './profiles.js';

export interface ModelEndpoint {
    url: string;
    headers: Record<string, string>;
    requiresApiKey: boolean;
    kind: ModelEndpointKind;
    openCodeMode: OpenCodeMode | null;
}

export function getModelEndpoint(provider: ProviderId, config: ModelListConfig): ModelEndpoint | null {
    const apiKey = config.apiKey || '';
    const profile = getProviderProfile(provider);
    const headers: Record<string, string> = { ...profile.headers };
    if (apiKey) {
        if (profile.authType === 'api_key') {
            headers[provider === 'gemini' ? 'x-goog-api-key' : 'x-api-key'] = apiKey;
        } else {
            headers.Authorization = `Bearer ${apiKey}`;
        }
    }

    if (provider === 'custom' && !config.url.trim()) {
        throw new Error('Enter an endpoint URL to fetch models.');
    }

    let url = profile.modelsUrl ?? getModelListUrl(config.url || profile.chatUrl, provider === 'ollama' ? '/api/tags' : '/v1/models');
    if (provider === 'gemini' && config.url) {
        url = `${stripTrailingSlash(config.url)}/models?pageSize=1000`;
    } else if (provider === 'opencode') {
        url = getOpenCodeModelsUrl(getOpenCodeMode(config.mode));
    } else if (config.url && provider !== 'gemini') {
        url = getModelListUrl(config.url, provider === 'ollama' ? '/api/tags' : '/v1/models');
    }

    return {
        url,
        headers,
        requiresApiKey: profile.modelAuthRequired,
        kind: profile.modelKind,
        openCodeMode: provider === 'opencode' ? getOpenCodeMode(config.mode) : null,
    };
}

export function parseModelList(text: string, kind: ModelEndpointKind, _openCodeMode: OpenCodeMode | null): string[] {
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

    const models = items.flatMap(item => {
        if (typeof item !== 'object' || item === null || Array.isArray(item)) return [];
        const model = item as Record<string, unknown>;
        if (kind === 'gemini' && Array.isArray(model.supportedGenerationMethods) &&
            !model.supportedGenerationMethods.includes('generateContent')) {
            return [];
        }
        const value = getModelName(model, kind);
        if (!value) return [];

        return value;
    });
    return [...new Set(models)];
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

function stripTrailingSlash(url: string): string {
    return url.replace(/\/+$/, '');
}

async function readModelPage(
    session: Soup.Session,
    msg: Soup.Message,
    cancellable: Gio.Cancellable
): Promise<string> {
    const bytes = await session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, cancellable);
    const data = bytes.get_data();
    const text = data ? new TextDecoder().decode(data) : '';
    if (msg.get_status() >= 400) {
        const detail = getErrorDetail(text);
        throw new Error(`HTTP ${msg.get_status()}${detail ? `: ${detail}` : ''}`);
    }
    return text;
}

function getErrorDetail(text: string): string {
    try {
        const parsed = JSON.parse(text) as Record<string, unknown>;
        const error = parsed.error;
        if (typeof error === 'string') return error.slice(0, 240);
        if (typeof error === 'object' && error !== null) {
            const message = (error as Record<string, unknown>).message;
            if (typeof message === 'string') return message.slice(0, 240);
        }
        if (typeof parsed.message === 'string') return parsed.message.slice(0, 240);
    } catch {
        return text.trim().replace(/\s+/g, ' ').slice(0, 240);
    }
    return '';
}

function createModelRequest(url: string, headers: Record<string, string>): Soup.Message {
    const msg = Soup.Message.new('GET', url);
    if (!msg) throw new Error(`Invalid model catalog URL: ${url}`);
    for (const [key, value] of Object.entries(headers)) {
        msg.get_request_headers().append(key, value);
    }
    return msg;
}

export function getNextPageUrl(currentUrl: string, text: string, kind: ModelEndpointKind): string | null {
    let root: Record<string, unknown>;
    try {
        const parsed = JSON.parse(text) as unknown;
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null;
        root = parsed as Record<string, unknown>;
    } catch {
        return null;
    }

    if (typeof root.next === 'string' && /^https?:\/\//i.test(root.next)) return root.next;
    const token = root.nextPageToken ?? root.next_page_token;
    if (typeof token === 'string' && token) {
        return withQueryParam(currentUrl, kind === 'gemini' ? 'pageToken' : 'page_token', token);
    }
    if (root.has_more === true && Array.isArray(root.data)) {
        const last = root.data.at(-1);
        if (typeof last === 'object' && last !== null && !Array.isArray(last)) {
            const id = (last as Record<string, unknown>).id;
            if (typeof id === 'string' && id) return withQueryParam(currentUrl, 'after_id', id);
        }
    }
    return null;
}

function withQueryParam(url: string, key: string, value: string): string {
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
}
