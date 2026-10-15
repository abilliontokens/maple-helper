"""The toolbar's search window (ui/gamesearch.py): the search itself over the KB's monsters, NPCs, maps and items
and where a monster lives, and its life as a window — opened in a mode (the same mode again a toggle), filled
as the player types (each row its picture, its tag chips, its muted line, a price on its end; every search
listed before anything is typed, Safe to sell?'s switch narrowing it), a click opening the thing's own
page in the detail window beside it (a header card over titled blocks — an NPC: where it stands and the way there;
a monster: its maps; an item: which quest gives it and who drops and sells it; a map: its monsters; Safe to
sell?: the verdict and what needs it), the history those pages push gone back through, the accent lighting the
open page's row, and the place on the screen the search is kept in."""
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(isolated_store):
    return isolated_store.Settings()


@pytest.fixture(autouse=True)
def _dark_look():
    """Every test starts and ends on today's dark glass, whatever look a test picked (npcoverlay's module state)."""
    from maplehelper.ui import npcoverlay
    npcoverlay.apply_look(None)
    yield
    npcoverlay.apply_look(None)


@pytest.fixture(scope="module")
def _own_kb(tmp_path_factory) -> Path:
    """This file's own copy of the fixture KB, without the tables any build writes (they are built here once):
    the shared folder's tables are built by every test worker at once, and on Windows a worker replacing a table
    another one has open fails its build and reads nothing (CI, 2026-10-10: every map of Snail missing)."""
    import shutil

    from maplehelper import tables
    dst = tmp_path_factory.mktemp("gamesearch") / "kb"
    shutil.copytree(Path(__file__).parent / "fixtures" / "kb", dst,
                    ignore=shutil.ignore_patterns(*tables.GENERATED, "*.tmp"))
    return dst


@pytest.fixture
def kb(_own_kb):
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(_own_kb)


def pump(qapp, ms):
    """Wait out a debounce (the typing, the geometry) the way a live event loop would; then, on a slow machine (macOS
    CI read the rows before a 150 ms typing pause had run, 50 ms into the margin), on until no search window's typing
    pause is still pending (2 s at most)."""
    from maplehelper.ui.gamesearch import GameSearch
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)
    end += 2.0
    while time.monotonic() < end and any(w._typing.isActive() for w in qapp.topLevelWidgets()
                                         if isinstance(w, GameSearch)):
        qapp.processEvents()
        time.sleep(0.005)


def delete_window(qapp, w):
    """A GameSearch a test is done with, gone before the next one: hidden (its detail window hidden with it,
    the guide let go), its debounces stopped, both windows deleted and the deletion carried out — another
    file's event pumping must never meet this test's windows (the overlay fixture in test_ux_chat.py and the
    env fixture in test_dialogs_provider.py do the same)."""
    from PySide6.QtCore import QEvent
    w.hide()                                     # hideEvent: the typing stopped, the detail hidden, the place saved
    d = getattr(w, "_detail", None)
    if d is not None:
        d.close()
        d.deleteLater()
    w.close()
    for timer in (w._typing, w._geom):
        timer.stop()
    w.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def profiles(isolated_store):
    return isolated_store.Profiles()


@pytest.fixture
def win(qapp, settings, profiles, kb):
    from maplehelper.i18n import I18n
    from maplehelper.ui.gamesearch import GameSearch
    w = GameSearch(kb, settings, profiles, I18n("en"))
    yield w
    delete_window(qapp, w)


@pytest.fixture
def clean_location():
    from maplehelper.ui.location import LOCATION
    old = (LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.route_dest)
    LOCATION.here = LOCATION.follow = LOCATION.guide = LOCATION.route_dest = None
    LOCATION.state = ""
    yield LOCATION
    LOCATION.here, LOCATION.state, LOCATION.follow, LOCATION.guide, LOCATION.route_dest = old


# a fake route graph: what the detail window reads of one — names, streets and minimap frames, no pictures
MID, FAR, GARDEN = "010020000", "010020001", "100000003"
MM = [2000, 4000, 1000, 2000]        # its minimap: width, height in map units, then the origin offset


class _FakeGraph:
    def __init__(self):
        from maplehelper.routes import MapInfo
        self.known = {
            MID: MapInfo(MID, "Fake Town", "Fake Street", True, "", MM, []),
            FAR: MapInfo(FAR, "Far Map", "Far Street", True, "", MM, []),
            GARDEN: MapInfo(GARDEN, "Snail Garden", "Victoria Road", True, "", MM, []),
        }

    def name(self, mid):
        m = self.known.get(mid)
        return m.name if m else mid

    def minimap(self, mid):
        return None


@pytest.fixture
def graph(monkeypatch):
    from maplehelper.ui import gamesearch
    g = _FakeGraph()
    monkeypatch.setattr(gamesearch.routes, "of", lambda kb: g)
    return g


def _here(mid=MID, spot=(0.5, 0.5)):
    from maplehelper.minimap import Here
    return Here(mid, spot)


def _kb_name(kb, key):
    """The name the detail window's header shows: the KB's own, else the key's id."""
    return str((kb.get(key) or {}).get("name") or key.partition("/")[2])


def _pieces(d):
    """The detail's body top to bottom, each titled block opened up: its title, then what is under it."""
    from maplehelper.ui.gamesearch import _Block
    out = []
    for w in d._rows:
        out += [w.title, *w.items] if isinstance(w, _Block) else [w]
    return out


def _texts(d):
    """Every line of the detail's body, top to bottom, as the player reads it (a block's title, then its lines; a
    route step's bold markup off)."""
    import re
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    out = []
    for w in _pieces(d):
        if isinstance(w, QLabel) and w.pixmap().isNull():
            text = w.text()
            out.append(re.sub(r"<[^>]+>", "", text) if w.textFormat() == Qt.RichText else text)
    return out


def _links(d):
    """The detail's rows, top to bottom (in its blocks too)."""
    from maplehelper.ui.gamesearch import _Row
    return [w for w in _pieces(d) if isinstance(w, _Row)]


def _seen(r):
    """A row as the player reads it: its name, its chips (the one on its end last), its muted line, and the number
    on its end over that number's unit."""
    chips = [c.text() for c in r.chips] + ([r.end_chip.text()] if r.end_chip is not None else [])
    return (r.name.text(), chips, r.sub.text() if r.sub is not None else "",
            r.num.text() if r.num is not None else "", r.unit.text() if r.unit is not None else "")


def _tones(r):
    """A row's chips' colours (gamesearch.TONES' names; "" a plain one), its end chip last."""
    return [c.property("tone") for c in r.chips] + ([r.end_chip.property("tone")] if r.end_chip is not None else [])


def _head(d):
    """The detail's header card as the player reads it: the name, its chips, the muted line under them."""
    return d.title.text(), [c.text() for c in d.chips], d.head_sub.text() if not d.head_sub.isHidden() else ""


REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "routes.json").exists(), reason="no routes.json in the real knowledge base")


# ---------------------------------------------------------------- the search itself (no window needed)

def test_exact_before_prefix_before_contains_and_ties_by_name(kb):
    from maplehelper.kb import memo
    from maplehelper.ui.gamesearch import Hit, search
    # the list is seeded for the ladder's sake: the fixture KB happens to hold no name another one starts with
    memo(kb, "_game_search")["item"] = [Hit("item/x", "Blue Snail Shell", ""), Hit("item/y", "Snail Shell", ""),
                                        Hit("item/z", "Snail", ""), Hit("item/w", "A Snail", "")]
    hits, total = search(kb, "item", "snail")
    assert [h.name for h in hits] == ["Snail", "Snail Shell", "A Snail", "Blue Snail Shell"] and total == 4


def test_a_prefix_beats_a_mere_contains(kb):
    from maplehelper.ui.gamesearch import search
    hits, _ = search(kb, "monster", "sna")
    assert [h.name for h in hits] == ["Snail", "Blue Snail", "Red Snail"]      # Snail starts "sna", the rest only have it


def test_the_words_match_in_any_order(kb):
    from maplehelper.ui.gamesearch import search
    one = search(kb, "monster", "snail blue")
    assert one == search(kb, "monster", "blue snail")
    assert [h.name for h in one[0]] == ["Blue Snail"] and one[1] == 1


def test_under_two_letters_finds_nothing(kb):
    from maplehelper.ui.gamesearch import search
    for q in ("", " ", "s", " s ", "a"):
        assert search(kb, "monster", q) == ([], 0)


def test_the_limit_and_the_total(kb):
    from maplehelper.ui.gamesearch import search
    hits, total = search(kb, "monster", "snail", limit=1)
    assert [h.name for h in hits] == ["Snail"] and total == 3


def test_each_list_is_built_once_per_kb(kb, monkeypatch):
    from maplehelper.ui import gamesearch
    calls = []
    build = gamesearch._BUILDERS["monster"]
    monkeypatch.setitem(gamesearch._BUILDERS, "monster", lambda kb: calls.append(1) or build(kb))
    gamesearch.search(kb, "monster", "snail")
    gamesearch.search(kb, "monster", "snail blue")
    gamesearch.search(kb, "monster", "red")
    assert calls == [1]


