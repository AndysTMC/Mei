# Mei (AI Assistant GNOME Extension)

Mei is a lightweight GNOME Shell extension that provides a quick-access panel popup for chatting with a local Ollama AI model.

## Features
- **Local Ollama Integration**: Connects directly to a local Ollama instance (default: `http://localhost:11435` with `llama3`).
- **Dynamic Popup UI**: Clean, non-intrusive container matching the system's dark/light theme.
- **Markdown Rendering**: Processes basic Markdown (headers, bold, italics, strikethrough, lists, blockquotes, and code blocks) using custom Pango markup.
- **Copy Button**: Quickly copy the latest AI response to your clipboard.
- **Input Control**: Support for multi-line inputs using `Shift+Enter` (press `Enter` to send).
- **Processing Glint**: The top-bar button glows while waiting for responses, and turns into a stop icon (`⏹`) on hover to cancel the active request.

## Installation

1. Copy or symlink this directory to the GNOME Shell extensions folder:
   ```sh
   mkdir -p ~/.local/share/gnome-shell/extensions/
   ln -s "$(pwd)" ~/.local/share/gnome-shell/extensions/mei@andystmc.com
   ```

2. Restart GNOME Shell:
   - **X11**: Press `Alt+F2`, type `r`, and hit `Enter`.
   - **Wayland**: Log out and log back in.

3. Enable the extension:
   ```sh
   gnome-extensions enable mei@andystmc.com
   ```

## Dependencies
- **GNOME Shell**: 40 or newer
- **Ollama**: A local instance running on port 11435 (can be configured in `extension.js`).
