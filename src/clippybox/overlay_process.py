"""
src/clippybox/overlay_process.py - macOS screen region selection overlay.

This script is intended to be run as a subprocess, NOT imported directly.
It is launched by __main__.py with a single argument: the path to write the
cropped PNG to on success.

Why a subprocess?
  PyObjC requires the main thread for all NSWindow/NSView operations.
  The main process uses tkinter for the result panel, which also wants
  the main thread. Running the overlay as a separate process sidesteps
  this conflict entirely.

Flow:
  1. Take a full screenshot before the overlay window appears.
  2. Show a borderless fullscreen NSWindow with the screenshot as background.
  3. User draws a selection box with the mouse.
  4. On mouse release: crop the screenshot to the selection, save to argv[1], exit 0.
  5. On Esc: exit 1 (no file written — __main__.py treats this as a cancellation).

Coordinate system:
  Cocoa uses bottom-left origin (y=0 at the bottom of the screen).
  PIL uses top-left origin. The y-axis is flipped when converting.
  On Retina displays the screenshot pixel dimensions are 2x the logical
  screen dimensions — a scale factor is applied to all crop coordinates.
"""

import io
import os
import sys
import tempfile
import subprocess

import objc
from objc import super  # Must shadow built-in super for PyObjC subclasses

from PIL import Image

