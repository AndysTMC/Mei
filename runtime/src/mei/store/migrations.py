"""Forward-only schema migrations. Never edit a released entry; append a new one."""

MIGRATIONS: list[str] = [
    # 1: conversations, messages, tasks, turns, the event journal, idempotent commands, config.
    """
    CREATE TABLE conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    );
    CREATE TABLE messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        task_id TEXT,
        ordinal INTEGER NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
        content TEXT NOT NULL,
        thinking TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL,
        UNIQUE (conversation_id, ordinal)
    );
    CREATE TABLE tasks (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        input_message_id TEXT NOT NULL,
        state TEXT NOT NULL,
        provider TEXT NOT NULL,
        error TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    );
    CREATE INDEX tasks_by_state ON tasks (state);
    CREATE TABLE turns (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        attempt INTEGER NOT NULL,
        epoch TEXT NOT NULL,
        message_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('running', 'done', 'lost')),
        draft_text TEXT NOT NULL DEFAULT '',
        draft_thinking TEXT NOT NULL DEFAULT '',
        draft_chunk INTEGER NOT NULL DEFAULT 0,
        started_at INTEGER NOT NULL,
        finished_at INTEGER
    );
    CREATE TABLE events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        conversation_id TEXT,
        task_id TEXT,
        type TEXT NOT NULL,
        required INTEGER NOT NULL,
        at TEXT NOT NULL,
        epoch TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE INDEX events_by_conversation ON events (conversation_id, seq);
    CREATE TABLE commands (
        command_id TEXT PRIMARY KEY,
        method TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        result TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        revision INTEGER NOT NULL,
        document TEXT NOT NULL
    );
    INSERT INTO config (id, revision, document) VALUES (1, 0, '{}')
    """,
    # 2: one row per imported legacy source version (§14.3), so imports run once.
    """
    CREATE TABLE imports (
        source TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        imported_at INTEGER NOT NULL,
        counts TEXT NOT NULL,
        PRIMARY KEY (source, sha256)
    )
    """,
    # 3: the agent loop (§7): tool turns in messages; batches, actions, approvals, grants, input
    # requests; per-task loop state. SQLite can't change a CHECK constraint, so messages is rebuilt.
    """
    CREATE TABLE messages_v3 (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        task_id TEXT,
        ordinal INTEGER NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
        content TEXT NOT NULL,
        thinking TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        tool_calls TEXT,
        replay TEXT,
        action_id TEXT,
        created_at INTEGER NOT NULL,
        UNIQUE (conversation_id, ordinal)
    );
    INSERT INTO messages_v3 (id, conversation_id, task_id, ordinal, role, content, thinking, metadata, created_at)
        SELECT id, conversation_id, task_id, ordinal, role, content, thinking, metadata, created_at FROM messages;
    DROP TABLE messages;
    ALTER TABLE messages_v3 RENAME TO messages;
    CREATE INDEX messages_by_task ON messages (task_id, ordinal);
    ALTER TABLE tasks ADD COLUMN mode TEXT NOT NULL DEFAULT 'INTERACTIVE';
    ALTER TABLE tasks ADD COLUMN tainted INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE tasks ADD COLUMN plan TEXT NOT NULL DEFAULT '{}';
    ALTER TABLE tasks ADD COLUMN outcome TEXT;
    ALTER TABLE tasks ADD COLUMN model_calls INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE tasks ADD COLUMN call_budget INTEGER NOT NULL DEFAULT 25;
    ALTER TABLE tasks ADD COLUMN active_ms INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE tasks ADD COLUMN time_budget_ms INTEGER NOT NULL DEFAULT 1800000;
    ALTER TABLE tasks ADD COLUMN finish_attempts INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE tasks ADD COLUMN nudges INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE tasks ADD COLUMN guard_trips INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE batches (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        message_id TEXT NOT NULL,
        seen_ordinal INTEGER NOT NULL,
        size INTEGER NOT NULL,
        cursor INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX batches_by_task ON batches (task_id, created_at);
    CREATE TABLE actions (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        call_id TEXT NOT NULL,
        tool TEXT NOT NULL,
        capability TEXT,
        version INTEGER,
        arguments TEXT NOT NULL,
        params TEXT,
        params_hash TEXT,
        effects TEXT,
        resources TEXT NOT NULL DEFAULT '[]',
        description TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT '',
        execution TEXT NOT NULL,
        verification TEXT NOT NULL DEFAULT 'not_applicable',
        disposition TEXT NOT NULL DEFAULT 'none',
        decision TEXT,
        decision_reason TEXT,
        policy_version TEXT,
        grant_id TEXT,
        approval_id TEXT,
        result TEXT,
        error TEXT,
        epoch TEXT,
        created_at INTEGER NOT NULL,
        started_at INTEGER,
        finished_at INTEGER,
        UNIQUE (batch_id, position)
    );
    CREATE INDEX actions_by_task ON actions (task_id, created_at);
    CREATE INDEX actions_by_state ON actions (execution);
    CREATE TABLE approvals (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        action_id TEXT NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
        params_hash TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('pending', 'allowed', 'denied', 'superseded')),
        scope TEXT,
        card TEXT NOT NULL,
        decided_by TEXT,
        created_at INTEGER NOT NULL,
        decided_at INTEGER
    );
    CREATE INDEX approvals_by_task ON approvals (task_id, state);
    CREATE TABLE grants (
        id TEXT PRIMARY KEY,
        task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
        capability TEXT NOT NULL,
        resources TEXT NOT NULL,
        description TEXT NOT NULL,
        approval_id TEXT,
        created_at INTEGER NOT NULL,
        revoked_at INTEGER
    );
    CREATE TABLE input_requests (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        action_id TEXT,
        kind TEXT NOT NULL CHECK (kind IN ('question', 'continue', 'in_doubt')),
        spec TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('pending', 'answered', 'superseded')),
        answer TEXT,
        created_at INTEGER NOT NULL,
        answered_at INTEGER
    );
    CREATE INDEX input_requests_by_task ON input_requests (task_id, state)
    """,
]
