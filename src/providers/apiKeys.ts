/**
 * Provider API keys live only in the keyring (ADR 0005, superseding ADR 0001). The runtime reads
 * them there by provider id; nothing in settings ever holds a key.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { isApiKeyPlaceholderLike, type StoredProviderConfig } from './configStore.js';
import { clearProviderApiKey, lookupProviderApiKey, storeProviderApiKey } from '../utils/secretStore.js';
import { Logger, Tag } from '../utils/logger.js';

/** Fill in the stored key (for showing "a key is saved"), without writing it anywhere. */
export async function resolveStoredProviderConfig(
    provider: string,
    config: StoredProviderConfig
): Promise<StoredProviderConfig> {
    try {
        const apiKey = await lookupProviderApiKey(provider);
        return { ...config, apiKey: apiKey ?? '', apiKeyStorage: apiKey ? 'secret' : '' };
    } catch (e) {
        Logger.warn(Tag.Extension, `Failed to read ${provider} API key from keyring: ${e}`);
        return { ...config, apiKey: '', apiKeyStorage: '' };
    }
}

/** Save or clear a key in the keyring. Throws if the keyring can't take it; there is no fallback. */
export async function updateStoredProviderApiKey(
    provider: string,
    config: StoredProviderConfig,
    apiKey: string
): Promise<StoredProviderConfig> {
    const trimmedKey = apiKey.trim();
    if (isApiKeyPlaceholderLike(trimmedKey)) return config;
    if (!trimmedKey) {
        await clearProviderApiKey(provider);
        return { ...config, apiKey: '', apiKeyStorage: '' };
    }
    if (!await storeProviderApiKey(provider, trimmedKey)) {
        throw new Error('The keyring is unavailable or locked, so the key was not saved.');
    }
    return { ...config, apiKey: '', apiKeyStorage: 'secret' };
}
