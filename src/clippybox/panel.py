# -*- coding: utf-8 -*-
"""
src/panel.py - Result panel UI.

Displays the AI explanation for a captured screen region and allows the user
to ask follow-up questions in a persistent chat interface.

UI structure (top to bottom):
  - Header bar    : app name + hotkey reminder
  - Capture strip : thumbnail of the captured region + pixel dimensions
  - Chat area     : scrollable conversation history (AI + user turns)
  - Input area    : text box + implicit Enter-to-send behaviour
  - Status line   : "Thinking..." indicator while the API call is in flight

Threading model:
  All API calls run in daemon threads to keep the UI responsive.
  Results are posted back to the tkinter main thread via root.after(0, ...).
"""

import re
import threading
import tkinter as tk
from tkinter import scrolledtext

from PIL import Image, ImageTk

from . import ai


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

PANEL_WIDTH  = 600
PANEL_HEIGHT = 740

# Warm dark palette — easier on the eyes than cold blue-blacks
BG       = "#1c1917"   # Main background (warm near-black)
BG_CHAT  = "#231f1d"   # Chat area (slightly lighter)
BG_INPUT = "#2a2520"   # Input field background
BORDER   = "#3a3530"   # Divider lines

TEXT     = "#e8e0d8"   # Primary text (warm off-white)
TEXT_DIM = "#7a6f67"   # Muted text (placeholders, labels)
TEXT_YOU = "#c4a882"   # "You" label colour (warm tan)
TEXT_AI  = "#a0b8a0"   # "AI" label colour (muted sage)

FONT_BODY  = ("Georgia", 20)             # Serif for AI responses — easy to read
FONT_LABEL = ("Helvetica Neue", 11, "bold")
FONT_INPUT = ("Helvetica Neue", 20)      # Matches what the user types
FONT_SMALL = ("Helvetica Neue", 11)
FONT_MONO  = ("Menlo", 12)               # Code blocks


