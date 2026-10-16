"""The hidden-portal dots, the guided NPC's ring and arrow, and the route's arrow over the game's minimap
(ui/portaldots.py): placed from each minimap read's view over the minimap's box (LOCATION.box) and moved with it,
hidden when there is nothing to place or their setting is off, an arrow pointing from the panel's edge at a step or
an NPC off the part shown, the route's in the colour its setting picks and the NPC's in the ring's green, both at the
size picked, with a name beside each saying what to click there, and blinking together with the flash setting;
how many maps are still to go on a strip just under the minimap box (the window grown by its height alone,
the strip above the box for a minimap at the foot of its screen), the way worked out again said there after a
stray, and the arrow going quiet on another map with Guide the whole way off; and the dots' switch, gone from
Settings to the bar's ⚙ panel."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

BOX = {"x": 100, "y": 100, "w": 200, "h": 200}
LIVE_BOX = {"x": 100, "y": 100, "w": 440, "h": 434}     # Kerning City's minimap window, as found live (_live_read)
LONG_NAME = "Sleepywood Dungeon: Another Entrance to the Ant Tunnel"     # a map's name past the tag's 18 characters


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def clean_location():
    from maplehelper.ui.location import LOCATION
    old = (LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box, LOCATION.route_dest,
           LOCATION.journey)
    LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box = None, "", None, None, None
    LOCATION.route_dest, LOCATION.journey = None, None
    yield LOCATION
    (LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box, LOCATION.route_dest,
     LOCATION.journey) = old


@pytest.fixture
def routed():
    """The ways the dots' stand-in graph was asked for (routes.Graph.route), in order: (from, to, taxi, teleport)."""
    return []




@pytest.fixture
def journeys():
    """The dots' stand-in journey.of (maplehelper/journey.py, which this window alone calls and publishes):
    `answer`, the Journey it gives — one object, or a callable of the player's map — and `asked`, every ask in
    order: (the player's map, the map picked, cabs & teleports, the journey published last)."""
    return SimpleNamespace(answer=None, asked=[])


def _journey(dest="020000000", left=2, off=False, arrived=False):
    """A journey as journey.of answers one, with as many maps left as a test wants."""
    from maplehelper.journey import Journey
    return Journey(dest=dest, legs=tuple(range(left)), left=left, off=off, arrived=arrived)


@pytest.fixture
def dots(qapp, isolated_store, kb, clean_location, monkeypatch, routed, journeys):
    from maplehelper.routes import Leg
    from maplehelper.ui import portaldots
    spots = {"010003000": [(0.5, 0.5), (0.9, 0.9), (0.0, 0.0)]}
    # the ways from the player's map (routes.Graph.route), by the map picked, and their first steps (routes.Leg):
    # through a portal at (0.5, 0.5) into Bush Road; no step left to take; through an NPC with no spot on the minimap;
    # through a portal at (0.0, 0.0); through a portal at the map's far left into West Road (Kerning City's west00 on
    # its way to Henesys, live), off the live view of the map's middle (_live_read); through a hidden teleport at
    # (0.5, 0.5) into a map with a long name; on an NPC's trip, Shanks at (0.5, 0.5). No way known to any other map.
    # Every ask is kept (routed); the maps' names are what the name beside the arrow says.
    me = "010003000"
    ways = {"020000000": [Leg(me, "010002000", "portal", "east00", spot=(0.5, 0.5))], "030000000": [],
            "040000000": [Leg(me, "040000000", "npc", "Shanks", spot=None)],
            "050000000": [Leg(me, "050000000", "portal", "west01", spot=(0.0, 0.0))],
            "060000000": [Leg(me, "010001000", "portal", "west00", spot=(0.0427, 0.7532))],
            "070000000": [Leg(me, "070000000", "portal", "tp00", spot=(0.5, 0.5), hidden=True)],
            "080000000": [Leg(me, "080000000", "npc", "Shanks", spot=(0.5, 0.5))]}
    names = {"010002000": "Bush Road", "010001000": "West Road", "020000000": "Henesys", "070000000": LONG_NAME}

    def route(frm, to, taxi=True, teleport=True):
        routed.append((frm, to, taxi, teleport))
        return SimpleNamespace(legs=ways[to]) if to in ways else None

    def journey_of(graph, here_map, dest, *, rides, last=None):
        journeys.asked.append((here_map, dest, rides, last))
        return journeys.answer(here_map) if callable(journeys.answer) else journeys.answer
    monkeypatch.setattr(portaldots.journey, "of", journey_of)
    monkeypatch.setattr(portaldots.routes, "of", lambda kb: SimpleNamespace(
        hidden_spots=lambda m: spots.get(m, []), route=route, name=lambda m: names.get(m, m)))
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


def _alpha(img, rect) -> int:
    """How solid the strip under the box is drawn: the alpha of its backing a few pixels inside its left edge,
    clear of its own edging and of the words over it (two translucent draws over each other would read more solid
    than either)."""
    return img.pixelColor(int(rect.left()) + 6, int(rect.center().y())).alpha()


def _pill_alpha(img, rect) -> int:
    """How solid the name beside an arrow is drawn: the alpha of its pill in its rounded end, before its words."""
    return img.pixelColor(int(rect.left() + 2.5), int(rect.center().y())).alpha()


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
    assert not w.isVisible() and w._arrow is None and w._tag is None


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
        route=lambda frm, to, taxi=True, teleport=True: asked.append((frm, to, taxi, teleport))))
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
    s["minimap_arrow_label"] = False                                # ... without its name: _span measures all drawn
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


