"""The minimap scanner (ui/minimapscan.py) and its Settings row: reads run on the interval (the minimap window is
found on its own at the game's top left), the box read is published, a bad read is "unknown" (never a crash), and
the interval saves like every other setting."""
import logging
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(qapp, isolated_store, kb, monkeypatch):
    from maplehelper import providers
    # the account checks answer at once: installed but signed out (no CLI, no network)
    for name in ("claude", "codex"):
        monkeypatch.setattr(type(providers.get(name)), "account",
                            lambda self: {"status": "logged_out", "email": None, "method": None})
        monkeypatch.setattr(type(providers.get(name)), "status", lambda self: "logged_out")
    s = isolated_store.Settings()
    s["language"] = "en"
    s["provider"] = "claude"
    before = set(threading.enumerate())
    yield s, isolated_store.Profiles(), kb
    for th in set(threading.enumerate()) - before:
        th.join(timeout=10)


@pytest.fixture
def clean_location():
    from maplehelper.ui.location import LOCATION
    old = LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box, LOCATION.route_dest
    LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box = None, "", None, None, None
    LOCATION.route_dest = None
    yield LOCATION
    LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.box, LOCATION.route_dest = old


@pytest.fixture(autouse=True)
def no_game(monkeypatch):
    """The real screen is never looked at: no game window unless a test puts one there (_Screen)."""
    from maplehelper import gamearea
    monkeypatch.setattr(gamearea.GameArea, "find", lambda self: None)


def _make_scanner(s, kb):
    from maplehelper.ui.minimapscan import MinimapScanner
    return MinimapScanner(kb, s)


BOX = {"x": 10, "y": 20, "w": 100, "h": 50}


def test_the_reads_run_on_their_own(env, clean_location, qapp, monkeypatch):
    """The minimap window is found on its own: a restart starts the reads and the follow, and keeps the player where
    they were."""
    from types import SimpleNamespace

    from maplehelper.minimap import Here
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        clean_location.set(Here("010001000", (0.5, 0.5)))
        sc.restart()
        assert clean_location.here == Here("010001000", (0.5, 0.5))
        assert sc._timer.isActive() and sc._timer.interval() == 1000 and sc._follow_timer.isActive()
        made = []
        monkeypatch.setattr(threading, "Thread",
                            lambda target=None, args=(), **k: SimpleNamespace(start=lambda: made.append(target.__name__)))
        sc._tick()
        assert made == ["_read"]
    finally:
        sc.stop()


def test_the_reads_run_on_the_interval(env, clean_location, qapp):
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        assert sc._timer.isActive() and sc._timer.interval() == 1000
        s["minimap_scan_interval"] = 2.5
        sc.restart()
        assert sc._timer.interval() == 2500
    finally:
        sc.stop()


def test_the_interval_is_clamped(env, clean_location, qapp):
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        for value, ms in ((0.01, 200), (600.0, 60000), ("junk", 1000), (None, 1000), (float("nan"), 1000)):
            s["minimap_scan_interval"] = value
            sc.restart()
            assert sc._timer.interval() == ms, value
    finally:
        sc.stop()


def test_a_kb_update_drops_the_locator(env, clean_location, qapp):
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc._locator, sc._graph = object(), object()
        sc.set_kb(kb)
        assert sc._locator is None and sc._graph is None
    finally:
        sc.stop()


def test_restart_resets_the_locator_lock(env, clean_location, qapp):
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        resets = []
        sc._locator = type("L", (), {"reset": lambda self: resets.append(1)})()
        sc.restart()
        assert resets == [1]
    finally:
        sc.stop()


def test_a_tick_skips_while_a_read_runs(env, clean_location, qapp, monkeypatch):
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        made = []

        class FakeThread:
            def __init__(self, *a, **k):
                made.append(1)

            def start(self):
                pass

        monkeypatch.setattr(threading, "Thread", FakeThread)
        sc._reading = True
        sc._tick()
        assert made == []
        sc._reading = False
        sc._tick()
        assert made == [1]
    finally:
        sc.stop()


class _Locator:
    def __init__(self, answer):
        self.answer = answer

    def locate(self, img):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def reset(self):
        pass


class _Graph:
    def name(self, mid):
        return "Henesys"