def test_where_a_monster_lives(kb):
    from maplehelper.ui.gamesearch import monster_maps
    assert monster_maps(kb, "monster/1210100") == [("map/100000002", "Henesys Hunting Ground II", "Victoria Road", 6)]
    assert monster_maps(kb, "map/100000000") == []            # not a monster at all


# ---------------------------------------------------------------- the window

def test_open_shows_that_mode_and_the_same_mode_again_toggles_off(win):
    modes = []
    win.mode_changed.connect(modes.append)
    win.open("monster_npc")
    assert win.isVisible() and win._kind == "monster_npc"
    assert win._title.text() == "Find a monster or NPC" and win._box.placeholderText() == "Monster or NPC name…"
    assert win._rows                                           # its first rows at once, nothing typed yet
    win.open("monster_npc")                                    # the same mode again: off
    assert not win.isVisible()
    assert modes == ["monster_npc", ""]


def test_typing_fills_the_rows(win, qapp):
    from PySide6.QtCore import QSize
    from maplehelper.ui import gamesearch
    win.open("monster_npc")
    win._box.setText("snail")
    pump(qapp, 200)                                            # the typing debounce
    assert [r.name.text() for r in win._rows] == ["Snail", "Blue Snail", "Red Snail"]
    # which kind it is and its level on a chip beside the name, its HP and EXP muted under it
    assert [_seen(r) for r in win._rows[:2]] == [("Snail", ["Monster · Lv. 1"], "8 HP · 3 EXP", "", ""),
                                                 ("Blue Snail", ["Monster · Lv. 2"], "15 HP · 4 EXP", "", "")]
    assert _tones(win._rows[0]) == ["monster"]
    # each row its picture in the same box (Snail has no sprite of its own in the fixture KB: the monster icon)
    assert not win._rows[0].pic.pixmap().isNull()
    assert {r.pic.size().toTuple() for r in win._rows} == {QSize(gamesearch.ROW_PIC, gamesearch.ROW_PIC).toTuple()}
    assert win._status.text() == ""                            # all of them shown: no "and N more"
    win._box.setText("zzz")
    pump(qapp, 200)
    assert not win._rows and win._status.text() == "Nothing found for “zzz”"


# ---------------------------------------------------------------- the detail window beside it

def test_clicking_a_monster_opens_the_detail_window_docked_beside(win, qapp, clean_location):
    from PySide6.QtCore import QPoint, QRect, QSize
    from maplehelper.ui import gamesearch
    from maplehelper.ui.glass import SHADOW
    from maplehelper.ui.npcoverlay import GUIDE_GAP
    win.open("monster_npc")
    win.setGeometry(QRect(400, 100, 320, 420))          # room on its left
    win._box.setText("snail")
    pump(qapp, 200)
    win._rows[0].clicked.emit()                         # Snail: its page, in a window of its own
    d = win._detail
    assert d.isVisible() and d.isWindow()               # a separate top-level window, docked to the search's left
    assert d.pos() == QPoint(win.x() + 2 * SHADOW - GUIDE_GAP - d.width(), win.y())
    assert win.isVisible() and [r.name.text() for r in win._rows] == ["Snail", "Blue Snail", "Red Snail"]  # still listed
    assert [r.property("sel") for r in win._rows] == [True, False, False]     # the one whose page shows, lit
    assert not d.back.isVisible()                       # nothing to go back to yet
    # the header card: the monster's picture, larger than a row's, its name, its level chip, its HP and EXP
    assert _head(d) == ("Snail", ["Monster · Lv. 1"], "8 HP · 3 EXP")
    assert not d.pic.pixmap().isNull() and d.pic.size() == QSize(gamesearch.HEAD_PIC, gamesearch.HEAD_PIC)
    # where it lives: a titled block, each map a row with its picture and how many spawn there on the end; then Hit
    # & damage, which needs a character (none here)
    assert _texts(d) == ["Where Snail lives", win.t("tool_calc"), win.t("md_no_char")]
    assert [(_seen(r), r.toolTip()) for r in _links(d)] == [
        (("Snail Garden", [], "Victoria Road", "6", "on the map"), "Click to see this map and the way there")]
    assert _links(d)[0].pic.size() == QSize(*gamesearch.MAP_PIC) and not _links(d)[0].pic.pixmap().isNull()
    win.move(500, 200)
    assert d.pos() == QPoint(win.x() + 2 * SHADOW - GUIDE_GAP - d.width(), win.y())      # it moves with the search
    win.move(4, 100)                                   # no room on the left any more: docked to its right
    assert d.x() == win.x() + win.width() - 2 * SHADOW + GUIDE_GAP and d.y() == win.y()
    win.hide()
    assert not d.isVisible()                            # hiding the search hides the detail
    assert not any(r.property("sel") for r in win._rows)    # and no row is lit any more


def test_a_map_row_opens_the_maps_page_and_back_returns(win, qapp, clean_location, graph, monkeypatch):
    from maplehelper import gamelookup
    monkeypatch.setattr(gamelookup, "map_monsters",
                        lambda kb, key: [("monster/2230104", "Stump", 15, 3)] if key == f"map/{GARDEN}" else [])
    monkeypatch.setattr(gamelookup, "way_to",
                        lambda kb, here, to, rides=True: gamelookup.Way(here=None, legs=(), known=False))
    win.open("monster_npc")
    win._box.setText("snail")
    pump(qapp, 200)
    win._rows[0].clicked.emit()
    d = win._detail
    snail = win._hits[0].key
    assert d._stack == [("monster", snail)]
    _links(d)[0].clicked.emit()                         # Snail Garden: the map's own page
    assert d._stack == [("monster", snail), ("map", f"map/{GARDEN}")]
    assert d.back.isVisible() and _head(d) == ("Snail Garden", [], "Victoria Road")   # the street under its name
    assert _texts(d) == ["The way from here on foot", "Your map isn't known yet, so there's no way from here",
                         "Monsters on this map"]
    assert [(_seen(r), r.toolTip()) for r in _links(d)] == [
        (("Stump", ["Lv. 15"], "", "3", "on the map"), "Click to see this monster")]
    assert _tones(_links(d)[0]) == ["monster"]
    d.go_back()
    assert d._stack == [("monster", snail)] and not d.back.isVisible()
    assert "Where Snail lives" in " ".join(_texts(d))
    _links(d)[0].clicked.emit()                         # the map again, then a new search click starts over
    win._rows[1].clicked.emit()                         # Blue Snail
    assert d._stack == [("monster", win._hits[1].key)] and not d.back.isVisible()
    d.close_btn.click()
    assert not d.isVisible()


def test_the_next_page_is_measured_at_once_never_folded_to_the_header(win, qapp, clean_location, graph, monkeypatch):
    """A page opened while the window already shows one: its rows were measured before they were shown (0 px) and
    the window folded to its header with the old page drawn under the title (offscreen render, 2026-10-10)."""
    from maplehelper import gamelookup
    monkeypatch.setattr(gamelookup, "map_monsters",
                        lambda kb, key: [("monster/2230104", "Stump", 15, 3)] if key == f"map/{GARDEN}" else [])
    monkeypatch.setattr(gamelookup, "way_to",
                        lambda kb, here, to, rides=True: gamelookup.Way(here=None, legs=(), known=False))
    win.open("monster_npc")
    win._box.setText("snail")
    pump(qapp, 200)
    win._rows[0].clicked.emit()
    d = win._detail
    first = d.height()
    _links(d)[0].clicked.emit()                         # the next page, no event pass in between
    assert d.height() > d._head.sizeHint().height() + 80 and all(w.isVisibleTo(d) for w in d._rows)
    d.go_back()
    assert d.height() == first


def test_the_page_window_keeps_the_size_the_player_drags_it_to(win, qapp, settings, clean_location, graph, monkeypatch):
    """It opens fitted to its page; a drag of its edges is kept (game_detail_size) once it settles, its pictures
    drawn again at the new width, and every page after, and the next session's, opens at that size."""
    from PySide6.QtCore import QSize

    from maplehelper import gamelookup
    from maplehelper.ui import gamesearch, mapview
    monkeypatch.setattr(gamelookup, "map_monsters", lambda kb, key: [])
    monkeypatch.setattr(gamelookup, "way_to",
                        lambda kb, here, to, rides=True: gamelookup.Way(here=None, legs=(), known=False))
    widths = []
    real = mapview.route_picture
    monkeypatch.setattr(mapview, "route_picture",
                        lambda path, spot=None, npc=False, you=None, cap_w=0: widths.append(cap_w) or real(path))
    win.open("monster_npc")
    win._box.setText("snail")
    pump(qapp, 200)
    win._rows[0].clicked.emit()
    d = win._detail
    assert d.width() == gamesearch.DETAIL_W and settings["game_detail_size"] is None    # shown: not the player's size
    pump(qapp, 500)
    assert settings["game_detail_size"] is None
    d.resize(420, 600)                                  # the player drags an edge
    pump(qapp, 500)                                     # the drag settles
    assert settings["game_detail_size"] == {"w": 420, "h": 600}
    widths.clear()
    _links(d)[0].clicked.emit()                         # the next page: the player's size, pictures at its width
    assert d.size() == QSize(420, 600) and len(widths) == 1
    # the picture grew with the drag, and still fits beside the scrollbar (past it, a long page was clipped under it)
    assert widths[0] > gamesearch.DETAIL_W - 2 * gamesearch.SIDE
    assert widths[0] + gamesearch.SCROLLBAR_W <= d.width() - 2 * gamesearch.SIDE
    win.hide()
    win.open("monster_npc")
    win._rows[0].clicked.emit()                         # opened again: still their size
    assert d.size() == QSize(420, 600)


