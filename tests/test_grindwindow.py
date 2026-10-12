"""The grind window over the game (ui/grindwindow.py): what each tab draws from grindlive's results (stubbed here: the
window shows what grindlive says, test_grindlive checks the numbers), the empty states that say what to do, the goals
kept in the settings, Show the way, a run's summary and Back, the keyboard taken only while a goal is typed, the KB's
own pictures, Hebrew mirrored, and the white glass."""
import datetime
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from maplehelper import grindlive, lootlog
from maplehelper.i18n import STRINGS, I18n

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
SNAIL, BLUE = "monster/100100", "monster/100101"     # the fixture KB's Snail and Blue Snail
POTION = "item/2000000"                                # its one item: Red Potion
HG1, HG2 = "100000001", "100000002"                    # Henesys Hunting Ground I and II
EN = I18n("en")
NOON = datetime.datetime.combine(datetime.date.today(), datetime.time(11, 0)).timestamp()
YESTERDAY = NOON - 86400


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(isolated_store):
    return isolated_store.Settings()


@pytest.fixture
def profiles(isolated_store):
    p = isolated_store.Profiles()
    p.add("ShadowK", "Thief", "Assassin", 31)
    return p


@pytest.fixture(autouse=True)
def _dark_look():
    """Every test starts and ends on today's dark glass, whatever look a test picked (npcoverlay's module state)."""
    from maplehelper.ui import npcoverlay
    npcoverlay.apply_look(None)
    yield
    npcoverlay.apply_look(None)


class Scanner(QObject):
    """The loot scanner as the window reads it: the active character's log (None: no run yet) and its changes."""

    changed = Signal()

    def __init__(self, lg=None):
        super().__init__()
        self.lg = lg
        self.held = False           # the player paused the run

    def cid(self) -> str:
        return "c1"

    def log_for(self, cid: str):
        return self.lg

    def running(self, cid: str) -> bool:
        return self.lg is not None and self.lg.ended is None

    def paused(self) -> bool:
        return self.held


HAVE = {("level", 35): (31, False, 4 * 3600), ("item", 5): (2, False, 600), ("mesos", 1_000_000): (1_000_000, True, 0.0)}


def run_now(goals, **changes):
    """A run on Henesys Hunting Ground I as grindlive.live says it: a death warned of, a better map for the level,
    each goal at HAVE's progress."""
    progress = [grindlive.GoalProgress(goal=g, have=HAVE.get((g.kind, g.target), (0, False, None))[0],
                                       done=HAVE.get((g.kind, g.target), (0, False, None))[1],
                                       eta_s=HAVE.get((g.kind, g.target), (0, False, None))[2]) for g in goals]
    live = dict(running=True, state="running", map_id=HG1, map_name="Henesys Hunting Ground I", wall_s=2520,
                session=grindlive.Rates(exp_h=52_340, mesos_h=8_120, loot_h=3_460, potions_h=1_240, profit_h=10_340,
                                        active_s=2280),
                recent=grindlive.Rates(exp_h=61_020, mesos_h=9_400, loot_h=4_100, potions_h=1_100, profit_h=12_400,
                                       active_s=300),
                level=31, exp_pct=42.51, to_level_s=3900, last_drop=None, warnings=[("gl_warn_died", {"n": 2})],
                deaths=2, potions=42, potion_cost=6_300, level_ups=[(NOON, 31)], goals=progress,
                move_on=grindlive.Spot(map_id=HG2, map_name="Henesys Hunting Ground II", active_s=5400, exp_h=79_500,
                                       profit_h=12_100, sessions=3))
    return grindlive.Live(**{**live, **changes})


RUN = grindlive.Summary(log_id=12, start=NOON, end=NOON + 4500, active_s=4200, exp=312_400, mesos=48_200, loot=41_300,
                        potion_cost=5_200, profit=84_300, levels=(30, 31), deaths=1,
                        maps=[(HG1, "Henesys Hunting Ground I", 2880), (HG2, "Henesys Hunting Ground II", 1320)],
                        top_drops=[(POTION, "Red Potion", 84)], exp_h=267_771, profit_h=72_257)
