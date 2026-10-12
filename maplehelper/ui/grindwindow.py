"""The grind window over the game: the live grind run, measured on this computer, in detail (a click on the grind bar
opens it, ui/grindbar.py; the run is the Loot Log's own, ui/lootscan.py). Four tabs and a run's summary, each read top
to bottom:

- Now: the run's map and state; its EXP and profit per hour big (the whole run's rate, the last 5 minutes' under
  each), the profit spelled out (mesos + loot − potions); the level's progress and the time to the next; grindlive's
  warnings about the map; deaths and potions; a map the player's own runs say pays more for their level (Show the
  way); then the goals, each with its progress bar and when it is reached, a ✕ to drop it, and a card to add one (a
  level, an item searched among the KB's, or an amount of mesos).
- Drops: every item this character picked up, how many come an hour ("4.2 per hour", or not enough time yet), how
  many in how long, and from which monsters.
- Best spots: the maps that paid this character best for their level (EXP and profit per hour, the time spent there,
  in how many runs), each with Show the way.
- History: the runs this character made, newest first; a click opens one's summary.
- A run's summary (show_summary: the bar opens it when a run ends): its time, levels, EXP, mesos, loot, potions,
  profit, the per-hour figures, deaths, the maps with their time and the top drops with their pictures; Back returns
  to the tabs.

Every number is grindlive's, worked out from what this computer read (the pickup messages, the HUD) and the KB's
tables: nothing is guessed here, and a tab with nothing to show yet says what to do. Built like the other windows over
the game (the gear advisor, the scroll planner): the NPCs window's glass in the tint, accent and opacity the ⚙ panel
picks, the title row that drags it, its place kept in grind_window_geom, its ✕ turning grind_window off. It never
takes the keyboard from the game, only while the player types in a new goal's boxes (Esc, Enter or Add gives it
back)."""
from __future__ import annotations

import datetime
import time

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QRegularExpression, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from .. import bidi, dates, grindlive, plan
from ..i18n import NBSP, I18n
from ..kb import KnowledgeBase
from ..store import Profiles, Settings
from . import mapview, theme
from .controls import FlowLayout, Segmented
from .gamesearch import glass_qss, rim
from .gamesearch import search as find_items
from .glass import SHADOW, EdgeResize
from .grindbar import per_hour
from .lookpick import line_icon
from .lootoverlay import DOT, SQUARE, STAT_COLORS, _elapsed, _Fit, _glyph
from .npcoverlay import (BOTTOM, GEOM_DEBOUNCE_MS, KEYS_CHECK_MS, OPACITY_DEFAULT, OPACITY_MAX, OPACITY_MIN, SIDE,
                         SYMBOL_FONT, TOP, _accept_keys, _flags, _foreground, _Header, _paint_glass, _to_foreground,
                         accent_of, ink, palette, set_capturable)
from .npcoverlay import keep_over_game
from .scrollplanner import _Body
from .widgets import fit_picture, zoom_on_hover

SHOW_KEY, GEOM_KEY, GOALS_KEY = "grind_window", "grind_window_geom", "grind_goals"
TABS = ("now", "drops", "spots", "history")
MIN_W, MIN_H = 380, 440             # the smallest the player can drag the window to (the four tabs still fit)
DEFAULT_W, DEFAULT_H = 440, 680     # what opens before it is ever resized
GAP = 8                             # between the bar and the window that opens under it
TICK_MS = 1000                      # the Now tab read again every second while it shows (the clock, the rates)
REREAD_MS = 2000                    # pickups while a list tab shows: its rows read again once they pause this long
TYPE_DEBOUNCE_MS = 150              # a pause in the item search's typing before its rows are read
GUTTER = 4                          # between the cards and the scrollbar
PICK_ROWS = 6                       # items the new goal's item search lists
MONSTERS_SHOWN = 3                  # a drop's monsters named before "and N more"
RATE_NONE_W = 72                    # "Not enough time yet" on a drop's end: two short lines, the monsters keep the room
MAPS_SHOWN = 3                      # a history row's maps named before "and N more"
MAP_PIC = (52, 38)                  # a map's minimap (most are wider than tall): the run's card, a spot's
ROW_MAP = (40, 30)                  # ... a history row's, a summary's maps
ROW_PIC, PICK_PIC = 30, 24          # an item's picture: a drop's, a search row's
GOAL_PIC, GLYPH = 24, 18            # a goal's icon: its item's picture, or the EXP's sparkle (a level), the mesos' coin
VALUE_PX, VALUE_MIN_PX = 20, 12     # a tile's big number, stepped down to fit its tile
LEVEL_MAX = 200                     # the highest level a goal can name
# each figure in a colour of its own, in its tile, a spot's numbers and a run's chips: the Loot Log's EXP blue, profit
# a gain's green — readable on every dark glass tint, darkened by ink() on the white one
COLORS = {"exp": STAT_COLORS["exp"], "profit": "#4CD07D"}
GAIN, LOSS, WARN = "#4CD07D", "#FF8A80", "#FFB066"
STATES = ("running", "paused", "dead", "stopped")
STATE_COLORS = {"paused": WARN, "dead": LOSS}       # running lights in the accent, stopped is muted
WARN_MARK, UP = "\u26a0\ufe0e", "\u25b2"
# what an empty tab's card shows in its circle (U+FE0E: the plain glyph, not the colour emoji)
EMPTY_ICONS = {"now": "\u2694\ufe0e", "drops": "\U0001F48E\ufe0e", "spots": "\U0001F5FA\ufe0e",
               "history": "\u231b\ufe0e"}


def _rgba(color: str, alpha: float) -> str:
    """A colour ("#RRGGBB" or "rgba(...)") at this opacity, for a tinted fill."""
    c = theme.qcolor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def qss(settings) -> str:
    """The window's own style at the accent the settings pick (npcoverlay.ACCENTS), in the palette of the glass under
    it (npcoverlay.palette(): dark text on the white glass; the figures' colours through ink): the lit tab, the run's
    state, the move-on card, the best spot, Show the way and Add; the glass itself is painted in the tint by
    _paint_glass. Built again whenever the look is picked, so the window follows with no code of its own."""
    p = palette()
    fill, on_fill = accent_of(settings)
    lit, gain = ink(fill), ink(GAIN)
    chip = "border-radius: 6px; padding: 1px 6px; font-size: 11px; font-weight: 700;"
    figures = "".join(
        f"QFrame#Tile_{k} {{ background: {_rgba(c, 0.12)}; border: 1px solid {_rgba(ink(c), 0.26)};"
        f" border-radius: 10px; }}\n"
        f"#TileName_{k} {{ color: {ink(c)}; font-size: 11px; font-weight: 700; }}\n"
        f"#Num_{k} {{ color: {ink(c)}; font-size: 14px; font-weight: 700; }}\n"
        f"QLabel#Chip_{k} {{ color: {ink(c)}; background: {_rgba(ink(c), 0.15)}; {chip} }}\n"
        for k, c in COLORS.items())
    states = "".join(
        f'QLabel#State[state="{s}"] {{ color: {ink(c)}; background: {_rgba(c, 0.16)};'
        f' border: 1px solid {_rgba(c, 0.5)}; }}\n'
        for s, c in (("running", fill), *STATE_COLORS.items()))
    return glass_qss(p) + f"""
QLabel {{ background: transparent; }}
#Segmented {{ background: {p.fill1}; border: none; border-radius: 10px; }}
QPushButton#Segment {{ background: transparent; color: {p.muted}; border: none; border-radius: 8px; min-height: 26px;
                       max-height: 26px; padding: 0 8px; font-size: 12px; font-weight: 600; text-align: center; }}
QPushButton#Segment:hover:!checked {{ background: {p.fill2}; color: {p.text}; }}
QPushButton#Segment:checked {{ background: {fill}; color: {on_fill}; font-weight: 700; }}
QFrame#AddCard QPushButton#Segment {{ min-height: 22px; max-height: 22px; }}
QFrame#Card, QFrame#Line, QFrame#GoalRow {{ background: {p.fill1}; border: 1px solid transparent;
                                           border-radius: 12px; }}
QFrame#Line {{ border-radius: 10px; }}
QFrame#Card[lit="true"], QFrame#Line[best="true"] {{ background: {_rgba(fill, 0.10)}; border: 1px solid {fill}; }}
QFrame#GoalRow[done="true"] {{ border: 1px solid {_rgba(gain, 0.6)}; }}
QFrame#AddCard {{ background: transparent; border: 1px dashed {rim(0.28, p)}; border-radius: 12px; }}
QFrame#Row {{ border-radius: 10px; }}
QFrame#Empty {{ background: {p.fill1}; border-radius: 12px; }}
#EmptyIcon {{ color: {p.text}; background: {p.fill2}; border-radius: 18px; font-family: "{SYMBOL_FONT}";
             font-size: 18px; }}
#EmptyTitle {{ color: {p.text}; font-size: 14px; font-weight: 600; }}
#EmptyHint {{ color: {p.muted}; font-size: 12px; }}
#MapName {{ color: {p.text}; font-size: 15px; font-weight: 700; }}
#Name {{ color: {p.text}; font-size: 13px; font-weight: 600; }}
#Sub {{ color: {p.muted}; font-size: 12px; }}
#Text {{ color: {p.text}; font-size: 13px; }}
#Note {{ color: {p.muted}; font-size: 11px; }}
#Head {{ color: {p.muted}; font-size: 11px; font-weight: 700; padding: 2px 2px 0 2px; }}
#Caption {{ color: {p.muted}; font-size: 10px; font-weight: 700; }}
#LitCaption {{ color: {lit}; font-size: 10px; font-weight: 700; }}
#Warn {{ color: {ink(WARN)}; font-size: 12px; }}
#WarnMark {{ color: {ink(WARN)}; font-family: "{SYMBOL_FONT}"; font-size: 12px; }}
#Count {{ color: {p.text}; font-size: 13px; font-weight: 700; }}
#Unit {{ color: {p.muted}; font-size: 10px; font-weight: 600; }}
#Rate {{ color: {p.text}; font-size: 14px; font-weight: 700; }}
#RateNone {{ color: {p.muted}; font-size: 11px; }}
#Up {{ color: {lit}; background: {_rgba(fill, 0.16)}; {chip} }}
#Slot, #MapPic {{ background: {rim(0.06, p)}; border-radius: 6px; }}
{figures}#TileValue {{ color: {p.text}; font-size: {VALUE_PX}px; font-weight: 700; }}
#TileSub {{ color: {p.muted}; font-size: 11px; }}
QLabel#Chip {{ color: {p.text}; background: {rim(0.10, p)}; {chip} }}
QLabel#State {{ border-radius: 10px; padding: 1px 9px; font-size: 12px; font-weight: 700; }}
QLabel#State[state="stopped"] {{ color: {p.muted}; background: {p.fill1}; border: 1px solid {p.fill2}; }}
{states}QPushButton#Act {{ background: transparent; color: {lit}; border: 1px solid {fill}; border-radius: 7px;
                  padding: 3px 10px; font-size: 12px; font-weight: 700; text-align: center; }}
QPushButton#Act:hover {{ background: {_rgba(fill, 0.18)}; }}
QPushButton#Act:disabled {{ color: {p.muted}; border: 1px solid {rim(0.18, p)}; }}
QToolButton#Remove {{ padding: 0 5px; font-size: 12px; }}
QLineEdit#Box {{ border: 1px solid transparent; padding: 5px 8px; }}
QLineEdit#Box:focus {{ border: 1px solid {fill}; }}
"""


