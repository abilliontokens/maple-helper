"""Tools > Farm (ui/farmtool.py): an item opened by name (exact, letter case, hyphens and spaces aside, else the
shortest item monsters drop that holds it) shows every monster that drops it; the search narrows to the items whose
name has the typed words; the tracked items are one-click picks; the links ask the app (toolwindow.NAV) for the KB's
own keys; the drop rates are the player's own pickups per active hour from the loot database; the monsters worth
farming list the character's level band; Hebrew mirrored."""
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from maplehelper import farm, grindlive, lootdb, tables, wishlist
from maplehelper.i18n import I18n
from maplehelper.lootlog import Event

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
LEVEL = 22


@pytest.fixture(scope="module")
def real_kb():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(isolated_store):
    s = isolated_store.Settings()
    s["farm_tool"] = True
    return s


@pytest.fixture
def profiles(isolated_store):
    p = isolated_store.Profiles()
    p.add("Kiwi", "Bowman", "Hunter", LEVEL)
    return p


@pytest.fixture
def make(qapp, real_kb, settings, profiles):
    """make(lang): the window over the game, shown, torn down after."""
    made = []

    def build(lang="en"):
        from maplehelper.ui.farmtool import FarmTool
        w = FarmTool(real_kb, settings, profiles, I18n(lang))
        made.append(w)
        w.refresh()
        return w
    yield build
    for w in made:
        w._searching.stop()
        w._geom.stop()
        w.hide()
        w.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def nav():
    """What the window asked the app for: (signal, key) in order."""
    from maplehelper.ui.toolwindow import NAV
    got = []
    slots = {name: (lambda key, n=name: got.append((n, key)))
             for name in ("map_requested", "monster_requested", "item_requested")}
    for name, slot in slots.items():
        getattr(NAV, name).connect(slot)
    yield got
    for name, slot in slots.items():
        getattr(NAV, name).disconnect(slot)


def shown(w, kind, name):
    """The window's widgets of a kind and style name that show: a card added to a shown window shows once the events
    run; a rebuilt card's old ones are hidden."""
    QApplication.processEvents()
    return [x for x in w.findChildren(kind, name) if x.isVisibleTo(w)]


def texts(widget, kind=QLabel, name=None) -> list[str]:
    QApplication.processEvents()
    return [x.text() for x in (widget.findChildren(kind, name) if name else widget.findChildren(kind))
            if x.isVisibleTo(widget)]


def dropper_cards(w) -> list[QFrame]:
    """The picked item's droppers: the cards with a Monster info link and no drops of their own (a monster worth
    farming lists its drops)."""
    return [c for c in shown(w, QFrame, "Card")
            if any(b.text() == "Monster info" for b in c.findChildren(QPushButton, "Link"))
            and not c.findChildren(QFrame, "Drop")]


def item(kb, name: str) -> str:
    key = farm.item_named(kb, name)
    assert key in kb.droppers, name
    return key


# ---------------------------------------------------------------- open_with, the droppers

@needs_kb
def test_open_with_picks_the_item_and_lists_its_droppers(make, real_kb, settings, profiles):
    cap = item(real_kb, "Green Mushroom Cap")
    w = make()
    w.open_with("green mushroom cap")                     # the wishlist's "Where to get it": its name, any case
    assert w.picked() == cap and settings["farm_target"] == {profiles.active.id: cap}
    assert w._box.text() == "Green Mushroom Cap" and not w._results_box.isVisible()
    titles = [c.findChildren(QLabel, "CardTitle")[0].text() for c in dropper_cards(w)]
    assert len(titles) == len(farm.droppers(real_kb, cap, LEVEL)) == len(real_kb.droppers[cap])
    for m in real_kb.droppers[cap]:
        assert any(real_kb.get(m)["name"] in t for t in titles)
    # hyphens and repeated spaces are one space; a part of a name is the shortest item monsters drop that holds it
    w.open_with("Green-Mushroom   CAP")
    assert w.picked() == cap
    w.open_with("mushroom cap")
    names = sorted((real_kb.get(k)["name"] for k in farm.farmable(real_kb)
                    if "mushroom cap" in real_kb.get(k)["name"].lower()), key=lambda n: (len(n), n))
    assert real_kb.get(w.picked())["name"] == names[0]