OLDER = grindlive.Summary(log_id=11, start=YESTERDAY, end=YESTERDAY + 2400, active_s=2200, exp=151_000, mesos=22_000,
                          loot=18_400, potion_cost=3_100, profit=37_300, levels=(30, 30), deaths=0,
                          maps=[(HG2, "Henesys Hunting Ground II", 2200)], top_drops=[], exp_h=247_090, profit_h=61_036)


@pytest.fixture
def grind(monkeypatch):
    """grindlive's answers, set by each test: the run (a function of the goals; None: the real live(), which with no
    log says "stopped" and zeros) and the three lists."""
    data = SimpleNamespace(run=None, drops=[], spots=[], history=[])
    real = grindlive.live

    def live(kb, lg, character, goals, now=None):
        return data.run(goals) if lg is not None and data.run is not None else real(kb, lg, character, goals, now)
    monkeypatch.setattr(grindlive, "live", live)
    monkeypatch.setattr(grindlive, "drop_rates", lambda kb, cid: list(data.drops))
    monkeypatch.setattr(grindlive, "best_spots", lambda kb, cid, level: list(data.spots))
    monkeypatch.setattr(grindlive, "history", lambda kb, cid, limit=30: list(data.history))
    return data


@pytest.fixture
def make(qapp, kb, settings, profiles, grind):
    """make(lg, lang): a window over a scanner whose log is lg (a running one by default), torn down after."""
    made = []

    def build(lg="running", lang="en"):
        from maplehelper.ui.grindwindow import GrindWindow
        scanner = Scanner(lootlog.Log(start=time.time() - 2520) if lg == "running" else lg)
        w = GrindWindow(kb, settings, profiles, scanner, I18n(lang))
        made.append(w)
        return w, scanner
    yield build
    for w in made:
        for timer in (w._clock, w._reread, w._searching, w._geom):
            timer.stop()
        w.hide()
        w.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def win(make, grind):
    grind.run = run_now
    return make()[0]


def settle() -> None:
    """Widgets added to a window that shows already show on the loop's next turn (Qt queues it): that turn now."""
    QApplication.processEvents()


def spaced(text: str) -> str:
    """A label's text as read: its no-break spaces as plain ones, and in Hebrew without the direction marks around its
    English blocks and around a button's words (bidi.button)."""
    for mark in ("\u200f", "\u2066", "\u2067", "\u2069", "\u202a", "\u202c", "\u2060"):
        text = text.replace(mark, "")
    return text.replace("\u00a0", " ")


def shown(parent, cls, name: str) -> list:
    settle()
    return [w for w in parent.findChildren(cls, name) if w.isVisibleTo(parent)]


def texts(parent, name: str) -> list[str]:
    return [spaced(w.text()) for w in shown(parent, QLabel, name)]


def clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


# ---------------------------------------------------------------- Now

