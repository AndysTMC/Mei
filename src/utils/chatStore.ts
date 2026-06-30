/**
 * Persistent chat session storage.
 *
 * Saves/loads chat sessions as JSON in the standard XDG data directory
 * (~/.local/share/mei/chats.json).
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';

import type { ChatMessage } from '../providers/types.js';
import { Logger, Tag } from './logger.js';

export interface ChatSession {
    id: string;
    title: string;
    messages: ChatMessage[];
    createdAt: number;
    updatedAt: number;
}

export class ChatStore {
    private _filePath: string;
    private _sessions: ChatSession[] = [];
    private _saveChain: Promise<void> = Promise.resolve();

    constructor() {
        const dataDir = GLib.get_user_data_dir();
        const dir = GLib.build_filenamev([dataDir, 'mei']);
        GLib.mkdir_with_parents(dir, 0o755);
        this._filePath = GLib.build_filenamev([dir, 'chats.json']);
        this._load();
    }

    private _load(): void {
        try {
            const file = Gio.File.new_for_path(this._filePath);
            if (!file.query_exists(null)) {
                this._sessions = [];
                return;
            }
            const [ok, contents] = file.load_contents(null);
            if (ok && contents) {
                const decoder = new TextDecoder();
                this._sessions = parseChatSessions(JSON.parse(decoder.decode(contents)));
            }
        } catch (e) {
            Logger.warn(Tag.Extension, `Failed to load chat history: ${e}`);
            this._sessions = [];
        }
    }

    private _save(): void {
        try {
            const json = JSON.stringify(this._sessions);
            const file = Gio.File.new_for_path(this._filePath);
            const bytes = new TextEncoder().encode(json);

            this._saveChain = this._saveChain
                .then(() => replaceFileContentsAsync(file, bytes))
                .catch(err => {
                    Logger.error(Tag.Extension, 'Failed to save chat history', err);
                });
        } catch (e) {
            Logger.error(Tag.Extension, 'Failed to serialize chat history', e);
        }
    }

    saveChat(session: ChatSession): void {
        const index = this._sessions.findIndex(s => s.id === session.id);
        if (index >= 0) {
            this._sessions[index] = session;
        } else {
            this._sessions.unshift(session);
        }
        this._save();
    }

    loadChats(): ChatSession[] {
        return [...this._sessions].sort((a, b) => b.updatedAt - a.updatedAt);
    }

    deleteChat(id: string): void {
        this._sessions = this._sessions.filter(s => s.id !== id);
        this._save();
    }

    getChat(id: string): ChatSession | null {
        return this._sessions.find(s => s.id === id) ?? null;
    }

    static generateId(): string {
        return `${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 8)}`;
    }

    static generateTitle(messages: ChatMessage[]): string {
        const firstUser = messages.find(m => m.role === 'user');
        if (!firstUser) return 'New Chat';
        const text = firstUser.content.trim();
        return text.length > 40 ? `${text.substring(0, 40)}…` : text;
    }
}

function parseChatSessions(value: unknown): ChatSession[] {
    if (!Array.isArray(value)) return [];

    return value.filter((session): session is ChatSession => {
        if (typeof session !== 'object' || session === null) return false;
        const candidate = session as Record<string, unknown>;
        return typeof candidate.id === 'string' &&
            typeof candidate.title === 'string' &&
            Array.isArray(candidate.messages) &&
            candidate.messages.every(isChatMessage) &&
            typeof candidate.createdAt === 'number' &&
            typeof candidate.updatedAt === 'number';
    });
}

function isChatMessage(value: unknown): value is ChatMessage {
    if (typeof value !== 'object' || value === null) return false;
    const candidate = value as Record<string, unknown>;
    return (candidate.role === 'user' ||
        candidate.role === 'assistant' ||
        candidate.role === 'system') &&
        typeof candidate.content === 'string' &&
        (candidate.thinking === undefined || typeof candidate.thinking === 'string') &&
        (candidate.metadata === undefined || isChatMetadata(candidate.metadata));
}

function isChatMetadata(value: unknown): boolean {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const metadata = value as Record<string, unknown>;
    return (metadata.providerId === undefined || typeof metadata.providerId === 'string') &&
        (metadata.providerLabel === undefined || typeof metadata.providerLabel === 'string') &&
        (metadata.providerType === undefined || typeof metadata.providerType === 'string') &&
        (metadata.model === undefined || typeof metadata.model === 'string') &&
        (metadata.endpoint === undefined || typeof metadata.endpoint === 'string') &&
        (metadata.durationMs === undefined || typeof metadata.durationMs === 'number') &&
        (metadata.tokens === undefined || isTokenUsage(metadata.tokens));
}

function isTokenUsage(value: unknown): boolean {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const tokens = value as Record<string, unknown>;
    return (tokens.inputTokens === undefined || typeof tokens.inputTokens === 'number') &&
        (tokens.outputTokens === undefined || typeof tokens.outputTokens === 'number') &&
        (tokens.totalTokens === undefined || typeof tokens.totalTokens === 'number');
}

function replaceFileContentsAsync(file: Gio.File, bytes: Uint8Array): Promise<void> {
    return new Promise((resolve, reject) => {
        file.replace_contents_async(
            bytes,
            null,
            false,
            Gio.FileCreateFlags.REPLACE_DESTINATION,
            null,
            (source, result) => {
                try {
                    const sourceFile = source ?? file;
                    sourceFile.replace_contents_finish(result);
                    resolve();
                } catch (e) {
                    reject(e);
                }
            }
        );
    });
}
