/**
 * Test seam for dev builds: lets the nested-Shell end-to-end tests drive the popup and read what
 * it shows, since GNOME 50 doesn't allow Shell.Eval. Exported only when the bundle is built with
 * `--dev` and MEI_DEV_HOOKS=1 is set; production builds drop the import entirely (`__DEV__`).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';

import type { ChatPopup } from '../ui/chatPopup.js';
import type { RuntimeChatController } from './controller.js';

const OBJECT_PATH = '/com/andystmc/MeiDev';
const XML = `
<node>
  <interface name="com.andystmc.MeiDev">
    <method name="Send"><arg type="s" direction="in" name="text"/></method>
    <method name="Popup"><arg type="s" direction="in" name="action"/></method>
    <method name="State"><arg type="s" direction="out" name="json"/></method>
  </interface>
</node>`;

export class DevHooks {
    private readonly _exported: Gio.DBusExportedObject;

    constructor(private readonly _popup: ChatPopup, private readonly _runtime: RuntimeChatController) {
        this._exported = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._exported.export(Gio.DBus.session, OBJECT_PATH);
    }

    destroy(): void {
        this._exported.unexport();
    }

    Send(text: string): void {
        this._popup.onSend?.(text); // the same path a typed message takes
    }

    Popup(action: string): void {
        if (action === 'open') this._popup.open();
        else if (action === 'close') this._popup.close();
        else if (action === 'expand' && !this._popup.isExpanded) this._popup.toggleExpand();
        else if (action === 'collapse' && this._popup.isExpanded) this._popup.toggleExpand();
        else if (action === 'new') this._popup.onNewChat?.();
        else if (action === 'load-latest') this._runtime.debugLoadLatest();
        else if (action === 'reload-draft') this._popup.onReload?.(this._runtime.draftIndex);
    }

    State(): string {
        return JSON.stringify({
            popup: { open: this._popup.isOpen, expanded: this._popup.isExpanded },
            shown: visibleText(this._popup.contentActor),
            controller: this._runtime.debugState(),
        });
    }
}

function visibleText(actor: Clutter.Actor): string[] {
    const out: string[] = [];
    const walk = (a: Clutter.Actor) => {
        if (!a.visible) return;
        if (a instanceof Clutter.Text) {
            const text = a.get_text();
            if (text.trim()) out.push(text);
        }
        for (const child of a.get_children()) walk(child);
    };
    walk(actor);
    return out;
}
