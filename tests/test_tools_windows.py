"""The game search's lists, guides, history, wishlist and pins: the audit's tools-windows findings, one test each."""
import datetime
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from maplehelper import pins  # noqa: E402

app = QApplication.instance() or QApplication([])
REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")


def pump(ms=30):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def deleted_on_close(d):
    """Close the way app.open_window's windows close: deleted right after."""
    d.setAttribute(Qt.WA_DeleteOnClose)
    d.close()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    pump()


@pytest.fixture(scope="module")
def real_kb():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


def cards(layout):
    return [layout.itemAt(i).widget() for i in range(layout.count())
            if layout.itemAt(i).widget() is not None and layout.itemAt(i).widget().objectName() == "Card"]


# ------------------------------------------------------------------ the game search's lists

@needs_kb
def test_the_game_search_offers_only_what_the_kb_says_is_in_the_game(real_kb):
    from maplehelper import availability, combat
    from maplehelper.ui.gamesearch import _map_hits, _monster_hits, search
    o = availability.of(real_kb)
    assert o.known
    # Ossyria's maps and monsters (and Jr. Sentinel's Forgotten Hollow) stay out while the release guide keeps them
    # shut, by the guide, not by this list: the day one opens, the nightly still passes
    maps = {h.name for h in _map_hits(real_kb)}
    every = [(e["name"], o.entity_open(k)) for k, e in real_kb.entities.items() if e.get("category") == "map"]
    shut = {n for n, op in every if not op} - {n for n, op in every if op}      # (a name both ways: not shut)
    assert maps and not shut & maps                      # today: Dead Mine I, Wolf Territory I, Cloud Park I, ...
    names = {h.name for h in _monster_hits(real_kb)}
    assert "Green Mushroom" in names
    closed = {m.name for m in combat.monsters(real_kb)} - {m.name for m in combat.monsters(real_kb)
                                                            if o.monster_key_open(m.key)}
    assert not names & closed
    # typed by hand, the search doesn't find a closed one either (today Star Pixie)
    hidden = next((n for n in ("Star Pixie", "Hector", "White Fang") if n in closed), next(iter(sorted(closed)), None))
    if hidden:
        assert hidden not in {h.name for h in search(real_kb, "monster", hidden)[0]}
    assert search(real_kb, "monster", "Green Mushroom")[0][0].name == "Green Mushroom"
    assert closed or not o.not_at_launch                 # something is shut while the guide names something


# ------------------------------------------------------------------ wishlist

@needs_kb
def test_wishlist_shows_only_droppers_and_maps_in_the_game(real_kb):
    from maplehelper.ui.wishlist import WishlistDialog
    # One-Handed Axe Attack Scroll: Greater listed Tick-Tock and Crimson Balrog ("No map data"); Stiff Feather a
    # Jr. Cellion at "Garden of Red I · Orbis"
    items = ["item/2", real_kb._item_by_name["stiff feather"]]
    d = WishlistDialog(items, real_kb, "en", "")
    texts = [lb.text() for lb in d.findChildren(QLabel)]
    # by the release guide, not by name: the day Ossyria opens, its droppers and towns may show
    from maplehelper import availability, combat
    o = availability.of(real_kb)
    names = [(m.name, o.monster_key_open(m.key)) for m in combat.monsters(real_kb)]
    shut = {n for n, op in names if not op} - {n for n, op in names if op}
    assert not [x for x in texts for n in shut & {"Crimson Balrog", "Tick-Tock", "Jr. Cellion"} if n in x]
    assert not [x for x in texts for town in ("Orbis", "El Nath") if town in x and not o.place_open(town)]
    assert any("Green Mushroom" in x for x in texts)
    # under each list, which list its drops are on: the MSEA reference caveat, or players' own reports
    assert sum("reference data" in x or "Players saw these drops" in x for x in texts) == 2
    d.close()


@needs_kb
@pytest.mark.parametrize("lang", ["en", "he"])
def test_wishlist_rows_fit_the_window(real_kb, lang):
    from PySide6.QtWidgets import QScrollArea
    from maplehelper.ui.wishlist import WishlistDialog
    # the site's shot: Dark Stone Golem's row (name + Lv, Community, Single report, Updated in one row) was 570 px
    # wide in a 434 px view, so every row was cut off at the edge
    from maplehelper.ui import theme
    d = WishlistDialog(["item/298", "item/379"], real_kb, lang, theme.stylesheet(theme.load_fonts(), 14))
    d.show()
    pump(60)
    scroll = d.findChild(QScrollArea)
    assert scroll.widget().minimumSizeHint().width() <= scroll.viewport().width()
    d.close()


