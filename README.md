# Mei (AI Assistant GNOME Extension)
Mei is a modern GNOME Shell extension powered by LLMs that understands your intent, interacts with your system, and assists in accomplishing tasks seamlessly.

## Key Features
- **Broad AI Support**: Seamless integration with local engines (Ollama, llama.cpp) and cloud APIs (OpenAI, Anthropic, Gemini, Groq, Mistral, OpenRouter).
- **Gets things done, with your say**: Mei can find, read (including PDFs), write, move, and trash files; open apps and switch windows; use the clipboard; play and pause music; check battery and disk; and change a short list of desktop settings (dark mode, accent color, text size, night light, wallpaper, volume). It asks before anything you didn't name, shows where each thing it touches came from, and checks the result itself: "Verified by Mei" means its own check passed, not that the model said so.
- **Runs commands in a sandbox**: builds, conversions, and archives run in a jail that sees only the folders the command names (read-only unless it asks to write, which needs your OK), with no network unless asked. A command outside the sandbox asks every time and shows you the exact command.
- **Remembers what you tell it**: "Remember that my invoices go in Documents/Invoices", and later tasks use it without being reminded. Settings → Memory shows everything Mei remembers, to search, pin, keep local, or delete. Anything a file or web page tried to make it remember waits for your review.
- **Works in the background**: close the popup and Mei keeps going. When a task finishes or needs you, a notification says so; clicking it opens the conversation. Tasks in progress are listed first in the history.
- **Ask about this**: press `Super+Alt+A` to ask about the window you're in, with the text you selected attached.
- **Talk to it**: press `Super+Alt+Space` (or the mic in the popup) and speak; Mei shows what it hears as you talk and answers out loud, then listens a moment more for a follow-up. Say "stop" to stop it. Speech runs on your computer by default; OpenAI, Groq, or Gemini can do it instead, and if they can't be reached, your computer takes over. Turn voice on in setup or Settings → Voice.
- **Dual Layouts**: Toggle between a compact quick-query popup and an expanded view with full chat history management.
- **Native Markdown Rendering**: Responses are beautifully formatted with native GNOME widgets for code blocks, tables, lists, and syntax formatting.
- **Deep System Integration**: Automatic GNOME dark/light mode syncing and responsive viewport constraints.

## How it fits together

Mei has two parts: a GNOME Shell extension (the panel button, the chat popup, and Settings) and a
small Python service, the Mei runtime, that keeps your conversations and settings and talks to the
models. The extension is only the interface; the runtime starts on demand as a systemd user service.

## Requirements

- **GNOME Shell 50 or newer** in a Wayland session, with a systemd user session
- **GNOME Keyring** (or another Secret Service) for API keys; local models work without one
- `gsettings`, `gdbus`, and `dconf` (the `libglib2.0-bin`/`glib2` and `dconf` packages)

