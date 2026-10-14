"""The hidden-portal dots and the route's arrow over the game's minimap (ui/portaldots.py): placed from each minimap
read's view over the minimap's box (LOCATION.box) and moved with it, hidden when there is nothing to place or their
setting is off, the arrow pointing from the panel's edge at a step off the part shown, in the colour and at the size
its settings pick and blinking with its flash setting; and the dots' switch, gone from Settings to the bar's ⚙
panel."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

BOX = {"x": 100, "y": 100, "w": 200, "h": 200}
LIVE_BOX = {"x": 100, "y": 100, "w": 440, "h": 434}     # Kerning City's minimap window, as found live (_live_read)


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def clean_location():
    from maplehelper.ui.location import LOCATION
    old = LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box, LOCATION.route_dest
    LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box = None, "", None, None, None
    LOCATION.route_dest = None
    yield LOCATION
    LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box, LOCATION.route_dest = old


@pytest.fixture
def routed():
    """The ways the dots' stand-in graph was asked for (routes.Graph.route), in order: (from, to, taxi, teleport)."""
    return []


@pytest.fixture
def dots(qapp, isolated_store, kb, clean_location, monkeypatch, routed):
    from maplehelper.ui import portaldots
    spots = {"010003000": [(0.5, 0.5), (0.9, 0.9), (0.0, 0.0)]}
    # the ways from the player's map (routes.Graph.route), by the map picked and the first step's spot there: through
    # a portal at (0.5, 0.5); no step left to take; through an NPC with no spot on the minimap; through a portal at
    # (0.0, 0.0); through a portal at the map's far left (Kerning City's west00 on its way to Henesys, live), off the
    # live view of the map's middle (_live_read). No way known to any other map. Every ask is kept (routed).
    ways = {"020000000": [SimpleNamespace(kind="portal", spot=(0.5, 0.5))], "030000000": [],
            "040000000": [SimpleNamespace(kind="npc", spot=None)],
            "050000000": [SimpleNamespace(kind="portal", spot=(0.0, 0.0))],
            "060000000": [SimpleNamespace(kind="portal", spot=(0.0427, 0.7532))]}

    def route(frm, to, taxi=True, teleport=True, hidden=False):
        routed.append((frm, to, taxi, teleport))
        return SimpleNamespace(legs=ways[to]) if to in ways else None
    monkeypatch.setattr(portaldots.routes, "of", lambda kb: SimpleNamespace(
        hidden_spots=lambda m: spots.get(m, []), route=route))
    s = isolated_store.Settings()
    clean_location.set_box(dict(BOX))        # the minimap window the reads grab, found or drawn
    w = portaldots.PortalDots(kb, s)
    yield w, s, clean_location
    clean_location.changed.disconnect(w.refresh)
    clean_location.followed.disconnect(w.refresh)
    clean_location.guided.disconnect(w.refresh)
    clean_location.routed.disconnect(w.refresh)
    clean_location.boxed.disconnect(w.refresh)
    w.close()


def _here(mid="010003000", panel=(0, 0, 200, 200)):
    from maplehelper.minimap import Here, View
    return Here(mid, (0.3, 0.3), View(10, 20, 100, 50, panel))


def _place(loc, here):
    """A confirmed read that placed its map, as the scanner hands it over: the map, and the follow started there."""
    loc.set(here)
    loc.set_follow((here.map, here.view))


def _live_read(x=-150.0):
    """Kerning City as read live in LIVE_BOX: its picture 643x263 with its top-left at (x, 143), so its left part
    lies off the panel shown from x=10; the player's dot at (0.577, 0.429), at (221, 256) in the box."""
    from maplehelper.minimap import Here, View
    return Here("010003000", (0.577, 0.429), View(x, 143, 643, 263, (10, 142, 430, 406)))


