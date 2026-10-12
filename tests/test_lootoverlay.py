"""The Loot log's window over the game (ui/lootoverlay.py LootOverlay, the toolbar's Loot window): it follows the
log and its setting, its buttons, the state chip, the three tiles, the items and the latest pickups; and where its
scanner (ui/lootscan.py LootScanner) reads the messages."""
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from maplehelper import lootlog  # noqa: E402
from maplehelper.i18n import I18n  # noqa: E402

app = QApplication.instance() or QApplication([])
REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
# five minutes of live pickups (test_lootlog's loot_reads_live.json): its EXP, mesos and items
LIVE_EXP, LIVE_MESOS = 358, 327
LIVE_ITEMS = (("Firewood", 5), ("Snail Shell", 2), ("Tree Branch", 2), ("Leaf", 2), ("Red Snail Shell", 1))
MARKS = dict.fromkeys(map(ord, "\u2066\u2069\u200e\u200f\u202a\u202c"))     # bidi marks aside


@pytest.fixture(scope="module")
def kb():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


@pytest.fixture(autouse=True)
def default_look():
    """Every test ends on today's dark glass (apply_look is module state every window over the game reads)."""
    yield
    from maplehelper.ui import npcoverlay
    npcoverlay.apply_look(None)


@pytest.fixture
def scan(isolated_store, kb):
    """The scanner as the app builds it, for a Magician with nothing logged yet; and its settings."""
    from maplehelper.ui.lootscan import LootScanner
    p = isolated_store.Profiles()
    p.add("Kiwi", "Magician", "Magician", 21)
    s = isolated_store.Settings()
    sc = LootScanner(kb, p, s)
    yield sc, s
    sc.stop()


def test_the_card_over_the_game_follows_the_log_and_its_switch(scan, kb):
    """Its own window over the game, at the other windows' opacity: a log starting opens it, its ✕ hides it (the
    toolbar's Loot button follows its setting), and a stopped log stays in it to read."""
    from maplehelper.ui.lootoverlay import LootOverlay
    sc, s = scan
    s["npc_overlay_opacity"] = 0.5
    card = LootOverlay(sc, s, kb)
    sc.changed.connect(card.sync)
    try:
        assert card.isWindow() and card.parent() is None and not card.isVisible()
        sc.start()
        assert card.isVisible() and card._opacity == 0.5 and s["loot_overlay"] is True
        sc._log.add([lootlog.Event(1.0, "mesos", 1234), lootlog.Event(2.0, "item", 1, "Leaf", "item/358")])
        sc.changed.emit()
        texts = card.lines()
        assert any("1,234" in x for x in texts) and any("Leaf" in x for x in texts)
        card._close.click()
        assert not card.isVisible() and s["loot_overlay"] is False
        assert sc.running(sc.cid())                     # hiding the window never stops the log
        s["loot_overlay"] = True                        # the toolbar's Loot button, as it flips the setting
        card.sync()
        assert card.isVisible()
        sc.end()
        assert card.isVisible() and any("1,234" in x for x in card.lines())
    finally:
        card.close()


def test_the_windows_buttons_start_stop_reset_and_fold(scan, kb):
    """Start when no log runs; Stop and Reset while one does (Reset: the log so far saved, a new one from zero);
    the – folds it to its title row, with what the log made in the title, and the fold is kept."""
    from maplehelper.ui.lootoverlay import LootOverlay
    sc, s = scan
    card = LootOverlay(sc, s, kb)
    sc.changed.connect(card.sync)
    s["loot_overlay"] = True
    card.sync()
    cid = sc.cid()
    try:
        assert card._start.isVisibleTo(card) and not card._stop.isVisibleTo(card)
        card._start.click()
        assert sc.running(cid) and card._stop.isVisibleTo(card) and card._reset.isVisibleTo(card)
        sc._log.add([lootlog.Event(1.0, "mesos", 500)])
        card._reset.click()
        assert sc.running(cid) and sc._log.totals()[1] == 0
        assert sc.store.recent(cid)[0]["mesos"] == 500
        sc._log.add([lootlog.Event(2.0, "mesos", 70)])
        card.refresh()
        full = card.height()
        card._fold.click()
        assert s["loot_overlay_folded"] is True and card.height() < full and not card._body.isVisibleTo(card)
        assert "70" in card._title.text()
        card._fold.click()
        assert s["loot_overlay_folded"] is False and card.height() == full
        card._stop.click()
        assert not sc.running(cid) and card._start.isVisibleTo(card) and card.isVisible()
    finally:
        card.close()


