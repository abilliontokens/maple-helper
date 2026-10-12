"""The loot database (lootdb.py): every log and pickup kept for good, and a day's totals read back from it."""
import datetime as dt
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from maplehelper import lootdb, lootlog

app = QApplication.instance() or QApplication([])
REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
LEAF = "item/358"


@pytest.fixture(scope="module")
def kb():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


def _at(date: dt.date, hour: int, minute: int = 0) -> float:
    return dt.datetime.combine(date, dt.time(hour, minute)).timestamp()


def _rows(sql: str, *args):
    with sqlite3.connect(lootdb.PATH) as con:
        return con.execute(sql, args).fetchall()


def test_a_day_counts_its_own_pickups_and_its_part_of_a_log_over_midnight(isolated_store, kb):
    d1 = dt.date(2026, 10, 10)
    d2 = d1 + dt.timedelta(days=1)
    a = lootdb.open_log("c1", "Kiwi", _at(d1, 23, 30))
    lootdb.add_events(a, [lootlog.Event(_at(d1, 23, 40), "exp", 21), lootlog.Event(_at(d1, 23, 41), "mesos", 27),
                          lootlog.Event(_at(d1, 23, 42), "item", 2, "Leaf", LEAF),
                          lootlog.Event(_at(d2, 0, 10), "mesos", 100)], kb)
    lootdb.end_log(a, _at(d2, 0, 30))
    other = lootdb.open_log("c2", "Other", _at(d1, 22))
    lootdb.add_events(other, [lootlog.Event(_at(d1, 22, 5), "mesos", 9999)], kb)
    lootdb.end_log(other, _at(d1, 22, 10))

    first = lootdb.day("c1", d1)
    from maplehelper import farm
    leaf = farm.value(kb, LEAF).price
    assert (first.exp, first.mesos) == (21, 27)
    assert first.items == [("Leaf", 2, LEAF, leaf)] and first.value == 27 + 2 * leaf
    assert first.seconds == pytest.approx(30 * 60)          # 23:30 to midnight
    second = lootdb.day("c1", d2)
    assert (second.exp, second.mesos, second.items, second.seconds) == (0, 100, [], pytest.approx(30 * 60))
    assert lootdb.day("c1", d2 + dt.timedelta(days=1)).value == 0
    assert [d.date for d in lootdb.days("c1")] == [d2, d1]
    assert [d.date for d in lootdb.days("c1", limit=1)] == [d2]


def test_a_new_log_closes_one_left_open_at_its_last_pickup(isolated_store, kb):
    """The app closed mid-log and the log never came back: its row ends where its pickups stop."""
    a = lootdb.open_log("c1", "Kiwi", 1000.0)
    lootdb.add_events(a, [lootlog.Event(1100.0, "exp", 5)], kb)
    lootdb.open_log("c1", "Kiwi", 5000.0)
    assert _rows("SELECT ended FROM logs WHERE id = ?", a) == [(1100.0,)]


def test_deleting_a_character_deletes_its_logs_and_pickups(isolated_store, kb):
    p = isolated_store.Profiles()
    c = p.add("Kiwi", "Magician", "Magician", 20)
    keep = p.add("Other", "Warrior", "Warrior", 20)
    a = lootdb.open_log(c.id, "Kiwi", 1000.0)
    lootdb.add_events(a, [lootlog.Event(1001.0, "exp", 5)], kb)
    b = lootdb.open_log(keep.id, "Other", 2000.0)
    lootdb.add_events(b, [lootlog.Event(2001.0, "exp", 7)], kb)
    p.remove(c.id)
    assert _rows("SELECT character_id FROM logs") == [(keep.id,)]
    assert _rows("SELECT amount FROM events") == [(7,)]