# ---------------------------------------------------------------- words and numbers

def _short(n) -> str:
    """A figure as a tile says it: 12,345; 123.5K; 1.23M; with its sign when it is a loss; "–" while unknown."""
    if n is None:
        return "\u2013"
    n = round(n)
    if n < 0:
        return "-" + _short(-n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 100_000:
        return f"{n / 1000:.1f}K"
    return f"{n:,}"


def _block(text: str, rtl: bool) -> str:
    """A short English piece ("Ant Tunnel I", "52.3K", "14:05–15:17") that a line never wraps inside, and in Hebrew one
    left-to-right block (wrapped, its halves landed on two lines in mirrored order)."""
    return bidi.ltr_block(text.replace(" ", NBSP) if len(text) <= bidi.KEEP_TOGETHER else text, rtl)


def _pct(v: float) -> str:
    """The level's EXP as the game shows it: 42.51%."""
    return f"{v:.2f}%"


def _number(text: str) -> int | None:
    """A typed amount ("1,000,000" or "35"); None for anything else."""
    digits = str(text).replace(",", "").strip()
    return int(digits) if digits.isdigit() else None


def _day(t: I18n, ts: float) -> str:
    """Today, Yesterday, or the day (6.10 / Oct 6), as the grind tracker's recent sessions say it."""
    d = datetime.date.fromtimestamp(ts)
    today = datetime.date.today()
    if d == today:
        return t("grind_today")
    if d == today - datetime.timedelta(days=1):
        return t("grind_yesterday")
    return dates.day(d, t.rtl)


def _clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def _label(text: str, name: str, wrap: bool = False) -> QLabel:
    w = QLabel(text, objectName=name)
    w.setWordWrap(wrap)
    return w


def _clear(lay) -> None:
    """Every widget out of a layout (the layouts this file clears hold widgets and stretches only)."""
    while lay.count():
        w = lay.takeAt(0).widget()
        if w is not None:
            w.hide()            # gone now: deleteLater alone left the old rows drawn under the new ones
            w.deleteLater()


def _set_prop(w: QWidget, name: str, value) -> None:
    """A style property (the run's state, a goal reached), the widget re-polished only when it changed."""
    if w.property(name) != value:
        w.setProperty(name, value)
        w.style().unpolish(w)
        w.style().polish(w)


# ---------------------------------------------------------------- the pieces

class _Pictures:
    """Each picture (a monster's, an item's, a map's minimap: kb.picture) fitted once per box: the Now tab is filled
    every second, and each row would read its file from disk and scale it again."""

    def __init__(self, kb):
        self.kb = kb
        self._paths: dict[str, object] = {}
        self._fitted: dict[tuple, QPixmap] = {}

    def path(self, key: str):
        if key not in self._paths:
            self._paths[key] = self.kb.picture(key) if key else None
        return self._paths[key]

    def get(self, key: str, w: int, h: int, widget: QWidget) -> QPixmap:
        """The picture fitted into w x h at the widget's screen; a null pixmap without one."""
        path = self.path(key)
        if not path:
            return QPixmap()
        dpr = widget.devicePixelRatioF()
        pm = self._fitted.get((key, w, h, dpr))
        if pm is None:
            raw = QPixmap(str(path))
            pm = fit_picture(raw, w, h, widget, trim=True) if not raw.isNull() else QPixmap()
            self._fitted[(key, w, h, dpr)] = pm
        return pm

    def show(self, label: QLabel, key: str, w: int, h: int, caption: str = "", zoom: bool = True) -> None:
        """The picture into this label (none: the box stays empty), shown large on hover unless zoom is off (a row
        that clicks has a tooltip of its own)."""
        pm = self.get(key, w, h, label)
        label.setPixmap(pm)
        label.setToolTip("")
        if zoom and not pm.isNull():
            zoom_on_hover(label, self.path(key), caption)

    def label(self, key: str, w: int, h: int | None = None, caption: str = "", zoom: bool = True,
              name: str = "Pic") -> QLabel:
        """The picture in a fixed box: without one the box stays empty and the rows still line up."""
        h = w if h is None else h
        pic = QLabel(objectName=name, alignment=Qt.AlignCenter)
        pic.setFixedSize(w, h)
        self.show(pic, key, w, h, caption, zoom)
        return pic


class _Bar(QWidget):
    """A thin progress bar: the track in the glass's own fill, the done part in a colour of its own, filled from the
    reading end (the right, in Hebrew)."""

    def __init__(self, height: int):
        super().__init__()
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._frac, self._color = 0.0, GAIN

    def set(self, frac: float, color: str) -> None:
        frac = min(1.0, max(0.0, float(frac)))
        if (frac, color) != (self._frac, self._color):
            self._frac, self._color = frac, color
            self.update()

    def frac(self) -> float:
        return self._frac

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        rad = r.height() / 2
        p.setBrush(theme.qcolor(palette().fill2))      # read at paint: the white glass's track is dark
        p.drawRoundedRect(r, rad, rad)
        if self._frac > 0:
            w = max(r.height(), r.width() * self._frac)
            p.setBrush(QColor(self._color))
            p.drawRoundedRect(QRectF(r.right() - w if self.isRightToLeft() else r.left(), r.top(), w, r.height()),
                              rad, rad)
        p.end()


class _Tile(QFrame):
    """One big figure in its own colour (COLORS): its name, the number big (stepped down to fit its tile: the tiles
    share the width), the line under it."""

    def __init__(self, key: str):
        super().__init__(objectName=f"Tile_{key}")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)      # three equal tiles, whatever they say
        v = QVBoxLayout(self)
        v.setContentsMargins(9, 7, 9, 8)
        v.setSpacing(1)
        self.name = _Fit(f"TileName_{key}", 11, 9)
        self.value = _Fit("TileValue", VALUE_PX, VALUE_MIN_PX)
        self.sub = _Fit("TileSub", 11, 9)
        for w in (self.name, self.value, self.sub):
            v.addWidget(w)


class _Empty(QFrame):
    """What a tab says with nothing to show: an icon in its circle, a line in bold and what to do under it."""

    def __init__(self):
        super().__init__(objectName="Empty")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(12)
        self.icon = QLabel(objectName="EmptyIcon", alignment=Qt.AlignCenter)
        self.icon.setFixedSize(36, 36)
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        self.title = _label("", "EmptyTitle", wrap=True)
        self.hint = _label("", "EmptyHint", wrap=True)
        v.addWidget(self.title)
        v.addWidget(self.hint)
        h.addWidget(self.icon, 0, Qt.AlignTop)
        h.addLayout(v, 1)

    def say(self, icon: str, title: str, hint: str, rtl: bool) -> None:
        self.icon.setText(icon)
        self.title.setText(bidi.plain(title, rtl))
        self.hint.setText(bidi.plain(hint, rtl))


