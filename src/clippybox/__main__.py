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
