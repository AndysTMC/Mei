/**
 * Provider catalog shared by Shell UI, preferences, and provider setup.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ProviderId } from './types.js';
import { normalizeOpenCodeModelId, PROVIDER_PROFILES, resolveProviderId, type ProviderType } from './profiles.js';

export type { ProviderType } from './profiles.js';
export type OpenCodeMode = 'go' | 'zen';
export type DeepSeekThinking = 'default' | 'enabled' | 'disabled';
export type DeepSeekReasoningEffort = 'low' | 'high' | 'max';

export const PROVIDER_TYPE_LABELS: Record<ProviderType, string> = {
    local: 'Local',
    cloud: 'Cloud',
    custom: 'Custom',
};

export const PROVIDER_LABELS = Object.fromEntries(
    Object.values(PROVIDER_PROFILES).map(profile => [profile.id, profile.label])
) as Record<ProviderId, string>;

export const PROVIDER_TYPE_IDS: ProviderType[] = ['local', 'cloud', 'custom'];
export const LOCAL_PROVIDER_IDS = providerIdsOfType('local');
export const CLOUD_PROVIDER_IDS = providerIdsOfType('cloud');
export const CUSTOM_PROVIDER_IDS = providerIdsOfType('custom');
export const LEGACY_PROVIDER_IDS = Object.values(PROVIDER_PROFILES)
    .filter(profile => profile.selectable === false)
    .map(profile => profile.id);

export const OPEN_CODE_MODE_LABELS: Record<OpenCodeMode, string> = {
    go: 'Go',
    zen: 'Zen',
};

export const DEEPSEEK_THINKING_LABELS: Record<DeepSeekThinking, string> = {
    default: 'Default',
    enabled: 'On',
    disabled: 'Off',
};

export const DEEPSEEK_REASONING_EFFORT_LABELS: Record<DeepSeekReasoningEffort, string> = {
    low: 'Low',
    high: 'High',
    max: 'Max',
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
    return resolveProviderId(value) === value;
}

export function getProviderLabel(provider: string): string {
    return isProviderId(provider) ? PROVIDER_LABELS[provider] : provider;
}

export function getOpenCodeMode(value: string | undefined): OpenCodeMode {
    return value === 'zen' ? 'zen' : 'go';
}

export function getDeepSeekThinking(value: string | undefined): DeepSeekThinking {
    return value === 'enabled' || value === 'disabled' ? value : 'default';
}

export function getDeepSeekReasoningEffort(value: string | undefined): DeepSeekReasoningEffort {
    if (value === 'low' || value === 'max') return value;
    return 'high';
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
    return normalizeOpenCodeModelId(model);
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
    if (!currentPath || currentPath === '/') return `${origin}${modelPath}`;
    const basePath = currentPath.endsWith('/v1') ? currentPath : `${currentPath}/v1`;
    return `${origin}${basePath}${modelPath.replace('/v1', '')}`;
}

function providerIdsOfType(type: ProviderType): ProviderId[] {
    return Object.values(PROVIDER_PROFILES)
        .filter(profile => profile.type === type && profile.selectable !== false)
        .map(profile => profile.id);
}
