# pywebview Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tkinter result panel with a pywebview-powered HTML/CSS panel using the Glass Dark visual design.

**Architecture:** The panel becomes an HTML file (`panel.html`) rendered in a frameless pywebview window. Python communicates with JS via pywebview's `js_api` bridge (Python→JS via `evaluate_js`, JS→Python via `window.pywebview.api.*`). The AI backend (`ai.py`), overlay subprocess, and hotkey listener remain unchanged.

**Tech Stack:** Python 3.10+, pywebview 5.x (WebKit on macOS), HTML/CSS/JS

---

### Task 1: Add pywebview dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pywebview to pyproject.toml**

```toml
[project]
name = "clippybox"
version = "0.1.0"
description = "Point at anything on your screen and instantly understand it."
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "Pillow>=10.0.0",
    "pynput>=1.7.6",
    "pyobjc-framework-Cocoa>=10.0",
    "pyobjc-framework-Quartz>=10.0",
    "pywebview>=5.0",
]

[project.scripts]
clippybox = "clippybox.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
clippybox = ["data/system_prompt.txt", "data/panel.html"]
```

- [ ] **Step 2: Add pywebview to requirements.txt**

```
Pillow>=10.0.0
pynput>=1.7.6
pyobjc-framework-Cocoa>=10.0
pyobjc-framework-Quartz>=10.0
pywebview>=5.0
```

- [ ] **Step 3: Install and verify**

