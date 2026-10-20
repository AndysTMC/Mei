# Agent protocol

## Commands

- Install: `npm install` (Node 20+)
- Dev: `npm run dev`
- Test (one file): `MEI_TEST_PATTERN=<name> npm test`
- Test (full): `npm test`
- Coverage: `npm run test:coverage`
- Lint / typecheck: `npm run typecheck` (`npm run lint` is the same)
- Format: `npm run format:check`
- Build: `npm run build`
- Check (test + typecheck + format + build + UI-only bundle check): `npm run check`
- Live provider smoke: `npm run smoke:providers` (runs `runtime/tests/live_smoke.py`; needs a local `.env` from `.env.example`; keys are never printed; never commit `.env`)
- Runtime (Python, `runtime/`): `cd runtime && uv sync && uv run pytest` (process tests need `dbus-run-session`)
- Protocol fixtures (after changing `runtime/src/mei/protocol.py` or event payloads): `cd runtime && uv run python tests/make_fixtures.py`
- End-to-end in a nested Shell (dev build, private session, mock provider): `scripts/e2e-stage1.sh`
- Install test (install, upgrade, uninstall, purge in a private home): `scripts/install-test.sh`
- Release build (wheel with the extension inside, plus a pinned `install.sh`): `scripts/build-release.sh`
- Run this checkout on your own session: `npm run build && npm run install:ext` (links `dist/` as the extension), then `cd runtime && uv run mei-runtime install-dev` (this checkout's runtime becomes the service); log out and back in. Undo with `uv run mei-runtime uninstall-dev`. `mei-runtime install` leaves a symlinked extension alone unless `--force`.

System deps for a real Shell install: GNOME Shell 50+, a keyring, `gsettings`/`gdbus`/`dconf` (checked by `install.sh --check`), `glib-compile-schemas` to build, optional mutter for nested sessions. Call system GLib tools by absolute path (`/usr/bin/gsettings`): Homebrew's can shadow them and silently ignore dconf.

## Hard rules

- Minimal diffs. Touch only what the task requires.
- Do not add a dependency, edit `dist/`, or change the GSettings schema without an explicit ask.
- Do not commit secrets, credentials, `.env` values, or API keys. `.env` is gitignored; `.env.example` is the template.
- For work that will edit more than two files, write `PLAN.md` first. Overwrite it each loop. Do not commit an empty `PLAN.md`.
- Run the targeted test (or `npm run typecheck` when there is no test) before calling the task done.
- README feature copy is not proof of shipped behavior. The extension is panel chat until the code says otherwise.
- `IMPLEMENTATION_PLAN.md` is a finished remediation checklist. Do not treat it as current architecture or test counts.
- Do not rewrite accepted files in `docs/decisions/`. Supersede with a new record.

## Authority

- Level 0 (not facts): `PLAN.md`, chat, `IMPLEMENTATION_PLAN.md`
- Level 2 (constraints): accepted files in `docs/decisions/`
- Level 3 (prefer over prose): `dist/`, compiled GSettings under `dist/schemas/`
- Level 4 (do not edit unless asked): this file, `LICENSE`, `metadata.json`

## Where to read

| Need | File |
|---|---|
| What this is | README.md |
| Extension id / Shell version | metadata.json |
| Portfolio snapshot | .andystmc/project.json |
| Why a choice was made | docs/decisions/ |
| Settings contract | schemas/org.gnome.shell.extensions.mei.gschema.xml |
| Entrypoints | src/extension.ts, src/prefs.ts |

## After you finish

Propose, do not silently apply: a decision draft if you chose something, a one-line note if git will not explain it. Do not silently edit this file, `LICENSE`, or `metadata.json`.
