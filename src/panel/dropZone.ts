/**
 * Dropping files or text from other apps on Mei's panel button (decision 0027).
 *
 * The Shell sees a Wayland drag pass over its actors (Meta.Dnd, through Main.xdndHandler) but never
 * gets its data, and a modal grab in the middle of a drag (Mei's popup opening) strands the drag. So
 * while a drag is over the button, a window of Mei's own (src/dropWindow.ts) sits under it and takes
 * the drop. The button and the panel stop being pickable meanwhile, so the drag reaches the window
 * beneath them; the person sees only the button's highlight. The window is a dock (no focus, not in
 * the window list); its process starts when a drag begins and leaves when drags stop.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import type St from 'gi://St';
import * as DND from 'resource:///org/gnome/shell/ui/dnd.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import { decodeDrop, type Drop } from '../runtime/attachment.js';
import { Logger, Tag } from '../utils/logger.js';

/** The drop arrives a few ms after the release (measured: 3–5 ms); past this there was none. */
const DROP_WAIT_MS = 1500;
/** The window's process stays this long after a drag, so the next drag finds it ready. */
const IDLE_EXIT_S = 120;
/** Once the window covers the button, the drag may wander this far before it has left. */
const SLACK_PX = 4;

interface Rect { x: number; y: number; width: number; height: number }

type State = 'idle' | 'dragging' | 'over' | 'dropping';

/** The drop window's process, started through Mutter so its window is known to be Mei's. */
class DropWindowProcess {
    readonly client: Meta.WaylandClient;
    private readonly _stdin: Gio.OutputStream | null;
    private readonly _stdout: Gio.DataInputStream;
    private readonly _cancel = new Gio.Cancellable();

    constructor(script: string, onDrop: (drop: Drop) => void, onGone: () => void) {
        const launcher = new Gio.SubprocessLauncher({ flags: Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE });
        launcher.setenv('GSK_RENDERER', 'cairo', true);
        this.client = Meta.WaylandClient.new_subprocess(global.context, launcher, ['gjs', '-m', script]);
        const process = this.client.get_subprocess();
        this._stdin = process.get_stdin_pipe();
        this._stdout = new Gio.DataInputStream({ base_stream: process.get_stdout_pipe()! });
        this.client.connect('client-destroyed', () => onGone());
        this._read(onDrop);
    }

    private _read(onDrop: (drop: Drop) => void): void {
        this._stdout.read_line_async(GLib.PRIORITY_DEFAULT, this._cancel, (_s, res) => {
            let line: string | null;
            try {
                [line] = this._stdout.read_line_finish_utf8(res);
            } catch {
                return; // cancelled, or the process went away (client-destroyed says so)
            }
            if (line === null) return;
            const drop = decodeDrop(line);
            if (drop) onDrop(drop);
            else Logger.warn(Tag.UI, 'The drop window sent something that isn’t a drop; ignored');
            this._read(onDrop);
        });
    }

    send(command: string): void {
        try {
            this._stdin?.write_all(new TextEncoder().encode(`${command}\n`), null);
            this._stdin?.flush(null);
        } catch (e) {
            Logger.warn(Tag.UI, `The drop window didn’t take “${command}”: ${(e as Error).message}`);
        }
    }

    quit(): void {
        this.send('quit');
        this._cancel.cancel();
        const process = this.client.get_subprocess();
        // It quits on "quit" or when its stdin closes; if it hangs, it is ours to end.
        GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
            if (!process.get_if_exited()) process.force_exit();
            return GLib.SOURCE_REMOVE;
        });
        this._stdin?.close(null);
    }
}

export class DropZone {
    /** Called with what was dropped on the button. */
    onDrop: ((drop: Drop) => void) | null = null;

    private _state: State = 'idle';
    private _process: DropWindowProcess | null = null;
    private _rect: Rect | null = null;
    /** Actors made unpickable while the window sits under them, with what they were. */
    private _unpicked: [Clutter.Actor, boolean][] = [];
    private _dropTimeout = 0;
    private _idleTimeout = 0;
    private readonly _monitor: DND.DragMonitor = { dragMotion: event => this._onMotion(event) };
    private readonly _windowCreated: number;

    constructor(private readonly _anchor: St.Widget, private readonly _script: string) {
        Main.xdndHandler.connectObject('drag-begin', () => this._onBegin(), 'drag-end', () => this._onEnd(), this);
        this._windowCreated = global.display.connect('window-created', (_d: Meta.Display, w: Meta.Window) =>
            this._onWindowCreated(w));
    }

    /** Where the drop zone is, and where the button is; for the dev-build test hooks. */
    get debugState(): { state: State; button: Rect | null } {
        return { state: this._state, button: this._anchor.mapped ? actorRect(this._anchor) : null };
    }

