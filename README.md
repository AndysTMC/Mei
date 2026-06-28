# Mei (AI Assistant GNOME Extension)
Mei is a modern GNOME Shell extension powered by LLMs that understands your intent, interacts with your system, and assists in accomplishing tasks seamlessly.

## Key Features
- **Broad AI Support**: Seamless integration with local engines (Ollama, llama.cpp) and cloud APIs (OpenAI, Anthropic, Gemini, Groq, Mistral, OpenRouter, DeepSeek).
- **Dual Layouts**: Toggle between a compact quick-query popup and an expanded view with full chat history management.
- **Native Markdown Rendering**: Responses are beautifully formatted with native GNOME widgets for code blocks, tables, lists, and syntax formatting.
- **Deep System Integration**: Automatic GNOME dark/light mode syncing and responsive viewport constraints.

## Dependencies
Before building, ensure you have the following installed on your system:
- **GNOME Shell 45+**
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

## Development

```sh
npm run typecheck   # Type-check TypeScript files without emitting
npm run build       # Full build to the dist/ directory
```

To test the extension in an isolated nested session (requires `mutter` development packages):
```sh
dbus-run-session gnome-shell --nested --wayland
```
