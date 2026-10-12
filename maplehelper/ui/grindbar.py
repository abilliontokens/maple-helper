"""The grind bar over the game: one slim row of glass in the proportions of the game's own megaphone strip (1568 x 86
on a 2734 x 1568 game) with the grind at a glance, the grind window (ui/grindwindow.py) one click away. Left to right
(mirrored in Hebrew): the dots that drag it; the map over a dot that says how the run stands (green running, grey
paused, red for 10 s after a death) and the grind time; EXP and profit per hour; the level and the time to the next
one over a progress bar lit in the accent and the level's percent; the last drop and how many of it come an hour
(with goals set: the first one still to reach and when); then Pause (Resume) and Stop, or Start with no run, every
figure "–" then.

Its figures are grindlive.live's, of the loot log's run (the grind session IS that run: ui/lootscan.LootScanner), read
again on every scanner change and every second while it shows (the time and the rates move). Everything in it scales
with its height (labels 0.163 x, figures 0.30 x); its edges resize it to any size from 900 x 56 (its proportions are
only its default's: dragged taller than its width has room for, its content stays at the size the width allows,
centred) and its size and place are kept in grind_bar_geom. With none kept it opens over the game's
picture as wide and tall as the megaphone strip (57.35 % x 5.48 % of the picture), centred just above the game's
bottom HUD strip; with no game window, 70 % of the screen's width at its bottom. A click on it (not on its buttons or
dots) opens the grind window; a right-click offers to hide it (settings["grind_bar"] off, as the toolbar's Grind
button turns it off). Like every window over the game it never takes the keyboard, follows the ⚙ panel's look (the
glass's tint and opacity, the accent: npcoverlay.palette(), accent_of, ink) and stays out of screen captures unless
"Show the overlays in screenshots" is on."""
from __future__ import annotations

import math
import sys
import time

from PySide6.QtCore import QAbstractAnimation, QPoint, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .. import bidi, grindlive
from ..gamearea import GameArea, valid_region
from ..hud import STRIP
from ..i18n import I18n
from . import theme
from .glass import SHADOW, EdgeResize
from .lookpick import line_icon
from .lootoverlay import STOP, _rgba
from .npcoverlay import (GEOM_DEBOUNCE_MS, OPACITY_DEFAULT, OPACITY_MAX, OPACITY_MIN, _flags, _paint_glass, accent_of,
                         ink, keep_over_game, palette, set_capturable)
from .regionpick import from_capture

BASE_W, BASE_H = 1568, 86           # the game's megaphone strip, measured on a 2734 x 1568 game: the bar's proportions
GAME_W, GAME_H = 0.5735, 0.0548     # ... its share of the game picture's width and height: the bar's default size
MIN_W, MIN_H = 900, 56              # the smallest glass the player can drag it to (any proportions above that)
SCREEN_SHARE = 0.70                 # no game window: as wide as this share of the primary screen...
SCREEN_GAP = 40                     # ... this far above its bottom (the taskbar's top)
LABEL_K, VALUE_K = 0.163, 0.30      # the labels' and the figures' font sizes over the glass's height (14 / 26 px at 86)
BUTTON_K = 0.17                     # the buttons' words
FIT_MIN = 0.6                       # a figure wider than its segment steps its font down, never below this share
TALL_K = 1.15                       # the content follows the height up to this much over the strip's proportions (a bar
                                    # dragged taller keeps that size, centred: its words would not fit across it)
# each segment's share of the row's width: fixed shares, so nothing shifts as the figures change (the last drop's
# item name takes the most)
STRETCH = {"map": 16, "exp": 11, "profit": 11, "level": 20, "slot": 25}
RUN, DEAD = "#4CD07D", "#FF6B6B"    # the dot running, and for the 10 s after a death (ink()ed on the white glass)
FLASH_MS = 1500                     # a tracked item's drop or a level-up: the right slot's accent outline pulses this long
DASH = "–"


def _num(n: int | None) -> str:
    """A figure as the bar shows it: in full with its thousands ("18,400"), millions shortened ("1.25M")."""
    if n is None:
        return DASH
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    return f"{n:,}"


