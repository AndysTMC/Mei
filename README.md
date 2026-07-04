# Mei (AI Assistant GNOME Extension)
Mei is a modern GNOME Shell extension powered by LLMs that understands your intent, interacts with your system, and assists in accomplishing tasks seamlessly.

## Key Features
- **Broad AI Support**: Seamless integration with local engines (Ollama, llama.cpp) and cloud APIs (OpenAI, Anthropic, Gemini, Groq, Mistral, OpenRouter, DeepSeek).
- **Dual Layouts**: Toggle between a compact quick-query popup and an expanded view with full chat history management.
- **Native Markdown Rendering**: Responses are beautifully formatted with native GNOME widgets for code blocks, tables, lists, and syntax formatting.
- **Deep System Integration**: Automatic GNOME dark/light mode syncing and responsive viewport constraints.

## Dependencies
Before building, ensure you have the following installed on your system:
- **GNOME Shell 50**
- **Node.js & npm** (for building from source)
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

- Provider configuration is stored in GNOME GSettings under `org.gnome.shell.extensions.mei`. API keys are stored in the desktop Secret Service/libsecret keyring when available and legacy plaintext keys are migrated on use. If libsecret or a Secret Service is unavailable, Mei falls back to plaintext GSettings storage so existing setups keep working; use provider-side key restrictions where available and avoid sharing your desktop account.
- For Gemini, prefer a Google API key restricted to the Gemini/Generative Language API and rotate it if your GSettings data may have been exposed. Mei sends Gemini keys in the `x-goog-api-key` header instead of embedding them in request URLs.
- Chat history is stored at `~/.local/share/mei/chats.json`.
- Logs are stored at `~/.local/state/mei/logs.txt`.
- Logs avoid recording full request and response bodies by default, but error messages and operational metadata may still include sensitive context.

### Compatibility

The published metadata currently targets GNOME Shell 50. Local validation was performed on GNOME Shell 50.1; support for older Shell versions should be restored only after smoke testing those versions.

## Development

```sh
npm test            # Run pure TypeScript/Node regression tests
npm run typecheck   # Type-check TypeScript files without emitting
npm run lint        # Dependency-free static check alias for typecheck
npm run format:check # Check source files for trailing whitespace/final newline drift
npm run smoke:providers # Live provider model-list checks when API token env vars are set
npm run build       # Full build to the dist/ directory
npm run check       # Run tests, static checks, formatting checks, and build
npm run dev         # Build, install, and start a GNOME Shell devkit session
```

To test the extension in an isolated development session (requires GNOME Shell development support):
```sh
dbus-run-session gnome-shell --devkit --wayland
```
