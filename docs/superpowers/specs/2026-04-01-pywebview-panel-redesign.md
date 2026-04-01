# ClippyBox Panel Redesign: tkinter → pywebview

## Summary

Replace the tkinter-based result panel with a pywebview window rendering HTML/CSS. This gives full control over visual design while keeping the panel as a native-feeling window managed by Python.

## Visual Direction

**Glass Dark** — modern, layered, translucent feel with subtle blue accents and frosted surfaces. Inspired by macOS system panels.

### Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#0f1923` | Main background (gradient start) |
| `--bg-end` | `#162033` | Gradient end |
| `--bg-input` | `rgba(0,0,0,0.15)` | Input area background |
| `--surface` | `rgba(255,255,255,0.04)` | Cards, input field, capture strip |
| `--border` | `rgba(255,255,255,0.06)` | Dividers and borders |
| `--border-input` | `rgba(255,255,255,0.08)` | Input field border |
| `--text` | `rgba(255,255,255,0.8)` | Primary text |
| `--text-strong` | `rgba(255,255,255,0.95)` | Bold/emphasized text |
| `--text-dim` | `rgba(255,255,255,0.25)` | Placeholders, hints |
| `--text-user` | `rgba(255,255,255,0.6)` | User message text |
| `--accent` | `#7eb8f0` | AI label, send button, streaming cursor, status dot |
| `--accent-glow` | `rgba(126,184,240,0.4)` | Header dot glow |
| `--accent-border` | `rgba(126,184,240,0.15)` | AI message left border |
| `--code-bg` | `rgba(255,255,255,0.06)` | Inline code background |
| `--code-text` | `#8cc8ff` | Inline code text |

### Typography

- Body: `-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif` at 14px, line-height 1.65
- Code: `Menlo, monospace` at 12px
- Labels: 11px, weight 600, uppercase, letter-spacing 0.8px
- Hints: 10px

## Architecture

### Window

- **pywebview** frameless window (no native title bar)
- Header row acts as drag region via `-webkit-app-region: drag`
- Window size: 580×700, positioned at right edge of screen
- Resizable with min size 400×500

### Files Changed

| File | Change |
|------|--------|
| `panel.py` | Complete rewrite: replace tkinter with pywebview. Create a `webview.create_window()` call with frameless=True. Expose Python functions to JS via `webview.expose()` for sending follow-up questions. |
| `panel.html` | New file in `data/`: the full HTML/CSS/JS template for the panel UI. Receives data via pywebview's JS bridge. |
| `__main__.py` | Minor: replace `tk.Tk()` + `mainloop()` with pywebview event loop integration. The hotkey listener and overlay subprocess remain unchanged. |
| `pyproject.toml` | Add `pywebview>=5.0` to dependencies |
| `requirements.txt` | Add `pywebview>=5.0` |

### Files NOT Changed

- `ai.py` — no changes needed. The streaming `on_token` callback API works the same.
- `overlay_process.py` — completely independent (PyObjC subprocess), untouched.
- `preflight.py` — no changes needed.
- `install.sh` — no changes needed (pip install handles the new dependency).

### Panel ↔ Python Communication

pywebview provides a JS bridge. Python exposes functions that JS can call:

```
JS → Python:
  send_followup(question: str)  — triggers ai.ask_followup in a thread
  new_capture()                 — (future: re-trigger overlay from panel)

Python → JS:
  window.evaluate_js("appendToken('...')")     — streaming tokens
  window.evaluate_js("newCapture(thumb, dims)") — new capture arrived
  window.evaluate_js("setStatus('...')")        — status updates
  window.evaluate_js("clearChat()")             — reset for new capture
```

### Panel UI Structure (HTML)

```
<div id="panel">
  <header>                    ← drag region
    <dot + "ClippyBox">       ← left
    <"⌘⇧E new capture">      ← right
  </header>
  <div id="capture-strip">   ← thumbnail + dimensions
  <div id="chat">            ← scrollable conversation
    <div class="msg ai">     ← AI messages with left accent border
    <div class="msg user">   ← user messages
  </div>
  <div id="input-area">      ← text input + send button + hints
</div>
```

### Streaming Flow

1. User draws selection → overlay saves crop → `__main__.py` loads image
2. `panel.new_capture(image)` called → JS: `clearChat()`, show "Analyzing..." with pulsing dot
3. Background thread calls `ai.explain_capture(image, [], on_token=callback)`
4. Each token: `window.evaluate_js(f"appendToken({json.dumps(token)})")`
5. Tokens append directly to the current AI message div
6. On completion: status clears

### Input Handling

- Enter sends the message (calls `send_followup()` via JS bridge)
- Shift+Enter inserts a newline
- Send button (↑ arrow) also triggers send
- Input disabled while AI is responding

### Threading

Same model as current: API calls run in daemon threads. pywebview's `evaluate_js()` is thread-safe and can be called from any thread — no `root.after()` scheduling needed.

## What This Does NOT Change

- The global hotkey mechanism (pynput)
- The overlay subprocess (PyObjC)
- The AI backend (ai.py, Ollama integration)
- The preflight checks
- The install script
- The configuration system (.env files)

## Dependencies Added

- `pywebview>=5.0` — lightweight, well-maintained, supports macOS/Linux/Windows. On macOS it uses WebKit (no Electron, no Chromium download).