def _near(c, colour: str, tol: int = 2) -> bool:
    """A drawn pixel (a QColor) is this "#RRGGBB" colour, give or take the antialiasing's rounding."""
    from PySide6.QtGui import QColor
    want = QColor(colour)
    return c.alpha() > 0 and all(abs(a - b) <= tol for a, b in ((c.red(), want.red()), (c.green(), want.green()),
                                                               (c.blue(), want.blue())))


def _span(w) -> tuple[int, int]:
    """How wide and how tall the window's drawing is, in its pixels: the arrow's, when it draws nothing else."""
    img = w.grab().toImage()
    drawn = [(x, y) for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x, y).alpha()]
    xs, ys = [x for x, _ in drawn], [y for _, y in drawn]
    return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def test_dots_sit_on_the_box_where_the_map_was_placed(dots, qapp):
    """Each hidden portal in view is a blue dot at its place in the minimap's box; one outside the window shown is
    left out. The window covers the box exactly and never takes a click."""
    from PySide6.QtCore import QPointF, QRect, Qt
    w, _, loc = dots
    _place(loc, _here(panel=(15, 5, 200, 200)))
    assert w.isVisible() and w.geometry() == QRect(100, 100, 200, 200)
    assert w._dots == [QPointF(60, 45), QPointF(100, 65)]          # (0, 0) lands at x=10, left of the panel
    assert w.testAttribute(Qt.WA_TransparentForMouseEvents)
    img = w.grab().toImage()
    c = img.pixelColor(60, 45)
    assert c.blue() > 200 and c.red() < 80                          # a blue dot, drawn
    assert img.pixelColor(150, 150).alpha() == 0                   # and nothing else


@pytest.mark.parametrize("change", ["setting_off", "no_view", "no_read", "no_box", "none_in_view", "other_map"])
def test_nothing_to_place_hides_the_dots(dots, change):
    from maplehelper.minimap import Here
    w, s, loc = dots
    _place(loc, _here())
    assert w.isVisible()
    if change == "setting_off":
        s["minimap_hidden_portals"] = False
        w.refresh()
    elif change == "no_view":
        _place(loc, Here("010003000", (0.3, 0.3)))
    elif change == "no_read":
        loc.set(None)
    elif change == "no_box":
        loc.set_box(None)                               # the minimap window gone, and no box drawn
    elif change == "none_in_view":
        _place(loc, _here(panel=(150, 150, 200, 200)))
    else:
        _place(loc, _here("100000000"))                 # a map with no hidden portals
    assert not w.isVisible() and w._dots == []


def test_a_new_box_moves_the_dots_over_it(dots):
    """The minimap window found elsewhere, or another size (a map with a bigger minimap): the dots' window covers the
    new box at once, the dots at the same place in it."""
    from PySide6.QtCore import QPointF, QRect
    w, _, loc = dots
    _place(loc, _here())
    assert w.geometry() == QRect(100, 100, 200, 200)
    loc.set_box({"x": 40, "y": 60, "w": 260, "h": 230})
    assert w.isVisible() and w.geometry() == QRect(40, 60, 260, 230)
    assert w._dots[0] == QPointF(60, 45)


def test_the_guided_npc_rings_where_the_map_was_placed(dots):
    """A guide rings its NPC green on the game's minimap (wider than the blue dots) from the follow alone: the
    hidden-portal setting gates only the dots, so the ring shows with it off and beside the dots with it on.
    Another map's guide, or none, leaves the window with nothing to draw."""
    from PySide6.QtCore import QPointF

    w, s, loc = dots
    s["minimap_hidden_portals"] = False
    _place(loc, _here())
    assert not w.isVisible()
    loc.set_guide(("010003000", (0.5, 0.5), "npc/303"))
    assert w.isVisible() and w._dots == [] and w._ring == QPointF(60, 45)
    img = w.grab().toImage()
    c = img.pixelColor(60, 38)                            # on the ring, 7 px above its centre
    assert c.green() > 90 and c.red() < 90                # the NPC's green, drawn
    loc.set_guide(("100000000", (0.5, 0.5), "npc/303"))   # a guide for another map: nothing to ring here
    assert not w.isVisible() and w._ring is None
    loc.set_guide(("010003000", (0.5, 0.5), "npc/303"))
    loc.set_guide(None)                                   # guiding stopped: the ring goes with it
    assert not w.isVisible() and w._ring is None
    loc.set_guide(("010003000", (0.5, 0.5), "npc/303"))
    s["minimap_hidden_portals"] = True
    w.refresh()                                           # beside the dots, when they show too
    assert w.isVisible() and w._dots and w._ring == QPointF(60, 45)


