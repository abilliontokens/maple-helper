"""Follow-up fixes after the audit merge (offscreen Qt): the COT2 label beside shop prices in the chat's answer,
keyboard and accessible names, the tip strip, wide guide tables, dialogs freed at once."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from maplehelper import market, quick  # noqa: E402
from maplehelper.i18n import I18n  # noqa: E402

app = QApplication.instance() or QApplication([])


def pump(ms=50):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


# ------------------------------------------------------------------ 2: COT2 prices are labelled where they show

def test_cot2_label_beside_the_shop_price(kb, monkeypatch):
    from maplehelper import combat
    shop = ("Mia", "Henesys · Potion Shop", 50)
    prices = market.NpcPrices(None, shops=[shop], labels={shop[:2]: "COT2"})
    monkeypatch.setattr(market, "npc_prices", lambda *a: prices)
    monkeypatch.setattr(combat, "released", lambda *a: True)
    a = quick.answer("where to buy red potion", kb, I18n("en"))
    assert a and "Mia · Henesys · Potion Shop · 50 mesos (COT2 test price)" in a.text
    # a price the KB doesn't label stays plain
    prices.labels.clear()
    a = quick.answer("where to buy red potion", kb, I18n("en"))
    assert a and "COT2" not in a.text


# ------------------------------------------------------------------ 3: the glossary "?" from the keyboard

def test_term_links_open_from_the_keyboard(monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

    from maplehelper import glossary
    from maplehelper.ui import terms
    monkeypatch.setattr(terms, "LANG", "en")
    monkeypatch.setattr(terms, "_popup", None)            # a card a Hebrew window before left behind
    opened = []
    monkeypatch.setattr(terms, "show", lambda link, lang, near=None: opened.append((link, near is not None)))
    from PySide6.QtWidgets import QApplication
    for other in QApplication.topLevelWidgets():         # windows earlier tests left open took the focus
        other.hide()
    w = QWidget()
    w.setLayoutDirection(Qt.LeftToRight)              # an English window, whatever a Hebrew one before it set
    QApplication.setLayoutDirection(Qt.LeftToRight)
    lay = QVBoxLayout(w)
    before, after = QLineEdit(), QLineEdit()
    lb = terms.watch(QLabel(glossary.annotate("Your HP and ACC", "en")))
    plain = terms.watch(QLabel("No terms here"))
    for x in (before, lb, plain, after):
        lay.addWidget(x)
    w.show()
    # its own window active: in a full run another test's window still held it, and Tab moved nothing
    w.raise_()
    w.activateWindow()
    QTest.qWaitForWindowActive(w, 1000)
    pump()
    assert plain.focusPolicy() == Qt.NoFocus              # nothing to open: not a Tab stop
    assert "Your HP and ACC" in lb.accessibleName() and "HP, ACC" in lb.accessibleDescription()
    before.setFocus()
    pump()
    QTest.keyClick(before, Qt.Key_Tab)
    pump()
    assert lb.hasFocus()
    QTest.keyClick(lb, Qt.Key_Return)                     # the first "?" right away, no empty stop before it
    QTest.keyClick(lb, Qt.Key_Tab)
    QTest.keyClick(lb, Qt.Key_Space)
    assert opened == [("g:HP", True), ("g:ACC", True)]
    QTest.keyClick(lb, Qt.Key_Tab)
    pump()
    assert after.hasFocus()                               # out of the label, past the one without a "?"
    lb.setText("plain now")
    pump()
    assert lb.focusPolicy() == Qt.NoFocus
    w.close()


# ------------------------------------------------------------------ 5: names for screen readers, the tip strip

def test_close_button_has_a_name_in_both_languages():
    from maplehelper.ui.glass import GlassDialog
    assert GlassDialog("x", rtl=False).close_btn.accessibleName() == "Close"       # an ✕ glyph, read as nothing
    assert GlassDialog("x", rtl=True).close_btn.accessibleName() == I18n("he")("close")


def test_tip_strip_asks_from_the_keyboard():
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from maplehelper import plan
    from maplehelper.ui.plancard import TipStrip
    strip = TipStrip()
    tip = plan.Tip(kind="k", key="tip_hide", args={}, question="What now?")
    strip.show_tip(tip, I18n("en"), rtl=False)
    asked = []
    strip.asked.connect(asked.append)
    assert strip.focusPolicy() & Qt.TabFocus and strip.accessibleName() == "Hide until the next level"
    QTest.keyClick(strip, Qt.Key_Return)
    QTest.keyClick(strip, Qt.Key_Space)
    assert asked == ["What now?", "What now?"]


# ------------------------------------------------------------------ 9: a wide guide table fits by its padding

def test_wide_table_gives_up_cell_padding_before_it_scrolls(monkeypatch):
    from PySide6.QtGui import QTextTable
    from PySide6.QtWidgets import QTextBrowser

    from maplehelper.ui import guides as gui
    words = " ".join(f"<td>Doombringer{i}</td>" for i in range(8))
    html = f"<table cellpadding='5' border='1' cellspacing='0'><tr>{words}</tr></table>"
    made = []

    def fitted(room: int) -> tuple[float, QTextBrowser]:
        """The table's width after fit_tables in a view with this much room."""
        b = QTextBrowser()
        made.append(b)
        b.setStyleSheet("font-size: 14px;")
        b.setHtml(html)
        b.show()
        pump()
        b.resize(room + int(2 * b.document().documentMargin()) + b.width() - b.viewport().width(), 200)
        pump()
        gui.fit_tables(b)
        table = next(f for f in b.document().rootFrame().childFrames() if isinstance(f, QTextTable))
        return b.document().documentLayout().frameBoundingRect(table).width(), b

    # the least the table can be: at the smallest font with the guides' padding, and with the least padding
    narrow, _ = fitted(60)
    with monkeypatch.context() as m:
        m.setattr(gui, "TABLE_MIN_PAD", 5)
        wide, _ = fitted(60)
    assert narrow < wide - 20
    room = int((wide + narrow) / 2)
    width, b = fitted(room)
    assert width <= room + 1 and b.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    for b in made:
        b.close()


