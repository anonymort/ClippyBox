# Homebrew Distribution & First-Run Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ClippyBox installable via `brew install` with guided first-run model setup.

**Architecture:** Restructure into a proper Python package, add preflight checks for Ollama/model, create Homebrew formula in a tap repo.

**Tech Stack:** Python 3.10+, setuptools, Homebrew, Ollama API

**Spec:** `docs/superpowers/specs/2026-04-01-homebrew-onboarding-design.md`

---

## Dependency graph

```
Task 1: Package restructure
  ├── Task 2: Lazy client init + config location  (independent)
  ├── Task 3: Preflight checks                    (independent)
  ├── Task 4: CLI entry point + flags              (depends on 3)
  ├── Task 5: README rewrite                       (independent)
  └── Task 6: Homebrew formula                     (depends on all)
```

Tasks 2, 3, 5 can run in parallel after Task 1. Task 4 after Task 3. Task 6 after all.

---

### Task 1: Package restructure

**Effort: high** — touches every file, changes all imports, highest risk.

**Files:**
- Create: `src/clippybox/__init__.py`
- Create: `src/clippybox/__main__.py` (move logic from `main.py`)
- Create: `src/clippybox/data/system_prompt.txt` (move from `src/system_prompt.txt`)
- Move: `src/ai.py` → `src/clippybox/ai.py`
- Move: `src/panel.py` → `src/clippybox/panel.py`
- Move: `src/overlay_process.py` → `src/clippybox/overlay_process.py`
- Modify: `pyproject.toml` — add `[project.scripts]`, `[tool.setuptools.package-data]`
- Delete: `main.py`, `src/__init__.py`, `src/system_prompt.txt`

- [ ] **Step 1: Create new directory structure**

```bash
mkdir -p src/clippybox/data
```

- [ ] **Step 2: Move files to new locations**

```bash
mv src/ai.py src/clippybox/ai.py
mv src/panel.py src/clippybox/panel.py
mv src/overlay_process.py src/clippybox/overlay_process.py
mv src/system_prompt.txt src/clippybox/data/system_prompt.txt
```

- [ ] **Step 3: Create `src/clippybox/__init__.py`**

```python
"""ClippyBox — Point at anything on your screen and instantly understand it."""
```

- [ ] **Step 4: Create `src/clippybox/__main__.py`**

Move the entry point logic from `main.py`. Key changes:
- `from .panel import ResultPanel` (relative import)
- Overlay invocation: `subprocess.run([sys.executable, "-m", "clippybox.overlay_process", tmp_path])`
- Remove `sys.path.insert` hack
- Extract `if __name__` block into `def main():`
- Keep `if __name__ == "__main__": main()` for `python -m clippybox`

```python
"""ClippyBox entry point."""

import os
import sys
import tempfile
import subprocess
import threading

import tkinter as tk
from PIL import Image

from .panel import ResultPanel


_tk_root: tk.Tk | None = None
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
            _tk_root.after(0, lambda: _open_panel(image))

    except Exception as e:
        print(f"[ClippyBox] Overlay error: {e}")

    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        _overlay_running = False


def _open_panel(image: Image.Image) -> None:
    global _result_panel

    if _result_panel is None or not _result_panel.is_open():
        _result_panel = ResultPanel(_tk_root)

    _result_panel.new_capture(image)


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
    global _tk_root

    _tk_root = tk.Tk()
    _tk_root.withdraw()

    _setup_hotkey()

    print("ClippyBox is running.")
    print("Press Cmd+Shift+E to capture any region of your screen.")
    print("Press Ctrl+C to quit.")

    _tk_root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Fix imports in `panel.py`**

Change line 27:
```python
# Old:
import ai
# New:
from . import ai
```

- [ ] **Step 6: Fix `system_prompt.txt` loading in `ai.py`**

```python
from importlib import resources

def _load_system_prompt() -> str:
    return resources.files("clippybox").joinpath("data", "system_prompt.txt").read_text().strip()
```

- [ ] **Step 7: Update `pyproject.toml`**

```toml
[project]
name = "clippybox"
version = "0.1.0"
description = "Point at anything on your screen and instantly understand it."
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "openai>=1.0.0",
    "Pillow>=10.0.0",
    "pynput>=1.7.6",
    "pyobjc-framework-Cocoa>=10.0",
    "pyobjc-framework-Quartz>=10.0",
]

