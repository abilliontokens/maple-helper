"""Where the game's MINI MAP window is, in a grab of the game's top-left corner: the box (x, y, w, h) of the whole
window (frame, title bar, header and map panel; the folded strip alone when the game folds the window inside a
building), whatever its size (it changes with the map) and whatever the game's UI scale (the UI scales with the game's
window: 1x at 1368x800, 2x at 2734x1568, smoothed in between).

The window is found by its title bar's right end, which every look of it shares: the orange WORLD button with the -
and + buttons left of it, each outlined in black. WORLD's fill is 34 game pixels (gp) wide, so its width gives the UI
scale, and the rest is measured in gp from it:

- the title body shows through the 2 gp gap between + and WORLD (white on the window, light grey on the folded strip):
  that column gives the body's top and bottom edges;
- the body runs left from the - button to the window's left frame;
- the window's edges sit a fixed number of gp outside the body: its right 6 gp right of WORLD's fill (5 folded), its
  left and top 4 gp out from the body (1 folded);
- the window ends in a bar of two blue lines 5 gp apart under the map panel, then 2 gp of white edge: the first such
  pair down the window, flat across its whole width, is its bottom, and the frame's blue lines run down both sides to
  it. Folded, the strip ends 1 gp under the body.

Every edge is placed to a fraction of a pixel (where the colour crosses halfway between its two sides) before it is
rounded, so a smoothly scaled picture gives the same box frame after frame (a pixel's jitter would reset the reader),
and all of them lie inside the window, whatever the game shows around it. Whatever fails a check is not the window:
the game's scene (leaves, bricks, name tags) and its other UI never carry this layout. Pure numpy, no Qt: the
scanner's worker thread calls it once a read, a few milliseconds each."""
from __future__ import annotations

import itertools
import math

import numpy as np
from PIL import Image

_FILL = 34          # WORLD's orange fill, gp wide between its black outlines: the yardstick of the UI scale
_BUTTONS = (-28, -17, -15, -4)  # the - and + buttons' black sides, gp from the fill's left edge: an orange run
                                # without them is not WORLD
_BODY = 14          # the title body's height in gp, between the frame lines over and under it ...
_BODY_FOLDED = 18   # ... and the folded strip's (it shows the map's name in a bigger font)
_FRAME = 136        # the frame line around the title body (its darkest channel), both looks: the body's edges are
_WHITE = 255        # where its colour, white on the window ...
_GREY = 221         # ... and light grey on the folded strip, crosses halfway to the frame's
_SEARCH = 0.4       # WORLD is looked for in this top share of the picture's rows ...
_LEFT = 0.15        # ... and the window's left edge lies in this left share of its width (the window sits at the
                    # game's top-left corner, under the OS caption)
_MIN_BODY = 40      # the title body runs at least this far (gp) left of the - button (130 or more on the live captures)
_DARK = 120         # an outline pixel's brightest channel is at most this, smoothing included
_SAMPLES = 32       # the bottom bar is looked for down this many columns across the window, then checked across all


def find_window(img: Image.Image) -> tuple[int, int, int, int] | None:
    """The MINI MAP window's box (x, y, w, h) in the picture's pixels (clipped to the picture), searched at its top
    left; None when there is none. The same picture gives the same box to the pixel. Any image mode is taken (an RGBA
    grab is converted)."""
    rgb = np.asarray(img if img.mode == "RGB" else img.convert("RGB"))
    for y, x0, x1 in _fills(rgb[:max(1, round(_SEARCH * rgb.shape[0]))]):
        box = _window(rgb, y, x0, x1)
        if box is not None:
            return box
    return None


