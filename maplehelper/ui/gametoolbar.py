"""The little bar over the game: the NPCs-here window's own switch, the searches — where a monster lives, any NPC,
any map, any item, and whether an item is safe to sell (each asks the app to open ui/gamesearch.py in that mode) —
the loot log, the grind bar (ui/grindbar.py), and Tools: a little card with the tool windows (Grind spots, Farm,
Quests, Citizenship, Build & skills, Gear, Scrolls, Crafting, Cash shop). Like the NPCs window it floats over the
game: frameless, always on top, never taking the keyboard from it (clicks still work), glass the minimap reads never
see. Its ends are draggable (its sides; its top and bottom when the ◯ before the grip stands it upright): the buttons
wrap into as many lines as the length leaves room for, the other side following, and show their icons alone once the
words would take more than WORD_LINES_MAX lines; the length is kept in game_toolbar_width (game_toolbar_height
upright). Each button has a line icon (assets/icons/toolbar, Lucide's) drawn in its text's colour: small beside the
words, or alone (a short bar, or the ⚙'s icons mode) with the name in the tooltip. The ⚙ beside the ✕ opens the
panel with the look of every window over the game, the icons mode, the bar's show/hide key, Cabs & Teleports, the
hidden-teleport routes and Minimap: the hidden portals' dots and the route's arrow on the game's minimap (its colour,
size, the name beside it and its flashing), a notice on reaching the map it points to, and the overlays in
screenshots (_SettingsPanel below); the ✕ hides the bar (the app then says how to bring it back). Where the player
left it is kept in game_toolbar_pos; with none saved it opens just above the game's minimap window (found at the
game's top left) and follows it until moved. Every colour is read from npcoverlay.palette() when a style is built or
a widget paints: light text on the dark glass tints, dark text on the white one."""
from __future__ import annotations

import re
import time

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QPainter,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import bidi
from ..i18n import I18n
from ..store import DEFAULT_SETTINGS, Settings
from . import mapview, theme
from .controls import FlowLayout, Switch
from .gamesearch import SCROLLBAR_W, rim
from .glass import SHADOW, EdgeResize
from .hotkeybox import HotkeyBox
from .location import LOCATION
from .lookpick import Slider, Swatch, line_icon
from .npcoverlay import (
    DARK,
    GAP,
    GEOM_DEBOUNCE_MS,
    LIGHT,
    OPACITY_DEFAULT,
    OPACITY_MAX,
    OPACITY_MIN,
    _flags,
    _Header,
    _paint_glass,
    accent_of,
    apply_look,
    keep_over_game,
    minimap_box,
    palette,
    set_capturable,
)
from .portaldots import ARROW_COLORS, ARROW_OPACITY, ARROW_OPACITY_MIN, ARROW_SIZE_MAX, ARROW_SIZE_MIN
from .theme import ACCENTS, LIGHT_TINTS, TINTS
from .widgets import tip_html

SIDE, TOP, BOTTOM = SHADOW + 12, SHADOW + 8, SHADOW + 8    # content margins, past the glass's shadow rim
FLOW_GAP = 6                                              # between the buttons, and between the rows they wrap into
# the most rows (columns, upright) the buttons' words may wrap into: dragged shorter, the bar shows icons alone
WORD_LINES_MAX = 2
QT_MAX = 16777215                                         # Qt's "no limit" for a widget's size
KINDS = {"monster_npc": "tb_monster_npc", "map": "tb_maps", "item": "tb_items", "sell": "tb_sell"}  # search buttons, i18n keys
# the tool windows the Tools card shows and hides, in the card's order: each button is its window's setting -> its i18n
# key (app.py makes each window: ui/toolwindow.py's tool windows, the scroll planner, gear and crafting advisors)
TOOLS = {"grind_spots": "tb_spots", "farm_tool": "tb_farm", "quest_tool": "tb_quests", "citizenship": "tb_town",
         "build_tool": "tb_build", "gear_advisor": "tb_gear", "scroll_planner": "tb_scrolls", "craft_advisor": "tb_craft",
         "cash_shop": "tb_shop"}
# each button's line icon, by its i18n key: assets/icons/toolbar/<name>.svg (Lucide's, its LICENSE beside them)
ICONS = {"tb_npcs_here": "users", "tb_monster_npc": "ghost", "tb_maps": "map", "tb_items": "backpack",
         "tb_sell": "coins", "tb_loot": "scroll-text", "tb_grind": "swords", "tb_tools": "toolbox",
         "tb_spots": "crosshair", "tb_farm": "sprout", "tb_quests": "list-checks", "tb_town": "landmark",
         "tb_build": "dumbbell", "tb_gear": "shield", "tb_scrolls": "sparkles", "tb_craft": "hammer", "tb_shop": "gem"}
MENU_COLS = 2           # the Tools card's buttons a row, in TOOLS' order (mirrored in Hebrew)
AWAY_MS = 1000          # the mouse this long off the Tools card and its button: the card goes
AWAY_POLL_MS = 150      # ... checked this often while it is up (it takes no focus to lose)
ICON_PX = 18            # an icon alone on its button (icons mode)
WORD_ICON_PX = 15       # the small one beside the word
TOOL_ICON_PX = 16       # the bar's ⚙ and ✕
PANEL_W = 600 + 2 * SHADOW                                # the ⚙ panel's card ~600 px wide, its shadow around it
PANEL_SIDE = SHADOW + 16
PANEL_COL_GAP = 32     # between the ⚙ panel's two columns, each PANEL_COL_W wide: the 268 px its one column had
PANEL_COL_W = (PANEL_W - 2 * PANEL_SIDE - PANEL_COL_GAP) // 2
PANEL_GUTTER = 4       # between the ⚙ panel's sections and their scrollbar, which shows in the side margin...
PANEL_BAR = SCROLLBAR_W + PANEL_GUTTER   # ...this much of it: the sections keep their place and width either way
PANEL_SPARE = 16       # the ⚙ panel's height stays this far inside its screen's room: past it, its sections scroll
FIRST_SENTENCE = re.compile(r".+?[.!?](?=\s)")   # a ⚙ panel hint's line: to its first full stop with more after it
FOLLOW_MS = 80         # a transparency or arrow-size drag: the windows over the game follow at most this often
# what "Reset to default look" puts back (the hotkey is no look: it stays)
LOOK_KEYS = ("overlay_tint", "overlay_accent", "npc_overlay_opacity", "game_toolbar_icons")


def qss(settings) -> str:
    """The bar's own style (and its Tools card's): the glass's text and fills (palette()), the accent that lights a
    lit button, from the settings, and the room an icon alone takes on its button (iconOnly: the ⚙'s icons mode, or a
    bar dragged too short for the words)."""
    accent, on_accent = accent_of(settings)
    pal = palette()
    return f"""
QPushButton {{ background: {pal.fill1}; color: {pal.text}; border: none; border-radius: 8px;
              padding: 5px 10px; text-align: center; }}
QPushButton[iconOnly="true"] {{ padding: 6px 9px; }}
QPushButton:hover {{ background: {pal.fill2}; }}
QPushButton:checked, QPushButton[on="true"] {{ background: {accent}; color: {on_accent}; }}
QPushButton#MenuItem {{ padding: 7px 12px; text-align: left; }}
QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: {pal.fill2}; }}
"""