Run: `pip install pywebview>=5.0`
Then: `python3 -c "import webview; print(webview.__version__)"`
Expected: version 5.x printed

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml requirements.txt
git commit -m "chore: add pywebview dependency"
```

---

### Task 2: Create the HTML panel template

**Files:**
- Create: `src/clippybox/data/panel.html`

This is the complete HTML/CSS/JS for the panel UI. It defines all the visual design (Glass Dark palette), the chat layout, input handling, and JS functions that Python calls via `evaluate_js`.

- [ ] **Step 1: Create panel.html**

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #0f1923;
    --bg-end: #162033;
    --bg-input: rgba(0,0,0,0.15);
    --surface: rgba(255,255,255,0.04);
    --border: rgba(255,255,255,0.06);
    --border-input: rgba(255,255,255,0.08);
    --text: rgba(255,255,255,0.8);
    --text-strong: rgba(255,255,255,0.95);
    --text-dim: rgba(255,255,255,0.25);
    --text-user: rgba(255,255,255,0.6);
    --accent: #7eb8f0;
    --accent-glow: rgba(126,184,240,0.4);
    --accent-border: rgba(126,184,240,0.15);
    --code-bg: rgba(255,255,255,0.06);
    --code-text: #8cc8ff;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
    background: linear-gradient(170deg, var(--bg) 0%, var(--bg-end) 100%);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }

  /* --- Header (drag region) --- */
  #header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    -webkit-app-region: drag;
    flex-shrink: 0;
  }
  #header-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  #header-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 6px var(--accent-glow);
  }
  #header-title {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.3px;
    color: var(--text-strong);
  }
  #header-hint {
    font-size: 11px;
    color: var(--text-dim);
    font-weight: 500;
    -webkit-app-region: no-drag;
  }

  /* --- Capture strip --- */
  #capture-strip {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 20px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  #thumb {
    width: 64px;
    height: 40px;
    border-radius: 6px;
    border: 1px solid var(--border-input);
    object-fit: cover;
    background: var(--code-bg);
  }
  #dims {
    font-size: 11px;
    color: var(--text-dim);
    font-weight: 500;
  }

  /* --- Chat area --- */
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    scroll-behavior: smooth;
  }
  #chat::-webkit-scrollbar { width: 6px; }
  #chat::-webkit-scrollbar-track { background: transparent; }
  #chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }

  .msg { margin-bottom: 20px; }
  .msg-label {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
  }
  .msg-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }
  .msg-role {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }
  .msg.ai .msg-dot { background: var(--accent); }
  .msg.ai .msg-role { color: var(--accent); }
  .msg.user .msg-dot { background: #a0a0a0; }
  .msg.user .msg-role { color: var(--text-dim); }

  .msg-body {
    font-size: 14px;
    line-height: 1.65;
    padding-left: 12px;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .msg.ai .msg-body {
    color: var(--text);
    border-left: 2px solid var(--accent-border);
  }
  .msg.user .msg-body {
    color: var(--text-user);
  }
  .msg-body strong { color: var(--text-strong); }
  .msg-body code {
    background: var(--code-bg);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
    font-family: Menlo, monospace;
    color: var(--code-text);
  }

  /* Streaming cursor */
  #cursor {
    display: inline-block;
    width: 2px;
    height: 14px;
    background: var(--accent);
    margin-left: 2px;
    vertical-align: text-bottom;
    animation: blink 1s step-end infinite;
  }
  @keyframes blink { 50% { opacity: 0; } }

  /* Analyzing placeholder */
  .analyzing {
    color: var(--text-dim);
    font-style: italic;
  }
  .analyzing-dot {
    display: inline-block;
    animation: pulse 1.5s ease-in-out infinite;
  }
  @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

  /* --- Input area --- */
  #input-area {
    border-top: 1px solid var(--border);
    padding: 12px 20px;
    background: var(--bg-input);
    flex-shrink: 0;
  }
  #input-row {
    display: flex;
    align-items: flex-end;
    gap: 12px;
  }
  #input {
    flex: 1;
    background: var(--surface);
    border: 1px solid var(--border-input);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 13px;
    font-family: inherit;
    color: var(--text);
    resize: none;
    outline: none;
    min-height: 38px;
    max-height: 120px;
  }
  #input::placeholder { color: var(--text-dim); }
  #input:focus { border-color: rgba(126,184,240,0.3); }
  #input:disabled { opacity: 0.5; cursor: not-allowed; }

  #send-btn {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background: rgba(126,184,240,0.1);
    border: 1px solid rgba(126,184,240,0.2);
    color: var(--accent);
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  #send-btn:hover { background: rgba(126,184,240,0.2); }
  #send-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  #input-hints {
    display: flex;
    justify-content: space-between;
    margin-top: 8px;
    font-size: 10px;
    color: rgba(255,255,255,0.15);
  }
</style>
</head>
<body>

  <div id="header">
    <div id="header-left">
      <div id="header-dot"></div>
      <span id="header-title">ClippyBox</span>
    </div>
    <span id="header-hint">⌘⇧E new capture</span>
  </div>

  <div id="capture-strip" style="display:none;">
    <img id="thumb" src="" alt="capture">
    <span id="dims"></span>
  </div>

  <div id="chat">
    <div id="welcome" style="display:flex; align-items:center; justify-content:center; height:100%; color:var(--text-dim); font-size:13px;">
      Press ⌘⇧E to capture a screen region
    </div>
  </div>

  <div id="input-area">
    <div id="input-row">
      <textarea id="input" rows="1" placeholder="Ask a follow-up..." disabled></textarea>
      <button id="send-btn" disabled>↑</button>
    </div>
    <div id="input-hints">
      <span>Enter to send · Shift+Enter for new line</span>
      <span id="model-name"></span>
    </div>
  </div>

<script>
  const chat = document.getElementById('chat');
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('send-btn');
  let currentAiBody = null;

  // --- Python → JS API ---

  function newCapture(thumbBase64, width, height, modelName) {
    document.getElementById('welcome').style.display = 'none';
    document.getElementById('capture-strip').style.display = 'flex';
    document.getElementById('thumb').src = 'data:image/jpeg;base64,' + thumbBase64;
    document.getElementById('dims').textContent = width + ' × ' + height;
    document.getElementById('model-name').textContent = modelName;
    chat.innerHTML = '';
    addAiMessage('<span class="analyzing"><span class="analyzing-dot">●</span> Analyzing…</span>');
    setInputEnabled(false);
  }

  function startStreaming() {
    if (currentAiBody) {
      currentAiBody.innerHTML = '<span id="cursor"></span>';
    }
  }

  function appendToken(token) {
    if (!currentAiBody) return;
    const cursor = document.getElementById('cursor');
    const textNode = document.createTextNode(token);
    if (cursor) {
      currentAiBody.insertBefore(textNode, cursor);
    } else {
      currentAiBody.appendChild(textNode);
    }
    chat.scrollTop = chat.scrollHeight;
  }

  function endStreaming() {
    const cursor = document.getElementById('cursor');
    if (cursor) cursor.remove();
    setInputEnabled(true);
    input.focus();
  }

  function showError(msg) {
    if (currentAiBody) {
      currentAiBody.innerHTML = '';
      currentAiBody.style.color = '#f08080';
      currentAiBody.textContent = msg;
    }
    setInputEnabled(true);
  }

  function setStatus(msg) {
    // Status is shown via the analyzing placeholder; no separate element needed.
  }

  // --- Helpers ---

  function addAiMessage(bodyHtml) {
    const msg = document.createElement('div');
    msg.className = 'msg ai';
    msg.innerHTML =
      '<div class="msg-label"><div class="msg-dot"></div><span class="msg-role">AI</span></div>' +
      '<div class="msg-body">' + bodyHtml + '</div>';
    chat.appendChild(msg);
    currentAiBody = msg.querySelector('.msg-body');
    chat.scrollTop = chat.scrollHeight;
  }

  function addUserMessage(text) {
    const msg = document.createElement('div');
    msg.className = 'msg user';
    msg.innerHTML =
      '<div class="msg-label"><div class="msg-dot"></div><span class="msg-role">You</span></div>' +
      '<div class="msg-body"></div>';
    msg.querySelector('.msg-body').textContent = text;
    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
  }

  function setInputEnabled(enabled) {
    input.disabled = !enabled;
    sendBtn.disabled = !enabled;
  }

  // --- Input handling ---

  function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    addUserMessage(text);
    addAiMessage('<span class="analyzing"><span class="analyzing-dot">●</span> Thinking…</span>');
    input.value = '';
    autoResize();
    setInputEnabled(false);
    window.pywebview.api.send_followup(text);
  }

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  sendBtn.addEventListener('click', sendMessage);

  // Auto-resize textarea
  function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  }
  input.addEventListener('input', autoResize);
</script>
</body>
</html>
```