from Cocoa import (
    NSApplication,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSBorderlessWindowMask,
    NSColor,
    NSData,
    NSFloatingWindowLevel,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSMakeRect,
    NSApp,
    NSString,
    NSView,
    NSWindow,
)
from Quartz import CGDisplayPixelsHigh, CGDisplayPixelsWide, CGMainDisplayID


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def take_screenshot() -> Image.Image:
    """
    Capture the main display using the macOS `screencapture` CLI.

    Using `screencapture` rather than PIL's ImageGrab is intentional:
    ImageGrab returns a black image on macOS unless Screen Recording
    permission has been granted in a specific way. `screencapture` respects
    the system permission prompt automatically.

    Flags:
      -x  Suppress the shutter sound.
      -m  Capture the main display only (avoids multi-monitor confusion).

    Returns:
        A PIL.Image.Image of the full main display at native resolution.

    Raises:
        subprocess.CalledProcessError: If screencapture exits non-zero.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        subprocess.run(["screencapture", "-x", "-m", tmp.name], check=True)
        img = Image.open(tmp.name)
        img.load()
        return img
    finally:
        os.unlink(tmp.name)


def pil_to_nsimage(pil_img: Image.Image):
    """
    Convert a PIL image to an NSImage suitable for drawing in a Cocoa view.

    Args:
        pil_img: Any PIL.Image.Image instance.

    Returns:
        An NSImage instance initialised from the PNG-encoded pixel data.
    """
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    raw = buf.getvalue()
    ns_data = NSData.dataWithBytes_length_(raw, len(raw))
    return NSImage.alloc().initWithData_(ns_data)


# ---------------------------------------------------------------------------
# Module-level screen state (computed once at startup)
# ---------------------------------------------------------------------------

_display    = CGMainDisplayID()
SCREEN_W    = CGDisplayPixelsWide(_display)   # Logical pixel width
SCREEN_H    = CGDisplayPixelsHigh(_display)   # Logical pixel height

screenshot  = take_screenshot()
SCALE       = screenshot.width / SCREEN_W     # 2.0 on Retina, 1.0 otherwise
ns_screenshot = pil_to_nsimage(screenshot)

OUTPUT_PATH = sys.argv[1]  # Temp file path passed by __main__.py


# ---------------------------------------------------------------------------
# NSWindow subclass — allows borderless windows to become key
# ---------------------------------------------------------------------------

class KeyWindow(NSWindow):
    """
    NSWindow subclass that opts in to keyboard focus.

    By default, borderless windows (NSBorderlessWindowMask) return False
    from canBecomeKeyWindow, which prevents them from receiving keyboard
    events. Overriding both methods here enables Esc to work correctly.
    """

    def canBecomeKeyWindow(self):
        """Allow this borderless window to become the key window."""
        return True

    def canBecomeMainWindow(self):
        """Allow this borderless window to become the main window."""
        return True


# ---------------------------------------------------------------------------
# NSView subclass — draws the overlay and handles interaction
# ---------------------------------------------------------------------------

class OverlayView(NSView):
    """
    Full-screen NSView that renders the selection overlay.

    Drawing layers (bottom to top):
      1. Screenshot — so the user can see their screen content.
      2. Semi-transparent black dim — to indicate the overlay is active.
      3. Selection rectangle (white border + corner dots) — drawn while dragging.
      4. Instruction text — top-centre of the screen.

    Interaction:
      - Click and drag to draw a selection.
      - Release the mouse to confirm and save the crop.
      - Press Esc to cancel without saving.
    """

    def initWithFrame_(self, frame):
        """Initialise the view and set up selection state."""
        self = super().initWithFrame_(frame)
        if self is not None:
            self._start = None   # (x, y) where the mouse was pressed
            self._end   = None   # (x, y) current mouse position while dragging
        return self

    def drawRect_(self, dirtyRect):
        """
        Render all overlay layers.

        Called by AppKit whenever the view needs to be redrawn — on first
        display and after every call to setNeedsDisplay_(True).
        """
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height

        # Layer 1: screenshot as background
        ns_screenshot.drawInRect_(bounds)

        # Layer 2: subtle dark dim (25% opacity — visible but not oppressive)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0, 0, 0, 0.25).set()
        NSBezierPath.fillRect_(bounds)

        # Layer 3: selection rectangle (only while the user is dragging)
        if self._start and self._end:
            sx, sy = self._start
            ex, ey = self._end
            x,  y  = min(sx, ex), min(sy, ey)
            rw, rh = abs(ex - sx), abs(ey - sy)
            rect   = NSMakeRect(x, y, rw, rh)

            # White border
            NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 1, 1, 0.9).set()
            border = NSBezierPath.bezierPathWithRect_(rect)
            border.setLineWidth_(1.5)
            border.stroke()

            # Corner handle dots
            dot = 6.0
            for cx, cy in [(x, y), (x + rw, y), (x, y + rh), (x + rw, y + rh)]:
                NSColor.whiteColor().set()
                NSBezierPath.fillRect_(NSMakeRect(cx - dot / 2, cy - dot / 2, dot, dot))

        # Layer 4: instruction label
        label_attrs = {
            NSForegroundColorAttributeName: NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 1, 1, 0.7),
            NSFontAttributeName:            NSFont.systemFontOfSize_(13),
        }
        NSString.stringWithString_("Draw a box   |   Esc to cancel") \
            .drawAtPoint_withAttributes_(
                NSMakeRect(w // 2 - 100, h - 40, 250, 25).origin,
                label_attrs,
            )

    def mouseDown_(self, event):
        """Record the anchor point when the user presses the mouse button."""
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        self._start = (p.x, p.y)
        self._end   = (p.x, p.y)
        self.setNeedsDisplay_(True)

    def mouseDragged_(self, event):
        """Update the live selection rectangle as the user drags."""
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        self._end = (p.x, p.y)
        self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        """
        Finalise the selection on mouse release.

        Converts the logical Cocoa coordinates to PIL pixel coordinates,
        crops the screenshot, saves it to OUTPUT_PATH, and terminates.
        Ignores selections smaller than 10x10 logical pixels.
        """
        p  = self.convertPoint_fromView_(event.locationInWindow(), None)
        sx, sy = self._start
        ex, ey = p.x, p.y

        x1, y1 = min(sx, ex), min(sy, ey)
        x2, y2 = max(sx, ex), max(sy, ey)

        if (x2 - x1) < 10 or (y2 - y1) < 10:
            return  # Too small — ignore accidental clicks

        # Flip y-axis (Cocoa: bottom-left origin → PIL: top-left origin)
        # and apply Retina scale factor to get real pixel coordinates
        rx1 = int(x1 * SCALE)
        ry1 = int((SCREEN_H - y2) * SCALE)
        rx2 = int(x2 * SCALE)
        ry2 = int((SCREEN_H - y1) * SCALE)

        cropped = screenshot.crop((rx1, ry1, rx2, ry2))
        cropped.save(OUTPUT_PATH)
        NSApp.terminate_(None)

    def keyDown_(self, event):
        """Cancel the overlay when the user presses Esc (keyCode 53)."""
        if event.keyCode() == 53:
            NSApp.terminate_(None)  # Exits with code 0; __main__.py checks file size

    def acceptsFirstResponder(self):
        """Allow this view to receive keyboard events."""
        return True


# ---------------------------------------------------------------------------
# Application setup and run loop
# ---------------------------------------------------------------------------

app = NSApplication.sharedApplication()

# NSApplicationActivationPolicyRegular (0) is required for the app to
# receive keyboard events. NSApplicationActivationPolicyAccessory (1)
# silently drops key events even when the window is frontmost.
app.setActivationPolicy_(0)

win = KeyWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    NSMakeRect(0, 0, SCREEN_W, SCREEN_H),
    NSBorderlessWindowMask,
    NSBackingStoreBuffered,
    False,
)
win.setLevel_(NSFloatingWindowLevel + 1)  # Float above all other windows
win.setOpaque_(False)
win.setBackgroundColor_(NSColor.clearColor())

view = OverlayView.alloc().initWithFrame_(NSMakeRect(0, 0, SCREEN_W, SCREEN_H))
win.setContentView_(view)
win.makeKeyAndOrderFront_(None)
win.makeFirstResponder_(view)
app.activateIgnoringOtherApps_(True)

app.run()