@pytest.fixture
def card(scan, kb):
    """The window over the game in English, following the scanner as the app wires it."""
    from maplehelper.ui.lootoverlay import LootOverlay
    sc, s = scan
    w = LootOverlay(sc, s, kb, I18n("en"))
    sc.changed.connect(w.sync)
    yield w
    sc.changed.disconnect(w.sync)
    _delete(w)


def _delete(w) -> None:
    """Closed and gone now (its 5 s clock with it): deleteLater alone waits for an event loop the tests never run."""
    from PySide6.QtCore import QEvent
    w.close()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)


def _key(kb, name: str) -> str:
    return lootlog.item_names(kb)[name.lower()]


def _live_log(scan, kb, now: float, minutes: int = 30) -> None:
    """The running log as the live session counted it, started `minutes` ago: per hour is then 60 / minutes times
    each total."""
    scan._log.start = now - minutes * 60
    scan._log.add([lootlog.Event(now - 300, "exp", LIVE_EXP), lootlog.Event(now - 290, "mesos", LIVE_MESOS)]
                  + [lootlog.Event(now - 280 + i, "item", n, name, _key(kb, name))
                     for i, (name, n) in enumerate(LIVE_ITEMS)])


def _shown(card, rows) -> list:
    return [r for r in rows if r.isVisibleTo(card)]


def test_the_windows_tiles_give_exp_mesos_and_the_items_npc_value_each_per_hour(scan, card, kb):
    """EXP, mesos and what an NPC pays for the items (not the mesos again: the summary's value counts them), each
    with its per-hour figure; under a minute there is no rate yet."""
    sc, _ = scan
    sc.start()
    now = time.time()
    _live_log(sc, kb, now)
    card.refresh()
    sm = lootlog.summarize(kb, sc._log)
    worth = sum(n * (price or 0) for _, n, _, price in sm.items)
    assert worth and sm.value == worth + LIVE_MESOS
    tiles = {k: (name.text(), value.text(), rate.text()) for k, (_tile, name, value, rate) in card._tiles.items()}
    assert tiles == {"exp": ("EXP", "358", "716/h"), "mesos": ("Mesos", "327", "654/h"),
                     "items": ("Items value", f"{worth:,}", f"{2 * worth:,}/h")}
    sc._log.start = time.time() - 30
    card.refresh()
    assert [rate.text() for _tile, _name, _value, rate in card._tiles.values()] == ["–/h"] * 3
    assert card._tiles["exp"][3].toolTip() == I18n("en")("loot_tip_wait")


def test_the_windows_items_show_their_pictures_counts_and_npc_value_in_place(scan, card, kb):
    """Most picked first, each with its picture, a count badge and what an NPC pays for them; a refresh fills the
    same rows in place (a picture only changes with the item), more items than rows end in "and N more items", and
    an item the database doesn't know shows "?" with no price."""
    from maplehelper import farm
    sc, _ = scan
    sc.start()
    now = time.time()
    _live_log(sc, kb, now)
    card.refresh()
    rows = _shown(card, card._rows)
    assert [(r.name.full(), r.badge.text()) for r in rows] == [
        ("Firewood", "×5"), ("Leaf", "×2"), ("Snail Shell", "×2"), ("Tree Branch", "×2"), ("Red Snail Shell", "×1")]
    assert all(not r.pic.pixmap().isNull() for r in rows)
    assert rows[0].worth.text() == f"{5 * farm.value(kb, _key(kb, 'Firewood')).price:,}"
    assert not card._more.isVisibleTo(card)
    pictures = [r.pic.pixmap().cacheKey() for r in rows]
    sc._log.add([lootlog.Event(now, "item", 1, "Leaf", _key(kb, "Leaf"))])
    card.refresh()
    assert _shown(card, card._rows) == rows and [r.pic.pixmap().cacheKey() for r in rows] == pictures
    assert rows[1].badge.text() == "×3"
    sc._log.add([lootlog.Event(now, "item", 9, "Srail Shel", "")])      # a name read in part
    card.refresh()
    top = card._rows[0]
    assert (top.name.full(), top.badge.text(), top.pic.text(), top.worth.text()) == ("Srail Shel", "×9", "?", "–")
    assert top.pic.pixmap().isNull()
    assert card._more.isVisibleTo(card) and card._more.text() == "and 1 more item"
    assert card._more.toolTip() == "Red Snail Shell ×1"
    from maplehelper.ui.lootoverlay import LootOverlay
    he = LootOverlay(sc, card.settings, kb, I18n("he"))
    try:
        he.refresh()
        badges = [r.badge.text().translate(MARKS) for r in _shown(he, he._rows)]
        assert badges[:2] == ["9 יח'", "5 יח'"] and not any("×" in b for b in badges)  # no "×5" beside a Hebrew word
        feed = [r.text.full().translate(MARKS) for r in _shown(he, he._feed)]
        assert feed[1] == "Leaf · יחידה אחת" and not any("1 יחידות" in x for x in feed)     # one is "one"
    finally:
        _delete(he)