- [ ] **Step 2: Verify the file loads in a browser**

Run: `open src/clippybox/data/panel.html`
Expected: The Glass Dark panel UI renders in the browser (non-functional, but visually correct).

- [ ] **Step 3: Commit**

```bash
git add src/clippybox/data/panel.html
git commit -m "feat: add Glass Dark HTML panel template"
```

---

### Task 3: Rewrite panel.py for pywebview

**Files:**
- Rewrite: `src/clippybox/panel.py`

Replace all tkinter code with a pywebview-based panel. The public API stays the same: `ResultPanel` with `new_capture(image)` and `is_open()`.

- [ ] **Step 1: Rewrite panel.py**

```python
"""
src/clippybox/panel.py - Result panel UI (pywebview).

Displays the AI explanation in a frameless pywebview window with a
Glass Dark HTML/CSS interface. Tokens stream in via evaluate_js().
"""

import base64
import io
import json
import os
import threading

from PIL import Image

from . import ai


_PANEL_HTML = os.path.join(os.path.dirname(__file__), "data", "panel.html")


class PanelAPI:
    """JS → Python bridge. Methods are callable from JS as window.pywebview.api.*"""

    def __init__(self, panel: "ResultPanel") -> None:
        self._panel = panel

    def send_followup(self, question: str) -> None:
        threading.Thread(
            target=self._panel._do_followup,
            args=(question,),
            daemon=True,
        ).start()


class ResultPanel:
    """
    Floating panel that shows the AI explanation for a captured region.

    Public API:
      new_capture(image) — start a new capture session
      is_open()          — check if the window is still open
      start(on_started)  — create the window (call once from main thread)
    """

    def __init__(self) -> None:
        self.current_image = None
        self.history: list = []
        self._window = None
        self._open = False
        self._loaded = threading.Event()
        self._model = os.environ.get("MODEL", "llava")

    def start(self) -> None:
        """Create the pywebview window. Must be called before webview.start()."""
        import webview

        screen = webview.screens[0]
        x = screen.width - 580 - 24
        y = 60

        self._window = webview.create_window(
            "ClippyBox",
            _PANEL_HTML,
            js_api=PanelAPI(self),
            width=580,
            height=700,
            x=x,
            y=y,
            frameless=True,
            min_size=(580, 500),
            hidden=True,
        )
        self._window.events.loaded += self._on_loaded
        self._window.events.closed += self._on_closed

    def _on_loaded(self) -> None:
        self._loaded.set()

    def _on_closed(self) -> None:
        self._open = False

    def _eval_js(self, js: str) -> None:
        """Safely call evaluate_js, waiting for the window to be loaded."""
        if not self._loaded.wait(timeout=10):
            return
        if self._window is None:
            return
        try:
            self._window.evaluate_js(js)
        except Exception:
            pass

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def new_capture(self, image: Image.Image) -> None:
        """Start a new capture session."""
        self.current_image = image
        self.history = []

        # Generate thumbnail
        thumb = image.copy()
        thumb.thumbnail((128, 80), Image.LANCZOS)
        buf = io.BytesIO()
        thumb.convert("RGB").save(buf, format="JPEG", quality=85)
        thumb_b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

        w, h = image.size
        model = json.dumps(self._model)

        self._window.show()
        self._eval_js(
            f"newCapture({json.dumps(thumb_b64)}, {w}, {h}, {model})"
        )
        self._open = True

        threading.Thread(target=self._explain, daemon=True).start()

    def is_open(self) -> bool:
        return self._open

    # -------------------------------------------------------------------
    # AI calls (background threads)
    # -------------------------------------------------------------------

    def _on_token(self, token: str) -> None:
        self._eval_js(f"appendToken({json.dumps(token)})")

    def _explain(self) -> None:
        try:
            self._streaming_started = False

            def on_first_token(token: str) -> None:
                if not self._streaming_started:
                    self._streaming_started = True
                    self._eval_js("startStreaming()")
                self._on_token(token)

            response, self.history = ai.explain_capture(
                self.current_image, [], on_token=on_first_token
            )
        except Exception as e:
            self._eval_js(f"showError({json.dumps(str(e))})")
        finally:
            self._eval_js("endStreaming()")

    def _do_followup(self, question: str) -> None:
        try:
            self._streaming_started = False

            def on_first_token(token: str) -> None:
                if not self._streaming_started:
                    self._streaming_started = True
                    self._eval_js("startStreaming()")
                self._on_token(token)

            response, self.history = ai.ask_followup(
                self.current_image, question, self.history,
                on_token=on_first_token,
            )
        except Exception as e:
            self._eval_js(f"showError({json.dumps(str(e))})")
        finally:
            self._eval_js("endStreaming()")
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('src/clippybox/panel.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/clippybox/panel.py
git commit -m "feat: rewrite panel with pywebview and Glass Dark UI"
```