def test_the_arrows_opacity_setting_fades_the_way_and_nothing_else(dots, journeys):
    """The bar's ⚙ panel picks how solid the way's own marks are drawn (settings["minimap_arrow_opacity"], solid
    as they always were): the arrow and the maps-left strip fade together, so the way can be left on over a minimap
    it would otherwise cover, while the hidden portals' blue dots stay solid — as they stay through the flash — and
    the name beside the arrow keeps its own opacity. The faintest it goes is ARROW_OPACITY_MIN, and a setting
    holding no number draws it solid."""
    from maplehelper.ui import portaldots
    w, s, loc = dots
    s["language"] = "en"
    loc.set_box({"x": 100, "y": 100, "w": 600, "h": 200})           # room for the strip's words
    journeys.answer = _journey(left=3)
    loc.set_route_dest("020000000")
    _place(loc, _here(panel=(0, 0, 600, 200)))
    assert s["minimap_arrow_opacity"] == portaldots.ARROW_OPACITY == 1.0 and portaldots.ARROW_OPACITY_MIN == 0.2
    strip, tag = w._strip.rect, w._tag.rect
    back = portaldots.STRIP_ALPHA                                  # the strip's backing, under the words
    pill = round(255 * portaldots.TAG_ALPHA)                       # the name's pill, a little see-through
    solid = w.grab().toImage()
    assert solid.pixelColor(60, 37).alpha() == 255
    assert _alpha(solid, strip) == pytest.approx(round(255 * back), abs=3)
    assert _pill_alpha(solid, tag) == pytest.approx(pill, abs=3)
    for value, op in ((0.4, 0.4), (0.75, 0.75), (0.0, portaldots.ARROW_OPACITY_MIN), (1000, 1.0), ("half", 1.0),
                      (None, 1.0), (True, 1.0), (float("nan"), 1.0)):
        s["minimap_arrow_opacity"] = value
        w.refresh()
        img = w.grab().toImage()
        assert img.pixelColor(60, 37).alpha() == pytest.approx(round(255 * op), abs=3), value   # the arrow's step
        assert _alpha(img, strip) == pytest.approx(round(255 * back * op), abs=3), value        # the strip with it
        assert _pill_alpha(img, tag) == pytest.approx(pill, abs=3), value          # the name: its own opacity
        assert img.pixelColor(100, 65).alpha() == 255, value                        # a hidden portal's dot: solid


def test_the_names_opacity_setting_fades_the_name_beside_the_arrow_alone(dots, journeys):
    """The name beside the arrow takes an opacity of its own (settings["minimap_arrow_label_opacity"], solid as it
    always was), whatever the arrow's: the pill fades, its words with it, while the arrow, the maps-left strip and
    the hidden portals' dots are drawn as before. A faint name on a solid arrow and a solid name on a faint arrow
    both hold; the same range as the arrow's, and a setting holding no number draws it solid."""
    from maplehelper.ui import portaldots
    w, s, loc = dots
    s["language"] = "en"
    loc.set_box({"x": 100, "y": 100, "w": 600, "h": 200})
    journeys.answer = _journey(left=3)
    loc.set_route_dest("020000000")
    _place(loc, _here(panel=(0, 0, 600, 200)))
    assert s["minimap_arrow_label_opacity"] == 1.0
    strip, tag = w._strip.rect, w._tag.rect
    back, pill = portaldots.STRIP_ALPHA, portaldots.TAG_ALPHA
    for value, op in ((0.4, 0.4), (0.75, 0.75), (0.0, portaldots.ARROW_OPACITY_MIN), (1000, 1.0), ("half", 1.0),
                      (None, 1.0), (True, 1.0), (float("nan"), 1.0)):
        s["minimap_arrow_label_opacity"] = value
        w.refresh()
        img = w.grab().toImage()
        assert _pill_alpha(img, tag) == pytest.approx(round(255 * pill * op), abs=3), value    # the name fades
        assert img.pixelColor(60, 37).alpha() == 255, value                         # the arrow: solid
        assert _alpha(img, strip) == pytest.approx(round(255 * back), abs=3), value  # the strip as it was
        assert img.pixelColor(100, 65).alpha() == 255, value                        # a hidden portal's dot: solid
    s["minimap_arrow_label_opacity"], s["minimap_arrow_opacity"] = 1.0, 0.4        # a solid name on a faint arrow
    w.refresh()
    img = w.grab().toImage()
    assert _pill_alpha(img, tag) == pytest.approx(round(255 * pill), abs=3)
    assert img.pixelColor(60, 37).alpha() == pytest.approx(round(255 * 0.4), abs=3)


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
    FLASH_MS, to catch the eye on a busy minimap: the dots and the guided NPC's ring stay drawn throughout (the NPC's
    own arrow blinks on the same beat), and the refresh of every follow frame keeps the beat going rather than restart
    it. The setting off, or no arrow left to show (the route stopped and the guide let go), stops the timer with the
    arrows shown, so no redraw leaves them hidden."""
    from maplehelper.ui import portaldots
    w, s, loc = dots
    assert s["minimap_arrow_flash"] is False
    loc.set_route_dest("020000000")
    _place(loc, _here())
    loc.set_guide(("010003000", (0.9, 0.9), "npc/303"))            # its ring around the dot at (100, 65)
    timer = w._flash_timer

    def arrow_drawn() -> bool:
        """The route's arrow on its shaft, 8 px above its step; the dot and the ring are drawn whatever it does."""
        img = w.grab().toImage()
        # the dot sampled 2 px below its centre: the guided NPC's arrow has its tip on the NPC's spot, the dot's centre
        dot, ring = img.pixelColor(100, 67), img.pixelColor(100, 58)
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
    loc.set_route_dest(None)                                        # the route stopped: the NPC's arrow blinks on
    assert w._arrow is None and w._npc_arrow is not None and timer.isActive() and not w._flash_on
    loc.set_guide(None)                                             # and the guide let go: no arrow left to blink
    assert w.isVisible() and w._arrow is None and not timer.isActive() and w._flash_on
    loc.set_guide(("010003000", (0.9, 0.9), "npc/303"))
    loc.set_route_dest("020000000")                                 # a route again: blinking again, shown first
    assert timer.isActive() and w._flash_on and arrow_drawn()
    loc.set_follow(("010003000", None))                             # the picture lost: all of it hidden, the blink too
    assert not w.isVisible() and not timer.isActive() and w._flash_on


