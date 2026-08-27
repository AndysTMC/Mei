/**
 * Headers for OpenAI-compatible provider profiles.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

export function buildBearerHeaders(apiKey: string): Record<string, string> {
    return apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
}

export function buildFireworksHeaders(apiKey: string): Record<string, string> {
    return {
        ...buildBearerHeaders(apiKey),
        'HTTP-Referer': 'https://github.com/AndysTMC/Mei',
        'X-Title': 'Mei',
    };
}

export function buildNvidiaHeaders(apiKey: string): Record<string, string> {
    return {
        ...buildBearerHeaders(apiKey),
        'X-BILLING-INVOKE-ORIGIN': 'Mei',
    };
}
