/**
 * Shell-side connection to the Mei runtime over the session bus (ADR 0003).
 *
 * The first call D-Bus-activates the runtime. `Attach(after_seq)` resumes from the projection's
 * cursor; events that arrive while attaching are buffered and handed over after the reply, and
 * the projection drops anything it already has. When the runtime goes away we re-attach, which
 * also restarts it.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import { Logger, Tag } from '../utils/logger.js';
import {
    BUS_NAME,
    ERROR_PREFIX,
    INTERFACE,
    OBJECT_PATH,
    PROTOCOL_VERSION,
    type AttachReply,
    type Envelope,
    type HelloReply,
} from './protocol.js';

const CALL_TIMEOUT_MS = 10_000;

export interface CallOptions {
    flags?: Gio.DBusCallFlags;
    /** For methods that wait on the network or the user (TestProvider, unlocking the keyring). */
    timeoutMs?: number;
}
const RECONNECT_FAST_MS = 300;
const RECONNECT_SLOW_MS = 5_000;
const KNOWN_EVENTS = new Set([
    'conversation.created', 'conversation.deleted', 'message.completed', 'task.accepted',
    'task.state_changed', 'model.started', 'task.finished', 'config.changed', 'message.delta', 'runtime.notice',
    // 2.2
    'plan.updated', 'action.proposed', 'policy.decided', 'action.started', 'action.updated', 'action.finished',
    'approval.requested', 'approval.resolved', 'input.requested', 'input.answered', 'grant.created', 'grant.revoked',
    // 2.3
    'memory.saved', 'memory.pending_review', 'memory.updated', 'memory.deleted',
    // 2.4 (ephemeral)
    'voice.state', 'voice.partial', 'voice.reading', 'voice.level',
]);

export type ConnectionStatus = 'connecting' | 'connected' | 'unavailable' | 'incompatible';

export class RuntimeError extends Error {
    constructor(readonly code: string, message: string) {
        super(message);
    }
}

export class RuntimeClient {
    onEvent: ((event: Envelope) => void) | null = null;
    onAttached: ((reply: AttachReply, hello: HelloReply) => void) | null = null;
    onStatus: ((status: ConnectionStatus, detail?: string) => void) | null = null;

    private _subscription = 0;
    private _watch = 0;
    private _seenOwner = false;
    private _retryId = 0;
    private _attaching = false;
    private _buffer: Envelope[] = [];
    private _generation = 0;
    private _destroyed = false;
    private _owner: string | null = null;

    /** `_bridge`: the Shell bridge's object path, offered in Hello; empty for clients without one. */
    constructor(private readonly _cursor: () => number, private readonly _bridge = '') {}

    /** The runtime's current unique bus name, while it is running. */
    get owner(): string | null {
        return this._owner;
    }

