"""The crafting window's Professions tab (ui/craftadvisor.py): a switch of the six professions, the picked one's level
saved to the character (Character.crafts) and its Mastery bar % (craft_pct), the EXP to its next level and what that
level opens, its recipes (what the level allows, every one, one level; searched by a recipe's or an ingredient's
name), each ingredient's item page a click away, its teacher and quests. The behaviour on test_craftplan.py's tiny KB
(the Mithril Wand's chain); the teacher, the quests and NiaMeowDB's numbers on the real KB. Ported from the Play tools'
crafting page tests (test_tools_audit TL1-6, test_look_ux TL2-16, test_farm's quest jump)."""

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from test_craftplan import WAND, _delete_window, _pump, _texts, make_kb

from maplehelper import crafting, craftplan, tables
from maplehelper.kb import KnowledgeBase

ROOT = Path(__file__).resolve().parent.parent
REAL_KB = ROOT / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
_MARKS = dict.fromkeys(map(ord, "\u2066\u2067\u2069\u200e\u200f\u202a\u202c\u2060"))


@pytest.fixture(scope="module")
def _tiny_kb(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("craftadvisor") / "kb"
    make_kb(root)
    assert tables.ensure(kb=KnowledgeBase(root), wait=30)
    return root


@pytest.fixture
def kb(_tiny_kb) -> KnowledgeBase:
    return KnowledgeBase(_tiny_kb)


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def default_look():
    """Every test ends on today's dark glass (apply_look is module state every window over the game reads)."""
    yield
    from maplehelper.ui import npcoverlay

    npcoverlay.apply_look(None)


@pytest.fixture
def settings(isolated_store):
    return isolated_store.Settings()


@pytest.fixture
def profiles(isolated_store):
    """The Mithril Wand's sample character: a level-30 Wizard, Arcforge 4 at 40%."""
    p = isolated_store.Profiles()
    p.add("Wiz", "Magician", "Wizard", 30)
    c = p.active
    c.crafts, c.craft_pct, c.craft_targets = {"arcforge": 4}, {"arcforge": 40}, [WAND]
    p.save()
    return p


def _open(qapp, kb, settings, profiles, lang: str = "en"):
    """The window shown on its Professions tab."""
    from maplehelper.i18n import I18n
    from maplehelper.ui.craftadvisor import CraftAdvisor

    w = CraftAdvisor(kb, settings, profiles, I18n(lang))
    settings["craft_advisor"] = True
    w.refresh()
    w._tabs.group.buttons()[2].click()
    _pump(qapp)
    return w


@pytest.fixture
def win(qapp, kb, settings, profiles):
    w = _open(qapp, kb, settings, profiles)
    yield w
    _delete_window(qapp, w)


@pytest.fixture
def nav():
    """What the window asked the app for, in order: (signal, its arguments...)."""
    from maplehelper.ui.toolwindow import NAV

    got = []
    names = ("map_requested", "monster_requested", "npc_requested", "item_requested", "tool_requested", "ask_requested")
    slots = {name: (lambda *args, n=name: got.append((n, *args))) for name in names}
    for name, slot in slots.items():
        getattr(NAV, name).connect(slot)
    yield got
    for name, slot in slots.items():
        getattr(NAV, name).disconnect(slot)


def _plain(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).translate(_MARKS).replace("\xa0", " ")


def _cards(w) -> list:
    """The recipe cards that show, top to bottom."""
    out = []
    for i in range(w._rec_lay.count()):
        card = w._rec_lay.itemAt(i).widget()
        if card is not None and card.objectName() == "Card":
            out.append(card)
    return out


def _name(card) -> str:
    from PySide6.QtWidgets import QLabel

    return re.sub(r"\s*\(makes \d+\)$", "", _plain(card.findChild(QLabel, "CardTitle").text()))


def _recipes(w) -> list[str]:
    """The recipe cards' products, top to bottom (what one craft makes left out)."""
    return [_name(c) for c in _cards(w)]


def _buttons(w, parent, name: str) -> dict:
    from PySide6.QtWidgets import QPushButton

    return {_plain(b.text()): b for b in parent.findChildren(QPushButton, name) if b.isVisibleTo(w)}


def _click(widget) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.mouseClick(widget, Qt.LeftButton)


# ---------------------------------------------------------------- the switch and the level


def test_the_switch_shows_one_profession_and_its_stepper_saves_its_level(qapp, win, profiles, isolated_store):
    """The tab opens on the profession the character is highest in (Arcforge 4, its recipes newest level first); a tile
    picks another, its card and recipes follow; the stepper saves the level to the character (on disk too), the recipes
    the level allows follow it and the tile says the new level."""
    assert win._prof == "arcforge" and win._tiles["arcforge"].isChecked()
    assert "Lv. 4 · 40%" in _texts(win._tiles["arcforge"])
    assert _recipes(win) == ["Metal Wand", "Processed Parchment", "Aquamarine"]
    win._tiles["smithing"].click()
    _pump(qapp)
    assert win._tiles["smithing"].isChecked() and not win._tiles["arcforge"].isChecked()
    assert "Smithing" in _texts(win._prof_card) and win._step.value() == 1  # never learned: level 1, as the plan counts
    assert _recipes(win) == ["Bronze Ingot", "Iron Ingot"]  # Smithing 1's (the Mithril Ingot asks for 2)
    win._step._plus.click()
    _pump(qapp)
    assert profiles.active.crafts == {"arcforge": 4, "smithing": 2}
    assert isolated_store.Profiles().active.crafts == {"arcforge": 4, "smithing": 2}  # saved, not only shown
    assert _recipes(win) == ["Mithril Ingot", "Bronze Ingot", "Iron Ingot"]
    assert "Lv. 2" in _texts(win._tiles["smithing"])


def test_a_bar_percent_still_being_typed_is_saved_to_its_own_profession(qapp, win, profiles):
    """The bar % box is the picked profession's: typed, then another tile picked before the pause is over, it is
    saved to the one it was typed for, and the box shows the new profession's."""
    win._pct_box.setText("75")
    assert win._edit.isActive()
    win._tiles["tailoring"].click()
    _pump(qapp)
    assert profiles.active.craft_pct == {"arcforge": 75}
    assert win._prof == "tailoring" and win._pct_box.text() == ""


def test_a_saved_level_above_the_top_shows_as_the_top(qapp, kb, settings, profiles):
    """TL1-6: a saved Smithing 50 showed "at Smithing level 50" beside a stepper at the KB's top. The stepper, its +
    and the recipes' line all stop at the top the KB's Crafting Levels page gives."""
    profiles.active.crafts = {"smithing": 50}
    profiles.save()
    w = _open(qapp, kb, settings, profiles)
    try:
        top = craftplan.top_level(kb)
        assert w._prof == "smithing" and w._step.value() == top and not w._step._plus.isEnabled()
        head = _plain(w._rec_head.text())
        assert f"level {top}" in head and "level 50" not in head
        assert "Smithing is at its top level." in _texts(w._prof_card)
    finally:
        _delete_window(qapp, w)


def test_open_with_a_profession_shows_it_on_the_professions_tab(qapp, win):
    """NAV.tool_requested("craft_advisor", <profession>): the tab on that profession; anything else changes nothing."""
    win._tabs.group.buttons()[0].click()
    win.open_with("Smithing")
    assert win._stack.currentIndex() == 2 and win._prof == "smithing" and win._tiles["smithing"].isChecked()
    win.open_with("Cooking")
    assert win._prof == "smithing"


# ---------------------------------------------------------------- the way to the next level


def test_the_card_shows_the_exp_to_the_next_level_what_it_asks_and_what_it_opens(qapp, win, profiles):
    """Arcforge 4 at 40%: 123 of the 308 EXP to level 5 (the bar % of the level's own requirement, as the plan counts
    it), the character level that level asks for; the bar % and the character level typed move both; a level that
    opens recipes says how many, and its link shows them; an EXP the player measured replaces the KB's."""
    card = _texts(win._prof_card)
    assert "123 / 308 EXP · 185 more to Lv. 5" in card
    assert "Lv. 5 asks for character level 25: you have it." in card
    assert not win._next_box.isVisibleTo(win)  # Arcforge 5 opens nothing in this KB
    win._pct_box.setText("50")
    win._lv_box.setText("20")
    win._edits_saved()
    _pump(qapp)
    assert profiles.active.craft_pct["arcforge"] == 50 and profiles.active.level == 20
    card = _texts(win._prof_card)
    assert "154 / 308 EXP · 154 more to Lv. 5" in card and "25: 5 levels to go." in card
    assert win._req_line.objectName() == "Warn"
    win._step._plus.click()  # Arcforge 5: level 6 opens the Mithril Wand
    _pump(qapp)
    assert "225 / 450 EXP · 225 more to Lv. 6" in _texts(win._prof_card)
    assert "Lv. 6 unlocks 1 recipe" in _texts(win._next_box)
    win._next_link.click()
    _pump(qapp)
    assert win._scope == 6 and _recipes(win) == ["Mithril Wand"]
    assert "Not yet: you're at level 5." in _plain(win._rec_head.text()).replace("&#x27;", "'")
    win._exp_boxes[5].setText("900")
    win._edits_saved()
    assert "450 / 900 EXP · 450 more to Lv. 6 (yours)" in _texts(win._prof_card)


# ---------------------------------------------------------------- the recipes


def test_the_recipes_show_what_the_level_allows_every_one_or_one_level_and_search_by_ingredient(qapp, win):
    """What Smithing 1 allows; every recipe by the level that opens it (the next level marked); one level's (a locked
    one says so); the search finds a recipe by an ingredient's name, or says there is none."""
    win._tiles["smithing"].click()
    _pump(qapp)
    _buttons(win, win._rec_box, "Scope")["All recipes"].click()
    _pump(qapp)
    assert _recipes(win) == ["Bronze Ingot", "Iron Ingot", "Mithril Ingot"]  # the first level first
    assert "LEVEL 2 · NEXT" in _texts(win._rec_box)
    levels = _buttons(win, win._rec_box, "LvChip")
    assert list(levels) == ["1", "2"] and levels["2"].property("locked") is True
    levels["2"].click()
    _pump(qapp)
    assert _recipes(win) == ["Mithril Ingot"] and "Not yet" in _plain(win._rec_head.text())
    _buttons(win, win._rec_box, "Scope")["All recipes"].click()
    win._rec_search.setText("bronze ore")  # what an ingredient goes into
    win._fill_recipes()
    assert _recipes(win) == ["Bronze Ingot"]
    win._rec_search.setText("mithril")  # ... and a recipe by its own name
    win._fill_recipes()
    assert _recipes(win) == ["Mithril Ingot"]
    win._rec_search.setText("no such thing")
    win._fill_recipes()
    _pump(qapp)  # (a label added to a shown window shows once the events run)
    assert not _recipes(win) and "No recipe like that here." in _texts(win._rec_box)


def test_a_recipes_ingredients_say_where_they_come_from_and_open_their_item_page(qapp, win, nav):
    """The Mithril Wand's card: each ingredient with its picture and count, where it comes from (the profession that
    makes it), the optional catalyst marked; a click opens the ingredient's item page; Ask in chat asks about it."""
    win._scope_set("all")
    _pump(qapp)
    from PySide6.QtWidgets import QFrame

    wand = next(c for c in _cards(win) if _name(c) == "Mithril Wand")
    rows = [r for r in wand.findChildren(QFrame, "IngRow") if r.isVisibleTo(win)]
    texts = [_texts(r) for r in rows]
    assert any("6× Mithril Ingot" in x and "Smithing 2" in x for x in texts)
    assert any("18× Screw" in x and "Weaponcrafting 1" in x for x in texts)
    assert any("One-Handed Weapon Crafting Catalyst" in x and "optional" in x for x in texts)
    ingot = next(r for r, x in zip(rows, texts) if "Mithril Ingot" in x)
    _click(ingot)
    assert nav[-1] == ("item_requested", "item/422")
    _buttons(win, wand, "Link")["Ask in chat"].click()
    assert nav[-1][0] == "ask_requested" and "Mithril Wand" in nav[-1][1]


def test_hebrew_level_chips_keep_a_visible_gap(qapp, kb, settings, profiles):
    """TL2-16: the digit 1's ink sits against the Hebrew word: with a plain space the chip read "רמה1". Hebrew is
    mirrored, the professions' and the recipes' names stay English."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    w = _open(qapp, kb, settings, profiles, "he")
    try:
        assert w.layoutDirection() == Qt.RightToLeft
        w._scope_set("all")
        _pump(qapp)
        chips = [lb.text() for lb in w._rec_box.findChildren(QLabel) if lb.isVisibleTo(w)
                 and lb.objectName() in ("Chip", "ChipWarn") and "רמה" in lb.text()]
        one = [x for x in chips if "\u202a1\u202c" in x]  # the level-1 recipes' chips
        assert one and all("רמה\xa0\u2006" in x for x in chips), chips[:3]
        assert "Arcforge" in _texts(w._prof_card) and "Mithril Wand" in " ".join(_recipes(w))
        assert "Lv" not in _texts(w._prof_card) + _texts(w._rec_box)  # Hebrew says רמה
    finally:
        _delete_window(qapp, w)


# ---------------------------------------------------------------- the real KB: NiaMeowDB's numbers, the teacher


@pytest.fixture
def real(qapp, isolated_store):
    """The window on the real KB for a level-30 Fighter at Smithing 3."""
    p = isolated_store.Profiles()
    p.add("Kiwi", "Warrior", "Fighter", 30)
    p.active.crafts = {"smithing": 3}
    p.save()
    w = _open(qapp, KnowledgeBase(REAL_KB), isolated_store.Settings(), p)
    yield w
    _delete_window(qapp, w)


@needs_kb
def test_real_kb_recipes_name_the_best_value_and_what_a_craft_gains_or_costs(real):
    """What Smithing 3 allows, the newest level first: its best value on top, lit (NiaMeowDB's fewest mesos burned per
    EXP), every card saying what a craft gains or costs at NPC prices when NiaMeowDB has its numbers."""
    cards = _cards(real)
    assert cards and cards[0].property("lit") is True and "Best value" in _texts(cards[0])
    assert sum(1 for c in cards if c.property("lit")) == 1
    assert "Level 3" in _texts(cards[0])
    econ = crafting.economy(real._kb, "smithing")
    third = [r for r in craftplan.profession_recipes(real._kb, "smithing") if r.prof_lv == 3]
    first = next(r for r in third if r.product == _name(cards[0]))
    net = econ[(first.product.casefold(), 3, first.makes)].net
    assert (f"Gains {net:,} mesos" if net >= 0 else f"Costs {-net:,} mesos") in _texts(cards[0])
    # the best: the fewest mesos burned per EXP of the level's recipes NiaMeowDB has numbers for
    burns = [crafting.burn_per_exp(econ[k]) for r in third if (k := (r.product.casefold(), 3, r.makes)) in econ]
    assert crafting.burn_per_exp(econ[(first.product.casefold(), 3, first.makes)]) == min(burns)


@needs_kb
def test_real_kb_teacher_mode_shows_the_teacher_where_to_craft_and_the_quests(qapp, real, nav):
    """Teacher & quests: who teaches Smithing and where, where to craft, then its first and master quests — right
    here, with what they need a click from its page (a monster's, an item's) — the master quest's Smithing 5 marked
    while the character is short of it; Open in Quests opens the Quests window on it, the way to the teacher the Maps
    search (test_farm's quest jump: a profession's own quest is on the page, the rest in the Quests window)."""
    kb = real._kb
    real._prof_tabs.group.buttons()[0].click()  # Teacher & quests
    _pump(qapp)
    i = crafting.info(kb, "smithing")
    text = _texts(real._teach_box)
    for words in (i.teacher, i.teacher_town, i.station, i.start_quest, i.master_quest):
        assert words in text, words
    from PySide6.QtWidgets import QFrame, QLabel

    warn = [lb.text() for lb in real._teach_box.findChildren(QLabel, "ChipWarn") if lb.isVisibleTo(real)]
    assert any("Smithing 5" in _plain(x) for x in warn)
    links = _buttons(real, real._teach_box, "Link")
    links["Way to the teacher"].click()
    assert nav[-1][0] == "map_requested" and nav[-1][1].startswith("map/")
    links["NPC info"].click()
    assert nav[-1] == ("npc_requested", i.teacher_key)
    start = real._quest_named(i.start_quest)
    needs = [r for r in real._teach_box.findChildren(QFrame, "IngRow") if r.isVisibleTo(real)]
    mob = next(r for r in needs if "defeat" in _texts(r))
    _click(mob)
    assert nav[-1][0] == "monster_requested" and nav[-1][1].startswith("monster/")
    opens = [b for b in real._teach_box.findChildren(type(links["NPC info"]), "Link")
             if b.isVisibleTo(real) and _plain(b.text()) == "Open in Quests"]
    opens[0].click()
    assert nav[-1] == ("tool_requested", "quest_tool", start.key)
