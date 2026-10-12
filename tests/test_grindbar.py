"""The grind bar over the game (ui/grindbar.py): shown from its own setting, its five segments filled from
grindlive.live (every figure "–" with no run, the first goal still to reach in the right slot), the dot's colour by how
the run stands, Pause / Resume / Stop / Start asking the scanner, a click on its body (never on a button or its dots)
opening the grind window, every size following its height, its default size the game's megaphone strip, its place
kept, Hebrew mirrored (its figures left-to-right blocks), and the white glass's palette in its style. Also the
toolbar's Grind button, which is the bar's setting."""
import os
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from maplehelper.i18n import I18n

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _dark_look():
    """Every test starts and ends on today's dark glass (npcoverlay's module state every window over the game reads)."""
    from maplehelper.ui import npcoverlay
    npcoverlay.apply_look(None)
    yield
    npcoverlay.apply_look(None)


class FakeScanner(QObject):
    """What the bar asks of ui/lootscan.LootScanner: whose run, the run's log, and its buttons' four calls."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.calls: list[str] = []
        self.is_paused = False

    def cid(self) -> str:
        return "c1"

    def log_for(self, cid):
        return None

    def paused(self) -> bool:
        return self.is_paused

    def start(self) -> None:
        self.calls.append("start")

    def end(self) -> None:
        self.calls.append("end")

    def pause(self) -> None:
        self.calls.append("pause")

    def resume_run(self) -> None:
        self.calls.append("resume_run")


def _live(running=True, **kw):
    """A grindlive.Live as the bar reads it: Ant Tunnel I, 42:10, 18,400 / 14,200 an hour, Lv. 31 at 63 %, the last
    drop 4.2 an hour."""
    rates = SimpleNamespace(exp_h=18400, mesos_h=9000, loot_h=6400, potions_h=1200, profit_h=14200,
                            active_s=42 * 60 + 10)
    base = dict(running=running, state="running" if running else "stopped", map_id="105070001",
                map_name="Ant Tunnel I", wall_s=2700.0, session=rates, recent=rates, level=31, exp_pct=63.4,
                to_level_s=38 * 60, last_drop=("Horny Mushroom Cap", "item/4000020", 4.2), warnings=[], deaths=0,
                potions=0, potion_cost=0, level_ups=[], goals=[], move_on=None)
    return SimpleNamespace(**{**base, **kw})


@pytest.fixture
def bar(qapp, isolated_store, kb, monkeypatch):
    """The bar in English over a fake scanner (its changes refresh it, as the app wires it), grindlive.live stubbed:
    `shown["live"]` is what the next fill gets, `asked` every call's (log, goals)."""
    from maplehelper import grindlive
    from maplehelper.ui import grindbar
    shown, asked = {"live": _live()}, []

    def live(kb_, lg, character, goals, now=None):
        asked.append((lg, goals))
        return shown["live"]

    monkeypatch.setattr(grindlive, "live", live)
    monkeypatch.setattr(grindbar, "_game_rect", lambda: None)      # no game window: the screen's default place
    s = isolated_store.Settings()
    sc = FakeScanner()
    w = grindbar.GrindBar(sc, s, kb, isolated_store.Profiles(), I18n("en"))
    sc.changed.connect(w.refresh)
    s["grind_bar"] = True
    yield SimpleNamespace(w=w, s=s, sc=sc, shown=shown, asked=asked)
    w.hide()
    w.deleteLater()


def _pump():
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()


# ------------------------------------------------------------ its setting

def test_it_shows_while_its_setting_is_on_and_reads_every_second_while_it_shows(bar):
    w, s = bar.w, bar.s
    s["grind_bar"] = False
    w.refresh()
    assert not w.isVisible() and bar.asked == []
    s["grind_bar"] = True
    w.refresh()
    assert w.isVisible() and w._clock.isActive() and len(bar.asked) == 1
    bar.sc.changed.emit()                           # a pickup, a bar read: the figures again
    assert len(bar.asked) == 2
    s["grind_bar"] = False
    bar.sc.changed.emit()
    assert not w.isVisible() and not w._clock.isActive()


