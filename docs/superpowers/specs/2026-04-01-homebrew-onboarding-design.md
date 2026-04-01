# ClippyBox: Homebrew Distribution & First-Run Onboarding

**Date:** 2026-04-01
**Target user:** Semi-technical Mac user — comfortable with terminal, doesn't want to manage Python environments.
**Goal:** `brew install` + `clippybox` → working app with guided model setup.

---

## 1. Package restructure (prerequisite)

The current layout uses `sys.path.insert` hacks and bare imports (`import ai` in `panel.py`). This breaks when pip-installed into a virtualenv (as Homebrew does). Must restructure into a proper Python package first.

### Current layout

```
clippybox/
├── main.py                  # entry point, sys.path hack
├── src/
│   ├── __init__.py
│   ├── ai.py                # bare "import ai" won't work installed
│   ├── overlay_process.py
│   ├── panel.py
│   └── system_prompt.txt
├── .env
├── pyproject.toml
└── requirements.txt
```

### New layout

```
clippybox/
├── src/
│   └── clippybox/
│       ├── __init__.py
│       ├── __main__.py      # entry point: calls main()
│       ├── ai.py            # uses relative imports
│       ├── overlay_process.py
│       ├── panel.py
│       ├── preflight.py     # new: first-run checks
│       └── data/
│           └── system_prompt.txt
├── .env.example             # template, not loaded at runtime
├── pyproject.toml
└── requirements.txt
```

### Import changes

- All internal imports become relative: `from . import ai`, `from .ai import explain_capture`, etc.
- `panel.py` line 28: `import ai` → `from . import ai`
- `main.py` logic moves into `__main__.py` with `from .panel import ResultPanel`

### pyproject.toml changes

```toml
[project]
name = "clippybox"
version = "0.1.0"
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

[tool.setuptools.package-data]
clippybox = ["data/system_prompt.txt"]
```

### overlay_process.py path resolution

`main.py` currently locates the overlay script via `os.path.dirname(__file__)`. After install, this breaks.

Fix: invoke the overlay as a module — `python -m clippybox.overlay_process` — using `sys.executable` and `-m`. This works regardless of install location.

```python
result = subprocess.run([sys.executable, "-m", "clippybox.overlay_process", tmp_path])
```

### system_prompt.txt path resolution

Currently loaded via `os.path.dirname(__file__)` relative path. After restructure, use `importlib.resources`:

```python
from importlib import resources

def _load_system_prompt() -> str:
    return resources.files("clippybox").joinpath("data", "system_prompt.txt").read_text().strip()
```

---

## 2. Config file location

### Problem

The current `.env` is loaded relative to `ai.py`'s `__file__`, which points inside the Homebrew Cellar after install. Users should not edit files in the Cellar.

### Solution

Config lookup order (first match wins):

1. Real environment variables (always highest priority)
2. `~/.config/clippybox/.env` (user config directory)
3. `./.env` in the current working directory (developer convenience)
4. Built-in defaults (`OLLAMA_BASE_URL=http://localhost:11434/v1`, `MODEL=llava`, `MAX_TOKENS=1024`)

On first run, if `~/.config/clippybox/` doesn't exist, preflight creates it and copies a template `.env.example` with comments explaining each variable.

The `_load_dotenv()` function stays in `ai.py` — no separate config module needed. Preflight reads the two env vars it needs (`OLLAMA_BASE_URL`, `MODEL`) directly.

---

## 3. Lazy client initialization in ai.py

### Problem

`ai.py` currently creates the `OpenAI` client and runs a connectivity check at import time (module level). Since `panel.py` imports `ai` at the top, these side effects fire before preflight can run.

### Solution

Defer client creation to first use:

```python
_client = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _load_dotenv()
        _api_key = os.environ.get("API_KEY") or "ollama"
        _client = OpenAI(base_url=_base_url, api_key=_api_key)
    return _client
```

- `_call_api()` calls `_get_client()` instead of using a module-level `client`
- Remove the module-level connectivity check (lines 71-79) — preflight replaces it
- `_load_dotenv()`, `_base_url`, `_model`, `_max_tokens` can stay module-level since they're side-effect-free reads

---

## 4. Preflight checks (`src/clippybox/preflight.py`)

Called from `main()` in `__main__.py` before tkinter setup. Exits early with actionable messages if anything is wrong.

### Check 1: Is Ollama installed?

```python
if shutil.which("ollama") is None:
    print("Ollama is not installed.\n")
    print("Install with Homebrew:")
    print("  brew install ollama\n")
    print("Or download from https://ollama.com\n")
    print("Then relaunch ClippyBox.")
    sys.exit(1)
```

**Skip condition:** If `OLLAMA_BASE_URL` is set to something other than `localhost:11434`, skip all three Ollama-specific checks — the user is pointing at a remote or non-Ollama backend.

### Check 2: Is Ollama running?

Hit the native Ollama API at `http://localhost:11434/api/tags` (derived by stripping `/v1` from the base URL — the OpenAI-compat suffix).

```python
print("Ollama is installed but not running.\n")
print("Start it with:")
print("  ollama serve\n")
print("Or open the Ollama app, then relaunch ClippyBox.")
sys.exit(1)
```

### Check 3: Is the configured model available?