def per_hour(v: float) -> str:
    """How many of an item come an hour: one decimal under 10 ("4.2"), whole above ("18"), as the bar and the grind
    window's Drops tab say it."""
    tenths = round(v, 1)
    return f"{tenths:.1f}" if tenths < 10 else f"{round(v):,}"


def _clock(secs: float) -> str:
    """The grind time as a stopwatch says it: "42:10", "1:02:10"."""
    s = max(0, int(secs))
    h, m, s = s // 3600, s // 60 % 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _duration(t: I18n, secs: float) -> str:
    """How long until something, in whole minutes (the grind tracker's own "38 min" / "1:05 h")."""
    m = max(1, math.ceil(secs / 60))
    return t("grind_hours", h=m // 60, m=f"{m % 60:02d}") if m >= 60 else t("grind_minutes", m=m)


def qss(settings, unit: int) -> str:
    """The bar's own style for a glass `unit` px tall (every size follows it), in the palette of the glass under it
    (palette(): light text on the dark tints, dark on the white one): the labels muted, the figures in the text's
    colour, Start lit in the accent, Stop in its warm red ink()ed to read on the glass. Rebuilt on every refresh and
    resize, set only when it changed."""
    accent, on_accent = accent_of(settings)
    pal = palette()
    stop = ink(STOP)
    label, value, button = round(LABEL_K * unit), round(VALUE_K * unit), round(BUTTON_K * unit)
    return f"""
QLabel {{ background: transparent; }}
#Label {{ color: {pal.muted}; font-size: {label}px; font-weight: 600; letter-spacing: {label * 0.05:.1f}px; }}
#Value {{ color: {pal.text}; font-size: {value}px; font-weight: 600; }}
QFrame#Divider {{ background: {pal.fill2}; border: none; }}
QPushButton {{ background: {pal.fill1}; color: {pal.text}; border: none; border-radius: {round(0.13 * unit)}px;
              padding: 0 {round(0.17 * unit)}px; font-size: {button}px; font-weight: 600; }}
QPushButton:hover {{ background: {pal.fill2}; }}
QPushButton#Go {{ background: {accent}; color: {on_accent}; }}
QPushButton#Go:hover {{ background: {QColor(accent).lighter(112).name()}; }}
QPushButton#Stop {{ background: {_rgba(stop, 0.16)}; color: {stop}; }}
QPushButton#Stop:hover {{ background: {_rgba(stop, 0.28)}; }}
"""


def _mark(kind: str, px: int, colour: str, dpr: float) -> QIcon:
    """A button's mark drawn at its size, in its words' colour: ▶ Start and Resume, two bars Pause, ■ Stop (the bar
    scales with its height: a font's glyph sat a little off its box at some sizes)."""
    n = max(1, round(px * dpr))
    pm = QPixmap(n, n)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(n / 12, n / 12)                 # drawn on a 12-unit square
    path = QPainterPath()
    if kind == "play":
        path.moveTo(2.5, 1.2)
        path.lineTo(11, 6)
        path.lineTo(2.5, 10.8)
        path.closeSubpath()
    elif kind == "pause":
        path.addRoundedRect(QRectF(2, 1.5, 3, 9), 0.9, 0.9)
        path.addRoundedRect(QRectF(7, 1.5, 3, 9), 0.9, 0.9)
    else:
        path.addRoundedRect(QRectF(1.8, 1.8, 8.4, 8.4), 1.5, 1.5)
    p.fillPath(path, theme.qcolor(colour))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


def _game_rect() -> QRect | None:
    """The game's picture on screen in logical pixels (gamearea's capture pixels over its screen's ratio, as the
    minimap box is placed: npcoverlay.minimap_box); None with no game window."""
    play = GameArea().find()
    if not play:
        return None
    x, y, w, h = play
    screens = [(s.geometry(), s.devicePixelRatio()) for s in QGuiApplication.screens()]
    rect, _ = from_capture({"x": x, "y": y, "w": w, "h": h}, screens, scale=sys.platform != "darwin")
    return rect


# ---------------------------------------------------------------- its pieces

class _Line(QLabel):
    """One line of a segment, ending in "…" where it is wider than its room (a long map or item name), the whole of
    it in the tooltip. `compose` lays the line out around the name as shown (the words around it, its bidi marks)."""

    def __init__(self, name: str):
        super().__init__(objectName=name)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._name, self._compose = "", str

    def set(self, name: str, compose=str) -> None:
        self._name, self._compose = name, compose
        self.fit()

    def full(self) -> str:
        return self._compose(self._name)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.fit()

    def fit(self) -> None:
        self.ensurePolished()
        fm = self.fontMetrics()
        room = self.contentsRect().width() - fm.horizontalAdvance(self._compose(""))
        shown = fm.elidedText(self._name, Qt.ElideRight, max(1, room)) if self._name else ""
        text = self._compose(shown)
        if text != self.text():
            self.setText(text)
        self.setToolTip(self.full() if shown != self._name else "")


class _Figure(QLabel):
    """A figure ("18,400", "42:10", "63%"), never cut: wider than its room, its font steps down (never below
    FIT_MIN of the size the bar's height gives it); its height stays the full size's, so the row never jumps."""

    def __init__(self):
        super().__init__(objectName="Value")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.px = 0                         # the size the bar's height gives it (GrindBar._scale)

    def setText(self, text: str) -> None:
        if text != self.text():
            super().setText(text)
        self.fit()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.fit()

    def fit(self) -> None:
        if not self.px:
            return
        self.ensurePolished()
        f = QFont(self.font())
        f.setPixelSize(self.px)
        self.setMinimumHeight(QFontMetrics(f).height())
        room, px, floor = self.contentsRect().width(), self.px, max(1, round(self.px * FIT_MIN))
        while px > floor and QFontMetrics(f).horizontalAdvance(self.text()) > room:
            px -= 1
            f.setPixelSize(px)
        sheet = f"font-size: {px}px;" if px != self.px else ""      # (its own sheet wins over the bar's)
        if sheet != self.styleSheet():
            self.setStyleSheet(sheet)


class _Grip(QWidget):
    """The dots at the bar's leading end: dragging them moves it (a click anywhere else opens the grind window)."""

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.OpenHandCursor)
        self._grab: QPoint | None = None
        self._icon, self._icon_for = None, None     # its dots, and the colour they were drawn in

    def paintEvent(self, e) -> None:
        colour = palette().muted                   # the glass's muted colour now: drawn again when it changes
        if colour != self._icon_for:
            self._icon, self._icon_for = line_icon("grip-vertical", colour), colour
        s = min(self.height(), 3 * self.width())   # the dots are the icon's middle third: as wide as the widget
        p = QPainter(self)
        self._icon.paint(p, QRect((self.width() - s) // 2, (self.height() - s) // 2, s, s))

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._grab = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._grab is not None and e.buttons() & Qt.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._grab)

    def mouseReleaseEvent(self, e) -> None:
        self._grab = None


class _Dot(QWidget):
    """How the run stands, before the time: green running, grey paused (or no run), red for 10 s after a death."""

    def __init__(self):
        super().__init__()
        self.state = "stopped"

    def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.update()

    def color(self) -> QColor:
        if self.state == "running":
            return QColor(ink(RUN))
        if self.state == "dead":
            return QColor(ink(DEAD))
        return theme.qcolor(palette().muted)

    def paintEvent(self, e) -> None:
        d = min(self.width(), self.height())
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color())
        p.drawEllipse(QRectF((self.width() - d) / 2, (self.height() - d) / 2, d, d))


