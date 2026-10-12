"""UX fixes in the chips, the guides, the patch notes and the wishlist (TOOL-xx, PERF-04/05)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def real_kb():
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


def test_a_picked_chip_has_room_for_its_bold_text(app):
    """TOOL-02: a picked "All levels" was sized for its regular text and drew "ll levels"."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QPushButton, QWidget

    from maplehelper.ui import theme
    from maplehelper.ui.controls import FlowLayout
    w = QWidget()
    w.setStyleSheet(theme.stylesheet(theme.load_fonts(), 14))
    flow = FlowLayout(w)
    b = QPushButton("All levels", objectName="Chip")
    b.setCheckable(True)
    b.setChecked(True)
    flow.addWidget(b)
    w.resize(400, 80)
    w.show()
    app.processEvents()
    bold = b.font()
    bold.setBold(True)
    assert b.width() >= QFontMetrics(bold).horizontalAdvance("All levels") + 26      # its 13 px padding each side
    w.close()


def test_guide_search_lights_no_category_and_counts(app):
    """TOOL-11: the search looks in every guide while "For you" stayed lit."""
    from types import SimpleNamespace

    from maplehelper.ui.guides import GuidesDialog
    kb = SimpleNamespace(entities={}, page=lambda k: "", get=lambda k: None, picture=lambda k: None)
    d = GuidesDialog(kb, None, "en", "")
    d.all = [{"key": f"guide/g{i}", "title": f"Henesys {i}", "category": "general", "minutes": None} for i in range(3)]
    d._texts = {g["key"]: "" for g in d.all}
    d.search.setText("henesys")
    assert d.cats.checkedButton() is None
    shown = [d.rows.itemAt(i).widget() for i in range(d.rows.count())]
    assert shown[0].text() == "3 guides from every category"
    d.search.clear()
    assert d.cats.checkedButton() is d.cats.buttons()[0]
    d.search.setText("henesys")
    d.cats.buttons()[2].click()                  # a category chip: browse it, the search emptied
    assert d.search.text() == "" and d.cats.checkedButton() is d.cats.buttons()[2]
    d.close()


def test_patch_note_item_lists_keep_names_whole_and_cut_long_lists():
    """TOOL-04."""
    from maplehelper import bidi, recent
    from maplehelper.i18n import NBSP, I18n
    names = [f"Earring STR Scroll {i}" for i in range(12)]
    he = recent._items(I18n("he"), names)
    assert f"{bidi.LRI}Earring{NBSP}STR{NBSP}Scroll{NBSP}0{bidi.PDI}" in he and he.endswith("ועוד 4")
    assert recent._items(I18n("en"), names[:2]) == "Earring STR Scroll 0, Earring STR Scroll 1"
    assert "One-\u2060Handed" in recent._items(I18n("he"), ["Scroll for One-Handed Sword"])


@needs_kb
def test_patch_notes_show_fast_and_the_rest_on_demand(app, real_kb):
    """PERF-04 / TOOL-21: every card at once held the window blank for 1.3-1.8 s; "and N more" was a dead end."""
    from PySide6.QtWidgets import QPushButton

    from maplehelper.ui import patchnotes
    from maplehelper.ui.widgets import EntityCard
    monsters = [k for k, e in real_kb.entities.items() if e.get("category") == "monster"][:30]
    entry = {"version": "2026.10.04.0100", "date": "2026-10-04", "counts": {"added": 30},
             "added": [{"key": k, "name": real_kb.get(k)["name"], "category": "monster"} for k in monsters]}
    d = patchnotes.PatchNotesDialog([entry], "en", "", real_kb)
    cards = lambda: d.findChildren(EntityCard)       # noqa: E731
    assert len(cards()) == patchnotes.FIRST_CARDS                 # the rest after the window is up
    for _ in range(50):
        app.processEvents()
    assert len(cards()) == patchnotes.SHOWN
    assert all(c._lazy is None for c in cards())                  # the pictures followed
    more = next(b for b in d.findChildren(QPushButton) if b.text() == "Show more")
    more.click()
    for _ in range(50):
        app.processEvents()
    assert len(cards()) == 30 and more.isHidden()
    d.close()


@needs_kb
def test_farm_needs_leave_out_professions_not_taken(real_kb):
    """TOOL-05: Garnet Ore "for a quest" of a profession the player never took."""
    from maplehelper import farm, quests
    crafting_quests = {q.name for k, e in real_kb.entities.items() if e.get("category") == "quest"
                       for q in [quests.quest(real_kb, k)] if q and q.area == "Crafting"}
    none = farm.needs(real_kb, 35, "Thief", "Assassin", [], None, [])
    assert not [v for v in none.values() if v[0] == "quest" and v[1] in crafting_quests]
    smith = farm.needs(real_kb, 35, "Thief", "Assassin", [], {"smithing": 5}, [])
    assert any(v[0] == "quest" and v[1] in crafting_quests for v in smith.values())


@needs_kb
def test_item_pages_are_read_once_per_kb(real_kb, monkeypatch):
    """PERF-05: the item list and the Farm tab read ~2,000 pages on every open."""
    from maplehelper import market, sitedata
    from maplehelper.kb import KnowledgeBase
    from maplehelper.ui.wishlist import item_rows
    key = real_kb._item_by_name["red potion"]
    first = market.npc_prices(real_kb, key)
    sitedata.untradeable(real_kb, key)
    item_rows(real_kb)
    reads = []
    monkeypatch.setattr(KnowledgeBase, "page", lambda self, k: reads.append(k) or "")
    assert market.npc_prices(real_kb, key) is first
    sitedata.untradeable(real_kb, key)
    item_rows(real_kb)
    assert reads == []


@needs_kb
def test_wishlist_droppers_say_their_level_in_hebrew_and_lead_to_the_tools(app, real_kb):
    """TOOL-07: "Snail • Lv. 1" in Hebrew, and "Ask in chat" the only way on."""
    from PySide6.QtWidgets import QLabel, QPushButton

    from maplehelper.ui.wishlist import WishlistDialog
    key = real_kb._item_by_name["garnet ore"]
    d = WishlistDialog([key], real_kb, "he", "", 35)
    names = [lb.text() for lb in d.findChildren(QLabel) if lb.objectName() == "CardName"]
    assert any("רמה" in n for n in names) and not any("Lv." in n for n in names)
    asked = []
    d.farm_requested.connect(asked.append)
    d.route_requested.connect(asked.append)
    links = {b.text().strip("‏"): b for b in d.findChildren(QPushButton) if b.objectName() == "Link"}
    next(b for t, b in links.items() if "פארם" in t).click()
    next(b for t, b in links.items() if "איך מגיעים" in t).click()
    assert asked[0] == "Garnet Ore" and len(asked) == 2
    d.close()
