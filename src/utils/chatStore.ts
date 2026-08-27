/**
 * Persistent chat session storage.
 *
 * Saves/loads chat sessions as JSON in the standard XDG data directory
 * (~/.local/share/mei/chats.json).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';

import type { ChatMessage } from '../providers/types.js';
import { generateChatId, generateChatTitle, MAX_CHAT_SESSIONS, parseChatSessions, type ChatSession } from './chatSession.js';
import { Logger, Tag } from './logger.js';

export type { ChatSession } from './chatSession.js';

const MAX_CHAT_STORE_BYTES = 16 * 1024 * 1024;

export class ChatStore {
    private _filePath: string;
    private _sessions: ChatSession[] = [];
    private _saveChain: Promise<void> = Promise.resolve();

    constructor() {
        const dataDir = GLib.get_user_data_dir();
        const dir = GLib.build_filenamev([dataDir, 'mei']);
        GLib.mkdir_with_parents(dir, 0o700);
        setPrivateMode(dir, 0o700);
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
            const info = file.query_info(
                Gio.FILE_ATTRIBUTE_STANDARD_SIZE,
                Gio.FileQueryInfoFlags.NONE,
                null
            );
            if (info.get_size() > MAX_CHAT_STORE_BYTES) {
                throw new Error('Chat history exceeds the 16 MiB safety limit');
            }
            const [ok, contents] = file.load_contents(null);
            if (ok && contents) {
                const decoder = new TextDecoder();
                const raw = JSON.parse(decoder.decode(contents)) as unknown;
                if (!Array.isArray(raw)) throw new Error('Chat history root was not an array');
                this._sessions = parseChatSessions(raw);
                if (this._sessions.length !== raw.length) {
                    Logger.warn(Tag.Extension, 'Chat history contained invalid, duplicate, or excess sessions');
                    this._quarantine(file);
                }
            }
        } catch (e) {
            Logger.warn(Tag.Extension, `Failed to load chat history: ${e}`);
            this._quarantine(Gio.File.new_for_path(this._filePath));
            this._sessions = [];
        }
    }

    private _quarantine(file: Gio.File): void {
        try {
            if (!file.query_exists(null)) return;
            const quarantinePath = `${this._filePath}.corrupt-${Date.now()}`;
            const quarantine = Gio.File.new_for_path(quarantinePath);
            file.move(quarantine, Gio.FileCopyFlags.NOFOLLOW_SYMLINKS, null, null);
            setPrivateMode(quarantinePath, 0o600);
            Logger.warn(Tag.Extension, `Preserved unreadable chat history at ${quarantinePath}`);
        } catch (e) {
            Logger.warn(Tag.Extension, `Failed to preserve unreadable chat history: ${e}`);
        }
    }

    private _save(): void {
        try {
            const json = JSON.stringify(this._sessions);
            const file = Gio.File.new_for_path(this._filePath);
            const bytes = new TextEncoder().encode(json);
            if (bytes.length > MAX_CHAT_STORE_BYTES) {
                Logger.error(Tag.Extension, 'Chat history was not saved because it exceeds the 16 MiB safety limit');
                return;
            }

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
        if (parseChatSessions([session]).length !== 1) {
            Logger.error(Tag.Extension, 'Chat history was not saved because the session is invalid or too large');
            return;
        }
        const index = this._sessions.findIndex(s => s.id === session.id);
        if (index >= 0) {
            this._sessions[index] = session;
        } else {
            if (this._sessions.length >= MAX_CHAT_SESSIONS) {
                Logger.error(Tag.Extension, `Chat history was not saved because it reached the ${MAX_CHAT_SESSIONS}-session limit`);
                return;
            }
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

    flush(): Promise<void> {
        return this._saveChain;
    }

    getChat(id: string): ChatSession | null {
        return this._sessions.find(s => s.id === id) ?? null;
    }

    static generateId(): string {
        return generateChatId();
    }

    static generateTitle(messages: ChatMessage[]): string {
        return generateChatTitle(messages);
    }
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
                    setPrivateMode(file.get_path(), 0o600);
                    resolve();
                } catch (e) {
                    reject(e);
                }
            }
        );
    });
}

function setPrivateMode(path: string | null, mode: number): void {
    if (!path) return;
    try {
        Gio.File.new_for_path(path).set_attribute_uint32(
            Gio.FILE_ATTRIBUTE_UNIX_MODE,
            mode,
            Gio.FileQueryInfoFlags.NONE,
            null
        );
    } catch (e) {
        Logger.warn(Tag.Extension, `Failed to set private permissions on ${path}: ${e}`);
    }
}
