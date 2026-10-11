"""The look pickers both look settings share: the toolbar's ⚙ panel (ui/gametoolbar.py) picks the look of the
windows over the game, Settings (ui/dialogs.py) the look of the app's own windows. Swatch is one colour to pick (a
glass tint as a small tile of that glass, an accent as a dot of it), Slider the glass's opacity at any whole
percent. Neither knows the glass it sits on: the window that holds them gives `edge`, its hairline or faint fill at
an alpha (white on dark glass, black on white), and `light`, whether that glass is a light one. The line icons the
toolbar draws its buttons with (assets/icons/toolbar, Lucide's) live here too: a picked swatch's check is one."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QByteArray, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QIconEngine,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ..store import ASSETS
from . import theme

ICON_DIR = ASSETS / "icons" / "toolbar"      # the line icons: <name>.svg (Lucide's, its LICENSE beside them)


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


# ---------------------------------------------------------------- the pickers

class Swatch(QPushButton):
    """One colour to pick: a glass tint as a small tile of that glass, an accent as a dot of it. The chosen one is
    ringed in the accent (an accent's own dot: in itself), with a check in `check`. `edge(alpha)` is the hairline of
    the glass it sits on: a tile's edge, a dot's ring under the mouse."""

    def __init__(self, kind: str, key: str, colour: str, check: str, edge: Callable[[int], QColor]):
        super().__init__(checkable=True)
        self._kind = kind
        self._edge = edge
        self._fill, self._ring = QColor(colour), QColor(colour)
        self._check = line_icon("check", check)
        self.setProperty("key", key)
        self.setProperty("colour", colour)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        if kind == "tint":
            self.setMinimumSize(36, 36)                 # six tiles and their gaps across the ⚙ panel's 268 px
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
            p.setPen(QPen(self._edge(115 if hover and not on else 46), 1))  # the white tile still edged on white glass
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
                p.setPen(QPen(self._edge(90), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, d / 2 - 1, d / 2 - 1)
            p.setPen(Qt.NoPen)
            p.setBrush(self._fill)
            p.drawEllipse(c, d / 2 - 4.5, d / 2 - 4.5)
            mark = 14
        if on:
            self._check.paint(p, QRect(round(r.center().x() - mark / 2), round(r.center().y() - mark / 2), mark, mark))


class Slider(QWidget):
    """The glass's opacity as a slider from `lo` to `hi`, at any whole percent: the track lit in the accent from its
    start up to the knob; a click or a drag puts the knob there (mirrored in Hebrew: the start on the right), and so
    do the keys where its window gives it the keyboard (Settings; the ⚙ panel over the game never takes it).
    changed(value) on every percent it moves to, released() when the mouse lets go. `edge(alpha)` is the faint
    colour of the glass it sits on (the unlit track), `light()` whether that glass is a light one (the white knob
    gets a hairline round it there)."""

    changed = Signal(float)
    released = Signal()
    KNOB = 16

    def __init__(self, lo: float, hi: float, edge: Callable[[int], QColor], light: Callable[[], bool]):
        super().__init__()
        self._lo, self._hi = lo, hi
        self._edge, self._light = edge, light
        self._v = hi
        self._accent = QColor(Qt.white)           # (set_accent gives it the accent)
        self.setFixedHeight(24)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def value(self) -> float:
        return self._v

    def set_value(self, v: float) -> None:
        v = round(min(self._hi, max(self._lo, v)), 2)
        if v != self._v:
            self._v = v
            self.update()

    def set_accent(self, colour: str) -> None:
        if QColor(colour) != self._accent:
            self._accent = QColor(colour)
            self.update()

    def _x(self, v: float) -> float:
        frac = (v - self._lo) / (self._hi - self._lo)
        if self.layoutDirection() == Qt.RightToLeft:
            frac = 1 - frac
        return self.KNOB / 2 + frac * (self.width() - self.KNOB)

    def _value_at(self, x: float) -> float:
        """The whole percent under this x (the ends past the track: the ends themselves)."""
        frac = min(1.0, max(0.0, (x - self.KNOB / 2) / max(1, self.width() - self.KNOB)))
        if self.layoutDirection() == Qt.RightToLeft:
            frac = 1 - frac
        return round(self._lo + frac * (self._hi - self._lo), 2)

    def _drag(self, x: float) -> None:
        self._move(self._value_at(x))

    def _move(self, v: float) -> None:
        """The knob to the whole percent v, kept between the ends: changed(v) when it moved."""
        v = round(min(self._hi, max(self._lo, v)), 2)
        if v != self._v:
            self._v = v
            self.update()
            self.changed.emit(v)

    def keyPressEvent(self, e):
        """← and → a percent toward the side they point (the start on the right in Hebrew), ↑ and ↓ a percent up
        and down, Page Up / Page Down ten, Home and End the ends."""
        k = e.key()
        if k in (Qt.Key_Home, Qt.Key_End):
            self._move(self._lo if k == Qt.Key_Home else self._hi)
        elif k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            more = Qt.Key_Left if self.layoutDirection() == Qt.RightToLeft else Qt.Key_Right
            step = 0.1 if k in (Qt.Key_PageUp, Qt.Key_PageDown) else 0.01
            self._move(self._v + (step if k in (more, Qt.Key_Up, Qt.Key_PageUp) else -step))
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag(e.position().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._drag(e.position().x())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.released.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cy = self.height() / 2
        start, knob = self._x(self._lo), self._x(self._v)
        left, right = self.KNOB / 2, self.width() - self.KNOB / 2
        p.setPen(Qt.NoPen)
        p.setBrush(self._edge(38))
        p.drawRoundedRect(QRectF(left - 2, cy - 2, right - left + 4, 4), 2, 2)
        p.setBrush(self._accent)
        lo, hi = min(start, knob), max(start, knob)
        p.drawRoundedRect(QRectF(lo - 2, cy - 2, hi - lo + 4, 4), 2, 2)
        p.setBrush(QColor(0, 0, 0, 60))                 # the knob, on a soft shadow
        p.drawEllipse(QRectF(knob - self.KNOB / 2, cy - self.KNOB / 2 + 1, self.KNOB, self.KNOB))
        if self._light():                               # a hairline round the white knob on a light glass
            p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(knob - self.KNOB / 2, cy - self.KNOB / 2, self.KNOB, self.KNOB))
