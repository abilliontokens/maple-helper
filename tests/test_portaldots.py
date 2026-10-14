"""The hidden-portal dots and the route's arrow over the game's minimap (ui/portaldots.py): placed from each minimap
read's view over the minimap's box (LOCATION.box) and moved with it, hidden when there is nothing to place or their
setting is off; and the dots' Settings switch."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

BOX = {"x": 100, "y": 100, "w": 200, "h": 200}


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
    # (0.0, 0.0), left of a panel starting at x=15. No way known to any other map. Every ask is kept (routed).
    ways = {"020000000": [SimpleNamespace(kind="portal", spot=(0.5, 0.5))], "030000000": [],
            "040000000": [SimpleNamespace(kind="npc", spot=None)],
            "050000000": [SimpleNamespace(kind="portal", spot=(0.0, 0.0))]}

    def route(frm, to, taxi=True, teleport=True):
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
    assert w.isVisible() and w._arrow == QPointF(60, 45) and w._dots
    img = w.grab().toImage()
    c = img.pixelColor(60, 37)                                      # on the shaft, 8 px above the step
    assert c.red() > 200 and c.green() > 120 and c.blue() < 120     # the route's orange, drawn
    d = img.pixelColor(100, 65)
    assert d.blue() > 200 and d.red() < 80                          # a dot beside it, still blue
    assert img.pixelColor(150, 150).alpha() == 0                    # and nothing else


@pytest.mark.parametrize("change", ["setting_off", "no_route", "arrived", "no_way", "no_steps", "no_spot",
                                    "out_of_view", "no_routing"])
def test_no_next_step_to_point_at_hides_the_arrow(dots, kb, monkeypatch, change):
    """The arrow needs its setting, a route picked to a map other than the player's, a way known there and a first
    step with a spot in the minimap's window: without one there is nothing to point at, and with no dots or ring
    either the window hides. A graph that can't route (an older stand-in) places no arrow and breaks nothing."""
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
    elif change == "out_of_view":
        loc.set_route_dest("050000000")                             # its first step is left of the window shown
    else:
        monkeypatch.setattr(portaldots.routes, "of", lambda kb: SimpleNamespace(hidden_spots=lambda m: []))
        w.set_kb(kb)                                                # another KB, its graph one that can't route
    assert not w.isVisible() and w._arrow is None


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


def test_the_switch_is_on_by_default_and_saves(qapp, isolated_store, kb, monkeypatch):
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
        assert dlg.hidden_portals.isChecked() and not dlg.unsaved()
        dlg.hidden_portals.setChecked(False)
        assert dlg.unsaved()
        dlg._save()
        assert s["minimap_hidden_portals"] is False
    finally:
        dlg.close()