[project.scripts]
clippybox = "clippybox.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
clippybox = ["data/system_prompt.txt"]
```

- [ ] **Step 8: Delete old files**

```bash
rm main.py src/__init__.py
```

- [ ] **Step 9: Verify it runs**

```bash
cd /Users/mattkneale/Documents/Coding/ClippyBox
python -m clippybox
```

Expected: "ClippyBox is running." (Ctrl+C to quit)

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: restructure into proper Python package"
```

---

### Task 2: Lazy client init + config file location

**Effort: medium** — changes `ai.py` internals only.

**Files:**
- Modify: `src/clippybox/ai.py`

- [ ] **Step 1: Update `_load_dotenv` to search multiple locations**

Lookup order: `~/.config/clippybox/.env` → `./.env` → defaults.

```python
def _load_dotenv() -> None:
    candidates = [
        os.path.expanduser("~/.config/clippybox/.env"),
        os.path.join(os.getcwd(), ".env"),
    ]

    for env_path in candidates:
        if not os.path.exists(env_path):
            continue
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                os.environ.setdefault(key.strip(), value)
        break  # stop after first found
```

- [ ] **Step 2: Make client lazy-initialized**

Replace module-level `client = OpenAI(...)` and connectivity check with:

```python
_load_dotenv()

_base_url   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_model      = os.environ.get("MODEL", "llava")
_max_tokens = int(os.environ.get("MAX_TOKENS", "1024"))

_client: OpenAI | None = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("API_KEY") or "ollama"
        _client = OpenAI(base_url=_base_url, api_key=api_key)
    return _client
```

- [ ] **Step 3: Update `_call_api` to use `_get_client()`**

```python
def _call_api(messages: list) -> str:
    response = _get_client().chat.completions.create(
        model=_model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        max_tokens=_max_tokens,
    )
    content = response.choices[0].message.content
    if content is None:
        return "(No response from model)"
    return content
```

- [ ] **Step 4: Remove the old connectivity check block** (lines 69-79)

Delete the `try: client.models.list()` block entirely — preflight replaces it.

- [ ] **Step 5: Remove `import sys`** (no longer needed after connectivity check removal — unless used elsewhere)

- [ ] **Step 6: Verify it still runs**

```bash
python -m clippybox
```

- [ ] **Step 7: Commit**

```bash
git add src/clippybox/ai.py
git commit -m "refactor: lazy client init and multi-location config loading"
```

---

### Task 3: Preflight checks

**Effort: medium** — new file, straightforward logic.

**Files:**
- Create: `src/clippybox/preflight.py`

- [ ] **Step 1: Create `preflight.py`**

```python
"""First-run checks for Ollama availability and model readiness."""

import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

import urllib.request
import json


def _is_local_ollama(base_url: str) -> bool:
    """Return True if the base URL points at a local Ollama instance."""
    parsed = urlparse(base_url)
    return parsed.hostname in ("localhost", "127.0.0.1") and "11434" in str(parsed.port or "")


def _ollama_api_url(base_url: str) -> str:
    """Derive the native Ollama API base from the OpenAI-compat URL."""
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 11434}"


def run() -> None:
    """Run preflight checks. Exits the process if any check fails."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("MODEL", "llava")

    if not _is_local_ollama(base_url):
        return  # non-Ollama backend; skip checks

    # Check 1: Is Ollama installed?
    if shutil.which("ollama") is None:
        print("Ollama is not installed.\n")
        print("Install with Homebrew:")
        print("  brew install ollama\n")
        print("Or download from https://ollama.com\n")
        print("Then relaunch ClippyBox.")
        sys.exit(1)

    # Check 2: Is Ollama running?
    api_base = _ollama_api_url(base_url)
    try:
        urllib.request.urlopen(f"{api_base}/api/tags", timeout=3)
    except Exception:
        print("Ollama is installed but not running.\n")
        print("Start it with:")
        print("  ollama serve\n")
        print("Or open the Ollama app, then relaunch ClippyBox.")
        sys.exit(1)

    # Check 3: Is the configured model available?
    try:
        resp = urllib.request.urlopen(f"{api_base}/api/tags", timeout=3)
        data = json.loads(resp.read())
        local_models = [m["name"].split(":")[0] for m in data.get("models", [])]
    except Exception:
        return  # can't check; let the API call fail later with a clear error

    if model.split(":")[0] in local_models:
        return  # model is available

    if not sys.stdin.isatty():
        print(f'Model "{model}" is not available locally.\n')
        print("Download it with:")
        print(f"  ollama pull {model}\n")
        print("Then relaunch ClippyBox.")
        sys.exit(1)

    answer = input(f'Model "{model}" is not downloaded. Download now? [Y/n] ')
    if answer.strip().lower() in ("", "y", "yes"):
        try:
            subprocess.run(["ollama", "pull", model], check=True)
        except KeyboardInterrupt:
            print(f"\nDownload paused. Run `ollama pull {model}` to resume.")
            sys.exit(1)
        except subprocess.CalledProcessError:
            print(f"\nDownload failed. Try manually: ollama pull {model}")
            sys.exit(1)
    else:
        print(f"\nRun `ollama pull {model}` when ready, then relaunch ClippyBox.")
        sys.exit(0)
```

