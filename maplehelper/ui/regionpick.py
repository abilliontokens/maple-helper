"""A box in capture coordinates (what `maplehelper.capture.grab_image` takes: the game's minimap window in
LOCATION.box, the game's picture from gamearea) back to the logical pixels the windows over the game are placed in."""
from __future__ import annotations

from PySide6.QtCore import QRect


def from_capture(box: dict, screens: list[tuple[QRect, float]], scale: bool = True) -> tuple[QRect, float]:
    """A capture-coordinates box back to logical pixels, with the devicePixelRatio of the screen holding its centre
    (capture pixels per logical pixel: 1.0 when unscaled).

    `screens` pairs each screen's logical geometry with its devicePixelRatio. Windows capture coordinates are
    physical pixels, and Qt maps each screen from its own native origin, so the box is scaled on the screen holding
    its centre (a box straddling two screens follows its middle). With `scale=False` (macOS: capture coordinates are
    points) the box passes through unchanged."""
    x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
    if not scale or not screens:
        return QRect(x, y, w, h), 1.0
    cx, cy = x + w / 2, y + h / 2
    geo, ratio = screens[0]
    for g, r in screens:
        o = g.topLeft()
        if o.x() <= cx < o.x() + g.width() * r and o.y() <= cy < o.y() + g.height() * r:
            geo, ratio = g, r
            break
    o = geo.topLeft()
    return QRect(round(o.x() + (x - o.x()) / ratio), round(o.y() + (y - o.y()) / ratio),
                 max(1, round(w / ratio)), max(1, round(h / ratio))), ratio