# ------------------------------------------------------------------ guides

GUIDES = {f"guide/{slug}": {"category": "guide", "name": name} for slug, name in (
    ("thief-class-guide", "Thief Class Guide"), ("assassin-class-guide", "Assassin Class Guide"),
    ("kerning-city-party-quest-kpq-guide", "Kerning City Party Quest (KPQ) Guide"))}


def _fake_kb():
    return SimpleNamespace(entities=GUIDES, page=lambda k: "", get=GUIDES.get, picture=lambda k: None)


def test_zoom_popup_goes_with_its_window():
    from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

    from maplehelper.ui.guides import ImageZoom
    dlg = QDialog()
    QVBoxLayout(dlg).addWidget(br := QTextBrowser())
    zoom = ImageZoom(br)
    dlg.show()
    pump()
    img = Path(os.environ["APPDATA"]) / "zoom-test.png"
    QImage(10, 10, QImage.Format_RGB32).save(str(img))
    zoom.show(str(img))
    pop = zoom.pop
    assert pop.isVisible()
    tops = lambda: [w for w in QApplication.topLevelWidgets() if w is pop]  # noqa: E731
    deleted_on_close(dlg)
    assert not tops()                    # hidden at once and deleted, not left floating over the game


def test_guide_rows_open_from_the_keyboard():
    from maplehelper.ui.guides import GuideRow, GuidesDialog
    d = GuidesDialog(_fake_kb(), None, "en", "")
    d.show()
    opened = []
    d.open_guide = opened.append           # rows connect to it when made: made again below
    next(b for b in d.cats.buttons() if b.property("cat") == "classes").click()
    rows = d.findChildren(GuideRow)
    assert rows and rows[0].focusPolicy() & Qt.TabFocus and rows[0].accessibleName()
    rows[0].setFocus()
    QTest.keyClick(rows[0], Qt.Key_Return)
    QTest.keyClick(rows[0], Qt.Key_Space)
    assert opened == [rows[0].key, rows[0].key]
    d.search.setText("guide")
    d.search.returnPressed.emit()          # Enter in the search box opens the top result
    assert len(opened) == 3
    d.close()


def test_hebrew_names_find_guides():
    from maplehelper.ui.guides import GuidesDialog
    kb = _fake_kb()
    kb.resolve_names = lambda q: q.replace("קרנינג", "Kerning City")
    d = GuidesDialog(kb, None, "he", "")
    d.search.setText("קרנינג")
    assert d._queries("קרנינג") == ["קרנינג", "kerning city"]
    from maplehelper.ui.guides import GuideRow
    keys = [r.key for r in d.findChildren(GuideRow) if not r.isHidden()]
    assert "guide/kerning-city-party-quest-kpq-guide" in keys
    d.close()


@needs_kb
def test_hebrew_guide_search_with_the_real_aliases(real_kb):
    from maplehelper.ui.guides import GuideRow, GuidesDialog
    d = GuidesDialog(real_kb, None, "he", "")
    d.search.setText("קרנינג")
    assert [r for r in d.findChildren(GuideRow) if not r.isHidden()]
    d.close()


def test_a_link_inside_a_guide_and_back_returns_to_the_place():
    from maplehelper.ui.guides import GuidesDialog
    d = GuidesDialog(_fake_kb(), None, "en", "")
    d.resize(560, 700)
    d.show()
    d.open_guide("guide/thief-class-guide")
    pump()
    bar = d.browser.verticalScrollBar()
    bar.setValue(min(1500, bar.maximum()))
    at = bar.value()
    assert at > 0
    d._on_link(QUrl("guide:assassin-class-guide"))
    assert d._reading == "guide/assassin-class-guide" and "Back to" in d.back.text()
    QTest.keyClick(d, Qt.Key_Escape)        # Esc (like Back) returns to the Thief guide where it was
    pump()
    assert d._reading == "guide/thief-class-guide" and d.stack.currentIndex() == 1 and bar.value() == at
    assert "All guides" in d.back.text()
    d.back.click()                          # then to the list
    assert d.stack.currentIndex() == 0
    d.close()