def test_the_arrow_carries_the_name_of_the_map_its_portal_leads_to(dots):
    """Beside the arrow a small name says what to click there (settings["minimap_arrow_label"], on by default): for
    a portal, the map it leads to (the way's next map, not the route's own), on a pill centred just above the
    shaft's top, the arrow's rim a little see-through with the words in its fill. The arrow is drawn as before, and
    with the setting off it shows without the name."""
    from PySide6.QtCore import QPointF

    from maplehelper.ui import portaldots
    w, s, loc = dots
    assert s["minimap_arrow_label"] is True
    s["minimap_hidden_portals"] = False                             # the arrow alone
    s["language"] = "en"
    loc.set_route_dest("020000000")                                 # Henesys: the way's first portal into Bush Road
    _place(loc, _here())
    tag = w._tag
    assert w._arrow == QPointF(60, 45) and tag is not None and tag.text == "→ Bush Road" and not tag.rtl
    r = tag.rect
    assert abs(r.center().x() - 60) < 0.5 and 26 <= r.bottom() <= 29 and r.top() > 0    # over the shaft's top, y=30
    _, fill, rim = portaldots.ARROW_COLORS["orange"]
    img = w.grab().toImage()
    back = img.pixelColor(int(r.left() + 2.5), int(r.center().y()))     # in its rounded end, before its words
    assert _near(back, rim, tol=4) and abs(back.alpha() - round(portaldots.TAG_ALPHA * 255)) <= 3
    inner = range(int(r.left() + r.height() / 2), int(r.right() - r.height() / 2))     # past its rounded ends
    assert max(img.pixelColor(x, y).red() for x in inner
               for y in range(int(r.top()) + 2, int(r.bottom()) - 1)) > 150    # its words: orange (the rim's red: 58)
    c = img.pixelColor(60, 37)                                      # on the shaft, 8 px above the step
    assert c.alpha() == 255 and _near(c, fill)                      # the arrow as before
    assert all(r.left() - 1 <= x <= r.right() + 1 and r.top() - 1 <= y <= r.bottom() + 1
               for y in range(29) for x in range(200) if img.pixelColor(x, y).alpha())    # above the shaft: the pill
    s["minimap_arrow_label"] = False                                # its setting off: the arrow without it
    w.refresh()
    assert w._tag is None and w._arrow == QPointF(60, 45)
    img = w.grab().toImage()
    assert _near(img.pixelColor(60, 37), fill)
    assert not any(img.pixelColor(x, y).alpha() for y in range(29) for x in range(200))     # nothing above the shaft


@pytest.mark.parametrize("dest, lang", [("070000000", "en"), ("070000000", "he"), ("070000000", None),
                                        ("080000000", "en"), ("080000000", "he")])
def test_a_hidden_teleport_or_an_npc_says_so_beside_the_arrow(dots, dest, lang):
    """A first step through a hidden teleport has words of its own beside the arrow (⚡ and the map it leads to), and
    a cab's, a boat's or an NPC's trip names the NPC to talk to (💬), in the app's language (Hebrew until one is
    picked). The name is a game name: one left-to-right block in a Hebrew line, and past about 18 characters cut
    short with "…", its glyph never."""
    from maplehelper import bidi
    w, s, loc = dots
    s["language"] = lang
    loc.set_route_dest(dest)
    _place(loc, _here())
    tag = w._tag
    assert w._arrow is not None and tag is not None and tag.rtl == (lang != "en")
    glyph, name = ("⚡", LONG_NAME) if dest == "070000000" else ("💬", "Shanks")
    if lang == "en":
        assert tag.text.startswith(glyph + " ")
        shown = tag.text[len(glyph) + 1:]
    else:                                                           # "{name} ⚡": the name first, as Hebrew reads
        after = bidi.PDI + " " + glyph
        assert tag.text.startswith(bidi.LRI) and tag.text.endswith(after)
        shown = tag.text[len(bidi.LRI):-len(after)]
    if name == LONG_NAME:                                           # cut short to about 18 characters, its glyph whole
        assert shown.endswith("…") and LONG_NAME.startswith(shown[:-1]) and 12 <= len(shown) <= 19
    else:
        assert shown == name