class _WarnRow(QWidget):
    """One of grindlive's warnings: its ⚠ in a label of its own, in the symbol font (inside a Hebrew line the mark
    fell back to no font and showed a box), and the sentence wrapped beside it."""

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        mark = QLabel(WARN_MARK, objectName="WarnMark", alignment=Qt.AlignCenter)
        self.text = _label("", "Warn", wrap=True)
        h.addWidget(mark, 0, Qt.AlignTop)
        h.addWidget(self.text, 1)


class _GoalRow(QFrame):
    """One goal: its icon (the item's picture, the EXP's sparkle for a level, the mesos' coin), what it is over its
    progress bar, how far and when it is reached under that, and a ✕ that drops it."""

    removed = Signal()

    def __init__(self, t: I18n):
        super().__init__(objectName="GoalRow")
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 7, 6, 8)
        h.setSpacing(9)
        self.icon = QLabel(objectName="Slot", alignment=Qt.AlignCenter)
        self.icon.setFixedSize(GOAL_PIC + 6, GOAL_PIC + 6)
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.title = _label("", "Name", wrap=True)
        self.bar = _Bar(6)
        self.sub = _label("", "Sub", wrap=True)
        v.addWidget(self.title)
        v.addWidget(self.bar)
        v.addWidget(self.sub)
        h.addWidget(self.icon, 0, Qt.AlignTop)
        h.addLayout(v, 1)
        self.remove = QToolButton(objectName="Remove", text=theme.SYMBOL_ICONS["close"])
        self.remove.setCursor(Qt.PointingHandCursor)
        self.remove.setFocusPolicy(Qt.NoFocus)
        self.remove.setToolTip(t("gw_goal_remove"))
        self.remove.setAccessibleName(t("gw_goal_remove"))
        self.remove.clicked.connect(lambda _=False: self.removed.emit())
        h.addWidget(self.remove, 0, Qt.AlignTop)


class _KeyBox(QLineEdit):
    """A new goal's box. Its window never takes the keyboard, so a click in here asks for it while the player types
    (wants_keys); Esc gives it back (done), Enter is the box's own (entered: add the goal, pick the first item)."""

    wants_keys = Signal()
    done = Signal()
    entered = Signal()

    def __init__(self):
        super().__init__(objectName="Box")
        self.setFocusPolicy(Qt.ClickFocus)          # never the focus a shown window hands its first box

    def mousePressEvent(self, e) -> None:
        self.wants_keys.emit()
        super().mousePressEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.done.emit()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.entered.emit()
        else:
            super().keyPressEvent(e)


class _Press(QFrame):
    """A row that clicks (a run in History, an item the goal's search found)."""

    clicked = Signal()

    def __init__(self, name: str):
        super().__init__(objectName=name)
        self.setAttribute(Qt.WA_Hover, True)          # its QSS :hover
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


# ---------------------------------------------------------------- the window