def _fills(band: np.ndarray) -> list[tuple[int, int, int]]:
    """WORLD's fill candidates in these top rows, topmost first: (row, x0, x1) of runs of its orange (221, 153, 17)
    as wide as the fill at any UI scale (0.75x to 4x), with its black outline within 3 pixels past both ends (bright
    orange in the game's scene has none: of the 1305 such runs in a live scene of falling maple leaves scaled up, none
    passed). The rows of one button (both ends within a pixel from row to row, the letters' rows between) count once,
    by their middle row: the - and + buttons span it."""
    r, g, b = band[..., 0], band[..., 1], band[..., 2]
    orange = (r >= 190) & (b <= 70) & (g >= 110) & (g.astype(np.int16) + 40 <= r)
    w = orange.shape[1]
    step = np.diff(np.pad(orange, ((0, 0), (1, 1))).view(np.int8), axis=1)
    ys, x0s = np.nonzero(step == 1)
    _, x1s = np.nonzero(step == -1)
    keep = (x1s - x0s >= 0.75 * _FILL) & (x1s - x0s <= 4 * _FILL)
    ys, x0s, x1s = ys[keep], x0s[keep], x1s[keep]

    def dark(xs: np.ndarray) -> np.ndarray:
        return band[ys, np.clip(xs, 0, w - 1)].max(axis=-1) <= _DARK

    outlined = (dark(x0s - 1) | dark(x0s - 2) | dark(x0s - 3)) & (dark(x1s) | dark(x1s + 1) | dark(x1s + 2))
    buttons: list[list[tuple[int, int, int]]] = []
    for y, x0, x1 in zip(ys[outlined].tolist(), x0s[outlined].tolist(), x1s[outlined].tolist()):
        for rows in buttons:
            ly, l0, l1 = rows[-1]
            if abs(x0 - l0) <= 1 and abs(x1 - l1) <= 1 and y - ly <= 8 * (x1 - x0) / _FILL:
                rows.append((y, x0, x1))
                break
        else:
            buttons.append([(y, x0, x1)])
    return [rows[len(rows) // 2] for rows in buttons]


def _window(rgb: np.ndarray, y: int, x0: int, x1: int) -> tuple[int, int, int, int] | None:
    """The window around this WORLD candidate (an orange run on row y from x0 to x1, exclusive), None when the layout
    around it is not the window's."""
    H, W = rgb.shape[0], rgb.shape[1]
    s = (x1 - x0) / _FILL
    if not (_dark(rgb, y, x0 - 1.5 * s - 1, x0) and _dark(rgb, y, x1, x1 + 1.5 * s + 1)):
        return None
    ends = _fill_ends(rgb, y, x0, x1, s)
    if ends is None or abs(ends[0] - x0) > 0.5 * s + 1 or abs(ends[1] - x1) > 0.5 * s + 1:
        return None
    xl, xr = ends
    s = (xr - xl) / _FILL       # the UI scale (screen pixels a gp), to a fraction of a pixel
    if not all(_dark(rgb, y, xl + (g + 0.5) * s - 1.5, xl + (g + 0.5) * s + 1.5) for g in _BUTTONS):
        return None
    # the title body through the gap between + and WORLD: the gap's brightest column, from the frame over the body
    # to the frame under it
    gap = [x for x in range(math.ceil(xl - 2.75 * s - 0.5), math.floor(xl - 1.25 * s - 0.5) + 1) if 0 <= x < W]
    if not gap:
        return None
    col = rgb[:, gap[int(np.argmax(rgb[y, gap].min(axis=-1)))]].astype(np.int16)
    dim = col.min(axis=1)
    neutral = col.max(axis=1) - dim <= 30
    lit = _run((dim >= (_FRAME + _GREY) / 2) & neutral, y)
    end = math.floor(xl - 29.5 * s)         # 1.5 gp left of the - button
    if lit is None or end <= _MIN_BODY * s:
        return None
    # the body's top rows under its rounded corner (2 gp tall folded) and over any text (5 gp down): white on the
    # window, grey folded
    top_rows = rgb[int(lit[0] + 3 * s):int(lit[0] + 4.5 * s), :end].min(axis=-1)
    if not top_rows.size:
        return None
    level = float(np.median(top_rows[:, -max(1, round(20 * s)):]))
    if level >= 238:
        folded = False
    elif level >= 205:
        folded = True
    else:
        return None
    half = (_FRAME + (_GREY if folded else _WHITE)) / 2
    body = _run((dim >= half) & neutral, y)
    if body is None or body[0] < 1 or body[1] >= H:
        return None
    body_top, body_bottom = _crossing(dim, body[0], half), _crossing(dim, body[1], half)
    if not 0.85 <= (body_bottom - body_top) / ((_BODY_FOLDED if folded else _BODY) * s) <= 1.15:
        return None
    if not folded:      # the header's pale blue under the title bar
        under = col[math.floor(body_bottom + 1.5 * s):math.ceil(body_bottom + 4 * s)]
        if not len(under) or not _bluish(under.mean(axis=0)):
            return None
    # the body's left end: along its top rows the light runs left from the - button to the frame
    light = top_rows.mean(axis=0)
    dark = np.flatnonzero(light < half)
    if not len(dark) or end - (int(dark[-1]) + 1) < _MIN_BODY * s:
        return None
    body_left = _crossing(light, int(dark[-1]) + 1, half)
    if folded:
        left, top, right, bottom = body_left - s, body_top - s, xr + 5 * s, body_bottom + s
    else:
        left, top, right = body_left - 4 * s, body_top - 4 * s, xr + 6 * s
    if left >= _LEFT * W:
        return None
    if not folded:
        bar = _bar(rgb, left, right, body_bottom, s)
        if bar is None:
            return None
        bar_top, bottom = bar
        sides = math.ceil(body_bottom), bar_top
        if not (_framed(rgb, left + 1.5 * s, *sides) and _framed(rgb, right - 1.5 * s, *sides)):
            return None
    bx, by = max(0, _round(left)), max(0, _round(top))
    bw, bh = min(W, _round(right)) - bx, min(H, _round(bottom)) - by
    return (bx, by, bw, bh) if bw > 0 and bh > 0 else None


def _fill_ends(rgb: np.ndarray, y: int, x0: int, x1: int, s: float) -> tuple[float, float] | None:
    """WORLD's fill on row y to a fraction of a pixel: where its red falls halfway from the fill's own (the run's
    median: a sharpened edge overshoots it) to the darkest of the black outline beside it, each side. A smoothed
    picture leaves an edge pixel half in the fill, which the orange run's whole pixels miss; at the 1x UI the 1-pixel
    outline smooths out to half the fill's red, which a fixed level would walk straight through."""
    red = rgb[y, :, 0].astype(np.float64)
    fill = float(np.median(red[x0:x1]))
    reach = math.ceil(1.5 * s) + 1
    if x0 - reach < 1 or x1 + reach >= len(red):
        return None
    lo, hi = (fill + red[x0 - reach:x0].min()) / 2, (fill + red[x1:x1 + reach].min()) / 2
    a, b = x0, x1
    while red[a - 1] >= lo and a > x0 - reach:
        a -= 1
    while red[b] >= hi and b < x1 + reach:
        b += 1
    return _crossing(red, a, lo), _crossing(red, b, hi)


def _bar(rgb: np.ndarray, left: float, right: float, body_bottom: float, s: float) -> tuple[int, float] | None:
    """The window's bottom bar under its map panel: two blue (85, 119, 153) lines 5 gp apart, paler blue between,
    then the window's 2 gp white edge. Looked for down _SAMPLES columns across the window (inside its rounded corners)
    from under the title bar; the first pair that is also flat across the window's whole width counts. Its top row
    and the window's bottom edge (2 gp under the lower line, to a fraction of a pixel); None without."""
    H = rgb.shape[0]
    xa, xb = max(0, math.ceil(left + 8 * s)), min(rgb.shape[1], math.floor(right - 8 * s))
    ya = math.ceil(body_bottom + 4 * s)
    if xb - xa < _SAMPLES or H - ya < 10 * s:
        return None
    cols = np.linspace(xa, xb - 1, _SAMPLES).round().astype(np.intp)
    m, flat = _rows(rgb[ya:, cols].astype(np.int16))
    red, blue = m[:, 0], m[:, 2]
    line = np.flatnonzero(flat & (red <= 160) & (blue - red >= 30))
    if len(line) < 2:
        return None
    cut = np.flatnonzero(np.diff(line) > 1)
    runs = list(zip(np.r_[line[0], line[cut + 1]].tolist(), np.r_[line[cut], line[-1]].tolist()))  # [first, last]
    white = flat & (m.min(axis=1) >= 230)
    thin = 1.5 * s + 2
    for (a0, a1), (b0, b1) in itertools.pairwise(runs):
        if a1 - a0 + 1 > thin or b1 - b0 + 1 > thin:
            continue
        # 5 gp between the lines' darkest rows (their runs' middles shift with whatever lies either side)
        apart = (b0 + int(np.argmin(red[b0:b1 + 1]))) - (a0 + int(np.argmin(red[a0:a1 + 1])))
        if abs(apart - 5 * s) > max(1.5, 0.3 * s):
            continue
        if b0 <= a1 + 1 or flat[a1 + 1:b0].mean() < 0.8 or (red[a1 + 1:b0] < 140).any():
            continue
        if b1 + 1 >= len(red) or not white[b1 + 1:b1 + 2 + math.ceil(s)].any():
            continue
        if _rows(rgb[ya + a0:ya + b1 + 1, xa:xb].astype(np.int16))[1].mean() < 0.85:
            continue
        return ya + a0, ya + _crossing(red, b1 + 1, 170) + 2 * s
    return None


def _rows(px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each row's colour (the mean of its pixels near the plain mean: a stray pixel can't drag it) and whether the row
    is one flat colour (three in four of its pixels within 24 of that). px: rows x columns x RGB, int16."""
    m = px.mean(axis=1)
    near = np.abs(px - m[:, None]).max(axis=-1) <= 40
    m = (px * near[..., None]).sum(axis=1) / np.maximum(1, near.sum(axis=1))[:, None]
    return m, (np.abs(px - m[:, None]).max(axis=-1) <= 24).mean(axis=1) >= 0.75


def _framed(rgb: np.ndarray, x: float, y0: int, y1: int) -> bool:
    """Whether the frame's blue line runs down past x (a pixel either side) from row y0 to y1."""
    px = rgb[y0:y1, max(0, _round(x) - 1):min(rgb.shape[1], _round(x) + 2)].astype(np.int16)
    if not px.size:
        return False
    return bool(((px[..., 2] - px[..., 0] >= 15) & (px[..., 0] <= 200)).any(axis=1).mean() >= 0.8)


def _dark(rgb: np.ndarray, y: int, xa: float, xb: float) -> bool:
    """Whether row y holds a black outline pixel between xa and xb."""
    a, b = max(0, math.floor(xa)), min(rgb.shape[1], math.ceil(xb))
    return b > a and int(rgb[y, a:b].max(axis=-1).min()) <= _DARK


def _run(mask: np.ndarray, i: int) -> tuple[int, int] | None:
    """The run of True through index i of this 1-D mask, [start, end); None when i is False."""
    if not mask[i]:
        return None
    off = np.flatnonzero(~mask)
    k = int(np.searchsorted(off, i))
    return (int(off[k - 1]) + 1 if k else 0), (int(off[k]) if k < len(off) else len(mask))


def _crossing(p: np.ndarray, i: int, t: float) -> float:
    """Where profile p crosses t between its pixels i-1 and i, rising or falling (pixel i spans [i, i+1), so the two
    centres sit at i-0.5 and i+0.5): an edge to a fraction of a pixel, kept between the two."""
    a, b = float(p[i - 1]), float(p[i])
    return i - 0.5 + (min(1.0, max(0.0, (t - a) / (b - a))) if b != a else 0.5)


def _bluish(c: np.ndarray) -> bool:
    """Whether a colour is the window's pale blue-grey (blue well over red, at least green)."""
    return bool(c[2] - c[0] >= 25 and c[2] >= c[1])


def _round(v: float) -> int:
    """A pixel edge rounded half up: the same value always gives the same edge."""
    return math.floor(v + 0.5)