def test_the_follow_moves_the_dots_between_reads_and_a_lost_one_hides_them(dots):
    """The fast follow is newer than the read: the dots move with it (the minimap scrolled 5 px left); a follow
    that lost the picture (the loading screen) or sees another map (a teleport not yet confirmed by the reads) hides
    them at once, while the read still names the old map."""
    from PySide6.QtCore import QPointF

    from maplehelper.minimap import View
    w, _, loc = dots
    _place(loc, _here())
    assert w._dots[0] == QPointF(60, 45)
    loc.set_follow(("010003000", View(5, 20, 100, 50, (0, 0, 200, 200))))
    assert w.isVisible() and w._dots[0] == QPointF(55, 45)
    loc.set(_here())                                    # an older read landing after it: the follow still counts
    assert w._dots[0] == QPointF(55, 45)
    loc.set_follow(("010003000", None))
    assert not w.isVisible()
    loc.set_follow(("010003000", View(5, 20, 100, 50, (0, 0, 200, 200))))
    assert w.isVisible()
    loc.set_follow(("100000000", View(5, 20, 100, 50, (0, 0, 200, 200))))
    assert not w.isVisible()


def test_entering_a_shop_never_flashes_the_streets_dots_back(dots):
    """Into a shop: the follow loses the street's picture, then a read names the shop (no minimap picture) and the
    follow is cleared, while the known map is still the street for a read until the shop is confirmed. The street's
    last read view must not bring its dots back meanwhile (they flashed for a second, live)."""
    from maplehelper.minimap import Here
    w, _, loc = dots
    _place(loc, _here())
    assert w.isVisible()
    loc.set_follow(("010003000", None))                 # the loading screen
    assert not w.isVisible()
    loc.set_follow(None)                                # the shop read cleared the follow; the street is still known
    assert loc.here.view is not None and not w.isVisible()
    loc.set(Here("010003001", None))                    # the shop confirmed
    assert not w.isVisible()


def test_the_route_arrow_points_down_at_the_ways_next_step(dots):
    """A route picked to another map (LOCATION.route_dest): an orange arrow on the game's minimap points down at the
    way's first step there (its portal or NPC), its shaft above the step, placed from the follow like the dots and
    drawn over them. Its setting is on by default."""
    from PySide6.QtCore import QPointF
    w, s, loc = dots
    assert s["minimap_route_arrow"] is True
    _place(loc, _here())
    assert w._arrow is None                                         # no route picked: the dots alone
    loc.set_route_dest("020000000")
    assert w.isVisible() and w._arrow == QPointF(60, 45) and w._dots and w._arrow_angle == 0 and not w._arrow_edge
    img = w.grab().toImage()
    c = img.pixelColor(60, 37)                                      # on the shaft, 8 px above the step
    assert c.red() > 200 and c.green() > 120 and c.blue() < 120     # the route's orange, drawn
    d = img.pixelColor(100, 65)
    assert d.blue() > 200 and d.red() < 80                          # a dot beside it, still blue
    assert img.pixelColor(150, 150).alpha() == 0                    # and nothing else


@pytest.mark.parametrize("change", ["setting_off", "no_route", "arrived", "no_way", "no_steps", "no_spot",
                                    "no_routing"])