    start(): void {
        this._subscription = Gio.DBus.session.signal_subscribe(
            BUS_NAME, INTERFACE, 'Event', OBJECT_PATH, null, Gio.DBusSignalFlags.NONE,
            (_conn, _sender, _path, _iface, _signal, params) => this._onSignal(params));
        this._watch = Gio.bus_watch_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameWatcherFlags.NONE,
            (_conn, _name, owner) => {
                this._seenOwner = true;
                this._owner = owner;
            },
            () => {
                this._owner = null;
                this._onVanished();
            });
        void this._connect();
    }

    destroy(): void {
        this._destroyed = true;
        this._generation++;
        if (this._subscription) Gio.DBus.session.signal_unsubscribe(this._subscription);
        if (this._watch) Gio.bus_unwatch_name(this._watch);
        if (this._retryId) GLib.source_remove(this._retryId);
        this._subscription = this._watch = this._retryId = 0;
        this._buffer = [];
        // Tell the runtime to stop sending us events; never start it just to say goodbye. If it
        // isn't running there is nothing to detach from, so a failure only matters for debugging.
        this.call('Detach', {}, { flags: Gio.DBusCallFlags.NO_AUTO_START })
            .catch(e => Logger.debug(Tag.Extension, `Detach: ${(e as Error).message}`));
    }

    /** Re-attach from the current cursor, e.g. after the projection saw a gap. */
    reattach(): void {
        void this._connect();
    }

    call<T>(method: string, args: object = {}, opts: CallOptions = {}): Promise<T> {
        return new Promise((resolve, reject) => {
            Gio.DBus.session.call(
                BUS_NAME, OBJECT_PATH, INTERFACE, method, new GLib.Variant('(s)', [JSON.stringify(args)]),
                new GLib.VariantType('(s)'), opts.flags ?? Gio.DBusCallFlags.NONE, opts.timeoutMs ?? CALL_TIMEOUT_MS, null,
                (conn, res) => {
                    // Turned off meanwhile (the extension disabled): the answer is dropped, so nothing
                    // waiting on it touches a popup that is gone.
                    if (this._destroyed) return;
                    try {
                        const reply = conn!.call_finish(res).deepUnpack() as [string];
                        resolve(JSON.parse(reply[0]) as T);
                    } catch (e) {
                        reject(toRuntimeError(e));
                    }
                });
        });
    }

    private async _connect(): Promise<void> {
        if (this._destroyed) return;
        const generation = ++this._generation;
        this._attaching = true;
        this._buffer = [];
        this.onStatus?.('connecting');
        try {
            const hello = await this.call<HelloReply>('Hello', {
                client: { kind: 'shell', version: '1' },
                protocol: PROTOCOL_VERSION,
                ...(this._bridge ? { bridge: this._bridge } : {}),
            });
            if (generation !== this._generation) return;
            const reply = await this.call<AttachReply>('Attach', { scope: 'all', after_seq: this._cursor() });
            if (generation !== this._generation) return;
            this._attaching = false;
            this.onAttached?.(reply, hello);
            const buffered = this._buffer;
            this._buffer = [];
            for (const event of buffered) this.onEvent?.(event);
            this.onStatus?.('connected');
        } catch (e) {
            if (generation !== this._generation) return;
            this._attaching = false;
            const err = e as RuntimeError;
            if (err.code === 'Unsupported') {
                this.onStatus?.('incompatible', err.message);
            } else if (err.code === 'ServiceUnknown') {
                this.onStatus?.('unavailable', "The Mei runtime isn't installed for this user.");
                this._scheduleReconnect(RECONNECT_SLOW_MS);
            } else {
                Logger.warn(Tag.Extension, `Runtime connection failed: ${err.message}`);
                this.onStatus?.('unavailable', err.message);
                this._scheduleReconnect(RECONNECT_SLOW_MS);
            }
        }
    }

    private _onSignal(params: GLib.Variant): void {
        let event: Envelope;
        try {
            event = JSON.parse((params.deepUnpack() as [string])[0]) as Envelope;
        } catch (e) {
            Logger.warn(Tag.Extension, `Ignoring malformed runtime event: ${e}`);
            return;
        }
        if (!KNOWN_EVENTS.has(event.type) && event.required) {
            this.onStatus?.('incompatible', `Unknown required event ${event.type}; update Mei.`);
            return;
        }
        // Any other event a newer runtime sends goes on: the projection skips it but counts its seq, so
        // the next one isn't taken for a gap (which used to cost a re-attach each time).
        if (this._attaching) {
            this._buffer.push(event);
            return;
        }
        this.onEvent?.(event);
    }

    private _onVanished(): void {
        // bus_watch_name reports "vanished" at once if the runtime isn't running yet; the Hello call
        // starts it. Only a name we've seen owned and then lost means the runtime went away.
        if (!this._seenOwner || this._destroyed) return;
        this._seenOwner = false;
        this.onStatus?.('connecting');
        this._scheduleReconnect(RECONNECT_FAST_MS);
    }

    private _scheduleReconnect(delayMs: number): void {
        if (this._retryId || this._destroyed) return;
        this._retryId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delayMs, () => {
            this._retryId = 0;
            void this._connect();
            return GLib.SOURCE_REMOVE;
        });
    }
}

function toRuntimeError(error: unknown): RuntimeError {
    if (error instanceof GLib.Error) {
        const remote = Gio.DBusError.get_remote_error(error);
        Gio.DBusError.strip_remote_error(error);
        if (remote?.startsWith(ERROR_PREFIX)) return new RuntimeError(remote.slice(ERROR_PREFIX.length), error.message);
        if (remote === 'org.freedesktop.DBus.Error.ServiceUnknown') return new RuntimeError('ServiceUnknown', error.message);
        return new RuntimeError(remote ?? 'Transport', error.message);
    }
    return new RuntimeError('Unknown', error instanceof Error ? error.message : String(error));
}
