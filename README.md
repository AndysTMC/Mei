# Mei (AI Assistant GNOME Extension)
Mei is a modern GNOME Shell extension powered by LLMs that understands your intent, interacts with your system, and assists in accomplishing tasks seamlessly.

## Key Features
- **Broad AI Support**: Seamless integration with local engines (Ollama, llama.cpp) and cloud APIs (OpenAI, Anthropic, Gemini, Groq, Mistral, OpenRouter).
- **Dual Layouts**: Toggle between a compact quick-query popup and an expanded view with full chat history management.
- **Native Markdown Rendering**: Responses are beautifully formatted with native GNOME widgets for code blocks, tables, lists, and syntax formatting.
- **Deep System Integration**: Automatic GNOME dark/light mode syncing and responsive viewport constraints.

## Dependencies
Before building, ensure you have the following installed on your system:
- **GNOME Shell 50**
- **Node.js 20 or newer & npm** (for building from source)
- **glib2.0-bin** or **glib2** (for `glib-compile-schemas` used in the build process)
- **mutter-dev** or **mutter-bin-dev** (optional, required only for testing in a nested session)

## Build & Install

```sh
# Clone the repository
git clone https://github.com/AndysTMC/Mei.git
cd Mei

# Install dependencies and build
npm install
npm run build

# Install the extension to your local GNOME extensions directory
npm run install:ext
```

After installing, restart GNOME Shell:
- **X11**: Press `Alt+F2`, type `r`, and press `Enter`
- **Wayland**: Log out and log back in

Finally, enable the extension:
```sh
gnome-extensions enable mei@andystmc.com
```

## Configuration & Usage
To select your preferred AI provider and enter API keys, open the extension settings via the ⚙ (gear) icon in the chat popup, or run:
```sh
gnome-extensions prefs mei@andystmc.com
```

### Privacy & Local Data

- Provider configuration is stored in GNOME GSettings under `org.gnome.shell.extensions.mei`. API keys are also stored in the desktop Secret Service/libsecret keyring when available, with a plaintext GSettings fallback retained because the Secret Service can become unavailable across Shell restarts. Use provider-side key restrictions where available and avoid sharing your desktop account.
- For Gemini, prefer a Google API key restricted to the Gemini/Generative Language API and rotate it if your GSettings data may have been exposed. Mei sends Gemini keys in the `x-goog-api-key` header instead of embedding them in request URLs.
- Chat history is stored at `~/.local/share/mei/chats.json`.
- Logs are stored at `~/.local/state/mei/logs.txt`.
- Logs avoid recording full request and response bodies by default, but error messages and operational metadata may still include sensitive context.

### Compatibility

The published metadata currently targets GNOME Shell 50. Local validation was performed on GNOME Shell 50.1; support for older Shell versions should be restored only after smoke testing those versions.

## Development

```sh
npm test            # Run pure TypeScript/Node regression tests
npm run test:coverage # Run the regression suite with Node coverage reporting
npm run typecheck   # Type-check TypeScript files without emitting
npm run lint        # Dependency-free static check alias for typecheck
npm run format:check # Check source files for trailing whitespace/final newline drift
npm run test:live   # Load .env and run live provider model-list checks
npm run build       # Full build to the dist/ directory
npm run check       # Run tests, static checks, formatting checks, and build
npm run dev         # Build, install, and start a GNOME Shell devkit session
```

For live provider validation, copy `.env.example` to `.env` and fill only the
providers you want to test. Model-list checks are read-only. Text-generation
checks are disabled by default because they can consume quota or incur charges;
set `MEI_LIVE_CHAT=1` explicitly to enable them. Local providers are also
opt-in so the suite does not fail merely because a local server is not running.

Never commit `.env`; it is ignored by Git. The live runner reports provider
names and sanitized API errors but never prints credential values.

To test the extension in an isolated development session (requires GNOME Shell development support):
```sh
dbus-run-session gnome-shell --devkit --wayland
```

## See also

- [AGENTS.md](AGENTS.md) — install, test, and hard rules for coding agents
- [docs/decisions/](docs/decisions/) — binding choices
- [LICENSE](LICENSE) — GPL-3.0-only

