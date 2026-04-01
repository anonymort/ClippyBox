"""
src/clippybox/ai.py - AI backend integration (Ollama / OpenAI-compatible).

Calls the OpenAI-compatible chat completions endpoint using stdlib only
(urllib.request + json). No third-party HTTP or SDK dependencies needed.

Configuration (via .env or environment variables):
  OLLAMA_BASE_URL   Base URL for the OpenAI-compatible endpoint.
                    Default: http://localhost:11434/v1
  MODEL             Model name to request. Must support vision.
                    Default: llava

Conversation model:
  Each capture session maintains its own message history. History is stored
  and managed by the caller (ResultPanel) and passed in on every call.
  The model itself is stateless — the full history is re-sent each request.
"""

import base64
import io
import json
import os
import urllib.request


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """
    Load key=value pairs from a .env file into os.environ.

    Searches in order: ~/.config/clippybox/.env, then ./.env.
    Stops after the first file found. Skips blank lines and comments.
    Does not overwrite existing env vars.
    """
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
                # Strip matching surrounding quotes so MODEL="llava" → llava.
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                os.environ.setdefault(key.strip(), value)
        break  # stop after first found


_load_dotenv()

_base_url   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_model      = os.environ.get("MODEL", "llava")
_max_tokens = int(os.environ.get("MAX_TOKENS", "512"))
_api_key    = os.environ.get("API_KEY") or "ollama"


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Load the system prompt from the package data directory."""
    from importlib import resources
    return resources.files("clippybox").joinpath("data", "system_prompt.txt").read_text().strip()


SYSTEM_PROMPT = _load_system_prompt()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAX_EDGE = 768  # Vision models internally resize; larger images are wasted compute.


def _prepare_image(image) -> "Image.Image":
    """
    Downscale to at most _MAX_EDGE on the longest side.

    Returns a new image (or the original if already small enough).
    """
    from PIL import Image as _Img

    w, h = image.size
    if max(w, h) <= _MAX_EDGE:
        return image
    ratio = _MAX_EDGE / max(w, h)
    return image.resize((int(w * ratio), int(h * ratio)), _Img.LANCZOS)


def _image_to_base64(image) -> str:
    """
    Downscale and JPEG-encode a PIL image for the vision API.

    JPEG is ~5-10x smaller than PNG for screenshots, which reduces
    base64 encoding time and payload size. Quality 85 preserves text
    legibility while keeping the payload compact.
    """
    image = _prepare_image(image)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    data = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{data}"


def _build_text_message(text: str) -> dict:
    """
    Build an OpenAI-format user message containing only text (no image).

    Used to store conversation turns in history without duplicating the base64
    image payload, which would overflow local model context on follow-ups.
    """
    return {"role": "user", "content": text}


def _build_image_message(image, text: str) -> dict:
    """
    Build an OpenAI-format user message containing an image and a text prompt.
    """
    return {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": _image_to_base64(image)},
            },
            {
                "type": "text",
                "text": text,
            },
        ],
    }


def _call_api(messages: list, on_token=None) -> str:
    """
    POST to the chat completions endpoint.

    If *on_token* is provided, streams the response and calls
    on_token(delta_str) for each chunk. Returns the full concatenated text.
    If *on_token* is None, uses a non-streaming request and returns the
    complete response at once.
    """
    stream = on_token is not None
    payload = json.dumps({
        "model": _model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "max_tokens": _max_tokens,
        "stream": stream,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{_base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key}",
        },
    )

    if not stream:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        return content if content else "(No response from model)"

    # Streaming: read SSE lines, extract deltas
    parts: list[str] = []
    with urllib.request.urlopen(req) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    parts.append(delta)
                    on_token(delta)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

    return "".join(parts) or "(No response from model)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain_capture(image, history: list, on_token=None) -> tuple[str, list]:
    """
    Send a newly captured screenshot to the model and return an explanation.

    Args:
        image:    PIL.Image.Image — the cropped screen region to explain.
        history:  Should be an empty list for a new session.
        on_token: Optional callback(str) invoked with each streamed token.

    Returns:
        A (response_text, updated_history) tuple. Pass updated_history back
        to subsequent ask_followup() calls to maintain context.
    """
    prompt = "Please explain what I'm looking at in this screenshot."
    api_message = _build_image_message(image, prompt)
    response_text = _call_api([api_message], on_token=on_token)

    # Store text-only in history so follow-ups don't carry a duplicate image.
    updated_history = [
        _build_text_message(prompt),
        {"role": "assistant", "content": response_text},
    ]
    return response_text, updated_history


def ask_followup(image, question: str, history: list, on_token=None) -> tuple[str, list]:
    """
    Send a follow-up question about the current capture.

    The image is included only in the current turn so the model has full visual
    context without duplicating the base64 payload across every history entry.
    History is stored as text-only to stay within local model context limits.
    """
    api_message = _build_image_message(image, question)
    messages = history + [api_message]
    response_text = _call_api(messages, on_token=on_token)

    updated_history = history + [
        _build_text_message(question),
        {"role": "assistant", "content": response_text},
    ]
    return response_text, updated_history
