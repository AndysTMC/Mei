# mei-runtime

The Python service behind the Mei GNOME Shell extension (ADR 0002). It owns conversations, tasks,
providers, and the store, and talks to the extension over the session bus as `com.andystmc.Mei1`
(ADR 0003). Architecture: `docs/architecture/mei-agent-architecture.md`.

```bash
uv sync                      # create .venv with dev tools
uv run pytest                # unit and process-level tests (needs dbus-run-session)
uv run mei-runtime serve     # run on the current session bus
uv run mei-runtime install-dev   # register this checkout with systemd/D-Bus for your session
uv run mei-runtime schema    # print the IPC protocol's JSON Schema
```

Layout (architecture §6): `protocol.py` (IPC shapes), `store/` (SQLite: journal, tasks, config),
`core/` (state machine, engine), `providers/` (OpenAI-compatible chat, fake), `ipc/` (D-Bus service and
the pinned dbus-fast patch), `secrets.py` (keyring), `app.py` (wiring). Data lives in
`$XDG_DATA_HOME/mei/mei.db` (override with `MEI_DATA_DIR`).