def test_no_next_step_to_point_at_hides_the_arrow(dots, kb, monkeypatch, change):
    """The arrow needs its setting, a route picked to a map other than the player's, a way known there and a first
    step with a spot on the minimap's picture (in the part shown or not: one off it is pointed at from the panel's
    edge): without one there is nothing to point at, and with no dots or ring either the window hides. A graph that
    can't route (an older stand-in) places no arrow and breaks nothing."""
    from PySide6.QtCore import QPointF

    from maplehelper.ui import portaldots
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrow alone
    loc.set_route_dest("020000000")
    _place(loc, _here(panel=(15, 5, 200, 200)))
    assert w.isVisible() and w._arrow == QPointF(60, 45)
    if change == "setting_off":
        s["minimap_route_arrow"] = False
        w.refresh()
    elif change == "no_route":
        loc.set_route_dest(None)                                    # the route stopped
    elif change == "arrived":
        loc.set_route_dest("010003000")                             # the route's map is the player's own
    elif change == "no_way":
        loc.set_route_dest("990000000")                             # no way known there
    elif change == "no_steps":
        loc.set_route_dest("030000000")                             # a way with no step left to take
    elif change == "no_spot":
        loc.set_route_dest("040000000")                             # its first step isn't on the minimap
    else:
        monkeypatch.setattr(portaldots.routes, "of", lambda kb: SimpleNamespace(hidden_spots=lambda m: []))
        w.set_kb(kb)                                                # another KB, its graph one that can't route
    assert not w.isVisible() and w._arrow is None


def test_a_next_step_off_the_part_shown_is_pointed_at_from_the_panels_edge(dots):
    """The game's minimap often shows only part of the map, and the way's next step can lie off it: Kerning City's
    way to Henesys starts at the portal west00, at x=-123 in the box, left of the panel shown from x=10 (live). The
    arrow still shows, a bigger sign than the mark on a step: just inside the panel's edge, on the line from the
    player's dot toward the step, turned to point out along it (its shaft behind its tip, not above it), and none of
    it past the edge."""
    import math

    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrow alone
    loc.set_box(dict(LIVE_BOX))
    here = _live_read()
    _place(loc, here)
    loc.set_route_dest("060000000")                                 # its first step at (0.0427, 0.7532)
    v = here.view
    me = (v.x + 0.577 * v.w, v.y + 0.429 * v.h)                     # the player's dot: (221, 256)
    step = (v.x + 0.0427 * v.w, v.y + 0.7532 * v.h)                 # the step: (-123, 341), left of the panel
    assert w.isVisible() and w._arrow is not None and w._arrow_edge
    tip = w._arrow
    assert 10 <= tip.x() <= 20                                      # at the panel's left edge, inside it
    assert me[1] < tip.y() < step[1]                                # on the way down-left toward the step
    assert 45 < w._arrow_angle < 135                                # turned from pointing down to pointing left
    n = math.hypot(step[0] - me[0], step[1] - me[1])
    ux, uy = (step[0] - me[0]) / n, (step[1] - me[1]) / n           # that way, one pixel long
    img = w.grab().toImage()
    for back in (4, 16):                        # in the head just behind the tip, and on the shaft further back (right)
        c = img.pixelColor(int(tip.x() - back * ux), int(tip.y() - back * uy))
        assert c.red() > 200 and c.green() > 120 and c.blue() < 120     # the route's orange, drawn
    assert img.pixelColor(int(tip.x()), int(tip.y()) - 16).alpha() == 0    # no shaft above the tip: not pointing down
    assert not any(img.pixelColor(x, y).alpha() for x in range(10) for y in range(434))    # nothing past the edge