def test_an_answer_reaches_location(env, clean_location, qapp, monkeypatch, caplog):
    from maplehelper.minimap import Here
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        sc._locator, sc._graph = _Locator(Here("010001000", (0.5, 0.5))), _Graph()
        _Screen(monkeypatch, GAME, (4, 30, 300, 200))
        with caplog.at_level(logging.INFO, logger="maplehelper"):
            sc._read()
            assert clean_location.here == Here("010001000", (0.5, 0.5)) and clean_location.state == ""
            sc._read()                      # the same map again: logged once, not twice
        named = [r for r in caplog.records
                 if r.name == "maplehelper" and r.levelno == logging.INFO and "Henesys" in r.getMessage()]
        assert len(named) == 1
    finally:
        sc.stop()


def test_an_unrecognized_minimap_reads_as_unknown(env, clean_location, qapp, monkeypatch):
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        sc._locator, sc._graph = _Locator(None), _Graph()
        _Screen(monkeypatch, GAME, (4, 30, 300, 200))
        sc._read()
        assert clean_location.here is None and clean_location.state == "unknown"
    finally:
        sc.stop()


def test_a_failed_read_logs_once_and_reads_unknown(env, clean_location, qapp, monkeypatch, caplog):
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        sc._locator, sc._graph = _Locator(RuntimeError("boom")), _Graph()
        _Screen(monkeypatch, GAME, (4, 30, 300, 200))
        with caplog.at_level(logging.WARNING, logger="maplehelper"):
            sc._read()
            sc._read()                      # the same error again: logged once, not twice
            assert clean_location.here is None and clean_location.state == "unknown"
            assert clean_location.box == WINDOW     # the box it was reading
        warnings = [r for r in caplog.records
                    if r.name == "maplehelper" and r.levelno == logging.WARNING and "boom" in r.getMessage()]
        assert len(warnings) == 1
    finally:
        sc.stop()


def test_misses_back_off_and_hits_reset(env, clean_location, qapp, monkeypatch):
    from maplehelper.minimap import Here
    from maplehelper.ui import minimapscan
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        s["minimap_scan_interval"] = 1.0
        sc.restart()
        sc._locator, sc._graph = _Locator(None), _Graph()
        _Screen(monkeypatch, GAME, (4, 30, 300, 200))
        now = [1000.0]
        monkeypatch.setattr(minimapscan.time, "monotonic", lambda: now[0])
        started = []

        class FakeThread:
            def __init__(self, *a, **k):
                started.append(1)

            def start(self):
                pass

        monkeypatch.setattr(threading, "Thread", FakeThread)
        sc._read()                              # a miss: unknown, and no read for max(5 s, 5 x 1 s)
        assert clean_location.state == "unknown" and sc._cooldown_until == 1005.0
        sc._tick()
        assert started == [] and not sc._reading
        now[0] = 1004.9
        sc._tick()
        assert started == []
        now[0] = 1005.0
        sc._tick()
        assert started == [1] and sc._reading
        sc._reading = False
        sc._locator = _Locator(Here("010001000", (0.5, 0.5)))
        sc._read()                              # a hit: back to reading every interval
        assert sc._cooldown_until == 0.0
        sc._tick()
        assert started == [1, 1]
    finally:
        sc.stop()