def test_the_now_tab_draws_the_live_run(qapp, win, settings, grind):
    win.open_tab("now")
    settle()
    assert win.isVisible() and settings["grind_window"] is True
    assert spaced(win._map_name.text()) == "Henesys Hunting Ground I"
    assert spaced(win._times.text()) == "42 min · 38 min active"
    assert spaced(win._state.text()) == "\u25cf Grinding" and win._state.property("state") == "running"
    tiles = {k: (spaced(t.name.text()), spaced(t.value.text()), spaced(t.sub.text())) for k, t in win._tiles.items()}
    assert tiles == {"exp": ("EXP / hour", "52,340", "Last 5 min: 61,020"),
                     "profit": ("Profit / hour", "10,340", "Last 5 min: 12,400")}
    assert win._tiles["exp"].width() == win._tiles["profit"].width()      # the two share the row
    assert spaced(win._profit_line.text()) == "Per hour: 8,120 mesos + 3,460 loot \u2212 1,240 potions"
    assert spaced(win._level_text.text()) == "Lv. 31 · 42.51%" and win._level_bar.frac() == pytest.approx(0.4251)
    assert spaced(win._to_level.text()) == "Next level in about 1:05 h"
    assert spaced(win._level_up.text()) == "\u25b2 Lv. 31"
    assert texts(win._warn_card, "Caption") == ["THIS MAP"]
    assert texts(win._warn_card, "Warn") == [EN("gl_warn_died", n=2)]        # grindlive's warning, in words
    assert spaced(win._toll.text()) == "Died 2 times · 42 potions (6,300 mesos)"
    # the better map is weighed against the last minutes here, as grindlive picks it
    assert spaced(win._move_text.text()) == ("Henesys Hunting Ground II fits your level and gave you +30% EXP/hr "
                                             "(79,500/h).")
    # a pickup: the numbers again at once
    grind.run = lambda goals: run_now(goals, session=grindlive.Rates(exp_h=60_000, active_s=2400), warnings=[])
    win._scanner.changed.emit()
    assert spaced(win._tiles["exp"].value.text()) == "60,000"
    assert not win._profit_line.isVisibleTo(win)            # no profit rate yet: nothing to spell out
    assert not win._warn_card.isVisibleTo(win)              # no warning: no map card


def test_a_paused_or_ended_run_says_so(qapp, win, grind):
    grind.run = lambda goals: run_now(goals, state="paused")
    win.open_tab("now")
    assert spaced(win._state.text()) == "Paused" and win._state.property("state") == "paused"
    assert "120" not in win._state.toolTip() and "2 minutes" in win._state.toolTip()        # no EXP for a while
    win._scanner.held = True
    win._scanner.changed.emit()
    assert win._state.toolTip() == EN("gw_paused_manual_tip")
    grind.run = lambda goals: run_now(goals, state="stopped", running=False)
    win._scanner.changed.emit()
    assert spaced(win._state.text()) == "\u25a0 Stopped" and win._state.toolTip() == EN("gw_stopped_tip")


def test_without_a_run_the_now_tab_says_how_to_start_one(qapp, make, grind):
    w, scanner = make(lg=None)
    w.open_tab("now")
    settle()
    assert w._now_empty.isVisibleTo(w) and not w._run_box.isVisibleTo(w)
    assert spaced(w._now_empty.title.text()) == "No run yet"
    hint = spaced(w._now_empty.hint.text())
    assert "Loot Log" in hint and "grind bar" in hint and "kill" in hint
    assert w._goals_head.isVisibleTo(w) and w._add_btn.isVisibleTo(w)      # goals are set before a run too
    scanner.lg = lootlog.Log(start=time.time() - 60)                      # a run starts
    grind.run = run_now
    scanner.changed.emit()
    assert not w._now_empty.isVisibleTo(w) and w._run_box.isVisibleTo(w)


def test_show_the_way_asks_for_the_map(qapp, win, grind):
    asked = []
    win.route_requested.connect(asked.append)
    win.open_tab("now")
    win._move_btn.click()
    assert asked == [HG2]
    grind.spots = [grindlive.Spot(map_id=HG2, map_name="Henesys Hunting Ground II", active_s=5400, exp_h=79_500,
                                  profit_h=12_100, sessions=3),
                   grindlive.Spot(map_id=HG1, map_name="Henesys Hunting Ground I", active_s=2700, exp_h=52_340,
                                  profit_h=10_340, sessions=1)]
    win.open_tab("spots")
    cards = shown(win._pages["spots"], QFrame, "Line")
    shown(cards[1], QPushButton, "Act")[0].click()
    assert asked == [HG2, HG1]


# ---------------------------------------------------------------- the lists

