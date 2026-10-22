/**
 * What the setup assistant and Settings say about each step. No GTK here, so it is unit-tested.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type {
    ApprovalPreset, CloudFiles, MemoryView, MicLevelReply, ModelsStep, ServiceStep, SttChoice, TestProviderReply, TtsChoice,
    VoiceModelView, VoiceStateName,
} from '../runtime/protocol.js';

export interface StepInfo {
    id: 'service' | 'models' | 'approvals' | 'memory' | 'voice' | 'privacy' | 'shortcuts';
    title: string;
    skippable: boolean;
}

/** In order. Setup grows a step when its feature ships (§18.3, §22). */
export const SETUP_STEPS: StepInfo[] = [
    { id: 'service', title: 'Mei service', skippable: false },
    { id: 'models', title: 'Models', skippable: true },
    { id: 'approvals', title: 'Approvals', skippable: true },
    { id: 'memory', title: 'Memory', skippable: true },
    { id: 'voice', title: 'Voice', skippable: true },
    { id: 'privacy', title: 'Privacy', skippable: true },
    { id: 'shortcuts', title: 'Shortcuts', skippable: true },
];

/** The approval presets (§13.2), in the order offered, with what each means in practice. */
export const APPROVAL_PRESETS: { id: ApprovalPreset; label: string; description: string }[] = [
    { id: 'cautious', label: 'Always',
        description: 'Mei asks before it changes any file, setting, or app, even ones you named.' },
    { id: 'balanced', label: 'Unless I named it',
        description: 'Changes to the folders, files, apps, and settings you mention go ahead; anything else asks first.' },
    { id: 'hands_off', label: 'Less often',
        description: 'Changes inside your home folder go ahead too, unless a file or page suggested them.' },
];

/** Always true, whatever the preset: shown so nobody thinks a preset turns these off. */
export const APPROVAL_FLOOR = 'Whatever you choose, Mei always asks before anything that can’t be undone, anything '
    + 'involving passwords or keys, changes to whole top-level folders, and anything a file or web page suggested '
    + 'sending off this computer. It never reads your SSH keys, keyrings, or browser profiles.';

export const CLOUD_FILES: { id: CloudFiles; label: string; description: string }[] = [
    { id: 'pointed', label: 'Files I point to',
        description: 'Contents of files in folders you named go to cloud models; others stay on this computer.' },
    { id: 'always', label: 'Any file', description: 'Everything Mei reads can go to your cloud model.' },
    { id: 'never', label: 'Never', description: 'File contents only go to models running on this computer.' },
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

const MEMORY_SOURCE: Record<MemoryView['provenance'], string> = {
    user_stated: 'You said this',
    inferred: 'Mei worked this out',
    untrusted: 'From something Mei read',
};

/** Under a memory in Settings: where it came from, how often Mei used it, and how it's kept. */
export function memorySubtitle(memory: MemoryView): string {
    const used = memory.use_count ? `used ${memory.use_count} ${memory.use_count === 1 ? 'time' : 'times'}` : 'not used yet';
    const kept = [memory.pinned ? 'pinned' : '', memory.sensitivity === 'local_only' ? 'local only' : ''].filter(Boolean);
    return [MEMORY_SOURCE[memory.provenance] ?? '', used, ...kept].filter(Boolean).join(' · ');
}

/** Who writes down what the person says (§11.5: a cloud choice says where the voice goes). */
export const STT_CHOICES: { id: SttChoice; label: string; description: string }[] = [
    { id: 'local', label: 'On this computer', description: 'Your voice stays on this computer.' },
    { id: 'openai', label: 'OpenAI', description: 'What you say is sent to OpenAI to be written down (uses your OpenAI key).' },
    { id: 'groq', label: 'Groq', description: 'What you say is sent to Groq to be written down (uses your Groq key).' },
];

export const TTS_CHOICES: { id: TtsChoice; label: string; description: string }[] = [
    { id: 'piper', label: 'Amy (quick)', description: 'On this computer; starts speaking at once.' },
    { id: 'kokoro', label: 'Natural', description: 'On this computer; sounds more natural. Quick with an NVIDIA GPU, slower to start without one.' },
    { id: 'openai', label: 'OpenAI', description: 'Mei’s answers are sent to OpenAI to be spoken (uses your OpenAI key).' },
    { id: 'gemini', label: 'Gemini', description: 'Mei’s answers are sent to Google to be spoken (uses your Gemini key).' },
];

const VOICE_STATUS: Record<VoiceStateName, string> = {
    off: 'Off', unavailable: 'Not ready', starting: 'Getting ready…', idle: 'Ready',
    listening: 'Listening', thinking: 'Thinking', speaking: 'Speaking', suspended: 'Paused while the screen is locked',
};

export function voiceStatusText(state: VoiceStateName, note: string): string {
    const base = VOICE_STATUS[state] ?? state;
    return note ? `${base}: ${note}` : base;
}

export function modelLine(m: VoiceModelView): string {
    const size = `${Math.round(m.size / 1_000_000)} MB`;
    if (m.error) return `${size} · couldn’t download: ${m.error}`;
    if (m.have) return `${size} · downloaded`;
    if (m.got !== undefined && m.total) return `${size} · downloading ${Math.floor((100 * m.got) / m.total)}%`;
    return `${size} · ${m.needed ? 'needed' : 'not downloaded'}`;
}

export function micText(level: MicLevelReply): string {
    if (level.overdriven) {
        return `Too loud even in silence (${level.db.toFixed(0)} dB, ${level.clipped_pct.toFixed(1)}% clipped): Mei will mishear. Fix lowers the microphone’s level.`;
    }
    return `Sounds right (${level.db.toFixed(0)} dB in silence)`;
}
