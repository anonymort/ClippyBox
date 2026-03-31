"""
src/ai.py - Claude API integration.

Responsibilities:
  - Load the Anthropic API key from the environment or a .env file
  - Encode PIL images as base64 for the vision API
  - Send the initial explanation request for a new capture
  - Send follow-up questions within an existing capture session

Conversation model:
  Each capture session maintains its own message history. History is stored
  and managed by the caller (ResultPanel) and passed in on every call.
  Claude itself is stateless — the full history is re-sent with each request.
"""

import base64
import io
import os

from anthropic import Anthropic


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """
    Load key=value pairs from a .env file into os.environ.

    Looks for .env two levels up from this file (i.e. the project root).
    Skips blank lines and comments. Does not overwrite existing env vars.
    """
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_path = os.path.normpath(env_path)

    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()
client = Anthropic()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """
    Load the system prompt from src/system_prompt.txt.

    Keeping the prompt in a plain text file makes it easy to customise
    without touching any Python code. The file is resolved relative to
    this module so it works regardless of where main.py is invoked from.
    """
    prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
    with open(prompt_path, encoding="utf-8") as f:
        return f.read().strip()


SYSTEM_PROMPT = _load_system_prompt()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _image_to_base64(image) -> tuple[str, str]:
    """
    Encode a PIL image as a base64 PNG string suitable for the Claude API.

    PNG is used (over JPEG) for lossless quality, which is important when
    the captured region contains code, error messages, or small text.

    Args:
        image: A PIL.Image.Image instance.

    Returns:
        A (base64_data, media_type) tuple, e.g. ("iVBORw...", "image/png").
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
    return data, "image/png"


def _build_image_message(image, text: str) -> dict:
    """
    Build a Claude API user message containing both an image and a text prompt.

    Args:
        image: A PIL.Image.Image instance to include in the message.
        text:  The accompanying text prompt.

    Returns:
        A dict in the Claude messages API format.
    """
    img_data, media_type = _image_to_base64(image)
    return {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": img_data,
                },
            },
            {
                "type": "text",
                "text": text,
            },
        ],
    }


def _call_api(messages: list) -> str:
    """
    Send a list of messages to the Claude API and return the response text.

    Args:
        messages: Full conversation history in Claude messages API format.

    Returns:
        The assistant's response as a plain string.

    Raises:
        anthropic.APIError: On any API-level error (auth, rate limit, etc).
    """
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain_capture(image, history: list) -> tuple[str, list]:
    """
    Send a newly captured screenshot to Claude and return an explanation.

    This is called for the first message in a capture session. The image is
    encoded and sent alongside a fixed prompt asking for an explanation.

    Args:
        image:   PIL.Image.Image — the cropped screen region to explain.
        history: Should be an empty list for a new session.

    Returns:
        A (response_text, updated_history) tuple. Pass updated_history back
        to subsequent ask_followup() calls to maintain context.
    """
    user_message = _build_image_message(
        image,
        "Please explain what I'm looking at in this screenshot."
    )
    messages = [user_message]
    response_text = _call_api(messages)

    updated_history = [
        user_message,
        {"role": "assistant", "content": response_text},
    ]
    return response_text, updated_history


def ask_followup(image, question: str, history: list) -> tuple[str, list]:
    """
    Send a follow-up question about the current capture to Claude.

    The original image is re-included in every follow-up so Claude always has
    full visual context, regardless of how many turns have passed.

    Args:
        image:    PIL.Image.Image — the original captured region.
        question: The user's follow-up question as a plain string.
        history:  The conversation history returned by the previous call.

    Returns:
        A (response_text, updated_history) tuple.
    """
    user_message = _build_image_message(image, question)
    messages = history + [user_message]
    response_text = _call_api(messages)

    updated_history = messages + [
        {"role": "assistant", "content": response_text},
    ]
    return response_text, updated_history