def test_the_name_by_the_sign_at_the_panels_edge_stays_inside_the_panel(dots):
    """By the sign at the panel's edge the name sits inward of it, past its tail, and by a corner of the panel too
    (the player's dot by its bottom-left corner, the way leaving off its left, and the biggest arrow, so the biggest
    letters): all of the pill stays inside the panel, slid along the arrow's tail rather than pushed over it, and
    nothing is drawn over the minimap's frame."""
    import math

    from PySide6.QtGui import QPolygonF, QTransform

    from maplehelper.minimap import Here
    from maplehelper.ui import portaldots
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrow alone
    s["language"] = "en"
    loc.set_box(dict(LIVE_BOX))
    v = _live_read().view
    x0, y0, x1, y1 = v.panel
    loc.set_route_dest("060000000")                                 # its first step at (-123, 341), into West Road
    for spot, size in (((0.577, 0.429), 22), ((0.2644, 0.9772), 22), ((0.2644, 0.9772), portaldots.ARROW_SIZE_MAX)):
        s["minimap_arrow_size"] = size
        _place(loc, Here("010003000", spot, v))                     # the player's dot mid-panel, then by the corner
        w.refresh()
        tag, tip = w._tag, w._arrow
        assert w._arrow_edge and tag is not None and tag.text == "→ West Road", (spot, size)
        r = tag.rect
        assert x0 <= r.left() and r.right() <= x1 and y0 <= r.top() and r.bottom() <= y1, (spot, size)    # inside
        arrow = QTransform().rotate(w._arrow_angle).map(
            portaldots._shape(portaldots.EDGE_ARROW_PX, w._arrow_scale / w._ratio)).translated(tip)
        assert not arrow.intersects(QPolygonF(r)), (spot, size)    # clear of the arrow, its head and its tail
        a = math.radians(w._arrow_angle)                            # the way it points: down, turned so
        assert (r.center().x() - tip.x()) * -math.sin(a) + (r.center().y() - tip.y()) * math.cos(a) < 0    # behind it
        img = w.grab().toImage()
        assert not any(img.pixelColor(x, y).alpha() for x in range(img.width()) for y in range(img.height())
                       if not (x0 <= x < x1 and y0 <= y < y1)), (spot, size)    # nothing over the minimap's frame


def test_a_flash_off_beat_leaves_the_name_out_with_the_arrow(dots):
    """The name blinks with the arrow (settings["minimap_arrow_flash"]): a beat that hides the arrow leaves its pill
    out too, so with the arrow alone on the minimap nothing is drawn at all, and the next beat shows both again."""
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrow alone
    s["minimap_arrow_flash"] = True
    loc.set_route_dest("020000000")
    _place(loc, _here())
    timer, r = w._flash_timer, w._tag.rect

    def drawn() -> tuple[bool, bool]:
        """The arrow on its shaft, 8 px above its step, and anything of its pill."""
        img = w.grab().toImage()
        pill = any(img.pixelColor(x, y).alpha() for x in range(int(r.left()), int(r.right()))
                   for y in range(int(r.top()), int(r.bottom())))
        return img.pixelColor(60, 37).alpha() > 0, pill

    assert timer.isActive() and w._flash_on and drawn() == (True, True)
    timer.timeout.emit()                                            # a beat: the arrow hidden, its name with it
    assert not w._flash_on and w._tag is not None
    img = w.grab().toImage()
    assert not any(img.pixelColor(x, y).alpha() for x in range(img.width()) for y in range(img.height()))
    timer.timeout.emit()                                            # the next: both shown again
    assert w._flash_on and drawn() == (True, True)


def test_the_guided_npc_gets_a_green_arrow_on_its_ring(dots):
    """Clicking an NPC (the NPCs-here window, the search's NPC page) whose spot the minimap shows gives it the route's
    step's treatment: the mark pointing down with its tip on the NPC's spot, over the green ring that stays as it
    was. It is drawn in the ring's colours (RING_FILL on RING_RIM) whatever colour the route's arrow is picked, so it
    reads as the NPC and never as a step, and it needs no route."""
    from PySide6.QtCore import QPointF

    from maplehelper.ui import portaldots
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the ring and the NPC's arrow alone
    s["minimap_arrow_color"] = "blue"                               # the route's arrow's colour: never the NPC's
    _place(loc, _here())
    assert not w.isVisible()
    loc.set_guide(("010003000", (0.5, 0.5), "npc/1012100"))         # Athena Pierce, at (60, 45)
    assert w.isVisible() and w._arrow is None and w._ring == QPointF(60, 45)
    assert w._npc_arrow == QPointF(60, 45) and w._npc_arrow_angle == 0 and not w._npc_arrow_edge
    img = w.grab().toImage()
    c = img.pixelColor(60, 37)                                      # on its shaft, 8 px above the NPC
    assert c.alpha() == 255 and _near(c, portaldots.RING_FILL.name())     # the ring's green, not the route's blue
    assert _near(img.pixelColor(60, 29), portaldots.RING_RIM.name(), tol=12)    # half over the shaft's top: its rim
    for x, y in ((60, 51), (53, 45), (66, 45)):                     # the ring below the tip and either side of it
        r = img.pixelColor(x, y)
        assert r.alpha() == 255 and r.green() > 90 and r.red() < 90, (x, y)     # green, as it was