def test_its_right_click_hide_turns_the_setting_off_and_says_so(bar):
    w, s = bar.w, bar.s
    w.refresh()
    closed = []
    w.closed.connect(lambda: closed.append(s["grind_bar"]))
    w._hide_clicked()
    assert closed == [False] and not w.isVisible()


# ------------------------------------------------------------ what it shows

def test_its_five_segments_say_the_run(bar):
    w = bar.w
    w.refresh()
    assert w.texts() == {"map": ("ANT TUNNEL I", "42:10"), "exp": ("EXP / HR", "18,400"),
                         "profit": ("PROFIT / HR", "14,200"),
                         "level": ("LV. 31 → 32 · ABOUT 38 MIN", "63%"),
                         "slot": ("LAST DROP · 4.2 / HR", "Horny Mushroom Cap")}
    assert w._progress.value == pytest.approx(0.634)
    assert bar.asked[-1] == (None, [])              # the scanner's log for its character, the settings' goals


def test_with_no_run_every_figure_is_a_dash_and_start_shows(bar):
    w = bar.w
    bar.shown["live"] = _live(running=False)
    w.refresh()
    texts = w.texts()
    assert [v for _label, v in texts.values()] == ["–"] * 5
    assert texts["map"][0] == "MAP" and texts["level"][0] == "LEVEL" and texts["slot"][0] == "LAST DROP"
    assert w._progress.value is None
    assert w._start.isVisibleTo(w) and not w._pause.isVisibleTo(w) and not w._stop.isVisibleTo(w)
    assert w._start.text().strip() == "Start"


def test_long_figures_are_shortened_and_an_hour_shows_in_the_clock(bar):
    w = bar.w
    rates = SimpleNamespace(exp_h=1_840_000, profit_h=-1200, active_s=3 * 3600 + 42 * 60 + 10)
    bar.shown["live"] = _live(session=rates, to_level_s=75 * 60, last_drop=("Horny Mushroom Cap", "item/4000020", None))
    w.refresh()
    t = w.texts()
    assert t["map"][1] == "3:42:10" and t["exp"][1] == "1.84M"
    assert t["profit"][1] == "-1,200" and t["level"][0] == "LV. 31 → 32 · ABOUT 1:15 H"
    assert t["slot"][0] == "LAST DROP"              # under a minute: no rate yet


@pytest.mark.parametrize("per_h,said", [(0.25, "0.2"), (4.2, "4.2"), (9.96, "10"), (18.4, "18"), (1234.6, "1,235")])
def test_the_last_drops_rate_has_one_decimal_under_ten_and_is_whole_above(bar, per_h, said):
    w = bar.w
    bar.shown["live"] = _live(last_drop=("Horny Mushroom Cap", "item/4000020", per_h))
    w.refresh()
    assert w.texts()["slot"] == (f"LAST DROP · {said} / HR", "Horny Mushroom Cap")


def test_the_first_goal_still_to_reach_takes_the_right_slot(bar):
    from maplehelper import grindlive
    w = bar.w
    done = grindlive.GoalProgress(grindlive.Goal("mesos", 1000), 1500, True, 0.0)
    level = grindlive.GoalProgress(grindlive.Goal("level", 32), 31, False, 38 * 60)
    bar.shown["live"] = _live(goals=[done, level])
    w.refresh()
    assert w.texts()["slot"] == ("GOAL · LV. 32", "about 38 min")
    item = grindlive.GoalProgress(grindlive.Goal("item", 10, "item/4000020", "Horny Mushroom Cap"), 3, False, None)
    bar.shown["live"] = _live(goals=[item])
    w.refresh()
    assert w.texts()["slot"] == ("GOAL · 10 HORNY MUSHROOM CAP", "3 / 10")


def test_a_long_name_ends_in_an_ellipsis_with_the_whole_name_in_its_tooltip(bar):
    from maplehelper.ui import grindbar
    w = bar.w
    w.refresh()
    w.resize(900 + 2 * grindbar.SHADOW, 56 + 2 * grindbar.SHADOW)      # its smallest
    bar.shown["live"] = _live(last_drop=("Blue One-Lined T-Shirt (M) of the Very Long Name", "item/1", 7))
    bar.sc.changed.emit()
    _pump()
    shown = w._slot.value.text()
    assert shown.endswith("…") and w._slot.value.toolTip() == "Blue One-Lined T-Shirt (M) of the Very Long Name"


