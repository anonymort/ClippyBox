# ClippyBox

<video src="https://github.com/user-attachments/assets/65a4884c-1b71-4f41-8040-f11def6c3b34" autoplay loop muted playsinline width="700"></video>

> Press ⌘⇧E, draw a box around anything on your screen, get an instant AI explanation.

Works everywhere — your IDE, browser, terminal, PDF viewer, Figma, anywhere. No copy-pasting, no context switching, no prompt writing.

**Requires macOS and Ollama.**

---

## Install

```bash
brew tap anonymort/clippybox
brew install clippybox
clippybox
```

First install may take a few minutes while pyobjc dependencies compile.
First launch will prompt you to download a vision model if one isn't available locally.

<details>
<summary>Developer install (from source)</summary>

```bash
git clone https://github.com/anonymort/clippybox
cd clippybox
uv venv
source .venv/bin/activate
uv pip install -e .
python -m clippybox
```

</details>

---

## macOS permissions (first run only)

macOS requires two permissions. It will usually prompt you automatically,
but if the hotkey or screenshot isn't working, grant them manually:

**Accessibility** — needed for the global hotkey:
> System Settings → Privacy & Security → Accessibility → add your Terminal app (or iTerm2, VS Code, etc.)

**Screen Recording** — needed for the screenshot:
> System Settings → Privacy & Security → Screen Recording → add your Terminal app

After granting either permission, quit and restart ClippyBox.

---

## How to use

1. Press **⌘⇧E** from any app
2. Your screen dims slightly — click and drag to draw a box around anything
3. Release the mouse — the explanation panel appears on the right
4. Read the explanation, then ask follow-up questions in the input box
5. Press **Enter** to send a follow-up, **Shift+Enter** for a new line
6. Press **⌘⇧E** again to capture something new

---

## How it works

```
⌘⇧E pressed anywhere
  └─ pynput global hotkey listener (background thread)
       └─ src/clippybox/overlay_process.py launched as subprocess
            └─ screencapture takes a screenshot (before overlay appears)
            └─ PyObjC renders a borderless fullscreen overlay
            └─ user draws a selection box
            └─ selection is cropped and saved to a temp PNG file
       └─ src/clippybox/__main__.py reads the temp file
            └─ src/clippybox/ai.py sends image to local vision model via Ollama
            └─ src/clippybox/panel.py displays the response (tkinter)
            └─ follow-up questions re-send image + conversation history
```

**Why a subprocess for the overlay?**
PyObjC requires the main thread for all window operations. tkinter (used for
the result panel) also wants the main thread. Running the overlay as a
separate process sidesteps this conflict entirely — the two never share a thread.

---

## Project structure

```
clippybox/
├── pyproject.toml           # Project metadata and entry point
├── requirements.txt         # Python dependencies
├── .env.example             # Config template — copy to ~/.config/clippybox/.env
└── src/
    └── clippybox/
        ├── __init__.py
        ├── __main__.py      # Entry point — hotkey listener + app wiring
        ├── preflight.py     # First-run Ollama and model checks
        ├── ai.py            # Ollama API calls + conversation history
        ├── overlay_process.py  # macOS selection overlay (PyObjC subprocess)
        ├── panel.py         # Result panel UI (tkinter)
        └── data/
            └── system_prompt.txt
```

---

## Configuration

ClippyBox reads config from (first match wins):

1. Real environment variables
2. `~/.config/clippybox/.env`
3. `./.env` in the current working directory

Copy `.env.example` to get started:

```bash
mkdir -p ~/.config/clippybox
cp .env.example ~/.config/clippybox/.env
```

| Variable          | Default                          | Description                                      |
|-------------------|----------------------------------|--------------------------------------------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1`      | Ollama (or any OpenAI-compatible) endpoint       |
| `MODEL`           | `llava`                          | Vision model to use (must be pulled in Ollama)   |
| `MAX_TOKENS`      | `1024`                           | Maximum response length                          |
| `API_KEY`         | `ollama`                         | API key — only needed for hosted endpoints       |

To use a different model:

```bash
ollama pull llava:13b
# In ~/.config/clippybox/.env:
MODEL=llava:13b
```

---

## Troubleshooting

**Nothing happens when I press ⌘⇧E**
→ Grant Accessibility permission (see above). The message "This process is not trusted" in the terminal confirms this is the issue.

**The overlay is black / I can't see my screen**
→ Grant Screen Recording permission (see above).

**"Ollama is not installed"**
→ Install Ollama: `brew install ollama` or download from [ollama.com](https://ollama.com).

**"Ollama is installed but not running"**
→ Start Ollama: run `ollama serve` in a separate terminal, or open the Ollama app.

**"Model is not downloaded"**
→ Pull the model: `ollama pull llava`. ClippyBox will also offer to do this automatically on first run.

**The panel doesn't appear after drawing a box**
→ Make sure you draw a selection larger than ~10×10px. Tiny accidental clicks are ignored.

---

## License

MIT
