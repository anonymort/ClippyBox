"""First-run checks for Ollama availability and model readiness."""

import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

import urllib.request
import json


def _is_local_ollama(base_url: str) -> bool:
    """Return True if the base URL points at a local Ollama instance."""
    parsed = urlparse(base_url)
    return parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1") and parsed.port == 11434


def _ollama_api_url(base_url: str) -> str:
    """Derive the native Ollama API base from the OpenAI-compat URL."""
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 11434}"


def _check_accessibility() -> None:
    """Prompt for Accessibility permission if not already granted."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        from CoreFoundation import kCFBooleanTrue
        # kAXTrustedCheckOptionPrompt triggers the system dialog
        options = {"AXTrustedCheckOptionPrompt": kCFBooleanTrue}
        if not AXIsProcessTrustedWithOptions(options):
            print("Accessibility permission required for the global hotkey.\n")
            print("A system dialog should have appeared — grant access to your")
            print("terminal app, then relaunch ClippyBox.")
            sys.exit(1)
    except ImportError:
        pass  # not on macOS or framework unavailable


def run() -> None:
    """Run preflight checks. Exits the process if any check fails."""
    _check_accessibility()

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("MODEL", "llava")

    if not _is_local_ollama(base_url):
        return  # non-Ollama backend; skip checks

    # Check 1: Is Ollama installed?
    if shutil.which("ollama") is None:
        print("Ollama is not installed.\n")
        print("Install with Homebrew:")
        print("  brew install ollama\n")
        print("Or download from https://ollama.com\n")
        print("Then relaunch ClippyBox.")
        sys.exit(1)

    # Check 2: Is Ollama running? Start it automatically if not.
    api_base = _ollama_api_url(base_url)
    try:
        urllib.request.urlopen(f"{api_base}/api/tags", timeout=3)
    except Exception:
        print("Starting Ollama...")
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait up to 15 seconds for it to become ready
        import time
        for _ in range(30):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(f"{api_base}/api/tags", timeout=2)
                break
            except Exception:
                continue
        else:
            print("Ollama did not start in time.\n")
            print("Try starting it manually:")
            print("  ollama serve\n")
            print("Then relaunch ClippyBox.")
            sys.exit(1)

    # Check 3: Is the configured model available?
    try:
        resp = urllib.request.urlopen(f"{api_base}/api/tags", timeout=3)
        data = json.loads(resp.read())
        local_models = [m["name"].split(":")[0] for m in data.get("models", [])]
    except Exception:
        return  # can't check; let the API call fail later with a clear error

    if model.split(":")[0] in local_models:
        return  # model is available

    if not sys.stdin.isatty():
        print(f'Model "{model}" is not available locally.\n')
        print("Download it with:")
        print(f"  ollama pull {model}\n")
        print("Then relaunch ClippyBox.")
        sys.exit(1)

    answer = input(f'Model "{model}" is not downloaded. Download now? [Y/n] ')
    if answer.strip().lower() in ("", "y", "yes"):
        try:
            subprocess.run(["ollama", "pull", model], check=True)
        except KeyboardInterrupt:
            print(f"\nDownload paused. Run `ollama pull {model}` to resume.")
            sys.exit(1)
        except subprocess.CalledProcessError:
            print(f"\nDownload failed. Try manually: ollama pull {model}")
            sys.exit(1)
    else:
        print(f"\nRun `ollama pull {model}` when ready, then relaunch ClippyBox.")
        sys.exit(0)
