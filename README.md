# ClippyBox

<video src="https://github.com/user-attachments/assets/65a4884c-1b71-4f41-8040-f11def6c3b34" autoplay loop muted playsinline width="700"></video>

> Press ⌘⇧E, draw a box around anything on your screen, get an instant AI explanation.

Works everywhere — your IDE, browser, terminal, PDF viewer, Figma, anywhere. No copy-pasting, no context switching, no prompt writing.

**Requires macOS and an Anthropic API key.**

---

## Install

### 1. Clone the repo

```bash
git clone https://github.com/shaier/clippybox
cd clippybox
```

### 2. Install uv (recommended)

uv is a fast Python package manager. Skip this step if you already have it.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal after installing so the `uv` command is available.

### 3. Create a virtual environment and install dependencies

**With uv:**
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

**With pip:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Get an Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com) and sign up or log in
2. Navigate to **API Keys** and click **Create Key**
3. Go to **Billing** and add credits (a few dollars is plenty for extensive use)

Theres an `.env` file in the project root. Replace `sk-ant-...` with your actual key. No quotes needed around the value.

### 5. Run

```bash
python main.py
```

You should see:
```
ClippyBox is running.
Press Cmd+Shift+E to capture any region of your screen.
```

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
       └─ src/overlay_process.py launched as subprocess
            └─ screencapture takes a screenshot (before overlay appears)
            └─ PyObjC renders a borderless fullscreen overlay
            └─ user draws a selection box
            └─ selection is cropped and saved to a temp PNG file
       └─ main.py reads the temp file
            └─ src/ai.py sends image to Claude Vision API
            └─ src/panel.py displays the response (tkinter)
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
├── main.py                  # Entry point — hotkey listener + app wiring
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Project metadata (for uv / pip)
├── .env                     # Your API key (never commit this)
└── src/
    ├── __init__.py
    ├── ai.py                # Claude API calls + conversation history
    ├── overlay_process.py   # macOS selection overlay (PyObjC subprocess)
    └── panel.py             # Result panel UI (tkinter)
```

---

## Troubleshooting

**Nothing happens when I press ⌘⇧E**
→ Grant Accessibility permission (see above). The message "This process is not trusted" in the terminal confirms this is the issue.

**The overlay is black / I can't see my screen**
→ Grant Screen Recording permission (see above).

**`API key` or authentication error**
→ Open `.env` and confirm your key starts with `sk-ant-` with no surrounding quotes or extra characters.

**The panel doesn't appear after drawing a box**
→ Make sure you draw a selection larger than ~10×10px. Tiny accidental clicks are ignored.

---

## License

MIT
