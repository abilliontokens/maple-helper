"""The loot scanner as the grind's run (ui/lootscan.py): each pickup tagged with the map and the player's level; the
bottom bar sampled while the run counts (hud.read_strip); the grind bar's watch starting a run on the first EXP gain;
the player's pause; the names of items logged as one no pickup names repaired when it starts and on a new KB."""
import json
import logging
import os
import sqlite3
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtWidgets import QApplication

from maplehelper import hud, lootdb, lootlog
from maplehelper.minimap import Here
from maplehelper.ui.location import LOCATION

app = QApplication.instance() or QApplication([])
FIXTURES = Path(__file__).parent / "fixtures"
TABLE = {9: 1242, 10: 1716, 11: 2360, 30: 98000}
MAP = "102000000"
BOX = {"x": 0, "y": 0, "w": 300, "h": 200}
MESOS = "You have gained mesos (+27)"
EXP21 = "You received EXP (+21)"
EXP8 = "You received EXP (+8)"
LEAF = "Leaf x1 earned. (Etc)"


@pytest.fixture
def scan(isolated_store, kb, monkeypatch):
    """The scanner of a level 20 character, on MAP as the minimap reads say."""
    from maplehelper.ui.lootscan import LootScanner
    monkeypatch.setattr(LOCATION, "here", Here(MAP))
    p = isolated_store.Profiles()
    p.add("Kiwi", "Magician", "Magician", 20)
    s = LootScanner(kb, p, isolated_store.Settings())
    yield s
    for timer in (s._timer, s._hud_timer, s._save_timer):
        timer.stop()


def _deliver(scan, at: float, *texts: str) -> None:
    """A read of the messages box as it comes back from the worker: `texts` top to bottom (the newest at the bottom,
    each older one a row higher)."""
    n = len(texts)
    scan._deliver([(text, 128.0 - 28.0 * (n - 1 - i), 14.0) for i, text in enumerate(texts)], at, (BOX, "ok"))


def _counted(scan) -> list[tuple[str, int]]:
    return [(e.kind, e.amount) for e in scan._log.events]


# ------------------------------------------------------------ the bottom bar's strip

def test_the_bars_strip_alone_reads_as_the_whole_picture():
    """The scanner grabs only the bottom hud.STRIP of the game's picture: read alone, it gives what hud.read gives on
    the whole picture (tests/test_hud.py's live bar, at the bottom of a 2562x1440 play area)."""
    pytest.importorskip("rapidocr")
    bar = Image.open(FIXTURES / "hud_bar_live.png").convert("RGB")
    img = Image.new("RGB", (2562, 1440), (110, 140, 190))
    img.paste(bar, (0, 1440 - bar.height))
    strip = img.crop((0, int(1440 * (1 - hud.STRIP)), 2562, 1440))
    whole, alone = hud.read(img, TABLE), hud.read_strip(strip, TABLE)
    assert whole is not None and alone is not None
    assert (alone.level, alone.exp, alone.exp_pct, alone.hp) == (whole.level, whole.exp, whole.exp_pct, whole.hp)
    assert (alone.level, alone.exp, alone.exp_pct, alone.hp) == (10, 219, 12.76, (431, 444))


# ------------------------------------------------------------ tags

def test_a_counted_pickup_gets_the_map_and_the_level(scan):
    scan.start()
    t = time.time()
    _deliver(scan, t, MESOS)                                # on screen when the log started: not counted
    _deliver(scan, t + 0.5, MESOS, EXP21)
    (ev,) = scan._log.events
    assert (ev.kind, ev.amount, ev.map, ev.level) == ("exp", 21, MAP, 20)      # (no bar read yet)
    assert not hasattr(ev, "monster")                       # (no kill: a pickup message never says what was killed)
    _deliver(scan, t + 1.0, MESOS, EXP21, "You have gained mesos (+5)")
    mesos = scan._log.events[-1]
    assert (mesos.kind, mesos.amount, mesos.map, mesos.level) == ("mesos", 5, MAP, 20)
    # the level from the latest bar read that showed one (one without it changes nothing)
    scan._hud_deliver(hud.Hud(31, None, None, 100, 5.0, (50, 60)), time.time())
    scan._hud_deliver(hud.Hud(None, None, None, None, None, (40, 60)), time.time())
    _deliver(scan, t + 1.5, MESOS, EXP21, "You have gained mesos (+5)", EXP8)
    assert (scan._log.events[-1].amount, scan._log.events[-1].level) == (8, 31)
    assert not any(hasattr(e, "monster") for e in scan._log.events)