def test_a_guided_npc_off_the_part_shown_is_pointed_at_from_the_panels_edge(dots, caplog):
    """A third of Kerning City is off the minimap's panel at any time (live), and a guide's NPC can stand there: no
    ring then, but the sign at the panel's edge the route's step gets, on the line from the player's dot toward the
    NPC, in the ring's green and all of it inside the panel, the window up for it alone. The minimap scrolling the NPC
    into the part shown brings the ring back with the mark on it, and off again the sign; the log says each change
    once, as for the route's arrow. A follow that lost the picture takes it all away."""
    import logging
    import math

    from PySide6.QtCore import QPointF
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the NPC's arrow alone
    loc.set_box(dict(LIVE_BOX))
    here = _live_read()
    v = here.view
    me = (v.x + 0.577 * v.w, v.y + 0.429 * v.h)                     # the player's dot: (221, 256)
    npc = (v.x + 0.0427 * v.w, v.y + 0.7532 * v.h)                  # the NPC: (-123, 341), left of the panel
    edge, on = "npc arrow: pointing from the edge: the NPC is off the part shown", "npc arrow: on the minimap"
    with caplog.at_level(logging.INFO, logger="maplehelper"):
        _place(loc, here)
        loc.set_guide(("010003000", (0.0427, 0.7532), "npc/1012100"))
        assert w.isVisible() and w._ring is None and w._arrow is None and w._npc_arrow_edge
        tip = w._npc_arrow
        assert 10 <= tip.x() <= 20 and me[1] < tip.y() < npc[1]     # at the panel's left edge, on the way to it
        assert 45 < w._npc_arrow_angle < 135                        # turned from pointing down to pointing left
        n = math.hypot(npc[0] - me[0], npc[1] - me[1])
        ux, uy = (npc[0] - me[0]) / n, (npc[1] - me[1]) / n         # that way, one pixel long
        img = w.grab().toImage()
        for back in (4, 16):                        # in the head just behind the tip, and on the shaft further back
            c = img.pixelColor(int(tip.x() - back * ux), int(tip.y() - back * uy))
            assert c.green() > 90 and c.red() < 90, back            # the ring's green, not the route's orange
        x0, y0, x1, y1 = v.panel
        assert not any(img.pixelColor(x, y).alpha() for x in range(img.width()) for y in range(img.height())
                       if not (x0 <= x < x1 and y0 <= y < y1))     # none of it outside the panel, its name neither
        loc.set_follow(("010003000", _live_read(-145.0).view))      # a frame on, the NPC still off: along the edge
        assert w._ring is None and w._npc_arrow_edge
        loc.set_follow(("010003000", _live_read(150.0).view))       # scrolled far enough: the NPC shows
        spot = QPointF(150.0 + 0.0427 * 643, 143 + 0.7532 * 263)
        assert w._ring == spot and w._npc_arrow == spot and not w._npc_arrow_edge and w._npc_arrow_angle == 0
        loc.set_follow(("010003000", _live_read().view))            # and back off it
        assert w._ring is None and w._npc_arrow_edge
    assert [m for m in caplog.messages if m in (edge, on)] == [edge, on, edge]
    loc.set_follow(("010003000", None))                             # the picture lost: all of it gone
    assert not w.isVisible() and w._npc_arrow is None and w._npc_tag is None


def test_the_guided_npcs_arrow_carries_its_name(dots, kb):
    """Beside the NPC's arrow its name, as beside the route's (settings["minimap_arrow_label"], on by default): 💬 and
    the NPC's name as the KB has it, or its id when the KB has none; a game name, one left-to-right block in a Hebrew
    line and cut short with "…" past about 18 characters; on a pill just above the shaft in the arrow's colours, the
    ring's green on its dark rim a little see-through. With the setting off the arrow shows without it."""
    from PySide6.QtCore import QPointF

    from maplehelper import bidi
    from maplehelper.ui import portaldots
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the ring and the NPC's arrow alone
    s["language"] = "en"
    _place(loc, _here())
    loc.set_guide(("010003000", (0.5, 0.5), "npc/1012100"))         # the fixture KB's Athena Pierce, at (60, 45)
    tag = w._npc_tag
    assert tag is not None and tag.text == "💬 Athena Pierce" and not tag.rtl and w._tag is None
    r = tag.rect
    assert r.left() < 60 < r.right() and r.bottom() <= 29 and r.top() > 0     # over the shaft's top, y=30
    img = w.grab().toImage()
    back = img.pixelColor(int(r.left() + 2.5), int(r.center().y()))     # in its rounded end, before its words
    assert _near(back, portaldots.RING_RIM.name(), tol=4)
    assert abs(back.alpha() - round(portaldots.TAG_ALPHA * 255)) <= 3
    inner = range(int(r.left() + r.height() / 2), int(r.right() - r.height() / 2))     # past its rounded ends
    assert max(img.pixelColor(x, y).green() for x in inner
               for y in range(int(r.top()) + 2, int(r.bottom()) - 1)) > 120    # its words: green (the rim's: 48)
    s["language"] = "he"                                            # "{name} 💬": the name first, as Hebrew reads
    w.refresh()
    assert w._npc_tag.rtl and w._npc_tag.text == bidi.LRI + "Athena Pierce" + bidi.PDI + " 💬"
    s["language"] = "en"
    loc.set_guide(("010003000", (0.5, 0.5), "npc/303"))             # an NPC the KB doesn't have: its id
    assert w._npc_tag.text == "💬 303"
    kb.entities["npc/9100000"] = {"key": "npc/9100000", "id": "9100000", "name": LONG_NAME, "category": "npc"}
    loc.set_guide(("010003000", (0.5, 0.5), "npc/9100000"))         # past 18 characters: cut short, 💬 whole
    text = w._npc_tag.text
    shown = text[len("💬 "):]
    assert text.startswith("💬 ") and shown.endswith("…") and LONG_NAME.startswith(shown[:-1])
    assert 12 <= len(shown) <= 19
    s["minimap_arrow_label"] = False                                # its setting off: the arrow without it
    w.refresh()
    assert w._npc_tag is None and w._npc_arrow == QPointF(60, 45)
    img = w.grab().toImage()
    assert _near(img.pixelColor(60, 37), portaldots.RING_FILL.name())     # the arrow as before
    assert not any(img.pixelColor(x, y).alpha() for y in range(29) for x in range(200))     # nothing above the shaft


