"""The little bar over the game: the NPCs-here window's own switch, the searches — where a monster lives, any NPC,
any map, any item, and whether an item is safe to sell (each asks the app to open ui/gamesearch.py in that mode) —
Cabs & Teleports for the way shown, the loot log and the tool windows. Like the NPCs window it floats over the game:
frameless, always on top, never taking the keyboard from it (clicks still work), dark glass the minimap reads never
see. Its ends are draggable (its sides; its top and bottom when the ◯ before the grip stands it upright): the buttons
wrap into as many lines as the length leaves room for, the other side following, and show their icons alone once the
words would take more than WORD_LINES_MAX lines; the length is kept in game_toolbar_width (game_toolbar_height
upright). Each button has a line icon (assets/icons/toolbar, Lucide's) drawn in its text's colour: small beside the
words, or alone (a short bar, or the ⚙'s icons mode) with the name in the tooltip. The ⚙ beside the ✕
opens the panel with the look of every window over the game, the icons mode and the bar's show/hide key
(_SettingsPanel below); the ✕ hides the bar (the app then says how to bring it back). Where the player left it is
kept in game_toolbar_pos; with none saved it opens just above the drawn minimap box."""
from __future__ import annotations

import sys

from PySide6.QtCore import QByteArray, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QIconEngine, QImage, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import bidi
from ..i18n import I18n
from ..store import ASSETS, DEFAULT_SETTINGS, Settings
from . import mapview, theme
from .controls import FlowLayout, Switch
from .glass import SHADOW, EdgeResize
from .hotkeybox import HotkeyBox
from .npcoverlay import (
    ACCENTS,
    FILL1,
    FILL2,
    GAP,
    GEOM_DEBOUNCE_MS,
    MUTED,
    OPACITY_DEFAULT,
    OPACITY_MAX,
    OPACITY_MIN,
    OPACITY_STEPS,
    TEXT,
    TINTS,
    _flags,
    _Header,
    _paint_glass,
    accent_of,
    apply_look,
    set_capturable,
)
from .npcoverlay import keep_over_game
from .regionpick import from_capture

SIDE, TOP, BOTTOM = SHADOW + 12, SHADOW + 8, SHADOW + 8    # content margins, past the glass's shadow rim
FLOW_GAP = 6                                              # between the buttons, and between the rows they wrap into
# the most rows (columns, upright) the buttons' words may wrap into: dragged shorter, the bar shows icons alone
WORD_LINES_MAX = 2
QT_MAX = 16777215                                         # Qt's "no limit" for a widget's size
KINDS = {"monster_npc": "tb_monster_npc", "map": "tb_maps", "item": "tb_items", "sell": "tb_sell"}  # search buttons, i18n keys
# the tool windows the bar shows and hides, after the loot log: each button is its window's setting -> its i18n key
TOOLS = {"scroll_planner": "tb_scrolls", "gear_advisor": "tb_gear", "craft_advisor": "tb_craft"}
# each button's line icon, by its i18n key: assets/icons/toolbar/<name>.svg (Lucide's, its LICENSE beside them)
ICON_DIR = ASSETS / "icons" / "toolbar"
ICONS = {"tb_npcs_here": "users", "tb_monster_npc": "ghost", "tb_maps": "map", "tb_items": "backpack",
         "tb_sell": "coins", "tb_rides": "car-taxi-front", "tb_loot": "scroll-text", "tb_scrolls": "sparkles",
         "tb_gear": "shield", "tb_craft": "hammer"}
ICON_PX = 18            # an icon alone on its button (icons mode)
WORD_ICON_PX = 15       # the small one beside the word
TOOL_ICON_PX = 16       # the bar's ⚙ and ✕
PANEL_W = 300 + 2 * SHADOW                                # the ⚙ panel's card ~300 px wide, its shadow around it
PANEL_SIDE = SHADOW + 16
# what "Reset to default look" puts back (the hotkey is no look: it stays)
LOOK_KEYS = ("overlay_tint", "overlay_accent", "npc_overlay_opacity", "game_toolbar_icons")


# ---------------------------------------------------------------- the line icons

_SVGS: dict[str, bytes] = {}


def _svg(name: str) -> bytes:
    if name not in _SVGS:
        _SVGS[name] = (ICON_DIR / f"{name}.svg").read_bytes()
    return _SVGS[name]