def test_an_unknown_map_tags_none(scan, monkeypatch):
    monkeypatch.setattr(LOCATION, "here", None)
    scan.start()
    t = time.time()
    _deliver(scan, t, MESOS)
    _deliver(scan, t + 0.5, MESOS, EXP21)
    assert _counted(scan) == [("exp", 21)] and scan._log.events[0].map == ""


# ------------------------------------------------------------ item names repaired

def test_the_item_names_are_repaired_when_it_starts_and_on_a_new_kb(isolated_store, kb, monkeypatch, caplog):
    """Items logged as a Cash item (a cut-off read matched to the Green Mushroom Hat, live) are named again: in the
    database and loot.json, by the KB's own tracker, once when the scanner starts and again for a new KB."""
    from maplehelper.ui.lootscan import LootScanner
    calls = []

    def repair(resolve, bad, price=None):
        calls.append((resolve, bad))
        return 3
    monkeypatch.setattr(lootdb, "repair_items", repair)
    monkeypatch.setattr(lootlog, "unpickable_keys", lambda kb: {"item/3551"})
    caplog.set_level(logging.INFO, logger="maplehelper")
    s = LootScanner(kb, isolated_store.Profiles(), isolated_store.Settings())
    try:
        assert len(calls) == 1 and calls[0][1] == {"item/3551"}
        assert calls[0][0].__self__ is s._tracker and calls[0][0]("Red Potion") == ("Red Potion", "item/2000000")
        assert "loot: repaired 3 item names" in caplog.messages
        s.set_kb(kb)
        assert len(calls) == 2 and calls[1][0].__self__ is s._tracker
    finally:
        for timer in (s._timer, s._hud_timer, s._save_timer):
            timer.stop()


def test_a_running_log_is_repaired_before_it_goes_on(isolated_store, kb, monkeypatch):
    """loot.json's running log: its pickups of an item no pickup names are the right item when the scanner takes it
    up; a failing database repair is a warning, never a scanner that won't start."""
    from maplehelper.ui.lootscan import LootScanner
    monkeypatch.setattr(lootlog, "unpickable_keys", lambda kb: {"item/9"})
    now = time.time()
    older = lootdb.open_log("", "", now - 600)              # an older log's pickup, in the database
    lootdb.add_events(older, [lootlog.Event(now - 590, "item", 1, "Red Potions", "item/9")], kb)
    lg = lootlog.Log(start=now - 60, events=[lootlog.Event(now - 30, "item", 1, "Red Potions", "item/9")])
    lootlog.Store.path.write_text(json.dumps({"active": {"": lg.to_json()}, "recent": {}}), encoding="utf-8")
    works = lootdb.repair_items

    def broken(resolve, bad, price=None):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(lootdb, "repair_items", broken)
    s = LootScanner(kb, isolated_store.Profiles(), isolated_store.Settings())
    try:
        assert s.running("") and [(e.name, e.key) for e in s._log.events] == [("Red Potion", "item/2000000")]
        assert any("loot repair" in m for m in s._logged)
        # (the running log went into the database fixed; the older pickup waits for a repair that works)
        assert [(r.item, r.item_key) for r in lootdb.events("")] == [("Red Potions", "item/9"),
                                                                    ("Red Potion", "item/2000000")]
        monkeypatch.setattr(lootdb, "repair_items", works)
        s.set_kb(kb)
        assert [(r.item, r.item_key) for r in lootdb.events("")] == [("Red Potion", "item/2000000")] * 2
        assert [(e.name, e.key) for e in s.store.log("").events] == [("Red Potion", "item/2000000")]
    finally:
        for timer in (s._timer, s._hud_timer, s._save_timer):
            timer.stop()


