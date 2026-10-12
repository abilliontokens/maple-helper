"""The game's picture on screen: its window (osapi: winapi on Windows, macapi on macOS) without the black bars a 16:9
game draws on an ultrawide screen. The loot log finds the game's pickup messages in it (ui/lootscan.py), and the
minimap reads find the game's MINI MAP window at its top left (ui/minimapscan.py)."""
from __future__ import annotations

import sys
import time

from . import capture, osapi

BARS_EVERY_S = 30.0     # how often the game's black bars are measured again (one whole-window grab); and on a resize


def valid_region(region) -> bool:
    """A saved box ({"x","y","w","h"}: a window's place and size): ints (or floats) with a size, not a stray dict."""
    return (isinstance(region, dict)
            and all(isinstance(region.get(k), (int, float)) and not isinstance(region.get(k), bool)
                    for k in ("x", "y", "w", "h"))
            and region["w"] > 0 and region["h"] > 0)


class GameArea:
    """The game's picture on screen (x, y, w, h in capture coordinates), found from its window. The black bars are
    measured on a whole-window grab when the window's size changes and every BARS_EVERY_S; the window's own place on
    every call, so a moved window is followed at once. Worker thread only (each reader keeps its own)."""

    def __init__(self):
        self._hwnd = None
        self._rect: tuple | None = None
        self._inset: tuple[int, int, int, int] = (0, 0, 0, 0)    # the picture's (left, top, right, bottom) margins
        self._measured = 0.0

    def find(self) -> tuple[int, int, int, int] | None:
        rect = osapi.window_rect(self._hwnd) if self._hwnd else None
        if rect is None:
            problem = capture.LAST_PROBLEM         # (find_game_window resets it: the chat's own note stays)
            self._hwnd = osapi.find_game_window()
            capture.LAST_PROBLEM = problem
            rect = osapi.window_rect(self._hwnd) if self._hwnd else None
            if rect is None:
                self._rect = None
                return None
        x, y, w, h = rect
        if self._rect is None or self._rect[2:] != rect[2:] or time.monotonic() - self._measured > BARS_EVERY_S:
            self._inset = self._bars(rect)
            self._measured = time.monotonic()
        self._rect = rect
        left, top, right, bottom = self._inset
        return x + left, y + top, max(1, w - left - right), max(1, h - top - bottom)

    @staticmethod
    def _bars(rect) -> tuple[int, int, int, int]:
        img = capture.grab_image(*rect)
        box = capture.content_box(img)
        if not box:
            return 0, 0, 0, 0
        sx, sy = rect[2] / img.width, rect[3] / img.height     # (a Retina grab has more pixels than points)
        return (round(box[0] * sx), round(box[1] * sy), round((img.width - box[2]) * sx),
                round((img.height - box[3]) * sy))

    def covered(self, box: dict) -> bool:
        """Another app's window over the box (the loot log's messages): a screen grab would read its text (a chat
        window over the game's corner was read live). Windows only: the macOS layer has no such check."""
        if sys.platform != "win32" or not self._hwnd:
            return False
        from .winapi import covered
        return covered(self._hwnd, (box["x"], box["y"], box["w"], box["h"]))
