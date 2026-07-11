/**
 * Provider catalog shared by Shell UI, preferences, and provider setup.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ProviderId } from './types.js';

export type ProviderType = 'local' | 'cloud' | 'custom';
export type OpenCodeMode = 'go' | 'zen';

export const PROVIDER_TYPE_LABELS: Record<ProviderType, string> = {
    local: 'Local',
    cloud: 'Cloud',
    custom: 'Custom',
};

export const PROVIDER_LABELS: Record<ProviderId, string> = {
    ollama: 'Ollama',
    llamacpp: 'llama.cpp',
    lmstudio: 'LM Studio',
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    gemini: 'Gemini',
    groq: 'Groq',
    mistral: 'Mistral',
    openrouter: 'OpenRouter',
    custom: 'Custom',
    opencode: 'OpenCode',
    githubcopilot: 'GitHub Models',
};

export const PROVIDER_TYPE_IDS: ProviderType[] = ['local', 'cloud', 'custom'];
export const LOCAL_PROVIDER_IDS: ProviderId[] = ['ollama', 'llamacpp', 'lmstudio'];
export const CLOUD_PROVIDER_IDS: ProviderId[] = [
    'openai',
    'anthropic',
    'gemini',
    'groq',
    'mistral',
    'openrouter',
    'opencode',
    'githubcopilot',
];
export const CUSTOM_PROVIDER_IDS: ProviderId[] = ['custom'];

export const OPEN_CODE_MODE_LABELS: Record<OpenCodeMode, string> = {
    go: 'Go',
    zen: 'Zen',
};

const OPEN_CODE_CHAT_MODEL_IDS: Record<OpenCodeMode, readonly string[]> = {
    go: [
        'glm-5.2',
        'glm-5.1',
        'kimi-k2.7-code',
        'kimi-k2.6',
        'deepseek-v4-pro',
        'deepseek-v4-flash',
        'mimo-v2.5',
        'mimo-v2.5-pro',
    ],
    zen: [
        'deepseek-v4-pro',
        'deepseek-v4-flash',
        'minimax-m3',
        'minimax-m2.7',
        'minimax-m2.5',
        'glm-5.2',
        'glm-5.1',
        'glm-5',
        'kimi-k2.5',
        'kimi-k2.6',
        'kimi-k2.7-code',
        'grok-build-0.1',
        'grok-4.5',
        'big-pickle',
        'mimo-v2.5-free',
        'north-mini-code-free',
        'nemotron-3-ultra-free',
        'deepseek-v4-flash-free',
    ],
};

export function getProviderType(value: string): ProviderType {
    return value === 'local' || value === 'custom' ? value : 'cloud';
}

export function getProviderIdsForType(type: ProviderType): ProviderId[] {
    if (type === 'local') return LOCAL_PROVIDER_IDS;
    if (type === 'custom') return CUSTOM_PROVIDER_IDS;
    return CLOUD_PROVIDER_IDS;
}

export function isProviderId(value: string): value is ProviderId {
    return value in PROVIDER_LABELS;
}

export function getProviderLabel(provider: string): string {
    return isProviderId(provider) ? PROVIDER_LABELS[provider] : provider;
}

export function getOpenCodeMode(value: string | undefined): OpenCodeMode {
    return value === 'zen' ? 'zen' : 'go';
}

export function getOpenCodeChatCompletionsUrl(mode: OpenCodeMode): string {
    return mode === 'zen'
        ? 'https://opencode.ai/zen/v1/chat/completions'
        : 'https://opencode.ai/zen/go/v1/chat/completions';
}

export function getOpenCodeModelsUrl(mode: OpenCodeMode): string {
    return mode === 'zen'
        ? 'https://opencode.ai/zen/v1/models'
        : 'https://opencode.ai/zen/go/v1/models';
}

export function getOpenCodeModelId(model: string): string {
    return model.replace(/^opencode-go\//, '').replace(/^opencode\//, '');
}

export function isOpenCodeChatCompletionsModel(model: string, mode: OpenCodeMode): boolean {
    return OPEN_CODE_CHAT_MODEL_IDS[mode].includes(getOpenCodeModelId(model));
}

export function getModelListUrl(chatUrl: string, modelPath: '/api/tags' | '/v1/models'): string {
    const match = chatUrl.trim().match(/^(https?:\/\/[^/?#]+)([^?#]*)/i);
    if (!match) return chatUrl;

    const origin = match[1];
    const currentPath = (match[2] || '').replace(/\/+$/, '');
    const chatSuffix = modelPath === '/api/tags' ? '/api/chat' : '/v1/chat/completions';
    if (currentPath.endsWith(chatSuffix)) {
        return `${origin}${currentPath.slice(0, -chatSuffix.length)}${modelPath}`;
    }
    return `${origin}${modelPath}`;
}