The installer checks these and prints the exact package command for apt, dnf, pacman, or zypper. It
never uses `sudo`; everything is installed for your user only. Python comes from
[uv](https://docs.astral.sh/uv/), which the installer adds if it's missing.

## Install

From a source checkout (Node.js 20+ and uv needed to build):

```sh
git clone https://github.com/AndysTMC/Mei.git && cd Mei
npm install
scripts/build-release.sh           # builds release/: the runtime wheel with the extension inside
bash release/install.sh --wheel release/mei_runtime-*.whl
```

Then **log out and back in** (GNOME Shell only notices new extensions at login). Mei's setup opens
at your next login. Run the installer again to upgrade in place. To remove Mei:

```sh
bash release/install.sh --uninstall            # keeps your conversations and settings
bash release/install.sh --uninstall --purge    # also deletes them and Mei's API keys
```

Once releases are published, `install.sh` from a release downloads the pinned runtime and checks
its sha256 before installing anything.

## Configuration & Usage

Setup walks through the Mei service, your model provider and key, when Mei asks before acting,
memory, voice, privacy, and the shortcuts (by default `Super+Alt+M` opens Mei, `Super+Alt+A` asks
about the current window, and `Super+Alt+Space` talks to Mei). Every choice can be changed later in Settings, opened from the ⚙
(gear) icon in the chat popup or with:

```sh
gnome-extensions prefs mei@andystmc.com
```

### Privacy & Local Data

- Conversations and settings live in `~/.local/share/mei/mei.db` (SQLite). They're kept until you
  delete them, unless you choose a retention period in Settings → Privacy.
- API keys are kept only in your keyring ([ADR 0005](docs/decisions/0005-keyring-only-api-keys.md)).
  They never pass through Mei's settings, its D-Bus interface, or its logs.
- Upgrading from an older Mei imports `~/.local/share/mei/chats.json` and your provider settings
  once, moves any API keys stored in GSettings into the keyring, and removes the plaintext copies
  after checking each key reads back.
- Mei sends Gemini keys in the `x-goog-api-key` header, never in request URLs.
- File contents Mei reads go to a cloud model only from files you pointed at (Settings → Privacy can
  change that to any file or none); local models see what Mei reads.
- Whatever approval setting you choose, Mei always asks before anything that can't be undone,
  anything involving passwords or keys, changes to whole top-level folders, and anything a file or
  web page suggested sending off your computer. It never reads SSH keys, keyrings, or browser
  profiles ([ADR 0008](docs/decisions/0008-policy-outside-the-model.md)). Only the popup can approve.
- Overwritten files are backed up under `~/.local/share/mei/backups`, and "delete" means the trash.
- What Mei remembers stays in the same database. Memories marked local-only never go to a cloud
  model, and Settings → Memory → "Forget everything" deletes them all.
- Commands run in a scratch folder per conversation (`~/.cache/mei/workspaces`); their long output
  is kept under `~/.local/share/mei/artifacts`. Both are deleted with the conversation
  ([ADR 0011](docs/decisions/0011-commands-in-a-jail.md)).
- Text you attach with "Ask about this" is treated like a document Mei read: it can't ask Mei to do
  anything on your behalf ([ADR 0013](docs/decisions/0013-background-notices-and-attachments.md)).
- Voice is off until you turn it on. Its models (~125 MB) download once, from the sherpa-onnx
  project's releases, and are checked against pinned checksums. Mei never records: audio stays in
  memory, the speech process has no network and can't see your files, and the microphone closes
  while the screen is locked. If you choose a cloud provider for speech, what you say (or Mei's
  answers) goes to that provider, and Settings says so where you choose it
  ([ADR 0018](docs/decisions/0018-voice-as-built.md)).
- Saying "yes, do it" approves only small, undoable, private actions that Mei has read back to
  you, since anyone in the room could say it. Anything else needs a click on the card.
- The runtime logs to the journal (`journalctl --user -u mei-runtime`); Settings → Logs shows
  recent entries. Logs are redacted and don't record request or response bodies.

### Compatibility

The published metadata targets GNOME Shell 50. Local validation was performed on GNOME Shell 50.1.

## Development

```sh
npm test               # TypeScript/Node unit tests
npm run check          # tests, typecheck, format check, build, and the UI-only bundle check
npm run test:runtime   # the runtime's pytest suite (cd runtime && uv sync first)
npm run test:e2e       # nested GNOME Shell + extension + runtime, on a private session
npm run test:install   # install.sh install/upgrade/uninstall in a private home
npm run smoke:providers # live provider checks using keys from .env
npm run eval           # the eval tasks with the scripted model; add -- --provider groq for a real one
npm run release        # scripts/build-release.sh
npm run dev            # build, link dist/ as the extension, and start a devkit Shell
```

For live provider checks, copy `.env.example` to `.env` and fill only the providers you want to
test. By default the smoke lists each provider's models (read-only); `MEI_LIVE_CHAT=1` also sends
one short message per provider, which can use quota. Local providers are skipped when they aren't
running. Never commit `.env`; it is ignored by Git, and the smoke never prints key values.

To work on the runtime against your own session without installing a release, see
[AGENTS.md](AGENTS.md).

## See also

- [AGENTS.md](AGENTS.md) — install, test, and hard rules for coding agents
- [docs/decisions/](docs/decisions/) — binding choices
- [LICENSE](LICENSE) — GPL-3.0-only

