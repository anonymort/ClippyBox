"""
ClippyBox - Point at anything on your screen and instantly understand it.

Entry point. Responsibilities:
  - Register the global hotkey (Cmd+Shift+E)
  - Launch the selection overlay as a subprocess when triggered
  - Load the captured image and hand it to the result panel
  - Keep the tkinter main loop alive for the result panel UI

Architecture note:
  The overlay (src/overlay_process.py) runs as a separate subprocess because
  PyObjC requires the main thread and conflicts with tkinter's main loop.
  Communication happens via a temp PNG file on disk.
"""

import os
import sys
import tempfile
import subprocess
import threading

import tkinter as tk
from PIL import Image
from pynput import keyboard

# Add src/ to the path so we can import from it cleanly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from panel import ResultPanel


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_tk_root: tk.Tk | None = None
_result_panel: ResultPanel | None = None
_overlay_running: bool = False  # Guard against launching multiple overlays at once


# ---------------------------------------------------------------------------
# Overlay lifecycle
# ---------------------------------------------------------------------------

def _launch_overlay() -> None:
    """
    Launch the selection overlay as a subprocess and handle the result.

    Runs in a background thread so the hotkey listener is never blocked.
    The overlay writes the cropped PNG to a temp file on success, or exits
    with a non-zero return code if the user cancels (Esc).
    """
    global _overlay_running

    if _overlay_running:
        return  # Ignore hotkey if overlay is already open
    _overlay_running = True

    # Create a temp file for the overlay to write the cropped image into
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    tmp_path = tmp.name

    try:
        python = sys.executable
        script = os.path.join(os.path.dirname(__file__), "src", "overlay_process.py")
        result = subprocess.run([python, script, tmp_path])

        # A valid capture means: clean exit + non-empty file
        captured = (
            result.returncode == 0
            and os.path.exists(tmp_path)
            and os.path.getsize(tmp_path) > 0
        )

        if captured:
            image = Image.open(tmp_path)
            image.load()
            # Hand off to the panel on the tkinter main thread
            _tk_root.after(0, lambda: _open_panel(image))

    except Exception as e:
        print(f"[ClippyBox] Overlay error: {e}")

    finally:
        # Always clean up the temp file
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        _overlay_running = False


def _open_panel(image: Image.Image) -> None:
    """
    Open (or reuse) the result panel and start a new capture session.

    Always called on the tkinter main thread via root.after().

    Args:
        image: The cropped PIL image from the overlay selection.
    """
    global _result_panel

    if _result_panel is None or not _result_panel.is_open():
        _result_panel = ResultPanel(_tk_root)

    _result_panel.new_capture(image)


# ---------------------------------------------------------------------------
# Hotkey setup
# ---------------------------------------------------------------------------

def _setup_hotkey() -> keyboard.Listener:
    """
    Register the global hotkey (Cmd+Shift+E) using pynput.

    The hotkey triggers _launch_overlay in a daemon thread so the listener
    thread is never blocked waiting for the overlay subprocess.

    Returns:
        The running keyboard.Listener instance.
    """
    hotkey = keyboard.HotKey(
        keyboard.HotKey.parse("<cmd>+<shift>+e"),
        lambda: threading.Thread(target=_launch_overlay, daemon=True).start()
    )

    def on_press(key: keyboard.Key) -> None:
        try:
            hotkey.press(listener.canonical(key))
        except Exception:
            pass

    def on_release(key: keyboard.Key) -> None:
        try:
            hotkey.release(listener.canonical(key))
        except Exception:
            pass

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    return listener


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Hidden root window — required to anchor tkinter even though it's invisible.
    # The result panel (ResultPanel) creates its own Toplevel attached to this root.
    _tk_root = tk.Tk()
    _tk_root.withdraw()

    listener = _setup_hotkey()

    print("ClippyBox is running.")
    print("Press Cmd+Shift+E to capture any region of your screen.")
    print("Press Ctrl+C to quit.")

    _tk_root.mainloop()