---

### Task 4: Update __main__.py for pywebview

**Files:**
- Modify: `src/clippybox/__main__.py`

Replace tkinter event loop with pywebview. The hotkey listener and overlay subprocess are unchanged.

- [ ] **Step 1: Rewrite __main__.py**

```python
"""ClippyBox entry point."""

import os
import sys
import tempfile
import subprocess
import threading

from PIL import Image

from .panel import ResultPanel


_result_panel: ResultPanel | None = None
_overlay_running: bool = False


def _launch_overlay() -> None:
    global _overlay_running

    if _overlay_running:
        return
    _overlay_running = True

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    tmp_path = tmp.name

    try:
        result = subprocess.run([
            sys.executable, "-m", "clippybox.overlay_process", tmp_path
        ])

        captured = (
            result.returncode == 0
            and os.path.exists(tmp_path)
            and os.path.getsize(tmp_path) > 0
        )

        if captured:
            image = Image.open(tmp_path)
            image.load()
            _result_panel.new_capture(image)

    except Exception as e:
        print(f"[ClippyBox] Overlay error: {e}")

    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        _overlay_running = False


def _setup_hotkey():
    from pynput import keyboard

    hotkey = keyboard.HotKey(
        keyboard.HotKey.parse("<cmd>+<shift>+e"),
        lambda: threading.Thread(target=_launch_overlay, daemon=True).start()
    )

    def on_press(key):
        try:
            hotkey.press(listener.canonical(key))
        except Exception:
            pass

    def on_release(key):
        try:
            hotkey.release(listener.canonical(key))
        except Exception:
            pass

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    return listener


def main() -> None:
    global _result_panel

    if "--version" in sys.argv:
        from importlib.metadata import version, PackageNotFoundError
        try:
            print(f"ClippyBox {version('clippybox')}")
        except PackageNotFoundError:
            print("ClippyBox (dev)")
        return

    if "--help" in sys.argv or "-h" in sys.argv:
        print("ClippyBox — Point at anything on your screen and instantly understand it.\n")
        print("Usage: clippybox\n")
        print("Hotkey: Cmd+Shift+E to capture a screen region\n")
        print("Environment variables (set in ~/.config/clippybox/.env):")
        print("  OLLAMA_BASE_URL  Ollama endpoint    (default: http://localhost:11434/v1)")
        print("  MODEL            Vision model       (default: llava)")
        print("  MAX_TOKENS       Response length    (default: 512)")
        print("  API_KEY          API key            (default: ollama)")
        return

    from . import preflight
    preflight.run()

    import webview

    _result_panel = ResultPanel()
    _result_panel.start()

    _setup_hotkey()

    print("ClippyBox is running.")
    print("Press Cmd+Shift+E to capture any region of your screen.")
    print("Press Ctrl+C to quit.")

    webview.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('src/clippybox/__main__.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/clippybox/__main__.py
git commit -m "feat: replace tkinter event loop with pywebview"
```

---

### Task 5: Install, test end-to-end, push

**Files:**
- No new files

- [ ] **Step 1: Install the updated package**

Run: `~/.local/share/clippybox/.venv/bin/pip install --quiet /Users/mattkneale/Documents/Coding/ClippyBox`
Expected: installs without errors

- [ ] **Step 2: Test basic launch**

Run: `clippybox`
Expected: "ClippyBox is running." printed. A hidden pywebview window is created (not visible until first capture).

- [ ] **Step 3: Test capture flow**

Press ⌘⇧E, draw a selection. Expected:
- Panel appears as a frameless Glass Dark window on the right edge
- Thumbnail and dimensions shown in the capture strip
- "Analyzing..." with pulsing dot shown
- Tokens stream in with a blinking cursor
- After completion, cursor disappears, input becomes enabled

- [ ] **Step 4: Test follow-up**

Type a question and press Enter. Expected:
- User message appears
- "Thinking..." with pulsing dot shown
- AI response streams in
- Input re-enables after completion

- [ ] **Step 5: Test re-capture**

Press ⌘⇧E again and draw a new selection. Expected:
- Chat clears, new thumbnail shown, fresh "Analyzing..." appears
- Previous conversation is discarded

- [ ] **Step 6: Push**

```bash
git push
```
