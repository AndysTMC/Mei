# Mei (AI Assistant GNOME Extension)

Mei is a GNOME Shell extension that provides a quick-access panel popup for chatting with AI models — local or cloud.

## Features

- **Multiple AI Providers**: Ollama, llama.cpp, OpenAI, Anthropic, Gemini, Groq, Mistral, OpenRouter, DeepSeek, OpenCode, and Custom.
- **Unified Settings UI**: Configure preferences using a clean, tabbed window with navigation pages (General, Providers, Advanced, Logs) accessible via the ⚙ icon in the popup.
- **Isolated Provider Configs**: Connection settings, API keys, and active models are stored independently for each provider.
- **Dynamic Model Fetching**: Fetch model dropdown lists directly from provider endpoints.
- **Markdown Rendering**: Headers, bold, italic, strikethrough, code blocks, lists, blockquotes — rendered via Pango markup.
- **Copy Button**: One-click copy of the last AI response.
- **Dark/Light Theme**: Automatically matches your system color scheme.
- **Processing Indicator**: The panel label glows while waiting; hover to reveal a stop button.

## Requirements

- GNOME Shell 45+
- Node.js & npm (for building)
- An AI backend (e.g., [Ollama](https://ollama.com) running locally, or a cloud provider API key)

## Build & Install

```sh
npm install
npm run build
npm run install:ext
```

Then restart GNOME Shell:
- **X11**: `Alt+F2` → type `r` → Enter
- **Wayland**: Log out and log back in

Enable the extension:
```sh
gnome-extensions enable mei@andystmc.com
```

## Configuration

Open settings via the ⚙ icon in the popup, or run:
```sh
gnome-extensions prefs mei@andystmc.com
```

### Settings Pages

- **General**: Select the active AI provider, choose or input the model name, and set preferences like system prompt or memory limits.
- **Providers**: Manage independent configuration for each AI provider. Customize provider type (Cloud, Local, Custom), edit custom endpoints, input API keys, and dynamically fetch/select available models.
- **Advanced**: Adjust network timeout settings and other extension behavior.
- **Logs**: View extension log output for debugging.

## Development

```sh
npm run typecheck   # Type-check without emitting
npm run build       # Full build to dist/
```

The extension UUID is `mei@andystmc.com`.

