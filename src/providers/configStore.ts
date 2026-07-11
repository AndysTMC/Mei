/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

export type ProviderConfigKey = 'url' | 'modelName' | 'apiKey' | 'mode' | 'thinking' | 'reasoningEffort';
export type ApiKeyStorage = '' | 'secret';

export interface StoredProviderConfig {
    url: string;
    modelName: string;
    apiKey: string;
    apiKeyStorage: ApiKeyStorage;
    mode: string;
    thinking: string;
    reasoningEffort: string;
}

export type ProviderConfigs = Record<string, StoredProviderConfig>;

export const API_KEY_PLACEHOLDER = '********';

export function createEmptyProviderConfig(): StoredProviderConfig {
    return { url: '', modelName: '', apiKey: '', apiKeyStorage: '', mode: '', thinking: '', reasoningEffort: '' };
}

export function isApiKeyPlaceholder(value: string | undefined): boolean {
    return value === API_KEY_PLACEHOLDER;
}

export function isApiKeyPlaceholderLike(value: string | undefined): boolean {
    return typeof value === 'string' && /^\*{1,8}$/.test(value);
}

export function withSecretApiKeyFallback(
    config: StoredProviderConfig,
    apiKey: string
): StoredProviderConfig {
    return { ...config, apiKey, apiKeyStorage: 'secret' };
}

export function parseProviderConfigs(json: string): ProviderConfigs {
    try {
        const parsed = JSON.parse(json || '{}') as unknown;
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
            return {};
        }

        const configs: ProviderConfigs = {};
        for (const [provider, value] of Object.entries(parsed)) {
            if (typeof value !== 'object' || value === null || Array.isArray(value)) continue;
            const source = value as Record<string, unknown>;
            configs[provider] = {
                url: typeof source.url === 'string' ? source.url : '',
                modelName: typeof source.modelName === 'string' ? source.modelName : '',
                apiKey: typeof source.apiKey === 'string' ? source.apiKey : '',
                apiKeyStorage: source.apiKeyStorage === 'secret' ? 'secret' : '',
                mode: typeof source.mode === 'string' ? source.mode : '',
                thinking: typeof source.thinking === 'string' ? source.thinking : '',
                reasoningEffort: typeof source.reasoningEffort === 'string' ? source.reasoningEffort : '',
            };
        }
        return configs;
    } catch {
        return {};
    }
}

export function mergeMigratedApiKeyConfigs(
    original: ProviderConfigs,
    migrated: ProviderConfigs,
    current: ProviderConfigs
): ProviderConfigs {
    const merged = { ...current };
    for (const [provider, before] of Object.entries(original)) {
        const after = migrated[provider];
        const latest = current[provider];
        if (!after || !latest) continue;
        if (before.apiKey === after.apiKey && before.apiKeyStorage === after.apiKeyStorage) continue;
        if (latest.apiKey !== before.apiKey || latest.apiKeyStorage !== before.apiKeyStorage) continue;

        merged[provider] = {
            ...latest,
            apiKey: after.apiKey,
            apiKeyStorage: after.apiKeyStorage,
        };
    }
    return merged;
}