class GrindWindow(EdgeResize, QWidget):
    """The window itself: over the game, in the NPCs window's glass. Clicks work (the tabs, a run, Show the way; the
    edges resize it) but it never takes the keyboard from the game, only while the player types in a new goal's box.
    Shows while settings["grind_window"] is on; its place is kept in grind_window_geom. The Now tab is read again every
    second while it shows and on every pickup (scanner.changed); a list tab when it opens, and once pickups pause."""

    closed = Signal()               # the ✕ turned the setting off: the grind bar follows
    route_requested = Signal(str)   # a map id: show the way there (a spot's or the move-on hint's Show the way)

    def __init__(self, kb: KnowledgeBase, settings: Settings, profiles: Profiles, scanner, t: I18n):
        super().__init__(None, _flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)      # a picture's zoom while the game has the keyboard
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)          # hovering the rim shows the resize cursor
        self.setMinimumSize(MIN_W, MIN_H)
        self.resize(DEFAULT_W, DEFAULT_H)
        self.setWindowTitle("Maple Helper")
        self._kb, self._settings, self._profiles, self._scanner, self.t = kb, settings, profiles, scanner, t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self._pics = _Pictures(kb)
        self._tab = TABS[0]
        self._tabs: Segmented | None = None
        self._kinds: Segmented | None = None
        self._summary = None                  # the run whose summary shows (grindlive.Summary); None: the tabs
        self._live = None                     # the Now tab's last read (grindlive.Live)
        self._lists: dict[str, list] = {}     # each list tab's rows as drawn: drawn again only when they change
        self._map_key: str | None = None      # the map whose picture the run's card shows
        self._exp_needs: dict[int, int] | None = None    # the KB's EXP to the next level (plan.exp_table), read once
        self._warn_rows: list[_WarnRow] = []
        self._goal_rows: list[_GoalRow] = []
        self._goals_drawn: list | None = None   # the goals the rows were made for (made again when they change)
        self._goal_kind = "level"             # what the new goal is: "level" | "item" | "mesos"
        self._goal_item: tuple[str, str] | None = None   # (KB key, name) of the item picked for it
        self._pick_rows: list[_Press] = []
        self._move_to = ""                    # the move-on hint's map id
        self._typing = False                  # a goal's box has the keyboard (_take_keys)
        self._keys_from = 0                   # ... and the window that had it before, the game (_give_keys)
        self._opacity = OPACITY_DEFAULT
        self._placed = False                  # geometry applied at least once: there is a place to remember
        self._under: QRect | None = None      # the bar's rect, where the window first opens
        self._geom = QTimer(self, singleShot=True, interval=GEOM_DEBOUNCE_MS, timeout=self._remember)
        self._clock = QTimer(self, interval=TICK_MS, timeout=self._tick)
        self._reread = QTimer(self, singleShot=True, interval=REREAD_MS, timeout=self._fill_list)
        self._searching = QTimer(self, singleShot=True, interval=TYPE_DEBOUNCE_MS, timeout=self._fill_picks)
        self.setStyleSheet(qss(settings))
        self._build()
        self._retext()
        self._show_view()
        scanner.changed.connect(self._scanner_changed)

    # ------------------------------------------------------------ the panel

    def _build(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(SIDE, TOP, SIDE, BOTTOM)
        col.setSpacing(8)
        head = _Header()
        hrow = QHBoxLayout(head)
        hrow.setContentsMargins(0, 0, 0, 0)
        hrow.setSpacing(8)
        self._title = QLabel(objectName="Title")
        self._close = QToolButton(objectName="Close", text=theme.SYMBOL_ICONS["close"])
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.setFocusPolicy(Qt.NoFocus)
        self._close.clicked.connect(self._close_clicked)
        hrow.addWidget(self._title, 1)
        hrow.addWidget(self._close, 0, Qt.AlignTop)
        col.addWidget(head)
        # the tabs (made in _make_tabs: their words are the language's), or Back over a run's summary
        self._tabs_slot = QVBoxLayout()
        self._tabs_slot.setContentsMargins(0, 0, 0, 0)
        col.addLayout(self._tabs_slot)
        self._back = QPushButton(objectName="Back")
        self._back.setCursor(Qt.PointingHandCursor)
        self._back.setFocusPolicy(Qt.NoFocus)
        self._back.clicked.connect(lambda _=False: self._back_clicked())
        col.addWidget(self._back, 0, Qt.AlignLeft)
        self._scroll = QScrollArea(objectName="Body")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = _Body(objectName="Rows")
        self._body_lay = QVBoxLayout(body)
        self._body_lay.setSpacing(0)
        # one page per tab and the summary's, one shown at a time (a hidden page takes no room)
        self._pages: dict[str, QWidget] = {"now": self._build_now()}
        self._list_lays: dict[str, QVBoxLayout] = {}
        for tab in TABS[1:]:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            self._pages[tab], self._list_lays[tab] = page, lay
        self._sum_page = QWidget()
        self._sum_lay = QVBoxLayout(self._sum_page)
        self._sum_lay.setContentsMargins(0, 0, 0, 0)
        self._sum_lay.setSpacing(8)
        for page in (*self._pages.values(), self._sum_page):
            self._body_lay.addWidget(page)
        self._body_lay.addStretch(1)
        self._scroll.setWidget(body)
        col.addWidget(self._scroll, 1)

    def _build_now(self) -> QWidget:
        """The Now tab: the empty card (no run yet) or the run's sections, then the goals (shown either way)."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self._now_empty = _Empty()
        v.addWidget(self._now_empty)
        self._run_box = QWidget()
        r = QVBoxLayout(self._run_box)
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(10)
        # the run: its map's picture and name, how long it has gone, and its state on the end
        card = QFrame(objectName="Card")
        h = QHBoxLayout(card)
        h.setContentsMargins(10, 9, 10, 9)
        h.setSpacing(10)
        self._map_pic = QLabel(objectName="MapPic", alignment=Qt.AlignCenter)
        self._map_pic.setFixedSize(*MAP_PIC)
        h.addWidget(self._map_pic, 0, Qt.AlignVCenter)
        mid = QVBoxLayout()
        mid.setSpacing(2)
        self._map_name = _label("", "MapName", wrap=True)
        self._times = _label("", "Sub", wrap=True)
        mid.addWidget(self._map_name)
        mid.addWidget(self._times)
        h.addLayout(mid, 1)
        self._state = QLabel(objectName="State")
        h.addWidget(self._state, 0, Qt.AlignTop)
        r.addWidget(card)
        # the two big figures, then the profit spelled out
        tiles = QWidget()
        trow = QHBoxLayout(tiles)
        trow.setContentsMargins(0, 0, 0, 0)
        trow.setSpacing(6)
        self._tiles = {key: _Tile(key) for key in COLORS}
        for tile in self._tiles.values():
            trow.addWidget(tile, 1)
        r.addWidget(tiles)
        self._profit_line = _label("", "Sub", wrap=True)
        r.addWidget(self._profit_line)
        # the level: where it stands, its EXP bar, the time to the next
        level = QFrame(objectName="Card")
        lv = QVBoxLayout(level)
        lv.setContentsMargins(12, 9, 12, 10)
        lv.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        self._level_text = _label("", "Name", wrap=True)
        self._level_up = QLabel(objectName="Up")
        top.addWidget(self._level_text, 1)
        top.addWidget(self._level_up, 0, Qt.AlignVCenter)
        lv.addLayout(top)
        self._level_bar = _Bar(8)
        lv.addWidget(self._level_bar)
        self._to_level = _label("", "Sub", wrap=True)
        lv.addWidget(self._to_level)
        r.addWidget(level)
        # the map: grindlive's warnings about it (shown only with one)
        self._warn_card = QFrame(objectName="Card")
        f = QVBoxLayout(self._warn_card)
        f.setContentsMargins(12, 9, 12, 10)
        f.setSpacing(5)
        self._warn_head = _label("", "Caption")
        f.addWidget(self._warn_head)
        self._warn_lay = QVBoxLayout()
        self._warn_lay.setContentsMargins(0, 0, 0, 0)
        self._warn_lay.setSpacing(4)
        f.addLayout(self._warn_lay)
        r.addWidget(self._warn_card)
        # deaths and potions
        self._toll = _label("", "Sub", wrap=True)
        r.addWidget(self._toll)
        # the move-on hint, lit in the accent
        self._move_card = QFrame(objectName="Card")
        self._move_card.setProperty("lit", True)
        m = QVBoxLayout(self._move_card)
        m.setContentsMargins(12, 9, 12, 10)
        m.setSpacing(6)
        self._move_head = _label("", "LitCaption")
        self._move_text = _label("", "Text", wrap=True)
        self._move_btn = QPushButton(objectName="Act")
        self._move_btn.setCursor(Qt.PointingHandCursor)
        self._move_btn.setFocusPolicy(Qt.NoFocus)
        self._move_btn.clicked.connect(lambda _=False: self.route_requested.emit(self._move_to))
        m.addWidget(self._move_head)
        m.addWidget(self._move_text)
        m.addWidget(self._move_btn, 0, Qt.AlignLeft)        # the leading edge (mirrored in Hebrew)
        r.addWidget(self._move_card)
        v.addWidget(self._run_box)
        v.addWidget(self._build_goals())
        return page

    def _build_goals(self) -> QWidget:
        """The goals: their rows (made in _fill_goals), the line with none, and the card that adds one — what kind,
        for an item its search and the rows it found, how many, and Add."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)
        self._goals_head = _label("", "Head")
        v.addWidget(self._goals_head)
        self._goal_lay = QVBoxLayout()
        self._goal_lay.setContentsMargins(0, 0, 0, 0)
        self._goal_lay.setSpacing(6)
        v.addLayout(self._goal_lay)
        self._goals_none = _label("", "Note", wrap=True)
        v.addWidget(self._goals_none)
        add = QFrame(objectName="AddCard")
        a = QVBoxLayout(add)
        a.setContentsMargins(10, 8, 10, 10)
        a.setSpacing(7)
        self._add_head = _label("", "Caption")
        a.addWidget(self._add_head)
        self._kinds_slot = QVBoxLayout()
        self._kinds_slot.setContentsMargins(0, 0, 0, 0)
        a.addLayout(self._kinds_slot)
        self._item_box = _KeyBox()
        self._item_find = self._item_box.addAction(QIcon(), QLineEdit.LeadingPosition)
        self._item_box.wants_keys.connect(lambda: self._take_keys(self._item_box))
        self._item_box.done.connect(self._give_keys)
        self._item_box.entered.connect(self._pick_first)
        self._item_box.textEdited.connect(self._item_typed)
        a.addWidget(self._item_box)
        self._picks = QWidget()
        self._picks_lay = QVBoxLayout(self._picks)
        self._picks_lay.setContentsMargins(0, 0, 0, 0)
        self._picks_lay.setSpacing(3)
        a.addWidget(self._picks)
        self._picks_note = _label("", "Note", wrap=True)
        a.addWidget(self._picks_note)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._num_box = _KeyBox()
        self._num_box.setValidator(QRegularExpressionValidator(QRegularExpression(r"[\d,]{0,13}"), self._num_box))
        self._num_box.wants_keys.connect(lambda: self._take_keys(self._num_box))
        self._num_box.done.connect(self._give_keys)
        self._num_box.entered.connect(self._add_goal)
        self._num_box.textChanged.connect(lambda _t: self._goal_check())
        row.addWidget(self._num_box, 1)
        self._add_btn = QPushButton(objectName="Act")
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.setFocusPolicy(Qt.NoFocus)
        self._add_btn.clicked.connect(lambda _=False: self._add_goal())
        row.addWidget(self._add_btn)
        a.addLayout(row)
        v.addWidget(add)
        return box

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._opacity)

    # ------------------------------------------------------------ the contract (the app wires exactly this)

    def refresh(self) -> None:
        """Shown while settings["grind_window"] is on, in the look the ⚙ panel picks (accent, tint, opacity), out of
        screen captures, the view that shows read again; hidden when it is off."""
        if not self._settings[SHOW_KEY]:
            if self.isVisible():
                self.hide()
            return
        self._restyle()
        self._read_opacity()
        if not self.isVisible():
            self._lists.clear()              # each opening reads the lists afresh
            self._place()
            self.show()
            set_capturable(self, self._settings)
            self._clock.start()
        self.raise_()
        self._fill()
        self.update()                     # the glass repaints in the tint the settings now give

    def open_tab(self, name: str) -> None:
        """The window open on a tab ("now" | "drops" | "spots" | "history"), the setting on."""
        if name not in TABS:
            raise ValueError(f"no grind window tab {name!r}")
        self._tab, self._summary = name, None
        if self._tabs is not None:
            self._tabs.set_value(name)
        self._show_view()
        self._settings[SHOW_KEY] = True
        self.refresh()
        self._scroll.verticalScrollBar().setValue(0)

    def show_summary(self, summary) -> None:
        """The window open on one run's summary (grindlive.Summary), the setting on; Back returns to the tabs."""
        self._summary = summary
        self._fill_summary()
        self._show_view()
        self._settings[SHOW_KEY] = True
        self.refresh()
        self._scroll.verticalScrollBar().setValue(0)

    def place_under(self, rect: QRect) -> None:
        """Where the window opens the first time (no place kept yet): just under the bar's rect."""
        self._under = QRect(rect) if isinstance(rect, QRect) else None

    def apply_language(self, t: I18n) -> None:
        """Every word again in the new language, right to left in Hebrew: the tabs, the goals and the lists made
        again, the view that shows (a summary too) as it stood."""
        self.t = t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self._lists.clear()
        self._goals_drawn = None
        self._retext()
        self._fill_summary()
        self._fill()

    def set_kb(self, kb: KnowledgeBase) -> None:
        """A KB update swapped the KB: its pictures and names, everything read again."""
        self._kb = kb
        self._pics = _Pictures(kb)
        self._lists.clear()
        self._goals_drawn = None
        self._map_key = None
        self._exp_needs = None
        self._fill_summary()
        self._fill()

    # ------------------------------------------------------------ words (all of them, for apply_language)

    def _caption(self, key: str) -> str:
        """A section's small heading ("THIS MAP", "GOALS"): capitals in English, Hebrew has none."""
        text = self.t(key)
        return text if self.t.rtl else text.upper()

    def _retext(self) -> None:
        t, rtl = self.t, self.t.rtl
        self._title.setText(bidi.plain(t("gw_title"), rtl))
        self._close.setToolTip(t("gw_close"))
        self._close.setAccessibleName(t("gw_close"))
        self._back.setText(bidi.plain(f"\u2039 {t('lk_back')}", rtl))
        self._back.setToolTip(t("gw_back_tip"))
        self._make_tabs()
        self._make_kinds()
        self._retext_add()
        self._warn_head.setText(bidi.plain(self._caption("gw_map_head"), rtl))
        self._profit_line.setToolTip(t("gw_profit_tip"))
        self._move_head.setText(bidi.plain(self._caption("gw_move_on_head"), rtl))
        self._move_btn.setText(bidi.plain(t("gw_show_way"), rtl))
        self._move_btn.setToolTip(t("gw_show_way_tip"))
        self._goals_head.setText(bidi.plain(self._caption("gw_goals_head"), rtl))
        self._goals_none.setText(bidi.plain(t("gw_goals_none"), rtl))
        # the cards keep a little room on the scrollbar's side (right, or left in Hebrew, where Qt moves it)
        self._body_lay.setContentsMargins(GUTTER if rtl else 0, 0, 0 if rtl else GUTTER, 0)

    def _make_tabs(self) -> None:
        """The four tabs, made again whenever their words change (another language)."""
        t, rtl = self.t, self.t.rtl
        if self._tabs is not None:
            self._tabs_slot.removeWidget(self._tabs)
            self._tabs.hide()
            self._tabs.deleteLater()
        self._tabs = Segmented([(t(f"gw_tab_{tab}"), tab) for tab in TABS], self._tab, rtl)
        self._tabs.set_label(t("gw_tabs_a11y"))
        for b in self._tabs.group.buttons():
            b.setFocusPolicy(Qt.NoFocus)
        self._tabs.changed.connect(self._tab_picked)
        self._tabs_slot.addWidget(self._tabs)
        self._tabs.setVisible(self._summary is None)

    def _make_kinds(self) -> None:
        """What a new goal is (a level, an item, mesos), made again with the language."""
        t, rtl = self.t, self.t.rtl
        if self._kinds is not None:
            self._kinds_slot.removeWidget(self._kinds)
            self._kinds.hide()
            self._kinds.deleteLater()
        self._kinds = Segmented([(t(f"gw_kind_{k}"), k) for k in ("level", "item", "mesos")], self._goal_kind, rtl)
        self._kinds.set_label(t("gw_kind_a11y"))
        for b in self._kinds.group.buttons():
            b.setFocusPolicy(Qt.NoFocus)
        self._kinds.changed.connect(self._kind_picked)
        self._kinds_slot.addWidget(self._kinds)

    def _retext_add(self) -> None:
        """The add card for the kind picked: the item search only for an item, the number box's hint, Add."""
        t, rtl = self.t, self.t.rtl
        kind = self._goal_kind
        self._add_head.setText(bidi.plain(self._caption("gw_add_head"), rtl))
        self._item_box.setVisible(kind == "item")
        self._item_box.setPlaceholderText(bidi.plain(t("gw_ph_item"), rtl))
        self._item_box.setAccessibleName(t("gw_ph_item"))
        self._item_find.setIcon(line_icon("search", palette().muted))
        hint = {"level": "gw_ph_level", "item": "gw_ph_count", "mesos": "gw_ph_mesos"}[kind]
        self._num_box.setPlaceholderText(bidi.plain(t(hint), rtl))
        self._num_box.setAccessibleName(t(hint))
        self._add_btn.setText(bidi.plain(t("gw_add"), rtl))
        self._add_btn.setToolTip(t("gw_add_tip"))
        self._goal_check()
        self._fill_picks()

    # ------------------------------------------------------------ which view shows

    def _show_view(self) -> None:
        """The picked tab's page, or the summary's with Back in the tabs' place."""
        summary = self._summary is not None
        for tab, page in self._pages.items():
            page.setVisible(not summary and tab == self._tab)
        self._sum_page.setVisible(summary)
        if self._tabs is not None:
            self._tabs.setVisible(not summary)
        self._back.setVisible(summary)

    def _tab_picked(self, tab) -> None:
        if tab not in TABS or tab == self._tab:
            return
        self._tab = tab
        self._show_view()
        self._fill()
        self._scroll.verticalScrollBar().setValue(0)

    def _back_clicked(self) -> None:
        """Back from a summary: the tab it was opened over."""
        self._summary = None
        self._show_view()
        self._fill()
        self._scroll.verticalScrollBar().setValue(0)

    def _fill(self) -> None:
        """The view that shows, read again (a summary shows the run it was given, as it was)."""
        if self._summary is not None:
            return
        if self._tab == "now":
            self._fill_now()
        else:
            self._fill_list()

    def _tick(self) -> None:
        if self.isVisible() and self._summary is None and self._tab == "now":
            self._fill_now()

    def _scanner_changed(self) -> None:
        """A pickup, a run started or ended: the Now tab at once; a list tab once the pickups pause."""
        if not self.isVisible() or self._summary is not None:
            return
        if self._tab == "now":
            self._fill_now()
        else:
            self._reread.start()

    # ------------------------------------------------------------ Now: the live run

    def _fill_now(self) -> None:
        """The run as grindlive.live reads it now; with no run at all, the card saying how to start one. The goals
        either way."""
        t, rtl = self.t, self.t.rtl
        lg = self._scanner.log_for(self._scanner.cid())
        live = self._live = grindlive.live(self._kb, lg, self._profiles.active, self._goals())
        self._now_empty.setVisible(lg is None)
        self._run_box.setVisible(lg is not None)
        if lg is None:
            self._now_empty.say(EMPTY_ICONS["now"], t("gw_now_empty_title"), t("gw_now_empty"), rtl)
        else:
            self._fill_run(live)
            self._fill_tiles(live)
            self._fill_level(live)
            self._fill_warnings(live)
            self._fill_toll(live)
            self._fill_move_on(live)
        self._fill_goals(live.goals)

    def _fill_run(self, live) -> None:
        """The run's card: the map (its minimap, its name), how long the run has gone and how much of it counted,
        and its state as a chip — grinding in the accent, paused, dead, stopped."""
        t, rtl = self.t, self.t.rtl
        key = f"map/{live.map_id}" if live.map_id else ""
        if key != self._map_key:
            self._map_key = key
            self._pics.show(self._map_pic, key, *MAP_PIC, live.map_name)
        self._map_pic.setVisible(bool(key))
        self._map_name.setText(bidi.ltr_name(live.map_name, rtl) if live.map_name
                               else bidi.plain(t("gw_map_unknown"), rtl))
        wall, active = live.wall_s, live.session.active_s
        times = _elapsed(t, wall) if wall - active < 60 else t("gw_times", wall=_elapsed(t, wall),
                                                                active=_elapsed(t, active))
        self._times.setText(bidi.plain(times, rtl))
        self._times.setToolTip(t("gw_times_tip", m=grindlive.IDLE_S // 60))
        state = live.state if live.state in STATES else "stopped"
        mark = {"running": DOT, "stopped": SQUARE}.get(state)
        word = t(f"gw_state_{state}")
        self._state.setText(bidi.plain(f"{mark} {word}" if mark else word, rtl))
        _set_prop(self._state, "state", state)
        if state == "paused":
            tip = (t("gw_paused_manual_tip") if self._scanner.paused()
                   else t("gw_paused_idle_tip", m=grindlive.IDLE_S // 60))
        else:
            tip = {"dead": t("gw_dead_tip"), "stopped": t("gw_stopped_tip")}.get(state, "")
        self._state.setToolTip(tip)

    def _fill_tiles(self, live) -> None:
        """EXP and profit per hour: the whole run's rate big, the last minutes' under it; then what the profit is made
        of."""
        t, rtl = self.t, self.t.rtl
        s, recent = live.session, live.recent
        minutes = grindlive.RECENT_S // 60
        for key, now, last in (("exp", s.exp_h, recent.exp_h), ("profit", s.profit_h, recent.profit_h)):
            tile = self._tiles[key]
            tile.name.setText(bidi.plain(t(f"gw_tile_{key}"), rtl))
            tile.value.setText(bidi.ltr_name(_short(now), rtl))
            tile.sub.setText(bidi.plain(t("gw_recent", m=minutes, v=_block(_short(last), rtl)), rtl))
            tile.setToolTip(t("gw_recent_tip", m=minutes) if now is not None else t("gw_wait_tip"))
            tile.value.setAccessibleName(f"{t(f'gw_tile_{key}')}: {_short(now)}")
        parts = t("gw_parts", mesos=_block(_short(s.mesos_h), rtl), loot=_block(_short(s.loot_h), rtl),
                  potions=_block(_short(s.potions_h), rtl))
        self._profit_line.setText(bidi.plain(t("gw_per_hour", parts=parts), rtl))
        self._profit_line.setVisible(s.profit_h is not None)

    def _fill_level(self, live) -> None:
        """The level and its EXP as the HUD reads them, the bar to the next, the time to it, and the level-ups of
        this run as a chip."""
        t, rtl = self.t, self.t.rtl
        known = live.level is not None
        pct = live.exp_pct if known else None
        text = t("lv_short", n=live.level) if known else t("gw_level_unknown")
        if pct is not None:
            text += f" · {_block(_pct(pct), rtl)}"
        self._level_text.setText(bidi.plain(text, rtl))
        self._level_bar.setVisible(pct is not None)
        if pct is not None:
            self._level_bar.set(pct / 100, accent_of(self._settings)[0])
        eta = live.to_level_s
        self._to_level.setVisible(known)
        self._to_level.setText(bidi.plain(t("gw_to_level", time=_elapsed(t, eta)) if eta is not None
                                          else t("gw_to_level_none"), rtl))
        ups = live.level_ups
        self._level_up.setVisible(bool(ups))
        if ups:
            self._level_up.setText(bidi.plain(f"{UP} {t('lv_short', n=ups[-1][1])}", rtl))
            self._level_up.setToolTip(t("gw_level_ups_tip", list="\n".join(
                f"{t('lv_short', n=lvl)} · {_clock(at)}" for at, lvl in ups)))

    def _fill_warnings(self, live) -> None:
        """The map's card: grindlive's warnings in the player's language, each with its ⚠; hidden with none."""
        t, rtl = self.t, self.t.rtl
        lines = [bidi.plain(t(key, **params), rtl) for key, params in live.warnings]
        while len(self._warn_rows) < len(lines):
            row = _WarnRow()
            self._warn_lay.addWidget(row)
            self._warn_rows.append(row)
        for i, row in enumerate(self._warn_rows):
            row.text.setText(lines[i] if i < len(lines) else "")
            row.setVisible(i < len(lines))
        self._warn_card.setVisible(bool(lines))

    def _fill_toll(self, live) -> None:
        """What the run cost: deaths, and the potions drunk with what they cost."""
        t, rtl = self.t, self.t.rtl
        deaths = t("gw_deaths", n=live.deaths) if live.deaths else t("gw_deaths_none")
        potions = (t("gw_potions", n=f"{live.potions:,}", cost=_block(_short(live.potion_cost), rtl))
                   if live.potions else t("gw_potions_none"))
        self._toll.setText(bidi.plain(f"{deaths} · {potions}", rtl))

    def _fill_move_on(self, live) -> None:
        """A map for the player's level that their own runs say paid more (grindlive's pick), how much more than the
        last minutes here (what grindlive weighs it against; the whole run's rate before there are any), and Show the
        way."""
        t, rtl = self.t, self.t.rtl
        spot = live.move_on
        self._move_card.setVisible(spot is not None)
        if spot is None:
            return
        self._move_to = spot.map_id
        here = live.recent.exp_h if live.recent.exp_h is not None else live.session.exp_h
        there = spot.exp_h
        name, exp = _block(spot.map_name or spot.map_id, rtl), _block(_short(there), rtl)
        if here and there and there > here:
            text = t("gw_move_on", map=name, pct=round((there - here) * 100 / here), exp=exp)
        else:
            text = t("gw_move_on_plain", map=name, exp=exp)
        self._move_text.setText(bidi.plain(text, rtl))

    # ------------------------------------------------------------ Now: the goals

    def _goals(self) -> list:
        """The goals kept in the settings (grind_goals: Goal.to_json dicts), each read back."""
        raw = self._settings[GOALS_KEY]
        return [g for d in raw if (g := grindlive.Goal.from_json(d)) is not None] if isinstance(raw, list) else []

    def _save_goals(self, goals: list) -> None:
        self._settings[GOALS_KEY] = [g.to_json() for g in goals]

    def _fill_goals(self, progress: list) -> None:
        """A row per goal (made again only when the goals change), its bar, how far it is and when it is reached
        filled in every second."""
        t, rtl = self.t, self.t.rtl
        goals = self._goals()
        if goals != self._goals_drawn:
            self._goals_drawn = goals
            for row in self._goal_rows:
                self._goal_lay.removeWidget(row)
                row.hide()
                row.deleteLater()
            self._goal_rows = []
            for i, goal in enumerate(goals):
                row = _GoalRow(t)
                row.removed.connect(lambda i=i: self._remove_goal(i))
                if goal.kind == "item":
                    self._pics.show(row.icon, goal.item_key, GOAL_PIC, GOAL_PIC, goal.item)
                else:
                    row.icon.setPixmap(_glyph("exp" if goal.kind == "level" else "mesos", GLYPH, row.icon))
                row.title.setText(bidi.plain(self._goal_words(goal), rtl))
                self._goal_lay.addWidget(row)
                self._goal_rows.append(row)
        accent = accent_of(self._settings)[0]
        for row, goal in zip(self._goal_rows, goals):
            gp = next((p for p in progress if p.goal == goal), None)
            have = gp.have if gp is not None else 0
            done = gp is not None and gp.done
            row.bar.set(1.0 if done else self._goal_frac(goal, have), ink(GAIN) if done else accent)
            if done:
                when = t("gw_goal_done")
            elif gp is not None and gp.eta_s is not None:
                when = t("gw_goal_eta", time=_elapsed(t, gp.eta_s))
            else:
                when = t("gw_goal_no_eta")
            row.sub.setText(bidi.plain(f"{self._goal_have(goal, have)} · {when}", rtl))
            _set_prop(row, "done", done)
        self._goals_none.setVisible(not goals)

    def _goal_frac(self, goal, have: int) -> float:
        """How far a goal is, 0 to 1: the count over the target; for a level, the EXP it takes from level 1 (each
        level takes more than the one before: Lv. 31 of 35 counted as levels drew the bar nearly full, hours away),
        the level's own EXP % in it."""
        if goal.target <= 0:
            return 0.0
        if goal.kind == "level" and self._exp_needs is None:
            self._exp_needs = plan.exp_table(self._kb)          # (a page read from disk: not every second)
        table = self._exp_needs if goal.kind == "level" else {}
        total = sum(table.get(lv, 0) for lv in range(1, goal.target))
        if not total:
            return have / goal.target
        live = self._live
        pct = live.exp_pct if live is not None and live.level == have and live.exp_pct is not None else 0.0
        return (sum(table.get(lv, 0) for lv in range(1, have)) + pct / 100 * table.get(have, 0)) / total

    def _goal_words(self, goal) -> str:
        t, rtl = self.t, self.t.rtl
        if goal.kind == "level":
            return t("gw_goal_level", n=goal.target)
        if goal.kind == "mesos":
            return t("gw_goal_mesos", n=_block(f"{goal.target:,}", rtl))
        return t("gw_goal_item", n=f"{goal.target:,}", item=_block(goal.item or goal.item_key, rtl))

    def _goal_have(self, goal, have: int) -> str:
        """How far a goal is: "Lv. 31 / 35", "62 / 100", "420.5K / 1.00M"."""
        rtl = self.t.rtl
        if goal.kind == "level":
            return f"{self.t('lv_short', n=have)} / {goal.target}"
        if goal.kind == "mesos":
            return _block(f"{_short(have)} / {_short(goal.target)}", rtl)
        return _block(f"{have:,} / {goal.target:,}", rtl)

    def _kind_picked(self, kind) -> None:
        """Another kind of goal: the boxes empty again, the item search shown for an item."""
        if kind == self._goal_kind:
            return
        self._goal_kind = kind
        self._goal_item = None
        self._num_box.clear()
        self._item_box.clear()
        self._retext_add()

    def _item_typed(self, _text: str = "") -> None:
        """A keystroke in the item search: the item picked before is let go, the rows read once the typing pauses."""
        self._goal_item = None
        self._searching.start()
        self._goal_check()

    def _fill_picks(self) -> None:
        """The KB's items for what is typed in the search (the searches' own ranking: the exact name first), each with
        its picture; a click picks it. Nothing while an item is picked or under two letters are typed."""
        t, rtl = self.t, self.t.rtl
        for w in self._pick_rows:
            self._picks_lay.removeWidget(w)
            w.hide()
            w.deleteLater()
        self._pick_rows = []
        q = self._item_box.text()
        asked = self._goal_kind == "item" and self._goal_item is None and len(q.replace(" ", "")) >= 2
        hits, total = find_items(self._kb, "item", q, PICK_ROWS) if asked else ([], 0)
        for hit in hits:
            row = _Press("Row")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(6, 4, 8, 4)
            hl.setSpacing(8)
            hl.addWidget(self._pics.label(hit.key, PICK_PIC, zoom=False), 0, Qt.AlignVCenter)
            words = QVBoxLayout()
            words.setSpacing(0)
            words.addWidget(_label(bidi.ltr_name(hit.name, rtl), "Name", wrap=True))
            if hit.sub:
                words.addWidget(_label(bidi.ltr_name(hit.sub, rtl), "Sub", wrap=True))
            hl.addLayout(words, 1)
            row.setAccessibleName(hit.name)
            row.clicked.connect(lambda hit=hit: self._pick_item(hit.key, hit.name))
            self._picks_lay.addWidget(row)
            self._pick_rows.append(row)
        self._picks.setVisible(bool(hits))
        note = (t("gw_pick_none") if asked and not hits
                else t("lk_more", n=f"{total - len(hits):,}") if total > len(hits) else "")
        self._picks_note.setText(bidi.plain(note, rtl) if note else "")
        self._picks_note.setVisible(bool(note))

    def _pick_item(self, key: str, name: str) -> None:
        """A found item clicked: it is the goal's, its name in the search, the rows gone, how many asked next."""
        self._goal_item = (key, name)
        self._item_box.setText(name)            # (setText: no textEdited, the pick stays)
        self._fill_picks()
        self._goal_check()
        if self._typing:
            self._num_box.setFocus(Qt.OtherFocusReason)

    def _pick_first(self) -> None:
        """Enter in the item search: the first item it found."""
        if self._searching.isActive():
            self._searching.stop()
            self._fill_picks()
        if self._pick_rows:
            self._pick_rows[0].clicked.emit()

    def _goal_ready(self):
        """The goal the add card says now (grindlive.Goal), or None while it says no whole one: a level from 2 to
        LEVEL_MAX, an item picked and how many, an amount of mesos."""
        n = _number(self._num_box.text())
        if n is None or n <= 0:
            return None
        if self._goal_kind == "level":
            return grindlive.Goal("level", n) if 1 < n <= LEVEL_MAX else None
        if self._goal_kind == "item":
            return grindlive.Goal("item", n, *self._goal_item) if self._goal_item else None
        return grindlive.Goal("mesos", n)

    def _goal_check(self) -> None:
        self._add_btn.setEnabled(self._goal_ready() is not None)

    def _add_goal(self) -> None:
        """Add (or Enter in the number box): the goal saved after the others (one already there stays once), the
        boxes empty again and the keyboard back to the game."""
        goal = self._goal_ready()
        if goal is None:
            return
        goals = self._goals()
        if goal not in goals:
            goals.append(goal)
            self._save_goals(goals)
        self._goal_item = None
        self._num_box.clear()
        self._item_box.clear()
        self._fill_picks()
        self._give_keys()
        self._fill_now()

    def _remove_goal(self, i: int) -> None:
        goals = self._goals()
        if 0 <= i < len(goals):
            del goals[i]
            self._save_goals(goals)
        self._fill_now()

    # ------------------------------------------------------------ the keyboard, only while a goal's box is typed in

    def _take_keys(self, box: QLineEdit) -> None:
        """A goal's box clicked: the one time this window takes the keyboard, while the player types in it. It goes
        back to the window that had it (the game) on Esc, Enter in the number box or Add; a click on another window
        takes it there."""
        if not self._typing:
            self._typing = True
            self._keys_from = _foreground()
            _accept_keys(self, True)
            self.activateWindow()
            QTimer.singleShot(KEYS_CHECK_MS, self, self._keys_given)
        box.setFocus(Qt.MouseFocusReason)

    def _keys_given(self) -> None:
        """Windows may refuse the activation (another program holds the foreground): then the window goes back to
        never taking the keyboard — left able to, a click on a tab would take it from the game."""
        if self._typing and not self.isActiveWindow():
            self._give_keys(back=False)

    def _give_keys(self, back: bool = True) -> None:
        """The window never takes the keyboard again until a box is clicked; back: to the window that had it."""
        if not self._typing:
            return
        self._typing = False
        for box in (self._num_box, self._item_box):
            box.clearFocus()
        _accept_keys(self, False)
        if back:
            _to_foreground(self._keys_from)
        self._keys_from = 0

    def changeEvent(self, e) -> None:
        if e.type() == QEvent.ActivationChange and self._typing and not self.isActiveWindow():
            self._give_keys(back=False)     # the player clicked another window: the keyboard is there already
        super().changeEvent(e)

    # ------------------------------------------------------------ Drops, Best spots, History

    def _level(self) -> int | None:
        """The player's level: the HUD's latest read, else the character's own."""
        if self._live is not None and self._live.level is not None:
            return self._live.level
        c = self._profiles.active
        return c.level if c is not None else None

    def _fill_list(self) -> None:
        """The list tab that shows, read from the run database (grindlive), its rows made again only when they
        changed; with none, the card saying how they come."""
        tab = self._tab
        if self._summary is not None or tab == "now":
            return
        cid = self._scanner.cid()
        if tab == "drops":
            rows = grindlive.drop_rates(self._kb, cid)
        elif tab == "spots":
            rows = grindlive.best_spots(self._kb, cid, self._level())
        else:
            rows = grindlive.history(self._kb, cid)
        if tab in self._lists and self._lists[tab] == rows:
            return
        self._lists[tab] = rows
        t, rtl = self.t, self.t.rtl
        lay = self._list_lays[tab]
        bar = self._scroll.verticalScrollBar()
        at = bar.value()
        _clear(lay)
        if not rows:
            empty = _Empty()
            empty.say(EMPTY_ICONS[tab], t(f"gw_{tab}_empty_title"), t(f"gw_{tab}_empty"), rtl)
            lay.addWidget(empty)
            return
        lay.addWidget(_label(bidi.plain(t(f"gw_{tab}_head"), rtl), "Note", wrap=True))
        make = {"drops": self._drop_row, "spots": self._spot_row, "history": self._history_row}[tab]
        for i, row in enumerate(rows):
            lay.addWidget(make(row, i))
        QTimer.singleShot(0, self, lambda: bar.setValue(at))      # a re-read keeps the player's place

    def _names(self, names: list[str], shown: int) -> str:
        """English names for one line, each whole ("Horny Mushroom, Zombie Mushroom"), then "and N more"."""
        rtl = self.t.rtl
        text = ", ".join(_block(n, rtl) for n in names[:shown])
        if len(names) > shown:
            text += " " + self.t("lk_more", n=len(names) - shown)
        return text

    def _drop_row(self, d, _i: int = 0) -> QFrame:
        """One item: its picture, its name, how many were picked up in how long and from which monsters, and on the
        end how many come an hour ("4.2 per hour"), or that the time is too short to say yet."""
        t, rtl = self.t, self.t.rtl
        card = QFrame(objectName="Line")
        h = QHBoxLayout(card)
        h.setContentsMargins(8, 7, 10, 8)
        h.setSpacing(10)
        h.addWidget(self._pics.label(d.item_key, ROW_PIC, caption=d.item), 0, Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(2)
        v.addWidget(_label(bidi.ltr_name(d.item, rtl), "Name", wrap=True))
        v.addWidget(_label(bidi.plain(t("gw_drop_sub", n=f"{d.count:,}", time=_elapsed(t, d.active_s)), rtl), "Sub",
                           wrap=True))
        names = []
        for m in d.monsters:
            name = str((self._kb.get(m) or {}).get("name") or m)
            if name not in names:
                names.append(name)
        if names:
            v.addWidget(_label(bidi.plain(t("gw_drop_from", list=self._names(names, MONSTERS_SHOWN)), rtl), "Sub",
                               wrap=True))
        h.addLayout(v, 1)
        if d.per_h is not None:
            rate = _label(bidi.plain(t("gw_drop_per_h", n=_block(per_hour(d.per_h), rtl)), rtl), "Rate")
            rate.setToolTip(t("gw_drop_per_h_tip"))
        else:
            rate = _label(bidi.plain(t("gw_not_enough"), rtl), "RateNone", wrap=True)
            rate.setFixedWidth(RATE_NONE_W)
            rate.setAlignment(Qt.AlignRight | Qt.AlignTop)
        h.addWidget(rate, 0, Qt.AlignRight | Qt.AlignTop)
        return card

    def _spot_row(self, sp, i: int = 0) -> QFrame:
        """One map: its minimap, its name and the time spent there, Show the way, and what it paid per hour (EXP,
        profit) in the tiles' colours. The best first, lit in the accent."""
        t, rtl = self.t, self.t.rtl
        card = QFrame(objectName="Line")
        card.setProperty("best", i == 0)
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 8, 10, 9)
        v.setSpacing(7)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._pics.label(f"map/{sp.map_id}", *MAP_PIC, caption=sp.map_name, name="MapPic"), 0,
                      Qt.AlignTop)
        who = QVBoxLayout()
        who.setSpacing(1)
        if i == 0:
            who.addWidget(_label(bidi.plain(self._caption("gw_best"), rtl), "LitCaption"))
        who.addWidget(_label(bidi.ltr_name(sp.map_name or sp.map_id, rtl), "Name", wrap=True))
        who.addWidget(_label(bidi.plain(t("gw_spot_time", time=_elapsed(t, sp.active_s), n=sp.sessions), rtl),
                             "Sub", wrap=True))
        top.addLayout(who, 1)
        top.addWidget(self._way_button(sp.map_id), 0, Qt.AlignTop)
        v.addLayout(top)
        nums = QHBoxLayout()
        nums.setSpacing(6)
        for key, value in (("exp", sp.exp_h), ("profit", sp.profit_h)):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(_label(bidi.ltr_name(_short(value), rtl), f"Num_{key}"))
            cell.addWidget(_label(bidi.plain(t(f"gw_spot_{key}"), rtl), "Unit"))
            nums.addLayout(cell, 1)
        v.addLayout(nums)
        return card

    def _way_button(self, map_id: str) -> QPushButton:
        b = QPushButton(bidi.plain(self.t("gw_show_way"), self.t.rtl), objectName="Act")
        b.setCursor(Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.NoFocus)
        b.setToolTip(self.t("gw_show_way_tip"))
        b.clicked.connect(lambda _=False, m=map_id: self.route_requested.emit(m))
        return b

    def _chips(self, chips: list[tuple[str, str]]) -> QWidget:
        """A row of chips (text, its QSS name) that wraps onto more lines rather than widen the window."""
        box = QWidget()
        flow = FlowLayout(box, spacing=4, line_spacing=4)
        for text, name in chips:
            flow.addWidget(_label(bidi.plain(text, self.t.rtl), name))
        return box

    def _when(self, start: float, end: float | None) -> str:
        """When a run was: "Today · 14:05–15:17" (one still going: when it started)."""
        span = _clock(start) + (f"\u2013{_clock(end)}" if end else "")
        return f"{_day(self.t, start)} · {_block(span, self.t.rtl)}"

    def _levels(self, levels) -> str:
        """A run's levels: "Lv. 31 → 32", one level when it stayed, "" when the HUD never read it."""
        a, b = levels
        if a is not None and b is not None and a != b:
            return self.t("lv_short", n=_block(f"{a} \u2192 {b}", self.t.rtl))
        lv = b if b is not None else a
        return self.t("lv_short", n=lv) if lv is not None else ""

    def _history_row(self, s, _i: int = 0) -> _Press:
        """One run: its first map's minimap; when it was and how long it counted; its maps; its EXP, profit and
        levels as chips. A click opens its summary."""
        t, rtl = self.t, self.t.rtl
        row = _Press("Row")
        row.setToolTip(t("gw_row_tip"))
        row.clicked.connect(lambda s=s: self.show_summary(s))
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 7, 10, 8)
        h.setSpacing(10)
        first = s.maps[0][0] if s.maps else ""
        h.addWidget(self._pics.label(f"map/{first}" if first else "", *ROW_MAP, zoom=False, name="MapPic"), 0,
                    Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(8)
        when = bidi.plain(self._when(s.start, s.end), rtl)
        top.addWidget(_label(when, "Name", wrap=True), 1)
        top.addWidget(_label(bidi.plain(_elapsed(t, s.active_s), rtl), "Count"), 0, Qt.AlignTop)
        v.addLayout(top)
        names = [name or mid for mid, name, _secs in s.maps]
        if names:
            v.addWidget(_label(bidi.plain(self._names(names, MAPS_SHOWN), rtl), "Sub", wrap=True))
        chips = [(t("gw_chip_exp", n=_block(_short(s.exp), rtl)), "Chip_exp"),
                 (t("gw_chip_profit", n=_block(_short(s.profit), rtl)), "Chip_profit")]
        levels = self._levels(s.levels)
        if levels:
            chips.append((levels, "Chip"))
        v.addWidget(self._chips(chips))
        h.addLayout(v, 1)
        row.setAccessibleName(f"{when}: {t('gw_row_tip')}")
        return row

    # ------------------------------------------------------------ a run's summary

    def _fill_summary(self) -> None:
        """The summary's card: when the run was, its active time, levels and deaths; its EXP and profit big with their
        per-hour rates; the mesos, loot and potions behind the profit; the maps with their time; the top drops with
        their pictures."""
        s = self._summary
        if s is None:
            return
        t, rtl = self.t, self.t.rtl
        lay = self._sum_lay
        _clear(lay)
        head = QFrame(objectName="Card")
        v = QVBoxLayout(head)
        v.setContentsMargins(12, 10, 12, 11)
        v.setSpacing(3)
        v.addWidget(_label(bidi.plain(self._caption("gw_sum_caption"), rtl), "Caption"))
        v.addWidget(_label(bidi.plain(self._when(s.start, s.end), rtl), "MapName", wrap=True))
        bits = [t("gw_sum_active", time=_elapsed(t, s.active_s))]
        levels = self._levels(s.levels)
        if levels:
            bits.append(levels)
        bits.append(t("gw_deaths", n=s.deaths) if s.deaths else t("gw_deaths_none"))
        v.addWidget(_label(bidi.plain(" · ".join(bits), rtl), "Sub", wrap=True))
        lay.addWidget(head)
        tiles = QWidget()
        trow = QHBoxLayout(tiles)
        trow.setContentsMargins(0, 0, 0, 0)
        trow.setSpacing(6)
        for key, total, per in (("exp", s.exp, s.exp_h), ("profit", s.profit, s.profit_h)):
            tile = _Tile(key)
            tile.name.setText(bidi.plain(t(f"gw_sum_{key}"), rtl))
            tile.value.setText(bidi.ltr_name(_short(total), rtl))
            tile.sub.setText(bidi.plain(t("loot_card_per_h", h=_block(_short(per), rtl)), rtl))
            trow.addWidget(tile, 1)
        lay.addWidget(tiles)
        parts = t("gw_parts", mesos=_block(_short(s.mesos), rtl), loot=_block(_short(s.loot), rtl),
                  potions=_block(_short(s.potion_cost), rtl))
        line = _label(bidi.plain(parts, rtl), "Sub", wrap=True)
        line.setToolTip(t("gw_profit_tip"))
        lay.addWidget(line)
        if s.maps:
            lay.addWidget(_label(bidi.plain(self._caption("gw_sum_maps"), rtl), "Head"))
            for mid, name, secs in s.maps:
                lay.addWidget(self._line_row(f"map/{mid}", ROW_MAP, name or mid, _elapsed(t, secs)))
        lay.addWidget(_label(bidi.plain(self._caption("gw_sum_drops"), rtl), "Head"))
        for key, name, n in s.top_drops:
            lay.addWidget(self._line_row(key, (ROW_PIC, ROW_PIC), name, t("loot_badge", n=f"{n:,}")))
        if not s.top_drops:
            lay.addWidget(_label(bidi.plain(t("gw_sum_no_drops"), rtl), "Note", wrap=True))

    def _line_row(self, key: str, size: tuple[int, int], name: str, end: str) -> QFrame:
        """A summary's row: a picture, a name, and a figure on the end (a map's time, a drop's count)."""
        rtl = self.t.rtl
        row = QFrame(objectName="Line")
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 5, 10, 5)
        h.setSpacing(10)
        h.addWidget(self._pics.label(key, *size, caption=name, name="MapPic" if key.startswith("map/") else "Pic"),
                    0, Qt.AlignVCenter)
        h.addWidget(_label(bidi.ltr_name(name, rtl), "Name", wrap=True), 1)
        h.addWidget(_label(bidi.plain(end, rtl), "Count"), 0, Qt.AlignVCenter)
        return row

    # ------------------------------------------------------------ look, closing

    def _restyle(self) -> None:
        """The accent and the palette the settings pick, in the window's style sheet (set only when it changed: a
        restyle re-polishes every row), the goals' sparkle and coin and the search's magnifier drawn again in it."""
        sheet = qss(self._settings)
        if sheet != self.styleSheet():
            self.setStyleSheet(sheet)
            self._goals_drawn = None
            self._item_find.setIcon(line_icon("search", palette().muted))

    def _read_opacity(self) -> None:
        """The NPCs window's own slider sets it: the same glass, as see-through as the player asked."""
        try:
            self._opacity = min(OPACITY_MAX, max(OPACITY_MIN, float(self._settings["npc_overlay_opacity"])))
        except (TypeError, ValueError):
            self._opacity = OPACITY_DEFAULT

    def _close_clicked(self, _=False) -> None:
        """The ✕: the setting off (the grind bar follows), hidden until switched back on. The run goes on."""
        self._settings[SHOW_KEY] = False
        self.hide()
        self.closed.emit()

    def hideEvent(self, e) -> None:
        for timer in (self._clock, self._reread, self._searching):   # nothing is read behind the back once hidden
            timer.stop()
        self._give_keys()
        if self._placed:            # hidden (the ✕, the bar, the app closing): keep the place now, not 400 ms later
            self._geom.stop()
            self._remember()
        super().hideEvent(e)

    # ------------------------------------------------------------ place, move, resize

    def _place(self) -> None:
        """Where the window opens: where the player left it, when that is still on a screen (a monitor since
        unplugged: under the bar again)."""
        screens = [s.geometry() for s in QGuiApplication.screens()]
        saved = self._settings[GEOM_KEY]
        size = QSize(self.width(), self.height())
        if isinstance(saved, dict) and isinstance(saved.get("w"), int) and isinstance(saved.get("h"), int):
            size = mapview.clamp_size(saved["w"], saved["h"], screens, self.minimumSize())
        spot = mapview.saved_spot(saved, size, screens)
        self.setGeometry(QRect(spot if spot is not None else self._default_spot(size), size))
        self._placed = True

    def _default_spot(self, size: QSize) -> QPoint:
        """Just under the bar (a click on it opens this), kept on that screen; without one, the primary screen's
        top-left corner."""
        primary = QGuiApplication.primaryScreen().availableGeometry()
        screens = [s.geometry() for s in QGuiApplication.screens()]
        under = self._under
        if isinstance(under, QRect) and not under.isNull():
            screen = next((g for g in screens if g.intersects(under)), primary)
            x = min(max(under.left(), screen.left()), max(screen.left(), screen.right() - size.width() + 1))
            y = min(max(under.bottom() + 1 + GAP, screen.top()), max(screen.top(), screen.bottom() - size.height() + 1))
            return QPoint(x, y)
        return primary.topLeft() + QPoint(SHADOW + 4, SHADOW + 4)

    def moveEvent(self, e) -> None:
        self._geom.start()
        super().moveEvent(e)

    def resizeEvent(self, e) -> None:
        self._geom.start()
        super().resizeEvent(e)

    def _remember(self) -> None:
        if self._placed:
            self._settings[GEOM_KEY] = {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()}
