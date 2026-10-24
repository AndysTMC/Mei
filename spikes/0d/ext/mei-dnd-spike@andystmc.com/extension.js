// Spike 0d: what a Shell extension sees of a Wayland drag, and whether a window it owns can take
// the drop. Throwaway: a panel button standing in for Mei's, a drop window it can show over it,
// a virtual pointer to drag with, and a log of what happened with CLOCK_MONOTONIC times (ms).

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';
import * as DND from 'resource:///org/gnome/shell/ui/dnd.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const XML = `
<node>
  <interface name="com.andystmc.MeiDndSpike">
    <method name="SetMode"><arg type="s" direction="in" name="mode"/></method>
    <method name="Targets"><arg type="s" direction="out" name="json"/></method>
    <method name="Drag"><arg type="s" direction="in" name="json"/></method>
    <method name="Log"><arg type="s" direction="out" name="json"/></method>
    <method name="Reset"/>
  </interface>
</node>`;

const now = () => GLib.get_monotonic_time() / 1000;

function rectOf(actor) {
    const [x, y] = actor.get_transformed_position();
    const [w, h] = actor.get_transformed_size();
    return { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
}

const inside = (r, x, y, pad = 0) => x >= r.x - pad && x < r.x + r.w + pad && y >= r.y - pad && y < r.y + r.h + pad;

export default class DndSpike extends Extension {
    enable() {
        this._log = [];
        this._mode = { win: false, layer: 'none', passthrough: false, prewarm: false, popup: false, popupDrop: false };
        this._client = null;
        this._stdin = null;
        this._shownAt = null;
        this._overSince = 0;
        this._dragging = false;

        const seat = Clutter.get_default_backend().get_default_seat();
        this._pointer = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);

        this._button = new PanelMenu.Button(0.5, 'Spike', false);
        this._button.add_child(new St.Icon({ icon_name: 'edit-paste-symbolic', style_class: 'system-status-icon' }));
        this._button._delegate = this._button;
        this._button.handleDragOver = (source, _actor, x, y) => {
            this._note('button-drag-over', { xdnd: source === Main.xdndHandler, x: Math.round(x), y: Math.round(y) });
            return DND.DragMotionResult.CONTINUE;
        };
        this._button.acceptDrop = () => {
            this._note('button-accept-drop');
            return true;
        };
        const item = new PopupMenu.PopupBaseMenuItem({ reactive: false });
        this._popupBox = new St.BoxLayout({ width: 360, height: 240, reactive: true });
        this._popupBox.add_child(new St.Label({ text: 'Spike popup' }));
        item.add_child(this._popupBox);
        this._button.menu.addMenuItem(item);
        Main.panel.addToStatusArea('mei-dnd-spike', this._button);

        this._monitor = { dragMotion: e => this._onMotion(e) };
        Main.xdndHandler.connectObject(
            'drag-begin', () => this._onBegin(),
            'drag-end', () => this._onEnd(), this);
        global.display.connectObject('window-created', (_d, w) => this._onWindowCreated(w), this);
        global.display.connectObject('notify::focus-window', () =>
            this._note('focus', { title: global.display.focus_window?.get_title() ?? null }), this);

        this._exported = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._exported.export(Gio.DBus.session, '/com/andystmc/MeiDndSpike');
    }

    disable() {
        this._exported.unexport();
        Main.xdndHandler.disconnectObject(this);
        global.display.disconnectObject(this);
        this._quitClient();
        this._button.destroy();
        this._pointer = null;
    }

    _note(what, data = {}) {
        this._log.push({ t: Math.round(now() * 10) / 10, what, ...data });
    }

    // ── D-Bus ────────────────────────────────────────────────────────────────

    SetMode(mode) {
        const flags = Object.fromEntries(mode.split(',').filter(Boolean).map(f => f.includes('=') ? f.split('=') : [f, true]));
        this._mode = {
            win: Boolean(flags.win), layer: flags.layer ?? 'none', passthrough: Boolean(flags.passthrough),
            prewarm: Boolean(flags.prewarm), popup: Boolean(flags.popup), popupDrop: Boolean(flags.popupdrop),
            free: Boolean(flags.free), resident: Boolean(flags.resident), cairo: Boolean(flags.cairo),
            realize: Boolean(flags.realize), twice: Boolean(flags.twice),
        };
        if (this._mode.win && this._mode.resident) this._spawn();
        if (this._mode.twice) {
            this._send('show 60 32');
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
                this._send('hide');
                return GLib.SOURCE_REMOVE;
            });
        }
        if (flags.openmenu) this._button.menu.open();
        this._note('mode', { mode: this._mode });
    }

    Targets() {
        return JSON.stringify({
            button: rectOf(this._button),
            popup: this._button.menu.isOpen ? rectOf(this._popupBox) : null,
            windows: global.get_window_actors().map(a => {
                const w = a.get_meta_window();
                const r = w.get_frame_rect();
                return { title: w.get_title(), x: r.x, y: r.y, w: r.width, h: r.height, type: w.get_window_type(),
                    layer: w.get_layer(), group: a.get_parent() === global.top_window_group ? 'top' : 'window' };
            }),
            focus: global.display.focus_window?.get_title() ?? null,
        });
    }

    Reset() {
        this._log = [];
        this._quitClient();
        if (this._button.menu.isOpen) this._button.menu.close();
    }

    /** Press at `from`, move in `steps` to `to`, keep still (or jiggle) for `holdMs`, release. */
    Drag(json) {
        const { from, to, steps = 20, stepMs = 30, holdMs = 400, jiggle = true, release = true, via = null } = JSON.parse(json);
        const points = [];
        const legs = via ? [[from, via], [via, to]] : [[from, to]];
        for (const [a, b] of legs)
            for (let i = 1; i <= steps; i++)
                points.push([a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps]);
        const p = this._pointer;
        p.notify_absolute_motion(GLib.get_monotonic_time(), from[0], from[1]);
        let i = 0;
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
            p.notify_button(GLib.get_monotonic_time(), Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
            this._note('press', { at: from });
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, stepMs, () => {
                if (i < points.length) {
                    const [x, y] = points[i++];
                    p.notify_absolute_motion(GLib.get_monotonic_time(), x, y);
                    return GLib.SOURCE_CONTINUE;
                }
                this._note('arrived', { at: to });
                let held = 0;
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
                    held += 50;
                    if (held < holdMs) {
                        if (jiggle) p.notify_absolute_motion(GLib.get_monotonic_time(), to[0] + (held / 50) % 2, to[1]);
                        return GLib.SOURCE_CONTINUE;
                    }
                    if (release) {
                        p.notify_button(GLib.get_monotonic_time(), Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
                        this._note('release', { at: to });
                    }
                    return GLib.SOURCE_REMOVE;
                });
                return GLib.SOURCE_REMOVE;
            });
            return GLib.SOURCE_REMOVE;
        });
    }

    Log() {
        return JSON.stringify(this._log);
    }

    // ── The drag ─────────────────────────────────────────────────────────────

    _onBegin() {
        this._dragging = true;
        this._overSince = 0;
        this._positions = 0;
        this._note('xdnd-begin');
        DND.addDragMonitor(this._monitor);
        if (this._mode.win && this._mode.prewarm) this._spawn();
    }

    _onEnd() {
        this._dragging = false;
        this._note('xdnd-end', { positions: this._positions });
        DND.removeDragMonitor(this._monitor);
        // The drag ends at the release, before the drop's data is read: hiding now would cancel it.
        const shown = this._shownAt;
        this._shownAt = null;
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
            this._setPassthrough(false);
            if (shown) this._send('hide');
            return GLib.SOURCE_REMOVE;
        });
    }

    _onMotion(e) {
        this._positions++;
        const button = rectOf(this._button);
        const popup = this._button.menu.isOpen ? rectOf(this._popupBox) : null;
        if (!this._dragging) return DND.DragMotionResult.CONTINUE;
        const target = inside(button, e.x, e.y) ? button : popup && inside(popup, e.x, e.y) ? popup : null;
        const picked = e.targetActor;
        if (target && !this._overSince) {
            this._overSince = now();
            this._note('over-target', { which: target === button ? 'button' : 'popup', picked: picked?.toString().slice(0, 80) });
        }
        if (!target && this._overSince && !(this._shownAt && inside(this._shownAt, e.x, e.y, 8))) {
            this._overSince = 0;
            this._note('left-target');
            if (this._shownAt) this._send('hide');
            this._shownAt = null;
            this._setPassthrough(false);
        }
        if (target && this._mode.popup && !this._button.menu.isOpen && now() - this._overSince > 300) {
            this._note('popup-open');
            this._button.menu.open();
        }
        if (target && this._mode.win && !this._shownAt && (target === button || this._mode.popupDrop)) {
            this._shownAt = target;
            this._setPassthrough(this._mode.passthrough);
            if (!this._client) this._spawn();
            this._note('show-requested', { rect: target });
            this._send(`show ${target.w} ${target.h}`);
        }
        return DND.DragMotionResult.CONTINUE;
    }

    _setPassthrough(on) {
        // Chrome over the drop window must not be picked, or the drag never reaches the window.
        if (on && !this._saved) {
            this._saved = [this._button, Main.panel, this._popupBox, this._button.menu.actor].map(a => [a, a.reactive]);
            for (const [a] of this._saved) a.reactive = false;
            this._note('passthrough-on');
        } else if (!on && this._saved) {
            for (const [a, r] of this._saved) a.reactive = r;
            this._saved = null;
        }
    }

    // ── The drop window ──────────────────────────────────────────────────────

    _spawn() {
        if (this._client) return;
        const launcher = new Gio.SubprocessLauncher({ flags: Gio.SubprocessFlags.STDIN_PIPE });
        launcher.setenv('MEI_DROP_LOG', GLib.getenv('MEI_DROP_LOG') ?? '/dev/null', true);
        if (this._mode.cairo) launcher.setenv('GSK_RENDERER', 'cairo', true);
        if (this._mode.realize) launcher.setenv('MEI_DROP_REALIZE', '1', true);
        this._note('spawn');
        this._client = Meta.WaylandClient.new_subprocess(global.context, launcher,
            ['gjs', '-m', `${GLib.getenv('MEI_SPIKE_DIR')}/dropwin.js`]);
        this._stdin = this._client.get_subprocess().get_stdin_pipe();
        this._client.connectObject('client-destroyed', () => {
            this._note('client-destroyed');
            this._client = null;
        }, this);
    }

    _send(line) {
        if (!this._stdin) return;
        this._stdin.write_bytes(new GLib.Bytes(new TextEncoder().encode(`${line}\n`)), null);
        this._stdin.flush(null);
    }

    _quitClient() {
        if (!this._client) return;
        this._send('quit');
        this._client.disconnectObject(this);
        this._client = null;
        this._stdin = null;
    }

    _onWindowCreated(window) {
        const ours = this._client?.owns_window(window) ?? false;
        this._note('window-created', { title: window.get_title(), ours, type: window.get_window_type(), layer: window.get_layer() });
        if (!ours) return;
        const types = { dock: Meta.WindowType.DOCK, tooltip: Meta.WindowType.TOOLTIP, dnd: Meta.WindowType.DND,
            notification: Meta.WindowType.NOTIFICATION, utility: Meta.WindowType.UTILITY,
            override: Meta.WindowType.OVERRIDE_OTHER, popup: Meta.WindowType.POPUP_MENU };
        try {
            if (types[this._mode.layer] !== undefined) window.set_type(types[this._mode.layer]);
        } catch (e) {
            this._note('set-type-failed', { error: String(e) });
        }
        if (this._mode.layer === 'above') window.make_above();
        // Mutter 50 lets the Shell lift a window's work-area constraints, so it can sit over the top bar.
        if (this._mode.free) {
            const M = Meta.WindowConstraint.MONITOR;
            window.override_constraints(M, M, M, M);
        }
        window.hide_from_window_list();
        const place = () => {
            const r = this._shownAt;
            if (!r) return;
            window.move_frame(false, r.x, r.y);
            const f = window.get_frame_rect();
            const actor = window.get_compositor_private();
            this._note('placed', { frame: { x: f.x, y: f.y, w: f.width, h: f.height }, type: window.get_window_type(),
                layer: window.get_layer(), group: actor?.get_parent() === global.top_window_group ? 'top' : 'window',
                focus: global.display.focus_window?.get_title() ?? null });
        };
        window.connectObject('shown', () => {
            this._note('window-shown');
            place();
            const actor = window.get_compositor_private();
            actor?.connectObject('first-frame', () => this._note('first-frame'), this);
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
                const f = window.get_frame_rect();
                this._note('after-300ms', { frame: { x: f.x, y: f.y, w: f.width, h: f.height },
                    focus: global.display.focus_window?.get_title() ?? null,
                    pickedAtCentre: global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE, f.x + f.width / 2,
                        f.y + f.height / 2)?.toString().slice(0, 80) });
                return GLib.SOURCE_REMOVE;
            });
        }, this);
    }
}