def test_the_drops_tab_lists_the_rates_and_says_what_to_do_without_any(qapp, win, grind):
    grind.drops = [grindlive.DropRate(item_key=POTION, item="Red Potion", count=84, active_s=16_200, per_h=18.67,
                                      monsters=[SNAIL]),
                   grindlive.DropRate(item_key="item/8", item="Blue Snail Shell", count=3, active_s=2_571, per_h=4.2,
                                      monsters=[BLUE]),
                   grindlive.DropRate(item_key="item/9", item="Snail Shell", count=1, active_s=420, per_h=None,
                                      monsters=[SNAIL, BLUE, "monster/130101", "monster/1210100"])]
    win.open_tab("now")
    win._tabs.group.buttons()[1].click()                  # the Drops tab
    assert win._tab == "drops" and win._pages["drops"].isVisibleTo(win) and not win._pages["now"].isVisibleTo(win)
    assert texts(win._pages["drops"], "Note") == [("How many of each item you pick up an hour, from all of this "
                                                   "character's runs.")]
    first, second, third = shown(win._pages["drops"], QFrame, "Line")
    assert texts(first, "Name") == ["Red Potion"] and texts(first, "Rate") == ["19 per hour"]     # whole above 10
    assert shown(first, QLabel, "Rate")[0].toolTip() == EN("gw_drop_per_h_tip")
    assert texts(first, "Sub") == ["84 picked up in 4:30 h", "from Snail"]
    assert texts(second, "Rate") == ["4.2 per hour"] and texts(second, "Sub") == ["3 picked up in 42 min",
                                                                                   "from Blue Snail"]
    assert texts(third, "RateNone") == ["Not enough time yet"] and not texts(third, "Rate")
    assert texts(third, "Sub") == ["1 picked up in 7 min", f"from Snail, Blue Snail, Red Snail {EN('lk_more', n=1)}"]
    grind.drops = []
    win.open_tab("drops")                                   # read again: none now
    assert not shown(win._pages["drops"], QFrame, "Line")
    assert texts(win._pages["drops"], "EmptyTitle") == ["No drops yet"]
    assert "Loot Log" in texts(win._pages["drops"], "EmptyHint")[0]


def test_the_best_spots_tab_lights_the_best_and_says_what_to_do_without_any(qapp, win, grind):
    grind.spots = [grindlive.Spot(map_id=HG2, map_name="Henesys Hunting Ground II", active_s=5400, exp_h=79_500,
                                  profit_h=12_100, sessions=3),
                   grindlive.Spot(map_id=HG1, map_name="Henesys Hunting Ground I", active_s=2700, exp_h=52_340,
                                  profit_h=10_340, sessions=1)]
    win.open_tab("spots")
    best, other = shown(win._pages["spots"], QFrame, "Line")
    assert best.property("best") is True and other.property("best") is False
    assert texts(best, "LitCaption") == ["BEST FOR YOU"] and not texts(other, "LitCaption")
    assert texts(best, "Name") == ["Henesys Hunting Ground II"]
    assert (texts(best, "Num_exp"), texts(best, "Num_profit")) == (["79,500"], ["12,100"])
    assert texts(best, "Unit") == ["EXP / hr", "Profit / hr"]
    assert texts(best, "Sub") == ["1:30 h over 3 runs"] and texts(other, "Sub") == ["45 min in 1 run"]
    grind.spots = []
    win.open_tab("spots")
    assert texts(win._pages["spots"], "EmptyTitle") == ["No spots yet"]


def test_a_history_row_opens_its_summary_and_back_returns(qapp, win, grind):
    from PySide6.QtTest import QTest
    grind.history = [RUN, OLDER]
    win.open_tab("history")
    rows = shown(win._pages["history"], QFrame, "Row")
    assert [texts(r, "Name")[0] for r in rows] == [f"Today · {clock(NOON)}\u2013{clock(NOON + 4500)}",
                                                   f"Yesterday · {clock(YESTERDAY)}\u2013{clock(YESTERDAY + 2400)}"]
    assert texts(rows[0], "Count") == ["1:10 h"]
    assert texts(rows[0], "Sub") == ["Henesys Hunting Ground I, Henesys Hunting Ground II"]
    chips = [texts(rows[0], n) for n in ("Chip_exp", "Chip_profit", "Chip")]
    assert chips == [["312.4K EXP"], ["84,300 profit"], ["Lv. 30 \u2192 31"]]
    assert texts(rows[1], "Chip") == ["Lv. 30"]
    QTest.mouseClick(rows[0], Qt.LeftButton)
    settle()
    assert win._sum_page.isVisibleTo(win) and not win._pages["history"].isVisibleTo(win)
    assert win._back.isVisibleTo(win) and not win._tabs.isVisibleTo(win)
    assert texts(win._sum_page, "MapName") == [f"Today · {clock(NOON)}\u2013{clock(NOON + 4500)}"]
    win._back.click()
    settle()
    assert win._pages["history"].isVisibleTo(win) and win._tabs.isVisibleTo(win) and not win._back.isVisibleTo(win)
    assert win._tabs.value() == "history"
    grind.history = []
    win.open_tab("history")
    assert texts(win._pages["history"], "EmptyTitle") == ["No runs yet"]