# the database as the first version made it (before each pickup's map and level), as players have it
V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    character_id TEXT NOT NULL,
    character_name TEXT NOT NULL DEFAULT '',
    started REAL NOT NULL,
    ended REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    log_id INTEGER NOT NULL REFERENCES logs(id) ON DELETE CASCADE,
    t REAL NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('exp', 'mesos', 'item')),
    amount INTEGER NOT NULL,
    item TEXT NOT NULL DEFAULT '',
    item_key TEXT NOT NULL DEFAULT '',
    npc_price INTEGER
);
CREATE INDEX IF NOT EXISTS events_t ON events(t);
CREATE INDEX IF NOT EXISTS events_log ON events(log_id);
CREATE INDEX IF NOT EXISTS logs_character ON logs(character_id, started);
PRAGMA user_version = 1;
"""
# version 2's: the first one's tables with each pickup's map, an EXP gain's kill (dropped in 3) and the level
V2_SCHEMA = V1_SCHEMA.replace("PRAGMA user_version = 1;", """
ALTER TABLE events ADD COLUMN map_key TEXT NOT NULL DEFAULT '';
ALTER TABLE events ADD COLUMN monster_key TEXT NOT NULL DEFAULT '';
ALTER TABLE events ADD COLUMN level INTEGER;
PRAGMA user_version = 2;
""")


def _columns() -> list[str]:
    return [r[1] for r in _rows("PRAGMA table_info(events)")]


def test_a_version_1_database_gets_the_new_columns_in_place_and_keeps_its_rows(isolated_store, kb):
    with closing(sqlite3.connect(lootdb.PATH)) as con:
        con.executescript(V1_SCHEMA + "INSERT INTO logs VALUES (1, 'c1', 'Kiwi', 1000.0, 1100.0);"
                          "INSERT INTO events (log_id, t, kind, amount, item, item_key, npc_price) VALUES "
                          f"(1, 1010.0, 'exp', 21, '', '', NULL), (1, 1020.0, 'item', 2, 'Leaf', '{LEAF}', 5);")
    assert lootdb.events("c1") == [lootdb.Row(1, 1000.0, 1100.0, 1010.0, "exp", 21, "", "", None, "", None),
                                   lootdb.Row(1, 1000.0, 1100.0, 1020.0, "item", 2, "Leaf", LEAF, 5, "", None)]
    assert _rows("PRAGMA user_version") == [(lootdb.VERSION,)] == [(3,)]
    assert "monster_key" not in _columns() and {"map_key", "level"} <= set(_columns())
    b = lootdb.open_log("c1", "Kiwi", 2000.0)
    lootdb.add_events(b, [lootlog.Event(2010.0, "exp", 32, map="102000000", level=12)], kb)
    assert lootdb.events("c1")[-1] == lootdb.Row(b, 2000.0, None, 2010.0, "exp", 32, "", "", None, "102000000", 12)
    assert _rows("SELECT COUNT(*) FROM events") == [(3,)]


def test_a_version_2_database_loses_the_kills_and_keeps_its_rows(isolated_store, kb):
    """Version 2 kept an EXP gain's kill, matched from its EXP: a pickup message never says what was killed."""
    with closing(sqlite3.connect(lootdb.PATH)) as con:
        con.executescript(V2_SCHEMA + "INSERT INTO logs VALUES (1, 'c1', 'Kiwi', 1000.0, 1100.0);"
                          "INSERT INTO events (log_id, t, kind, amount, item, item_key, npc_price, map_key, "
                          "monster_key, level) VALUES "
                          "(1, 1010.0, 'exp', 21, '', '', NULL, '102000000', 'monster/dark-stump', 12), "
                          f"(1, 1020.0, 'item', 2, 'Leaf', '{LEAF}', 5, '102000000', '', 12);")
    assert "monster_key" in _columns()
    assert lootdb.events("c1") == [
        lootdb.Row(1, 1000.0, 1100.0, 1010.0, "exp", 21, "", "", None, "102000000", 12),
        lootdb.Row(1, 1000.0, 1100.0, 1020.0, "item", 2, "Leaf", LEAF, 5, "102000000", 12)]
    assert _rows("PRAGMA user_version") == [(3,)] and "monster_key" not in _columns()
    lootdb.add_events(lootdb.open_log("c1", "Kiwi", 2000.0), [lootlog.Event(2010.0, "mesos", 9)], kb)
    assert _rows("SELECT COUNT(*) FROM events") == [(3,)]


def test_items_logged_as_one_no_pickup_names_are_named_again(isolated_store):
    """59 Green Mushroom Caps were kept as the Green Mushroom Hat (item/3551, a Cash Hat): the cap's, and its price."""
    tr = lootlog.Tracker({"green mushroom cap": "item/360", "\0green mushroom cap": "Green Mushroom Cap",
                          "leaf": LEAF, "\0leaf": "Leaf"}, {"item/360"})
    bad = {"item/3551", "item/3285"}
    assert lootdb.repair_items(tr.resolve, bad) == 0 and not lootdb.PATH.exists()     # (no database: none made)
    a = lootdb.open_log("c1", "Kiwi", 1000.0)
    with closing(sqlite3.connect(lootdb.PATH)) as con, con:
        con.executemany("INSERT INTO events (log_id, t, kind, amount, item, item_key, npc_price) VALUES "
                        "(?, ?, 'item', 1, ?, ?, NULL)",
                        [(a, 1001.0, "Green Mushroom Hat", "item/3551"), (a, 1002.0, "Green Mushroom Hat", "item/3551"),
                         (a, 1003.0, "Leaf", LEAF), (a, 1004.0, "Blue Mushroom Hat", "item/3285"),
                         (a, 1005.0, "Green Mushroom", "")])
        con.execute("INSERT INTO events (log_id, t, kind, amount) VALUES (?, 1006.0, 'exp', 21)", (a,))
    assert lootdb.repair_items(tr.resolve, bad, price={"item/360": 14}.get) == 2
    assert _rows("SELECT item, item_key, npc_price FROM events ORDER BY t") == [
        ("Green Mushroom Cap", "item/360", 14), ("Green Mushroom Cap", "item/360", 14), ("Leaf", LEAF, None),
        ("Blue Mushroom Hat", "item/3285", None),       # (no item it reads as: kept as it was)
        ("Green Mushroom", "", None), ("", "", None)]
    assert lootdb.repair_items(tr.resolve, bad) == 0