def test_the_follow_runs_only_for_dots_and_a_loss_starts_one_read(env, clean_location, qapp, monkeypatch):
    """The fast follow runs only while the dots have something to show (the setting on, hidden portals on the
    map). Its answers reach LOCATION.follow; losing the picture (a teleport) starts a whole read at once, once per
    loss, not every 100 ms while the loading screen lasts."""
    from types import SimpleNamespace

    from maplehelper.minimap import Here, View
    from maplehelper.ui import minimapscan
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        assert sc._follow_timer.isActive()
        sc._box = dict(BOX)                                 # the box the last read used: the follow grabs it
        spots = {"010003000": [(0.5, 0.5)]}
        sc._locator = _Locator(None)
        sc._graph = SimpleNamespace(hidden_spots=lambda m: spots.get(m, []), name=lambda m: m)
        started = []

        class FakeThread:
            def __init__(self, target=None, args=(), **k):
                self.target = target

            def start(self):
                started.append(self.target.__name__)

        monkeypatch.setattr(threading, "Thread", FakeThread)
        clean_location.set(Here("100000000", None))         # no hidden portals here: no follow
        sc._follow_tick()
        assert started == []
        clean_location.set(Here("010003000", None))
        s["minimap_hidden_portals"] = False
        sc._follow_tick()
        assert started == []
        s["minimap_hidden_portals"] = True
        sc._follow_tick()
        sc._follow_tick()                                   # still going: no second one
        assert started == ["_follow"]
        sc._following = False
        view = View(1, 2, 30, 40, (0, 0, 100, 50))
        assert sc._follow_timer.interval() == minimapscan.FOLLOW_IDLE_MS
        # the minimap moved: the next follow starts at once (at 100 ms, then 50, the dots trailed each scroll step
        # and snapped after it, live), and still so through a pause between the game's scroll steps
        sc._on_followed(("010003000", view))
        assert clean_location.follow == ("010003000", view) and started == ["_follow"] * 2
        sc._following = False
        sc._on_followed(("010003000", view))
        assert started == ["_follow"] * 3
        sc._following = False
        sc._moved_at -= minimapscan.FOLLOW_HOLD_S            # stood still FOLLOW_HOLD_S: back to the timer's pace
        sc._on_followed(("010003000", view))
        assert started == ["_follow"] * 3 and sc._follow_timer.interval() == minimapscan.FOLLOW_IDLE_MS
        sc._on_followed(("010003000", None))                 # lost: one whole read now, no follow chained
        sc._on_followed(("010003000", None))
        assert clean_location.follow == ("010003000", None) and started == ["_follow"] * 3 + ["_read"]
        sc._reading = False
        sc._on_followed(("010003000", view))                 # found again, then lost again: another read
        sc._on_followed(("010003000", None))
        assert started == ["_follow"] * 3 + ["_read", "_follow", "_read"]
        sc._on_followed(("010003000", view))
        sc._on_followed(None)                               # nothing locked: no stale follow left behind
        assert clean_location.follow is None
    finally:
        sc.stop()


def test_the_follow_also_runs_while_a_guide_is_on_the_players_map(env, clean_location):
    """The fast follow keeps the guided NPC's ring placed on the game's minimap too (ui/portaldots.py), hidden
    portals or not; a guide for another map keeps nothing running."""
    from types import SimpleNamespace

    from maplehelper.minimap import Here
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc._graph = SimpleNamespace(hidden_spots=lambda m: [], name=lambda m: m)
        clean_location.set(Here("010003000", None))
        assert not sc._wants_follow()                      # nothing to follow for: no portals, no guide
        clean_location.set_guide(("010003000", (0.5, 0.5), "npc/303"))
        assert sc._wants_follow()                          # the ring needs the follow to stay placed
        s["minimap_hidden_portals"] = False
        assert sc._wants_follow()                          # the dots' setting off: the guide keeps it running
        s["minimap_hidden_portals"] = True
        clean_location.set_guide(("100000000", (0.5, 0.5), "npc/303"))
        assert not sc._wants_follow()                      # a guide elsewhere rings nothing here
        clean_location.set_guide(None)
        assert not sc._wants_follow()
    finally:
        sc.stop()


def test_the_follow_also_runs_while_a_route_leads_off_the_players_map(env, clean_location):
    """The fast follow keeps the route's arrow placed on the game's minimap too (ui/portaldots.py), hidden portals
    or not: while a route is picked to another map and the arrow's setting is on. Arrived (the route's map is the
    player's), the setting off, or no route: nothing keeps it running."""
    from types import SimpleNamespace

    from maplehelper.minimap import Here
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc._graph = SimpleNamespace(hidden_spots=lambda m: [], name=lambda m: m)
        clean_location.set(Here("010003000", None))
        assert not sc._wants_follow()                      # nothing to follow for: no portals, no guide, no route
        clean_location.set_route_dest("020000000")
        assert sc._wants_follow()                          # the arrow needs the follow to stay placed
        s["minimap_hidden_portals"] = False
        assert sc._wants_follow()                          # the dots' setting off: the route keeps it running
        s["minimap_route_arrow"] = False
        assert not sc._wants_follow()                      # the arrow's setting off: nothing to place
        s["minimap_route_arrow"] = True
        clean_location.set_route_dest("010003000")
        assert not sc._wants_follow()                      # arrived: the route's map is the player's
        clean_location.set_route_dest(None)
        assert not sc._wants_follow()
    finally:
        sc.stop()


