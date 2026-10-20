/**
 * Stage 2a bridge: hand the extension's provider preferences to the runtime, which owns the
 * provider profiles and resolves endpoints itself. Only non-secret fields cross the bus; the
 * runtime reads the API key from the keyring by provider id (§13.8). Removed once settings live
 * in the runtime.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { getProviderProfile } from '../providers/profiles.js';
import type { ProviderId } from '../providers/types.js';
import type { RuntimeProviderConfig } from './protocol.js';

export interface StoredProviderFields {
    url?: string;
    modelName?: string;
    mode?: string;
    thinking?: string;
    reasoningEffort?: string;
}

export interface BridgeResult {
    config: RuntimeProviderConfig;
    /** Set when the runtime can't serve this provider; shown to the user. */
    unsupported?: string;
}

const NONE: RuntimeProviderConfig = { id: '', model: '', url: '', mode: '', thinking: '', reasoning_effort: '', options: {} };

export function toRuntimeProvider(providerId: ProviderId, stored: StoredProviderFields): BridgeResult {
    const profile = getProviderProfile(providerId);
    if (!profile.selectable) {
        return { config: NONE, unsupported: `${profile.label} is no longer available. Choose another provider in Mei's settings.` };
    }
    const model = (stored.modelName ?? '').trim();
    if (!model) return { config: NONE, unsupported: `Choose a ${profile.label} model in Mei's settings first.` };
    return {
        config: {
            id: providerId,
            model,
            url: (stored.url ?? '').trim(),
            mode: stored.mode ?? '',
            thinking: stored.thinking ?? '',
            reasoning_effort: stored.reasoningEffort ?? '',
            options: {},
        },
    };
}

export function sameProvider(a: RuntimeProviderConfig, b: RuntimeProviderConfig): boolean {
    return a.id === b.id && a.model === b.model && a.url === b.url && a.mode === b.mode &&
        a.thinking === b.thinking && a.reasoning_effort === b.reasoning_effort &&
        JSON.stringify(a.options ?? {}) === JSON.stringify(b.options ?? {});
}