def test_the_arrow_moves_between_its_step_and_the_edge_as_the_minimap_scrolls(dots, caplog):
    """The minimap scrolls as the player walks: the step coming into the part shown gets the mark pointing down at
    it, exactly as before, and going off it again the sign at the edge. The log says each change once (a player's
    report tells which they saw), never once a frame."""
    import logging

    from PySide6.QtCore import QPointF
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrow alone
    loc.set_box(dict(LIVE_BOX))
    edge, on = ("route arrow: pointing from the edge: its next step is off the part shown",
                "route arrow: on the minimap")
    with caplog.at_level(logging.INFO, logger="maplehelper"):
        loc.set_route_dest("060000000")
        _place(loc, _live_read())
        assert w.isVisible() and w._arrow_edge
        loc.set_follow(("010003000", _live_read(-145.0).view))      # a frame on, the step still off: along the edge
        assert w.isVisible() and w._arrow_edge
        loc.set_follow(("010003000", _live_read(150.0).view))       # scrolled far enough: the step shows
        assert w.isVisible() and not w._arrow_edge and w._arrow_angle == 0
        assert w._arrow == QPointF(150.0 + 0.0427 * 643, 143 + 0.7532 * 263)    # on the step, pointing down at it
        loc.set_follow(("010003000", _live_read().view))            # and back off it
        assert w.isVisible() and w._arrow_edge
    assert [m for m in caplog.messages if m in (edge, on)] == [edge, on, edge]


def test_the_follow_moves_the_arrow_and_a_lost_one_hides_it(dots):
    """Between reads the arrow moves with the minimap's scroll like the dots (5 px left), and a follow that lost the
    picture (the loading screen) or sees another map hides it at once."""
    from PySide6.QtCore import QPointF

    from maplehelper.minimap import View
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrow alone
    loc.set_route_dest("020000000")
    _place(loc, _here())
    assert w._arrow == QPointF(60, 45)
    loc.set_follow(("010003000", View(5, 20, 100, 50, (0, 0, 200, 200))))
    assert w.isVisible() and w._arrow == QPointF(55, 45)
    loc.set_follow(("010003000", None))
    assert not w.isVisible() and w._arrow is None
    loc.set_follow(("010003000", View(5, 20, 100, 50, (0, 0, 200, 200))))
    assert w.isVisible() and w._arrow == QPointF(55, 45)
    loc.set_follow(("100000000", View(5, 20, 100, 50, (0, 0, 200, 200))))
    assert not w.isVisible() and w._arrow is None


def test_the_arrow_shows_without_the_dots_or_a_guide(dots):
    """The hidden-portal setting gates only the dots, and a guide only the ring: a route alone puts the window up
    with its arrow, and stopping it takes the window down."""
    from PySide6.QtCore import QPointF
    w, s, loc = dots
    s["minimap_hidden_portals"] = False
    _place(loc, _here())
    assert not w.isVisible()                                        # no dots, no guide, no route: nothing to draw
    loc.set_route_dest("020000000")
    assert w.isVisible() and w._dots == [] and w._ring is None and w._arrow == QPointF(60, 45)
    loc.set_route_dest(None)
    assert not w.isVisible() and w._arrow is None


@pytest.mark.parametrize("rides", [False, True])
def test_the_arrows_way_takes_cabs_and_teleports_only_with_the_toolbars_switch(dots, monkeypatch, rides):
    """The arrow points along the way the search's page and the ◎ window draw: on foot, or with cabs and NPC
    teleports when the toolbar's switch says so (settings["game_rides"])."""
    from maplehelper.ui import portaldots
    _, s, loc = dots
    asked = []
    monkeypatch.setattr(portaldots.routes, "of", lambda kb: SimpleNamespace(
        hidden_spots=lambda m: [],
        route=lambda frm, to, taxi=True, teleport=True, hidden=False: asked.append((frm, to, taxi, teleport))))
    s["game_rides"] = rides
    loc.set_route_dest("020000000")
    _place(loc, _here())
    assert asked and set(asked) == {("010003000", "020000000", rides, rides)}


