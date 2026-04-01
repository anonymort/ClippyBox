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


if __name__ == "__main__":
    main()
