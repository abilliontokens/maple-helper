"""Launch-audit fixes in the quest lists, the Grind spots and Farm windows, the market cache and the keyboard
(offscreen Qt): TL1 / TL2 and UX (Enter on a Tabbed button, the tour's count, the pin's name)."""
import os
import sys
import time
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


@needs_kb
def test_quests_for_a_level_is_worked_out_once_and_handed_out_fresh(real_kb):
    # TL1-4: the quests page, its search and a jump to a quest each worked the lists out again
    from maplehelper import quests
    a = quests.for_level(real_kb, 31, "Thief", "Assassin", [])
    a["now"].clear()
    b = quests.for_level(real_kb, 31, "Thief", "Assassin", [])
    assert b["now"] and b["now"][0] is quests.for_level(real_kb, 31, "Thief", "Assassin", [])["now"][0]
    done = quests.for_level(real_kb, 31, "Thief", "Assassin", [b["now"][0].key])
    assert b["now"][0].key not in [q.key for q in done["now"]]


def test_market_cache_is_shared_safely_between_threads(monkeypatch):
    # TL2-10: the price card's and the sell check's threads both evicted and inserted with no lock
    import threading

    from maplehelper import market
    monkeypatch.setattr(market, "_item_cache", {})
    monkeypatch.setattr(market, "_get", lambda url, timeout: None)
    errors = []

    def run(start):
        try:
            for i in range(start, start + 400):
                market._lookup(i)
        except Exception as e:      # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=run, args=(n * 1000,)) for n in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors and len(market._item_cache) <= market.CACHE_ITEMS


@needs_kb
@pytest.mark.parametrize("lang", ["en", "he"])
def test_grind_spot_and_farm_cards_fit_the_window(app, real_kb, isolated_store, lang):
    # UX-1 / TL2-2: four links in one row made each English monster card 561 px in a 514 px page; a farm drop line
    # (link + chips) was up to 518 px. UX-2: "Hit & damage" showed as "Hit _damage"
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QPushButton

    from maplehelper.i18n import I18n
    from maplehelper.ui.farmtool import FarmTool
    from maplehelper.ui.grindspots import GrindSpots
    p = isolated_store.Profiles()
    p.set_active(p.add("Kiwi", "Thief", "Assassin", 35).id)
    p.active.stats = {"acc": 96, "dmg_min": 182, "dmg_max": 431}      # every chip a spot card can have
    s = isolated_store.Settings()
    s["grind_spots"] = s["farm_tool"] = True
    windows = [GrindSpots(real_kb, s, p, I18n(lang)), FarmTool(real_kb, s, p, I18n(lang))]
    try:
        for w in windows:
            w.refresh()
            for width in (w.DEFAULT_W, w.MIN_W):
                w.resize(width, 800)
                app.processEvents()
                body = w._scroll
                assert body.widget().minimumSizeHint().width() <= body.viewport().width(), (type(w).__name__, width)
        hit = [b for b in windows[0].findChildren(QPushButton) if "damage" in b.text()]
        assert lang == "he" or (hit and all("&&" in b.text() for b in hit))
    finally:
        windows[0]._saving.stop()
        windows[1]._searching.stop()
        for w in windows:
            w._geom.stop()
            w.hide()
            w.deleteLater()
        app.processEvents()
        app.sendPostedEvents(None, QEvent.DeferredDelete)


def test_enter_on_a_tabbed_button_clicks_that_button(app):
    # UX-14: Enter on a focused Back went forward; on Save (no Enter button) it did nothing
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QPushButton, QVBoxLayout

    from maplehelper.ui import glass
    d = glass.GlassDialog("t", False)
    lay = QVBoxLayout(d.content)
    clicked = []
    back, nxt = QPushButton("Back"), QPushButton("Next")
    back.clicked.connect(lambda: clicked.append("back"))
    nxt.clicked.connect(lambda: clicked.append("next"))
    lay.addWidget(back)
    lay.addWidget(nxt)
    d.enter_button = nxt
    d.show()
    d.activateWindow()
    app.processEvents()

    def enter():
        d.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    back.setFocus(Qt.OtherFocusReason)        # the window's own first focus: Enter is still Next
    app.processEvents()
    enter()
    assert clicked == ["next"]
    nxt.setFocus(Qt.OtherFocusReason)
    app.processEvents()
    glass._TabKeys._at = time.monotonic()      # a Tab the player pressed
    back.setFocus(Qt.TabFocusReason)
    app.processEvents()
    if not back.hasFocus():
        pytest.skip("no focus offscreen")
    enter()
    assert clicked == ["next", "back"]
    d.close()


def test_tour_counts_its_numbered_cards_from_one(app, isolated_store, kb):
    # UX-20: the first numbered card read "2 / 15"
    from maplehelper.ui.overlay import Overlay
    ov = Overlay(isolated_store.Settings(), isolated_store.Profiles(), kb, None)
    ov.resize(520, 760)
    ov.show()
    ov.start_tour()
    tr = ov._tour
    n = len(tr.steps) - 2
    tr.go(1)
    assert tr.count.text() == f"1 / {n}"
    tr.go(len(tr.steps) - 2)
    assert tr.count.text() == f"{n} / {n}"
    tr.finish()
    ov.hide()


def test_the_pin_under_an_answer_has_a_name(app):
    # UX-15: an icon-font glyph with a tooltip only: a screen reader read nothing
    from PySide6.QtWidgets import QToolButton

    from maplehelper.ui.widgets import Bubble
    b = Bubble("an answer", "assistant", False)
    b.add_pin(lambda: None, "Pin this answer")
    pins = [x for x in b.findChildren(QToolButton) if x.toolTip() == "Pin this answer"]
    assert pins and pins[0].accessibleName() == "Pin this answer"
