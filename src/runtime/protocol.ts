/**
 * The IPC protocol with the Mei runtime (ADR 0003). Mirrors runtime/src/mei/protocol.py; both are
 * checked against protocol/fixtures/.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

export const BUS_NAME = 'com.andystmc.Mei1';
export const OBJECT_PATH = '/com/andystmc/Mei1';
export const INTERFACE = 'com.andystmc.Mei1.Runtime';
export const ERROR_PREFIX = 'com.andystmc.Mei1.Error.';
export const PROTOCOL_VERSION: [number, number] = [2, 2];

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

export type Execution =
    | 'PROPOSED' | 'REJECTED' | 'POLICY_DENIED' | 'AWAITING_APPROVAL' | 'DENIED' | 'EXPIRED' | 'SUPERSEDED'
    | 'AUTHORIZED' | 'SKIPPED' | 'STARTED' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'IN_DOUBT' | 'ABANDONED';

export type Provenance = 'user' | 'untrusted' | 'model';

export interface ActionResource {
    kind: 'path' | 'app' | 'setting';
    value: string;
    access: 'read' | 'write';
    role: string;
    provenance: Provenance;
}

/** One capability call (§7.3), without its observation (which can be large and private). */
export interface ActionView {
    id: string;
    task_id: string;
    batch_id: string;
    /** The assistant message whose tool call this is. */
    message_id: string;
    position: number;
    tool: string;
    capability: string | null;
    description: string;
    execution: Execution;
    verification: 'not_applicable' | 'pending' | 'passed' | 'failed' | 'unverifiable';
    disposition: 'none' | 'confirmed' | 'reverted' | 'unknown';
    decision: 'allow' | 'ask' | 'deny' | null;
    decision_reason: string | null;
    error: string | null;
    summary: string;
    resources: ActionResource[];
    undo_recorded: boolean;
    created_at: number;
    finished_at: number | null;
}

export type ApprovalScope = 'once' | 'task' | 'always';

/** What an approval card shows (§13.3). `why` is the model's own stated reason. */
export interface ApprovalCard {
    title: string;
    capability: string;
    why?: string;
    reason?: string;
    reason_text?: string;
    resources: { role: string; kind: string; value: string; provenance: Provenance }[];
    effects: string[];
    read_from?: string[];
    scopes: ApprovalScope[];
    default_scope: ApprovalScope;
    scope_text: Partial<Record<ApprovalScope, string>>;
}

export interface ApprovalView {
    id: string;
    task_id: string;
    action_id: string;
    state: 'pending' | 'allowed' | 'denied' | 'superseded';
    card: ApprovalCard;
    created_at: number;
}

export interface FormField {
    name: string;
    label: string;
    kind?: 'text' | 'select' | 'checkbox' | 'date';
    options?: string[];
}

export interface InputRequestView {
    id: string;
    task_id: string;
    action_id: string | null;
    kind: 'question' | 'continue' | 'in_doubt';
    spec: { question: string; choices: string[]; fields: FormField[] };
    state: 'pending' | 'answered' | 'superseded';
    created_at: number;
}

export interface PlanStep {
    text: string;
    status: 'pending' | 'in_progress' | 'done' | 'skipped';
}

export interface PlanCriterion {
    text: string;
    check: { type: string } | null;
    status: 'pending' | 'passed' | 'failed' | 'unverifiable' | 'reported';
}

export interface Plan {
    steps?: PlanStep[];
    criteria?: PlanCriterion[];
}

/** How a task that changed things ended (§8.5). Badges claim only what checks established. */
export interface Outcome {
    kind: 'outcome_verified' | 'partially_verified' | 'reported';
    summary: string;
    criteria: { index: number; text: string; check: string | null; status: string; detail: string }[];
    open_issues: string[];
    note: string;
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
    mode?: string;
    plan?: Plan;
    outcome?: Outcome | null;
    actions?: ActionView[];
    approval?: ApprovalView | null;
    input_request?: InputRequestView | null;
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

/** What the user chose for one provider. The runtime resolves endpoint, format, auth, and headers. */
export interface ProviderSettings {
    model: string;
    url: string;
    mode: string;
    thinking: string;
    reasoning_effort: string;
    options: Record<string, unknown>;
}

export type ApprovalPreset = 'cautious' | 'balanced' | 'hands_off';
export type CloudFiles = 'pointed' | 'always' | 'never';

export interface ConfigDoc {
    active: string;
    providers: Record<string, ProviderSettings>;
    privacy: { conversation_retention_days: number | null; cloud_files?: CloudFiles; [field: string]: unknown };
    approvals?: { preset: ApprovalPreset; [field: string]: unknown };
    /** Fields a newer runtime added; kept as they are when this client writes the config back. */
    [field: string]: unknown;
}

export interface ConfigReply {
    revision: number;
    config: ConfigDoc;
}

export interface ModelsReply {
    models: string[];
    requires_key: boolean;
    from_fallback: boolean;
    error?: string;
}

export interface LogEntry {
    id: number;
    t: number;
    level: string;
    logger: string;
    msg: string;
}

/** Setup steps the runtime can check (§18.3). The Shell's shortcut step is the UI's own. */
export interface ServiceStep {
    id: 'service';
    state: 'done' | 'attention';
    runtime_version: string;
    keyring: 'unlocked' | 'locked' | 'missing';
    data_dir: string;
    data_bytes: number;
    free_bytes: number;
}

export interface ModelsStep {
    id: 'models';
    state: 'done' | 'todo';
    provider: string;
    label: string;
    model: string;
    requires_key: boolean;
    has_key: boolean | null;
}

export interface PrivacyStep {
    id: 'privacy';
    state: 'done';
    conversation_retention_days: number | null;
}

export interface SetupStatusReply {
    version: number;
    completed: boolean;
    offered: boolean;
    skipped: string[];
    steps: (ServiceStep | ModelsStep | PrivacyStep)[];
}

export interface TestProviderReply {
    ok: boolean;
    reply?: string;
    error?: string;
    ms: number;
}

export interface GrantView {
    id: string;
    task_id: string | null;
    capability: string;
    rules: { kind: string; access: string; value: string }[];
    description: string;
    created_at: number;
}