def test_a_placed_read_starts_the_follow_but_never_overrides_a_live_one(env, clean_location, qapp):
    """The dots draw from the follow only, so a confirmed read that placed its map starts it there: the first
    read, and one after the follow lost the picture. A live follow of that map is newer than the read's picture and
    stays (overwriting it jumped the dots back mid-walk). A read with no placing starts nothing."""
    from maplehelper.minimap import Here, View
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        sc._graph = _Graph()
        read_view, live = View(1, 2, 30, 40, (0, 0, 100, 50)), View(9, 2, 30, 40, (0, 0, 100, 50))
        sc._deliver(Here("010003000", (0.5, 0.5), read_view), BOX)
        assert clean_location.follow == ("010003000", read_view)
        clean_location.set_follow(("010003000", live))
        sc._deliver(Here("010003000", (0.5, 0.5), read_view), BOX)
        assert clean_location.follow == ("010003000", live)
        clean_location.set_follow(("010003000", None))       # lost: the next placed read takes over
        sc._deliver(Here("010003000", (0.5, 0.5), read_view), BOX)
        assert clean_location.follow == ("010003000", read_view)
        clean_location.set_follow(None)
        sc._deliver(Here("010003000", None), BOX)
        assert clean_location.follow is None
    finally:
        sc.stop()


def test_a_known_map_is_never_dropped_for_unreadable_reads(env, clean_location, qapp, monkeypatch):
    """Reads without a readable title (a bubble over the header, a loading screen) keep the known map, however long
    they last (the owner's, 2026-10-08: "not recognized" and back every few seconds reset the way mid-walk); past
    the grace they only slow the reads to max(2 s, 2 reads)."""
    from maplehelper.minimap import Here
    from maplehelper.ui import minimapscan
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        s["minimap_scan_interval"] = 1.0
        sc.restart()
        now = [500.0]
        monkeypatch.setattr(minimapscan.time, "monotonic", lambda: now[0])
        perion = Here("010004000", (0.3, 0.4))
        sc._deliver(perion, BOX)
        sc._deliver(None, BOX)
        assert clean_location.here == perion and clean_location.state == "" and sc._cooldown_until == 0.0
        now[0] = 503.0
        sc._deliver(None, BOX)                 # past the grace: still Perion, reads slow a little
        assert clean_location.here == perion and clean_location.state == ""
        assert sc._cooldown_until == 505.0
        now[0] = 900.0
        sc._deliver(None, BOX)
        assert clean_location.here == perion and clean_location.state == ""
        sc._deliver(perion, BOX)               # read again: back to every interval
        assert sc._cooldown_until == 0.0
    finally:
        sc.stop()


def test_another_map_needs_two_reads_in_a_row(env, clean_location, qapp, monkeypatch):
    """One read naming another map (a misread) doesn't move the player; two in a row do."""
    from maplehelper.minimap import Here
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        site, road, kerning = Here("010003010", (0.5, 0.5)), Here("088000000", None), Here("010003000", None)
        sc._deliver(site, BOX)                 # the first map known counts at once
        assert clean_location.here == site
        sc._deliver(road, BOX)                 # a lone misread: ignored
        assert clean_location.here == site
        sc._deliver(site, BOX)                 # back: the misread is forgotten
        sc._deliver(road, BOX)
        assert clean_location.here == site
        sc._deliver(None, BOX)                 # a miss between doesn't count as a second read of it either
        sc._deliver(kerning, BOX)
        assert clean_location.here == site
        sc._deliver(kerning, BOX)              # two reads in a row: moved
        assert clean_location.here == kerning
    finally:
        sc.stop()


def test_restart_clears_the_backoff_and_failures_back_off(env, clean_location, qapp, monkeypatch):
    from maplehelper.ui import minimapscan
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        s["minimap_scan_interval"] = 10.0     # the backoff is max(5 s, 5 x 10 s) = 50 s
        sc.restart()
        now = [2000.0]
        monkeypatch.setattr(minimapscan.time, "monotonic", lambda: now[0])
        sc._complain("RuntimeError: boom", BOX)  # a failing read backs off too
        assert sc._cooldown_until == 2050.0 and clean_location.state == "unknown"
        sc.restart()                          # a new interval: read right away
        assert sc._cooldown_until == 0.0
    finally:
        sc.stop()


# --- the minimap window, found on its own -------------------------------------------------------------------------


class _Reader:
    """A locator that keeps every picture a read gave it, and counts its resets (its lock dropped)."""

    def __init__(self, answer):
        self.answer = answer
        self.images = []
        self.resets = 0

    def locate(self, img):
        self.images.append(img)
        return self.answer

    def reset(self):
        self.resets += 1