def test_the_windows_latest_pickups_are_newest_first_with_a_picture_each(scan, card, kb):
    """Newest on top, each with the item's picture (the mesos' coin, the EXP's sparkle) and how long ago; older
    lines fainter."""
    sc, _ = scan
    sc.start()
    now = time.time()
    sc._log.add([lootlog.Event(now - 150, "exp", 21), lootlog.Event(now - 40, "item", 1, "Leaf", _key(kb, "Leaf")),
                 lootlog.Event(now - 20, "mesos", 27), lootlog.Event(now - 1, "item", 2, "Firewood",
                                                                     _key(kb, "Firewood"))])
    card.refresh()
    feed = _shown(card, card._feed)
    assert [r.text.full() for r in feed] == ["Firewood ×2", "+27 mesos", "Leaf ×1", "+21 EXP"]
    assert feed[0].ago.text() == "just now" and feed[1].ago.text().endswith(" s ago")
    assert feed[3].ago.text() == "2 min ago"
    assert all(not r.icon.pixmap().isNull() for r in feed)
    alpha = [r.text.palette().color(QPalette.WindowText).alphaF() for r in feed]
    assert alpha == sorted(alpha, reverse=True) and alpha[0] > alpha[-1]
    sc._log.add([lootlog.Event(time.time(), "mesos", 5)])
    card.refresh()
    assert [r.text.full() for r in _shown(card, card._feed)] == ["+5 mesos", "Firewood ×2", "+27 mesos", "Leaf ×1"]


def test_the_windows_state_chip_follows_start_stop_and_the_accent(scan, card):
    """● Recording in the accent while the log runs (Start lights in it too, Stop is red), Stopped muted after, the
    reason nothing counts while the game is covered; folded, the title keeps what the log made, with the accent's dot
    while it records."""
    from maplehelper.ui import npcoverlay
    from maplehelper.ui.lootoverlay import STOP
    sc, s = scan
    s["loot_overlay"] = True
    card.sync()
    assert card._chip_off.isVisibleTo(card) and card._chip_off.text() == "The log isn't running"
    assert not card._chip_on.isVisibleTo(card) and not card._elapsed.isVisibleTo(card)
    card._start.click()
    assert card._chip_on.isVisibleTo(card) and card._chip_on.text() == "● Recording"
    assert not card._chip_off.isVisibleTo(card) and card._elapsed.text() == "0 s"
    s["overlay_accent"] = "blue"
    card.refresh()
    blue = npcoverlay.ACCENTS["blue"][1]
    sheet = card.styleSheet()
    assert f"#ChipOn {{ color: {blue};" in sheet and f"QPushButton#Go {{ background: {blue};" in sheet
    assert card._stop.objectName() == "Stop" and f"QPushButton#Stop {{ background: rgba(255,138,128,0.16); color: {STOP}; }}" in sheet
    sc.state = "covered"
    card.refresh()
    assert card._status.isVisibleTo(card) and "covers the game" in card._status.text()
    sc.state = "ok"
    sc._log.add([lootlog.Event(time.time(), "mesos", 70)])
    card._fold.click()
    assert card._dot.isVisibleTo(card) and card._title.text() == "Loot Log · 70 made"
    card._fold.click()
    card._stop.click()
    assert card._chip_off.isVisibleTo(card) and card._chip_off.text() == "■ Stopped" and not card._chip_on.isVisibleTo(card)
    assert not card._status.isVisibleTo(card)
    card._fold.click()
    assert not card._dot.isVisibleTo(card) and card._title.text() == "Loot Log · 70 made"