@pytest.mark.parametrize("state,colour", [("running", "#4CD07D"), ("dead", "#FF6B6B"), ("paused", None)])
def test_the_dot_says_how_the_run_stands(bar, state, colour):
    from maplehelper.ui import npcoverlay, theme
    w = bar.w
    bar.shown["live"] = _live(state=state)
    w.refresh()
    assert w._dot.state == state
    want = QColor(colour) if colour else theme.qcolor(npcoverlay.palette().muted)      # grey: the glass's muted
    assert w._dot.color().rgba() == want.rgba()
    bar.shown["live"] = _live(running=False)
    w.refresh()
    assert w._dot.state == "stopped" and w._dot.color().rgba() == theme.qcolor(npcoverlay.palette().muted).rgba()


def test_the_flash_pulses_the_right_slot(bar):
    w = bar.w
    w.refresh()
    assert not w._slot.flashing()
    w.flash()
    assert w._slot.flashing()


# ------------------------------------------------------------ its buttons and clicks

def test_pause_resume_stop_and_start_ask_the_scanner(bar):
    w, sc = bar.w, bar.sc
    w.refresh()
    assert w._pause.text().strip() == "Pause" and w._stop.text().strip() == "Stop"
    w._pause.click()
    sc.is_paused = True
    sc.changed.emit()
    assert w._pause.text().strip() == "Resume"
    w._pause.click()
    w._stop.click()
    bar.shown["live"] = _live(running=False)
    sc.changed.emit()
    w._start.click()
    assert sc.calls == ["pause", "resume_run", "end", "start"]


def test_a_click_on_its_body_opens_the_window_but_not_on_a_button_or_its_dots(bar):
    w = bar.w
    w.refresh()
    opened = []
    w.open_window.connect(lambda: opened.append(True))
    for part in (w._exp_fig, w._slot.value, w._level_label):
        QTest.mouseClick(part, Qt.LeftButton)
    assert opened == [True] * 3
    QTest.mouseClick(w._stop, Qt.LeftButton)
    QTest.mouseClick(w._grip, Qt.LeftButton)
    assert opened == [True] * 3 and bar.sc.calls == ["end"]


# ------------------------------------------------------------ its size and place

def test_its_fonts_and_sizes_follow_its_height(bar):
    from maplehelper.ui import grindbar
    w = bar.w
    w.refresh()
    sizes = {}
    for glass_w, glass_h in ((1568, 86), (2000, 110)):
        w.resize(glass_w + 2 * grindbar.SHADOW, glass_h + 2 * grindbar.SHADOW)
        _pump()
        sheet = w.styleSheet()
        label, value = round(0.163 * glass_h), round(0.30 * glass_h)
        assert f"font-size: {label}px;" in sheet.split("#Label")[1].split("}")[0]
        assert f"font-size: {value}px;" in sheet.split("#Value")[1].split("}")[0]
        assert w._exp_label.font().pixelSize() == label and w._exp_fig.font().pixelSize() == value
        sizes[glass_h] = (w._dot.height(), w._progress.height(), w._stop.height())
    assert sizes[86] == (11, 9, 41) and all(b > a for a, b in zip(sizes[86], sizes[110]))


def test_any_size_from_900_by_56_is_allowed(bar):
    from maplehelper.ui import grindbar
    w = bar.w
    assert (w.minimumWidth(), w.minimumHeight()) == (900 + 2 * grindbar.SHADOW, 56 + 2 * grindbar.SHADOW)


