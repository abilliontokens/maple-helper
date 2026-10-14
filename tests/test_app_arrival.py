"""Reaching the map the route arrow points to (app._route_arrived, on LOCATION.changed): the route is let go, so the
arrow on the game's minimap goes, and a toast says so once, naming the map, while its setting
(minimap_arrival_notice) is on; off, the arrow still goes and only the word stays unsaid. Another map, or no read,
leaves the route as it is. The handler runs on a stand-in for the app: its settings, its KB and its toasts."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

HENESYS = "100000000"
NAMES = {HENESYS: "Henesys"}      # the stand-in route graph's names (routes.Graph.name)


@pytest.fixture
def location():
    """LOCATION with no route picked, each route change it sends (LOCATION.routed) kept in order; the route put back
    as it was after."""
    from maplehelper.ui.location import LOCATION
    old, LOCATION.route_dest = LOCATION.route_dest, None
    sent = []

    def keep(dest):
        sent.append(dest)
    LOCATION.routed.connect(keep)
    yield LOCATION, sent
    LOCATION.routed.disconnect(keep)
    LOCATION.route_dest = old


@pytest.fixture
def app(monkeypatch):
    """What _route_arrived reads off the app, on a bare stand-in: its settings (English, the word on), its KB, whose
    route graph names the maps (routes.of stood in, for the app's own KB only: from any other the word would name
    the map by its id), and its toasts, collected."""
    from maplehelper import routes
    me = SimpleNamespace(settings={"language": "en", "minimap_arrival_notice": True}, kb=SimpleNamespace(), toasts=[])
    me.toast = lambda title, message="", timeout_ms=5000, on_click=None: me.toasts.append((title, message))
    graph = SimpleNamespace(name=lambda mid: NAMES.get(mid, mid))      # as routes.Graph.name: the id when unknown
    monkeypatch.setattr(routes, "of", lambda kb: graph if kb is me.kb else None)
    return me


def _here(mid: str, spot=(0.5, 0.5)):
    from maplehelper.minimap import Here
    return Here(mid, spot)


def _read(me, here) -> None:
    """A read handed to the app as LOCATION.changed hands it: the app's own method, called unbound on the stand-in."""
    from maplehelper.app import MapleHelperApp
    MapleHelperApp._route_arrived(me, here)


def test_arriving_lets_the_route_go_and_says_so_once(app, location):
    loc, sent = location
    loc.route_dest = HENESYS
    _read(app, _here(HENESYS))
    assert loc.route_dest is None and sent == [None]        # through LOCATION: the arrow and the way views follow
    assert app.toasts == [("You're there — Henesys", "The route arrow is off.")]
    _read(app, _here(HENESYS, (0.6, 0.5)))                  # the next read there, the dot moved: no route left to end
    assert loc.route_dest is None and sent == [None] and len(app.toasts) == 1


def test_with_the_word_off_the_route_still_goes(app, location):
    """The setting governs the toast only: the arrow must not outlive the arrival."""
    loc, sent = location
    app.settings["minimap_arrival_notice"] = False
    loc.route_dest = HENESYS
    _read(app, _here(HENESYS))
    assert loc.route_dest is None and sent == [None] and app.toasts == []


def test_another_map_keeps_the_route_and_says_nothing(app, location):
    loc, sent = location
    loc.route_dest = HENESYS
    _read(app, _here("104000000"))                          # on the way, not there yet
    assert loc.route_dest == HENESYS and sent == [] and app.toasts == []


def test_no_read_or_no_route_does_nothing(app, location):
    """No read (the minimap not found, or not recognized) ends no route; a read with no route picked says nothing."""
    loc, sent = location
    loc.route_dest = HENESYS
    _read(app, None)
    assert loc.route_dest == HENESYS and sent == [] and app.toasts == []
    loc.route_dest = None
    _read(app, _here(HENESYS))
    assert loc.route_dest is None and sent == [] and app.toasts == []


def test_a_name_that_cant_be_looked_up_names_the_map_by_its_id(app, location, monkeypatch):
    """The route graph failing (a KB that won't load) never keeps the arrow up: the route goes, and the word names
    the map by its id."""
    from maplehelper import routes

    def broken(kb):
        raise ValueError("routes.json unreadable")
    monkeypatch.setattr(routes, "of", broken)
    loc, sent = location
    loc.route_dest = HENESYS
    _read(app, _here(HENESYS))
    assert loc.route_dest is None and sent == [None]
    assert app.toasts == [(f"You're there — {HENESYS}", "The route arrow is off.")]


def test_in_hebrew_the_maps_english_name_stays_one_block(app, location):
    """The name is laid out left to right inside the Hebrew sentence (bidi.ltr_block), as map names are elsewhere."""
    from maplehelper import bidi
    loc, _ = location
    app.settings["language"] = "he"
    loc.route_dest = HENESYS
    _read(app, _here(HENESYS))
    assert loc.route_dest is None and len(app.toasts) == 1
    assert f"{bidi.LRI}Henesys{bidi.PDI}" in app.toasts[0][0]
