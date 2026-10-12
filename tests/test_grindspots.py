"""The Grind spots window over the game (ui/grindspots.py): the spots combat.spots ranks for the character's level and
stats, the best lit and the most mesos marked; Your stats typed in the window saved to the character and the spots
ranked again by them; the cards' links (the way to the map, the monster's Hit & damage) and Read from screen asking
the rest of the app through NAV with the KB's keys; open_with opening the stat boxes; the add-a-character card."""
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from maplehelper import combat
from maplehelper.i18n import I18n

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
STATS = {"acc": 96, "dmg_min": 182, "dmg_max": 431}     # an Assassin at 32, as the Stat window says it
EN = I18n("en")


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def real_kb():
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


@pytest.fixture(autouse=True)
def _dark_look():
    """Every test starts and ends on today's dark glass, whatever look a test picked (npcoverlay's module state)."""
    from maplehelper.ui import npcoverlay
    npcoverlay.apply_look(None)
    yield
    npcoverlay.apply_look(None)


@pytest.fixture
def make(qapp, isolated_store):
    """make(kb, profiles, lang): the window shown (its setting on), torn down after."""
    made = []

    def build(kb, profiles, lang="en"):
        from maplehelper.ui.grindspots import GrindSpots
        settings = isolated_store.Settings()
        settings["grind_spots"] = True
        w = GrindSpots(kb, settings, profiles, I18n(lang))
        made.append(w)
        w.refresh()
        qapp.processEvents()
        return w
    yield build
    for w in made:
        w._saving.stop()
        w._geom.stop()
        w.hide()
        w.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def assassin(isolated_store):
    """Profiles with one Assassin at 32, the active one; its stats as the test sets them."""
    p = isolated_store.Profiles()
    p.add("Kiwi", "Thief", "Assassin", 32)
    return p


@pytest.fixture
def signals():
    """What the window asked of the app through NAV: (signal name, its argument) in order."""
    from maplehelper.ui.toolwindow import NAV
    got = []
    wired = [(NAV.map_requested, lambda k: got.append(("map", k))),
             (NAV.monster_requested, lambda k: got.append(("monster", k))),
             (NAV.read_screen_requested, lambda: got.append(("read", None))),
             (NAV.stats_changed, lambda: got.append(("stats", None))),
             (NAV.add_character_requested, lambda: got.append(("add", None)))]
    for sig, slot in wired:
        sig.connect(slot)
    yield got
    for sig, slot in wired:
        sig.disconnect(slot)


def plain(text: str) -> str:
    """A label's text as read: no direction marks around its English blocks, no-break spaces as plain ones."""
    for mark in ("\u200f", "\u200e", "\u2066", "\u2067", "\u2068", "\u2069", "\u202a", "\u202c", "\u2060"):
        text = text.replace(mark, "")
    return text.replace("\u00a0", " ")


def cards(w) -> list[QFrame]:
    """The spot cards the window shows now, top to bottom (not the ones a refill let go)."""
    items = (w.body.itemAt(i).widget() for i in range(w.body.count()))
    return [c for c in items if isinstance(c, QFrame) and c.objectName() == "Card"]


def title(card) -> str:
    return plain(card.findChild(QLabel, "CardTitle").text())


def chips(card) -> list[str]:
    return [plain(lb.text()) for lb in card.findChildren(QLabel) if lb.objectName().startswith("Chip")]


def links(card) -> dict[str, QPushButton]:
    return {plain(b.text()).replace("&&", "&"): b for b in card.findChildren(QPushButton, "Link")}


# ---------------------------------------------------------------- the spots

@needs_kb
def test_the_spots_are_combat_spots_for_the_level_and_stats_the_best_lit(make, real_kb, assassin):
    assassin.active.stats = dict(STATS)
    w = make(real_kb, assassin)
    rows = combat.spots(real_kb, 32, 96, (182, 431), False, n=6)
    shown = cards(w)
    assert rows and [title(c) for c in shown] == [f"{s.monster.name} · Lv. {s.monster.level}" for s in rows]
    assert [bool(c.property("lit")) for c in shown] == [True] + [False] * (len(rows) - 1)
    for card, s in zip(shown, rows):
        said = chips(card)
        assert EN("spot_hit", pct=round(s.hit * 100)) in said                  # the ACC typed: the hit chance
        assert EN("spot_hits", n=s.hits) in said                              # the damage typed: hits to kill
    # the stats fold to one line once typed
    assert not w._stats_edit.isVisibleTo(w)
    assert plain(w._stats_line.text()) == "ACC 96 · Damage 182–431"
    assert not w._need.isVisibleTo(w)


@needs_kb
def test_without_stats_the_boxes_are_open_and_say_what_to_do(make, real_kb, assassin):
    w = make(real_kb, assassin)
    assert w._stats_edit.isVisibleTo(w) and w._read.isVisibleTo(w)
    assert w._need.isVisibleTo(w) and plain(w._need.text()) == EN("gs_need_stats")
    rows = combat.spots(real_kb, 32, n=6)                     # ranked by EXP per HP: no hit chance, no hit counts
    shown = cards(w)
    assert [title(c) for c in shown] == [f"{s.monster.name} · Lv. {s.monster.level}" for s in rows]
    assert not any(c.endswith("% hit") or "basic hit" in c for card in shown for c in chips(card))