def test_its_default_is_the_megaphone_strip_just_above_the_games_bottom_bar(bar, monkeypatch):
    """57.35 % x 5.48 % of the game's picture (1568 x 86 on a 2734 x 1568 game), centred, its glass ending where the
    game's bottom HUD strip begins; no game window: 70 % of the screen's width, in the strip's proportions."""
    from maplehelper.ui import grindbar
    from PySide6.QtGui import QGuiApplication
    w = bar.w
    monkeypatch.setattr(grindbar, "_game_rect", lambda: QRect(100, 50, 2734, 1568))
    glass = w.default_geometry().adjusted(grindbar.SHADOW, grindbar.SHADOW, -grindbar.SHADOW, -grindbar.SHADOW)
    assert (glass.width(), glass.height()) == (1568, 86)
    assert glass.x() == 100 + (2734 - 1568) // 2
    assert glass.y() + glass.height() == 50 + 1568 - round(1568 * grindbar.STRIP)
    monkeypatch.setattr(grindbar, "_game_rect", lambda: None)
    scr = QGuiApplication.primaryScreen().availableGeometry()
    glass = w.default_geometry().adjusted(grindbar.SHADOW, grindbar.SHADOW, -grindbar.SHADOW, -grindbar.SHADOW)
    assert glass.width() == max(grindbar.MIN_W, round(scr.width() * 0.7))
    assert abs(glass.center().x() - scr.center().x()) <= 1 and glass.bottom() < scr.bottom()


def test_its_place_and_size_are_kept_and_reopened(bar, isolated_store, kb):
    from maplehelper.ui import grindbar
    w, s = bar.w, bar.s
    w.refresh()
    w.setGeometry(QRect(40, 60, 1300, 100))
    _pump()
    w.hide()                                        # hidden (or the app quitting): kept at once
    assert s["grind_bar_geom"] == {"x": 40, "y": 60, "w": 1300, "h": 100}
    again = grindbar.GrindBar(bar.sc, s, kb, isolated_store.Profiles(), I18n("en"))
    try:
        again.refresh()
        assert again.geometry() == QRect(40, 60, 1300, 100)
    finally:
        again.hide()
        again.deleteLater()


# ------------------------------------------------------------ in Hebrew

def _bare(text: str) -> str:
    """A line as read, without the bidi marks that lay it out (RLM, the isolates and embeddings, their pops)."""
    from maplehelper import bidi
    for mark in (bidi.RLM, bidi.LRI, bidi.RLI, bidi.PDI, bidi.LRE, bidi.PDF):
        text = text.replace(mark, "")
    return text.replace("\u00a0", " ")


def test_in_hebrew_the_row_is_mirrored_and_the_progress_fills_from_the_right(bar):
    """The dots at the right edge, the buttons at the left, the map first from the right and the last drop last; the
    level's bar lit from its right end."""
    from maplehelper.ui import npcoverlay
    w = bar.w
    w.apply_language(I18n("he"))
    _pump()
    assert w.layoutDirection() == Qt.RightToLeft
    x = lambda part: part.mapTo(w, part.rect().topLeft()).x()
    assert x(w._grip) > x(w._map) > x(w._exp) > x(w._profit) > x(w._level) > x(w._slot)
    assert x(w._slot) > x(w._pause) > x(w._stop)
    assert x(w._grip) + w._grip.width() > w.width() - 2 * w.unit       # at the edge, not just right of the middle
    assert w._progress.isRightToLeft()
    img = w._progress.grab().toImage()
    accent = QColor(npcoverlay.accent_of(bar.s)[0]).rgb()
    mid = img.height() // 2
    assert img.pixelColor(round(img.width() * 0.9), mid).rgb() == accent                 # 63 %: the right end lit
    assert img.pixelColor(round(img.width() * 0.1), mid).rgb() != accent                 # ... the left one not