class ResultPanel:
    """
    Floating panel that shows the AI explanation for a captured region.

    Lifecycle:
      1. Instantiated once by main.py when the first capture completes.
      2. new_capture(image) is called for each subsequent capture — this
         resets the conversation and starts a fresh API call.
      3. The user types follow-up questions in the input box and presses Enter.
      4. is_open() is checked by main.py before reusing an existing panel.

    Args:
        root: The hidden tkinter root window (tk.Tk instance).
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root          = root
        self.current_image = None   # PIL image for the current capture session
        self.history       = []     # Claude conversation history for this session
        self._open         = False

        self._build()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        """Create the top-level window and all child widgets."""
        self.win = tk.Toplevel(self.root)
        self.win.title("ClippyBox")

        # Position panel to the right edge of the primary screen
        sw = self.root.winfo_screenwidth()
        self.win.geometry(f"{PANEL_WIDTH}x{PANEL_HEIGHT}+{sw - PANEL_WIDTH - 24}+60")
        self.win.configure(bg=BG)
        self.win.resizable(True, True)
        self.win.minsize(PANEL_WIDTH, 500)  # Ensure input box is always visible
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._open = True

        self._build_header()
        self._build_capture_strip()
        self._build_chat()
        self._build_input()

    def _build_header(self) -> None:
        """App name on the left, hotkey hint on the right."""
        frame = tk.Frame(self.win, bg=BG, pady=14)
        frame.pack(fill=tk.X, padx=20)

        tk.Label(frame, text="ClippyBox", bg=BG, fg=TEXT,
                 font=("Helvetica Neue", 13, "bold")).pack(side=tk.LEFT)

        tk.Label(frame, text="⌘⇧E to capture", bg=BG, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side=tk.RIGHT)

        tk.Frame(self.win, bg=BORDER, height=1).pack(fill=tk.X)

    def _build_capture_strip(self) -> None:
        """Thumbnail of the captured region and its pixel dimensions."""
        self.strip = tk.Frame(self.win, bg=BG, pady=10)
        self.strip.pack(fill=tk.X, padx=20)

        self.thumb_lbl = tk.Label(self.strip, bg=BG, fg=TEXT_DIM,
                                  text="No capture yet", font=FONT_SMALL)
        self.thumb_lbl.pack(side=tk.LEFT)

        self.info_lbl = tk.Label(self.strip, bg=BG, fg=TEXT_DIM,
                                 text="", font=FONT_SMALL)
        self.info_lbl.pack(side=tk.LEFT, padx=10)

        tk.Frame(self.win, bg=BORDER, height=1).pack(fill=tk.X)

    def _build_chat(self) -> None:
        """Scrollable text widget that holds the conversation history."""
        self.chat = scrolledtext.ScrolledText(
            self.win,
            bg=BG_CHAT, fg=TEXT,
            font=FONT_BODY,
            wrap=tk.WORD,
            state=tk.DISABLED,      # Read-only; we enable it briefly to insert text
            relief=tk.FLAT, bd=0,
            padx=20, pady=16,
            spacing1=2, spacing3=6,
            insertbackground=TEXT,
            selectbackground="#3a3020",
        )
        self.chat.pack(fill=tk.BOTH, expand=True)
        self.chat.configure(height=18)  # ~18 lines visible minimum

        # Named text tags for styled runs within the chat widget
        self.chat.tag_configure("you_label",   foreground=TEXT_YOU, font=FONT_LABEL)
        self.chat.tag_configure("ai_label",    foreground=TEXT_AI,  font=FONT_LABEL)
        self.chat.tag_configure("you_body",    foreground=TEXT,      font=FONT_INPUT)
        self.chat.tag_configure("ai_body",     foreground=TEXT,      font=FONT_BODY)
        self.chat.tag_configure("thinking",    foreground=TEXT_DIM,  font=("Helvetica Neue", 13, "italic"))
        self.chat.tag_configure("code",        foreground="#b8d4b8", font=FONT_MONO,
                                background="#1a1f1a")
        # Markdown formatting tags
        self.chat.tag_configure("h1",          foreground=TEXT,      font=("Helvetica Neue", 22, "bold"))
        self.chat.tag_configure("h2",          foreground=TEXT,      font=("Helvetica Neue", 18, "bold"))
        self.chat.tag_configure("h3",          foreground=TEXT,      font=("Helvetica Neue", 15, "bold"))
        self.chat.tag_configure("bold",        foreground=TEXT,      font=("Georgia", 20, "bold"))
        self.chat.tag_configure("italic",      foreground=TEXT,      font=("Georgia", 20, "italic"))
        self.chat.tag_configure("bold_italic", foreground=TEXT,      font=("Georgia", 20, "bold", "italic"))
        self.chat.tag_configure("code_inline", foreground="#b8d4b8", font=FONT_MONO,
                                background="#1a1f1a")

        tk.Frame(self.win, bg=BORDER, height=1).pack(fill=tk.X)

    def _build_input(self) -> None:
        """
        Multi-line input box with placeholder text.

        Enter sends the message; Shift+Enter inserts a newline.
        The send button is implicit (Enter key) to keep the UI clean.
        """
        container = tk.Frame(self.win, bg=BG_INPUT)
        container.pack(fill=tk.X)

        self.input = tk.Text(
            container,
            bg=BG_INPUT, fg=TEXT,
            font=FONT_INPUT,
            height=3,
            wrap=tk.WORD,
            relief=tk.FLAT, bd=0,
            padx=16, pady=12,
            insertbackground=TEXT,
        )
        self.input.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.input.insert("1.0", "Ask a follow-up…")
        self.input.configure(fg=TEXT_DIM)

        self.input.bind("<FocusIn>",  self._on_focus_in)
        self.input.bind("<FocusOut>", self._on_focus_out)
        self.input.bind("<Return>",   self._on_enter)

        # Status line (e.g. "Thinking…") sits below the input
        self.status_var = tk.StringVar(value="")
        tk.Label(self.win, textvariable=self.status_var,
                 bg=BG, fg=TEXT_DIM, font=FONT_SMALL,
                 anchor="w", pady=5).pack(fill=tk.X, padx=20)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def new_capture(self, image: Image.Image) -> None:
        """
        Start a new capture session.

        Resets conversation history, updates the thumbnail, clears the chat,
        and kicks off the initial explanation API call in a background thread.

        Args:
            image: The cropped PIL image from the overlay selection.
        """
        self.current_image = image
        self.history       = []

        self._update_thumb(image)
        self._clear_chat()
        self._append("AI", "Analyzing…", "thinking")

        self.win.deiconify()
        self.win.lift()

        threading.Thread(target=self._explain, daemon=True).start()

    def is_open(self) -> bool:
        """
        Return True if the panel window still exists and is open.

        Used by main.py to decide whether to reuse or recreate the panel.
        """
        try:
            return self._open and self.win.winfo_exists()
        except Exception:
            return False

    # -----------------------------------------------------------------------
    # API calls (run in background threads)
    # -----------------------------------------------------------------------

    def _explain(self) -> None:
        """
        Fetch the initial explanation from Claude for the current capture.

        Runs in a daemon thread. Posts the result back to the main thread
        via root.after() to safely update the tkinter widgets.
        """
        try:
            self._set_status("Thinking…")
            response, self.history = ai.explain_capture(self.current_image, [])
            self.root.after(0, lambda: self._replace_thinking(response))
        except Exception as e:
            self.root.after(0, lambda: self._replace_thinking(f"Error: {e}"))
        finally:
            self._set_status("")

    def _do_followup(self, question: str) -> None:
        """
        Send a follow-up question to Claude and append the response.

        Runs in a daemon thread. Always re-sends the original image so
        Claude has full visual context throughout the conversation.

        Args:
            question: The user's question as a plain string.
        """
        try:
            self._set_status("Thinking…")
            response, self.history = ai.ask_followup(
                self.current_image, question, self.history
            )
            self.root.after(0, lambda: self._replace_thinking(response))
        except Exception as e:
            self.root.after(0, lambda: self._replace_thinking(f"Error: {e}"))
        finally:
            self._set_status("")

    # -----------------------------------------------------------------------
    # Chat widget helpers
    # -----------------------------------------------------------------------

    def _append(self, role: str, text: str, body_tag: str) -> None:
        """
        Append a labelled message block to the chat widget.

        Each block consists of a small role label ("AI" or "You") on its own
        line, followed by the message body with the given text tag applied.

        Args:
            role:     Display name for the sender, e.g. "AI" or "You".
            text:     Message content.
            body_tag: tkinter text tag name for styling the body text.
        """
        self.chat.configure(state=tk.NORMAL)

        # Add spacing between messages
        if self.chat.get("1.0", tk.END).strip():
            self.chat.insert(tk.END, "\n\n")

        label_tag = "ai_label" if role == "AI" else "you_label"
        self.chat.insert(tk.END, f"{role}\n", label_tag)
        self.chat.insert(tk.END, text, body_tag)

        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _replace_thinking(self, new_text: str) -> None:
        """
        Replace the "Thinking…" or "Analyzing…" placeholder with the real response,
        rendered with markdown formatting.

        Searches backwards for the placeholder and deletes from that point to end,
        then inserts the markdown-formatted response.

        Args:
            new_text: The markdown response text to substitute in.
        """
        self.chat.configure(state=tk.NORMAL)
        content = self.chat.get("1.0", tk.END)

        for placeholder in ("Thinking…", "Analyzing…"):
            idx = content.rfind(placeholder)
            if idx == -1:
                continue
            line = content[:idx].count("\n") + 1
            col  = idx - content[:idx].rfind("\n") - 1
            # Delete from placeholder position to end, then insert markdown
            self.chat.delete(f"{line}.{col}", tk.END)
            self._insert_markdown(new_text)
            break
        else:
            self._insert_markdown(new_text)

        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _insert_markdown(self, text: str) -> None:
        """
        Insert markdown-formatted text into the chat widget.

        Handles: headers (h1–h3), fenced code blocks, bullet and numbered lists,
        and inline formatting (**bold**, *italic*, ***bold italic***, `code`).

        Assumes the chat widget is already in NORMAL (editable) state.

        Args:
            text: Markdown string to render.
        """
        lines = text.split("\n")
        in_code_block = False
        code_lines: list[str] = []

        for line in lines:
            # --- Fenced code blocks ---
            if line.startswith("```"):
                if not in_code_block:
                    in_code_block = True
                    code_lines = []
                else:
                    in_code_block = False
                    self.chat.insert(tk.END, "\n".join(code_lines) + "\n", "code")
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            # --- Block-level elements ---
            if line.startswith("### "):
                self._insert_inline(line[4:], "h3")
                self.chat.insert(tk.END, "\n")
            elif line.startswith("## "):
                self._insert_inline(line[3:], "h2")
                self.chat.insert(tk.END, "\n")
            elif line.startswith("# "):
                self._insert_inline(line[2:], "h1")
                self.chat.insert(tk.END, "\n")
            elif re.match(r"^[-*]\s", line):
                self.chat.insert(tk.END, "  • ", "ai_body")
                self._insert_inline(line[2:], "ai_body")
                self.chat.insert(tk.END, "\n")
            elif re.match(r"^\d+\.\s", line):
                m = re.match(r"^(\d+\.\s)", line)
                self.chat.insert(tk.END, "  " + m.group(1), "ai_body")
                self._insert_inline(line[m.end():], "ai_body")
                self.chat.insert(tk.END, "\n")
            elif line == "":
                self.chat.insert(tk.END, "\n")
            else:
                self._insert_inline(line, "ai_body")
                self.chat.insert(tk.END, "\n")

    def _insert_inline(self, text: str, base_tag: str) -> None:
        """
        Insert a single line of text with inline markdown formatting applied.

        Recognises ***bold italic***, **bold**, *italic*, and `inline code`.
        Unstyled spans use base_tag.

        Assumes the chat widget is already in NORMAL state.

        Args:
            text:     The line content (no leading block markers).
            base_tag: Tag to apply to plain text spans.
        """
        pattern = r"(\*\*\*[^*]+?\*\*\*|\*\*[^*]+?\*\*|\*[^*]+?\*|`[^`]+?`)"
        for part in re.split(pattern, text):
            if not part:
                continue
            if part.startswith("***") and part.endswith("***"):
                self.chat.insert(tk.END, part[3:-3], "bold_italic")
            elif part.startswith("**") and part.endswith("**"):
                self.chat.insert(tk.END, part[2:-2], "bold")
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                self.chat.insert(tk.END, part[1:-1], "italic")
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                self.chat.insert(tk.END, part[1:-1], "code_inline")
            else:
                self.chat.insert(tk.END, part, base_tag)

    def _clear_chat(self) -> None:
        """Delete all content from the chat widget."""
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)

    def _update_thumb(self, image: Image.Image) -> None:
        """
        Update the thumbnail strip with the new capture.

        Creates a 72x54 thumbnail for display and updates the dimension label.
        Keeps a reference to the PhotoImage on the label to prevent garbage
        collection (tkinter does not hold its own reference).

        Args:
            image: The full captured PIL image.
        """
        try:
            thumb = image.copy()
            thumb.thumbnail((72, 54), Image.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            self.thumb_lbl.configure(image=photo, text="")
            self.thumb_lbl.image = photo  # Prevent GC
            w, h = image.size
            self.info_lbl.configure(text=f"{w}×{h}px")
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Input widget helpers
    # -----------------------------------------------------------------------

    def _send(self) -> None:
        """
        Read the input box, append the question to the chat, and fire the API call.

        Does nothing if the input is empty or no image has been captured yet.
        """
        question = self._get_input()
        if not question or not self.current_image:
            return

        self._clear_input()
        self._append("You", question, "you_body")
        self._append("AI", "Thinking…", "thinking")

        threading.Thread(
            target=self._do_followup,
            args=(question,),
            daemon=True,
        ).start()

    def _get_input(self) -> str:
        """
        Return the current input box text, stripped of whitespace.

        Returns an empty string if the box contains only the placeholder text.
        """
        text = self.input.get("1.0", tk.END).strip()
        return "" if text == "Ask a follow-up…" else text

    def _clear_input(self) -> None:
        """Reset the input box to its placeholder state."""
        self.input.delete("1.0", tk.END)
        self.input.insert("1.0", "Ask a follow-up…")
        self.input.configure(fg=TEXT_DIM)

    def _set_status(self, message: str) -> None:
        """
        Update the status line beneath the input box.

        Always scheduled on the main thread via root.after() so it is safe
        to call from background threads.

        Args:
            message: Text to display, e.g. "Thinking…" or "" to clear.
        """
        self.root.after(0, lambda: self.status_var.set(message))

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------

    def _on_enter(self, event: tk.Event) -> str | None:
        """Send on Enter; allow Shift+Enter to insert a newline."""
        if not (event.state & 0x1):  # Shift not held
            self._send()
            return "break"           # Prevent the default newline insertion
        return None

    def _on_focus_in(self, _: tk.Event) -> None:
        """Clear the placeholder text when the input gains focus."""
        if self.input.get("1.0", tk.END).strip() == "Ask a follow-up…":
            self.input.delete("1.0", tk.END)
            self.input.configure(fg=TEXT)

    def _on_focus_out(self, _: tk.Event) -> None:
        """Restore the placeholder text when the input loses focus while empty."""
        if not self.input.get("1.0", tk.END).strip():
            self.input.insert("1.0", "Ask a follow-up…")
            self.input.configure(fg=TEXT_DIM)

    def _on_close(self) -> None:
        """Handle the window close button — mark panel as closed and destroy."""
        self._open = False
        try:
            self.win.destroy()
        except Exception:
            pass