# ------------------------------------------------------------ the grind bar's watch

def test_the_grind_bar_watches_and_the_first_exp_gain_starts_a_run(scan):
    assert not scan._timer.isActive()                       # no log, no grind bar: nothing is read
    scan._settings["grind_bar"] = True
    scan.restart()                                          # (the app, when the setting flips)
    assert scan._timer.isActive() and not scan._hud_timer.isActive() and scan._log is None
    t = time.time()
    _deliver(scan, t, MESOS)                                # on screen when the watch began
    _deliver(scan, t + 0.5, MESOS, LEAF)                    # an item alone starts nothing...
    _deliver(scan, t + 1.0, MESOS, LEAF, "You have gained mesos (+5)")     # ... nor mesos
    assert scan._log is None and not scan.running(scan.cid())
    changed = []
    scan.changed.connect(lambda: changed.append(True))
    _deliver(scan, t + 1.5, MESOS, LEAF, "You have gained mesos (+5)", EXP21)
    assert scan.running(scan.cid()) and changed
    lg = scan._log
    assert _counted(scan) == [("exp", 21)] and lg.start == lg.events[0].t
    assert lg.events[0].map == MAP
    assert scan._hud_timer.isActive() and scan.store.running(scan.cid()) is not None and lg.db_id is not None
    # the reads go on from it (no new baseline): the next pickup counts
    _deliver(scan, t + 2.0, MESOS, LEAF, "You have gained mesos (+5)", EXP21, "You have gained mesos (+9)")
    assert _counted(scan) == [("exp", 21), ("mesos", 9)]
    # stopped with the bar on, it watches again; the bar off, nothing is read
    scan.end()
    assert scan._timer.isActive() and not scan._hud_timer.isActive()
    scan._settings["grind_bar"] = False
    scan.restart()
    assert not scan._timer.isActive()
    _deliver(scan, t + 3.0, MESOS, EXP21)
    _deliver(scan, t + 3.5, MESOS, EXP21, EXP8)
    assert scan._log is None


def test_a_start_by_hand_while_the_bar_watches_counts_from_a_new_baseline(scan):
    """Start from the Loot Log window while the grind bar watches: the run is that one, from a new baseline."""
    scan._settings["grind_bar"] = True
    scan.restart()
    scan.start()
    t = time.time()
    _deliver(scan, t, MESOS, EXP21)                         # on screen at Start: not counted
    _deliver(scan, t + 0.5, MESOS, EXP21, EXP8)
    assert _counted(scan) == [("exp", 8)]


# ------------------------------------------------------------ pause

def test_a_paused_run_reads_and_counts_nothing_until_it_resumes(scan):
    scan.start()
    lg = scan._log
    t = time.time()
    _deliver(scan, t, MESOS)
    changed = []
    scan.changed.connect(lambda: changed.append(True))
    scan.pause()
    assert scan.paused() and lg.paused and len(lg.pauses) == 1 and lg.pauses[0][1] is None and changed
    assert not scan._timer.isActive() and not scan._hud_timer.isActive()
    scan._tick()
    scan._hud_tick()
    assert not scan._reading and not scan._hud_reading      # a tick due anyway starts no read
    _deliver(scan, t + 0.5, MESOS, EXP21)                   # reads on their way when it paused: dropped
    scan._hud_deliver(hud.Hud(10, None, None, 219, 12.76, (431, 444)), time.time())
    assert lg.events == [] and lg.samples == []
    assert scan.store.running(scan.cid()).paused            # (saved paused)
    changed.clear()
    scan.resume_run()
    assert not scan.paused() and lg.pauses[0][1] is not None and changed
    assert scan._timer.isActive() and scan._hud_timer.isActive()
    _deliver(scan, t + 1.0, MESOS, EXP21)                   # on screen at the resume: a new baseline
    _deliver(scan, t + 1.5, MESOS, EXP21, EXP8)
    assert _counted(scan) == [("exp", 8)]
    # paused again and ended: the pause ends with the run
    scan.pause()
    scan.end()
    assert lg.pauses[-1][1] == lg.ended and not lg.paused and len(lg.pauses) == 2
    assert scan.store.log(scan.cid()).pauses == lg.pauses