@needs_kb
def test_a_magicians_damage_is_never_asked_for(make, real_kb, isolated_store):
    """The Stat window's damage is a staff swing for a Magician: the ACC alone ranks, and no hit counts show."""
    p = isolated_store.Profiles()
    p.add("Wiz", "Magician", "Cleric", 32).stats = {"acc": 70}
    w = make(real_kb, p)
    assert not w._need.isVisibleTo(w)
    assert cards(w) and not any("basic hit" in c for card in cards(w) for c in chips(card))


@needs_kb
def test_the_spot_with_the_most_mesos_per_swing_is_marked(make, real_kb, assassin, monkeypatch):
    rows = combat.spots(real_kb, 32, n=6)
    second = rows[1].monster.key
    monkeypatch.setattr(real_kb, "mesos_per_kill", lambda key: 500.0 if key == second else 10.0)
    w = make(real_kb, assassin)
    marked = [i for i, card in enumerate(cards(w)) if EN("spot_most_mesos") in chips(card)]
    assert marked == [1]                                      # marked, never moved: the ranking stays by EXP
    monkeypatch.setattr(real_kb, "mesos_per_kill", lambda key: 500.0 if key == second else None)
    w._refill()
    assert not any(EN("spot_most_mesos") in chips(card) for card in cards(w))   # one report: nothing to compare


# ---------------------------------------------------------------- your stats

@needs_kb
def test_typed_stats_are_saved_to_the_character_and_rank_the_spots(make, real_kb, assassin, signals, isolated_store):
    w = make(real_kb, assassin)
    for key, value in STATS.items():
        QTest.keyClicks(w._boxes[key], str(value))
    assert w._saving.isActive()                               # saved once the typing pauses...
    w._stats_btn.click()                                      # ... or at once on Done
    assert assassin.active.stats == STATS
    assert isolated_store.Profiles().active.stats == STATS    # on disk too
    assert ("stats", None) in signals                         # the monster page's Hit & damage follows
    assert not w._stats_edit.isVisibleTo(w)                   # folded to its line
    rows = combat.spots(real_kb, 32, 96, (182, 431), False, n=6)
    assert [title(c) for c in cards(w)] == [f"{s.monster.name} · Lv. {s.monster.level}" for s in rows]
    assert EN("spot_hits", n=rows[0].hits) in chips(cards(w)[0])
    # a box emptied: that stat is no longer said (the others, and what the screen read, stay)
    assassin.active.stats = {**STATS, "hp": 900}
    w.open_with("")
    w._boxes["acc"].selectAll()
    QTest.keyClick(w._boxes["acc"], Qt.Key_Backspace)
    w._saving.stop()
    w._stats_saved()
    assert assassin.active.stats == {"dmg_min": 182, "dmg_max": 431, "hp": 900}
    assert not any(c.endswith("% hit") for card in cards(w) for c in chips(card))


@needs_kb
def test_open_with_opens_the_stat_boxes_and_read_from_screen_asks_the_chat(make, real_kb, assassin, signals):
    assassin.active.stats = dict(STATS)
    w = make(real_kb, assassin)
    assert not w._stats_edit.isVisibleTo(w)
    w.open_with("")                                           # the monster page's "Type your stats"
    assert w._stats_edit.isVisibleTo(w) and plain(w._boxes["dmg_max"].text()) == "431"
    w._read.click()
    assert signals == [("read", None)]


# ---------------------------------------------------------------- the links

@needs_kb
def test_a_cards_links_ask_for_the_map_and_the_monster_by_their_kb_keys(make, real_kb, assassin, signals):
    assassin.active.stats = dict(STATS)
    w = make(real_kb, assassin)
    s = combat.spots(real_kb, 32, 96, (182, 431), False, n=6)[0]
    acts = links(cards(w)[0])
    assert list(acts) == [EN("gw_show_way"), EN("tool_calc")]          # no grind tracker any more
    acts[EN("gw_show_way")].click()
    acts[EN("tool_calc")].click()
    (kind, map_key), monster = signals[0], signals[1]
    assert kind == "map" and real_kb.get(map_key)["category"] == "map"
    assert s.map.startswith(real_kb.get(map_key)["name"])                # the spot's own map, its street after
    assert monster == ("monster", s.monster.key) and s.monster.key.startswith("monster/")


@needs_kb
def test_every_spots_map_has_its_kb_key(real_kb):
    for level in (10, 20, 32, 45):
        for s in combat.spots(real_kb, level, n=6):
            key = combat.map_key(real_kb, s.map)
            assert key and s.map.startswith(real_kb.get(key)["name"]), (level, s.map)
    assert combat.map_key(real_kb, "") is None and combat.map_key(real_kb, "No Such Map Anywhere") is None


# ---------------------------------------------------------------- no character

def test_without_a_character_one_card_adds_one(make, kb, isolated_store, signals):
    w = make(kb, isolated_store.Profiles())
    assert w._no_char.isVisibleTo(w) and not w._page.isVisibleTo(w) and not w._top_box.isVisibleTo(w)
    w._no_char.button.click()
    assert signals == [("add", None)]
    w.open_with("")                                           # nothing to open without one
    assert not w._top_box.isVisibleTo(w)


@needs_kb
def test_hebrew_is_mirrored_with_the_english_names_whole(make, real_kb, assassin):
    assassin.active.stats = dict(STATS)
    w = make(real_kb, assassin, "he")
    s = combat.spots(real_kb, 32, 96, (182, 431), False, n=6)[0]
    assert w.layoutDirection() == Qt.RightToLeft
    first = cards(w)[0]
    assert s.monster.name in title(first) and "רמה" in title(first) and "Lv" not in title(first)
    assert "\u2066" in first.findChild(QLabel, "CardTitle").text()       # the name one left-to-right block