class _Grip(QWidget):
    """The dots at the bar's end: dragging them moves it (the buttons around them still click)."""

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.OpenHandCursor)
        self._grab = None          # (its window is self.window(), not kept)
        self._upright = False
        self._icon, self._icon_for = None, None     # its dots, and the (upright, colour) they were drawn for
        self.set_upright(False)

    def set_upright(self, upright: bool) -> None:
        """Its dots across an upright bar (grip-horizontal), down a lying one (grip-vertical)."""
        self._upright = upright
        self.setFixedSize(28, 12) if upright else self.setFixedSize(12, 28)
        self.update()

    def paintEvent(self, e):
        want = (self._upright, palette().muted)       # the glass's muted colour now: redrawn when it changes
        if want != self._icon_for:
            self._icon = line_icon("grip-horizontal" if self._upright else "grip-vertical", want[1])
            self._icon_for = want
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

def panel_qss() -> str:
    """The ⚙ panel's style in the glass's colours now (palette()): a title, small muted section heads, labels with
    their picked value, one-line hints (its accent-lit controls paint themselves: the swatches' rings, the slider,
    the switches, the key box), and the thin scrollbar of the windows over the game (gamesearch.glass_qss's) for
    the sections when they scroll."""
    pal = palette()
    faint = "rgba(60,60,67,0.30)" if pal.light else "rgba(235,235,245,0.30)"
    return f"""
QLabel {{ background: transparent; }}
#Title {{ color: {pal.text}; font-size: 14px; font-weight: 600; }}
#Section {{ color: {pal.muted}; font-size: 11px; font-weight: 700; }}
#Label {{ color: {pal.text}; font-size: 13px; }}
#Picked {{ color: {pal.muted}; font-size: 12px; }}
#Value {{ color: {pal.text}; font-size: 13px; font-weight: 600; }}
#Hint {{ color: {pal.muted}; font-size: 11px; }}
QFrame#Rule {{ background: {pal.shade}; border: none; }}
QToolButton#Close {{ background: transparent; color: {pal.muted}; border: none; border-radius: 6px;
                     padding: 2px 7px; font-size: 13px; }}
QToolButton#Close:hover {{ background: {pal.fill2}; color: {pal.text}; }}
QToolButton#Reset {{ background: transparent; color: {pal.muted}; border: none; padding: 4px 0;
                     font-size: 12px; font-weight: 600; }}
QToolButton#Reset:hover {{ color: {pal.text}; }}
QToolButton#Reset:disabled {{ color: {faint}; }}
QScrollBar:vertical {{ background: transparent; width: {SCROLLBAR_W}px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {rim(0.25, pal)}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


def _edge(alpha: int) -> QColor:
    """A hairline or faint fill on the glass now: white on the dark tints, black on the white one (a little less of
    it: black reads stronger on white than white on dark)."""
    r, g, b = palette().rim
    return QColor(r, g, b, round(alpha * 0.8) if palette().light else alpha)


class _GlassSwitch(Switch):
    """controls.Switch drawn for the glass over the game: its track in the windows' accent when on, a faint one off
    (white on the dark tints, grey on the white one)."""

    W, H = 40, 24

    def __init__(self):
        super().__init__(False)
        self._accent = QColor(DARK.text)
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
        off, on = _edge(46), self._accent
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


class _Hint(QLabel):
    """A row's hint in the ⚙ panel: one muted line under the row, its first sentence (FIRST_SENTENCE), ending in "…"
    where that is wider than the column (wrapped whole under every row, the hints took most of the panel's height).
    As widgets.ElideLink's, its text() is what it says, not what fits: the whole hint, which is also its accessible
    name and, wrapped, its tooltip; the panel gives the row's label and control the same tooltip."""

    def __init__(self):
        super().__init__(objectName="Hint")
        self._hint, self._rtl = "", False
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)    # its column's width, however long it is

    def set_hint(self, text: str, rtl: bool) -> None:
        self._hint, self._rtl = text, rtl
        self.setToolTip(tip_html(text, rtl))
        self.setAccessibleName(text)
        self._cut()

    def text(self) -> str:          # what it says, not what fits
        return bidi.plain(self._hint, self._rtl)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._cut()

    def _cut(self) -> None:
        self.ensurePolished()
        first = FIRST_SENTENCE.match(self._hint)
        line = self.fontMetrics().elidedText(first.group(0) if first else self._hint, Qt.ElideRight,
                                             max(1, self.contentsRect().width()))
        line = bidi.plain(line, self._rtl)      # cut first: in Hebrew the "…" ends the line, not an English name in it
        if line != super().text():
            super().setText(line)


