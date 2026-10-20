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
]
