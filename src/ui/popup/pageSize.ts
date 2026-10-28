/**
 * How big the popup's large page is (decision 0034): about 65% of the primary monitor's width at
 * 16:10, never past the work area's edges. Pure, so it's tested without the Shell.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

export interface Size {
    width: number;
    height: number;
}

export interface Area extends Size {
    x: number;
    y: number;
}

const SHARE_OF_WIDTH = 0.65;
const ASPECT = 16 / 10;
/** Kept clear at the sides and bottom of the work area. */
const EDGE = 24;
/** Under the top bar: the popup's own margin and arrow. */
const TOP_GAP = 16;
const MIN = { width: 320, height: 240 };

/** 1920×1080 with a 32 px top bar: 1248×780. */
export function largePageSize(monitor: Size, workArea: Area): Size {
    const width = Math.min(monitor.width * SHARE_OF_WIDTH, workArea.width - 2 * EDGE);
    const height = Math.min(width / ASPECT, workArea.height - TOP_GAP - EDGE);
    return { width: Math.round(Math.max(MIN.width, width)), height: Math.round(Math.max(MIN.height, height)) };
}