Parse the JSON response from `/api/tags` to list local model names. If the configured `MODEL` isn't present:

```python
if not sys.stdin.isatty():
    print(f'Model "{model}" is not available locally.\n')
    print(f"Download it with:")
    print(f"  ollama pull {model}\n")
    print("Then relaunch ClippyBox.")
    sys.exit(1)

answer = input(f'Model "{model}" is not downloaded. Download now? [Y/n] ')
if answer.strip().lower() in ("", "y", "yes"):
    subprocess.run(["ollama", "pull", model])
else:
    print(f"\nRun `ollama pull {model}` when ready, then relaunch ClippyBox.")
    sys.exit(0)
```

Design notes:
- No hardcoded size estimate — model sizes vary and change across versions.
- `sys.stdin.isatty()` check — if not interactive, print instructions instead of blocking on input.
- `ollama pull` is resumable — if the user hits Ctrl+C, catch `KeyboardInterrupt` and print "Download paused. Run `ollama pull {model}` to resume."

---

## 5. CLI flags

Homebrew convention expects `--version` at minimum.

`__main__.py` handles two flags before starting the app:

- `--version` → prints `ClippyBox 0.1.0` and exits
- `--help` → prints usage, env vars, hotkey, and exits

No argument parsing library needed — just check `sys.argv`.

---

## 6. Homebrew formula & tap repo

### Tap repo structure

Separate GitHub repo: `shaier/homebrew-clippybox`

```
homebrew-clippybox/
├── Formula/
│   └── clippybox.rb
└── README.md
```

### Formula: `clippybox.rb`

```ruby
class Clippybox < Formula
  include Language::Python::Virtualenv

  desc "Point at anything on your screen and instantly understand it"
  homepage "https://github.com/shaier/clippybox"
  url "https://github.com/shaier/clippybox/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "..."

  depends_on :macos
  depends_on "python@3.12"
  depends_on "python-tk@3.12"

  # Resource blocks for each PyPI dependency
  # Generated with: poet -r requirements.txt
  resource "openai" do ... end
  resource "Pillow" do ... end
  resource "pynput" do ... end
  resource "pyobjc-framework-Cocoa" do ... end
  resource "pyobjc-framework-Quartz" do ... end
  # (plus transitive deps)

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "ClippyBox", shell_output("#{bin}/clippybox --version")
  end
end
```

Design notes:
- **No `depends_on "ollama"`** — would conflict with users who have the Ollama macOS app. Preflight handles detection.
- **`depends_on "python-tk@3.12"`** — Homebrew Python does not include tkinter by default. Without this, the app crashes on launch with `ModuleNotFoundError: No module named '_tkinter'`.
- **Resource blocks** generated with `homebrew-pypi-poet`. pyobjc frameworks may compile from source — this is expected and takes a few minutes on first install.
- **Release workflow:** Tag a release on the main repo → update `url` and `sha256` in the formula. Manual for now, GitHub Action later.

### User experience

```bash
brew tap shaier/clippybox
brew install clippybox    # installs Python, tkinter, deps, clippybox
clippybox                 # first run: preflight prompts for model download
```

---

## 7. README rewrite

### Primary install path

```markdown
## Install

```bash
brew tap shaier/clippybox
brew install clippybox
clippybox
```

First launch will prompt you to download a vision model (~5 min on broadband).
```

### Developer install (collapsed)

```markdown
<details>
<summary>Developer install (from source)</summary>

git clone ... && cd clippybox
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
python -m clippybox

</details>
```

### Other updates

- Remove all Anthropic API references
- "How it works" diagram: "Claude Vision API" → "local vision model (Ollama)"
- New "Configuration" section documenting env vars (`OLLAMA_BASE_URL`, `MODEL`, `API_KEY`, `MAX_TOKENS`) and the `~/.config/clippybox/.env` location
- Troubleshooting: add Ollama-specific entries (not running, model not pulled, permission issues)
- Keep macOS permissions section (Accessibility + Screen Recording)
- Note: "First install may take a few minutes while dependencies compile"

---

## Not in scope

- GitHub Actions for auto-updating the formula (add later)
- `.app` bundle / Homebrew cask (ruled out — too much build complexity)
- Non-macOS support (PyObjC is macOS-only)
- Auto-detecting macOS permissions and prompting (nice-to-have, not blocking)
- Uninstall cleanup of Ollama models (user manages their own Ollama models)

---

## User journey (end-to-end)

```
$ brew tap shaier/clippybox
$ brew install clippybox
  ==> Installing clippybox ...
  ==> Pouring python@3.12, python-tk@3.12 ...
  ==> Installing clippybox dependencies ...     # may compile pyobjc (~2-3 min)
  ==> clippybox 0.1.0 installed

$ clippybox
  Ollama is installed but not running.

  Start it with:
    ollama serve

  Or open the Ollama app, then relaunch ClippyBox.

$ open -a Ollama    # user opens the app
$ clippybox
  Model "llava" is not downloaded. Download now? [Y/n] y
  pulling manifest...
  pulling sha256:...   100%  ████████████  4.7 GB

  ClippyBox is running.
  Press Cmd+Shift+E to capture any region of your screen.
  Press Ctrl+C to quit.
```
