import '@girs/gjs';
import '@girs/gjs/dom';
import '@girs/gnome-shell/ambient';
import '@girs/gnome-shell/extensions/global';
import '@girs/soup-3.0';

/** Build-time constant injected by esbuild. `true` in dev, `false` in prod. */
declare global {
    const __DEV__: boolean;
}

declare module 'resource:///org/gnome/shell/ui/animation.js' {
    import Clutter from 'gi://Clutter';
    export class Spinner extends Clutter.Actor {
        constructor(size: number, options?: { animate?: boolean; hideOnStop?: boolean });
        play(): void;
        stop(): void;
    }
}