def test_the_arrows_way_is_routed_once_not_on_every_follow_frame(dots, routed, kb):
    """refresh runs on the GUI thread for every follow frame while the minimap scrolls, and Graph.route is a Dijkstra
    search of the whole map graph: the way is routed once for the player's map, the route's map and the toolbar's
    switch, and the frames, reads and other refreshes after only move the arrow along (its setting still takes it
    away and back, and a lost follow still hides it). Another route's map, the switch flipped, the player on another
    map or another KB route it again."""
    from PySide6.QtCore import QPointF

    from maplehelper.minimap import Here, View
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrow alone
    loc.set_route_dest("020000000")
    _place(loc, _here())
    assert w._arrow == QPointF(60, 45) and routed == [("010003000", "020000000", False, False)]
    for x in (9, 8, 7, 6, 5):                                       # the minimap scrolling, frame by frame
        loc.set_follow(("010003000", View(x, 20, 100, 50, (0, 0, 200, 200))))
    loc.set(Here("010003000", (0.4, 0.3), loc.here.view))          # a newer read: the player walked on
    loc.set_box({"x": 40, "y": 60, "w": 260, "h": 230})             # the minimap window found elsewhere
    w.refresh()
    assert w.isVisible() and w._arrow == QPointF(55, 45) and len(routed) == 1
    loc.set_follow(("010003000", None))                             # the picture lost a moment: hidden
    assert not w.isVisible() and w._arrow is None
    loc.set_follow(("010003000", View(5, 20, 100, 50, (0, 0, 200, 200))))
    assert w.isVisible() and w._arrow == QPointF(55, 45)
    s["minimap_route_arrow"] = False                                # the setting off: no arrow, a way kept or not
    w.refresh()
    assert not w.isVisible() and w._arrow is None
    s["minimap_route_arrow"] = True
    w.refresh()
    assert w.isVisible() and w._arrow == QPointF(55, 45) and len(routed) == 1     # never routed again
    s["game_rides"] = True                                          # the toolbar's switch (the app refreshes the dots)
    w.refresh()
    w.refresh()
    assert routed[1:] == [("010003000", "020000000", True, True)]
    loc.set_route_dest("050000000")                                 # a route picked to another map
    loc.set_follow(("010003000", View(4, 20, 100, 50, (0, 0, 200, 200))))
    assert w._arrow == QPointF(4, 20) and routed[2:] == [("010003000", "050000000", True, True)]
    _place(loc, _here("010003001"))                                 # the player on another map
    assert w._arrow == QPointF(10, 20) and routed[3:] == [("010003001", "050000000", True, True)]
    w.set_kb(kb)                                                    # another KB, another graph
    assert w._arrow == QPointF(10, 20) and routed[4:] == [("010003001", "050000000", True, True)]


@pytest.mark.parametrize("name, drawn", [("orange", "orange"), ("blue", "blue"), ("teal", "teal"), ("pink", "pink"),
                                         ("chartreuse", "orange"), (None, "orange"), (["green"], "orange")])
def test_the_arrow_takes_the_colour_its_setting_picks(dots, name, drawn):
    """The bar's ⚙ panel picks the arrow's colour (settings["minimap_arrow_color"]), orange by default as the map
    windows mark a portal: the next refresh paints the arrow in that fill on its dark rim. A name ARROW_COLORS
    doesn't know, or none, keeps the orange; the dots stay blue whatever it is."""
    from maplehelper.ui import portaldots
    w, s, loc = dots
    assert s["minimap_arrow_color"] == "orange"
    assert portaldots.ARROW_COLORS["orange"][1:] == ("#F5B642", "#3A2A05")     # today's orange, on its rim
    loc.set_route_dest("020000000")
    _place(loc, _here())
    s["minimap_arrow_color"] = name
    w.refresh()
    _, fill, rim = portaldots.ARROW_COLORS[drawn]
    img = w.grab().toImage()
    c = img.pixelColor(60, 37)                                      # on the shaft, 8 px above the step
    assert c.alpha() == 255 and _near(c, fill)                      # in the colour picked
    assert _near(img.pixelColor(60, 29), rim, tol=12)               # half over the shaft's top end: its rim
    d = img.pixelColor(100, 65)
    assert d.blue() > 200 and d.red() < 80                          # a dot beside it, still blue