def test_an_item_page_lists_droppers_and_sellers_and_a_dropper_opens_the_monster(
        win, qapp, kb, clean_location, graph, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtCore import QSize

    from maplehelper import gamelookup, market
    from maplehelper.ui import gamesearch
    monkeypatch.setattr(gamelookup, "item_sources", lambda kb, key: (
        [gamelookup.Dropper("monster/1210100", "Pig", 7), gamelookup.Dropper("monster/2230104", "Stump", 15)],
        [gamelookup.Seller("npc/2", "Al", 50, "Fake Town"), gamelookup.Seller("npc/9", "Bree", None, "Henesys")]))
    monkeypatch.setattr(market, "npc_prices", lambda kb, key: SimpleNamespace(sell_back=1250))
    win.open("item")
    assert win._box.placeholderText() == "Item name…"
    win._box.setText("red")
    pump(qapp, 200)
    assert _seen(win._rows[0]) == ("Red Potion", [], "", "1,250", "mesos")    # what an NPC pays, on the row's end
    win._rows[0].clicked.emit()                         # Red Potion: its page
    d = win._detail
    assert d._stack == [("item", "item/2000000")]
    assert _head(d) == ("Red Potion", [], "An NPC pays 1,250 mesos")     # (the fixture KB gives it no type)
    assert d.pic.size() == QSize(gamesearch.HEAD_PIC, gamesearch.HEAD_PIC) and not d.pic.pixmap().isNull()
    assert _texts(d) == ["Dropped by", "Sold by"]       # two titled blocks
    # who drops it: each monster's picture and its level on the end; who sells it: the NPC's map, its price
    assert [(_seen(r), r.toolTip()) for r in _links(d)] == [
        (("Pig", ["Lv. 7"], "", "", ""), "Click to see this monster"),
        (("Stump", ["Lv. 15"], "", "", ""), "Click to see this monster"),
        (("Al", [], "Fake Town", "50", "mesos"), "Click to see this NPC"),
        (("Bree", [], "Henesys", gamesearch.NO_NUM, ""), "Click to see this NPC")]
    assert _links(d)[3].num.toolTip() == "No NPC price in the database"     # the dash says why on hover
    assert all(not r.pic.pixmap().isNull() for r in _links(d))     # the KB's picture, else the kind's own icon
    _links(d)[0].clicked.emit()                         # who drops it: the monster's page
    assert d._stack == [("item", "item/2000000"), ("monster", "monster/1210100")]
    assert _head(d) == ("Pig", ["Monster · Lv. 7"], "80 HP · 12 EXP")
    assert "Where Pig lives" in _texts(d)


def test_item_rows_show_the_type_word_an_equips_level_and_the_npc_price(win, qapp, kb, monkeypatch):
    """Items: each row its picture, its type's word (itemterms.kind) muted under the name, an equip's required
    level on a chip, and what an NPC pays on the end — a muted dash when no NPC buys it."""
    from types import SimpleNamespace

    from maplehelper import market
    from maplehelper.kb import memo
    from maplehelper.ui.gamesearch import NO_NUM, Hit
    memo(kb, "_game_search")["item"] = [Hit("item/1302000", "Sword", "Equip / One-Handed Sword", "", (10, 10)),
                                        Hit("item/1302001", "Sword of Ice", "Equip / One-Handed Sword"),
                                        Hit("item/4000000", "Swordfish Scale", "Etc / Monster Drop")]
    prices = {"item/1302000": 2500, "item/4000000": 4}
    monkeypatch.setattr(market, "npc_prices", lambda kb, key: SimpleNamespace(sell_back=prices.get(key)))
    win.open("item")
    win._box.setText("sword")
    pump(qapp, 200)
    assert [_seen(r) for r in win._rows] == [("Sword", ["Lv. 10"], "One-Handed Sword", "2,500", "mesos"),
                                             ("Sword of Ice", [], "One-Handed Sword", NO_NUM, ""),
                                             ("Swordfish Scale", [], "Monster Drop", "4", "mesos")]
    assert win._rows[1].num.toolTip() == "No NPC price in the database"
    assert all(not r.pic.pixmap().isNull() for r in win._rows)


def test_droppers_and_sellers_are_capped_at_a_dozen_with_and_n_more(win, qapp, clean_location, graph, monkeypatch):
    from maplehelper import gamelookup
    monkeypatch.setattr(gamelookup, "item_sources", lambda kb, key: (
        [gamelookup.Dropper(f"monster/{1000 + i}", f"M{i}", i) for i in range(14)], []))
    win.open("item")
    win._box.setText("red")
    pump(qapp, 200)
    win._rows[0].clicked.emit()
    d = win._detail
    assert len(_links(d)) == 12 and "and 2 more" in _texts(d)


def test_an_item_nothing_drops_or_sells_says_so(win, qapp, clean_location, graph, monkeypatch):
    from maplehelper import gamelookup
    monkeypatch.setattr(gamelookup, "item_sources", lambda kb, key: ([], []))
    win.open("item")
    win._box.setText("red")
    pump(qapp, 200)
    win._rows[0].clicked.emit()
    assert _texts(win._detail) == ["No known drops or shops"]     # the fixture KB gives Red Potion no type line


def _rewards(monkeypatch, rows, quests=()):
    """The KB's rewards (and quests) tables answered with these rows, every other table read as it really is."""
    from maplehelper import tables
    real = tables.rows
    tables_by_name = {"rewards": list(rows), "quests": list(quests)}
    monkeypatch.setattr(tables, "rows", lambda kb, name, build=True: (
        tables_by_name[name] if name in tables_by_name else real(kb, name, build=build)))


def test_an_item_a_quest_gives_lists_that_quest_on_its_page(win, qapp, clean_location, graph, monkeypatch):
    """"Where do I get this?" answered by a quest: the quests that hand the item over (rewards.tsv's "sure" rows —
    Arcon's Blood comes from no monster and no shop), each with its NPC and its level, a click opening it in the
    Quests window. A quest the KB doesn't count as open is no source, and one of a roll isn't a sure one."""
    from types import SimpleNamespace

    from maplehelper import availability, gamelookup
    from maplehelper.ui.toolwindow import NAV
    monkeypatch.setattr(gamelookup, "item_sources", lambda kb, key: ([], []))
    monkeypatch.setattr(availability, "of",
                        lambda kb: SimpleNamespace(quest_open=lambda k: k != "quest/404"))
    _rewards(monkeypatch,
             [{"quest": "Arcon's Blood?", "quest_level": 21, "quest_key": "quest/10109",
               "item_key": "item/2000000", "kind": "sure", "count": 1},
              {"quest": "Closed Business", "quest_level": 30, "quest_key": "quest/404",
               "item_key": "item/2000000", "kind": "sure", "count": 1},      # not in the game: never a source
              {"quest": "Lucky Roll", "quest_level": 5, "quest_key": "quest/10200",
               "item_key": "item/2000000", "kind": "random", "count": 1},    # a roll, not what it always gives
              {"quest": "Someone Else's", "quest_level": 9, "quest_key": "quest/10300",
               "item_key": "item/999", "kind": "sure", "count": 1}],
             [{"key": "quest/10109", "npc": "Manji"}])
    win.open("item")
    win._box.setText("red")
    pump(qapp, 200)
    win._rows[0].clicked.emit()
    d = win._detail
    assert _texts(d) == ["Quest reward"]           # its own titled block, where no drop and no shop has it
    assert [(_seen(r), r.toolTip()) for r in _links(d)] == [
        (("Arcon's Blood?", ["Lv. 21"], "Manji", "", ""), "Click to open this quest in the Quests window")]
    asked = []
    NAV.tool_requested.connect(lambda key, arg: asked.append((key, arg)))
    try:
        _links(d)[0].clicked.emit()                # the row opens that quest
    finally:
        NAV.tool_requested.disconnect()
    assert asked == [("quest_tool", "quest/10109")]


def test_an_item_no_quest_gives_lists_nothing_extra(win, qapp, clean_location, graph, monkeypatch):
    from maplehelper import gamelookup
    monkeypatch.setattr(gamelookup, "item_sources", lambda kb, key: ([], []))
    _rewards(monkeypatch, [{"quest": "Someone Else's", "quest_level": 9, "quest_key": "quest/10300",
                            "item_key": "item/999", "kind": "sure", "count": 1}])
    win.open("item")
    win._box.setText("red")
    pump(qapp, 200)
    win._rows[0].clicked.emit()
    assert _texts(win._detail) == ["No known drops or shops"]
    assert _links(win._detail) == []


def test_a_tradeable_items_page_links_to_its_free_market_prices(win, qapp, kb, clean_location, graph, monkeypatch):
    """The Free Market details window (MesoWatch's sales, where to buy: ui/marketview.py), reached from an item's
    page — the old Play tools' Item price page held its only way in — for an item players can trade; an untradeable
    one (a pet: the Cash Shop only) has none."""
    from maplehelper import gamelookup, sitedata
    from maplehelper.ui.widgets import MARKET_REQUESTS
    monkeypatch.setattr(gamelookup, "item_sources", lambda kb, key: ([], []))
    monkeypatch.setattr(sitedata, "sell_list", lambda kb: sitedata.SellList("2026-10-10", {}))
    d = win._detail
    asked = []
    MARKET_REQUESTS.requested.connect(asked.append)
    try:
        d.open_view("item", "item/2000000")
        assert d.market_link is not None and d.market_link.text() == win.t("md_market") + " ›"
        d.market_link.click()
        d.open_view("sell", "item/2000000")                # its Safe to sell? page too, under the NPC price
        d.market_link.click()
        assert asked == ["item/2000000", "item/2000000"]
        monkeypatch.setattr(sitedata, "untradeable", lambda kb, key: True)
        d.open_view("item", "item/2000000")
        assert d.market_link is None
        d.open_view("sell", "item/2000000")
        assert d.market_link is None
    finally:
        MARKET_REQUESTS.requested.disconnect(asked.append)


def test_safe_to_sell_says_keep_with_what_needs_it_or_safe_with_the_npc_price(
        win, qapp, clean_location, graph, monkeypatch):
    """Safe to sell?: an item on NiaMeowDB's list is one to keep — its row's chips say why (how many quests and
    recipes, Repeatable), its page the verdict on a big chip, then each quest and recipe that needs it; off the
    list, safe, at the NPC price; a KB without the list never says "safe"."""
    from types import SimpleNamespace

    from PySide6.QtWidgets import QLabel

    from maplehelper import market, sitedata
    need = sitedata.SellNeeds("item/2000000", "Red Potion", 25,
                              (("quest/1", "Potion Run", 3, False), ("quest/2", "Daily Brew", 1, True)),
                              (("Alchemy", "Elixir", 2),), ("Al", "Bree"))
    now = {"list": sitedata.SellList("2026-10-10", {"item/2000000": need})}
    monkeypatch.setattr(sitedata, "sell_list", lambda kb: now["list"])
    monkeypatch.setattr(market, "npc_prices", lambda kb, key: SimpleNamespace(sell_back=12))
    win.open("sell")
    assert win._title.text() == "Safe To Sell"
    win._box.setText("red")
    pump(qapp, 200)
    # the list's own price for it (25), before its page's (12)
    assert _seen(win._rows[0]) == ("Red Potion", ["2 quests", "1 recipe", "Repeatable"], "", "25", "mesos")
    assert _tones(win._rows[0]) == ["quest", "craft", "repeat"]
    win._rows[0].clicked.emit()
    d = win._detail
    assert d._stack == [("sell", "item/2000000")] and _head(d) == ("Red Potion", [], "")
    verdict = _pieces(d)[0]
    assert isinstance(verdict, QLabel) and verdict.objectName() == "Verdict"
    assert (verdict.text(), verdict.property("tone")) == ("Keep", "keep")
    assert _texts(d) == ["Keep", "A current quest or crafting recipe still needs it", "Quests that need it",
                         "Recipes that use it", "NPC shops that sell it",
                         "From NiaMeowDB's Safe to Sell? list, 2026-10-10"]
    assert [_seen(r) for r in _links(d)] == [
        ("Potion Run", ["×3"], "", "", ""), ("Daily Brew", ["×1", "Repeatable"], "", "", ""),
        ("Elixir", ["×2"], "Alchemy", "", ""), ("What an NPC pays for one", [], "", "25", "mesos"),
        ("Al, Bree", [], "You can buy it back (shop access may vary)", "", ""), ("Who drops and sells it", [], "", "›", "")]
    assert all(not r.pic.pixmap().isNull() for r in _links(d)[:3])     # each quest its giver's, each recipe its own
    _links(d)[-1].clicked.emit()                        # its item page, ‹ Back to the verdict
    assert d._stack == [("sell", "item/2000000"), ("item", "item/2000000")]
    now["list"] = sitedata.SellList("2026-10-10", {})   # nothing needs it any more
    win._run()
    assert _seen(win._rows[0]) == ("Red Potion", ["Safe to sell"], "", "12", "mesos")
    assert _tones(win._rows[0]) == ["safe"]
    win._rows[0].clicked.emit()
    assert _pieces(d)[0].property("tone") == "safe"
    assert _texts(d) == ["Safe to sell", "No current quest or crafting recipe needs it",
                         "From NiaMeowDB's Safe to Sell? list, 2026-10-10"]
    assert [_seen(r) for r in _links(d)] == [("What an NPC pays for one", [], "", "12", "mesos"),
                                             ("Who drops and sells it", [], "", "›", "")]
    now["list"] = None                                  # a KB from before the list
    win._run()
    assert win._rows[0].chips == [] and win._filter.isHidden()     # nothing known either way: no chips, no switch
    assert win._status.text() == "The Safe To Sell list isn't in your database yet. It comes with the next update."
    win._rows[0].clicked.emit()
    assert _texts(d) == ["The Safe To Sell list isn't in your database yet. It comes with the next update."]


def _sell_items(kb, monkeypatch):
    """Safe to sell? over 59 items "Item 000"... and Red Potion (seeded as the items search lists them: by name),
    NiaMeowDB's list needing four of them — Red Potion under another item of its name (the list picks one of two
    items sharing a name: Hero's Gladius, item/556 on it, item/465 searched) — and an NPC buying all but Item 001."""
    from types import SimpleNamespace

    from maplehelper import market, sitedata
    from maplehelper.kb import memo
    from maplehelper.ui.gamesearch import Hit
    memo(kb, "_game_search")["item"] = ([Hit(f"item/{i:03d}", f"Item {i:03d}", "Etc / Monster Drop") for i in range(59)]
                                        + [Hit("item/2000000", "Red Potion", "Use / Potion")])

    def quests(n, repeat=False):
        return tuple((f"quest/{i}", f"Quest {i}", 1, repeat and i == 0) for i in range(n))

    def recipes(n):
        return tuple(("Smithing", f"Recipe {i}", 2) for i in range(n))
    needs = {"item/040": sitedata.SellNeeds("item/040", "Item 040", 25, quests(2, True), recipes(1), ()),
             "item/041": sitedata.SellNeeds("item/041", "Item 041", 1234, (), recipes(5), ()),
             "item/042": sitedata.SellNeeds("item/042", "Item 042", 3, quests(1), (), ()),
             "item/999": sitedata.SellNeeds("item/999", "Red Potion", 7, quests(1), (), ())}
    monkeypatch.setattr(sitedata, "sell_list", lambda kb: sitedata.SellList("2026-10-10", needs))
    monkeypatch.setattr(market, "npc_prices",
                        lambda kb, key: SimpleNamespace(sell_back=None if key == "item/001" else 10))


def test_safe_to_sell_lists_fifty_before_anything_is_typed_the_most_needed_first(win, qapp, kb, monkeypatch):
    """It lists the items as soon as it opens, as NiaMeowDB's page sorts them: the ones a current quest or recipe
    needs first, the most needed first, then the rest by name — the first 50, and how many more; each row its
    why-keep chips (or Safe to sell, or No NPC price) and what an NPC pays on the end."""
    from maplehelper.ui import gamesearch
    _sell_items(kb, monkeypatch)
    win.open("sell")
    assert win._box.text() == "" and len(win._rows) == gamesearch.LIMIT == 50
    assert win._status.text() == "and 10 more — type more to narrow it down"
    assert [_seen(r) for r in win._rows[:6]] == [
        ("Item 041", ["5 recipes"], "", "1,234", "mesos"),
        ("Item 040", ["2 quests", "1 recipe", "Repeatable"], "", "25", "mesos"),
        ("Item 042", ["1 quest"], "", "3", "mesos"),
        ("Red Potion", ["1 quest"], "", "10", "mesos"),     # kept by its name; the list's price is the other item's
        ("Item 000", ["Safe to sell"], "", "10", "mesos"),
        ("Item 001", ["No NPC price"], "", gamesearch.NO_NUM, "")]   # the list leaves out what no NPC buys
    assert [_tones(r) for r in win._rows[:6]] == [["craft"], ["quest", "craft", "repeat"], ["quest"], ["quest"],
                                                  ["safe"], [""]]
    assert [r.name.text() for r in win._rows[6:9]] == ["Item 002", "Item 003", "Item 004"]
    assert all(not r.pic.pixmap().isNull() for r in win._rows)
    assert win._filter.isVisibleTo(win) and win._filter.value() == "all"
    from maplehelper import bidi
    from maplehelper.i18n import I18n
    win.apply_language(I18n("he"))      # one quest in its own words (not "1 quests"); the price's unit stays mesos
    assert [c.text() for c in win._rows[2].chips] == [bidi.plain("קווסט אחד", True)]
    assert win._rows[2].unit.text() == bidi.plain("mesos", True)


def test_the_switch_narrows_safe_to_sell_to_the_safe_or_the_kept_ones(win, qapp, kb, monkeypatch):
    """All / Safe to sell / Keep: the rows narrowed at once, typing searching only what the switch keeps, and the
    switch kept while the toolbar switches modes (shown in Safe to sell? alone)."""
    _sell_items(kb, monkeypatch)
    win.open("sell")
    buttons = {b.property("value"): b for b in win._filter.group.buttons()}
    assert [b.text() for b in win._filter.group.buttons()] == ["All", "Safe to sell", "Keep"]
    buttons["safe"].click()                             # only what nothing needs and an NPC buys
    assert win._total == 55 and len(win._rows) == 50
    assert win._status.text() == "and 5 more — type more to narrow it down"
    assert all(_seen(r)[1] == ["Safe to sell"] for r in win._rows)
    buttons["keep"].click()                             # only what something needs, the most needed first
    assert [r.name.text() for r in win._rows] == ["Item 041", "Item 040", "Item 042", "Red Potion"]
    assert win._status.text() == ""
    win._box.setText("potion")
    pump(qapp, 200)
    assert [r.name.text() for r in win._rows] == ["Red Potion"]
    buttons["safe"].click()
    assert not win._rows and win._status.text() == "Nothing found for “potion”"
    buttons["keep"].click()
    win.open("item")                                    # another mode: no switch there
    assert win._filter.isHidden()
    win.open("sell")                                    # back: the switch and the query as they were left
    assert not win._filter.isHidden() and win._filter.value() == "keep" and win._box.text() == "potion"
    assert [r.name.text() for r in win._rows] == ["Red Potion"]


def test_an_npc_on_the_players_map_guides_and_hiding_clears_it(win, qapp, kb, clean_location, graph, monkeypatch):
    from maplehelper import gamelookup
    from maplehelper.ui.location import LOCATION
    spot = (0.6, 0.5)                                  # 200 map units right of the player
    monkeypatch.setattr(gamelookup, "npc_place",
                        lambda kb, key, here_map=None: gamelookup.Place(MID, "Fake Town", "Fake Street", spot))
    monkeypatch.setattr(gamelookup, "map_monsters", lambda kb, key: [])
    monkeypatch.setattr(gamelookup, "way_to", lambda kb, here, to, rides=True:
                        gamelookup.Way(here="999999999", legs=(), known=False))
    clean_location.set(_here(MID, (0.5, 0.5)))
    win.open("monster_npc")
    win._detail.open_view("npc", "npc/3")
    d = win._detail
    name = _kb_name(kb, "npc/3")
    assert d.isVisible() and LOCATION.guide == (MID, spot, "npc/3")      # the game's own minimap rings it
    assert _head(d) == (name, ["NPC"], "") and [c.property("tone") for c in d.chips] == ["npc"]
    assert _texts(d) == [f"{name} is to your right"]
    clean_location.set(_here(MID, (0.86, 0.5)))        # the player walks past it: the sentence follows
    assert _texts(d) == [f"{name} is to your left"] and LOCATION.guide == (MID, spot, "npc/3")
    win.hide()
    assert not d.isVisible() and LOCATION.guide is None                     # hidden: the ring is let go
    clean_location.set(_here(MID, (0.5, 0.5)))
    win.open("monster_npc")
    d.open_view("npc", "npc/3")
    assert LOCATION.guide == (MID, spot, "npc/3")
    clean_location.set(_here("999999999", (0.5, 0.5)))  # another map: the ring goes, the way from there shown
    assert LOCATION.guide is None
    assert _texts(d) == [f"{name} is on Fake Town", "The way from here on foot",
                         win.t("lk_way_none_walk")]
    clean_location.set(_here(MID, (0.5, 0.5)))          # back on it: the map's own page says so
    d.open_view("map", f"map/{MID}")
    assert _head(d) == ("Fake Town", [], "Fake Street") and _texts(d) == ["You're on this map"]
    assert LOCATION.guide is None


def test_redrawing_an_npc_page_keeps_its_guide_until_the_page_or_the_window_lets_go(
        win, qapp, kb, clean_location, graph, monkeypatch):
    """The minimap reads redraw the page as the player moves (_moved): a redraw that guides the same NPC to
    the same spot never lets the guide go in between, so LOCATION.guided fires once for it, not once per read."""
    from maplehelper import gamelookup
    from maplehelper.ui.location import LOCATION
    spots = {"npc/3": (0.6, 0.5), "npc/4": (0.4, 0.5)}
    monkeypatch.setattr(gamelookup, "npc_place",
                        lambda kb, key, here_map=None: gamelookup.Place(MID, "Fake Town", "Fake Street",
                                                                        spots[key]) if key in spots else None)
    guided = []
    LOCATION.guided.connect(guided.append)
    try:
        clean_location.set(_here(MID, (0.5, 0.5)))
        win.open("monster_npc")
        d = win._detail
        d.open_view("npc", "npc/3")
        assert LOCATION.guide == (MID, spots["npc/3"], "npc/3") and guided == [(MID, spots["npc/3"], "npc/3")]
        for x in (0.51, 0.52, 0.53):                    # still reads, still the same NPC at the same spot
            clean_location.set(_here(MID, (x, 0.5)))
        assert LOCATION.guide == (MID, spots["npc/3"], "npc/3")
        assert guided == [(MID, spots["npc/3"], "npc/3")]          # one arming, not one per redraw
        d.open_view("npc", "npc/4")                                # another NPC: re-armed once, never via None
        assert guided == [(MID, spots["npc/3"], "npc/3"), (MID, spots["npc/4"], "npc/4")]
        clean_location.set(_here(MID, (0.54, 0.5)))
        assert guided == [(MID, spots["npc/3"], "npc/3"), (MID, spots["npc/4"], "npc/4")]
        d.open_view("npc", "npc/5")                                # nowhere the KB can place it: cleared once
        assert LOCATION.guide is None
        assert guided == [(MID, spots["npc/3"], "npc/3"), (MID, spots["npc/4"], "npc/4"), None]
        clean_location.set(_here(MID, (0.55, 0.5)))
        assert guided == [(MID, spots["npc/3"], "npc/3"), (MID, spots["npc/4"], "npc/4"), None]
        d.open_view("npc", "npc/3")
        win.hide()                                                 # hidden: the ring is let go, once
        assert not d.isVisible() and LOCATION.guide is None
        assert guided == [(MID, spots["npc/3"], "npc/3"), (MID, spots["npc/4"], "npc/4"), None,
                          (MID, spots["npc/3"], "npc/3"), None]
    finally:
        LOCATION.guided.disconnect(guided.append)


def test_an_npc_elsewhere_shows_the_way_there_step_by_step_with_each_maps_picture(
        win, qapp, kb, clean_location, graph, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QLabel

    from maplehelper import gamelookup
    from maplehelper.i18n import I18n
    from maplehelper.routes import Leg
    from maplehelper.ui import mapview
    from maplehelper.ui.location import LOCATION
    walk = (Leg(MID, FAR, "portal", "the door", spot=(0.9, 0.5)),)
    ride = (Leg(MID, "010020002", "taxi", "Regular Cab", npc="npc/8", spot=(0.2, 0.5)),
            Leg("010020002", FAR, "npc", "Bart", npc="npc/9", spot=(0.1, 0.5)))
    monkeypatch.setattr(gamelookup, "npc_place",
                        lambda kb, key, here_map=None: gamelookup.Place(FAR, "Far Map", "Far Street", (0.5, 0.5)))
    monkeypatch.setattr(gamelookup, "way_to", lambda kb, here, to, rides=True:
                        gamelookup.Way(here=MID, legs=ride if rides else walk, known=True))
    clean_location.set(_here(MID, (0.5, 0.5)))
    win.open("monster_npc")
    win._detail.open_view("npc", "npc/3")
    d = win._detail
    t = I18n("en")

    def says(legs):
        """Each step as the page reads: its number and map, then what to do there."""
        return [line for i, leg in enumerate(legs, 1)
                for line in (f"{i} · {d._map_name(graph, leg.frm)}",
                             mapview.route_says(t, graph, leg).replace("**", ""))]

    drawn = []

    def picture(path, spot=None, npc=False, you=None, cap_w=0):
        drawn.append((path, spot, npc, you))
        pm = QPixmap(10, 10)
        pm.fill(Qt.black)
        return pm
    monkeypatch.setattr(graph, "minimap", lambda mid: f"minimap/{mid}", raising=False)
    monkeypatch.setattr(mapview, "route_picture", picture)
    d.redraw()
    # the toolbar's Cabs & Teleports off (the default): on foot. Opened, the way armed the game minimap's route arrow
    # at the NPC's map by itself, the page saying so over the steps
    guiding = "Route arrow: to Far Map"
    assert LOCATION.route_dest == FAR
    assert _texts(d) == [f"{_kb_name(kb, 'npc/3')} is on Far Map", "The way from here on foot", guiding, *says(walk)]
    # the NPC's own map, then each step's map with its portal (orange) or NPC (green) marked, as the ◎ window draws
    # them; the player's blue dot on the first, the map they're on
    assert drawn == [(f"minimap/{FAR}", (0.5, 0.5), True, None), (f"minimap/{MID}", (0.9, 0.5), False, (0.5, 0.5))]
    assert len([w for w in _pieces(d) if isinstance(w, QLabel) and not w.pixmap().isNull()]) == 2
    # the steps' **bold** names are drawn bold, never shown as asterisks (offscreen render, 2026-10-10)
    assert all("**" not in w.text() for w in _pieces(d) if hasattr(w, "text"))
    assert LOCATION.guide is None                      # never ringed: it isn't where the player is
    # switched on: the page shown finds the way again, by cab and NPC teleport; off again, back on foot
    win._settings["game_rides"] = True
    win.rides_changed()
    assert _texts(d) == [f"{_kb_name(kb, 'npc/3')} is on Far Map", "The way from here by cab and teleport", guiding,
                         *says(ride)]
    win._settings["game_rides"] = False
    win.rides_changed()
    assert _texts(d)[1:] == ["The way from here on foot", guiding, *says(walk)]


def test_a_maps_page_arms_the_route_arrow_as_it_opens_and_lets_go_of_it_hidden(
        win, qapp, clean_location, graph, monkeypatch):
    """A map with a way there from the player's: its page, as it opens (a search click, a row's, ‹ Back), points the
    game minimap's route arrow along the way (LOCATION.route_dest) by itself, and a muted line heading the way, under
    its title and over the steps, says so. Nothing on the page to click: ⚙'s route arrow switch alone turns it off.
    Drawn again (the player walking on) it stays armed; pointed elsewhere in the ◎ window, the line goes and no redraw
    takes the arrow back. Hidden, the window lets go of the arrow it armed, never another window's. Nothing armed and
    no line with ⚙'s route arrow off, on the map itself, or with no way known (the player's map not read yet)."""
    from PySide6.QtWidgets import QLabel

    from maplehelper import gamelookup
    from maplehelper.routes import Leg
    walk = (Leg(MID, FAR, "portal", "the door", spot=(0.9, 0.5)),)

    def way_to(kb, here, to, rides=True):
        if here is None:
            return gamelookup.Way(None, (), False)
        return gamelookup.Way(here, () if here == to else walk, True)
    monkeypatch.setattr(gamelookup, "way_to", way_to)
    monkeypatch.setattr(gamelookup, "map_monsters", lambda kb, key: [])
    clean_location.set(_here(MID))
    win.open("monster_npc")
    d = win._detail
    d.open_view("map", f"map/{FAR}")
    title, step, guiding = "The way from here on foot", "1 · Fake Town", "Route arrow: to Far Map"
    assert clean_location.route_dest == FAR                      # armed as it opened: the game's minimap points there
    assert _texts(d)[:3] == [title, guiding, step]               # said heading the way, over the steps
    assert all(isinstance(w, QLabel) for w in _pieces(d))        # nothing to click
    d.redraw()                                                   # drawn again: still armed, still said
    clean_location.set(_here(MID, (0.4, 0.5)))                   # the player walks on: likewise
    assert clean_location.route_dest == FAR and _texts(d)[:3] == [title, guiding, step]
    clean_location.set_route_dest(GARDEN)                        # pointed elsewhere in the ◎ window: the line goes,
    d.redraw()                                                   # and no redraw takes the arrow back
    clean_location.set(_here(MID, (0.6, 0.5)))
    assert clean_location.route_dest == GARDEN and _texts(d)[:2] == [title, step]
    d.push("map", f"map/{MID}")                                  # their own map's page: nothing to arm there
    assert clean_location.route_dest == GARDEN and _texts(d) == ["You're on this map"]
    d.go_back()                                                  # ‹ Back: the way opened again, armed again
    assert clean_location.route_dest == FAR and _texts(d)[:3] == [title, guiding, step]
    win._settings["minimap_route_arrow"] = False                 # ⚙'s switch off: no arrow drawn, and the page drawn
    win.rides_changed()                                          # again (the app's _minimap_toggled) says none
    assert _texts(d)[:2] == [title, step] and guiding not in _texts(d)
    win._settings["minimap_route_arrow"] = True
    win.hide()                                                   # hidden with the search: the arrow it armed let go
    assert not d.isVisible() and clean_location.route_dest is None
    win.open("monster_npc")
    d.open_view("map", f"map/{FAR}")
    assert clean_location.route_dest == FAR
    clean_location.set_route_dest(GARDEN)                        # pointed elsewhere in the ◎ window meanwhile
    d.close_btn.click()                                          # hidden: that one isn't this window's to let go
    assert not d.isVisible() and clean_location.route_dest == GARDEN
    clean_location.set_route_dest(None)
    win._settings["minimap_route_arrow"] = False                 # ⚙'s route arrow off: the steps, nothing armed
    d.open_view("map", f"map/{FAR}")
    assert clean_location.route_dest is None and _texts(d)[:2] == [title, step] and guiding not in _texts(d)
    win._settings["minimap_route_arrow"] = True
    clean_location.set(_here(FAR))                               # on the map itself: nowhere to guide to
    d.open_view("map", f"map/{FAR}")
    assert clean_location.route_dest is None and _texts(d) == ["You're on this map"]
    clean_location.set(None)                                     # their map not read yet: no way known
    d.open_view("map", f"map/{FAR}")
    assert clean_location.route_dest is None and _texts(d) == [title, win.t("lk_way_unknown_here")]


def test_the_maps_are_listed_before_anything_is_typed_and_a_search_narrows_them(win, qapp, kb, monkeypatch):
    """Maps: the first 50 by name as soon as it opens, with how many more there are; typing narrows them as every
    search does; each row its minimap's picture, the levels it is for on a chip, its street muted, and a click
    opens the map's own page."""
    from PySide6.QtCore import QSize

    from maplehelper import tables
    from maplehelper.ui import gamesearch
    rows = [{"key": f"map/{100000000 + i:09d}", "map": f"Field {i:03d}", "street": "Victoria Road",
             "lv_min": i, "lv_max": i + 5} for i in range(60)]
    rows.append({"key": "map/100000999", "map": "Henesys", "street": "Victoria Road", "lv_min": None, "lv_max": None})
    rows.append({"key": "map/100000998", "map": "Henesys Pig Farm", "street": "Victoria Road", "lv_min": 7, "lv_max": 7})
    real = tables.rows
    monkeypatch.setattr(tables, "rows", lambda kb, name, *a, **kw: rows if name == "maps" else real(kb, name, *a, **kw))
    monkeypatch.setattr(tables, "ready", lambda kb: True)
    opened = []
    monkeypatch.setattr(win._detail, "open_view", lambda kind, key: opened.append((kind, key)))
    win.open("map")
    assert win._title.text() == "Maps" and win._box.placeholderText() == "Search maps…"
    assert len(win._rows) == gamesearch.LIMIT == 50
    assert _seen(win._rows[0]) == ("Field 000", ["Lv. 0–5"], "Victoria Road", "", "")
    assert win._rows[0].pic.size() == QSize(*gamesearch.MAP_PIC) and not win._rows[0].pic.pixmap().isNull()
    assert win._status.text() == "and 12 more — type more to narrow it down"
    win._box.setText("henesys")
    pump(qapp, 200)
    assert [_seen(r) for r in win._rows] == [("Henesys", [], "Victoria Road", "", ""),
                                             ("Henesys Pig Farm", ["Lv. 7"], "Victoria Road", "", "")]
    assert win._status.text() == ""
    win._rows[0].clicked.emit()
    assert opened == [("map", "map/100000999")]


@pytest.mark.parametrize("kind", ["item", "monster_npc"])
def test_items_and_monsters_and_npcs_are_listed_before_anything_is_typed(win, qapp, kb, kind):
    """Like the maps, the first LIMIT rows as soon as it opens, no "type more" line: the items by name, the
    monsters by level and then the NPCs; one letter typed still lists them (two narrow it, as before)."""
    from maplehelper.ui import gamesearch
    hits, total = gamesearch.search(kb, kind, "")
    assert 0 < len(hits) == min(total, gamesearch.LIMIT)
    if kind == "item":
        assert [h.name.casefold() for h in hits] == sorted(h.name.casefold() for h in hits)
    else:
        monsters = [h for h in hits if h.kind == "monster"]
        assert monsters and hits[:len(monsters)] == monsters                 # the monsters first...
        assert [h.lv for h in monsters] == sorted(h.lv for h in monsters)     # ... by level
    win.open(kind)
    assert [r.name.text() for r in win._rows] == [h.name for h in hits]
    assert win._status.text() in ("", f"and {total - len(hits):,} more — type more to narrow it down")
    win._box.setText("s")
    pump(qapp, 200)
    assert [r.name.text() for r in win._rows] == [h.name for h in hits]


def test_switching_modes_keeps_each_ones_query(win, qapp):
    modes = []
    win.open("monster_npc")
    win._box.setText("snail")
    pump(qapp, 200)
    win.mode_changed.connect(modes.append)
    win.open("item")                                           # another mode while it shows: a switch, not a toggle
    assert win.isVisible() and win._kind == "item" and win._box.text() == "" and modes == ["item"]
    win._box.setText("red")
    pump(qapp, 200)
    win.open("monster_npc")
    assert win._box.text() == "snail" and [r.name.text() for r in win._rows] == ["Snail", "Blue Snail", "Red Snail"]
    win.open("item")
    assert win._box.text() == "red" and win._rows
    assert modes == ["item", "monster_npc", "item"]


def test_monsters_and_npcs_list_together_and_each_opens_its_own_page(win, qapp, clean_location, monkeypatch):
    """One search over both: an NPC beside the monsters with the same words, each row's chips saying which it is
    (a monster's with its level, Boss beside a boss), and a click opening the monster's page or the NPC's. (The
    fixture KB's own NPCs are all shut by its release guide.)"""
    from maplehelper.ui import gamesearch
    monkeypatch.setitem(gamesearch._BUILDERS, "npc",
                        lambda kb: [gamesearch.Hit("npc/3", "Snail Keeper", "Henesys · Victoria Road", "npc")])
    mobs = gamesearch._BUILDERS["monster"]
    monkeypatch.setitem(gamesearch._BUILDERS, "monster", lambda kb: mobs(kb) + [
        gamesearch.Hit("monster/9999", "Snail King", "5,000 HP", "monster", (20, 20), True)])
    opened = []
    monkeypatch.setattr(win._detail, "open_view", lambda kind, key: opened.append((kind, key)))
    win.open("monster_npc")
    win._box.setText("snail")
    pump(qapp, 200)
    rows = {r.name.text(): r for r in win._rows}
    # ranked together: the exact name, then the ones "snail" starts, then the rest
    assert list(rows) == ["Snail", "Snail Keeper", "Snail King", "Blue Snail", "Red Snail"]
    assert _seen(rows["Snail Keeper"]) == ("Snail Keeper", ["NPC"], "Henesys · Victoria Road", "", "")
    assert _seen(rows["Snail King"]) == ("Snail King", ["Monster · Lv. 20", "Boss"], "5,000 HP", "", "")
    assert [_tones(rows[n]) for n in ("Snail", "Snail Keeper", "Snail King")] == [
        ["monster"], ["npc"], ["monster", "boss"]]
    rows["Snail Keeper"].clicked.emit()
    rows["Snail"].clicked.emit()
    assert opened == [("npc", "npc/3"), ("monster", win._hits[0].key)]


def test_esc_in_the_box_hides(win, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    modes = []
    win.mode_changed.connect(modes.append)
    win.open("monster_npc")
    QTest.keyClick(win._box, Qt.Key_Escape)
    assert not win.isVisible() and modes == ["monster_npc", ""]


def test_apply_language_retexts_and_mirrors(win, qapp):
    import re

    from PySide6.QtCore import Qt
    from maplehelper import bidi
    from maplehelper.i18n import I18n
    win.open("monster_npc")
    win._box.setText("snail")
    pump(qapp, 200)
    win.apply_language(I18n("he"))
    assert win.layoutDirection() == Qt.RightToLeft and win._detail.layoutDirection() == Qt.RightToLeft
    assert win._title.text() == bidi.plain("חיפוש מפלצת או דמות", True)
    assert win._box.placeholderText() == bidi.plain("שם המפלצת או הדמות…", True)
    assert [r.name.text() for r in win._rows] == [bidi.ltr_name(n, True) for n in ("Snail", "Blue Snail", "Red Snail")]      # rebuilt, still there
    row = win._rows[0]
    chip = row.chips[0]
    bare = re.sub("[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", chip.text())     # the direction marks off
    assert bare == "מפלצת · רמה 1"                       # its level in Hebrew words (lv_short), no "Lv"
    pump(qapp, 50)
    assert chip.geometry().right() < row.name.geometry().left()      # mirrored: the name at the right, its chip left


def test_the_lit_row_and_the_switch_take_the_accent_picked(win, qapp, settings):
    """The ⚙ look's accent lights the open page's row and the switch's picked segment, in both windows' style
    sheets; picked again, both follow (the app calls _read_opacity whenever the look changes)."""
    from maplehelper.ui import gamesearch, npcoverlay
    win.open("sell")
    green = npcoverlay.accent_of(settings)[0]
    assert gamesearch._rgba(green, 0.26) in win.styleSheet()
    settings["overlay_accent"] = "purple"
    win._read_opacity()
    purple = npcoverlay.ACCENTS["purple"][1]
    sheet = win.styleSheet()
    assert gamesearch._rgba(purple, 0.26) in sheet and gamesearch._rgba(green, 0.26) not in sheet
    assert f"QPushButton#Segment:checked {{ background: {purple};" in sheet
    assert win._detail.styleSheet() == sheet


def test_the_white_glass_takes_dark_text_and_back(win, qapp, settings):
    """The ⚙ panel's white glass: both windows' style sheets in the light palette's dark text (no light text left,
    the chips' pastels darkened by ink); the dark glass again, today's light text back."""
    from maplehelper.ui import gamesearch, npcoverlay
    win.open("sell")
    assert npcoverlay.DARK.text in win.styleSheet()
    settings["overlay_tint"] = "white"
    npcoverlay.apply_look(settings)
    win._read_opacity()                                     # what the app calls whenever the look changes
    sheet = win.styleSheet()
    assert f"color: {npcoverlay.LIGHT.text};" in sheet and npcoverlay.DARK.text not in sheet
    assert npcoverlay.DARK.muted not in sheet and "rgba(255,255,255" not in sheet
    assert f"color: {npcoverlay.ink(gamesearch.TONES['safe'])};" in sheet and gamesearch.TONES["safe"] not in sheet
    assert win._detail.styleSheet() == sheet
    settings["overlay_tint"] = "dark"
    npcoverlay.apply_look(settings)
    win._read_opacity()
    sheet = win.styleSheet()
    assert f"color: {npcoverlay.DARK.text};" in sheet and npcoverlay.LIGHT.text not in sheet
    assert win._detail.styleSheet() == sheet


# ---------------------------------------------------------------- a monster's Hit & damage (the old Play tools page)

STUMP, SNAIL_KEY, RED_SNAIL = "monster/5130104", "monster/100100", "monster/130101"


@pytest.fixture
def fight_kb(_own_kb, tmp_path, monkeypatch):
    """This file's KB with an AVOID and P.DEF for Axe Stump (Lv. 17; the fixture pages have none), the players' mesos
    for Snail (as test_community's KB has them) and an EXP table for level 15."""
    import json
    import shutil

    from maplehelper import plan
    from maplehelper.kb import KnowledgeBase
    root = tmp_path / "fight_kb"
    shutil.copytree(_own_kb, root)
    page = root / "pages" / "monster" / "5130104.md"
    page.write_text(page.read_text(encoding="utf-8") + "\nAVOID\n20\nP.DEF\n15\n", encoding="utf-8")
    (root / "community.json").write_text(json.dumps({"source": "test", "fetched": "2026-10-04", "monsters": {
        SNAIL_KEY: {"drops": [], "mesos": {"min": 18, "max": 23, "chance": 60, "count": 12, "trusted": 9},
                    "fetched": "2026-10-04"}}}), encoding="utf-8")
    monkeypatch.setattr(plan, "exp_table", lambda kb: {15: 1000})
    return KnowledgeBase(root)


@pytest.fixture
def fight(qapp, settings, profiles, fight_kb):
    from maplehelper.i18n import I18n
    from maplehelper.ui.gamesearch import GameSearch
    w = GameSearch(fight_kb, settings, profiles, I18n("en"))
    yield w
    delete_window(qapp, w)


def _figures(d) -> dict[str, tuple[str, str]]:
    """The Hit & damage figures as the player reads them: each one's name -> (its big number, the line under it)."""
    from maplehelper import bidi

    def strip(s: str) -> str:
        return "".join(ch for ch in s if ch not in (bidi.LRI, bidi.PDI, bidi.RLM))
    return {strip(label): (strip(value), strip(sub)) for label, value, sub in (f.figure for f in d.hit_figures)}


def _calc_block(d):
    """The page's last block: Hit & damage."""
    from maplehelper.ui.gamesearch import _Block
    block = d._rows[-1]
    assert isinstance(block, _Block) and block.title.text() == d._owner.t("tool_calc")
    return block


@pytest.mark.parametrize("cls, job, stat", [("Thief", "Assassin", "DEX"), ("Magician", "Wizard", "INT")])
def test_hit_and_damage_are_combats_figures_for_the_active_character(fight, fight_kb, profiles, cls, job, stat):
    """Each figure is combat's own for the character on the monster: the hit chance with its ACC and what is missing
    for 100% (in DEX, a Magician's INT), the ACC to never miss, the stat window's damage after the monster's P.DEF
    and the basic hits that kill it (a Magician's too: the staff swing), the EXP a kill gives, the kills to the next
    level from the EXP bar."""
    import math

    from maplehelper import combat
    c = profiles.add("Kiwi", cls, job, 15)
    c.exp_pct = 40.0
    c.stats = {"acc": 60, "dmg_min": 20, "dmg_max": 40}
    m = combat.monster(fight_kb, STUMP)
    assert (m.level, m.avoid, m.pdef) == (17, 20, 15)
    fight._detail.open_view("monster", STUMP)
    t, figs = fight.t, _figures(fight._detail)
    hit = combat.hit_chance(60, 15, 17, 20)
    need = combat.acc_needed(15, 17, 20)
    assert 0 < hit < 1                                  # a gap to close
    short = need - 60
    pts = math.ceil(short / combat.acc_per_point(cls))
    assert figs[t("calc_hit")] == (f"{round(hit * 100)}%", t("calc_more_acc", n=short, pts=pts, stat=stat))
    assert figs[t("md_acc")] == (str(need), t("calc_acc_need90", n=combat.acc_needed(15, 17, 20, 0.9)))
    lo, hi = (int(combat.landed(x, 15, 15, 17)) for x in (20, 40))
    assert figs[t("md_damage")] == (f"{lo}–{hi}", t("md_damage_sub", range="20–40", n="15"))
    hits, avg = combat.hits_to_kill(20, 40, m, 15)
    assert figs[t("md_hits")] == (str(hits), t("md_avg", n=f"{avg:.1f}") if avg < hits - 0.05 else "")
    assert figs[t("md_exp")] == ("32", "")
    kills = combat.kills_to_level(fight_kb, 15, 40.0, m)
    assert kills == math.ceil(1000 * 0.6 / 32) and figs[t("md_kills", n=16)] == (f"{kills:,}", "")
    assert fight._detail.stats_link is None                         # every stat typed: nothing to ask for
    notes = [w.text() for w in _calc_block(fight._detail).items if hasattr(w, "text")]
    assert t("calc_hits_mage" if cls == "Magician" else "calc_hits_basic") in notes


def test_a_monster_that_never_dodges_is_always_hit(fight, profiles):
    c = profiles.add("Kiwi", "Thief", "Assassin", 15)
    c.stats = {"acc": 5}
    fight._detail.open_view("monster", SNAIL_KEY)            # Avoid 0
    t, d = fight.t, fight._detail
    figs = _figures(d)
    assert figs[t("calc_hit")] == ("100%", "") and figs[t("md_acc")] == ("0", t("md_never_dodges"))
    hit = next(f for f in d.hit_figures if f.figure[0] == t("calc_hit"))
    assert hit.findChildren(type(d.title), "FigValue")[0].property("tone") == "good"


def test_without_a_character_hit_and_damage_is_one_line(fight):
    fight._detail.open_view("monster", STUMP)
    d = fight._detail
    block = _calc_block(d)
    assert [w.text() for w in block.items] == [fight.t("md_no_char")]
    assert d.hit_figures == [] and d.stats_link is None


def test_without_stats_it_says_which_and_links_to_the_stats_editor(fight, profiles):
    """No ACC and no damage typed: only what needs none (the ACC to never miss, EXP, kills), the line saying both are
    needed and "Type your stats", which opens Grind spots (its stats editor). The ACC alone: the hit chance, and the
    damage still asked for."""
    from maplehelper.ui.toolwindow import NAV
    c = profiles.add("Kiwi", "Thief", "Assassin", 15)
    d, t = fight._detail, fight.t
    d.open_view("monster", STUMP)
    figs = _figures(d)
    assert t("calc_hit") not in figs and t("md_damage") not in figs and t("md_hits") not in figs
    assert {t("md_acc"), t("md_exp"), t("md_kills", n=16)} <= set(figs)
    assert figs[t("md_kills", n=16)][1] == t("md_kills_from0")     # no EXP bar read: counted from 0%
    texts = [w.text() for w in _calc_block(d).items if hasattr(w, "text")]
    assert t("md_need_both") in texts and d.stats_link is not None
    asked = []
    NAV.tool_requested.connect(lambda key, arg: asked.append((key, arg)))
    try:
        d.stats_link.click()
    finally:
        NAV.tool_requested.disconnect()
    assert asked == [("grind_spots", "")]
    c.stats = {"acc": 60}
    fight.character_changed()                     # the stats typed: the page drawn again for them
    figs = _figures(d)
    assert t("calc_hit") in figs and t("md_damage") not in figs
    texts = [w.text() for w in _calc_block(d).items if hasattr(w, "text")]
    assert t("md_need_dmg") in texts and t("md_need_both") not in texts
    c.stats = {"acc": 60, "dmg_min": 20, "dmg_max": 40}
    fight.character_changed()
    assert t("md_damage") in _figures(d) and d.stats_link is None


def test_another_character_redraws_the_monster_page(fight, profiles):
    a = profiles.add("Kiwi", "Thief", "Assassin", 15)
    a.stats = {"acc": 60}
    d = fight._detail
    d.open_view("monster", STUMP)
    assert fight.t("calc_hit") in _figures(d)
    b = profiles.add("Mango", "Warrior", "Fighter", 15)
    profiles.active_id = b.id
    fight.character_changed()
    assert fight.t("calc_hit") not in _figures(d) and d.stats_link is not None
    profiles.active_id = None
    fight.character_changed()
    assert d.hit_figures == []


def test_hit_and_damage_shows_the_mesos_players_reported(fight, fight_kb, profiles):
    """Ported from the old Play tools' Hit & damage (test_community): the mesos range players reported and its
    average per kill; a monster nobody reported says so."""
    profiles.add("Kiwi", "Thief", "Thief", 3)
    d, t = fight._detail, fight.t
    d.open_view("monster", SNAIL_KEY)
    assert _figures(d)[t("calc_mesos")] == ("18–23", t("md_avg", n=f"{fight_kb.mesos_per_kill(SNAIL_KEY):,.0f}"))
    assert f"{fight_kb.mesos_per_kill(SNAIL_KEY):,.0f}" == "12"
    d.open_view("monster", RED_SNAIL)
    assert _figures(d)[t("calc_mesos")] == ("\u2014", t("mesos_none"))


def test_the_hebrew_figures_read_left_to_right(fight_kb, qapp, settings, profiles):
    from maplehelper import bidi
    from maplehelper.i18n import I18n
    from maplehelper.ui.gamesearch import GameSearch
    c = profiles.add("Kiwi", "Thief", "Assassin", 15)
    c.stats = {"acc": 60, "dmg_min": 20, "dmg_max": 40}
    w = GameSearch(fight_kb, settings, profiles, I18n("he"))
    try:
        w._detail.open_view("monster", STUMP)
        values = [f.figure[1] for f in w._detail.hit_figures if f.figure[1] != "\u2014"]    # (no mesos reported)
        assert len(values) == 6 and all(bidi.LRI in v and bidi.PDI in v for v in values)
        from PySide6.QtCore import Qt
        assert w._detail.layoutDirection() == Qt.RightToLeft
    finally:
        delete_window(qapp, w)



# ---------------------------------------------------------------- its place on the screen

def test_it_first_opens_just_under_the_toolbar(win):
    from PySide6.QtCore import QPoint, QRect
    from maplehelper.ui import gamesearch
    win.place_under(QRect(100, 60, 200, 40))
    win.open("monster_npc")
    assert win.pos() == QPoint(100, 60 + 40 + gamesearch.GAP)


def test_it_reopens_where_the_player_left_it(win, settings):
    from PySide6.QtCore import QPoint, QSize
    settings["game_search_geom"] = {"x": 90, "y": 70, "w": 280, "h": 330}
    win.open("monster_npc")
    assert win.pos() == QPoint(90, 70) and win.size() == QSize(280, 330)


def test_the_place_is_saved_once_the_move_settles(win, qapp, settings):
    win.open("monster_npc")
    win.move(90, 70)
    win.resize(280, 330)
    pump(qapp, 500)                                            # the geometry debounce
    assert settings["game_search_geom"] == {"x": 90, "y": 70, "w": 280, "h": 330}


# ---------------------------------------------------------------- the real knowledge base


@pytest.fixture(scope="module")
def real():
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


@needs_kb
def test_snail_is_found_first_with_its_level(real):
    from maplehelper.ui.gamesearch import search
    hits, total = search(real, "monster", "snail")
    assert hits[0].name == "Snail" and hits[0].lv == (1, 1) and hits[0].key == "monster/2"
    assert hits[0].sub.endswith(" EXP") and " HP · " in hits[0].sub        # its muted line: HP and EXP
    assert {"Blue Snail", "Red Snail"} <= {h.name for h in hits} and total >= 3


@needs_kb
def test_where_snail_lives_is_every_map_most_spawns_first(real):
    from maplehelper.ui.gamesearch import monster_maps
    maps = monster_maps(real, "monster/2")
    assert maps[0] == ("map/000000040", "Snail Hunting Ground I", "Maple Road", 40)
    assert maps == sorted(maps, key=lambda m: -m[3])            # the most spawns first
    assert len({m[0] for m in maps}) == len(maps)               # each map once


@needs_kb
def test_an_npc_is_found_with_its_role_and_the_map_it_stands_on(real):
    from maplehelper.ui.gamesearch import search
    hits, _ = search(real, "npc", "roger")
    assert hits[0].name == "Roger" and hits[0].key == "npc/3"
    assert hits[0].sub == "Quest Giver · Mushroom Town"


@needs_kb
def test_an_item_is_found_with_its_type(real):
    from maplehelper.ui.gamesearch import search
    hits, _ = search(real, "item", "red potion")
    assert hits[0].name == "Red Potion" and hits[0].sub == "Use / Potion"


@needs_kb
def test_the_real_maps_list_opens_at_fifty(real):
    from maplehelper.ui.gamesearch import search
    hits, total = search(real, "map", "")
    assert len(hits) == 50 and total > 200 and all(h.key.startswith("map/") and h.kind == "map" for h in hits)
    hits, _ = search(real, "map", "henesys hunting")
    assert hits and all("henesys hunting" in h.name.lower() for h in hits)
