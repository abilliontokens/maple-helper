"""The MINI MAP window finder (maplehelper.minimapfind) on real captures: the whole window's box in a grab of the
game's top-left corner, at whatever size the map gives it, folded or not, at any UI scale.

The boxes are measured by hand on the fixtures, where the window's outer edge meets the game (pixel colours): in the
live grab the window's white edge spans x 3..442 and y 79..512, a box of (3, 79, 440, 434) at the game's 2x UI. The
tight crops are the owner's screenshots of the window with a few pixels of game around it: each is pasted with its
window where the live one was, onto the live grab with that window covered by game scene from the grab's right side,
so every case sits in the same busy picture. With the real KB, the window cropped to the box found reads as its map
through the minimap reader (OCR; skipped without the KB, like the other real-KB tests)."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from maplehelper.minimapfind import find_window

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "routes.json").exists(), reason="no routes.json in the real knowledge base")

# the live grab's window (x, y, w, h): white edge x 3..442 (2 px of white, then the frame's blue line at 5..6), y 79..512
# (its top white rows under two dark rows, 77..78, with a falling leaf over them at x 241..356; its bottom white under
# the bottom bar's second blue line at 507..508)
LIVE = (3, 79, 440, 434)
# each crop's window in the crop's own pixels, measured the same way: swamp1's crop cuts off the left white edge's
# 2 px; the folded strip's outer edge is its grey (136) outline, 1 gp outside its light grey body
CROPS = {
    "minimap_window_kerning_live.png": (3, 2, 440, 434),        # Kerning City: medium
    "minimap_window_swamp1_live.png": (-2, 6, 404, 380),        # The Swamp of Despair I: smaller
    "minimap_window_swamp2_live.png": (1, 5, 466, 364),         # The Swamp of Despair II: wider
    "minimap_window_collapsed_live.png": (4, 7, 496, 40),       # inside Niora Hospital: folded to its strip
}


@pytest.fixture(scope="module")
def graph():
    from maplehelper import routes
    from maplehelper.kb import KnowledgeBase
    return routes.of(KnowledgeBase(REAL_KB))


def _live() -> Image.Image:
    return Image.open(FIXTURES / "game_topleft_kerning_live.png").convert("RGB")


def _covered() -> Image.Image:
    """The live grab with its minimap window covered by game scene from the grab's right side (a wall, a pillar, the
    falling leaves): the game without the window."""
    img = _live()
    img.paste(img.crop((560, 70, 1020, 530)), (0, 70))
    return img


def _on_game(name: str, at: tuple[int, int] = LIVE[:2]) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """This crop pasted onto the covered grab with its window's top-left at `at`, and that window's box there."""
    x, y, w, h = CROPS[name]
    img = _covered()
    img.paste(Image.open(FIXTURES / name).convert("RGB"), (at[0] - x, at[1] - y))
    return img, (at[0], at[1], w, h)


def _read(graph, img: Image.Image, box: tuple[int, int, int, int]):
    """What the minimap reader makes of the picture cropped to this box (a fresh reader: nothing learned before)."""
    from maplehelper.minimap import Locator
    x, y, w, h = box
    return Locator(graph).locate(img.crop((x, y, x + w, y + h)))


def test_live_grab_gives_the_window_box():
    """The live grab (the game's top-left 40% x 45% with the OS caption; Kerning City's bricks, NPC names and a leaf
    on the window's top edge around it): the whole window's box, and the very same box again on the next call and
    on a fresh copy of the frame (a pixel's jitter between reads would reset the reader)."""
    img = _live()
    box = find_window(img)
    assert box == pytest.approx(LIVE, abs=2)
    assert find_window(img) == box
    assert find_window(img.copy()) == box


@pytest.mark.parametrize("name", list(CROPS))
def test_each_window_in_the_game_gives_its_box(name):
    """Each size the window takes (a map's own) and the folded strip, in the busy game picture where the live window
    was: that window's box, the strip alone when folded."""
    img, want = _on_game(name)
    assert find_window(img) == pytest.approx(want, abs=2)


@pytest.mark.parametrize("at", [(0, 31), (20, 31), (11, 52), (20, 99)])
def test_the_window_is_found_wherever_it_sits_by_the_corner(at):
    """The window right under the OS caption, at the very left, or ~20 px into the game: found there, same size."""
    for name in CROPS:
        img, want = _on_game(name, at)
        assert find_window(img) == pytest.approx(want, abs=2), name


@pytest.mark.parametrize("scale,smooth", [
    (1.0, Image.NEAREST),       # a 1368x800 game window
    (1.25, Image.LANCZOS),
    (1.4, Image.BILINEAR),      # ~1920x1080
    (1.82, Image.BICUBIC),      # an older live capture's UI scale
])
def test_the_window_is_found_at_any_ui_scale(scale, smooth):
    """The game draws its 2x UI in 2x2 blocks, so every other pixel of the live grab is the 1x picture, its window at
    (1, 39), 220 x 217. Scaled smoothly from there (the UI scales with the game's window, blurred between whole
    scales), the box scales with it to within a pixel and a half: no edge is a fixed pixel size."""
    one = Image.fromarray(np.asarray(_live())[1::2, 1::2])
    img = one.resize((round(one.width * scale), round(one.height * scale)), smooth)
    kx, ky = img.width / one.width, img.height / one.height
    got = find_window(img)
    assert got is not None
    x, y, w, h = got
    assert (x, y, x + w, y + h) == pytest.approx((1 * kx, 39 * ky, 221 * kx, 256 * ky), abs=1.5)


def test_an_rgba_picture_is_read_by_its_colours():
    """The owner's screenshots are RGBA: the crop alone gives its window's box."""
    img = Image.open(FIXTURES / "minimap_window_kerning_live.png")
    assert img.mode == "RGBA"
    assert find_window(img) == pytest.approx(CROPS["minimap_window_kerning_live.png"], abs=2)


@pytest.mark.parametrize("name,edges", [
    # Kerning City at the 2x UI, drawn a little outside the window: its white edge spans x 3..442, y 7..440
    ("minimap_kerning_hidden_portal_live.png", (3, 7, 443, 441)),
    # Henesys Market at a 1.56x UI, smoothed by the game's scaling: its white edge blends into the game over columns
    # 0 and 344 and rows 2 and 225 (about half of each, most of row 225)
    ("minimap_henesys_market_live.png", (0.5, 2.5, 344.5, 225.7)),
])
def test_older_live_captures_give_the_window_inside_them(name, edges):
    """Boxes once drawn around the window on live captures, at the game's own scaling (whole and smoothed): the
    window inside them (x0, y0, x1, y1 edges), to within a pixel."""
    got = find_window(Image.open(FIXTURES / name))
    assert got is not None
    x, y, w, h = got
    assert (x, y, x + w, y + h) == pytest.approx(edges, abs=1)


@pytest.mark.parametrize("part", ["right half", "window covered", "bottom rows"])
def test_no_window_is_none(part):
    """The game without the minimap window (the grab's right half; the window covered over; the bottom rows with the
    players and their name tags): nothing, never the nearest orange thing."""
    img = _live()
    pic = {"right half": lambda: img.crop((img.width // 2, 0, img.width, img.height)),
           "window covered": _covered,
           "bottom rows": lambda: img.crop((0, 520, img.width, img.height))}[part]()
    assert find_window(pic) is None


@needs_kb
@pytest.mark.parametrize("name,mid", [
    (None, "010003000"),                                    # the live grab: Kerning City
    ("minimap_window_swamp1_live.png", "010003090"),        # The Swamp of Despair I
    ("minimap_window_swamp2_live.png", "010003091"),        # The Swamp of Despair II
])
def test_the_window_found_reads_as_its_map(graph, name, mid):
    """The picture cropped to the box found is what the minimap reader reads: its title names the map."""
    img = _live() if name is None else _on_game(name)[0]
    here = _read(graph, img, find_window(img))
    assert here is not None and here.map == mid


@needs_kb
def test_the_folded_strip_found_reads_as_its_map(graph):
    """Inside a building the game folds the window to its strip, 'Victoria Road : Niora Hospital': the strip found
    (its box alone, 496 x 40) reads as Niora Hospital, with no map shown to place the dot on."""
    img, want = _on_game("minimap_window_collapsed_live.png")
    box = find_window(img)
    assert box == pytest.approx(want, abs=2)
    here = _read(graph, img, box)
    assert here is not None and here.map == "010003004" and here.spot is None
