"""
src/clippybox/ai.py - AI backend integration (Ollama / OpenAI-compatible).

Uses the OpenAI Python library pointed at a local Ollama instance by default,
so any open-source vision model (llava, moondream, minicpm-v, …) can be used
without an API key or cloud dependency.

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
import os

from openai import OpenAI


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
_max_tokens = int(os.environ.get("MAX_TOKENS", "1024"))

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        # api_key must be non-empty for the OpenAI client; Ollama ignores the value.
        # Real keys are needed for hosted OpenAI-compatible endpoints (LM Studio, vLLM, etc).
        api_key = os.environ.get("API_KEY") or "ollama"
        _client = OpenAI(base_url=_base_url, api_key=api_key)
    return _client


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

def _image_to_base64(image) -> str:
    """
    Encode a PIL image as a base64 PNG data-URI string.

    PNG is used (over JPEG) for lossless quality, which matters when the
    captured region contains code, error messages, or small text.

    Args:
        image: A PIL.Image.Image instance.

    Returns:
        A data URI string: "data:image/png;base64,<data>".
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{data}"


def _build_text_message(text: str) -> dict:
    """
    Build an OpenAI-format user message containing only text (no image).

    Used to store conversation turns in history without duplicating the base64
    image payload, which would overflow local model context on follow-ups.

    Args:
        text: The user's message text.

    Returns:
        A dict in the OpenAI messages API format.
    """
    return {"role": "user", "content": text}


def _build_image_message(image, text: str) -> dict:
    """
    Build an OpenAI-format user message containing an image and a text prompt.

    Args:
        image: A PIL.Image.Image instance to include in the message.
        text:  The accompanying text prompt.

    Returns:
        A dict in the OpenAI messages API format.
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


def _call_api(messages: list) -> str:
    """
    Send a list of messages to the configured model and return the response.

    Args:
        messages: Full conversation history in OpenAI messages API format.

    Returns:
        The assistant's response as a plain string.

    Raises:
        openai.OpenAIError: On any API-level error.
    """
    response = _get_client().chat.completions.create(
        model=_model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        max_tokens=_max_tokens,
    )
    content = response.choices[0].message.content
    # Some models return None content (e.g. on refusal or backend quirk).
    if content is None:
        return "(No response from model)"
    return content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain_capture(image, history: list) -> tuple[str, list]:
    """
    Send a newly captured screenshot to the model and return an explanation.

    Args:
        image:   PIL.Image.Image — the cropped screen region to explain.
        history: Should be an empty list for a new session.

    Returns:
        A (response_text, updated_history) tuple. Pass updated_history back
        to subsequent ask_followup() calls to maintain context.
    """
    prompt = "Please explain what I'm looking at in this screenshot."
    api_message = _build_image_message(image, prompt)
    response_text = _call_api([api_message])

    # Store text-only in history so follow-ups don't carry a duplicate image.
    updated_history = [
        _build_text_message(prompt),
        {"role": "assistant", "content": response_text},
    ]
    return response_text, updated_history


def ask_followup(image, question: str, history: list) -> tuple[str, list]:
    """
    Send a follow-up question about the current capture.

    The image is included only in the current turn so the model has full visual
    context without duplicating the base64 payload across every history entry.
    History is stored as text-only to stay within local model context limits.

    Args:
        image:    PIL.Image.Image — the original captured region.
        question: The user's follow-up question as a plain string.
        history:  The conversation history returned by the previous call.

    Returns:
        A (response_text, updated_history) tuple.
    """
    # Send the image with the current question, but keep history image-free.
    api_message = _build_image_message(image, question)
    messages = history + [api_message]
    response_text = _call_api(messages)

    # Store text-only for this turn so future calls don't accumulate images.
    updated_history = history + [
        _build_text_message(question),
        {"role": "assistant", "content": response_text},
    ]
    return response_text, updated_history
