# Mei (AI Assistant GNOME Extension)

Mei is a modern, feature-rich GNOME Shell extension that provides a quick-access panel popup for chatting with various AI models — both local and cloud-based.

## Features

- **Quick-Access Panel Popup**: Immediate, one-click access to AI assistance directly from the GNOME Shell top panel.
- **Local & Cloud Provider Support**: Native integration with local engines (Ollama, llama.cpp) and cloud-based APIs (OpenAI, Anthropic, Gemini, Groq, Mistral, OpenRouter, DeepSeek, OpenCode) or custom endpoints.
- **Dual Conversation Layouts**: Toggle between a compact popup for quick, ephemeral queries and a wider "Big Mode" that includes a nested view of your chat history.
- **Dynamic Settings & Config Manager**: Tabbed preferences window with isolated configs (API keys, custom endpoints) and automatic model listings for each provider.
- **Response Management**: Easily cancel active requests mid-generation or copy responses to your clipboard with a single click.

## User Experience (UX) Enhancements

- **Markdown Formatting**: Renders rich formatting (headers, bold, italic, lists, code blocks, and blockquotes) inside responses using Pango markup.
- **Responsive Viewport Scrolling**: Smart height constraints tailored to the display resolution (`60vh` max for messages, `20vh` max for input) with automatic scroll-to-bottom logic on text updates.
- **Custom Caret & Input Blinking**: Highly responsive manual cursor blinking and arrow-key navigation inside the text entry.
- **System Theme Integration**: Automatic, real-time styling sync with your preferred GNOME dark/light mode desktop settings.
- **State Indicators**: Visual feedback through inline button loaders and glowing panel labels when processing a prompt.

## Requirements

- GNOME Shell 45+
- Node.js & npm (for building from source)
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

## Development

```sh
npm run typecheck   # Type-check without emitting
npm run build       # Full build to dist/
```

The extension UUID is `mei@andystmc.com`.

### Testing in a Nested Session

To debug or test the extension in an isolated nested session, you can run:
```sh
dbus-run-session gnome-shell --nested --wayland
```

> [!NOTE]
> Running a nested GNOME Shell instance requires `mutter-bin-dev` (or the equivalent mutter binaries/development package on your distribution). Without it, the nested Wayland DBus session command will fail to instantiate the shell environment.