def test_wide_guide_tables_never_break_inside_a_word():
    """At the window's width the DPS table read "341,7" / "82" for one number, "Savag" / "e Blow"."""
    from maplehelper.ui.guides import GuidesDialog
    d = GuidesDialog(_fake_kb(), None, "en", "")
    d.resize(560, 760)
    d.show()
    d.open_guide("guide/class-dps-rankings")
    pump()
    doc, broken = d.browser.document(), []
    blk = doc.begin()
    while blk.isValid():
        lay, txt = blk.layout(), blk.text()
        for i in range(1, lay.lineCount()):
            st = lay.lineAt(i).textStart()
            if 0 < st < len(txt) and txt[st - 1].isalnum() and txt[st].isalnum():
                broken.append(txt[st - 6:st + 4])
        blk = blk.next()
    assert broken == []
    # a smaller font makes the table fit the window: no sideways bar, no column cut off
    assert doc.size().width() <= d.browser.viewport().width() + 2
    assert d.browser.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    d.close()


# ------------------------------------------------------------------ history

def _pairs(n, now=None):
    now = now or time.time()
    return [{"q": f"question {i}", "a": f"answer {i}", "t": now - i * 600} for i in reversed(range(n))]   # oldest first


def test_history_show_more_adds_cards_without_remaking_the_shown_ones():
    from maplehelper.ui.pinsview import HistoryDialog
    d = HistoryDialog(_pairs(200), "Elipaz", "en", "")
    first = cards(d.rows)[0]
    d.more_btn.click()
    now = cards(d.rows)
    assert len(now) == 160 and now[0] is first
    heads = [d.rows.itemAt(i).widget().text() for i in range(d.rows.count())
             if isinstance(d.rows.itemAt(i).widget(), QLabel) and d.rows.itemAt(i).widget().objectName() == "SectionHeader"]
    assert len(heads) == len(set(heads))                  # a day carried on under its header, not a second one
    d.more_btn.click()
    assert len(cards(d.rows)) == 200 and "200 results" in d.count.text()
    assert not [w for w in d.findChildren(QPushButton) if w.text().startswith("Show") and w.isVisibleTo(d)]
    d.close()


def test_history_card_opens_from_the_keyboard_and_makes_its_answer_then():
    from maplehelper.ui.pinsview import HistoryDialog
    d = HistoryDialog(_pairs(3), "Elipaz", "en", "")
    d.show()
    card = cards(d.rows)[0]
    assert not card.findChildren(QLabel, "PinAnswer")            # the whole answer waits for the first tap
    assert card.focusPolicy() & Qt.TabFocus and card.accessibleName() == "question 0"
    card.setFocus()
    QTest.keyClick(card, Qt.Key_Return)
    go = [b for b in card.findChildren(QPushButton) if b.text() == "Continue in chat"]
    assert go and go[0].isVisibleTo(d)
    got = []
    d.continue_requested.connect(lambda q, a, k: got.append(q))
    go[0].click()
    assert got == ["question 0"]
    QTest.keyClick(card, Qt.Key_Space)                           # and closes again
    assert not go[0].isVisibleTo(d)
    d.close()


def test_english_in_the_hebrew_history_is_laid_out_as_itself():
    """Wrapped as an isolate in a right-to-left paragraph, a nearly full line stuck out a space on the left and its
    first letter was cut. Rendered with a margin: no ink left of the text's own box."""
    from maplehelper.ui.pinsview import set_wrapped_name
    words = "Mano drops a shell and Red Potion when you hit the snail at the edge of the map".split()
    margin = 8

    def overflows(set_text) -> int:
        out = 0
        for n in range(40):
            text = " ".join(words[n % 7:] + words[:n % 7])
            lb = QLabel()
            lb.setStyleSheet("background: white; color: black;")
            lb.setWordWrap(True)
            lb.setContentsMargins(margin, 0, margin, 0)
            lb.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
            lb.setLayoutDirection(Qt.RightToLeft)
            set_text(lb, text)
            lb.setFixedWidth(150 + n * 3)
            lb.resize(lb.width(), lb.heightForWidth(lb.width()))
            img = lb.grab().toImage()
            ink = [x for x in range(margin - 1) for y in range(img.height()) if img.pixelColor(x, y).value() < 160]
            out += bool(ink)
        return out
    assert overflows(lambda lb, text: set_wrapped_name(lb, text, True)) == 0
    # (the old way, lb.setText(bidi.ltr_name(text, True)), stuck out with Windows' fonts; whether it does depends on
    # the fonts and on what earlier tests in the same worker loaded, so it failed CI on macOS: only the fix is checked)
    lb = QLabel()
    set_wrapped_name(lb, "Mano drops a shell", True)
    assert lb.layoutDirection() == Qt.LeftToRight and lb.text() == "Mano drops a shell"
    hebrew = QLabel()
    set_wrapped_name(hebrew, "מה מפיל מאנו?", True)
    assert hebrew.layoutDirection() == Qt.RightToLeft