def test_show_summary_opens_the_window_on_the_runs_card(qapp, win, settings):
    assert settings["grind_window"] is False and not win.isVisible()
    win.show_summary(RUN)                       # the bar, as a run ends
    settle()
    page = win._sum_page
    assert win.isVisible() and settings["grind_window"] is True and page.isVisibleTo(win)
    assert texts(page, "Caption") == ["RUN SUMMARY"]
    assert texts(page, "Sub")[0] == "1:10 h active · Lv. 30 \u2192 31 · Died once"
    assert texts(page, "TileName_exp") + texts(page, "TileName_profit") == ["EXP", "Profit"]
    assert texts(page, "TileValue") == ["312.4K", "84,300"]
    assert texts(page, "TileSub") == ["267.8K/h", "72,257/h"]
    assert texts(page, "Sub")[1] == "48,200 mesos + 41,300 loot \u2212 5,200 potions"
    lines = shown(page, QFrame, "Line")
    assert [(texts(r, "Name"), texts(r, "Count")) for r in lines] == [
        (["Henesys Hunting Ground I"], ["48 min"]), (["Henesys Hunting Ground II"], ["22 min"]),
        (["Red Potion"], ["\u00d784"])]
    # a picture on every row (here the KB's icon for its kind: the tiny KB has no sprites; the real one's below)
    assert all(not r.findChildren(QLabel)[0].pixmap().isNull() for r in lines)
    assert texts(page, "Head") == ["MAPS", "TOP DROPS"]
    win._back.click()
    settle()
    assert win._pages["now"].isVisibleTo(win) and not page.isVisibleTo(win)     # back on the tab it was on
    win.show_summary(OLDER)
    assert texts(win._sum_page, "Note") == ["No items picked up this run."]


# ---------------------------------------------------------------- goals

def test_goals_are_added_and_removed_in_the_settings(qapp, win, settings):
    from PySide6.QtTest import QTest

    from maplehelper.ui.grindwindow import TYPE_DEBOUNCE_MS
    win.open_tab("now")
    assert settings["grind_goals"] == [] and win._goals_none.isVisibleTo(win)
    assert not win._add_btn.isEnabled()
    win._num_box.setText("1")                     # level 1 is no goal
    assert not win._add_btn.isEnabled()
    win._num_box.setText("35")
    win._add_btn.click()
    assert settings["grind_goals"] == [grindlive.Goal("level", 35).to_json()]
    assert win._num_box.text() == "" and not win._goals_none.isVisibleTo(win)
    # an item: searched among the KB's items, picked from its row
    win._kinds.group.buttons()[1].click()
    assert win._item_box.isVisibleTo(win)
    win._num_box.setText("5")
    assert not win._add_btn.isEnabled()           # no item picked yet
    QTest.keyClicks(win._item_box, "red")
    QTest.qWait(TYPE_DEBOUNCE_MS + 100)
    assert [texts(r, "Name") for r in win._pick_rows] == [["Red Potion"]]
    QTest.mouseClick(win._pick_rows[0], Qt.LeftButton)
    assert win._item_box.text() == "Red Potion" and not win._pick_rows and win._add_btn.isEnabled()
    win._add_btn.click()
    assert settings["grind_goals"][1] == grindlive.Goal("item", 5, POTION, "Red Potion").to_json()
    # mesos
    win._kinds.group.buttons()[2].click()
    assert not win._item_box.isVisibleTo(win)
    win._num_box.setText("1,000,000")
    win._add_btn.click()
    assert settings["grind_goals"][2] == grindlive.Goal("mesos", 1_000_000).to_json()
    rows = shown(win, QFrame, "GoalRow")
    assert [spaced(r.title.text()) for r in rows] == ["Reach Lv. 35", "Collect 5 Red Potion", "Make 1,000,000 mesos"]
    assert [spaced(r.sub.text()) for r in rows] == ["Lv. 31 / 35 · about 4:00 h to go", "2 / 5 · about 10 min to go",
                                                    "1.00M / 1.00M · Done!"]
    assert [r.property("done") for r in rows] == [False, False, True] and rows[2].bar.frac() == 1.0
    assert rows[1].bar.frac() == pytest.approx(2 / 5)
    # ✕ drops one
    rows[1].remove.click()
    assert settings["grind_goals"] == [grindlive.Goal("level", 35).to_json(),
                                       grindlive.Goal("mesos", 1_000_000).to_json()]
    assert [spaced(r.title.text()) for r in shown(win, QFrame, "GoalRow")] == ["Reach Lv. 35", "Make 1,000,000 mesos"]