def test_the_arrows_size_setting_draws_it_bigger_or_smaller(dots):
    """The bar's ⚙ panel picks the arrow's size (settings["minimap_arrow_size"]: its length in screen pixels, 22 as
    it always was): the next refresh draws it that much bigger or smaller on the same step, kept within
    ARROW_SIZE_MIN..ARROW_SIZE_MAX; a setting holding no number draws it at the default size."""
    from PySide6.QtCore import QPointF

    from maplehelper.ui import portaldots
    w, s, loc = dots
    lo, hi = portaldots.ARROW_SIZE_MIN, portaldots.ARROW_SIZE_MAX
    assert (lo, hi) == (12, 40) and s["minimap_arrow_size"] == 22
    s["minimap_hidden_portals"] = False                             # the arrow alone
    loc.set_route_dest("020000000")
    _place(loc, _here())
    spans = {}
    for size in (22, hi, lo):
        s["minimap_arrow_size"] = size
        w.refresh()
        assert w._arrow == QPointF(60, 45)                          # on its step whatever its size
        spans[size] = _span(w)
    (w12, h12), (w22, h22), (w40, h40) = spans[lo], spans[22], spans[hi]
    assert w12 < w22 < w40 and h12 < h22 < h40
    assert w40 >= 1.5 * w22 and h40 >= 1.5 * h22                   # 40 px long against 22: near twice the size
    for size, like in ((1000, hi), (3, lo), ("big", 22), (None, 22), (True, 22), (float("nan"), 22)):
        s["minimap_arrow_size"] = size
        w.refresh()
        assert _span(w) == spans[like], size


def test_a_bigger_arrow_at_the_panels_edge_sits_further_in_and_stays_inside_it(dots):
    """The size draws the sign at the panel's edge bigger too, in the colour picked, and pulls its tip in as much
    further as it takes to keep all of it inside the panel: the player's dot by the panel's bottom-left corner,
    Kerning City's way to Henesys leaving off the panel's left (west00), so the arrow points up and left out of the
    corner, its head and shaft reaching down toward the bottom edge."""
    import math

    from maplehelper.minimap import Here
    from maplehelper.ui import portaldots
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrow alone
    s["minimap_arrow_color"] = "purple"
    loc.set_box(dict(LIVE_BOX))
    v = _live_read().view
    loc.set_route_dest("060000000")                                 # its first step at (0.0427, 0.7532): (-123, 341)
    _place(loc, Here("010003000", (0.2644, 0.9772), v))             # the player's dot at (20, 400), by the corner
    assert w.isVisible() and w._arrow_edge
    before = w._arrow
    s["minimap_arrow_size"] = portaldots.ARROW_SIZE_MAX
    w.refresh()
    tip = w._arrow
    assert w._arrow_edge and tip.y() < before.y() - 5               # pulled up off the bottom edge as it grew
    me = (v.x + 0.2644 * v.w, v.y + 0.9772 * v.h)
    step = (v.x + 0.0427 * v.w, v.y + 0.7532 * v.h)
    n = math.hypot(step[0] - me[0], step[1] - me[1])
    ux, uy = (step[0] - me[0]) / n, (step[1] - me[1]) / n           # the way it points, one pixel long
    img = w.grab().toImage()
    c = img.pixelColor(int(tip.x() - 30 * ux), int(tip.y() - 30 * uy))     # on its shaft 30 px back: past 22 px
    assert c.alpha() == 255 and _near(c, portaldots.ARROW_COLORS["purple"][1])
    x0, y0, x1, y1 = v.panel
    assert not any(img.pixelColor(x, y).alpha() for x in range(img.width()) for y in range(img.height())
                   if not (x0 <= x < x1 and y0 <= y < y1))          # none of it outside the panel