@needs_kb
def test_history_pictures_skip_guide_banners(real_kb):
    from maplehelper.ui.pinsview import HistoryDialog
    d = HistoryDialog([], "Elipaz", "en", "", kb=real_kb)
    mob = real_kb._monster_by_name["green mushroom"] if hasattr(real_kb, "_monster_by_name") else "monster/13"
    row = d._pictures([mob, "guide/what-is-maplestory-classic-worlds"])
    assert row is not None and len(row.findChildren(QLabel)) == 1
    assert d._pictures(["guide/what-is-maplestory-classic-worlds"]) is None
    d.close()


def test_yesterday_follows_the_calendar_across_a_clock_change(monkeypatch):
    """Israel, clocks forward Fri 27 Mar 2026 02:00 (+2 -> +3): at 28 Mar 00:30 "now minus 24 h" was 26 Mar."""
    from maplehelper.ui import pinsview
    switch = datetime.datetime(2026, 3, 27, 0, 0, tzinfo=datetime.timezone.utc).timestamp()

    class IsraelDate(datetime.date):
        @classmethod
        def fromtimestamp(cls, ts):
            local = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc) + datetime.timedelta(
                hours=3 if ts >= switch else 2)
            return cls(local.year, local.month, local.day)

    def local_ts(y, m, d, hh, mm):
        naive = datetime.datetime(y, m, d, hh, mm, tzinfo=datetime.timezone.utc).timestamp()
        return naive - (3 if naive - 3 * 3600 >= switch else 2) * 3600

    monkeypatch.setattr(pinsview, "dt", SimpleNamespace(date=IsraelDate, timedelta=datetime.timedelta))
    now = local_ts(2026, 3, 28, 0, 30)
    monkeypatch.setattr(pinsview.time, "time", lambda: now)
    d = pinsview.HistoryDialog([], "Elipaz", "en", "")
    assert d._day(local_ts(2026, 3, 27, 10, 0)) == "Yesterday"
    assert d._day(local_ts(2026, 3, 26, 23, 45)) == "Mar 26"            # never day.month in English (HEB-16)
    assert d._day(local_ts(2026, 3, 28, 0, 10)) == "Today"
    d.close()


def test_history_search_matches_only_what_the_cards_show():
    pairs = [{"q": "[about Mano] what does it drop?", "a": "**Mano** drops a Snail Shell", "t": 1},
             {"q": "where to train", "a": "Ant Tunnel", "t": 2}]
    assert pins.search(pairs, "about") == [] and pins.search(pairs, "[about") == []
    assert pins.search(pairs, "**") == []
    assert pins.search(pairs, "mano drops") == [pairs[0]]       # the name is still found in the answer
    assert pins.search(pairs, "drop") == [pairs[0]]


@needs_kb
def test_share_card_ellipsizes_a_long_name_and_wraps_a_long_map(isolated_store, real_kb):
    from maplehelper.i18n import I18n
    from maplehelper.ui.pinsview import character_card_image
    p = isolated_store.Profiles()
    short = p.add("Kiwi", "Thief", "Assassin", 34)
    short.map = "Ant Tunnel I"
    long = p.add("ElipazTheVeryLongNameXY", "Thief", "Assassin", 34)
    long.map = "Physical Fitness Test <Normal Waiting Room>"
    from maplehelper.ui import theme
    labels = []
    orig = QLabel.setText

    def spy(self, text):
        if self.objectName() == "ShareName":           # only the card's own name label, not every QLabel alive
            labels.append((self.objectName(), text, self.wordWrap()))
        orig(self, text)
    app.setStyleSheet(theme.stylesheet(theme.load_fonts(), 14))      # the card's real fonts (bold, 22 px name)
    try:
        with pytest.MonkeyPatch.context() as mp:        # undone even when the card raises
            mp.setattr(QLabel, "setText", spy)
            a = character_card_image(short, None, real_kb, None, I18n("en"))
            b = character_card_image(long, None, real_kb, None, I18n("en"))
    finally:
        app.setStyleSheet("")
    names = [t for o, t, _ in labels if o == "ShareName"]
    # cut where the font's widths say, ending in "…": how many letters fit moved with the font engine's state in a
    # full run ("ElipazThe…" once), so the cut is checked, not its exact place
    assert "Kiwi" in names and any(t.endswith("…") and len(t) > 6 and long.name.startswith(t[:-1]) for t in names)
    assert a.width() == b.width() and b.height() >= a.height()        # the long map took a second line