class _Progress(QWidget):
    """The level's progress: a rounded track lit in the accent up to the EXP's percent (from the right in Hebrew)."""

    def __init__(self, bar: GrindBar):
        super().__init__()
        self._bar = bar
        self.value: float | None = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, value: float | None) -> None:
        if value != self.value:
            self.value = value
            self.update()

    def paintEvent(self, e) -> None:
        r = QRectF(self.rect())
        rad = r.height() / 2
        track = QPainterPath()
        track.addRoundedRect(r, rad, rad)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillPath(track, theme.qcolor(palette().fill2))
        if self.value:
            w = r.width() * min(1.0, max(0.0, self.value))
            lit = QRectF(r.right() - w if self.isRightToLeft() else r.left(), r.top(), w, r.height())
            path = QPainterPath()
            path.addRoundedRect(lit, rad, rad)
            p.setClipPath(track)
            p.fillPath(path, QColor(accent_of(self._bar.settings)[0]))


class _Slot(QWidget):
    """The right slot: the last drop and how many of it come an hour, or the first goal still to reach, over the
    item's name or when. On a tracked item's drop or a level-up its accent outline pulses once (flash)."""

    def __init__(self, bar: GrindBar):
        super().__init__()
        self._bar = bar
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col = QVBoxLayout(self)
        col.setSpacing(0)
        self.label = _Line("Label")
        self.value = _Line("Value")
        col.addStretch(1)
        col.addWidget(self.label)
        col.addWidget(self.value)
        col.addStretch(1)
        self._pulse = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=FLASH_MS)
        self._pulse.valueChanged.connect(lambda _v: self.update())

    def flash(self) -> None:
        self._pulse.stop()
        self._pulse.start()

    def flashing(self) -> bool:
        return self._pulse.state() == QAbstractAnimation.Running

    def paintEvent(self, e) -> None:
        if not self.flashing():
            return
        glow = math.sin(math.pi * float(self._pulse.currentValue()))     # one pulse: up, then away
        if glow <= 0:
            return
        unit = self._bar.unit
        pen = max(1.5, 0.028 * unit)
        accent = QColor(accent_of(self._bar.settings)[0])
        line, fill = QColor(accent), QColor(accent)
        line.setAlphaF(glow)
        fill.setAlphaF(0.14 * glow)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(line, pen))
        p.setBrush(fill)
        rad = 0.14 * unit
        p.drawRoundedRect(QRectF(self.rect()).adjusted(pen / 2, pen / 2, -pen / 2, -pen / 2), rad, rad)


