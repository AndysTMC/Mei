/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { Logger, Tag } from './logger.js';

type SecretNamespace = {
    Schema: {
        ['new'](name: string, flags: number, attributes: Record<string, number>): unknown;
    };
    SchemaFlags: {
        NONE: number;
    };
    SchemaAttributeType: {
        STRING: number;
    };
    COLLECTION_DEFAULT: string;
    password_lookup(schema: unknown, attributes: Record<string, string>, cancellable: null, callback: (source: unknown, result: unknown) => void): void;
    password_lookup_finish(result: unknown): string | null;
    password_store(schema: unknown, attributes: Record<string, string>, collection: string, label: string, password: string, cancellable: null, callback: (source: unknown, result: unknown) => void): void;
    password_store_finish(result: unknown): boolean;
    password_clear(schema: unknown, attributes: Record<string, string>, cancellable: null, callback: (source: unknown, result: unknown) => void): void;
    password_clear_finish(result: unknown): boolean;
};

const SCHEMA_NAME = 'com.andystmc.mei.provider-api-key';
const EXTENSION_ID = 'mei@andystmc.com';
const SECRET_IMPORT = 'gi://Secret?version=1';

let secretModulePromise: Promise<SecretNamespace | null> | null = null;
let schema: unknown | null = null;

export async function lookupProviderApiKey(provider: string): Promise<string | null> {
    const Secret = await getSecretModule();
    if (!Secret) return null;

    return new Promise((resolve, reject) => {
        Secret.password_lookup(getSchema(Secret), getAttributes(provider), null, (_source, result) => {
            try {
                resolve(Secret.password_lookup_finish(result));
            } catch (e) {
                reject(e);
            }
        });
    });
}

export async function storeProviderApiKey(provider: string, apiKey: string): Promise<boolean> {
    const Secret = await getSecretModule();
    if (!Secret) return false;

    return new Promise((resolve, reject) => {
        Secret.password_store(
            getSchema(Secret),
            getAttributes(provider),
            Secret.COLLECTION_DEFAULT,
            `Mei ${provider} API key`,
            apiKey,
            null,
            (_source, result) => {
                try {
                    resolve(Boolean(Secret.password_store_finish(result)));
                } catch (e) {
                    reject(e);
                }
            }
        );
    });
}

export async function clearProviderApiKey(provider: string): Promise<boolean> {
    const Secret = await getSecretModule();
    if (!Secret) return false;

    return new Promise((resolve, reject) => {
        Secret.password_clear(getSchema(Secret), getAttributes(provider), null, (_source, result) => {
            try {
                resolve(Boolean(Secret.password_clear_finish(result)));
            } catch (e) {
                reject(e);
            }
        });
    });
}

async function getSecretModule(): Promise<SecretNamespace | null> {
    if (!secretModulePromise) {
        secretModulePromise = import(SECRET_IMPORT)
            .then(module => {
                const Secret = (module.default ?? module) as SecretNamespace;
                Logger.info(Tag.Extension, 'libsecret API key storage is available');
                return Secret;
            })
            .catch(e => {
                Logger.warn(Tag.Extension, `libsecret API key storage unavailable; falling back to GSettings: ${e}`);
                return null;
            });
    }

    return secretModulePromise;
}

function getSchema(Secret: SecretNamespace): unknown {
    if (!schema) {
        schema = Secret.Schema['new'](SCHEMA_NAME, Secret.SchemaFlags.NONE, {
            extension: Secret.SchemaAttributeType.STRING,
            provider: Secret.SchemaAttributeType.STRING,
        });
    }
    return schema;
}

function getAttributes(provider: string): Record<string, string> {
    return {
        extension: EXTENSION_ID,
        provider,
    };
}