class _Screen:
    """A fake screen (the real one is never grabbed): the game's picture at `game` (None: no game window), the
    minimap window at `window` in the grab of the game's corner (None: not there). Every grab is kept: noise, `scale`
    times its size (a Retina grab has more pixels than points)."""

    def __init__(self, monkeypatch, game=None, window=None, scale=1):
        from maplehelper import gamearea
        from maplehelper.ui import minimapscan
        self.game, self.window, self.scale = game, window, scale
        self.grabs, self.pictures, self.searched = [], [], []
        monkeypatch.setattr(gamearea.GameArea, "find", lambda _area: self.game)
        monkeypatch.setattr(minimapscan.capture, "grab_image", self.grab)
        monkeypatch.setattr(minimapscan.minimapfind, "find_window", self.find_window)

    def grab(self, x, y, w, h):
        import numpy as np
        from PIL import Image
        noise = np.random.default_rng(len(self.grabs)).integers(0, 256, (h * self.scale, w * self.scale, 3),
                                                                dtype=np.uint8)
        self.grabs.append((x, y, w, h))
        self.pictures.append(Image.fromarray(noise))
        return self.pictures[-1]

    def find_window(self, img):
        self.searched.append(img)
        return self.window


GAME = (100, 50, 1000, 800)                         # the game's picture: its corner searched is (100, 50, 600, 600)
WINDOW = {"x": 104, "y": 80, "w": 300, "h": 200}    # the minimap window found at (4, 30, 300, 200) in that corner


@pytest.mark.parametrize("scale", [1, 2])
def test_the_minimap_window_is_found_at_the_games_top_left(env, clean_location, qapp, monkeypatch, scale):
    """Each read grabs the top-left corner of the game's picture once (its left 60%, top 75%), finds the minimap
    window in it and reads that crop. The window's box, in capture pixels (a Retina grab has twice the pixels), is
    published and is what the fast follow grabs."""
    from types import SimpleNamespace

    import numpy as np

    from maplehelper.minimap import Here
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        screen = _Screen(monkeypatch, GAME, tuple(v * scale for v in (4, 30, 300, 200)), scale)
        here = Here("010003000", (0.5, 0.5))
        sc._locator = _Reader(here)
        sc._graph = SimpleNamespace(hidden_spots=lambda m: [(0.5, 0.5)], name=lambda m: m)
        sc._read()
        assert screen.grabs == [(100, 50, 600, 600)]                 # one grab: the corner
        assert len(screen.searched) == 1 and screen.searched[0] is screen.pictures[0]
        [img] = sc._locator.images
        assert img.size == (300 * scale, 200 * scale)
        corner = np.asarray(screen.pictures[0])
        assert np.array_equal(np.asarray(img), corner[30 * scale:230 * scale, 4 * scale:304 * scale])
        assert clean_location.box == WINDOW and clean_location.here == here
        started = []
        monkeypatch.setattr(threading, "Thread", lambda target=None, args=(), **k:
                            SimpleNamespace(start=lambda: started.append((target.__name__, args[1]))))
        sc._follow_tick()
        assert started == [("_follow", WINDOW)]
    finally:
        sc.stop()


def test_without_a_minimap_window_nothing_is_read_and_no_box_is_published(env, clean_location, qapp, monkeypatch):
    """No minimap window found: nothing is read and LOCATION.box goes back to None (nothing sits over a box that
    isn't there). It is a miss: the known map stays, and with none known the tries back off to max(5 s, 5 x
    interval); with no game open they grab nothing at all."""
    from maplehelper.minimap import Here
    from maplehelper.ui import minimapscan
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        screen = _Screen(monkeypatch, GAME, (4, 30, 300, 200))
        here = Here("010003000", (0.5, 0.5))
        sc._locator, sc._graph = _Reader(here), _Graph()
        sc._read()
        assert clean_location.box == WINDOW and clean_location.here == here
        screen.window = None                    # the game is there, its minimap window isn't
        sc._read()
        assert len(sc._locator.images) == 1 and clean_location.box is None and sc._box is None
        assert clean_location.here == here      # a miss: the known map stays
        clean_location.set(None)
        screen.game = None                      # no game at all
        now = [1000.0]
        monkeypatch.setattr(minimapscan.time, "monotonic", lambda: now[0])
        sc._read()
        assert len(sc._locator.images) == 1 and len(screen.grabs) == 2 and clean_location.box is None
        assert clean_location.state == "unknown" and sc._cooldown_until == 1005.0
    finally:
        sc.stop()


