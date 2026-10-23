/**
 * What voice says it's doing, in the composer (§11.2, Stage 5). Pure, so it is tested without the Shell.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { VoiceStateName } from './protocol.js';

export interface VoiceView {
    state: VoiceStateName;
    note: string;
    /** What the person is saying, as heard so far (or the final text, until the reply comes). */
    transcript: string;
    /** This listening is dictation (the mic): its words go into the message box. */
    dictating: boolean;
}

export interface VoiceLine {
    /** Shown at all? Only while voice is doing something, or can't. */
    visible: boolean;
    status: string;
    transcript: string;
    /** The bar offers Stop (listening or speaking). */
    stoppable: boolean;
}

const STATUS: Partial<Record<VoiceStateName, string>> = {
    listening: 'Listening…',
    thinking: 'Thinking…',
    speaking: 'Speaking…',
    starting: 'Getting voice ready…',
    suspended: 'Voice is paused while the screen is locked',
};

export function voiceLine(view: VoiceView): VoiceLine {
    const status = STATUS[view.state];
    if (status) {
        return { visible: true, status, transcript: view.state === 'speaking' ? '' : view.transcript,
            stoppable: view.state === 'listening' || view.state === 'speaking' };
    }
    if (view.state === 'unavailable' && view.note) {
        return { visible: true, status: `Voice isn't available: ${view.note}`, transcript: '', stoppable: false };
    }
    return { visible: false, status: '', transcript: '', stoppable: false };
}