def test_a_goals_box_takes_the_keyboard_only_while_typed_in(qapp, win):
    from PySide6.QtTest import QTest
    win.open_tab("now")
    assert win.windowFlags() & Qt.WindowDoesNotAcceptFocus                # clicks on the window leave the game's
    QTest.mouseClick(win._num_box, Qt.LeftButton)
    assert win._typing and not win.windowFlags() & Qt.WindowDoesNotAcceptFocus
    QTest.keyClick(win._num_box, Qt.Key_Escape)                           # Esc: back to the game
    assert not win._typing and win.windowFlags() & Qt.WindowDoesNotAcceptFocus


# ---------------------------------------------------------------- the window

def test_it_follows_its_setting_and_its_x_turns_it_off(qapp, win, settings):
    win.refresh()
    assert not win.isVisible()
    settings["grind_window"] = True
    win.refresh()
    assert win.isVisible() and win._clock.isActive()
    closed = []
    win.closed.connect(lambda: closed.append(True))
    win._close.click()
    assert settings["grind_window"] is False and not win.isVisible() and closed == [True]
    assert not win._clock.isActive()
    assert set(settings["grind_window_geom"]) == {"x", "y", "w", "h"}        # its place kept as it hid


def test_hebrew_mirrors_the_window(qapp, win, grind):
    win.open_tab("now")
    settle()
    assert win._tiles["exp"].x() < win._tiles["profit"].x()
    win.apply_language(I18n("he"))
    settle()
    assert win.layoutDirection() == Qt.RightToLeft
    assert spaced(win._title.text()) == STRINGS["gw_title"]["he"]
    assert spaced(win._tiles["exp"].name.text()) == STRINGS["gw_tile_exp"]["he"]
    assert win._tiles["exp"].x() > win._tiles["profit"].x()             # EXP first, on the right
    tabs = win._tabs.group.buttons()
    assert [spaced(b.text()) for b in tabs] == [STRINGS[f"gw_tab_{k}"]["he"] for k in ("now", "drops", "spots",
                                                                                     "history")]
    assert tabs[0].x() > tabs[3].x()
    assert win._tiles["exp"].width() == win._tiles["profit"].width()
    grind.drops = [grindlive.DropRate(item_key=POTION, item="Red Potion", count=84, active_s=16_200, per_h=4.2,
                                      monsters=[SNAIL])]
    win.open_tab("drops")
    line = shown(win._pages["drops"], QFrame, "Line")[0]
    rate = shown(line, QLabel, "Rate")[0]
    assert spaced(rate.text()) == "4.2 לשעה" and "\u20664.2\u2069" in rate.text()   # its figure one LTR block
    assert rate.x() < shown(line, QLabel, "Pic")[0].x()                 # the picture on the right, the rate left
    assert texts(line, "RateNone") == []
    win.open_tab("now")
    assert "Henesys Hunting Ground I" in spaced(win._map_name.text())    # the KB's English name, whole


