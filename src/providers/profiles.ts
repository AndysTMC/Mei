/**
 * Declarative provider profiles shared by setup, discovery, and runtime.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ProviderConfig, ProviderId } from './types.js';

export type ProviderType = 'local' | 'cloud' | 'custom';
export type ProviderApiMode = 'chat_completions' | 'responses' | 'anthropic_messages' | 'bedrock_converse';
export type ProviderAuthType = 'none' | 'bearer' | 'api_key' | 'aws_sdk' | 'oauth';
export type ModelEndpointKind = 'openai' | 'gemini' | 'ollama' | 'github';
export type ProviderTransport = 'openai' | 'anthropic' | 'gemini' | 'ollama' | 'llamacpp';

export interface ProviderProfile {
    id: ProviderId;
    aliases: readonly string[];
    label: string;
    type: ProviderType;
    transport: ProviderTransport;
    apiMode: ProviderApiMode;
    authType: ProviderAuthType;
    chatUrl: string;
    modelsUrl?: string;
    modelKind: ModelEndpointKind;
    modelAuthRequired: boolean;
    headers?: Readonly<Record<string, string>>;
    fallbackModels?: readonly string[];
}

export const PROVIDER_PROFILES: Record<ProviderId, ProviderProfile> = {
    ollama: profile('ollama', 'Ollama', 'local', 'ollama', 'none', 'http://127.0.0.1:11434/api/chat', 'ollama', {
        aliases: ['local'],
        fallbackModels: [],
    }),
    llamacpp: profile('llamacpp', 'llama.cpp', 'local', 'llamacpp', 'none', 'http://127.0.0.1:8080/v1/chat/completions', 'openai', {
        aliases: ['llama.cpp', 'llama-cpp'],
    }),
    lmstudio: profile('lmstudio', 'LM Studio', 'local', 'openai', 'none', 'http://127.0.0.1:1234/v1/chat/completions', 'openai', {
        aliases: ['lm-studio'],
    }),
    openai: profile('openai', 'OpenAI', 'cloud', 'openai', 'bearer', 'https://api.openai.com/v1/chat/completions', 'openai', {
        modelsUrl: 'https://api.openai.com/v1/models',
        fallbackModels: ['gpt-5.4', 'gpt-5.4-mini'],
    }),
    anthropic: profile('anthropic', 'Anthropic', 'cloud', 'anthropic', 'api_key', 'https://api.anthropic.com/v1/messages', 'openai', {
        modelsUrl: 'https://api.anthropic.com/v1/models?limit=1000',
        headers: { 'anthropic-version': '2023-06-01' },
        fallbackModels: ['claude-sonnet-4-6', 'claude-opus-4-6'],
    }),
    gemini: profile('gemini', 'Gemini', 'cloud', 'gemini', 'api_key', 'https://generativelanguage.googleapis.com/v1beta', 'gemini', {
        modelsUrl: 'https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000',
        fallbackModels: ['gemini-3-flash', 'gemini-3-pro'],
    }),
    groq: profile('groq', 'Groq', 'cloud', 'openai', 'bearer', 'https://api.groq.com/openai/v1/chat/completions', 'openai', {
        modelsUrl: 'https://api.groq.com/openai/v1/models',
    }),
    mistral: profile('mistral', 'Mistral', 'cloud', 'openai', 'bearer', 'https://api.mistral.ai/v1/chat/completions', 'openai', {
        modelsUrl: 'https://api.mistral.ai/v1/models',
    }),
    openrouter: profile('openrouter', 'OpenRouter', 'cloud', 'openai', 'bearer', 'https://openrouter.ai/api/v1/chat/completions', 'openai', {
        aliases: ['or'],
        modelsUrl: 'https://openrouter.ai/api/v1/models',
        modelAuthRequired: false,
        headers: { 'HTTP-Referer': 'https://github.com/AndysTMC/Mei', 'X-Title': 'Mei' },
        fallbackModels: ['anthropic/claude-sonnet-4.6', 'openai/gpt-5.4', 'deepseek/deepseek-chat'],
    }),
    opencode: profile('opencode', 'OpenCode', 'cloud', 'openai', 'bearer', 'https://opencode.ai/zen/go/v1/chat/completions', 'openai', {
        aliases: ['opencode-go', 'opencode-zen', 'go', 'zen'],
        headers: { 'HTTP-Referer': 'https://github.com/AndysTMC/Mei', 'X-Title': 'Mei' },
    }),
    githubcopilot: profile('githubcopilot', 'GitHub Models', 'cloud', 'openai', 'bearer', 'https://models.github.ai/inference/chat/completions', 'github', {
        aliases: ['github', 'github-models'],
        modelsUrl: 'https://models.github.ai/catalog/models',
        headers: { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10' },
    }),
    custom: profile('custom', 'Custom', 'custom', 'openai', 'none', 'http://127.0.0.1:8080/v1/chat/completions', 'openai', {
        aliases: ['vllm'],
    }),
};

interface ProfileOptions extends Partial<Omit<ProviderProfile, 'id' | 'label' | 'type' | 'transport' | 'authType' | 'chatUrl' | 'modelKind'>> { }

function profile(
    id: ProviderId,
    label: string,
    type: ProviderType,
    transport: ProviderTransport,
    authType: ProviderAuthType,
    chatUrl: string,
    modelKind: ModelEndpointKind,
    options: ProfileOptions = {}
): ProviderProfile {
    return {
        id,
        aliases: [],
        label,
        type,
        transport,
        apiMode: transport === 'anthropic' ? 'anthropic_messages' : 'chat_completions',
        authType,
        chatUrl,
        modelKind,
        modelAuthRequired: authType !== 'none',
        ...options,
    };
}

export function getProviderProfile(provider: ProviderId): ProviderProfile {
    return PROVIDER_PROFILES[provider];
}

export function resolveProviderId(value: string): ProviderId | null {
    const normalized = value.trim().toLowerCase();
    for (const provider of Object.values(PROVIDER_PROFILES)) {
        if (provider.id === normalized || provider.aliases.includes(normalized)) return provider.id;
    }
    return null;
}

export function getOpenCodeApiMode(model: string, mode: string): ProviderApiMode {
    const normalized = normalizeOpenCodeModelId(model).toLowerCase();
    const normalizedMode = mode.trim().toLowerCase();
    if (!normalized) return 'chat_completions';
    if (/^(?:gpt-|grok-|muse-spark)/.test(normalized)) return 'responses';
    if (normalizedMode === 'zen' && /^(?:claude-|qwen)/.test(normalized)) return 'anthropic_messages';
    if (normalizedMode !== 'zen' && /^(?:minimax-|qwen)/.test(normalized)) return 'anthropic_messages';
    return 'chat_completions';
}

export function normalizeOpenCodeModelId(model: string): string {
    return model.trim().split('/').at(-1) ?? '';
}

export function getOpenCodeBaseUrl(mode: string): string {
    return mode === 'zen' ? 'https://opencode.ai/zen/v1' : 'https://opencode.ai/zen/go/v1';
}

export function getApiModePath(apiMode: ProviderApiMode): string {
    if (apiMode === 'responses') return '/responses';
    if (apiMode === 'anthropic_messages') return '/messages';
    return '/chat/completions';
}

export interface ResolvedProviderRuntime {
    apiMode: ProviderApiMode;
    url: string;
}

export function resolveProviderRuntime(
    providerId: ProviderId,
    config: Pick<ProviderConfig, 'url' | 'model' | 'mode'>
): ResolvedProviderRuntime {
    const profile = getProviderProfile(providerId);
    const apiMode = providerId === 'opencode'
        ? getOpenCodeApiMode(config.model, config.mode ?? '')
        : profile.apiMode;
    if (providerId === 'opencode') {
        return {
            apiMode,
            url: `${getOpenCodeBaseUrl(config.mode ?? '')}${getApiModePath(apiMode)}`,
        };
    }
    return { apiMode, url: config.url || profile.chatUrl };
}