def _segment(*value: tuple[QWidget, int]) -> tuple[QWidget, _Line, QHBoxLayout]:
    """A segment: its muted label over its value row, (widget, stretch) by (widget, stretch)."""
    seg = QWidget()
    seg.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    col = QVBoxLayout(seg)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(0)
    label = _Line("Label")
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    for w, stretch in value:
        row.addWidget(w, stretch)
    col.addStretch(1)
    col.addWidget(label)
    col.addLayout(row)
    col.addStretch(1)
    return seg, label, row


# ---------------------------------------------------------------- the bar

class GrindBar(EdgeResize, QWidget):
    open_window = Signal()          # its body clicked: the grind window opens (the app makes it)
    closed = Signal()               # its right-click Hide turned the setting off: the toolbar's Grind button unchecks

    def __init__(self, scanner, settings, kb, profiles, t: I18n | None = None):
        super().__init__(None, _flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)          # hovering the rim shows the resize cursor
        self.setWindowTitle("Maple Helper")
        self.setMinimumSize(MIN_W + 2 * SHADOW, MIN_H + 2 * SHADOW)
        self.scanner, self.settings, self.kb, self.profiles = scanner, settings, kb, profiles
        self.t = t or I18n(settings["language"] or "he")
        self.setLayoutDirection(Qt.RightToLeft if self.t.rtl else Qt.LeftToRight)
        self._opacity = OPACITY_DEFAULT
        self._placed = False                 # shown at least once: there is a place to remember
        self.unit = 0                        # the glass's height every size was last scaled to
        self._pressed: QPoint | None = None  # a press on the body, where (its release there opens the window)
        self.live = None                     # the grindlive.Live shown now
        self._marked: bool | None = None     # Pause's mark drawn for a paused run (Resume's ▶), or not
        self._geom = QTimer(self, singleShot=True, interval=GEOM_DEBOUNCE_MS, timeout=self._remember)
        # the time and the rates move between the scanner's changes too
        self._clock = QTimer(self, interval=1000, timeout=lambda: self.isVisible() and self._fill())
        self._build()
        self.resize(BASE_W + 2 * SHADOW, BASE_H + 2 * SHADOW)      # its proportions until it is placed
        self._scale()
        self._retext()

    # ---------------------------------------------------------------- the row

    def _build(self) -> None:
        row = QHBoxLayout(self)
        self._grip = _Grip()
        row.addWidget(self._grip)
        self._dot = _Dot()
        self._time = _Figure()
        self._map, self._map_label, map_row = _segment((self._dot, 0), (self._time, 1))
        self._exp_fig, self._profit_fig = _Figure(), _Figure()
        self._exp, self._exp_label, _ = _segment((self._exp_fig, 1))
        self._profit, self._profit_label, _ = _segment((self._profit_fig, 1))
        self._progress = _Progress(self)
        self._pct = _Figure()
        self._pct.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)     # "100%" wide (_scale): the bar the rest
        self._level, self._level_label, level_row = _segment((self._progress, 1), (self._pct, 0))
        self._slot = _Slot(self)
        segs = {"map": self._map, "exp": self._exp, "profit": self._profit, "level": self._level, "slot": self._slot}
        self._dividers: list[QFrame] = []
        for i, (key, seg) in enumerate(segs.items()):
            if i:
                div = QFrame(objectName="Divider")
                self._dividers.append(div)
                row.addWidget(div, 0, Qt.AlignVCenter)
            row.addWidget(seg, STRETCH[key])
        self._value_rows = [map_row, level_row]
        self._pause = self._button(self._pause_clicked, "Pause")
        self._stop = self._button(self._stop_clicked, "Stop")
        self._start = self._button(self._start_clicked, "Go")
        for b in (self._pause, self._stop, self._start):
            row.addWidget(b, 0, Qt.AlignVCenter)

    def _button(self, then, name: str) -> QPushButton:
        b = QPushButton(objectName=name)
        b.setCursor(Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(then)
        return b

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._opacity)

    def _scale(self) -> None:
        """Every size from the glass's height (as far as its width has room for: TALL_K): margins, gaps, the dots, the
        dividers, the status dot, the progress bar, the buttons and (qss) the fonts. Each line then fits again."""
        w, h = self.width() - 2 * SHADOW, self.height() - 2 * SHADOW
        u = max(1, min(h, round(w * BASE_H / BASE_W * TALL_K)))
        if u == self.unit:
            return
        self.unit = u
        pad = round(0.26 * u)
        lay = self.layout()
        lay.setContentsMargins(SHADOW + pad, SHADOW, SHADOW + pad, SHADOW)
        lay.setSpacing(round(0.19 * u))
        self._grip.setFixedSize(round(0.16 * u), round(0.5 * u))
        for div in self._dividers:
            div.setFixedSize(1, round(0.5 * u))
        d = max(6, round(0.13 * u))
        self._dot.setFixedSize(d, d)
        self._progress.setFixedHeight(max(4, round(0.1 * u)))
        for r in self._value_rows:
            r.setSpacing(round(0.09 * u))
        self._slot.layout().setContentsMargins(round(0.1 * u), 0, round(0.1 * u), 0)
        for b in (self._pause, self._stop, self._start):
            b.setFixedHeight(round(0.48 * u))
        self._restyle(force=True)
        for f in (self._time, self._exp_fig, self._profit_fig, self._pct):
            f.px = round(VALUE_K * u)
        f = QFont(self._pct.font())
        f.setPixelSize(self._pct.px)
        self._pct.setFixedWidth(QFontMetrics(f).horizontalAdvance("100%") + 2)
        self._refit()

    def _refit(self) -> None:
        for w in self.findChildren(QLabel):
            if isinstance(w, (_Line, _Figure)):
                w.fit()

    def _restyle(self, force: bool = False) -> None:
        """The accent and the palette the settings pick at the bar's size, in its style sheet and its buttons' marks
        (its glass is painted in the tint by _paint_glass); skipped when nothing changed (it refreshes every second)."""
        sheet = qss(self.settings, self.unit)
        if sheet != self.styleSheet() or force:
            self.setStyleSheet(sheet)
            self._marks()
            self._refit()

    def _marks(self) -> None:
        _accent, on_accent = accent_of(self.settings)
        px, dpr = round(0.15 * self.unit), self.devicePixelRatioF() or 1.0
        paused = self._paused()
        for b, kind, colour in ((self._pause, "play" if paused else "pause", palette().text),
                                (self._stop, "stop", ink(STOP)), (self._start, "play", on_accent)):
            b.setIcon(_mark(kind, px, colour, dpr))
            b.setIconSize(QSize(px, px))
        self._marked = paused

    def _retext(self) -> None:
        """The buttons' words and every tooltip in the language now (the figures: _fill)."""
        t, rtl = self.t, self.t.rtl
        for b, key in ((self._stop, "gb_stop"), (self._start, "gb_start")):
            b.setText(bidi.plain(" " + t(key), rtl))       # (a space from its mark: Qt sets them flush)
            b.setToolTip(t(key + "_tip"))
            b.setAccessibleName(t(key))
        self._pause_text()
        self._grip.setToolTip(t("tb_move"))
        self._grip.setAccessibleName(t("tb_move"))
        self.setToolTip(t("gb_open_tip"))
        self._time.setToolTip(t("gb_time_tip"))

    def _paused(self) -> bool:
        return bool(self.live is not None and self.live.running and self.scanner.paused())

    def _pause_text(self) -> None:
        t, rtl = self.t, self.t.rtl
        key = "gb_resume" if self._paused() else "gb_pause"
        self._pause.setText(bidi.plain(" " + t(key), rtl))
        self._pause.setToolTip(t(key + "_tip"))
        self._pause.setAccessibleName(t(key))
        if self._marked != self._paused():
            self._marks()

    # ---------------------------------------------------------------- what it shows

    def _up(self, text: str) -> str:
        """A label in small caps: English upper-cased (Hebrew has no case)."""
        return text if self.t.rtl else text.upper()

    def _fill(self) -> None:
        """The figures of the run now (grindlive.live), "–" with no run (marked right-to-left in Hebrew: a bare dash
        lays out left-to-right, at the far end of its segment from the label over it)."""
        t, rtl = self.t, self.t.rtl
        goals = [g for g in (grindlive.Goal.from_json(d) for d in self.settings["grind_goals"] or []) if g is not None]
        live = self.live = grindlive.live(self.kb, self.scanner.log_for(self.scanner.cid()), self.profiles.active,
                                          goals, now=time.time())
        on = live.running
        fig = lambda s: bidi.plain(bidi.ltr_block(s, rtl), rtl)
        label = lambda s: bidi.plain(self._up(s), rtl)
        dash = bidi.plain(DASH, rtl)
        # the map, over how the run stands and the grind time
        if on and live.map_name:
            self._map_label.set(self._up(live.map_name), lambda s: bidi.ltr_name(s, rtl))
        else:
            self._map_label.set(label(t("gb_map")))
        self._dot.set_state(live.state if on else "stopped")
        self._dot.setToolTip(t(f"gb_state_{self._dot.state}"))
        self._time.setText(fig(_clock(live.session.active_s)) if on else dash)
        self._time.setAccessibleName(f"{t(f'gb_state_{self._dot.state}')}: {self._time.text()}")
        # EXP and profit per hour
        for line, figure, key, n in ((self._exp_label, self._exp_fig, "gb_exp_h", live.session.exp_h),
                                     (self._profit_label, self._profit_fig, "gb_profit_h", live.session.profit_h)):
            line.set(label(t(key)))
            figure.setText(fig(_num(n)) if on and n is not None else dash)
            figure.setAccessibleName(f"{t(key)}: {figure.text()}")
        # the level, the time to the next one, its progress
        if on and live.level is not None:
            words = t("gb_level", lv=live.level, nxt=live.level + 1)
            if live.to_level_s is not None:
                words += " · " + t("gb_about", t=_duration(t, live.to_level_s))
            self._level_label.set(label(words))
        else:
            self._level_label.set(label(t("gb_level_none")))
        pct = live.exp_pct if on else None
        self._progress.set_value(pct / 100 if pct is not None else None)
        self._pct.setText(fig(f"{int(pct)}%") if pct is not None else dash)
        self._pct.setAccessibleName(f"{self._level_label.full()}: {self._pct.text()}")
        self._fill_slot(live, on)
        self._fill_buttons(on)

    def _fill_slot(self, live, on: bool) -> None:
        """The first goal still to reach (over when, or how far), else the last drop (over its name) and how many of
        it come an hour (its figure one left-to-right block in Hebrew)."""
        t, rtl = self.t, self.t.rtl
        slot, dash = self._slot, bidi.plain(DASH, rtl)
        goal = next((g for g in live.goals if not g.done), None)
        if goal is not None:
            g = goal.goal
            if g.kind == "item":
                name = g.item or str((self.kb.get(g.item_key) or {}).get("name") or g.item_key)
                slot.label.set(self._up(name), lambda s, n=g.target: bidi.plain(
                    self._up(t("gb_goal_item", n=f"{n:,}", item=bidi.ltr_block(s, rtl))), rtl))
            else:
                key, n = ("gb_goal_level", g.target) if g.kind == "level" else ("gb_goal_mesos", _num(g.target))
                slot.label.set(bidi.plain(self._up(t(key, n=n)), rtl))
            if not on:
                slot.value.set(dash)
            elif goal.eta_s is not None:
                slot.value.set(bidi.plain(t("gb_about", t=_duration(t, goal.eta_s)), rtl))
            else:
                have, target = (_num(goal.have), _num(g.target)) if g.kind == "mesos" else (f"{goal.have:,}", f"{g.target:,}")
                slot.value.set(bidi.plain(bidi.ltr_block(f"{have} / {target}", rtl), rtl))
            return
        drop = live.last_drop if on else None
        words = t("gb_last_drop")
        if drop is not None and drop[2] is not None:
            words += " · " + t("gb_per_h", n=bidi.ltr_block(per_hour(drop[2]), rtl))
        slot.label.set(bidi.plain(self._up(words), rtl))
        if drop is not None and drop[0]:
            slot.value.set(drop[0], lambda s: bidi.ltr_name(s, rtl))
        else:
            slot.value.set(dash)

    def _fill_buttons(self, on: bool) -> None:
        """Pause (Resume while paused) and Stop while a run goes; Start with none."""
        self._start.setVisible(not on)
        self._pause.setVisible(on)
        self._stop.setVisible(on)
        self._pause_text()

    def texts(self) -> dict[str, tuple[str, str]]:
        """What each segment says now, its label over its value, whole (before any "…")."""
        return {"map": (self._map_label.full(), self._time.text()),
                "exp": (self._exp_label.full(), self._exp_fig.text()),
                "profit": (self._profit_label.full(), self._profit_fig.text()),
                "level": (self._level_label.full(), self._pct.text()),
                "slot": (self._slot.label.full(), self._slot.value.full())}

    def flash(self) -> None:
        """A tracked item dropped or the character levelled up: the right slot's accent outline pulses once."""
        self._slot.flash()

    # ---------------------------------------------------------------- following the app

    def refresh(self) -> None:
        """Shown while settings["grind_bar"] is on (the toolbar's Grind button), hidden when it is off; the look the
        ⚙ panel picks taken again (the glass's opacity, the palette, the accent) and the figures filled."""
        if not self.settings["grind_bar"]:
            if self.isVisible():
                self.hide()
            return
        try:
            self._opacity = min(OPACITY_MAX, max(OPACITY_MIN, float(self.settings["npc_overlay_opacity"])))
        except (TypeError, ValueError):
            self._opacity = OPACITY_DEFAULT
        self._restyle()
        if not self.isVisible():
            self._place()
            self.show()
            set_capturable(self, self.settings)
        self._fill()
        self.update()

    def apply_language(self, t: I18n) -> None:
        self.t = t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self._retext()
        self.refresh()

    def set_kb(self, kb) -> None:
        self.kb = kb
        if self.isVisible():
            self._fill()

    # ---------------------------------------------------------------- the buttons, the clicks

    def _start_clicked(self, _=False) -> None:
        self.scanner.start()

    def _pause_clicked(self, _=False) -> None:
        if self.scanner.paused():
            self.scanner.resume_run()
        else:
            self.scanner.pause()

    def _stop_clicked(self, _=False) -> None:
        """The run ends (saved, as the Loot Log's Stop saves it); the app opens its summary in the grind window."""
        self.scanner.end()

    def _hide_clicked(self) -> None:
        """Its right-click Hide: the setting off (the toolbar's Grind button follows), hidden until switched back on.
        A running run goes on counting."""
        self.settings["grind_bar"] = False
        self.hide()
        self.closed.emit()

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        menu.addAction(self.t("gb_hide"), self._hide_clicked)
        menu.exec(e.globalPos())

    def _glass(self) -> QRect:
        return self.rect().adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)

    def mousePressEvent(self, e) -> None:
        """A press on the body (what its buttons and dots don't take: they take their own): its release opens the
        grind window. The rim resizes (EdgeResize)."""
        pos = e.position().toPoint()
        if e.button() == Qt.LeftButton and not self._edges_at(pos) and self._glass().contains(pos):
            self._pressed = e.globalPosition().toPoint()
            e.accept()
            return
        self._pressed = None
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        pressed, self._pressed = self._pressed, None
        if (pressed is not None and e.button() == Qt.LeftButton
                and (e.globalPosition().toPoint() - pressed).manhattanLength() < QApplication.startDragDistance()):
            e.accept()
            self.open_window.emit()
            return
        super().mouseReleaseEvent(e)

    # ---------------------------------------------------------------- size and place

    def _place(self) -> None:
        """Where it shows: where the player left it (still on a screen), else its default over the game."""
        g = self.settings["grind_bar_geom"]
        if valid_region(g):
            rect = QRect(int(g["x"]), int(g["y"]), max(self.minimumWidth(), int(g["w"])),
                         max(self.minimumHeight(), int(g["h"])))
            if any(s.availableGeometry().intersects(rect) for s in QGuiApplication.screens()):
                self.setGeometry(rect)
                self._placed = True
                return
        self.setGeometry(self.default_geometry())
        self._placed = True

    def default_geometry(self) -> QRect:
        """The megaphone strip's share of the game's picture (logical pixels), centred over it just above its bottom
        HUD strip; with no game window, 70 % of the primary screen's width in the strip's proportions, at its bottom.
        Never under the smallest size."""
        game = _game_rect()
        if game is not None:
            w, h = max(MIN_W, round(game.width() * GAME_W)), max(MIN_H, round(game.height() * GAME_H))
            bottom = game.y() + game.height() - round(game.height() * STRIP)
            glass = QRect(game.x() + (game.width() - w) // 2, bottom - h, w, h)
        else:
            scr = QGuiApplication.primaryScreen().availableGeometry()
            w = max(MIN_W, round(scr.width() * SCREEN_SHARE))
            h = max(MIN_H, round(w * BASE_H / BASE_W))
            glass = QRect(scr.x() + (scr.width() - w) // 2, scr.y() + scr.height() - SCREEN_GAP - h, w, h)
        return glass.adjusted(-SHADOW, -SHADOW, SHADOW, SHADOW)

    def resizeEvent(self, e) -> None:
        self._scale()
        self._geom.start()
        super().resizeEvent(e)

    def moveEvent(self, e) -> None:
        self._geom.start()
        super().moveEvent(e)

    def showEvent(self, e) -> None:
        self._clock.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:
        self._clock.stop()
        if self._placed:             # hidden or the app closing: keep the place now, not 400 ms later
            self._geom.stop()
            self._remember()
        super().hideEvent(e)

    def _remember(self) -> None:
        if self._placed:
            self.settings["grind_bar_geom"] = {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()}