def test_the_arrows_setting_off_leaves_the_guided_npc_its_ring_alone(dots):
    """The NPC's arrow goes with the route's arrow's setting (settings["minimap_route_arrow"]): off, an NPC in the
    part shown keeps its ring as it always had, with no arrow or name, and one off the part shown gets nothing (the
    window hides, with nothing else to draw). Switched on again, the sign at the panel's edge points at it."""
    from PySide6.QtCore import QPointF

    from maplehelper.minimap import View
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the NPC's marks alone
    s["minimap_route_arrow"] = False
    _place(loc, _here())
    loc.set_guide(("010003000", (0.5, 0.5), "npc/1012100"))         # at (60, 45)
    assert w.isVisible() and w._ring == QPointF(60, 45) and w._npc_arrow is None and w._npc_tag is None
    img = w.grab().toImage()
    c = img.pixelColor(60, 38)                                      # on the ring, 7 px above its centre
    assert c.green() > 90 and c.red() < 90                          # the NPC's green, drawn
    assert not any(img.pixelColor(x, y).alpha() for y in range(34) for x in range(200))    # no shaft, no name above
    loc.set_follow(("010003000", View(-100, 20, 100, 50, (0, 0, 200, 200))))     # the NPC off the part shown
    assert not w.isVisible() and w._ring is None and w._npc_arrow is None
    s["minimap_route_arrow"] = True
    w.refresh()
    assert w.isVisible() and w._ring is None and w._npc_arrow is not None and w._npc_arrow_edge


def test_a_route_and_a_guide_get_an_arrow_each_in_their_own_colours(dots):
    """A guide here while the route leads to another map: both arrows at once, the route's on its step in the colour
    picked (orange by default) and the NPC's on the NPC in the ring's green, each with its name; where they meet,
    the NPC's is drawn over the route's."""
    from PySide6.QtCore import QPointF

    from maplehelper.ui import portaldots
    w, s, loc = dots
    s["minimap_hidden_portals"] = False                             # the arrows and the ring alone
    loc.set_route_dest("020000000")                                 # its step at (60, 45)
    _place(loc, _here())
    loc.set_guide(("010003000", (0.9, 0.9), "npc/303"))             # the NPC at (100, 65)
    assert w._arrow == QPointF(60, 45) and w._npc_arrow == QPointF(100, 65) and w._ring == QPointF(100, 65)
    assert not w._arrow_edge and not w._npc_arrow_edge and w._tag is not None and w._npc_tag is not None
    img = w.grab().toImage()
    route, npc = img.pixelColor(60, 37), img.pixelColor(100, 53)    # each on its shaft, the NPC's above its ring
    assert route.alpha() == 255 and _near(route, portaldots.ARROW_COLORS["orange"][1])
    assert npc.alpha() == 255 and _near(npc, portaldots.RING_FILL.name())
    loc.set_guide(("010003000", (0.5, 0.5), "npc/303"))             # the NPC on the route's step itself
    assert w._arrow == w._npc_arrow == QPointF(60, 45)
    assert _near(w.grab().toImage().pixelColor(60, 37), portaldots.RING_FILL.name())    # the NPC's over the route's


def test_a_flash_beat_hides_both_arrows_and_their_names_and_nothing_else(dots):
    """With the flash setting on, the NPC's arrow blinks on the route's beat: one timer for both, a beat hiding both
    arrows and their names together while the dots and the NPC's ring stay drawn, the next showing them again."""
    import math

    w, s, loc = dots
    s["minimap_arrow_flash"] = True
    loc.set_route_dest("020000000")                                 # the route's arrow on the dot at (60, 45)
    _place(loc, _here(panel=(15, 5, 200, 200)))                     # the dot at (10, 20) left of the panel
    loc.set_guide(("010003000", (0.9, 0.9), "npc/303"))             # the NPC's, ringed, on the dot at (100, 65)
    timer, pills = w._flash_timer, (w._tag.rect, w._npc_tag.rect)

    def drawn() -> tuple[bool, ...]:
        """Each arrow on its shaft, then anything of each name's pill; the dots and the ring stay whatever they do."""
        img = w.grab().toImage()
        dot, ring = img.pixelColor(60, 47), img.pixelColor(100, 71)     # below the route's tip; below the NPC's
        assert dot.blue() > 200 and dot.red() < 80                  # the dot, blue
        assert ring.green() > 90 and ring.red() < 90                # the ring, green
        names = [any(img.pixelColor(x, y).alpha() for x in range(int(r.left()), int(r.right()))
                     for y in range(int(r.top()), int(r.bottom()))) for r in pills]
        return (img.pixelColor(60, 37).alpha() > 0, img.pixelColor(100, 53).alpha() > 0, *names)

    assert timer.isActive() and w._flash_on and drawn() == (True, True, True, True)
    timer.timeout.emit()                                            # a beat: both arrows hidden, their names too
    assert not w._flash_on and w._arrow is not None and w._npc_arrow is not None
    assert drawn() == (False, False, False, False)
    img = w.grab().toImage()
    assert all(img.pixelColor(x, y).blue() > 200 for x, y in ((60, 45), (100, 65)))     # both dots whole again
    assert all(math.hypot(x + 0.5 - 60, y + 0.5 - 45) <= 5 or math.hypot(x + 0.5 - 100, y + 0.5 - 65) <= 10
               for y in range(img.height()) for x in range(img.width())
               if img.pixelColor(x, y).alpha())                     # nothing but the dots and the ring
    timer.timeout.emit()                                            # the next: all shown again
    assert w._flash_on and drawn() == (True, True, True, True)


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


