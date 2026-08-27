/**
 * Runtime provider construction from declarative profiles.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';

import { AnthropicProvider } from './anthropic.js';
import { GeminiProvider } from './gemini.js';
import { LlamaCppProvider } from './llamacpp.js';
import { OllamaProvider } from './ollama.js';
import {
    DeepSeekProvider,
    FireworksProvider,
    GitHubCopilotProvider,
    NvidiaProvider,
    OpenAICompatibleProvider,
} from './openai.js';
import {
    getProviderProfile,
    normalizeOpenCodeModelId,
    resolveProviderRuntime,
} from './profiles.js';
import { ResponsesProvider } from './responses.js';
import type { Provider, ProviderConfig, ProviderId } from './types.js';

export { resolveProviderRuntime } from './profiles.js';

export function createRuntimeProvider(
    session: Soup.Session,
    providerId: ProviderId,
    config: ProviderConfig
): Provider {
    const profile = getProviderProfile(providerId);
    const runtime = resolveProviderRuntime(providerId, config);
    const effectiveConfig = {
        ...config,
        url: runtime.url,
        model: providerId === 'opencode' ? normalizeOpenCodeModelId(config.model) : config.model,
    };

    if (runtime.apiMode === 'bedrock_converse') {
        throw new Error(`${profile.label} requires AWS SDK authentication, which is not configured in Mei.`);
    }
    if (runtime.apiMode === 'responses') {
        return new ResponsesProvider(
            session,
            effectiveConfig.model,
            config.apiKey ?? '',
            profile.label,
            runtime.url,
            profile.headers
        );
    }
    if (runtime.apiMode === 'anthropic_messages') {
        return new AnthropicProvider(
            session,
            effectiveConfig,
            profile.label,
            runtime.url,
            providerId !== 'anthropic',
            profile.headers
        );
    }

    if (providerId === 'deepseek') return new DeepSeekProvider(session, effectiveConfig);
    if (providerId === 'fireworks') return new FireworksProvider(session, effectiveConfig);
    if (providerId === 'nvidia') return new NvidiaProvider(session, effectiveConfig);
    if (providerId === 'githubcopilot') return new GitHubCopilotProvider(session, effectiveConfig);

    switch (profile.transport) {
        case 'ollama':
            return new OllamaProvider(session, effectiveConfig);
        case 'llamacpp':
            return new LlamaCppProvider(session, effectiveConfig);
        case 'gemini':
            return new GeminiProvider(session, effectiveConfig);
        case 'anthropic':
            return new AnthropicProvider(session, effectiveConfig);
        case 'openai':
            return new OpenAICompatibleProvider(
                session,
                effectiveConfig,
                profile.label,
                runtime.url,
                profile.headers
            );
    }
}