class _SettingsPanel(QWidget):
    """The bar's ⚙ panel, one card in the same glass over the game, its sections in two columns read from the
    leading edge (mirrored in Hebrew). The first holds the bar's own look and settings and navigation. Look: the
    glass colour of every window over the game as tiles of each tint and the lit buttons' accent as dots, the picked
    one ringed and named; Transparency: their glass's opacity on a slider, any whole percent; Toolbar: icons instead
    of words, and the bar's show/hide key in the same key box Settings has; Navigation, under a head of its own:
    whether the arrow guides the whole way across maps, whether it says how many maps are left, a notice on reaching
    the map it leads to (the arrow turns itself off then), and whether Maple Helper's own map window draws each
    hidden teleport as an arrow to where it lands — down this column, where there is room, rather than under the
    arrow's own switches, which left the second one scrolling on a 1080p screen. The second holds the way and the
    minimap. Directions: Cabs & Teleports, whether the way to a found NPC or map rides cabs and NPC teleports or walks
    (the bar's rides_toggled: a way shown is found again); Minimap: the hidden portals' blue dots and the route's
    arrow on the game's minimap, the arrow's colour as dots (the picked one ringed and named), its size in whole
    pixels and its opacity on sliders, the name beside it (the map its portal leads to, or the NPC to talk to) with
    that name's own opacity on a slider, and whether it flashes, and whether screenshots see the windows over the
    game (the bar's minimap_toggled: the app follows). A row's hint is one line under it, all of it
    in the row's tooltip (_Hint). Each choice is written, applies at once and stays; "Reset to default look", under
    both columns, puts the look back. ✕, the ⚙ again or Esc closes it (Esc once the panel has been clicked into: like
    the search window it takes the keyboard only then, never on opening). Side by side the sections fit a 1080p
    screen at 125 % (about 800 px of room) whole; on a screen shorter than they need they scroll under the title
    row, which stays put to drag the panel by and close it."""

    changed = Signal()          # a look choice applied: every window over the game follows (app.py wires it)
    hotkey_changed = Signal()   # the bar's key picked or cleared here: the app binds the new one

    def __init__(self, bar):
        # like the search window, not the bar's own flags: it takes the keyboard once clicked, for Esc and the key box
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)      # the rows' hints while the game has the keyboard too
        self._bar = bar
        self._settings = bar._settings
        self.t = bar.t
        self.setLayoutDirection(Qt.RightToLeft if self.t.rtl else Qt.LeftToRight)
        self._opacity = OPACITY_DEFAULT
        self.setFixedWidth(PANEL_W)
        self._pal = None                    # the glass's colours its style and icons were made in (refresh)
        outer = QVBoxLayout(self)
        # the side margins' inner PANEL_BAR is the title row's and the sections': their scrollbar shows in it (_fit)
        outer.setContentsMargins(PANEL_SIDE - PANEL_BAR, TOP + 4, PANEL_SIDE - PANEL_BAR, BOTTOM + 6)
        outer.setSpacing(0)
        # the title row: drags the panel; its ✕ closes it
        head = self._head = _Header()
        hrow = QHBoxLayout(head)
        hrow.setContentsMargins(PANEL_BAR, 0, PANEL_BAR, 0)
        hrow.setSpacing(8)
        self._title = QLabel(objectName="Title")
        self._close = QToolButton(objectName="Close", text=theme.SYMBOL_ICONS["close"])
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.clicked.connect(self._close_clicked)
        hrow.addWidget(self._title, 1)
        hrow.addWidget(self._close, 0, Qt.AlignTop)
        outer.addWidget(head)
        # every section under it, in a body that scrolls while the panel is taller than its screen has room for (_fit)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.viewport().setAutoFillBackground(False)      # the glass shows through
        outer.addWidget(self._scroll, 1)
        body = QWidget()
        lay = self._body_lay = QVBoxLayout(body)
        lay.setContentsMargins(PANEL_BAR, 0, PANEL_BAR, 0)
        lay.setSpacing(0)
        self._scroll.setWidget(body)
        body.setAutoFillBackground(False)                          # (setWidget turns it on: the glass shows through)
        # the sections in two columns from the leading edge (the right in Hebrew: the row mirrors), the bar's own look
        # and settings in the first, the way and the minimap in the second; each PANEL_COL_W wide, its strut and the
        # gap between them filling the sections' width exactly, whatever their rows would take
        cols = QHBoxLayout()
        cols.setSpacing(PANEL_COL_GAP)
        lay.addLayout(cols)
        look, way = QVBoxLayout(), QVBoxLayout()
        for col in (look, way):
            col.setSpacing(0)
            col.addStrut(PANEL_COL_W)
            cols.addLayout(col)
        # Look: the glass tint as tiles, the accent as dots, each named beside its label
        col = look
        self._look_head = self._section(col, first=True)
        self._tint_label, self._tint_name = self._label_row(col)
        col.addSpacing(6)
        self._tints = self._swatches("tint", TINTS, lambda k: "#{:02x}{:02x}{:02x}".format(*TINTS[k][1]),
                                     self._pick_tint, spacing=6)
        col.addWidget(self._tints)
        col.addSpacing(10)
        self._accent_label, self._accent_name = self._label_row(col)
        col.addSpacing(6)
        self._accents = self._swatches("accent", ACCENTS, lambda k: ACCENTS[k][1], self._pick_accent)
        col.addWidget(self._accents)
        # Transparency: the windows' glass opacity, any whole percent from OPACITY_MIN to OPACITY_MAX
        self._opacity_head = self._section(col)
        self._opacity_label, self._opacity_value = self._label_row(col, value="Value")
        col.addSpacing(4)
        self._slider = Slider(OPACITY_MIN, OPACITY_MAX, _edge, lambda: palette().light)
        self._slider.changed.connect(self._pick_opacity)
        self._slider.released.connect(self._opacity_settled)
        col.addWidget(self._slider)
        # every other window over the game follows a drag of the slider once a moment, not at every percent
        self._follow = QTimer(self, singleShot=True, interval=FOLLOW_MS, timeout=self.changed.emit)
        # Toolbar: icons instead of words, and the key that shows or hides the bar
        self._bar_head = self._section(col)
        self._icons_label, self._icons, self._icons_hint = self._switch_row(col, self._pick_icons)
        col.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(12)
        self._hotkey_label = QLabel(objectName="Label")
        self._hotkey = HotkeyBox(self._settings["game_toolbar_hotkey"], self.t, glass=True)
        self._hotkey.changed.connect(self._pick_hotkey)
        row.addWidget(self._hotkey_label, 1)
        row.addWidget(self._hotkey, 0, Qt.AlignVCenter)
        col.addLayout(row)
        self._hotkey_hint = self._hint(col)
        # Navigation: the arrow guiding the whole way across maps rather than one step, how many maps are left said
        # beside it, a notice on reaching the map it leads to, and — the odd one out, so its label names the window —
        # the teleport arrows on Maple Helper's own map window. Their own head, and down this column: more rows under
        # the arrow's own switches left the second column scrolling on a 1080p screen at 125 %, where this one had
        # room to spare.
        self._nav_head = self._section(col)
        (self._route_follow_label, self._route_follow,
         self._route_follow_hint) = self._switch_row(col, self._pick_route_follow)
        col.addSpacing(10)
        # the two under it say all there is to say in their labels: no hint line of their own
        self._route_steps_label, self._route_steps, _ = self._switch_row(col, self._pick_route_steps, hint=False)
        col.addSpacing(10)
        # a notice on reaching the map the arrow leads to (the arrow turns itself off then)
        self._arrival_label, self._arrival, self._arrival_hint = self._switch_row(col, self._pick_arrival)
        col.addSpacing(10)
        (self._teleport_arrows_label, self._teleport_arrows,
         _) = self._switch_row(col, self._pick_teleport_arrows, hint=False)
        col.addStretch(1)                           # (the shorter column's rows stay at its top)
        # Directions: the way to a found NPC or map with cabs and NPC teleports, or on foot (was a bar button)
        col = way
        self._way_head = self._section(col, first=True)
        self._rides_label, self._rides, self._rides_hint = self._switch_row(col, self._pick_rides)
        # Minimap: the hidden portals' dots and the route's arrow on the game's minimap, each on or off, and whether
        # screenshots see the windows over the game (were on the Settings page)
        self._minimap_head = self._section(col)
        (self._hidden_portals_label, self._hidden_portals,
         self._hidden_portals_hint) = self._switch_row(col, self._pick_hidden)
        col.addSpacing(10)
        self._route_arrow_label, self._route_arrow, self._route_arrow_hint = self._switch_row(col, self._pick_route)
        # the route arrow's look, under its switch: its colour as dots (the picked one ringed and named), its size on
        # a slider in whole pixels and how solid it is drawn on another (each beside its label), the name beside it
        # and how solid that is drawn on a third, and whether it flashes
        col.addSpacing(10)
        self._arrow_color_label, self._arrow_color_name = self._label_row(col)
        col.addSpacing(6)
        self._arrow_colors = self._swatches("arrow", ARROW_COLORS, lambda k: ARROW_COLORS[k][1], self._pick_arrow_color)
        col.addWidget(self._arrow_colors)
        col.addSpacing(10)
        self._arrow_size_label, self._arrow_size_value = self._label_row(col, value="Value")
        col.addSpacing(4)
        self._arrow_size = Slider(ARROW_SIZE_MIN, ARROW_SIZE_MAX, _edge, lambda: palette().light)
        self._arrow_size.changed.connect(self._pick_arrow_size)
        self._arrow_size.released.connect(self._arrow_size_settled)
        col.addWidget(self._arrow_size)
        # the app follows a drag of it once a moment, not at every pixel: minimap_toggled redraws windows too
        self._arrow_follow = QTimer(self, singleShot=True, interval=FOLLOW_MS, timeout=self._bar.minimap_toggled.emit)
        col.addSpacing(10)
        self._arrow_opacity_label, self._arrow_opacity_value = self._label_row(col, value="Value")
        col.addSpacing(4)
        self._arrow_opacity = Slider(ARROW_OPACITY_MIN, ARROW_OPACITY, _edge, lambda: palette().light)
        self._arrow_opacity.changed.connect(self._pick_arrow_opacity)
        self._arrow_opacity.released.connect(self._arrow_size_settled)   # the same follow: one timer for all three
        col.addWidget(self._arrow_opacity)
        col.addSpacing(10)
        (self._arrow_label_label, self._arrow_label,
         self._arrow_label_hint) = self._switch_row(col, self._pick_arrow_label)
        # ... how solid that name is drawn, on its own slider under its switch: a faint arrow can keep a name that reads
        col.addSpacing(10)
        self._label_opacity_label, self._label_opacity_value = self._label_row(col, value="Value")
        col.addSpacing(4)
        self._label_opacity = Slider(ARROW_OPACITY_MIN, ARROW_OPACITY, _edge, lambda: palette().light)
        self._label_opacity.changed.connect(self._pick_label_opacity)
        self._label_opacity.released.connect(self._arrow_size_settled)
        col.addWidget(self._label_opacity)
        col.addSpacing(10)
        (self._arrow_flash_label, self._arrow_flash,
         self._arrow_flash_hint) = self._switch_row(col, self._pick_arrow_flash)
        col.addSpacing(10)
        (self._overlay_shots_label, self._overlay_shots,
         self._overlay_shots_hint) = self._switch_row(col, self._pick_shots)
        col.addStretch(1)
        # Reset to default look, at the leading edge under a hairline across both columns
        lay.addSpacing(12)
        rule = QFrame(objectName="Rule")
        rule.setFixedHeight(1)
        lay.addWidget(rule)
        lay.addSpacing(4)
        row = QHBoxLayout()
        self._reset = QToolButton(objectName="Reset")
        self._reset.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._reset.setAutoRaise(True)              # the icon brightens with the text under the mouse
        self._reset.setCursor(Qt.PointingHandCursor)
        self._reset.setFocusPolicy(Qt.NoFocus)
        self._reset.setIconSize(QSize(14, 14))
        self._reset.clicked.connect(self._reset_look)
        row.addWidget(self._reset)
        row.addStretch(1)
        lay.addLayout(row)
        self.refresh()

    # ------------------------------------------------------------ the panel

    @staticmethod
    def _section(col, first: bool = False) -> QLabel:
        """A small muted head over a section, with room above it (less at the top of its column)."""
        col.addSpacing(8 if first else 16)
        lb = QLabel(objectName="Section")
        col.addWidget(lb)
        col.addSpacing(8)
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
    def _hint(col) -> _Hint:
        """A row's hint: one muted line just under it (_Hint)."""
        col.addSpacing(1)
        lb = _Hint()
        col.addWidget(lb)
        return lb

    def _switch_row(self, col, picked, hint: bool = True) -> tuple[QLabel, _GlassSwitch, _Hint | None]:
        """A label at the leading edge, its switch at the trailing one (a click: picked), and its hint under them;
        hint=False leaves the row without one, for a label that says all there is to say."""
        row = QHBoxLayout()
        row.setSpacing(12)
        label, switch = QLabel(objectName="Label"), _GlassSwitch()
        switch.setCursor(Qt.PointingHandCursor)
        switch.clicked.connect(picked)
        row.addWidget(label, 1)
        row.addWidget(switch, 0, Qt.AlignVCenter)
        col.addLayout(row)
        return label, switch, (self._hint(col) if hint else None)

    def _swatches(self, kind: str, presets: dict, colour_of, picked, spacing: int = 0) -> QWidget:
        """A row of colours, one per preset, across its column's width: tiles side by side (spacing), or dots spread
        evenly (no spacing: stretches between them)."""
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing)
        for i, key in enumerate(presets):
            if i and not spacing:
                row.addStretch(1)
            # a tint's check reads on its own tile (dark on the white one), a dot's in the dark colour its preset
            # pairs with it: an accent's own text colour, the route arrow's rim
            check = (LIGHT.text if key in LIGHT_TINTS else DARK.text) if kind == "tint" else presets[key][2]
            b = Swatch(kind, key, colour_of(key), check, _edge)
            b.clicked.connect(lambda _=False, k=key: picked(k))
            row.addWidget(b)
        return w

    def refresh(self) -> None:
        """Every choice back in step with the settings (the Settings dialog may have changed them), the panel's
        style and icons in the glass's colours now, its own glass at the transparency they give, and its height: what
        the sections need, at most the room on its screen (_fit)."""
        t, rtl, s = self.t, self.t.rtl, self._settings
        accent, _ = accent_of(s)
        pal = palette()
        if pal != self._pal:
            self._pal = pal
            self.setStyleSheet(panel_qss())
            self._reset.setIcon(line_icon("rotate-ccw", pal.muted, hover=pal.text))
        self._title.setText(bidi.plain(t("tbs_title"), rtl))
        self._close.setAccessibleName(t("tbs_close"))
        self._close.setToolTip(t("tbs_close"))
        for lb, key in ((self._look_head, "tbs_look"), (self._opacity_head, "tbs_opacity_head"),
                        (self._bar_head, "tbs_bar"), (self._way_head, "tbs_way"), (self._minimap_head, "tbs_minimap"),
                        (self._nav_head, "tbs_navigation")):
            lb.setText(bidi.plain(t(key) if rtl else t(key).upper(), rtl))
        tint = s["overlay_tint"] if s["overlay_tint"] in TINTS else next(iter(TINTS))      # a stale name: today's
        accent_key = s["overlay_accent"] if s["overlay_accent"] in ACCENTS else next(iter(ACCENTS))
        arrow_key = (s["minimap_arrow_color"] if s["minimap_arrow_color"] in ARROW_COLORS
                     else DEFAULT_SETTINGS["minimap_arrow_color"])                  # ... the arrow's: today's orange
        for lb, key in ((self._tint_label, "tbs_tint"), (self._tint_name, TINTS[tint][0]),
                        (self._accent_label, "tbs_accent"), (self._accent_name, ACCENTS[accent_key][0]),
                        (self._opacity_label, "tbs_opacity"), (self._icons_label, "tbs_icons"),
                        (self._hotkey_label, "tb_hotkey"), (self._rides_label, "tb_rides"),
                        (self._hidden_portals_label, "minimap_hidden_portals"),
                        (self._route_arrow_label, "minimap_route_arrow"),
                        (self._arrow_color_label, "tbs_arrow_colour"),
                        (self._arrow_color_name, ARROW_COLORS[arrow_key][0]),
                        (self._arrow_size_label, "tbs_arrow_size"),
                        (self._arrow_opacity_label, "tbs_arrow_opacity"),
                        (self._arrow_label_label, "tbs_arrow_label"),
                        (self._label_opacity_label, "tbs_arrow_label_opacity"),
                        (self._arrow_flash_label, "tbs_arrow_flash"),
                        (self._arrival_label, "tbs_arrival"),
                        (self._overlay_shots_label, "overlays_in_screenshots"),
                        (self._route_follow_label, "set_route_follow"),
                        (self._route_steps_label, "set_route_steps"),
                        (self._teleport_arrows_label, "set_teleport_arrows")):
            lb.setText(bidi.plain(t(key), rtl))
        # each row's hint: its first sentence on the line under the row, all of it in the tooltip of that line, of the
        # row's label and of its control (the key box keeps its own: how to pick a key)
        for hint, key, label, control in (
                (self._icons_hint, "tbs_icons_hint", self._icons_label, self._icons),
                (self._hotkey_hint, "tb_hotkey_hint", self._hotkey_label, None),
                (self._rides_hint, "tb_rides_tip", self._rides_label, self._rides),
                (self._hidden_portals_hint, "minimap_hidden_portals_hint", self._hidden_portals_label,
                 self._hidden_portals),
                (self._route_arrow_hint, "minimap_route_arrow_hint", self._route_arrow_label, self._route_arrow),
                (self._arrow_label_hint, "tbs_arrow_label_hint", self._arrow_label_label, self._arrow_label),
                (self._arrow_flash_hint, "tbs_arrow_flash_hint", self._arrow_flash_label, self._arrow_flash),
                (self._arrival_hint, "tbs_arrival_hint", self._arrival_label, self._arrival),
                (self._overlay_shots_hint, "overlays_in_screenshots_hint", self._overlay_shots_label,
                 self._overlay_shots),
                (self._route_follow_hint, "set_route_follow_tip", self._route_follow_label, self._route_follow)):
            # Hebrew: two pixels' room at the right, where a line as wide as the column drew its first letter past
            # the label's edge, cut off (the line is measured in whole pixels, the glyphs overhang)
            hint.setContentsMargins(0, 0, 2 if rtl else 0, 0)
            hint.set_hint(t(key), rtl)
            for w in (label, control):
                if w is not None:
                    w.setToolTip(hint.toolTip())
        self._reset.setText(bidi.plain(t("tbs_reset"), rtl))
        for row, chosen, presets in ((self._tints, tint, TINTS), (self._accents, accent_key, ACCENTS),
                                     (self._arrow_colors, arrow_key, ARROW_COLORS)):
            for b in row.findChildren(Swatch):
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
        self._slider.set_value(self._opacity)
        self._slider.set_accent(accent)
        self._slider.setAccessibleName(t("tbs_opacity"))
        self._opacity_value.setText(bidi.ltr_block(f"{round(self._opacity * 100)}%", rtl))
        self._icons.setChecked(bool(s["game_toolbar_icons"]))
        self._icons.set_accent(accent)
        self._icons.setAccessibleName(t("tbs_icons"))
        self._hotkey.set_key(s["game_toolbar_hotkey"])
        self._hotkey.set_accent(accent)
        self._hotkey.set_label(t("tb_hotkey"))
        # Directions', the Minimap's and Navigation's switches: each on from its setting, named as its label
        for switch, key, name in ((self._rides, "game_rides", "tb_rides"),
                                  (self._hidden_portals, "minimap_hidden_portals", "minimap_hidden_portals"),
                                  (self._route_arrow, "minimap_route_arrow", "minimap_route_arrow"),
                                  (self._arrow_label, "minimap_arrow_label", "tbs_arrow_label"),
                                  (self._arrow_flash, "minimap_arrow_flash", "tbs_arrow_flash"),
                                  (self._arrival, "minimap_arrival_notice", "tbs_arrival"),
                                  (self._overlay_shots, "overlays_in_screenshots", "overlays_in_screenshots"),
                                  (self._route_follow, "minimap_route_follow", "set_route_follow"),
                                  (self._route_steps, "minimap_route_steps", "set_route_steps"),
                                  (self._teleport_arrows, "map_teleport_arrows", "set_teleport_arrows")):
            switch.setChecked(bool(s[key]))
            switch.set_accent(accent)
            switch.setAccessibleName(t(name))
        # the route arrow's size in whole pixels, between the slider's ends (a size past one: that end)
        try:
            size = float(s["minimap_arrow_size"])
        except (TypeError, ValueError):
            size = DEFAULT_SETTINGS["minimap_arrow_size"]
        size = round(min(ARROW_SIZE_MAX, max(ARROW_SIZE_MIN, size)))
        self._arrow_size.set_value(size)
        self._arrow_size.set_accent(accent)
        self._arrow_size.setAccessibleName(t("tbs_arrow_size"))
        self._arrow_size_value.setText(bidi.ltr_block(f"{size} px", rtl))
        # ... how solid it is drawn and, on its own, the name beside it: each a whole percent between its slider's ends
        # (a value past one: that end)
        for slider, shown, key, name in ((self._arrow_opacity, self._arrow_opacity_value, "minimap_arrow_opacity",
                                          "tbs_arrow_opacity"),
                                         (self._label_opacity, self._label_opacity_value,
                                          "minimap_arrow_label_opacity", "tbs_arrow_label_opacity")):
            try:
                opacity = float(s[key])
            except (TypeError, ValueError):
                opacity = DEFAULT_SETTINGS[key]
            opacity = min(ARROW_OPACITY, max(ARROW_OPACITY_MIN, opacity))
            slider.set_value(opacity)
            slider.set_accent(accent)
            slider.setAccessibleName(t(name))
            shown.setText(bidi.ltr_block(f"{round(opacity * 100)}%", rtl))
        self._reset.setEnabled(any(s[k] != DEFAULT_SETTINGS[k] for k in LOOK_KEYS))
        self._fit(self._room())
        self.update()

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._opacity)

    def place_under(self, btn) -> None:
        """Under the ⚙ that opened it, centred on it, kept on its screen and no taller than the room there (_fit:
        the sections scroll past it; the panel may open on another screen than the primary one)."""
        g = btn.mapToGlobal(QPoint(0, btn.height()))
        self._fit(self._room(g))
        screen = QGuiApplication.screenAt(g) or QGuiApplication.primaryScreen()
        room = screen.availableGeometry()
        x = min(max(room.left(), g.x() + btn.width() // 2 - self.width() // 2),
                max(room.left(), room.right() - self.width() + 1))
        y = min(max(room.top(), g.y() + 4), max(room.top(), room.bottom() - self.height() + 1))
        self.move(x, y)

    def _room(self, at: QPoint | None = None) -> int:
        """The most height the panel takes: the room between the taskbar and the top of its screen (the one at `at`,
        the ⚙'s; else the one under the panel's centre), PANEL_SPARE kept."""
        screen = (QGuiApplication.screenAt(self.geometry().center() if at is None else at)
                  or QGuiApplication.primaryScreen())
        return screen.availableGeometry().height() - PANEL_SPARE

    def _fit(self, room: int) -> None:
        """As tall as the title row and the sections need (the taller column, then Reset under both), at most `room`:
        past it the sections scroll under the title row, their scrollbar in the side margin's PANEL_BAR (the right;
        the left in Hebrew, where Qt moves it), so they keep their place and width either way. With the room for
        them all (a 1080p screen at 125 % has it), no scrollbar."""
        m, lay = self.layout().contentsMargins(), self._body_lay
        b = lay.contentsMargins()
        # the sections at their own width (the panel's less its side margins), whatever room the scrollbar has now:
        # no row wraps (a hint is one line, cut to its column), so it is their size hint's height
        width = PANEL_W - 2 * PANEL_SIDE + b.left() + b.right()
        body = lay.totalHeightForWidth(width) if lay.hasHeightForWidth() else lay.totalSizeHint().height()
        needed = m.top() + self._head.sizeHint().height() + body + m.bottom()
        scrolls = needed > room
        near = PANEL_GUTTER if scrolls else PANEL_BAR            # the sections' margin on the scrollbar's side
        rtl = self.t.rtl
        self._body_lay.setContentsMargins(near if rtl else PANEL_BAR, 0, PANEL_BAR if rtl else near, 0)
        # shown exactly when they don't fit: Qt's own as-needed guess, made at the width before the scrollbar, could
        # leave it off for a few pixels' overflow and the sections spread over its room
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn if scrolls else Qt.ScrollBarAlwaysOff)
        self.resize(PANEL_W, min(needed, room))

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
        """A percent on the slider: written, on this panel's and the bar's glass at once, and every other window
        over the game follows a moment later (_follow: once per FOLLOW_MS of a drag, not at every percent)."""
        self._settings["npc_overlay_opacity"] = value
        self.refresh()
        self._bar.opacity_followed()
        if not self._follow.isActive():
            self._follow.start()

    def _opacity_settled(self) -> None:
        """The slider let go: every window at the last percent now, not after the moment's wait."""
        if self._follow.isActive():
            self._follow.stop()
            self.changed.emit()

    def _pick_rides(self, _=False) -> None:
        """Cabs & Teleports: written, and a way already shown is found again (the bar's rides_toggled, which the
        app wires to the search's page and the where-is-it window)."""
        self._settings["game_rides"] = self._rides.isChecked()
        self._bar.rides_toggled.emit()

    def _pick_hidden(self, _=False) -> None:
        """Hidden portals on the minimap: written, and the blue dots on the game's minimap come or go (the bar's
        minimap_toggled, which the app wires to the dots, the windows' captures and the pickers' pages)."""
        self._settings["minimap_hidden_portals"] = self._hidden_portals.isChecked()
        self._bar.minimap_toggled.emit()

    def _pick_route(self, _=False) -> None:
        """The route arrow on the minimap: written, and the arrow comes or goes, with the line naming it on the
        search's page and in the ◎ window (minimap_toggled)."""
        self._settings["minimap_route_arrow"] = self._route_arrow.isChecked()
        self._bar.minimap_toggled.emit()

    def _pick_arrow_color(self, key: str) -> None:
        """The route arrow's colour: written, ringed and named here, and the arrow on the game's minimap drawn in it
        (minimap_toggled)."""
        self._settings["minimap_arrow_color"] = key
        self.refresh()
        self._bar.minimap_toggled.emit()

    def _pick_arrow_size(self, value: float) -> None:
        """A length on the slider: the whole pixel nearest it is written at once, under the knob and beside the label,
        and the app follows a moment later (_arrow_follow: minimap_toggled, which redraws the arrow on the game's
        minimap but the search's page and the ◎ window too, once per FOLLOW_MS of a drag, not at every pixel)."""
        size = round(value)
        if size == self._settings["minimap_arrow_size"]:
            self._arrow_size.set_value(size)        # a step inside the same pixel: the knob stays on it
            return
        self._settings["minimap_arrow_size"] = size
        self.refresh()                              # the knob on the new pixel, its px beside the label
        if not self._arrow_follow.isActive():
            self._arrow_follow.start()

    def _arrow_size_settled(self) -> None:
        """The slider let go: the app follows the last pixel now, not after the moment's wait."""
        if self._arrow_follow.isActive():
            self._arrow_follow.stop()
            self._bar.minimap_toggled.emit()

    def _pick_arrow_opacity(self, value: float) -> None:
        """How solid the route's and the guided NPC's arrows and the maps-left strip are drawn (_pick_percent); the
        names beside the arrows keep their own (_pick_label_opacity), the hidden portals' dots and the NPC's ring
        stay solid."""
        self._pick_percent("minimap_arrow_opacity", self._arrow_opacity, value)

    def _pick_label_opacity(self, value: float) -> None:
        """How solid the names beside the arrows are drawn, whatever the arrows' own opacity (_pick_percent)."""
        self._pick_percent("minimap_arrow_label_opacity", self._label_opacity, value)

    def _pick_percent(self, key: str, slider: Slider, value: float) -> None:
        """A percent on one of the arrow's opacity sliders: written at once and shown beside its label, and the app
        follows a moment later on the size slider's own timer (_arrow_follow: minimap_toggled, once per FOLLOW_MS of
        a drag, and once more at the percent it was let go on, _arrow_size_settled)."""
        if value == self._settings[key]:
            slider.set_value(value)                 # a step inside the same percent: the knob stays on it
            return
        self._settings[key] = value
        self.refresh()                              # the knob on the new percent, its % beside the label
        if not self._arrow_follow.isActive():
            self._arrow_follow.start()

    def _pick_arrow_label(self, _=False) -> None:
        """The name beside the arrow: written, and the small label by the arrow on the game's minimap (the map its
        portal leads to, or the NPC to talk to) comes or goes (minimap_toggled)."""
        self._settings["minimap_arrow_label"] = self._arrow_label.isChecked()
        self._bar.minimap_toggled.emit()

    def _pick_arrow_flash(self, _=False) -> None:
        """The flashing arrow: written, and the arrow on the game's minimap blinks or holds still (minimap_toggled)."""
        self._settings["minimap_arrow_flash"] = self._arrow_flash.isChecked()
        self._bar.minimap_toggled.emit()

    def _pick_arrival(self, _=False) -> None:
        """The notice on arriving: written, and reaching the map the arrow leads to says so in a small notice, or
        passes without one (minimap_toggled)."""
        self._settings["minimap_arrival_notice"] = self._arrival.isChecked()
        self._bar.minimap_toggled.emit()

    def _pick_shots(self, _=False) -> None:
        """The overlays in screenshots: written, and every window over the game, this panel too, shows in screen
        captures or stays out of them at once (minimap_toggled: the app's _apply_overlay_capture)."""
        self._settings["overlays_in_screenshots"] = self._overlay_shots.isChecked()
        self._bar.minimap_toggled.emit()

    def _pick_route_follow(self, _=False) -> None:
        """Guiding the whole way: written, and the arrow either keeps leading map after map, re-pointing on each new
        read and working the way out again after a wrong portal, or leads one step only (minimap_toggled)."""
        self._settings["minimap_route_follow"] = self._route_follow.isChecked()
        self._bar.minimap_toggled.emit()

    def _pick_route_steps(self, _=False) -> None:
        """How many maps are left: written, and the count comes or goes beside the arrow (minimap_toggled)."""
        self._settings["minimap_route_steps"] = self._route_steps.isChecked()
        self._bar.minimap_toggled.emit()

    def _pick_teleport_arrows(self, _=False) -> None:
        """The teleport arrows on Maple Helper's own map window: written only. No minimap_toggled: nothing over the
        game changes, and the map window takes the setting the next time it draws."""
        self._settings["map_teleport_arrows"] = self._teleport_arrows.isChecked()

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