def test_on_the_white_glass_the_window_turns_dark_on_light(scan, card):
    """The ⚙ panel's white glass: the window's text and fills flip to the light palette, its figures' and Stop's
    colours darkened by ink to read on it; the dark glass brings today's look back."""
    from PySide6.QtGui import QPalette
    from maplehelper.ui import npcoverlay
    from maplehelper.ui.lootoverlay import STAT_COLORS, STOP
    sc, s = scan
    s["loot_overlay"] = True
    card.sync()
    card._start.click()
    sc._log.add([lootlog.Event(time.time(), "exp", 21), lootlog.Event(time.time(), "mesos", 27)])
    s["overlay_tint"] = "white"
    npcoverlay.apply_look(s)
    card.refresh()                                  # as the app does after the ⚙ panel's pick
    sheet = card.styleSheet()
    assert f"#Title {{ color: {npcoverlay.LIGHT.text};" in sheet and npcoverlay.LIGHT.muted in sheet
    assert npcoverlay.DARK.text not in sheet and "255,255,255" not in sheet and "235,235,245" not in sheet
    for key, colour in STAT_COLORS.items():
        assert f"#TileName_{key} {{ color: {npcoverlay.ink(colour)};" in sheet
    assert f"color: {npcoverlay.ink(STOP)};" in sheet and f"color: {STOP};" not in sheet
    assert card._title.palette().color(QPalette.WindowText).name() == npcoverlay.LIGHT.text.lower()
    s["overlay_tint"] = "dark"
    npcoverlay.apply_look(s)
    card.refresh()
    sheet = card.styleSheet()
    assert f"#Title {{ color: {npcoverlay.DARK.text};" in sheet and npcoverlay.LIGHT.text not in sheet
    assert f"QPushButton#Stop {{ background: rgba(255,138,128,0.16); color: {STOP}; }}" in sheet
    assert card._title.palette().color(QPalette.WindowText).name() == npcoverlay.DARK.text.lower()


def test_reads_follow_the_game_window_and_skip_a_covered_one(scan, monkeypatch):
    """Each read takes the messages box from the game's window as it is now (moved, resized), and reads nothing
    while another app's window covers it (its text was read live), telling the window over the game (which says
    so)."""
    from maplehelper import capture, gamearea
    sc, _ = scan
    grabbed, cover = [], [False]
    windows = iter([(0, 0, 1922, 1112), (500, 300, 1368, 800), (500, 300, 1368, 800)])
    monkeypatch.setattr(gamearea.GameArea, "find", lambda self: next(windows))
    monkeypatch.setattr(gamearea.GameArea, "covered", lambda self, box: cover[0])
    monkeypatch.setattr(capture, "grab_image", lambda x, y, w, h: grabbed.append((x, y, w, h)) or
                        __import__("PIL.Image", fromlist=["Image"]).new("RGB", (w, h)))
    monkeypatch.setattr(lootlog, "ocr_rows", lambda arr: [])
    got, told = [], []
    sc._read_done.disconnect()
    sc._read_done.connect(lambda rows, at, read: (got.append(read), sc._deliver(rows, at, read)))
    sc.start()
    sc._read()
    sc._read()
    assert grabbed == [tuple(lootlog.auto_box((0, 0, 1922, 1112)).values()),
                       tuple(lootlog.auto_box((500, 300, 1368, 800)).values())]
    cover[0] = True
    sc.changed.connect(lambda: told.append(sc.state))
    sc._read()
    assert len(grabbed) == 2 and got[-1][1] == "covered" and sc.state == "covered" and told == ["covered"]
    sc.end()
