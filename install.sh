#!/bin/bash
# ClippyBox installer — creates an isolated venv and a clippybox command.
# Usage: curl -sSL https://raw.githubusercontent.com/anonymort/ClippyBox/main/install.sh | bash

set -e

INSTALL_DIR="$HOME/.local/share/clippybox"
BIN_DIR="$HOME/.local/bin"
REPO="https://github.com/anonymort/ClippyBox/archive/refs/heads/main.tar.gz"

echo "Installing ClippyBox..."

# Check Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found. Install it with: brew install python"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "Error: Python 3.10+ required (found $PY_VERSION)"
    exit 1
fi

# Check tkinter
if ! python3 -c "import tkinter" &>/dev/null; then
    echo "Error: tkinter not found. Install it with: brew install python-tk@$PY_VERSION"
    exit 1
fi

# Clean previous install
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing previous install..."
    rm -rf "$INSTALL_DIR"
fi

# Download and extract
echo "Downloading..."
TMPDIR=$(mktemp -d)
curl -sSL "$REPO" | tar xz -C "$TMPDIR"
mv "$TMPDIR"/ClippyBox-main "$INSTALL_DIR"
rm -rf "$TMPDIR"

# Create venv and install deps
echo "Setting up environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet \
    Pillow pynput pyobjc-framework-Cocoa pyobjc-framework-Quartz

# Create bin directory and launcher script
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/clippybox" << 'LAUNCHER'
#!/bin/bash
exec "$HOME/.local/share/clippybox/.venv/bin/python" -m clippybox "$@"
LAUNCHER
chmod +x "$BIN_DIR/clippybox"

# Check PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "Add this to your shell profile (~/.zshrc):"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "Then restart your terminal, or run:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "ClippyBox installed! Run: clippybox"