- [ ] **Step 2: Commit**

```bash
git add src/clippybox/preflight.py
git commit -m "feat: add preflight checks for Ollama and model availability"
```

---

### Task 4: CLI entry point + flags + preflight integration

**Effort: low** — small additions to `__main__.py`.

**Files:**
- Modify: `src/clippybox/__main__.py`

- [ ] **Step 1: Add `--version`, `--help`, and preflight call to `main()`**

Update the `main()` function:

```python
def main() -> None:
    global _tk_root

    if "--version" in sys.argv:
        print("ClippyBox 0.1.0")
        return

    if "--help" in sys.argv or "-h" in sys.argv:
        print("ClippyBox — Point at anything on your screen and instantly understand it.\n")
        print("Usage: clippybox\n")
        print("Hotkey: Cmd+Shift+E to capture a screen region\n")
        print("Environment variables (set in ~/.config/clippybox/.env):")
        print("  OLLAMA_BASE_URL  Ollama endpoint    (default: http://localhost:11434/v1)")
        print("  MODEL            Vision model       (default: llava)")
        print("  MAX_TOKENS       Response length    (default: 1024)")
        print("  API_KEY          API key            (default: ollama)")
        return

    from . import preflight
    preflight.run()

    _tk_root = tk.Tk()
    _tk_root.withdraw()

    _setup_hotkey()

    print("ClippyBox is running.")
    print("Press Cmd+Shift+E to capture any region of your screen.")
    print("Press Ctrl+C to quit.")

    _tk_root.mainloop()
```

- [ ] **Step 2: Verify flags work**

```bash
python -m clippybox --version
python -m clippybox --help
```

- [ ] **Step 3: Commit**

```bash
git add src/clippybox/__main__.py
git commit -m "feat: add --version, --help flags and preflight integration"
```

---

### Task 5: README rewrite

**Effort: low** — text changes only.

**Files:**
- Modify: `README.md`
- Rename: `.env` → `.env.example`

- [ ] **Step 1: Rename `.env` to `.env.example`**

```bash
mv .env .env.example
echo ".env" >> .gitignore
```

- [ ] **Step 2: Rewrite `README.md`**

Key changes:
- Primary install: `brew tap anonymort/clippybox && brew install clippybox && clippybox`
- Developer install in collapsed `<details>` block: clone, venv, `python -m clippybox`
- Remove all Anthropic API references
- "How it works" diagram: "Claude Vision API" → "local vision model (Ollama)"
- New "Configuration" section: env vars + `~/.config/clippybox/.env` location
- Troubleshooting: add Ollama entries (not installed, not running, model not pulled)
- Keep macOS permissions section
- Note about first install compile time

- [ ] **Step 3: Commit**

```bash
git add README.md .env.example .gitignore
git rm .env 2>/dev/null || true
git commit -m "docs: rewrite README for Homebrew/Ollama, rename .env to .env.example"
```

---

### Task 6: Homebrew formula

**Effort: low** — template file + documentation.

This lives in a separate repo. For now, create the formula file locally in `docs/` as a reference.

**Files:**
- Create: `docs/homebrew/clippybox.rb`

- [ ] **Step 1: Create formula reference**

```ruby
class Clippybox < Formula
  include Language::Python::Virtualenv

  desc "Point at anything on your screen and instantly understand it"
  homepage "https://github.com/anonymort/clippybox"
  url "https://github.com/anonymort/clippybox/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "UPDATE_AFTER_RELEASE"

  depends_on :macos
  depends_on "python@3.12"
  depends_on "python-tk@3.12"

  # Generate resource blocks with: poet -r requirements.txt
  # resource "openai" do ... end
  # (plus all transitive dependencies)

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "ClippyBox", shell_output("#{bin}/clippybox --version")
  end
end
```

- [ ] **Step 2: Commit**

```bash
git add docs/homebrew/clippybox.rb
git commit -m "docs: add Homebrew formula reference"
```
