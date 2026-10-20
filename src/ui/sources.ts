/**
 * GLib timeouts and idles owned by one UI component. Destroying the set removes every pending
 * source, so no callback runs on an actor that's already gone.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import GLib from 'gi://GLib';

/** Return `GLib.SOURCE_CONTINUE` to run again, `GLib.SOURCE_REMOVE` to stop. */
export type SourceCallback = () => boolean;

export class SourceSet {
    private readonly _ids = new Set<number>();
    private _destroyed = false;

    timeout(ms: number, callback: SourceCallback, priority: number = GLib.PRIORITY_DEFAULT): number {
        const id: number = GLib.timeout_add(priority, ms, () => this._run(id, callback));
        this._ids.add(id);
        return id;
    }

    idle(callback: SourceCallback, priority: number = GLib.PRIORITY_DEFAULT_IDLE): number {
        const id: number = GLib.idle_add(priority, () => this._run(id, callback));
        this._ids.add(id);
        return id;
    }

    /** Remove a pending source. Ids that already ran (or 0) are ignored. Always returns 0, for `id = remove(id)`. */
    remove(id: number): 0 {
        if (id && this._ids.delete(id)) GLib.source_remove(id);
        return 0;
    }

    destroy(): void {
        this._destroyed = true;
        for (const id of this._ids) GLib.source_remove(id);
        this._ids.clear();
    }

    private _run(id: number, callback: SourceCallback): boolean {
        if (this._destroyed) return GLib.SOURCE_REMOVE;
        const again = callback();
        if (!again) this._ids.delete(id);
        return again;
    }
}