class _LineIcon(QIconEngine):
    """One of the bar's line icons drawn in a colour of the text around it, at the pixels the screen asks for (crisp
    at 125 % and 150 %): `colour` as it is, `on` on a lit (checked) button, `hover` under the mouse (a tool button's
    Active mode), faded when disabled."""

    def __init__(self, name: str, colour: str, on: str | None = None, hover: str | None = None):
        super().__init__()
        self._name = name
        self._colours = (colour, on or colour, hover or colour)
        self._cache: dict = {}

    def _colour(self, mode, state) -> QColor:
        normal, on, hover = self._colours
        c = theme.qcolor(on if state == QIcon.On else hover if mode == QIcon.Active else normal)
        if mode == QIcon.Disabled:
            c.setAlphaF(c.alphaF() * 0.4)
        return c

    def scaledPixmap(self, size, mode, state, scale):
        key = (size.width(), size.height(), mode, state, scale)
        pm = self._cache.get(key)
        if pm is None:
            c = self._colour(mode, state)
            px = QSize(max(1, round(size.width() * scale)), max(1, round(size.height() * scale)))
            img = QImage(px, QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            p.setOpacity(c.alphaF())
            QSvgRenderer(QByteArray(_svg(self._name).replace(b"currentColor", c.name().encode()))).render(
                p, QRectF(0, 0, px.width(), px.height()))
            p.end()
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(scale)
            self._cache[key] = pm
        return pm

    def pixmap(self, size, mode, state):
        return self.scaledPixmap(size, mode, state, 1.0)

    def paint(self, painter, rect, mode, state):
        dpr = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
        painter.drawPixmap(rect, self.scaledPixmap(rect.size(), mode, state, dpr))

    def clone(self):
        return _LineIcon(self._name, *self._colours)


def line_icon(name: str, colour: str, on: str | None = None, hover: str | None = None) -> QIcon:
    """assets/icons/toolbar/<name>.svg as an icon in these colours (see _LineIcon)."""
    return QIcon(_LineIcon(name, colour, on, hover))


def qss(settings) -> str:
    """The bar's own style: the accent that lights a lit button, from the settings, and the room an icon alone takes
    on its button (iconOnly: the ⚙'s icons mode, or a bar dragged too short for the words)."""
    accent, on_accent = accent_of(settings)
    return f"""
QPushButton {{ background: {FILL1}; color: {TEXT}; border: none; border-radius: 8px;
              padding: 5px 10px; text-align: center; }}
QPushButton[iconOnly="true"] {{ padding: 6px 9px; }}
QPushButton:hover {{ background: {FILL2}; }}
QPushButton:checked, QPushButton[on="true"] {{ background: {accent}; color: {on_accent}; }}
QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: {FILL2}; }}
"""


class _Grip(QWidget):
    """The dots at the bar's end: dragging them moves it (the buttons around them still click)."""

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.OpenHandCursor)
        self._grab = None          # (its window is self.window(), not kept)
        self.set_upright(False)

    def set_upright(self, upright: bool) -> None:
        """Its dots across an upright bar (grip-horizontal), down a lying one (grip-vertical)."""
        self.setFixedSize(28, 12) if upright else self.setFixedSize(12, 28)
        self._icon = line_icon("grip-horizontal" if upright else "grip-vertical", MUTED)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        s = 20                     # the dots sit in the icon's middle third: the widget is only as wide as they are
        self._icon.paint(p, QRect((self.width() - s) // 2, (self.height() - s) // 2, s, s))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._grab = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._grab is not None and e.buttons() & Qt.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._grab)

    def mouseReleaseEvent(self, e):
        self._grab = None


def _lines(lengths: list[int], room: int, gap: int) -> int:
    """How many lines (rows, or columns upright) items of these lengths wrap into within `room`, the way the bar's
    layout lays them out: a line takes the next item while it still fits, and every line takes at least one."""
    lines, used = 0, None
    for n in lengths:
        if used is None or used + gap + n > room:
            lines, used = lines + 1, n
        else:
            used += gap + n
    return lines


class _BarLayout(FlowLayout):
    """The bar's buttons in a row that wraps into rows, or (upright) a column that wraps into columns.

    It never says its height follows its width (hasHeightForWidth): Qt on Windows then refuses a system resize
    narrower than the width the window's current height fits, so dragging the bar's side only ever made it wider
    (2026-10-11, the side dragged 500 px in stayed at the one-row width). The bar sets its own other side from
    extent() as its length changes."""

    def __init__(self, spacing: int):
        super().__init__(spacing=spacing)
        self.upright = False

    def hasHeightForWidth(self):
        return False

    def setGeometry(self, rect):
        QLayout.setGeometry(self, rect)
        if self.upright:
            self._columns(rect, apply=True)
        else:
            self._arrange(rect, apply=True)

    def extent(self, room: int) -> int:
        """The other side the items take within this length: the height a row of `room` wraps them into, or upright
        the width a column of `room` wraps them into."""
        if self.upright:
            return self._columns(QRect(0, 0, 0, room), apply=False)
        return self._arrange(QRect(0, 0, room, 0), apply=False)

    def _columns(self, rect, apply: bool) -> int:
        """Columns of items top to bottom that fit the height, from the leading side (right in Hebrew); each column
        as wide as its widest item, its buttons stretched to that width (a menu's look), the small tool buttons
        centred. Returns the width used."""
        cols, col, y = [], [], 0
        for item in self._items:
            if item.isEmpty():
                continue
            h = item.sizeHint().height()
            if col and y + self._v + h > rect.height():
                cols.append(col)
                col, y = [], 0
            y += (self._v if col else 0) + h
            col.append(item)
        if col:
            cols.append(col)
        x, rtl = 0, self._rtl()
        for col in cols:
            w = max(self._width(item) for item in col)
            y = rect.y()
            for item in col:
                ih = item.sizeHint().height()
                iw = w if isinstance(item.widget(), QPushButton) else self._width(item)
                inset = (w - iw) // 2
                left = rect.right() - x - w + 1 + inset if rtl else rect.x() + x + inset
                if apply:
                    item.setGeometry(QRect(left, y, iw, ih))
                y += ih + self._v
            x += w + self._h
        return x - self._h if cols else 0


# ---------------------------------------------------------------- the ⚙ panel's own controls

# the ⚙ panel's style: a title, small muted section heads, labels with their picked value, one-line hints (its
# accent-lit controls paint themselves: the swatches' rings, the slider, the switch, the key box)
PANEL_QSS = f"""
QLabel {{ background: transparent; }}
#Title {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
#Section {{ color: {MUTED}; font-size: 11px; font-weight: 700; }}
#Label {{ color: {TEXT}; font-size: 13px; }}
#Picked {{ color: {MUTED}; font-size: 12px; }}
#Value {{ color: {TEXT}; font-size: 13px; font-weight: 600; }}
#Hint {{ color: {MUTED}; font-size: 11px; }}
QFrame#Rule {{ background: rgba(255,255,255,0.08); border: none; }}
QToolButton#Close {{ background: transparent; color: {MUTED}; border: none; border-radius: 6px;
                     padding: 2px 7px; font-size: 13px; }}
QToolButton#Close:hover {{ background: {FILL2}; color: {TEXT}; }}
QToolButton#Reset {{ background: transparent; color: {MUTED}; border: none; padding: 4px 0;
                     font-size: 12px; font-weight: 600; }}
QToolButton#Reset:hover {{ color: {TEXT}; }}
QToolButton#Reset:disabled {{ color: rgba(235,235,245,0.30); }}
"""


class _Swatch(QPushButton):
    """One colour to pick: a glass tint as a small tile of that glass, an accent as a dot of it. The chosen one is
    ringed in the accent (an accent's own dot: in itself), with a check."""

    def __init__(self, kind: str, key: str, colour: str, check: str):
        super().__init__(checkable=True)
        self._kind = kind
        self._fill, self._ring = QColor(colour), QColor(colour)
        self._check = line_icon("check", check)
        self.setProperty("key", key)
        self.setProperty("colour", colour)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        if kind == "tint":
            self.setMinimumSize(40, 36)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setFixedSize(32, 32)

    def sizeHint(self):
        return QSize(48, 36) if self._kind == "tint" else QSize(32, 32)

    def set_ring(self, colour: str) -> None:
        if QColor(colour) != self._ring:
            self._ring = QColor(colour)
            self.update()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on, hover = self.isChecked(), self.underMouse()
        r = QRectF(self.rect())
        if self._kind == "tint":
            if on:
                p.setPen(QPen(self._ring, 2))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 10, 10)
            tile = r.adjusted(4, 4, -4, -4)
            p.setPen(Qt.NoPen)
            p.setBrush(self._fill)
            p.drawRoundedRect(tile, 7, 7)
            sheen = QLinearGradient(tile.topLeft(), tile.bottomLeft())      # the glass's own light at its top
            sheen.setColorAt(0.0, QColor(255, 255, 255, 34))
            sheen.setColorAt(0.55, QColor(255, 255, 255, 0))
            p.setBrush(sheen)
            p.drawRoundedRect(tile, 7, 7)
            p.setPen(QPen(QColor(255, 255, 255, 115 if hover and not on else 46), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(tile.adjusted(0.5, 0.5, -0.5, -0.5), 6.5, 6.5)
            mark = 16
        else:
            d = min(r.width(), r.height())
            c = r.center()
            if on:
                p.setPen(QPen(self._ring, 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, d / 2 - 1, d / 2 - 1)
            elif hover:
                p.setPen(QPen(QColor(255, 255, 255, 90), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, d / 2 - 1, d / 2 - 1)
            p.setPen(Qt.NoPen)
            p.setBrush(self._fill)
            p.drawEllipse(c, d / 2 - 4.5, d / 2 - 4.5)
            mark = 14
        if on:
            self._check.paint(p, QRect(round(r.center().x() - mark / 2), round(r.center().y() - mark / 2), mark, mark))


class _StepSlider(QWidget):
    """The transparency as a slider over its few steps: the track lit in the accent up to the knob, a tick at each
    step; a click or a drag lands on the nearest one (mirrored in Hebrew: the first step on the right)."""

    changed = Signal(int)           # the step the player moved it to
    KNOB = 16

    def __init__(self, steps: int):
        super().__init__()
        self._n = steps
        self._i = 0
        self._accent = QColor(TEXT)
        self.setFixedHeight(24)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def index(self) -> int:
        return self._i

    def set_index(self, i: int) -> None:
        i = max(0, min(self._n - 1, i))
        if i != self._i:
            self._i = i
            self.update()

    def set_accent(self, colour: str) -> None:
        if QColor(colour) != self._accent:
            self._accent = QColor(colour)
            self.update()

    def _x(self, i: int) -> float:
        frac = i / (self._n - 1)
        if self.layoutDirection() == Qt.RightToLeft:
            frac = 1 - frac
        return self.KNOB / 2 + frac * (self.width() - self.KNOB)

    def _drag(self, x: float) -> None:
        i = min(range(self._n), key=lambda k: abs(self._x(k) - x))
        if i != self._i:
            self._i = i
            self.update()
            self.changed.emit(i)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag(e.position().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._drag(e.position().x())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cy = self.height() / 2
        start, knob = self._x(0), self._x(self._i)
        left, right = self.KNOB / 2, self.width() - self.KNOB / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 38))
        p.drawRoundedRect(QRectF(left - 2, cy - 2, right - left + 4, 4), 2, 2)
        p.setBrush(self._accent)
        lo, hi = min(start, knob), max(start, knob)
        p.drawRoundedRect(QRectF(lo - 2, cy - 2, hi - lo + 4, 4), 2, 2)
        for k in range(self._n):         # a small tick at each step, faint on the unlit track
            if k != self._i:
                lit = (lo <= self._x(k) <= hi)
                p.setBrush(QColor(255, 255, 255, 150 if lit else 70))
                p.drawEllipse(QRectF(self._x(k) - 2, cy - 2, 4, 4))
        p.setBrush(QColor(0, 0, 0, 60))                 # the knob, on a soft shadow
        p.drawEllipse(QRectF(knob - self.KNOB / 2, cy - self.KNOB / 2 + 1, self.KNOB, self.KNOB))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(knob - self.KNOB / 2, cy - self.KNOB / 2, self.KNOB, self.KNOB))


class _GlassSwitch(Switch):
    """controls.Switch drawn for the dark glass: its track in the windows' accent when on, a faint white one off."""

    W, H = 40, 24

    def __init__(self):
        super().__init__(False)
        self._accent = QColor(TEXT)
        self.setFocusPolicy(Qt.NoFocus)

    def sizeHint(self):
        return QSize(self.W, self.H)

    def set_accent(self, colour: str) -> None:
        if QColor(colour) != self._accent:
            self._accent = QColor(colour)
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, t = self.W, self.H, self._pos
        track = QRectF(0, (self.height() - h) / 2, w, h)
        off, on = QColor(255, 255, 255, 46), self._accent
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                          int(off.blue() + (on.blue() - off.blue()) * t), int(off.alpha() + (255 - off.alpha()) * t)))
        p.drawRoundedRect(track, h / 2, h / 2)
        rtl = self.layoutDirection() == Qt.RightToLeft
        x0, x1 = 2, w - h + 2
        x = x0 + (x1 - x0) * (1 - t if rtl else t)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QRectF(x, track.top() + 3, h - 4, h - 4))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, track.top() + 2, h - 4, h - 4))