# ------------------------------------------------------------------ 11: a dropped dialog goes at once, not at a GC

def test_a_dropped_glass_dialog_is_freed_without_the_garbage_collector():
    # its backdrop and title bar kept the window: a cycle, so the window and its widgets went whenever Python's
    # garbage collector next ran, deleting them under the code using them then
    import gc

    from maplehelper.ui.glass import GlassDialog
    gone = []
    gc.disable()
    try:
        d = GlassDialog("x", rtl=False)
        d.content.destroyed.connect(lambda *_: gone.append(True))
        del d
        app.processEvents()
        assert gone == [True]
    finally:
        gc.enable()


def test_chat_input_has_a_name_in_both_languages(isolated_store, kb, monkeypatch):
    from PySide6.QtCore import QRect

    from maplehelper import osapi
    from maplehelper.ui import terms
    from maplehelper.ui.overlay import Overlay
    for name in ("float_over_fullscreen", "activate_self", "focus_window"):
        monkeypatch.setattr(osapi, name, lambda *a: None)
    monkeypatch.setattr(osapi, "find_game_window", lambda: None)
    monkeypatch.setattr(terms, "LANG", terms.LANG)
    s, p = isolated_store.Settings(), isolated_store.Profiles()
    s["language"] = "he"
    p.set_active(p.add("Elipaz", "Thief", "Assassin", 32).id)
    ov = Overlay(s, p, kb, None)
    ov.setGeometry(QRect(-3000, -3000, 460, 700))
    try:
        assert ov.input.accessibleName() == I18n("he")("input_a11y")
        s["language"] = "en"
        ov.apply_language()
        assert ov.input.accessibleName() == "Your question"
    finally:
        ov.deleteLater()
