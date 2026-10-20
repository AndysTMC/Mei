/**
 * IPC protocol v1 with the Mei runtime (ADR 0003). Mirrors runtime/src/mei/protocol.py; both are
 * checked against protocol/v1/fixtures/.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

export const BUS_NAME = 'com.andystmc.Mei1';
export const OBJECT_PATH = '/com/andystmc/Mei1';
export const INTERFACE = 'com.andystmc.Mei1.Runtime';
export const ERROR_PREFIX = 'com.andystmc.Mei1.Error.';
export const PROTOCOL_VERSION: [number, number] = [1, 0];

export type TaskState =
    | 'ACCEPTED' | 'RUNNING' | 'WAITING_APPROVAL' | 'WAITING_INPUT' | 'WAITING_RESOURCE' | 'VERIFYING'
    | 'CANCEL_REQUESTED' | 'INTERRUPTED' | 'COMPLETED' | 'BLOCKED' | 'CANCELLED' | 'FAILED';

export const TERMINAL_STATES: ReadonlySet<TaskState> = new Set(['COMPLETED', 'BLOCKED', 'CANCELLED', 'FAILED']);

export interface Envelope {
    v: number;
    type: string;
    event_id: string;
    epoch: string;
    at: string;
    required: boolean;
    seq: number | null;
    conversation_id: string | null;
    task_id: string | null;
    payload: Record<string, unknown>;
}

export interface ConversationSummary {
    id: string;
    title: string;
    created_at: number;
    updated_at: number;
}

export interface MessageView {
    id: string;
    conversation_id: string;
    task_id: string | null;
    role: 'user' | 'assistant' | 'system';
    content: string;
    thinking: string | null;
    metadata: Record<string, unknown>;
    created_at: number;
}

export interface Draft {
    text: string;
    thinking: string;
}

export interface TaskView {
    id: string;
    conversation_id: string;
    state: TaskState;
    input_message_id: string;
    error: string | null;
    created_at: number;
    updated_at: number;
    draft?: Draft;
}

export interface StreamView {
    conversation_id: string;
    task_id: string;
    message_id: string;
    text: string;
    thinking: string;
    chunk: number;
}

export interface HelloReply {
    epoch: string;
    protocol: [number, number];
    runtime_version: string;
    seq: number;
    pid: number;
}

export interface AttachReply {
    epoch: string;
    seq: number;
    mode: 'snapshot' | 'replay';
    snapshot?: { conversations: ConversationSummary[] };
    events?: Envelope[];
    streams: StreamView[];
}

export interface ConversationReply {
    epoch: string;
    seq: number;
    conversation: ConversationSummary;
    messages: MessageView[];
    tasks: TaskView[];
    streams: StreamView[];
}

export interface SubmitReply {
    conversation_id: string;
    task_id: string;
    message_id: string;
    duplicate: boolean;
}

export interface RuntimeProviderConfig {
    kind: 'none' | 'fake' | 'openai_chat';
    id: string;
    label: string;
    url: string;
    model: string;
    headers: Record<string, string>;
    options: Record<string, unknown>;
}

export interface ConfigReply {
    revision: number;
    config: { provider: RuntimeProviderConfig };
}