def test_a_run_paused_when_the_app_closed_stays_paused_after(scan, kb):
    from maplehelper.ui.lootscan import LootScanner
    scan.start()
    scan.pause()
    scan.stop()
    again = LootScanner(kb, scan._profiles, scan._settings)
    try:
        assert again.running(scan.cid()) and again.paused() and not again._timer.isActive()
        again.resume_run()
        assert not again.paused() and again._timer.isActive()
    finally:
        for timer in (again._timer, again._hud_timer, again._save_timer):
            timer.stop()


# ------------------------------------------------------------ the bottom bar's samples

def test_the_bottom_bar_is_sampled_while_the_run_counts(scan, monkeypatch):
    """Every HUD_INTERVAL a worker grabs just the bar (the bottom hud.STRIP of the game's picture) and reads it: a
    sample of the live run, on LOCATION's map. No read, or one that fails, adds nothing; one at a time."""
    from maplehelper import capture, gamearea, plan
    from maplehelper.ui import lootscan
    grabbed = []
    monkeypatch.setattr(gamearea.GameArea, "find", lambda self: (100, 50, 1600, 900))
    monkeypatch.setattr(capture, "grab_image", lambda x, y, w, h: grabbed.append((x, y, w, h)) or Image.new("RGB", (w, h)))
    monkeypatch.setattr(plan, "exp_table", lambda kb: TABLE)
    reads = [hud.Hud(10, "Rogue", "Kalimero", 219, 12.76, (431, 444), (363, 363)), None]
    tables = []
    monkeypatch.setattr(hud, "read_strip", lambda img, table: tables.append(table) or reads.pop(0))
    started = []

    class Thread:
        def __init__(self, target, args, daemon):
            started.append(target.__name__)

        def start(self):
            pass
    monkeypatch.setattr(lootscan, "threading", types.SimpleNamespace(Thread=Thread))
    scan._hud_tick()
    assert started == []                                    # no run: no bar read
    scan.start()
    assert scan._hud_timer.isActive() and scan._hud_timer.interval() == int(lootscan.HUD_INTERVAL * 1000)
    scan._hud_tick()
    scan._hud_tick()                                        # the first still going: no pile-up
    assert started == ["_hud_read"] and scan._hud_reading
    changed = []
    scan.changed.connect(lambda: changed.append(True))
    before = time.time()
    scan._hud_read(scan.kb)                                 # (the worker's part, here)
    top = int(900 * (1 - hud.STRIP))
    assert grabbed == [(100, 50 + top, 1600, 900 - top)] and 900 - top == pytest.approx(900 * hud.STRIP, abs=1)
    assert tables == [TABLE] and not scan._hud_reading and changed
    (s,) = scan._log.samples
    assert s == lootlog.HudSample(s.t, MAP, 10, 219, 12.76, 431, 444, 363, 363) and s.t >= before
    scan._hud_read(scan.kb)                                 # a read that found no bar

    def gone(*_):
        raise OSError("screen gone")
    monkeypatch.setattr(capture, "grab_image", gone)
    scan._hud_read(scan.kb)                                 # a grab that failed
    assert len(scan._log.samples) == 1 and not scan._hud_reading
    # the events after it take its level, not the character's
    t = time.time()
    _deliver(scan, t, MESOS)
    _deliver(scan, t + 0.5, MESOS, EXP21)
    assert scan._log.events[0].level == 10
    # the run ended: a bar read on its way is no sample
    lg = scan._log
    scan.end()
    assert not scan._hud_timer.isActive()
    scan._hud_deliver(hud.Hud(11, None, None, 5, 0.2), time.time())
    assert len(lg.samples) == 1


def test_no_game_window_no_bar_read(scan, monkeypatch):
    from maplehelper import capture, gamearea
    monkeypatch.setattr(gamearea.GameArea, "find", lambda self: None)
    monkeypatch.setattr(capture, "grab_image", lambda *a: pytest.fail("grabbed with no game"))
    scan.start()
    scan._hud_read(scan.kb)
    assert scan._log.samples == [] and not scan._hud_reading