@needs_kb
def test_a_name_no_monster_drops_says_so_and_keeps_the_pick(make, real_kb):
    cap = item(real_kb, "Green Mushroom Cap")
    w = make()
    w.open_with("Green Mushroom Cap")
    w.open_with("zzz no such item")
    assert w.picked() == cap                               # nothing found: what was picked stays
    assert w._results_box.isVisible() and any("zzz no such item" in t for t in texts(w._results_box))


@needs_kb
def test_no_pick_and_the_box_emptied_put_the_item_down(make, real_kb, settings, profiles):
    w = make()
    assert w.picked() is None and shown(w, QFrame, "Empty")      # nothing picked: what to do
    w.open_with("Green Mushroom Cap")
    w._box.clear()
    w._box.textEdited.emit("")                                    # its ✕
    assert w.picked() is None and settings["farm_target"] == {}
    assert not dropper_cards(w)


# ---------------------------------------------------------------- the search

@needs_kb
def test_search_narrows_to_the_items_with_every_word(make, real_kb):
    w = make()
    farmable = {real_kb.get(k)["name"].lower() for k in farm.farmable(real_kb)}
    mush = w.search("mush")
    assert mush and all("mush" in real_kb.get(k)["name"].lower() for k in mush)
    assert len(mush) == sum("mush" in n for n in farmable)
    green = w.search("cap green")                                  # every word, in any order
    assert green and set(green) < set(w.search("cap"))
    assert all("green" in real_kb.get(k)["name"].lower() and "cap" in real_kb.get(k)["name"].lower() for k in green)
    assert w.search("green mushroom cap")[0] == item(real_kb, "Green Mushroom Cap")    # the exact name first
    assert w.search("") == [] and w.search("zzzz") == []


@needs_kb
def test_typing_lists_rows_and_a_row_or_enter_picks(make, real_kb):
    from maplehelper.ui.farmtool import PICK_ROWS
    w = make()
    QTest.keyClicks(w._box, "ma")
    w._fill_results()                                              # the typing pause, now
    rows = shown(w, QFrame, "Row")
    hits = w.search("ma")
    assert len(hits) > PICK_ROWS and len(rows) == PICK_ROWS and w._results_box.isVisible()
    assert [r.findChildren(QLabel, "Name")[0].text() for r in rows] == [real_kb.get(k)["name"] for k in hits[:PICK_ROWS]]
    assert any(str(len(hits) - PICK_ROWS) in t for t in texts(w._results_box, QLabel, "Note"))     # and N more
    rows[1].clicked.emit()
    assert w.picked() == hits[1] and not w._results_box.isVisible()
    assert w._box.text() == real_kb.get(hits[1])["name"]
    w._box.setText("green mushroom c")
    w._enter()                                                     # Enter: the first row
    assert w.picked() == w.search("green mushroom c")[0] == item(real_kb, "Green Mushroom Cap")


@needs_kb
def test_tracked_items_monsters_drop_are_one_click_picks(make, real_kb, settings, profiles):
    cap, ore = item(real_kb, "Green Mushroom Cap"), item(real_kb, "Bronze Ore")
    bought = next(k for k, e in real_kb.entities.items()           # an item no monster drops (a shop's, a quest's)
                  if k.startswith("item/") and k not in real_kb.droppers and e.get("name"))
    for k in (cap, bought, ore):
        wishlist.toggle(settings, profiles.active.id, k)
    w = make()
    chips = shown(w, QPushButton, "Wish")
    assert [b.text() for b in chips] == ["Green Mushroom Cap", "Bronze Ore"]      # only what monsters drop
    chips[1].click()
    assert w.picked() == ore
    assert [b.isChecked() for b in shown(w, QPushButton, "Wish")] == [False, True]


# ---------------------------------------------------------------- links

@needs_kb
def test_links_ask_the_app_for_the_kb_keys(make, real_kb, nav):
    cap = item(real_kb, "Green Mushroom Cap")
    w = make()
    w.open_with("Green Mushroom Cap")
    prices = [b for b in shown(w, QPushButton, "Link") if b.text() == "Prices"]
    prices[0].click()
    card = dropper_cards(w)[0]
    links = {b.text(): b for b in card.findChildren(QPushButton, "Link")}
    links["Monster info"].click()
    links["Show the way"].click()
    assert nav[0] == ("item_requested", cap)
    assert nav[1][0] == "monster_requested" and nav[1][1] in real_kb.droppers[cap]
    assert nav[2][0] == "map_requested" and nav[2][1].startswith("map/") and len(nav[2][1]) > 4


