// Stage 0a spike: Shell-side client for the §12 IPC shape. Throwaway code.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GioUnix from 'gi://GioUnix';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const NAME = 'com.andystmc.Mei1';
const PATH = '/com/andystmc/Mei1';
const IFACE = 'com.andystmc.Mei1.Runtime';
const S = new GLib.VariantType('(s)');

function log(msg) {
    console.log(`[mei-spike ${(GLib.get_monotonic_time() / 1e6).toFixed(3)}] ${msg}`);
}

export default class MeiSpike extends Extension {
    constructor(metadata) {
        super(metadata);
        this._lastSeq = 0;
        this._epoch = null;
        this._ranBenchmarks = false;
    }

    enable() {
        log('enable');
        this._enabled = true;
        this._attached = false;
        this._buffer = [];
        this._gaps = 0;
        this._received = 0;
        this._latencies = {tick: [], burst: []};
        this._seenOwner = false;
        this._sub = Gio.DBus.session.signal_subscribe(
            NAME, IFACE, 'Event', PATH, null, Gio.DBusSignalFlags.NONE,
            (_c, _sender, _path, _iface, _sig, params) => this._onEvent(params.deepUnpack()[0]));
        this._watch = Gio.bus_watch_name(
            Gio.BusType.SESSION, NAME, Gio.BusNameWatcherFlags.NONE,
            (_c, _n, owner) => {
                this._seenOwner = true;
                log(`name-appeared owner=${owner}`);
            },
            () => this._onVanished());
        this._connect('enable');
    }

    disable() {
        log(`disable last_seq=${this._lastSeq} received=${this._received} gaps=${this._gaps}`);
        this._enabled = false;
        Gio.DBus.session.signal_unsubscribe(this._sub);
        Gio.bus_unwatch_name(this._watch);
        if (this._retry) GLib.source_remove(this._retry);
        this._retry = 0;
        this._call('Detach', {}, () => {});
    }

    _call(method, args, done) {
        Gio.DBus.session.call(NAME, PATH, IFACE, method, new GLib.Variant('(s)', [JSON.stringify(args)]),
            S, Gio.DBusCallFlags.NONE, 5000, null, (c, res) => {
                try {
                    done(JSON.parse(c.call_finish(res).deepUnpack()[0]), null);
                } catch (e) {
                    done(null, e);
                }
            });
    }

    _connect(reason) {
        const t0 = GLib.get_monotonic_time();
        this._attached = false;
        this._buffer = [];
        this._call('Hello', {client: 'spike-ext', reason}, (hello, err) => {
            if (err) {
                log(`hello-error ${err.message}`);
                return;
            }
            log(`hello-ok reason=${reason} ms=${((GLib.get_monotonic_time() - t0) / 1000).toFixed(1)} epoch=${hello.epoch.slice(0, 8)} pid=${hello.pid}`);
            if (this._epoch && this._epoch !== hello.epoch) {
                log(`epoch-changed old=${this._epoch.slice(0, 8)} -> resync from 0`);
                this._lastSeq = 0;
            }
            this._epoch = hello.epoch;
            this._call('Attach', {after_seq: this._lastSeq}, (att, err2) => {
                if (err2) {
                    log(`attach-error ${err2.message}`);
                    return;
                }
                let replayed = 0;
                for (const e of att.events) {
                    if (this._apply(JSON.parse(e))) replayed++;
                }
                const buffered = this._buffer.length;
                this._attached = true;
                for (const env of this._buffer) this._apply(env);
                this._buffer = [];
                log(`attach-ok after_seq_requested replayed=${replayed} buffered=${buffered} reset=${att.snapshot_reset} last_seq=${this._lastSeq} gaps=${this._gaps}`);
                if (!this._ranBenchmarks) {
                    this._ranBenchmarks = true;
                    this._benchmarks();
                }
            });
        });
    }

    _onEvent(json) {
        const env = JSON.parse(json);
        if (env.epoch !== this._epoch) return;
        if (!this._attached) {
            this._buffer.push(env);
            return;
        }
        this._apply(env, true);
        if (env.type === 'tick' && this._received % 20 === 0)
            log(`tick seq=${env.seq} gaps=${this._gaps}`);
    }