def test_events_come_back_oldest_first_and_logs_newest_first(isolated_store, kb):
    from maplehelper import farm
    assert lootdb.events("c1") == [] and lootdb.logs("c1") == [] and not lootdb.PATH.exists()     # (none made)
    a = lootdb.open_log("c1", "Kiwi", 1000.0)
    lootdb.add_events(a, [lootlog.Event(1020.0, "mesos", 27, map="102000000", level=12),
                          lootlog.Event(1010.0, "exp", 21, map="102000000", level=12)], kb)
    lootdb.end_log(a, 1100.0)
    other = lootdb.open_log("c2", "Other", 1500.0)
    lootdb.add_events(other, [lootlog.Event(1510.0, "exp", 99)], kb)
    lootdb.end_log(other, 1600.0)
    b = lootdb.open_log("c1", "Kiwi", 2000.0)
    lootdb.add_events(b, [lootlog.Event(2010.0, "item", 1, "Leaf", LEAF, map="100000000", level=13)], kb)
    assert lootdb.events("c1") == [
        lootdb.Row(a, 1000.0, 1100.0, 1010.0, "exp", 21, "", "", None, "102000000", 12),
        lootdb.Row(a, 1000.0, 1100.0, 1020.0, "mesos", 27, "", "", None, "102000000", 12),
        lootdb.Row(b, 2000.0, None, 2010.0, "item", 1, "Leaf", LEAF, farm.value(kb, LEAF).price, "100000000", 13)]
    assert [r.t for r in lootdb.events("c1", since=1020.0)] == [1020.0, 2010.0] and lootdb.events("c3") == []
    assert lootdb.logs("c1") == [(b, 2000.0, None), (a, 1000.0, 1100.0)]
    assert lootdb.logs("c1", limit=1) == [(b, 2000.0, None)] and lootdb.logs("c2") == [(other, 1500.0, 1600.0)]


# ------------------------------------------------------------ written by the running log

@pytest.fixture
def scanner(isolated_store, kb):
    from maplehelper.ui.lootscan import LootScanner
    p = isolated_store.Profiles()
    p.add("Kiwi", "Magician", "Magician", 20)
    s = LootScanner(kb, p, isolated_store.Settings())
    yield s, p
    s._timer.stop()
    s._save_timer.stop()


def test_a_log_writes_a_pickup_once_no_read_can_change_it(scanner):
    """A pickup's value can still be corrected by the next reads of its line ("+28" read for "+26"): it goes in the
    database once that can't happen any more, with the corrected value; the log's end writes the rest."""
    s, p = scanner
    s.start()
    log_id = s._log.db_id
    assert _rows("SELECT character_id, character_name, ended FROM logs") == [(p.active.id, "Kiwi", None)]
    now = time.time()
    settled, fresh = lootlog.Event(now - 100, "mesos", 28), lootlog.Event(now, "exp", 21)
    s._log.add([settled, fresh])
    settled.amount = 26                     # a later read corrected it, before it settled
    s._save()
    assert _rows("SELECT kind, amount FROM events WHERE log_id = ?", log_id) == [("mesos", 26)]
    s.end()
    assert sorted(_rows("SELECT kind, amount FROM events WHERE log_id = ?", log_id)) == [("exp", 21), ("mesos", 26)]
    assert _rows("SELECT ended IS NOT NULL FROM logs WHERE id = ?", log_id) == [(1,)]
    # on the pickup's own day: run just after midnight (CI's 00:01 UTC), 100 s ago was yesterday
    assert lootdb.day(p.active.id, dt.date.fromtimestamp(settled.t)).value == 26


def test_closing_the_app_writes_every_pickup_and_the_log_goes_on_after(scanner, kb):
    from maplehelper.ui.lootscan import LootScanner
    s, p = scanner
    s.start()
    s._log.add([lootlog.Event(time.time(), "exp", 8)])
    s.stop()
    assert _rows("SELECT amount FROM events") == [(8,)]
    again = LootScanner(kb, p, s._settings)                 # the next start: the same log, nothing written twice
    try:
        assert again.running(p.active.id) and again._log.db_id == s._log.db_id
        again.end()
        assert _rows("SELECT amount FROM events") == [(8,)]
    finally:
        again._timer.stop()


def test_a_log_from_before_the_database_gets_its_row_when_it_resumes(scanner, kb):
    """A log running in loot.json from before this version: on the next start it gets a row, with its pickups."""
    from maplehelper.ui.lootscan import LootScanner
    s, p = scanner
    old = lootlog.Log(start=time.time() - 600, events=[lootlog.Event(time.time() - 500, "mesos", 40)])
    s.store.put(p.active.id, old)
    again = LootScanner(kb, p, s._settings)
    try:
        assert again._log.db_id is not None
        assert _rows("SELECT kind, amount FROM events") == [("mesos", 40)]
    finally:
        again._timer.stop()