def test_the_name_pill_names_only_what_the_arrow_points_at(dots, journeys):
    """The count no longer rides on the arrow's name pill: with a journey published and the switch on, the pill
    beside the route's arrow names what the arrow points at and nothing else (the count is under the box,
    _make_strip)."""
    w, s, loc = dots
    s["language"] = "en"
    s["minimap_hidden_portals"] = False
    loc.set_box({"x": 100, "y": 100, "w": 600, "h": 200})           # room on the pill for both, were it to carry it
    journeys.answer = _journey(left=3)
    loc.set_route_dest("020000000")
    _place(loc, _here(panel=(0, 0, 600, 200)))
    assert s["minimap_route_steps"] is True and loc.journey is journeys.answer
    assert w._tag.text == "→ Bush Road"
    assert w._strip is not None and "3 maps to go" in w._strip.text


@pytest.mark.parametrize("left, said", [(3, "3 maps to go"), (1, "Last map")])
def test_the_strip_under_the_box_says_how_many_maps_are_left(dots, journeys, left, said):
    """A strip just under the minimap box carries the count from LOCATION.journey
    (settings["minimap_route_steps"], on by default): the map the player is heading to and how many maps are still
    to pass through, with its own wording on the last one — off the minimap's own picture, which is small and
    busy."""
    w, s, loc = dots
    s["language"] = "en"
    s["minimap_hidden_portals"] = False
    loc.set_box({"x": 100, "y": 100, "w": 600, "h": 200})           # room for the strip's words
    journeys.answer = _journey(left=left)
    loc.set_route_dest("020000000")
    _place(loc, _here(panel=(0, 0, 600, 200)))
    assert loc.journey is journeys.answer
    assert w._strip.text == "Henesys · " + said
    assert w._strip.rect.top() == 200 and w._strip.rect.right() <= 600     # just under the box, inside it across


def test_straying_off_the_way_says_so_on_the_strip(dots, journeys):
    """A wrong portal puts the player off the way, and the journey worked out from where they now stand says so
    (Journey.off): the read after says it on the strip, in place of the count — and never on the pill."""
    w, s, loc = dots
    s["language"] = "en"
    s["minimap_hidden_portals"] = False
    loc.set_box({"x": 100, "y": 100, "w": 600, "h": 200})
    journeys.answer = _journey(left=4, off=True)
    loc.set_route_dest("020000000")
    _place(loc, _here(panel=(0, 0, 600, 200)))
    assert w._strip.text == "Henesys · Off the way — worked it out again from here"
    assert w._tag.text == "→ Bush Road"


@pytest.mark.parametrize("case", ["switch_off", "nothing_armed", "arrived"])
def test_nothing_to_say_draws_no_strip_and_grows_no_window(dots, journeys, case):
    """Nothing to say, nothing drawn: the switch off (settings["minimap_route_steps"]), no route armed, or the
    player already on the map they picked (Journey.arrived, which clears the arrow with it). The window must not
    grow for an empty strip."""
    from PySide6.QtCore import QRect
    w, s, loc = dots
    s["language"] = "en"
    loc.set_box({"x": 100, "y": 100, "w": 600, "h": 200})
    journeys.answer = _journey(left=0, arrived=True) if case == "arrived" else _journey(left=3)
    if case != "nothing_armed":
        loc.set_route_dest("020000000")
    if case == "switch_off":
        s["minimap_route_steps"] = False
    _place(loc, _here(panel=(0, 0, 600, 200)))
    assert w.isVisible() and w._strip is None
    assert w.geometry() == QRect(100, 100, 600, 200)


def test_the_strip_grows_the_window_down_and_moves_nothing_over_the_box(dots, journeys):
    """The window grows down by exactly the strip's height and keeps its top-left, which every mark over the box
    is measured from: the dots, the arrow and its pill are placed where they were without the strip, and every
    pixel drawn over the box is the same pixel."""
    from PySide6.QtCore import QRect
    w, s, loc = dots
    s["language"] = "en"
    loc.set_box({"x": 100, "y": 100, "w": 600, "h": 200})
    journeys.answer = _journey(left=3)
    loc.set_route_dest("020000000")
    _place(loc, _here(panel=(0, 0, 600, 200)))
    h = int(w._strip.rect.height())
    placed, with_strip = (list(w._dots), w._arrow, w._tag.rect), w.grab().toImage()
    assert h > 0 and w._shift == 0.0 and w.geometry() == QRect(100, 100, 600, 200 + h)
    s["minimap_route_steps"] = False
    w.refresh()
    bare = w.grab().toImage()
    assert w._strip is None and w.geometry() == QRect(100, 100, 600, 200)       # the strip's height, and no more
    assert (list(w._dots), w._arrow, w._tag.rect) == placed
    # every row of the box, the one next to the strip included: nothing of the strip may spill onto it
    assert all(with_strip.pixelColor(x, y) == bare.pixelColor(x, y)
               for x in range(0, 600, 3) for y in range(200))


