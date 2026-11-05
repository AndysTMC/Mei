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
    # 4: memory v0 (§17): profile memories, episode summaries, and full-text indexes over memories,
    # episodes, and the messages people see. The indexes are contentless and keyed by rowid; triggers
    # keep them in step, so deleting a memory or a conversation removes its index rows in the same
    # transaction. (A plain VACUUM could renumber rowids; Mei never runs one, and store.reindex()
    # rebuilds the indexes from the tables if they ever disagree.)
    """
    CREATE TABLE memories (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('profile')),
        text TEXT NOT NULL,
        provenance TEXT NOT NULL CHECK (provenance IN ('user_stated', 'inferred', 'untrusted')),
        status TEXT NOT NULL CHECK (status IN ('active', 'pending_review', 'archived')),
        sensitivity TEXT NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal', 'local_only')),
        pinned INTEGER NOT NULL DEFAULT 0,
        source_task_id TEXT,
        source_conversation_id TEXT,
        superseded_by TEXT,
        use_count INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        last_used_at INTEGER
    );
    CREATE INDEX memories_by_status ON memories (status, updated_at);
    CREATE VIRTUAL TABLE memories_fts USING fts5(text, content='', contentless_delete=1, tokenize='unicode61');
    CREATE TRIGGER memories_fts_insert AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts (rowid, text) VALUES (new.rowid, new.text);
    END;
    CREATE TRIGGER memories_fts_update AFTER UPDATE OF text ON memories BEGIN
        DELETE FROM memories_fts WHERE rowid = old.rowid;
        INSERT INTO memories_fts (rowid, text) VALUES (new.rowid, new.text);
    END;
    CREATE TRIGGER memories_fts_delete AFTER DELETE ON memories BEGIN
        DELETE FROM memories_fts WHERE rowid = old.rowid;
    END;
    CREATE TABLE episodes (
        task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        summary TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE VIRTUAL TABLE episodes_fts USING fts5(summary, content='', contentless_delete=1, tokenize='unicode61');
    CREATE TRIGGER episodes_fts_insert AFTER INSERT ON episodes BEGIN
        INSERT INTO episodes_fts (rowid, summary) VALUES (new.rowid, new.summary);
    END;
    CREATE TRIGGER episodes_fts_delete AFTER DELETE ON episodes BEGIN
        DELETE FROM episodes_fts WHERE rowid = old.rowid;
    END;
    CREATE VIRTUAL TABLE messages_fts USING fts5(content, content='', contentless_delete=1, tokenize='unicode61');
    CREATE TRIGGER messages_fts_insert AFTER INSERT ON messages WHEN new.role IN ('user', 'assistant') BEGIN
        INSERT INTO messages_fts (rowid, content) VALUES (new.rowid, new.content);
    END;
    CREATE TRIGGER messages_fts_delete AFTER DELETE ON messages WHEN old.role IN ('user', 'assistant') BEGIN
        DELETE FROM messages_fts WHERE rowid = old.rowid;
    END;
    INSERT INTO messages_fts (rowid, content) SELECT rowid, content FROM messages WHERE role IN ('user', 'assistant');
    ALTER TABLE tasks ADD COLUMN recalled TEXT NOT NULL DEFAULT '[]'
    """,
    # 5: computer use (§10.3, decision 0022): a "handoff" asks the person to do a step Mei may not (a
    # password field). SQLite can't change a CHECK in place, so the table is rebuilt with the same rows.
    """
    CREATE TABLE input_requests_v5 (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        action_id TEXT,
        kind TEXT NOT NULL CHECK (kind IN ('question', 'continue', 'in_doubt', 'handoff')),
        spec TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('pending', 'answered', 'superseded')),
        answer TEXT,
        created_at INTEGER NOT NULL,
        answered_at INTEGER
    );
    INSERT INTO input_requests_v5 (id, task_id, action_id, kind, spec, state, answer, created_at, answered_at)
        SELECT id, task_id, action_id, kind, spec, state, answer, created_at, answered_at FROM input_requests;
    DROP TABLE input_requests;
    ALTER TABLE input_requests_v5 RENAME TO input_requests;
    CREATE INDEX input_requests_by_task ON input_requests (task_id, state)
    """,
    # 6: the pause before Mei answers (decision 0028). A stored 8 s is decision 0026's default of one
    # day, not a choice anyone made: it becomes the new default, 0.8 s. Any other value is kept.
    """
    UPDATE config SET document = json_set(document, '$.voice.end_pause_ms', 800)
        WHERE json_extract(document, '$.voice.end_pause_ms') = 8000
    """,
    # 7: a grant remembers whether the card it came from said data would leave this computer
    # (decision 0031). Grants from before can't vouch for that, so they don't cover sending.
    """
    ALTER TABLE grants ADD COLUMN discloses INTEGER NOT NULL DEFAULT 0
    """,
    # 8: a memory saved as user-stated in a task that had read content others wrote went by word
    # overlap alone (decision 0041). Those go back to the person's review; keeping one makes it
    # theirs again. Memories whose task is gone can't be told apart and are left as they are.
    """
    UPDATE memories SET status = 'pending_review', provenance = 'untrusted'
        WHERE status = 'active' AND provenance = 'user_stated'
          AND source_task_id IN (SELECT id FROM tasks WHERE tainted = 1)
    """,
]