def test_a_new_box_drops_the_locators_lock_once_and_the_same_box_keeps_it(env, clean_location, qapp, monkeypatch):
    """The minimap window changes size with the map (and moves with the game): a read of another box than the last
    one drops the locator's lock on the picture once, and the follow's placing, which was in the old box; the same
    box read again keeps both (no reset every read)."""
    from maplehelper.minimap import Here, View
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        screen = _Screen(monkeypatch, GAME, (4, 30, 300, 200))
        read_view, live = View(1, 2, 30, 40, (0, 0, 300, 200)), View(5, 2, 30, 40, (0, 0, 300, 200))
        sc._locator, sc._graph = _Reader(Here("010003000", (0.5, 0.5), read_view)), _Graph()
        sc._read()
        assert sc._locator.resets == 1 and clean_location.follow == ("010003000", read_view)
        clean_location.set_follow(("010003000", live))
        sc._read()                              # the same box: the lock and the live follow stay
        assert sc._locator.resets == 1 and clean_location.follow == ("010003000", live)
        screen.window = (4, 30, 260, 180)       # another map's smaller window
        sc._read()
        assert sc._locator.resets == 2 and clean_location.box == {"x": 104, "y": 80, "w": 260, "h": 180}
        assert clean_location.follow == ("010003000", read_view)     # the read's own placing, in the new box
        sc._read()
        assert sc._locator.resets == 2
        screen.game = (120, 50, 1000, 800)      # the game moved: the same window elsewhere
        sc._read()
        assert sc._locator.resets == 3 and clean_location.box == {"x": 124, "y": 80, "w": 260, "h": 180}
    finally:
        sc.stop()


def test_the_game_window_and_each_new_minimap_window_size_log_once(env, clean_location, qapp, monkeypatch, caplog):
    """The reads run all the time and the log stays quiet: the game window appearing and going logs once each, the
    minimap window once per size it is found at (a map change), never once a read."""
    from maplehelper.minimap import Here
    s, _, kb = env
    sc = _make_scanner(s, kb)
    try:
        sc.restart()
        screen = _Screen(monkeypatch, None, (4, 30, 300, 200))
        sc._locator, sc._graph = _Reader(Here("010003000", (0.5, 0.5))), _Graph()
        with caplog.at_level(logging.INFO, logger="maplehelper"):
            sc._read()                          # no game yet: nothing to say
            screen.game = GAME
            sc._read()
            sc._read()
            screen.window = (4, 30, 260, 180)
            sc._read()
            sc._read()
            screen.game = None
            sc._read()
            sc._read()
        said = [r.getMessage() for r in caplog.records
                if r.name == "maplehelper" and r.levelno == logging.INFO and "window" in r.getMessage()]
        assert said == ["minimap: found the game's window, its picture at 100,50 (1000x800)",
                        "minimap: found the minimap window at 104,80 (300x200)",
                        "minimap: found the minimap window at 104,80 (260x180)",
                        "minimap: the game's window is gone"]
    finally:
        sc.stop()


# --- the Settings row ---------------------------------------------------------------------------------------------


def test_the_scan_row_saves_and_detects_changes(env, qapp):
    from maplehelper.ui.controls import Select
    from maplehelper.ui.dialogs import SCAN_CHOICES, SettingsDialog
    s, p, kb = env
    dlg = SettingsDialog(s, p, kb, lambda *_: "")
    try:
        # the app's own pop-up, not a bare number box (the owner's, 2026-10-08)
        assert isinstance(dlg.scan, Select) and dlg.scan.count() == len(SCAN_CHOICES)
        assert dlg.scan.text() == dlg.t("scan_every_1") and not dlg.unsaved()
        dlg.scan.setCurrentIndex(SCAN_CHOICES.index(5.0))
        assert dlg.unsaved()
        dlg._save()                 # stores it (Save closes the dialog, so _initial stays as it was, like every row)
        assert s["minimap_scan_interval"] == 5.0 and not dlg.isVisible()
    finally:
        dlg.close()


def test_the_scan_row_shows_the_nearest_choice(env, qapp):
    from maplehelper.ui.dialogs import SCAN_CHOICES, SettingsDialog
    s, p, kb = env
    for stored, shown in ((600.0, 10.0), (0.2, 0.5), (3.0, 2.0), (float("nan"), 1.0), ("x", 1.0), (-4, 1.0)):
        s["minimap_scan_interval"] = stored
        dlg = SettingsDialog(s, p, kb, lambda *_: "")
        try:
            assert SCAN_CHOICES[dlg.scan.currentIndex()] == shown and not dlg.unsaved(), stored
        finally:
            dlg.close()