@needs_kb
def test_worth_farming_lists_the_level_band_and_a_drop_picks_it(make, real_kb, settings, profiles):
    c = profiles.active
    w = make()
    wanted = farm.needs(real_kb, c.level, c.base_class, c.job, c.quests_done, None, wishlist.items(settings, c.id))
    rows = farm.targets(real_kb, c.level, n=6, wanted=wanted)
    cards = [x for x in shown(w, QFrame, "Card") if x.findChildren(QFrame, "Drop")]
    assert rows and len(cards) == len(rows)
    for r, card in zip(rows, cards):
        assert r.name in card.findChildren(QLabel, "CardTitle")[0].text()
    drop = rows[0].drops[0]
    next(x for x in cards[0].findChildren(QFrame, "Drop") if x.isVisibleTo(w)).clicked.emit()
    assert w.picked() == drop.key


# ---------------------------------------------------------------- your drop rates

def _seed_run(kb, cid: str) -> str:
    """15 minutes on a map with Green Mushrooms: 9 Green Mushroom Caps and 2 Leathers picked up there."""
    maps: dict[str, set[str]] = {}
    for r in tables.rows(kb, "spawns"):
        maps.setdefault(r["map_key"].removeprefix("map/"), set()).add(r["monster"])
    mid = next(m for m in sorted(maps) if "Green Mushroom" in maps[m])
    cap, leather = item(kb, "Green Mushroom Cap"), item(kb, "Leather")
    n = 15 * 12                                           # an EXP line every 5 s
    evs = [Event(i * 5.0, "exp", 20, map=mid) for i in range(n)]
    evs += [Event(10.0 + i * 60, "item", 1, "Green Mushroom Cap", cap, map=mid) for i in range(9)]
    evs += [Event(15.0 + i * 120, "item", 1, "Leather", leather, map=mid) for i in range(2)]
    lid = lootdb.open_log(cid, "Kiwi", 0.0)
    lootdb.add_events(lid, evs, kb)
    lootdb.end_log(lid, n * 5.0)
    return mid


@needs_kb
def test_drop_rates_are_the_players_pickups_from_the_loot_database(make, real_kb, profiles):
    from maplehelper.ui.grindbar import per_hour
    cid = profiles.active.id
    w = make()
    assert not shown(w, QFrame, "Line") and shown(w, QFrame, "Empty")    # no runs yet: how the rates come
    _seed_run(real_kb, cid)
    rates = {r.item_key: r for r in grindlive.drop_rates(real_kb, cid)}
    cap, leather = item(real_kb, "Green Mushroom Cap"), item(real_kb, "Leather")
    assert rates[cap].per_h == pytest.approx(36.0)
    # none picked: every item's rate, the most picked up first; a click picks the item
    w._fill()
    lines = shown(w, QFrame, "Line")
    assert [x.findChildren(QLabel, "Name")[0].text() for x in lines] == ["Green Mushroom Cap", "Leather"]
    assert per_hour(rates[cap].per_h) in shown(w, QLabel, "Rate")[0].text()
    lines[1].clicked.emit()
    assert w.picked() == leather
    # one picked: its own rate alone
    w.open_with("Green Mushroom Cap")
    lines = shown(w, QFrame, "Line")
    assert len(lines) == 1 and lines[0].findChildren(QLabel, "Name")[0].text() == "Green Mushroom Cap"
    assert texts(lines[0], QLabel, "Rate") == [f"{per_hour(36.0)} per hour"]
    # an item never picked up: no rate, a line saying how one comes
    w.open_with("Orange Mushroom Cap")
    assert not shown(w, QFrame, "Line")
    assert any("Orange Mushroom Cap" in t for t in texts(w, QLabel, "Hint"))


# ---------------------------------------------------------------- Hebrew

@needs_kb
def test_hebrew_is_mirrored_and_the_language_switches_in_place(make, real_kb):
    w = make("en")
    w.open_with("Green Mushroom Cap")
    w.apply_language(I18n("he"))
    assert w.layoutDirection() == Qt.RightToLeft and w.picked() == item(real_kb, "Green Mushroom Cap")
    assert any("מי מפיל אותו" in t for t in texts(w, QLabel, "Caption"))
    # every monster's link in Hebrew now: the picked item's droppers' and each monster worth farming's
    targets = [c for c in shown(w, QFrame, "Card") if c.findChildren(QFrame, "Drop")]
    links = [b for b in shown(w, QPushButton, "Link") if "פרטי המפלצת" in b.text()]
    assert targets and len(links) == len(real_kb.droppers[w.picked()]) + len(targets)