    _apply(env, live = false) {
        if (env.seq <= this._lastSeq) return false;
        if (env.seq !== this._lastSeq + 1) {
            this._gaps++;
            log(`GAP expected=${this._lastSeq + 1} got=${env.seq}`);
        }
        this._lastSeq = env.seq;
        this._received++;
        if (live) this._latencies[env.type]?.push((GLib.get_monotonic_time() * 1000 - env.t_ns) / 1e6);
        if (env.type === 'burst' && env.seq === this._burstEnd) {
            const ms = (GLib.get_monotonic_time() - this._burstStart) / 1000;
            log(`burst-received n=${this._burstN} ms=${ms.toFixed(1)}`);
        }
        return true;
    }

    _onVanished() {
        log(`name-vanished seen_owner=${this._seenOwner}`);
        // bus_watch_name reports 'vanished' at once when the name isn't owned yet; the Hello
        // call in _connect() activates the service, so only react after we've seen an owner.
        if (!this._seenOwner || !this._enabled || this._retry) return;
        this._vanishedAt = GLib.get_monotonic_time();
        this._retry = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
            this._retry = 0;
            if (this._enabled) this._connect('vanished');
            return GLib.SOURCE_REMOVE;
        });
    }

    _benchmarks() {
        // Ping round trips
        const n = 100;
        const rtts = [];
        const ping = i => {
            const t0 = GLib.get_monotonic_time();
            this._call('Ping', {}, () => {
                rtts.push((GLib.get_monotonic_time() - t0) / 1000);
                if (i + 1 < n) {
                    ping(i + 1);
                    return;
                }
                rtts.sort((a, b) => a - b);
                log(`ping n=${n} p50_ms=${rtts[n / 2].toFixed(2)} p99_ms=${rtts[n - 2].toFixed(2)}`);
                this._readArtifact();
            });
        };
        ping(0);
    }

    _readArtifact() {
        const t0 = GLib.get_monotonic_time();
        Gio.DBus.session.call_with_unix_fd_list(NAME, PATH, IFACE, 'ReadArtifact',
            new GLib.Variant('(s)', ['{"id":"spike"}']), new GLib.VariantType('(sh)'),
            Gio.DBusCallFlags.NONE, 5000, null, null, (c, res) => {
                try {
                    const [ret, fdList] = c.call_with_unix_fd_list_finish(res);
                    const [metaJson, idx] = ret.deepUnpack();
                    const meta = JSON.parse(metaJson);
                    const fd = fdList.get(idx);
                    const stream = new GioUnix.InputStream({fd, close_fd: true});
                    const bytes = stream.read_bytes(meta.size + 1, null);
                    stream.close(null);
                    const sha = GLib.compute_checksum_for_bytes(GLib.ChecksumType.SHA256, bytes);
                    log(`artifact size=${bytes.get_size()} sha_ok=${sha === meta.sha256} ms=${((GLib.get_monotonic_time() - t0) / 1000).toFixed(1)}`);
                } catch (e) {
                    log(`artifact-error ${e.message}`);
                }
                this._burst();
            });
    }

    _burst() {
        this._burstN = 1000;
        this._burstStart = GLib.get_monotonic_time();
        this._call('Burst', {n: this._burstN}, (r, err) => {
            if (err) {
                log(`burst-error ${err.message}`);
                return;
            }
            this._burstEnd = r.last_seq;
            if (this._lastSeq >= r.last_seq) {
                const ms = (GLib.get_monotonic_time() - this._burstStart) / 1000;
                log(`burst-received n=${this._burstN} ms=${ms.toFixed(1)} (all before reply)`);
            }
        });
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 3000, () => {
            for (const kind of ['tick', 'burst']) {
                const l = this._latencies[kind].slice().sort((a, b) => a - b);
                const p = q => l[Math.min(l.length - 1, Math.floor(q * l.length))].toFixed(2);
                if (l.length) log(`live-latency kind=${kind} n=${l.length} p50_ms=${p(0.5)} p99_ms=${p(0.99)} max_ms=${p(1)} gaps=${this._gaps}`);
            }
            return GLib.SOURCE_REMOVE;
        });
    }
}
