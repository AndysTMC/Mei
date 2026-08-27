/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

const SENSITIVE_FIELD = '(?:api[_-]?key|access[_-]?token|auth[_-]?token|authorization|proxy-authorization|x-api-key|token|key)';

export function redactSensitiveText(text: string): string {
    return text
        .replace(/\b(https?:\/\/)[^/?#\s@]+@/gi, '$1***@')
        .replace(new RegExp(`([?&]${SENSITIVE_FIELD}=)[^&#\\s]+`, 'gi'), '$1***')
        .replace(new RegExp(`("${SENSITIVE_FIELD}"\\s*:\\s*")[^"]*(")`, 'gi'), '$1***$2')
        .replace(new RegExp(`((?<![?&])\\b${SENSITIVE_FIELD}\\b\\s*[:=]\\s*)(?:bearer\\s+|basic\\s+)?[^\\s,;"']+`, 'gi'), '$1***')
        .replace(/\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+/gi, '$1 ***');
}