    destroy(): void {
        Main.xdndHandler.disconnectObject(this);
        global.display.disconnect(this._windowCreated);
        if (this._state !== 'idle') DND.removeDragMonitor(this._monitor);
        this._finish();
        this._clearIdle();
        this._process?.quit();
        this._process = null;
    }

    private _onBegin(): void {
        if (this._state === 'dropping') this._finish();
        if (this._state !== 'idle') return;
        this._state = 'dragging';
        this._clearIdle();
        DND.addDragMonitor(this._monitor);
        // Ready before the drag reaches the button: starting takes ~120 ms, showing then ~18 ms.
        this._process ??= new DropWindowProcess(this._script, drop => this._onDropped(drop), () => this._onGone());
    }

    private _onMotion(event: DND.DragEvent): DND.DragMotionResult {
        if (event.source !== Main.xdndHandler) return DND.DragMotionResult.CONTINUE;
        const button = this._anchor.mapped ? actorRect(this._anchor) : null;
        if (this._state === 'dragging' && button && inside(button, event.x, event.y, 0)) this._enter(button);
        else if (this._state === 'over' && !(this._rect && inside(this._rect, event.x, event.y, SLACK_PX))) this._leave();
        return DND.DragMotionResult.CONTINUE;
    }

    /** The drag reached the button: highlight it and put the window under it. */
    private _enter(button: Rect): void {
        this._state = 'over';
        this._rect = button;
        this._anchor.add_style_class_name('drop-target');
        this._unpick();
        this._process?.send(`show ${button.width} ${button.height}`);
    }

    private _leave(): void {
        this._state = 'dragging';
        this._hide();
    }

    /** The release ends the drag before the drop's data is read: keep the window until it has it. */
    private _onEnd(): void {
        DND.removeDragMonitor(this._monitor);
        if (this._state !== 'over') {
            this._finish();
            return;
        }
        this._state = 'dropping';
        this._dropTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, DROP_WAIT_MS, () => {
            this._dropTimeout = 0;
            this._finish();
            return GLib.SOURCE_REMOVE;
        });
    }

    private _onDropped(drop: Drop): void {
        if (this._state !== 'dropping' && this._state !== 'over') return; // a drop Mei didn't offer to take
        this._finish();
        this.onDrop?.(drop);
    }

    private _finish(): void {
        if (this._dropTimeout) GLib.source_remove(this._dropTimeout);
        this._dropTimeout = 0;
        this._hide();
        this._state = 'idle';
        this._clearIdle();
        this._idleTimeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, IDLE_EXIT_S, () => {
            this._idleTimeout = 0;
            this._process?.quit();
            this._process = null;
            return GLib.SOURCE_REMOVE;
        });
    }

    private _hide(): void {
        if (this._rect) this._process?.send('hide');
        this._rect = null;
        this._anchor.remove_style_class_name('drop-target');
        this._repick();
    }

    private _onGone(): void {
        this._process = null;
        if (this._state === 'over' || this._state === 'dropping') {
            Logger.warn(Tag.UI, 'The drop window went away during a drag');
            this._state = 'dragging';
            this._hide();
        }
    }

    private _clearIdle(): void {
        if (this._idleTimeout) GLib.source_remove(this._idleTimeout);
        this._idleTimeout = 0;
    }

    /** The button and every reactive actor holding it, up to the Shell's UI group, let the drag through. */
    private _unpick(): void {
        if (this._unpicked.length) return;
        for (let a: Clutter.Actor | null = this._anchor; a && a !== Main.layoutManager.uiGroup; a = a.get_parent()) {
            if (!a.reactive) continue;
            this._unpicked.push([a, a.reactive]);
            a.reactive = false;
        }
    }

    private _repick(): void {
        for (const [actor, reactive] of this._unpicked) actor.reactive = reactive;
        this._unpicked = [];
    }

    /** Mei's own window: a dock over the button (no focus, no work-area limits, not in the window list). */
    private _onWindowCreated(window: Meta.Window): void {
        if (!this._process?.client.owns_window(window)) return;
        window.set_type(Meta.WindowType.DOCK);
        window.hide_from_window_list();
        const shown = window.connect('shown', () => {
            window.disconnect(shown);
            if (this._rect) window.move_frame(false, this._rect.x, this._rect.y);
        });
    }
}

function actorRect(actor: Clutter.Actor): Rect {
    const [x, y] = actor.get_transformed_position();
    const [width, height] = actor.get_transformed_size();
    return { x: Math.round(x), y: Math.round(y), width: Math.round(width), height: Math.round(height) };
}

function inside(r: Rect, x: number, y: number, slack: number): boolean {
    return x >= r.x - slack && x < r.x + r.width + slack && y >= r.y - slack && y < r.y + r.height + slack;
}
