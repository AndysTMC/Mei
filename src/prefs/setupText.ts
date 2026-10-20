/**
 * What the setup assistant and Settings say about each step. No GTK here, so it is unit-tested.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ModelsStep, ServiceStep, TestProviderReply } from '../runtime/protocol.js';

export interface StepInfo {
    id: 'service' | 'models' | 'privacy' | 'shortcuts';
    title: string;
    skippable: boolean;
}

/** In order. Setup grows a step when its feature ships (§18.3, §22). */
export const SETUP_STEPS: StepInfo[] = [
    { id: 'service', title: 'Mei service', skippable: false },
    { id: 'models', title: 'Models', skippable: true },
    { id: 'privacy', title: 'Privacy', skippable: true },
    { id: 'shortcuts', title: 'Shortcuts', skippable: true },
];

const RETENTION_PRESETS: (number | null)[] = [null, 7, 30, 90, 365];

export function retentionLabel(days: number | null): string {
    return days === null ? 'Keep until I delete them' : `After ${periodText(days)}`;
}

export function periodText(days: number): string {
    if (days === 1) return 'a day';
    if (days === 7) return 'a week';
    if (days === 365) return 'a year';
    return `${days} days`;
}

/** The presets, plus the current value when something else set a custom one. */
export function retentionOptions(current: number | null): (number | null)[] {
    if (RETENTION_PRESETS.includes(current)) return [...RETENTION_PRESETS];
    return [null, ...[...RETENTION_PRESETS.slice(1), current as number].sort((a, b) => (a as number) - (b as number))];
}

/** Whether choosing `next` deletes conversations the current setting would keep. */
export function retentionShrinks(current: number | null, next: number | null): boolean {
    return next !== null && (current === null || next < current);
}

export function formatBytes(bytes: number): string {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let unit = 0;
    while (value >= 1000 && unit < units.length - 1) {
        value /= 1000;
        unit++;
    }
    const shown = unit === 0 || value >= 10 ? Math.round(value).toString() : value.toFixed(1);
    return `${shown} ${units[unit]}`;
}

export function homeRelative(path: string, home: string): string {
    return home && (path === home || path.startsWith(`${home}/`)) ? `~${path.slice(home.length)}` : path;
}

export function keyringText(state: ServiceStep['keyring']): string {
    if (state === 'unlocked') return 'Unlocked. API keys are kept here.';
    if (state === 'locked') return 'Locked. Unlock it so Mei can use your API keys.';
    return 'Not found. Install GNOME Keyring to use cloud models; local models work without it.';
}

export function storageText(step: ServiceStep, home: string): string {
    return `${homeRelative(step.data_dir, home)} · ${formatBytes(step.data_bytes)} used · ${formatBytes(step.free_bytes)} free`;
}

export function modelsText(step: ModelsStep): string {
    if (!step.provider) return 'No model chosen yet';
    const name = step.label || step.provider;
    if (!step.model) return `${name} · choose a model`;
    if (step.requires_key && step.has_key === false) return `${name} · ${step.model} · needs an API key`;
    if (step.requires_key && step.has_key === null) return `${name} · ${step.model} · unlock the keyring to check the key`;
    return `${name} · ${step.model}`;
}

export function testText(reply: TestProviderReply): string {
    const seconds = (reply.ms / 1000).toFixed(1);
    if (reply.ok) return `Answered in ${seconds} s: “${reply.reply ?? ''}”`;
    return `Didn't work: ${reply.error ?? 'no answer'}`;
}

/** The last page: what was skipped and where to change it. */
export function doneText(skipped: Iterable<string>, shortcutLabel: string): string {
    const titles = SETUP_STEPS.filter(s => [...skipped].includes(s.id)).map(s => s.title);
    const open = shortcutLabel ? `Open Mei from the top bar or with ${shortcutLabel}.` : 'Open Mei from the top bar.';
    if (!titles.length) return `${open} You can change any of this later in Settings.`;
    return `${open} You skipped ${joinTitles(titles)}; set ${titles.length === 1 ? 'it' : 'them'} up any time in Settings.`;
}

function joinTitles(titles: string[]): string {
    if (titles.length < 2) return titles.join('');
    return `${titles.slice(0, -1).join(', ')} and ${titles[titles.length - 1]}`;
}