class _SettingsPanel(QWidget):
    """The bar's ⚙ panel, a small card in the same dark glass over the game. Look: the glass colour of every window
    over the game as tiles of each tint and the lit buttons' accent as dots, the picked one ringed and named;
    Transparency: their glass's opacity on a slider; Toolbar: icons instead of words, and the bar's show/hide key in
    the same key box Settings has. Each choice is written, applies at once to every window and stays; "Reset to
    default look" puts the look back. ✕, the ⚙ again or Esc closes it (Esc once the panel has been clicked into:
    like the search window it takes the keyboard only then, never on opening)."""

    changed = Signal()          # a look choice applied: every window over the game follows (app.py wires it)
    hotkey_changed = Signal()   # the bar's key picked or cleared here: the app binds the new one

    def __init__(self, bar):
        # like the search window, not the bar's own flags: it takes the keyboard once clicked, for Esc and the key box
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._bar = bar
        self._settings = bar._settings
        self.t = bar.t
        self.setLayoutDirection(Qt.RightToLeft if self.t.rtl else Qt.LeftToRight)
        self._opacity = OPACITY_DEFAULT
        self.setFixedWidth(PANEL_W)
        self.setStyleSheet(PANEL_QSS)
        col = QVBoxLayout(self)
        col.setContentsMargins(PANEL_SIDE, TOP + 4, PANEL_SIDE, BOTTOM + 6)
        col.setSpacing(0)
        # the title row: drags the panel; its ✕ closes it
        head = _Header()
        hrow = QHBoxLayout(head)
        hrow.setContentsMargins(0, 0, 0, 0)
        hrow.setSpacing(8)
        self._title = QLabel(objectName="Title")
        self._close = QToolButton(objectName="Close", text=theme.SYMBOL_ICONS["close"])
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.clicked.connect(self._close_clicked)
        hrow.addWidget(self._title, 1)
        hrow.addWidget(self._close, 0, Qt.AlignTop)
        col.addWidget(head)
        # Look: the glass tint as tiles, the accent as dots, each named beside its label
        self._look_head = self._section(col, first=True)
        self._tint_label, self._tint_name = self._label_row(col)
        col.addSpacing(8)
        self._tints = self._swatches("tint", TINTS, lambda k: "#{:02x}{:02x}{:02x}".format(*TINTS[k][1]),
                                     self._pick_tint, spacing=8)
        col.addWidget(self._tints)
        col.addSpacing(16)
        self._accent_label, self._accent_name = self._label_row(col)
        col.addSpacing(8)
        self._accents = self._swatches("accent", ACCENTS, lambda k: ACCENTS[k][1], self._pick_accent)
        col.addWidget(self._accents)
        # Transparency: the windows' glass opacity, the steps Settings offered (OPACITY_STEPS)
        self._opacity_head = self._section(col)
        self._opacity_label, self._opacity_value = self._label_row(col, value="Value")
        col.addSpacing(6)
        self._slider = _StepSlider(len(OPACITY_STEPS))
        self._slider.changed.connect(lambda i: self._pick_opacity(OPACITY_STEPS[i]))
        col.addWidget(self._slider)
        # Toolbar: icons instead of words, and the key that shows or hides the bar
        self._bar_head = self._section(col)
        row = QHBoxLayout()
        row.setSpacing(12)
        self._icons_label = QLabel(objectName="Label")
        self._icons = _GlassSwitch()
        self._icons.setCursor(Qt.PointingHandCursor)
        self._icons.clicked.connect(self._pick_icons)
        row.addWidget(self._icons_label, 1)
        row.addWidget(self._icons, 0, Qt.AlignVCenter)
        col.addLayout(row)
        col.addSpacing(3)
        self._icons_hint = self._hint(col)
        col.addSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(12)
        self._hotkey_label = QLabel(objectName="Label")
        self._hotkey = HotkeyBox(self._settings["game_toolbar_hotkey"], self.t, glass=True)
        self._hotkey.changed.connect(self._pick_hotkey)
        row.addWidget(self._hotkey_label, 1)
        row.addWidget(self._hotkey, 0, Qt.AlignVCenter)
        col.addLayout(row)
        col.addSpacing(3)
        self._hotkey_hint = self._hint(col)
        # Reset to default look, at the leading edge under a hairline
        col.addSpacing(14)
        rule = QFrame(objectName="Rule")
        rule.setFixedHeight(1)
        col.addWidget(rule)
        col.addSpacing(6)
        row = QHBoxLayout()
        self._reset = QToolButton(objectName="Reset")
        self._reset.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._reset.setAutoRaise(True)              # the icon brightens with the text under the mouse
        self._reset.setCursor(Qt.PointingHandCursor)
        self._reset.setFocusPolicy(Qt.NoFocus)
        self._reset.setIcon(line_icon("rotate-ccw", MUTED, hover=TEXT))
        self._reset.setIconSize(QSize(14, 14))
        self._reset.clicked.connect(self._reset_look)
        row.addWidget(self._reset)
        row.addStretch(1)
        col.addLayout(row)
        self.refresh()

    # ------------------------------------------------------------ the panel

    @staticmethod
    def _section(col, first: bool = False) -> QLabel:
        """A small muted head over a section, with room above it."""
        col.addSpacing(12 if first else 20)
        lb = QLabel(objectName="Section")
        col.addWidget(lb)
        col.addSpacing(10)
        return lb

    @staticmethod
    def _label_row(col, value: str = "Picked") -> tuple[QLabel, QLabel]:
        """A label at the leading edge and what it is set to at the trailing one."""
        row = QHBoxLayout()
        row.setSpacing(8)
        label, picked = QLabel(objectName="Label"), QLabel(objectName=value)
        row.addWidget(label, 1)
        row.addWidget(picked)
        col.addLayout(row)
        return label, picked

    @staticmethod
    def _hint(col) -> QLabel:
        """A one- or two-line hint under its row, muted."""
        lb = QLabel(objectName="Hint")
        lb.setWordWrap(True)
        col.addWidget(lb)
        return lb

    def _swatches(self, kind: str, presets: dict, colour_of, picked, spacing: int = 0) -> QWidget:
        """A row of colours, one per preset, across the panel's width: tiles side by side (spacing), or dots spread
        evenly (no spacing: stretches between them)."""
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing)
        for i, key in enumerate(presets):
            if i and not spacing:
                row.addStretch(1)
            check = TEXT if kind == "tint" else ACCENTS[key][2]
            b = _Swatch(kind, key, colour_of(key), check)
            b.clicked.connect(lambda _=False, k=key: picked(k))
            row.addWidget(b)
        return w

    def refresh(self) -> None:
        """Every choice back in step with the settings (the Settings dialog may have changed them), and the
        panel's own glass at the transparency they give."""
        t, rtl, s = self.t, self.t.rtl, self._settings
        accent, _ = accent_of(s)
        self._title.setText(bidi.plain(t("tbs_title"), rtl))
        self._close.setAccessibleName(t("tbs_close"))
        self._close.setToolTip(t("tbs_close"))
        for lb, key in ((self._look_head, "tbs_look"), (self._opacity_head, "tbs_opacity_head"),
                        (self._bar_head, "tbs_bar")):
            lb.setText(bidi.plain(t(key) if rtl else t(key).upper(), rtl))
        tint = s["overlay_tint"] if s["overlay_tint"] in TINTS else next(iter(TINTS))      # a stale name: today's
        accent_key = s["overlay_accent"] if s["overlay_accent"] in ACCENTS else next(iter(ACCENTS))
        for lb, key in ((self._tint_label, "tbs_tint"), (self._tint_name, TINTS[tint][0]),
                        (self._accent_label, "tbs_accent"), (self._accent_name, ACCENTS[accent_key][0]),
                        (self._opacity_label, "tbs_opacity"), (self._icons_label, "tbs_icons"),
                        (self._icons_hint, "tbs_icons_hint"), (self._hotkey_label, "tb_hotkey"),
                        (self._hotkey_hint, "tb_hotkey_hint")):
            lb.setText(bidi.plain(t(key), rtl))
        for lb in (self._icons_hint, self._hotkey_hint):
            # Hebrew: two pixels' room at the right, where a line wrapped to the full width drew its first letter
            # past the label's edge, cut off (the wrap measures whole pixels, the glyphs overhang)
            lb.setContentsMargins(0, 0, 2 if rtl else 0, 0)
        self._reset.setText(bidi.plain(t("tbs_reset"), rtl))
        for row, chosen, presets in ((self._tints, tint, TINTS), (self._accents, accent_key, ACCENTS)):
            for b in row.findChildren(_Swatch):
                key = b.property("key")
                b.setChecked(key == chosen)
                b.set_ring(accent if row is self._tints else b.property("colour"))
                b.setToolTip(t(presets[key][0]))
                b.setAccessibleName(t(presets[key][0]))
        try:
            op = float(s["npc_overlay_opacity"])
        except (TypeError, ValueError):
            op = OPACITY_DEFAULT
        self._opacity = min(OPACITY_MAX, max(OPACITY_MIN, op))
        self._slider.set_index(min(range(len(OPACITY_STEPS)), key=lambda i: abs(OPACITY_STEPS[i] - self._opacity)))
        self._slider.set_accent(accent)
        self._slider.setAccessibleName(t("tbs_opacity"))
        self._opacity_value.setText(bidi.ltr_block(f"{round(self._opacity * 100)}%", rtl))
        self._icons.setChecked(bool(s["game_toolbar_icons"]))
        self._icons.set_accent(accent)
        self._icons.setAccessibleName(t("tbs_icons"))
        self._hotkey.set_key(s["game_toolbar_hotkey"])
        self._hotkey.set_accent(accent)
        self._hotkey.set_label(t("tb_hotkey"))
        self._reset.setEnabled(any(s[k] != DEFAULT_SETTINGS[k] for k in LOOK_KEYS))
        self.resize(PANEL_W, self.layout().totalHeightForWidth(PANEL_W))     # the hints wrapped at its width
        self.update()

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._opacity)

    def place_under(self, btn) -> None:
        """Under the ⚙ that opened it, centred on it, kept on its screen."""
        g = btn.mapToGlobal(QPoint(0, btn.height()))
        screen = QGuiApplication.screenAt(g) or QGuiApplication.primaryScreen()
        room = screen.availableGeometry()
        x = min(max(room.left(), g.x() + btn.width() // 2 - self.width() // 2),
                max(room.left(), room.right() - self.width() + 1))
        y = min(max(room.top(), g.y() + 4), max(room.top(), room.bottom() - self.height() + 1))
        self.move(x, y)

    # ------------------------------------------------------------ the choices

    def _pick_tint(self, key: str) -> None:
        self._settings["overlay_tint"] = key
        self._applied()

    def _pick_accent(self, key: str) -> None:
        self._settings["overlay_accent"] = key
        self._applied()

    def _pick_icons(self, _=False) -> None:
        self._settings["game_toolbar_icons"] = self._icons.isChecked()
        self._applied()

    def _pick_opacity(self, value: float) -> None:
        self._settings["npc_overlay_opacity"] = value
        self._applied()

    def _reset_look(self, _=False) -> None:
        """The look the app starts with: today's dark glass, green accent, 85 % and words on the buttons."""
        for key in LOOK_KEYS:
            self._settings[key] = DEFAULT_SETTINGS[key]
        self._applied()

    def _pick_hotkey(self, name: str) -> None:
        """A key picked in the box (or cleared): written now, and the app binds it (hotkey_changed)."""
        self._settings["game_toolbar_hotkey"] = name
        self.refresh()
        self.hotkey_changed.emit()

    def _applied(self) -> None:
        """One choice, on everything at once: written (it stays), the glass tint every _paint_glass paints,
        this panel's and the bar's own style and texts, then every other window over the game follows."""
        apply_look(self._settings)
        self.refresh()
        self._bar.look_followed()
        self.changed.emit()

    def _close_clicked(self, _=False) -> None:
        self.hide()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(e)

    def apply_language(self, t: I18n) -> None:
        self.t = t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self._hotkey.retext(t)
        self.refresh()


class GameToolbar(EdgeResize, QWidget):
    """The bar itself. The NPCs-here button flips settings["npc_overlay"] (npc_toggled: the window follows),
    the search buttons ask for their search (search_requested: "monster_npc", "map", "item" or "sell"), and
    the ✕ turns the bar itself off (closed: the app says how to bring it back). Its length is dragged shorter and
    longer (its width; its height upright, the ◯ before the grip turning it), the buttons wrapping into lines and
    showing icons alone once the words would take more than WORD_LINES_MAX lines; the ⚙ opens the panel with the
    look, the icons mode and the bar's key. Clicks work but it never takes the keyboard from the game, and the
    minimap reads never see it. Its place is kept in game_toolbar_pos, its length in game_toolbar_width (or
    game_toolbar_height upright), the way it stands in game_toolbar_vertical."""

    search_requested = Signal(str)     # which search to open: "monster_npc" | "map" | "item" | "sell"
    npc_toggled = Signal()             # settings["npc_overlay"] flipped: the NPCs-here window follows
    rides_toggled = Signal()           # settings["game_rides"] flipped: a way shown is found again, on foot or riding
    loot_toggled = Signal()            # settings["loot_overlay"] flipped: the loot log's window follows
    tool_toggled = Signal(str)         # a TOOLS setting flipped ("scroll_planner" | "gear_advisor"): its window follows
    look_changed = Signal()            # a ⚙ panel choice: every window over the game re-styles and repaints
    closed = Signal()                  # the ✕ turned the bar off: Settings' switch and the tray item follow
    hotkey_changed = Signal()          # the ⚙ panel picked or cleared the bar's key: the app binds it

    def __init__(self, settings: Settings, t: I18n):
        super().__init__(None, _flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)          # hovering a side shows the resize cursor
        self._settings = settings
        self.t = t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self._opacity = OPACITY_DEFAULT
        self._placed = False                 # geometry applied at least once: there is a place to remember
        self._mode = ""                      # the search window's mode, lit on its button ("" none)
        self._panel: _SettingsPanel | None = None   # the ⚙ panel, made on the first ask
        self._fitting = False                # our own fit of its size, not the player's drag to remember
        self._length_set = -1                # the length the settings last gave: a length past it is a drag
        self._icons_shown: bool | None = None   # icons alone on the buttons now (the ⚙'s choice, or too short)
        self._sizes: dict[bool, list[tuple[int, int]]] = {}   # words / icons alone -> each item's (width, height)
        self._geom = QTimer(self, singleShot=True, interval=GEOM_DEBOUNCE_MS, timeout=self._remember)
        self._lengths = QTimer(self, singleShot=True, interval=GEOM_DEBOUNCE_MS, timeout=self._remember_length)
        # the other side fitted just after a resize, never inside it: a resize of its own from resizeEvent cancelled
        # Windows' drag of the bar's side, every step of it (2026-10-11)
        self._refit = QTimer(self, singleShot=True, interval=0,
                             timeout=lambda: self._fit(self.height() if self._upright() else self.width()))
        self.setStyleSheet(qss(settings))
        self._build()

    # ------------------------------------------------------------ the bar

    def _build(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(SIDE, TOP, SIDE, BOTTOM)
        col.setSpacing(0)
        col.setSizeConstraint(QLayout.SetNoConstraint)    # the bar sets its own limits (_apply_size)
        self._flow = _BarLayout(FLOW_GAP)
        col.addLayout(self._flow)
        # the ◯ before the grip's dots: the bar upright (a column) or lying (a row)
        self._orient = QToolButton(objectName="Orient")
        self._orient.setIcon(line_icon("circle", MUTED, hover=TEXT))
        self._orient.setIconSize(QSize(TOOL_ICON_PX - 2, TOOL_ICON_PX - 2))
        self._orient.setAutoRaise(True)
        self._orient.setCursor(Qt.PointingHandCursor)
        self._orient.setFocusPolicy(Qt.NoFocus)
        self._orient.clicked.connect(self._orient_clicked)
        self._flow.addWidget(self._orient)
        self._grip = _Grip()
        self._flow.addWidget(self._grip)
        self._npcs = QPushButton(checkable=True)
        self._npcs.setCursor(Qt.PointingHandCursor)
        self._npcs.setFocusPolicy(Qt.NoFocus)
        self._npcs.clicked.connect(self._npcs_clicked)
        self._flow.addWidget(self._npcs)
        self._search: dict[str, QPushButton] = {}
        for kind in KINDS:
            b = QPushButton()
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, k=kind: self.search_requested.emit(k))
            self._search[kind] = b
            self._flow.addWidget(b)
        # the way to a found NPC or map: with cabs and NPC teleports, or on foot (the owner's, 2026-10-10)
        self._rides = QPushButton(checkable=True)
        self._rides.setCursor(Qt.PointingHandCursor)
        self._rides.setFocusPolicy(Qt.NoFocus)
        self._rides.clicked.connect(self._rides_clicked)
        self._flow.addWidget(self._rides)
        # the loot log's window, as the NPCs-here button is its window's: the checkable button is the setting
        self._loot = QPushButton(checkable=True)
        self._loot.setCursor(Qt.PointingHandCursor)
        self._loot.setFocusPolicy(Qt.NoFocus)
        self._loot.clicked.connect(self._loot_clicked)
        self._flow.addWidget(self._loot)
        # the scroll planner's, gear advisor's and crafting advisor's windows, each button its window's setting
        self._tools: dict[str, QPushButton] = {}
        for key in TOOLS:
            b = QPushButton(checkable=True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, k=key: self._tool_clicked(k))
            self._tools[key] = b
            self._flow.addWidget(b)
        # the ⚙: the panel with the look, the icons mode and the bar's key; then the ✕
        self._gear = QToolButton(objectName="Gear")
        self._close = QToolButton(objectName="Close")
        for b, name, slot in ((self._gear, "settings", self._gear_clicked), (self._close, "x", self._close_clicked)):
            b.setIcon(line_icon(name, MUTED, hover=TEXT))
            b.setIconSize(QSize(TOOL_ICON_PX, TOOL_ICON_PX))
            b.setAutoRaise(True)             # the icon brightens under the mouse (its Active mode)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(slot)
            self._flow.addWidget(b)
        self._retext()

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._opacity)

    # ------------------------------------------------------------ text and icons (all of it, for apply_language)

    def _buttons(self):
        """Every button on the bar with its i18n key: the texts, tooltips and icons follow the language."""
        yield self._npcs, "tb_npcs_here"
        for kind, key in KINDS.items():
            yield self._search[kind], key
        yield self._rides, "tb_rides"
        yield self._loot, "tb_loot"
        for key, text in TOOLS.items():
            yield self._tools[key], text

    def _paint_icon(self, b: QPushButton, key: str) -> None:
        """The button's line icon in its text's colours: the text colour, the accent's own text colour while lit
        (checked, or a search's mode lit by its "on")."""
        _, on_fill = accent_of(self._settings)
        b.setIcon(line_icon(ICONS[key], on_fill if b.property("on") else TEXT, on=on_fill))

    def _retext(self) -> None:
        t = self.t
        upright = bool(self._settings["game_toolbar_vertical"])
        if upright != self._flow.upright:       # the way it stands first: the grip's size is measured with it
            self._flow.upright = upright
            self._grip.set_upright(upright)
        self._grip.setAccessibleName(t("tb_move"))
        self._grip.setToolTip(t("tb_move"))
        self._orient.setAccessibleName(t("tb_horizontal" if upright else "tb_vertical"))
        self._orient.setToolTip(t("tb_horizontal" if upright else "tb_vertical"))
        for b, key in self._buttons():
            self._paint_icon(b, key)
        self._gear.setAccessibleName(t("tbs_title"))
        self._gear.setToolTip(t("tbs_title"))
        self._close.setAccessibleName(t("tb_close"))
        self._close.setToolTip(t("tb_close"))
        self._measure()
        self._apply_size()

    def _label(self, icons: bool) -> None:
        """The buttons' words (a small icon beside each, the tip in the tooltip), or their icons alone (the name in
        the tooltip and the accessible name, for what the icon is)."""
        t, rtl = self.t, self.t.rtl
        for b, key in self._buttons():
            name = t(key)
            if icons:
                b.setText("")
                b.setIconSize(QSize(ICON_PX, ICON_PX))
                b.setToolTip(name)
            else:
                b.setText(bidi.plain(name, rtl).replace("&", "&&"))   # "&" alone: Qt's shortcut mark
                b.setIconSize(QSize(WORD_ICON_PX, WORD_ICON_PX))
                b.setToolTip(t(key + "_tip"))
            b.setAccessibleName(name)
            if b.property("iconOnly") != icons:
                b.setProperty("iconOnly", icons)         # its padding (qss)
                b.style().unpolish(b)
                b.style().polish(b)
        self._icons_shown = icons

    def _measure(self) -> None:
        """Every item's size with words and with icons alone, so the bar knows which fit a length before it shows
        them (the language, the accent's bold lit text and the look change them; a drag doesn't)."""
        items = [self._flow.itemAt(i) for i in range(self._flow.count())]
        for icons in (False, True):
            self._label(icons)
            self._sizes[icons] = [(FlowLayout._width(it), it.sizeHint().height()) for it in items if not it.isEmpty()]

    # ------------------------------------------------------------ its length (the buttons wrap)

    def _upright(self) -> bool:
        return self._flow.upright

    def _pads(self) -> tuple[int, int]:
        """The margins along the bar's length and across it."""
        return (TOP + BOTTOM, 2 * SIDE) if self._upright() else (2 * SIDE, TOP + BOTTOM)

    def _wants_icons(self, length: int) -> bool:
        """Icons alone: the ⚙ asks for them, or this length would wrap the words into more than WORD_LINES_MAX
        lines."""
        if self._settings["game_toolbar_icons"]:
            return True
        axis = 1 if self._upright() else 0
        return _lines([s[axis] for s in self._sizes[False]], length - self._pads()[0], FLOW_GAP) > WORD_LINES_MAX

    def _limits(self) -> tuple[int, int]:
        """The shortest the bar goes along its length — its biggest single item with icons alone — and its natural
        one-line length (with words, unless the ⚙ asks for icons)."""
        axis = 1 if self._upright() else 0
        pad = self._pads()[0]
        line = self._sizes[bool(self._settings["game_toolbar_icons"])]
        return (max(s[axis] for s in self._sizes[True]) + pad,
                sum(s[axis] for s in line) + FLOW_GAP * (len(line) - 1) + pad)

    def _apply_size(self) -> None:
        """The length the settings give (None: its natural one-line length), clamped to its biggest item and to the
        screen; words or icons as that length leaves room for, and as wide (tall) as the lines take."""
        upright = self._upright()
        shortest, natural = self._limits()
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        room = screen.availableGeometry().height() if upright else screen.availableGeometry().width()
        try:
            want = int(self._settings["game_toolbar_height" if upright else "game_toolbar_width"])
        except (TypeError, ValueError):
            want = None
        length = min(max(natural if want is None else want, shortest), room)
        self._length_set = length
        if upright:
            self.setMinimumSize(1, shortest)
            self.setMaximumSize(QT_MAX, room)
        else:
            self.setMinimumSize(shortest, 1)
            self.setMaximumSize(room, QT_MAX)
        self._fit(length)

    def _fit(self, length: int) -> None:
        """The bar at this length: words or icons alone as it leaves room for, and across only as much as the
        lines they wrap into take."""
        icons = self._wants_icons(length)
        if icons != self._icons_shown:
            self._label(icons)
        along, across = self._pads()
        other = self._flow.extent(length - along) + across
        size = QSize(other, length) if self._upright() else QSize(length, other)
        if size != self.size():
            self._fitting = True
            try:
                self.resize(size)
            finally:
                self._fitting = False

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self._fitting:
            return
        self._lengths.start()              # the player's drag: remembered once it settles
        self._refit.start()

    def _edges_at(self, pos) -> Qt.Edge:
        """Only the bar's two ends along its length (its sides; its top and bottom upright): across, it is as big
        as its lines, never dragged."""
        ends = (Qt.TopEdge | Qt.BottomEdge) if self._upright() else (Qt.LeftEdge | Qt.RightEdge)
        return Qt.Edge(super()._edges_at(pos) & ends)

    def _remember_length(self) -> None:
        """The dragged length kept in game_toolbar_width (game_toolbar_height upright), the natural one-line length
        kept as None so a bigger font still fits; the settings' own length, applied by _apply_size, is not the
        player's to keep."""
        length = self.height() if self._upright() else self.width()
        if not self._placed or length == self._length_set:
            return
        _, natural = self._limits()
        self._settings["game_toolbar_height" if self._upright() else "game_toolbar_width"] = \
            length if length != natural else None
        self._length_set = length

    def _orient_clicked(self, _=False) -> None:
        """The ◯: the bar upright (a column, its height dragged) or lying (a row, its width dragged), its top-left
        corner kept and the whole bar still on its screen."""
        self._lengths.stop()
        self._remember_length()
        self._settings["game_toolbar_vertical"] = not bool(self._settings["game_toolbar_vertical"])
        self._retext()
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(min(max(self.x(), area.left()), area.right() - self.width() + 1),
                  min(max(self.y(), area.top()), area.bottom() - self.height() + 1))

    # ------------------------------------------------------------ the buttons

    def _npcs_clicked(self, _=False) -> None:
        """The checkable button is the setting: the window itself follows the flip (npc_toggled)."""
        self._settings["npc_overlay"] = self._npcs.isChecked()
        self.npc_toggled.emit()

    def _rides_clicked(self, _=False) -> None:
        """Cabs and NPC teleports in the way shown, or on foot: the button is the setting."""
        self._settings["game_rides"] = self._rides.isChecked()
        self.rides_toggled.emit()

    def _loot_clicked(self, _=False) -> None:
        """The loot log's window on or off: the button is the setting (its Start, Stop and Reset are in it)."""
        self._settings["loot_overlay"] = self._loot.isChecked()
        self.loot_toggled.emit()

    def _tool_clicked(self, key: str) -> None:
        """A tool window on or off: the button is its setting (the window follows tool_toggled)."""
        self._settings[key] = self._tools[key].isChecked()
        self.tool_toggled.emit(key)

    def _close_clicked(self, _=False) -> None:
        """The ✕: the setting off, the bar hidden until it's turned back on — from the tray item, its key or
        Settings, which the app's toast names (closed)."""
        self._settings["game_toolbar"] = False
        self.hide()
        self.closed.emit()

    def set_search_mode(self, kind: str) -> None:
        """The search window's mode lit on its button (mode_changed: "" when it closed, none lit)."""
        if kind == self._mode:
            return
        self._mode = kind
        for k, b in self._search.items():
            on = k == kind
            if b.property("on") != on:
                b.setProperty("on", on)
                b.style().unpolish(b)
                b.style().polish(b)
                self._paint_icon(b, KINDS[k])

    # ------------------------------------------------------------ the ⚙ panel

    def _gear_clicked(self, _=False) -> None:
        """The ⚙: the panel over the game under it, or gone when it is up (its own ✕ and Esc close it too)."""
        if self._panel is None:
            self._panel = _SettingsPanel(self)
            self._panel.changed.connect(self.look_changed.emit)
            self._panel.hotkey_changed.connect(self.hotkey_changed.emit)
        if self._panel.isVisible():
            self._panel.hide()
            return
        self._panel.refresh()
        self._panel.place_under(self._gear)
        self._panel.show()
        set_capturable(self._panel, self._settings)

    def look_followed(self) -> None:
        """A choice in the ⚙ panel: the bar's own style, texts and icons (icons mode, the accent) and glass follow
        at once."""
        self._restyle()
        self._retext()
        try:
            self._opacity = min(OPACITY_MAX, max(OPACITY_MIN, float(self._settings["npc_overlay_opacity"])))
        except (TypeError, ValueError):
            self._opacity = OPACITY_DEFAULT
        self.update()

    def _restyle(self) -> bool:
        """The accent (and the icons mode's room) the settings pick; skipped when it is the same. True: restyled."""
        sheet = qss(self._settings)
        if sheet == self.styleSheet():
            return False
        self.setStyleSheet(sheet)
        return True

    # ------------------------------------------------------------ place and move

    def _place(self) -> None:
        """Where the bar opens: where the player left it, when that is still on a screen (a monitor since
        unplugged: above the minimap box again)."""
        screens = [s.geometry() for s in QGuiApplication.screens()]
        spot = mapview.saved_spot(self._settings["game_toolbar_pos"], self.size(), screens)
        self.setGeometry(QRect(spot if spot is not None else self._default_spot(), self.size()))
        self._placed = True

    def _default_spot(self) -> QPoint:
        """Just above the drawn minimap box (the bar is about the map in it), left edges lined up; else the
        primary screen's top centre."""
        screens = [(s.geometry(), s.devicePixelRatio()) for s in QGuiApplication.screens()]
        region = self._settings["minimap_region"]
        primary = QGuiApplication.primaryScreen().availableGeometry()
        if isinstance(region, dict):
            try:
                box, _ = from_capture(region, screens, scale=sys.platform != "darwin")
            except (KeyError, TypeError, ValueError):
                box = None
            if box is not None:
                screen = next((g for g, _ in screens if g.intersects(box)), primary)
                x = min(max(box.left(), screen.left()), screen.right() - self.width() + 1)
                y = min(max(box.top() - self.height() - GAP, screen.top()),
                        max(screen.top(), screen.bottom() - self.height() + 1))
                return QPoint(x, y)
        return QPoint(primary.center().x() - self.width() // 2, primary.top() + SHADOW + 4)

    def moveEvent(self, e) -> None:
        self._geom.start()
        super().moveEvent(e)

    def hideEvent(self, e) -> None:
        if self._placed:             # turned off or the app closing: keep the place now, not 400 ms later
            self._geom.stop()
            self._remember()
            self._lengths.stop()
            self._remember_length()
        if self._panel is not None:
            self._panel.hide()
        super().hideEvent(e)

    def _remember(self) -> None:
        if self._placed:
            self._settings["game_toolbar_pos"] = {"x": self.x(), "y": self.y()}

    # ------------------------------------------------------------ the rest of the bar's life

    def refresh(self) -> None:
        """Show or hide from the setting (its ✕, its key, the tray item or Settings flipped it), the NPCs-here
        button back in step with the window's own (its ✕ turned it off), the width the settings give (its buttons
        wrapping into rows), and the glass at the opacity the player picked."""
        if self._restyle() or bool(self._settings["game_toolbar_vertical"]) != self._flow.upright:
            self._retext()        # the icons in the new accent's text colour, words or icons, the way it stands
        try:
            self._opacity = min(OPACITY_MAX, max(OPACITY_MIN, float(self._settings["npc_overlay_opacity"])))
        except (TypeError, ValueError):
            self._opacity = OPACITY_DEFAULT
        self._npcs.setChecked(bool(self._settings["npc_overlay"]))
        self._rides.setChecked(bool(self._settings["game_rides"]))
        self._loot.setChecked(bool(self._settings["loot_overlay"]))
        for key, b in self._tools.items():
            b.setChecked(bool(self._settings[key]))
        if not self._settings["game_toolbar"]:
            if self.isVisible():
                self.hide()
            return
        self._apply_size()
        if not self.isVisible():
            self._place()
            self.show()
            set_capturable(self, self._settings)
        if self._panel is not None and self._panel.isVisible():
            self._panel.refresh()
        self.update()

    def apply_language(self, t: I18n) -> None:
        self.t = t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        if self._panel is not None:
            self._panel.apply_language(t)
        self._retext()
