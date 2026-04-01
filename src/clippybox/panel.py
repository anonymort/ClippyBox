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
      start()            — create the window (call once from main thread)
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
        except Exception as e:
            print(f"[ClippyBox] JS eval failed: {e}")

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

        self._loaded.wait(timeout=10)
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

    def _make_token_callback(self):
        """Create a token callback that calls startStreaming() on the first token."""
        started = [False]

        def on_token(token: str) -> None:
            if not started[0]:
                started[0] = True
                self._eval_js("startStreaming()")
            self._on_token(token)

        return on_token

    def _explain(self) -> None:
        try:
            response, self.history = ai.explain_capture(
                self.current_image, [], on_token=self._make_token_callback()
            )
        except Exception as e:
            self._eval_js(f"showError({json.dumps(str(e))})")
        finally:
            self._eval_js("endStreaming()")

    def _do_followup(self, question: str) -> None:
        try:
            response, self.history = ai.ask_followup(
                self.current_image, question, self.history,
                on_token=self._make_token_callback(),
            )
        except Exception as e:
            self._eval_js(f"showError({json.dumps(str(e))})")
        finally:
            self._eval_js("endStreaming()")
