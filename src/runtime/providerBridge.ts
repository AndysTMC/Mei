/**
 * Stage 1 bridge: describe the extension's selected provider to the runtime. Only non-secret
 * fields cross the bus; the runtime reads the API key from the keyring by provider id (§13.8).
 * Stage 2a moves provider settings into the runtime and removes this.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { getProviderProfile, normalizeOpenCodeModelId, resolveProviderRuntime } from '../providers/profiles.js';
import type { ProviderId } from '../providers/types.js';
import type { RuntimeProviderConfig } from './protocol.js';

export interface StoredProviderFields {
    url?: string;
    modelName?: string;
    mode?: string;
}

export interface BridgeResult {
    config: RuntimeProviderConfig;
    /** Set when the runtime can't serve this provider yet; shown to the user. */
    unsupported?: string;
}

const NONE: RuntimeProviderConfig = { kind: 'none', id: '', label: '', url: '', model: '', headers: {}, options: {} };

export function toRuntimeProvider(providerId: ProviderId, stored: StoredProviderFields): BridgeResult {
    const profile = getProviderProfile(providerId);
    const runtime = resolveProviderRuntime(providerId, {
        url: stored.url ?? '',
        model: stored.modelName ?? '',
        mode: stored.mode ?? '',
    });
    const openaiCompatible = profile.transport === 'openai' || profile.transport === 'llamacpp';
    if (!profile.selectable || !openaiCompatible || runtime.apiMode !== 'chat_completions') {
        return {
            config: NONE,
            unsupported: `${profile.label} isn't supported by the Mei runtime yet. ` +
                'This build serves OpenAI-compatible chat providers only.',
        };
    }
    const model = providerId === 'opencode' ? normalizeOpenCodeModelId(stored.modelName ?? '') : (stored.modelName ?? '').trim();
    if (!model) return { config: NONE, unsupported: `Choose a ${profile.label} model in Mei's settings first.` };
    return {
        config: {
            kind: 'openai_chat',
            id: providerId,
            label: profile.label,
            url: runtime.url,
            model,
            headers: { ...(profile.headers ?? {}) },
            options: {},
        },
    };
}