def test_a_minimap_at_the_foot_of_the_screen_puts_the_strip_above_the_box(dots, journeys, qapp):
    """The strip stays on the screen the minimap is on: with no room under the box it goes above it instead, the
    window growing up and every mark over the box — the dots, the arrow, its pill — drawn that much down, so
    each lands over the box exactly where it did without the strip. The strip itself never moves with
    them: it keeps the window's own top rows."""
    from PySide6.QtCore import QPointF, QRect
    w, s, loc = dots
    s["language"] = "en"
    geo = qapp.primaryScreen().geometry()
    box = {"x": geo.x() + 100, "y": geo.y() + geo.height() - 200, "w": 200, "h": 200}
    loc.set_box(box)
    journeys.answer = _journey(left=3)
    loc.set_route_dest("020000000")
    _place(loc, _here(panel=(0, 0, 200, 200)))
    h = int(w._strip.rect.height())
    assert h > 0 and w._strip.rect.top() == 0 and w._shift == float(h)
    assert w.geometry() == QRect(box["x"], box["y"] - h, 200, 200 + h)
    assert w.geometry().bottom() <= geo.bottom()                    # all of it on the screen the minimap is on
    assert w._dots[0] == QPointF(60, 45)                            # placed from the box's top-left as ever ...
    above = w.grab().toImage()
    assert above.pixelColor(int(w._strip.rect.center().x()), int(w._strip.rect.center().y())).alpha()
    s["minimap_route_steps"] = False                                # ... and the same box with no strip at all
    w.refresh()
    assert w._strip is None and w._shift == 0.0 and w.geometry() == QRect(box["x"], box["y"], 200, 200)
    bare = w.grab().toImage()
    # every mark drawn over the box, that much down and nowhere else — and every row of it, the one next to the
    # strip included: the strip keeps the window's own top rows and spills onto none of the box's
    assert all(above.pixelColor(x, y + h) == bare.pixelColor(x, y)
               for x in range(0, 200, 2) for y in range(200))
    assert above.pixelColor(60, 45 + h) == bare.pixelColor(60, 45)      # the dot's own pixel, moved with the rest


def test_with_guiding_the_whole_way_off_the_arrow_goes_quiet_on_another_map(dots, journeys):
    """Guiding the whole way (settings["minimap_route_follow"], on by default) decides what the arrow does once the
    player leaves the map it was armed on: on, the map they picked stands and the way is worked out from wherever
    they are; off, the arrow guides on the map it was armed from alone and goes quiet — journey and all — the
    moment they leave it, and guides again when they come back."""
    from PySide6.QtCore import QPointF
    w, s, loc = dots
    s["minimap_hidden_portals"] = False
    journeys.answer = _journey(left=2)
    loc.set_route_dest("020000000")
    _place(loc, _here())                                            # armed on the player's own map
    assert w._arrow == QPointF(60, 45) and loc.journey is journeys.answer
    _place(loc, _here("010003001"))                                 # walked on: guided the whole way, as it comes
    assert w.isVisible() and w._arrow == QPointF(60, 45) and loc.journey is journeys.answer
    s["minimap_route_follow"] = False
    w.refresh()
    assert not w.isVisible() and w._arrow is None and w._tag is None and loc.journey is None
    _place(loc, _here())                                            # back on the map it was armed on
    assert w.isVisible() and w._arrow == QPointF(60, 45) and loc.journey is journeys.answer


def test_the_journey_is_published_once_per_asked_answer_not_per_frame(dots, journeys, routed):
    """The journey this window publishes is worked out where the arrow's own step is (journey.of costs a search of
    the map graph, and refresh runs for every follow frame while the minimap scrolls): once for the player's map,
    the map picked and the switches, the last answer handed to the next, and cleared the moment there is no
    destination."""
    from maplehelper.minimap import View
    w, s, loc = dots
    s["minimap_hidden_portals"] = False
    first, second = _journey(left=2), _journey(left=1)
    journeys.answer = first
    loc.set_route_dest("020000000")
    _place(loc, _here())
    assert journeys.asked == [("010003000", "020000000", False, None)] and loc.journey is first
    for x in (9, 8, 7, 6):                                          # the minimap scrolling, frame by frame
        loc.set_follow(("010003000", View(x, 20, 100, 50, (0, 0, 200, 200))))
    w.refresh()
    assert len(journeys.asked) == 1 and loc.journey is first        # nothing asked a frame
    journeys.answer = second
    _place(loc, _here("010003001"))                                 # a portal taken: the way from the new map
    assert journeys.asked[1:] == [("010003001", "020000000", False, first)] and loc.journey is second
    loc.set_route_dest(None)                                        # the route stopped: nothing to publish
    assert loc.journey is None and len(journeys.asked) == 2
    assert len(routed) == 2                                         # the arrow's own routing, once a map