def test_the_arrow_blinks_with_its_flash_setting_and_nothing_else_does(dots):
    """With its flash setting on (off by default), a timer on the window hides the arrow and shows it again every
    FLASH_MS, to catch the eye on a busy minimap: the dots and the guided NPC's ring stay drawn throughout, and the
    refresh of every follow frame keeps the beat going rather than restart it. The setting off, or no arrow to
    show, stops the timer with the arrow shown, so no redraw leaves it hidden."""
    from maplehelper.ui import portaldots
    w, s, loc = dots
    assert s["minimap_arrow_flash"] is False
    loc.set_route_dest("020000000")
    _place(loc, _here())
    loc.set_guide(("010003000", (0.9, 0.9), "npc/303"))            # its ring around the dot at (100, 65)
    timer = w._flash_timer

    def arrow_drawn() -> bool:
        """The arrow on its shaft, 8 px above its step; the dot and the ring are drawn whatever it does."""
        img = w.grab().toImage()
        dot, ring = img.pixelColor(100, 65), img.pixelColor(100, 58)
        assert dot.blue() > 200 and dot.red() < 80                  # the dot, blue
        assert ring.green() > 90 and ring.red() < 90                # the ring 7 px above its centre, green
        return img.pixelColor(60, 37).alpha() > 0

    assert w._arrow is not None and not timer.isActive() and w._flash_on and arrow_drawn()     # no blink by default
    s["minimap_arrow_flash"] = True
    w.refresh()
    assert timer.isActive() and timer.interval() == portaldots.FLASH_MS and arrow_drawn()     # shown first
    timer.timeout.emit()                                            # a beat: hidden
    assert not w._flash_on and not arrow_drawn()
    w.refresh()                                                     # a follow frame meanwhile: the beat goes on
    assert timer.isActive() and not w._flash_on and not arrow_drawn()
    timer.timeout.emit()                                            # the next: shown again
    assert w._flash_on and arrow_drawn()
    timer.timeout.emit()
    s["minimap_arrow_flash"] = False                                # switched off while hidden: shown, and stays
    w.refresh()
    assert not timer.isActive() and w._flash_on and arrow_drawn()
    s["minimap_arrow_flash"] = True
    w.refresh()
    timer.timeout.emit()
    loc.set_route_dest(None)                                        # the route stopped: no arrow left to blink
    assert w.isVisible() and w._arrow is None and not timer.isActive() and w._flash_on
    loc.set_route_dest("020000000")                                 # a route again: blinking again, shown first
    assert timer.isActive() and w._flash_on and arrow_drawn()
    loc.set_follow(("010003000", None))                             # the picture lost: all of it hidden, the blink too
    assert not w.isVisible() and not timer.isActive() and w._flash_on


def test_the_hidden_portal_switch_left_settings_for_the_toolbar_panel(qapp, isolated_store, kb, monkeypatch):
    """The dots are on by default, and their switch is the bar's ⚙ panel's (its Minimap section, beside the route's
    arrow and the overlays in screenshots), which applies at once: Settings keeps none of the three, so its Save
    never puts back what the panel picked meanwhile."""
    from maplehelper import providers
    from maplehelper.ui.dialogs import SettingsDialog
    for name in ("claude", "codex"):
        monkeypatch.setattr(type(providers.get(name)), "account",
                            lambda self: {"status": "logged_out", "email": None, "method": None})
        monkeypatch.setattr(type(providers.get(name)), "status", lambda self: "logged_out")
    s = isolated_store.Settings()
    s["language"] = "en"
    s["provider"] = "claude"
    assert s["minimap_hidden_portals"] is True
    dlg = SettingsDialog(s, isolated_store.Profiles(), kb, lambda *_: "")
    try:
        for gone in ("hidden_portals", "route_arrow", "overlay_shots"):
            assert not hasattr(dlg, gone), gone
        s["minimap_hidden_portals"] = False                         # turned off in the panel, Settings still open
        assert not dlg.unsaved()
        dlg._save()
        assert s["minimap_hidden_portals"] is False
    finally:
        dlg.close()
