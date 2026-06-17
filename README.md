# Mei (AI Assistant GNOME Extension)

Mei is a GNOME Shell extension that provides a quick-access panel popup for chatting with AI models — local or cloud.

## Features

- **Multiple AI Providers**: Ollama, llama.cpp, OpenAI, Anthropic, and Gemini.
- **Settings UI**: Configure provider, model, endpoint URL, and API key from a GTK4/Libadwaita preferences window (click the ⚙ icon in the popup).
- **Markdown Rendering**: Headers, bold, italic, strikethrough, code blocks, lists, blockquotes — rendered via Pango markup.
- **Copy Button**: One-click copy of the last AI response.
- **Dark/Light Theme**: Automatically matches your system color scheme.
- **Processing Indicator**: The panel label glows while waiting; hover to reveal a stop button.

## Requirements

- GNOME Shell 45+
- Node.js & npm (for building)
- An AI backend (e.g., [Ollama](https://ollama.com) running locally)

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

### Settings

| Setting | Description |
|---------|-------------|
| Provider | Ollama, llama.cpp, OpenAI, Anthropic, or Gemini |
| Model | Model identifier (e.g., `gemma4`, `gpt-4o`, `claude-sonnet-4-20250514`) |
| Endpoint URL | Custom URL (leave blank for provider default) |
| API Key | Required for cloud providers |

## Development

```sh
npm run typecheck   # Type-check without emitting
npm run build       # Full build to dist/
```

The extension UUID is `mei@andystmc.com`.
