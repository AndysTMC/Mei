/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import {
    createEmptyProviderConfig,
    isApiKeyPlaceholderLike,
    withSecretApiKeyFallback,
    type ProviderConfigs,
    type StoredProviderConfig,
} from './configStore.js';
import { clearProviderApiKey, lookupProviderApiKey, storeProviderApiKey } from '../utils/secretStore.js';
import { Logger, Tag } from '../utils/logger.js';

export async function resolveStoredProviderConfig(
    provider: string,
    config: StoredProviderConfig
): Promise<StoredProviderConfig> {
    if (config.apiKeyStorage !== 'secret' && config.apiKey && !isApiKeyPlaceholderLike(config.apiKey)) {
        return config;
    }

    try {
        const apiKey = await lookupProviderApiKey(provider);
        if (apiKey) return { ...config, apiKey };
        return isApiKeyPlaceholderLike(config.apiKey) ? { ...config, apiKey: '' } : config;
    } catch (e) {
        Logger.warn(Tag.Extension, `Failed to read ${provider} API key from keyring: ${e}`);
        return isApiKeyPlaceholderLike(config.apiKey) ? { ...config, apiKey: '' } : config;
    }
}

export async function updateStoredProviderApiKey(
    provider: string,
    config: StoredProviderConfig,
    apiKey: string
): Promise<StoredProviderConfig> {
    const trimmedKey = apiKey.trim();
    if (isApiKeyPlaceholderLike(trimmedKey)) {
        return config;
    }
    if (!trimmedKey) {
        try {
            await clearProviderApiKey(provider);
        } catch (e) {
            Logger.warn(Tag.Extension, `Failed to clear ${provider} API key from keyring: ${e}`);
        }
        return { ...config, apiKey: '', apiKeyStorage: '' };
    }

    try {
        if (await storeProviderApiKey(provider, trimmedKey)) {
            // Keep a GSettings fallback. Secret Service can be available while
            // saving and unavailable after a Shell restart; without this copy,
            // every cloud provider is recreated with an empty credential.
            return withSecretApiKeyFallback(config, trimmedKey);
        }
    } catch (e) {
        Logger.warn(Tag.Extension, `Failed to store ${provider} API key in keyring: ${e}`);
    }

    Logger.warn(Tag.Extension, `Falling back to plaintext GSettings storage for ${provider} API key`);
    return { ...config, apiKey: trimmedKey, apiKeyStorage: '' };
}

export async function migratePlaintextApiKeys(configs: ProviderConfigs): Promise<{ configs: ProviderConfigs; changed: boolean }> {
    let changed = false;
    const migrated: ProviderConfigs = {};

    for (const [provider, rawConfig] of Object.entries(configs)) {
        const config = { ...createEmptyProviderConfig(), ...rawConfig };
        if (!config.apiKey || config.apiKeyStorage === 'secret') {
            migrated[provider] = config;
            continue;
        }

        try {
            if (await storeProviderApiKey(provider, config.apiKey)) {
                migrated[provider] = withSecretApiKeyFallback(config, config.apiKey);
                changed = true;
                continue;
            }
        } catch (e) {
            Logger.warn(Tag.Extension, `Failed to migrate ${provider} API key to keyring: ${e}`);
        }

        migrated[provider] = config;
    }

    return { configs: migrated, changed };
}