def test_in_hebrew_the_labels_are_hebrew_and_the_figures_keep_their_digits(bar):
    from maplehelper import bidi
    w = bar.w
    w.apply_language(I18n("he"))
    texts = {k: (_bare(label), _bare(value)) for k, (label, value) in w.texts().items()}
    assert texts == {"map": ("Ant Tunnel I", "42:10"), "exp": ("EXP לשעה", "18,400"),
                     "profit": ("רווח לשעה", "14,200"),
                     "level": ("רמה 31 → 32 · בערך 38 דק'", "63%"),
                     "slot": ("השלל האחרון · 4.2 לשעה", "Horny Mushroom Cap")}
    # each figure one left-to-right block in its right-to-left line: "42:10" and "18,400" never read backwards
    for fig, shown in ((w._time, "42:10"), (w._exp_fig, "18,400"), (w._profit_fig, "14,200"), (w._pct, "63%")):
        assert fig.text() == f"{bidi.RLM}{bidi.LRI}{shown}{bidi.PDI}{bidi.RLM}"
    assert f"{bidi.LRI}4.2{bidi.PDI}" in w._slot.label.full()                    # the last drop's rate, too
    assert f"{bidi.LRI}31\u00a0→\u00a032{bidi.PDI}" in w._level_label.text()   # the arrow at the new level
    assert w._map_label.text() == f"{bidi.RLM}{bidi.LRI}Ant Tunnel I{bidi.PDI}{bidi.RLM}"
    assert w._slot.value.full() == f"{bidi.RLM}{bidi.LRI}Horny Mushroom Cap{bidi.PDI}{bidi.RLM}"
    shown = w._slot.value.text()                    # (at 900 px wide, "Horny Mushro…": its "…" inside the block too)
    assert shown.startswith(f"{bidi.RLM}{bidi.LRI}Horny") and shown.endswith(f"{bidi.PDI}{bidi.RLM}")
    assert (_bare(w._pause.text()).strip(), _bare(w._stop.text()).strip()) == ("השהיה", "עצירה")


def test_in_hebrew_with_no_run_the_dashes_sit_under_their_labels(bar):
    """A bare "–" laid out left to right, at the far end of its segment from its label: marked right-to-left."""
    from maplehelper import bidi
    w = bar.w
    bar.shown["live"] = _live(running=False)
    w.apply_language(I18n("he"))
    texts = w.texts()
    assert [_bare(label) for label, _v in texts.values()] == ["מפה", "EXP לשעה", "רווח לשעה", "רמה", "השלל האחרון"]
    assert [v for _label, v in texts.values()] == [f"{bidi.RLM}–{bidi.RLM}"] * 5
    assert w._start.isVisibleTo(w) and _bare(w._start.text()).strip() == "התחלה"


# ------------------------------------------------------------ its look

def test_the_white_glass_gives_its_style_the_light_palette(bar):
    from maplehelper.ui import npcoverlay
    w, s = bar.w, bar.s
    w.refresh()
    assert f"color: {npcoverlay.DARK.text};" in w.styleSheet()
    s["overlay_tint"] = "white"
    npcoverlay.apply_look(s)
    w.refresh()                                     # as the app does after the ⚙ panel's pick
    sheet = w.styleSheet()
    assert f"color: {npcoverlay.LIGHT.text};" in sheet and f"color: {npcoverlay.LIGHT.muted};" in sheet
    assert npcoverlay.DARK.text not in sheet and npcoverlay.DARK.muted not in sheet


# ------------------------------------------------------------ the toolbar's Grind button

def test_the_toolbars_grind_button_is_the_bars_setting(qapp, isolated_store):
    """As Loot Log is its window's: the button flips settings["grind_bar"] and says so (grind_toggled); refresh
    follows the setting (the bar's own Hide turned it off)."""
    from maplehelper.ui import gametoolbar
    from maplehelper.ui.location import LOCATION
    old, LOCATION.box = LOCATION.box, None
    s = isolated_store.Settings()
    w = gametoolbar.GameToolbar(s, I18n("en"))
    try:
        seen = []
        w.grind_toggled.connect(lambda: seen.append(s["grind_bar"]))
        assert w._grind.text() == "Grind" and not w._grind.isChecked() and not w._grind.icon().isNull()
        w._grind.click()
        assert seen == [True] and s["grind_bar"] is True
        w._grind.click()
        assert seen == [True, False] and s["grind_bar"] is False
        s["grind_bar"] = True
        w.refresh()
        assert w._grind.isChecked()
    finally:
        LOCATION.boxed.disconnect(w._box_moved)
        LOCATION.box = old
        w.close()