class _ToolsMenu(QWidget):
    """The bar's Tools button's little glass card: the tool windows (TOOLS) in MENU_COLS columns, read in rows from
    the leading edge (the right, in Hebrew), all one width; each is its window's switch (lit while the window is open;
    a click flips its setting through the bar's tool_toggled). Like the bar it never takes the keyboard from the game.
    It goes on a pick, on the Tools button again, with the bar hidden or moved, or once the mouse has been off it and
    the Tools button for AWAY_MS (no focus to lose: _check_away asks where the mouse is)."""

    def __init__(self, bar: GameToolbar):
        super().__init__(bar, _flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self._bar = bar
        self.setStyleSheet(bar.styleSheet())       # the bar's (qss); _restyle keeps them the same
        col = QVBoxLayout(self)
        col.setContentsMargins(SHADOW + 6, SHADOW + 6, SHADOW + 6, SHADOW + 6)
        col.setSizeConstraint(QLayout.SetFixedSize)     # as big as its buttons
        grid = QGridLayout()
        grid.setSpacing(4)
        col.addLayout(grid)
        self.buttons: dict[str, QPushButton] = {}
        for i, key in enumerate(TOOLS):
            b = QPushButton(checkable=True, objectName="MenuItem")
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setIconSize(QSize(WORD_ICON_PX, WORD_ICON_PX))
            b.clicked.connect(lambda _=False, k=key: bar._tool_clicked(k))
            self.buttons[key] = b
            grid.addWidget(b, i // MENU_COLS, i % MENU_COLS)
        self._away = QTimer(self, interval=AWAY_POLL_MS, timeout=self._check_away)
        self._away_since: float | None = None

    def retext(self, t: I18n, settings) -> None:
        """The tools' names, tips and icons (the glass's text colour, the accent's own text colour while lit)."""
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        _, on_fill = accent_of(settings)
        for key, b in self.buttons.items():
            name = TOOLS[key]
            b.setText(bidi.plain(t(name), t.rtl).replace("&", "&&"))
            b.setToolTip(t(name + "_tip"))
            b.setAccessibleName(t(name))
            b.setIcon(line_icon(ICONS[name], palette().text, on=on_fill))
        # every button as wide as the widest: the columns line up whatever the words (each language's own)
        for b in self.buttons.values():
            b.ensurePolished()
        widest = max(b.sizeHint().width() for b in self.buttons.values())
        for b in self.buttons.values():
            b.setMinimumWidth(widest)

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._bar._opacity)

    def place(self, btn: QPushButton, upright: bool) -> None:
        """Beside the bar at its Tools button: under (or, with no room, over) a lying bar, lined up with the button's
        leading edge; at the trailing side (or, with no room, the other) of an upright one, lined up with its top.
        The glass's edges sit GAP apart (each window's shadow margin left out), all of it on the button's screen."""
        self.adjustSize()
        bar, w, h = self._bar, self.width(), self.height()
        b = QRect(btn.mapToGlobal(QPoint(0, 0)), btn.size())
        f = bar.frameGeometry()
        screen = QGuiApplication.screenAt(b.center()) or QGuiApplication.primaryScreen()
        room = screen.availableGeometry()
        rtl = bar.layoutDirection() == Qt.RightToLeft
        if upright:
            after = f.left() + SHADOW - GAP - w + SHADOW if rtl else f.right() + 1 - SHADOW + GAP - SHADOW
            before = f.right() + 1 - SHADOW + GAP - SHADOW if rtl else f.left() + SHADOW - GAP - w + SHADOW
            fits = (lambda x: x >= room.left() - SHADOW) if rtl else (lambda x: x + w <= room.right() + 1 + SHADOW)
            x = after if fits(after) else before
            y = b.top() - SHADOW - 6
        else:
            x = b.right() + 1 - w + SHADOW + 6 if rtl else b.left() - SHADOW - 6
            below = f.bottom() + 1 - SHADOW + GAP - SHADOW
            y = below if below + h <= room.bottom() + 1 + SHADOW else f.top() + SHADOW - GAP - h + SHADOW
        self.move(min(max(x, room.left() - SHADOW), room.right() + 1 + SHADOW - w),
                  min(max(y, room.top() - SHADOW), room.bottom() + 1 + SHADOW - h))

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._away_since = None
        self._away.start()

    def hideEvent(self, e) -> None:
        self._away.stop()
        super().hideEvent(e)
        self._bar._tools_menu_shown(False)

    def _check_away(self) -> None:
        """The mouse off the card and the Tools button (with a few pixels' slack) for AWAY_MS: the card goes."""
        btn = self._bar._tools_btn
        zone = self.frameGeometry().adjusted(SHADOW - 8, SHADOW - 8, 8 - SHADOW, 8 - SHADOW).united(
            QRect(btn.mapToGlobal(QPoint(0, 0)), btn.size()).adjusted(-8, -8, 8, 8))
        if zone.contains(QCursor.pos()):
            self._away_since = None
            return
        now = time.monotonic()
        if self._away_since is None:
            self._away_since = now
        elif (now - self._away_since) * 1000 >= AWAY_MS:
            self.hide()


class GameToolbar(EdgeResize, QWidget):
    """The bar itself. The NPCs-here button flips settings["npc_overlay"] (npc_toggled: the window follows),
    the search buttons ask for their search (search_requested: "monster_npc", "map", "item" or "sell"), and
    the ✕ turns the bar itself off (closed: the app says how to bring it back). Its length is dragged shorter and
    longer (its width; its height upright, the ◯ before the grip turning it), the buttons wrapping into lines and
    showing icons alone once the words would take more than WORD_LINES_MAX lines; Tools opens a little card with the
    tool windows (_ToolsMenu); the ⚙ opens the panel with the look, the icons mode, the bar's key, Cabs & Teleports,
    the hidden-teleport routes and Minimap: the hidden portals, the route arrow (its colour, size, the name beside it
    and its flashing, and a notice on reaching its map) and the overlays in screenshots (rides_toggled and
    minimap_toggled stay the bar's signals). Clicks work but it never takes the keyboard from the game, and the
    minimap reads never see it. Its place is kept in game_toolbar_pos, its length in game_toolbar_width (or
    game_toolbar_height upright), the way it stands in game_toolbar_vertical."""

    search_requested = Signal(str)     # which search to open: "monster_npc" | "map" | "item" | "sell"
    npc_toggled = Signal()             # settings["npc_overlay"] flipped: the NPCs-here window follows
    rides_toggled = Signal()           # a ⚙ panel Directions switch flipped its setting: a way shown follows
    minimap_toggled = Signal()         # a ⚙ panel Minimap choice written: dots, arrow, screenshots, pickers follow
    loot_toggled = Signal()            # settings["loot_overlay"] flipped: the loot log's window follows
    grind_toggled = Signal()           # settings["grind_bar"] flipped: the grind bar over the game follows
    tool_toggled = Signal(str)         # a TOOLS setting flipped (the Tools card's buttons): its window follows
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
        self._default_at: QPoint | None = None   # where it opened by the minimap with no place saved, until moved
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
        LOCATION.boxed.connect(self._box_moved)  # the game's minimap window found, or found elsewhere

    # ------------------------------------------------------------ the bar

    def _build(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(SIDE, TOP, SIDE, BOTTOM)
        col.setSpacing(0)
        col.setSizeConstraint(QLayout.SetNoConstraint)    # the bar sets its own limits (_apply_size)
        self._flow = _BarLayout(FLOW_GAP)
        col.addLayout(self._flow)
        # the ◯ before the grip's dots: the bar upright (a column) or lying (a row)
        self._orient = QToolButton(objectName="Orient")       # (its icon, the ⚙'s and the ✕'s: _retext, in the glass's colours)
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
        # the loot log's window, as the NPCs-here button is its window's: the checkable button is the setting
        self._loot = QPushButton(checkable=True)
        self._loot.setCursor(Qt.PointingHandCursor)
        self._loot.setFocusPolicy(Qt.NoFocus)
        self._loot.clicked.connect(self._loot_clicked)
        self._flow.addWidget(self._loot)
        # the grind bar over the game, as Loot Log is its window's: the checkable button is the setting
        self._grind = QPushButton(checkable=True)
        self._grind.setCursor(Qt.PointingHandCursor)
        self._grind.setFocusPolicy(Qt.NoFocus)
        self._grind.clicked.connect(self._grind_clicked)
        self._flow.addWidget(self._grind)
        # Tools: the card with the tool windows' switches (TOOLS), lit while it is up
        self._tools_btn = QPushButton()
        self._tools_btn.setCursor(Qt.PointingHandCursor)
        self._tools_btn.setFocusPolicy(Qt.NoFocus)
        self._tools_btn.clicked.connect(self._tools_clicked)
        self._flow.addWidget(self._tools_btn)
        self._menu = _ToolsMenu(self)
        self._tools: dict[str, QPushButton] = self._menu.buttons     # each its window's setting
        # the ⚙: the panel with the look, the icons mode, the bar's key, Directions and Minimap; then the ✕
        self._gear = QToolButton(objectName="Gear")
        self._close = QToolButton(objectName="Close")
        for b, slot in ((self._gear, self._gear_clicked), (self._close, self._close_clicked)):
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
        """Every button on the bar with its i18n key: the texts, tooltips and icons follow the language (the Tools
        card's own buttons: _ToolsMenu.retext)."""
        yield self._npcs, "tb_npcs_here"
        for kind, key in KINDS.items():
            yield self._search[kind], key
        yield self._loot, "tb_loot"
        yield self._grind, "tb_grind"
        yield self._tools_btn, "tb_tools"

    def _paint_icon(self, b: QPushButton, key: str) -> None:
        """The button's line icon in its text's colours: the glass's text colour, the accent's own text colour while
        lit (checked, or lit by its "on": a search's mode, the Tools card up)."""
        _, on_fill = accent_of(self._settings)
        b.setIcon(line_icon(ICONS[key], on_fill if b.property("on") else palette().text, on=on_fill))

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
        pal = palette()
        self._orient.setIcon(line_icon("circle", pal.muted, hover=pal.text))
        for b in (self._gear, self._close):
            b.setIcon(line_icon("settings" if b is self._gear else "x", pal.muted, hover=pal.text))
        self._gear.setAccessibleName(t("tbs_title"))
        self._gear.setToolTip(t("tbs_title"))
        self._close.setAccessibleName(t("tb_close"))
        self._close.setToolTip(t("tb_close"))
        self._menu.retext(t, self._settings)
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
        if self._menu.isVisible():
            self._menu.place(self._tools_btn, self._upright())    # the Tools button moved with the wrap
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

    def _loot_clicked(self, _=False) -> None:
        """The loot log's window on or off: the button is the setting (its Start, Stop and Reset are in it)."""
        self._settings["loot_overlay"] = self._loot.isChecked()
        self.loot_toggled.emit()

    def _grind_clicked(self, _=False) -> None:
        """The grind bar on or off: the button is the setting (the bar has its own Start, Pause and Stop)."""
        self._settings["grind_bar"] = self._grind.isChecked()
        self.grind_toggled.emit()

    def _tools_clicked(self, _=False) -> None:
        """Tools: its card with the tool windows beside the button, or gone when it is up."""
        if self._menu.isVisible():
            self._menu.hide()
            return
        self._menu.place(self._tools_btn, self._upright())
        self._menu.show()
        set_capturable(self._menu, self._settings)
        self._tools_menu_shown(True)

    def _tools_menu_shown(self, on: bool) -> None:
        """The Tools button lit while its card is up, as a search's button is while its mode is."""
        b = self._tools_btn
        if b.property("on") != on:
            b.setProperty("on", on)
            b.style().unpolish(b)
            b.style().polish(b)
            self._paint_icon(b, "tb_tools")

    def _tool_clicked(self, key: str) -> None:
        """A tool window on or off from the Tools card: the button is its setting (the window follows
        tool_toggled), and the card goes, its pick made."""
        self._settings[key] = self._tools[key].isChecked()
        self._menu.hide()
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
        """A choice in the ⚙ panel: the bar's own style, texts and icons (icons mode, the accent, the glass's
        colours) and glass follow at once."""
        self._restyle()
        self._retext()
        self.opacity_followed()

    def opacity_followed(self) -> None:
        """The transparency the settings give, on the bar's glass and its Tools card's at once."""
        try:
            self._opacity = min(OPACITY_MAX, max(OPACITY_MIN, float(self._settings["npc_overlay_opacity"])))
        except (TypeError, ValueError):
            self._opacity = OPACITY_DEFAULT
        self.update()
        self._menu.update()

    def _restyle(self) -> bool:
        """The glass's colours, the accent (and the icons mode's room) the settings pick, on the bar and its Tools
        card; skipped when it is the same. True: restyled."""
        sheet = qss(self._settings)
        if sheet == self.styleSheet():
            return False
        self.setStyleSheet(sheet)
        self._menu.setStyleSheet(sheet)
        return True

    # ------------------------------------------------------------ place and move

    def _place(self) -> None:
        """Where the bar opens: where the player left it, when that is still on a screen (a monitor since
        unplugged: above the minimap box again)."""
        screens = [s.geometry() for s in QGuiApplication.screens()]
        spot = mapview.saved_spot(self._settings["game_toolbar_pos"], self.size(), screens)
        self._default_at = self._default_spot() if spot is None else None
        self.setGeometry(QRect(spot if spot is not None else self._default_at, self.size()))
        self._placed = True

    def _default_spot(self) -> QPoint:
        """Just above the game's minimap window (npcoverlay.minimap_box: the bar is about the map in it), left edges
        lined up; else the primary screen's top centre."""
        screens = [(s.geometry(), s.devicePixelRatio()) for s in QGuiApplication.screens()]
        box = minimap_box(screens)
        primary = QGuiApplication.primaryScreen().availableGeometry()
        if box is not None:
            screen = next((g for g, _ in screens if g.intersects(box)), primary)
            x = min(max(box.left(), screen.left()), screen.right() - self.width() + 1)
            y = min(max(box.top() - self.height() - GAP, screen.top()),
                    max(screen.top(), screen.bottom() - self.height() + 1))
            return QPoint(x, y)
        return QPoint(primary.center().x() - self.width() // 2, primary.top() + SHADOW + 4)

    def _box_moved(self, box: dict | None) -> None:
        """LOCATION.boxed: the game's minimap window found, or found elsewhere. Still where it opened by default
        (the player hasn't moved it), the bar moves above the new box; a box gone (the minimap closed) leaves it
        where it is."""
        if box is not None and self.isVisible() and self._default_at is not None and self.pos() == self._default_at:
            self._default_at = self._default_spot()
            self.move(self._default_at)

    def moveEvent(self, e) -> None:
        self._geom.start()
        if self._menu.isVisible():
            self._menu.hide()            # the bar dragged away from its Tools card
        super().moveEvent(e)

    def hideEvent(self, e) -> None:
        if self._placed:             # turned off or the app closing: keep the place now, not 400 ms later
            self._geom.stop()
            self._remember()
            self._lengths.stop()
            self._remember_length()
        if self._panel is not None:
            self._panel.hide()
        self._menu.hide()
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
        self.opacity_followed()
        self._npcs.setChecked(bool(self._settings["npc_overlay"]))
        self._loot.setChecked(bool(self._settings["loot_overlay"]))
        self._grind.setChecked(bool(self._settings["grind_bar"]))
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