def test_the_white_glass_takes_the_light_palette_and_back(qapp, win, settings):
    from maplehelper.ui import grindwindow, npcoverlay
    win.open_tab("now")
    assert f"color: {npcoverlay.DARK.text};" in win.styleSheet()
    settings["overlay_tint"] = "white"
    npcoverlay.apply_look(settings)
    win.refresh()                                       # the app's restyle on a look pick
    sheet = win.styleSheet()
    assert f"color: {npcoverlay.LIGHT.text};" in sheet and npcoverlay.DARK.text not in sheet
    assert npcoverlay.DARK.muted not in sheet and "rgba(255,255,255" not in sheet
    exp = grindwindow.COLORS["exp"]
    assert f"color: {npcoverlay.ink(exp)};" in sheet and f"color: {exp};" not in sheet      # darkened to read on white
    settings["overlay_tint"] = "dark"
    npcoverlay.apply_look(settings)
    win.refresh()
    sheet = win.styleSheet()
    assert f"color: {npcoverlay.DARK.text};" in sheet and npcoverlay.LIGHT.text not in sheet
    assert f"color: {exp};" in sheet


@needs_kb
def test_the_rows_show_the_kbs_own_pictures(qapp, settings, profiles, grind):
    """Ant Tunnel I in the real KB: the run's minimap, each drop's picture, a spot's minimap, and the summary's maps
    and drops — each the KB's own picture (shown large on hover)."""
    from maplehelper.kb import KnowledgeBase
    from maplehelper.ui.grindwindow import GrindWindow
    real = KnowledgeBase(REAL_KB)
    tunnel, horny, cap = "010005060", "monster/19", "item/366"
    uri = lambda key: real.image_path(key).resolve().as_uri()      # the file a picture's hover shows
    grind.run = lambda goals: run_now(goals, map_id=tunnel, map_name="Ant Tunnel I", move_on=None)
    grind.drops = [grindlive.DropRate(item_key=cap, item="Horny Mushroom Cap", count=84, active_s=16_200, per_h=18.67,
                                      monsters=[horny])]
    grind.spots = [grindlive.Spot(map_id=tunnel, map_name="Ant Tunnel I", active_s=5400, exp_h=52_340,
                                  profit_h=10_340, sessions=3)]
    w = GrindWindow(real, settings, profiles, Scanner(lootlog.Log(start=time.time() - 600)), I18n("en"))
    try:
        w.open_tab("now")
        assert uri(f"map/{tunnel}") in w._map_pic.toolTip() and not w._map_pic.pixmap().isNull()
        w.open_tab("drops")
        assert uri(cap) in shown(w._pages["drops"], QLabel, "Pic")[0].toolTip()
        w.open_tab("spots")
        assert uri(f"map/{tunnel}") in shown(w._pages["spots"], QLabel, "MapPic")[0].toolTip()
        w.show_summary(grindlive.Summary(log_id=1, start=NOON, end=NOON + 900, active_s=900, exp=40_000, mesos=6_000,
                                         loot=2_000, potion_cost=500, profit=7_500, levels=(31, 31),
                                         deaths=0, maps=[(tunnel, "Ant Tunnel I", 900)],
                                         top_drops=[(cap, "Horny Mushroom Cap", 12)], exp_h=160_000, profit_h=30_000))
        tips = [p.toolTip() for p in shown(w._sum_page, QLabel, "MapPic") + shown(w._sum_page, QLabel, "Pic")]
        assert uri(f"map/{tunnel}") in tips[0] and uri(cap) in tips[1]
    finally:
        for timer in (w._clock, w._reread, w._searching, w._geom):
            timer.stop()
        w.hide()
        w.deleteLater()
        qapp.processEvents()
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)
