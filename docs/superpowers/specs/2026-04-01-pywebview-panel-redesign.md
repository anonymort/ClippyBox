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
- Window size: 580×700, positioned at right edge of screen using `webview.screens[0].width`
- Resizable with min size 580×500

### Files Changed

| File | Change |
|------|--------|
| `src/clippybox/panel.py` | Complete rewrite: replace tkinter with pywebview. Create a `webview.create_window()` with `frameless=True`. Expose a `PanelAPI` class via `js_api=` parameter (not the removed `webview.expose()`). |
| `src/clippybox/data/panel.html` | New file: the full HTML/CSS/JS template for the panel UI. Communicates with Python via `window.pywebview.api.*` bridge. |
| `src/clippybox/__main__.py` | Replace `tk.Tk()` + `mainloop()` with `webview.start()`. Hotkey listener and overlay subprocess unchanged. |
| `pyproject.toml` | Add `pywebview>=5.0` to dependencies. Extend `package-data` to include `"data/*.html"`. |
| `requirements.txt` | Add `pywebview>=5.0` |

### Files NOT Changed

- `ai.py` — streaming `on_token` callback API unchanged.
- `overlay_process.py` — independent PyObjC subprocess, untouched.
- `preflight.py` — no changes needed.
- `install.sh` — pip install handles the new dependency.

### Panel ↔ Python Communication

pywebview 5.x uses `js_api=` on `create_window()`. JS calls methods via `window.pywebview.api.*`.

```
JS → Python (via js_api class):
  send_followup(question: str)  — triggers ai.ask_followup in a thread

Python → JS (via window.evaluate_js):
  startStreaming()               — clear placeholder, prepare AI bubble for tokens
  appendToken(token)             — append a streamed token to current AI bubble
  endStreaming()                 — remove cursor, re-enable input
  showError(msg)                 — display error in current AI bubble
  newCapture(thumb_b64, dims)    — new capture: update thumbnail, clear chat, show "Analyzing..."
  setStatus(msg)                 — update status text
```

### Threading & Window Lifecycle

- `webview.start()` blocks the main thread (like `mainloop()` did).
- pynput hotkey listener starts on a background thread before `webview.start()`.
- API calls run in daemon threads, same as before.
- `evaluate_js()` calls are guarded: a `_loaded` event (set by `window.events.loaded`) prevents calls before the webview is ready. All `evaluate_js()` calls go through a helper that waits on this event.
- Window show/focus on re-capture: call `window.show()` to bring panel forward.
- Panel tracks open/closed state via `window.events.closed` callback (replaces `is_open()`).

### Panel UI Structure (HTML)

```
<div id="panel">
  <header>                    ← drag region (-webkit-app-region: drag)
    <dot + "ClippyBox">       ← left
    <"⌘⇧E new capture">      ← right
  </header>
  <div id="capture-strip">   ← thumbnail + dimensions
  <div id="chat">            ← scrollable conversation
    <div class="msg ai">     ← AI messages with left accent border
    <div class="msg user">   ← user messages
  </div>
  <div id="input-area">      ← textarea + send button + hints
</div>
```

Input uses an HTML `<textarea>` with native `placeholder` attribute. Enter sends, Shift+Enter inserts newline. Input is disabled during streaming (re-enabled by `endStreaming()`).

### Streaming Flow

1. User draws selection → overlay saves crop → `__main__.py` loads image
2. Python calls `newCapture(thumb_b64, dims)` → JS clears chat, shows "Analyzing..." with pulsing dot
3. Background thread calls `ai.explain_capture(image, [], on_token=callback)`
4. First token triggers `startStreaming()` → clears "Analyzing...", creates AI bubble
5. Each subsequent token: `appendToken(token)` → appends to AI bubble with blinking cursor
6. On completion: `endStreaming()` → removes cursor, re-enables input, clears status
7. On error: `showError(msg)` → replaces placeholder with error text

### Conversation History

`panel.py` owns `self.history` (list of message dicts). Reset when `new_capture()` is called. Passed to `ai.explain_capture()` / `ai.ask_followup()` as before.

## What This Does NOT Change

- The global hotkey mechanism (pynput)
- The overlay subprocess (PyObjC)
- The AI backend (ai.py, Ollama integration)
- The preflight checks
- The install script
- The configuration system (.env files)

## Dependencies Added

- `pywebview>=5.0` — on macOS uses native WebKit (WKWebView). No Electron, no Chromium download. Requires macOS 10.13+ and Python 3.9+ (project already requires 3.10+).

## Known Risks

- `frameless=True` on macOS Sequoia (15.x) has open pywebview issues around hit-testing. If this surfaces during implementation, fall back to `frameless=True` without `transparent=True` and use a solid background instead of transparency.
