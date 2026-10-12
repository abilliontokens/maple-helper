"""The base of the tool windows over the game that the toolbar's Tools card opens (ui/gametoolbar.py TOOLS): Grind
spots, Farm, Quests, Citizenship, Build & skills and the Cash shop are each a ToolWindow, so they all look and behave
alike, as the grind window (ui/grindwindow.py) and the gear advisor (ui/gearadvisor.py) do:

- the NPCs window's glass (npcoverlay._paint_glass) in the tint, accent and opacity the ⚙ panel picks, its style
  (tool_qss) built again on every refresh, so a window follows the panel with no code of its own;
- the title row that drags it, its ✕ turning the window's setting (SHOW_KEY) off (closed: the bar's button follows);
  a tab row under it when the window has tabs (TABS: controls.Segmented, as the grind window's); a row that stays in
  view (self.top: a search box, say) over the cards, which scroll (self.body);
- its place and size kept in GEOM_KEY: just under the toolbar (place_under) until the player moves it, back there
  when the screen it was on is gone; out of screen captures (set_capturable), kept over the game on macOS;
- it never takes the keyboard from the game, only while the player types in one of its boxes (key_box: Esc, or a
  click on another window, gives it back);
- a window that reads the character (NEEDS_CHARACTER) shows one card instead while there is none: add a character
  (its button: NAV.add_character_requested).

A window sets SHOW_KEY, GEOM_KEY and TITLE_KEY (its setting, its place's setting, its title's i18n key), its sizes
and TABS; _build_body() makes its own widgets once, inside ToolWindow.__init__ (with the state they need), into
self.top and self.body; _rebuild() fills them, and runs every time the window opens and, while it shows, when a tab is
picked or the language, the KB or the character changes (never without a character when the window needs one: the
card shows instead). open_with(arg) shows it on one thing (an item's name, a quest's key). The builders below (card,
label, caption, chips, button, stat, empty, key_box) make each piece in the names the style knows.

NAV is how a tool window asks for the rest of the app, which wires it once at start-up (app.py): a map's, a
monster's, an NPC's or an item's page in the toolbar's search, another tool window on something, the chat, the
guides, a new character.

The style's names, the same in every tool window (tool_qss; a window adds its own in extra_qss()):
  Title                the title row's words
  Close                the ✕
  Tabs                 the tab row (its segments QPushButton#Segment; a switch of the window's own: #Segmented)
  Rows                 the scrolling body
  Card                 a card on the glass (card()); [lit="true"]: lit in the accent (the best pick)
  CardTitle            a card's name, bold
  CardSub              the line under it, muted
  Caption              a section's small heading over its cards (caption(): capitals in English)
  Text                 a sentence in the glass's text colour
  Muted                a sentence in the muted colour
  Hint                 a small muted line saying what to do
  Note                 a smaller muted note (where a number comes from, "and 5 more")
  Chip, ChipOn         a small tag (chips()); ChipOn lit in the accent
  Link                 a text button in the accent ("Show the way")
  Primary              the accent's solid button: the one thing to do
  Small                a small plain button (Edit, Done)
  SearchBox            a typing box (key_box())
  BigStat              a big figure (stat())
  BigStatLabel         ... its small name under it
  Empty, EmptyIcon, EmptyTitle, EmptyHint      a card with nothing to show yet (empty())"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from .. import bidi
from ..i18n import I18n
from ..kb import KnowledgeBase
from ..store import Profiles, Settings
from . import mapview, theme
from .controls import FlowLayout, Segmented
from .gamesearch import glass_qss, rim
from .glass import SHADOW, EdgeResize
from .lookpick import line_icon
from .npcoverlay import (BOTTOM, GEOM_DEBOUNCE_MS, KEYS_CHECK_MS, OPACITY_DEFAULT, OPACITY_MAX, OPACITY_MIN, SIDE,
                         TOP, _accept_keys, _flags, _foreground, _Header, _paint_glass, _to_foreground, accent_of,
                         ink, keep_over_game, palette, set_capturable)
from .scrollplanner import _Body

GAP = 8                 # between the toolbar and a window that opens under it
GUTTER = 4              # between the cards and the scrollbar
EMPTY_ICON = 36         # an empty card's circle
EMPTY_GLYPH = 18        # ... and the line icon in it
CLOSE_KEY = "tb_tool_close"     # the ✕'s tip: every tool window comes back from the bar's Tools card


class _Nav(QObject):
    """How a tool window asks for the rest of the app. app.py connects each signal once, at start-up; a window only
    emits. The keys are the KB's ("map/<id>", "monster/<id>", ...)."""

    map_requested = Signal(str)           # "map/<id>": the toolbar's Maps search opens on that map's page, the way there
    monster_requested = Signal(str)       # "monster/<id>": the Monsters & NPCs search on the monster's page
    npc_requested = Signal(str)           # "npc/<id>": ... on the NPC's page
    item_requested = Signal(str)          # "item/<id>": the Items search on the item's page (its prices, who drops it)
    tool_requested = Signal(str, str)     # a tool's key (gametoolbar.TOOLS) and what to show: that window's open_with
    add_character_requested = Signal()    # the add-a-character card's button: the new character's setup
    read_screen_requested = Signal()      # the chat reads the level, EXP and stats off a screenshot (overlay.sync_profile)
    guide_requested = Signal(str)         # a guide's KB key: the guides window open on it
    ask_requested = Signal(str)           # a question for the chat


NAV = _Nav()


def _rgba(color: str, alpha: float) -> str:
    """A colour ("#RRGGBB" or "rgba(...)") at this opacity, for a tinted fill."""
    c = theme.qcolor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def tool_qss(settings) -> str:
    """Every tool window's style at the accent the settings pick (npcoverlay.ACCENTS), in the palette of the glass
    under it (npcoverlay.palette(): dark text on the white glass; the accent's text through ink): the glass's own
    look (gamesearch.glass_qss), then the names this module's docstring lists. The glass itself is painted in the tint
    by _paint_glass. Built again on every refresh, so the window follows the ⚙ panel with no code of its own."""
    p = palette()
    fill, on_fill = accent_of(settings)
    lit = ink(fill)
    chip = "border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700;"
    return glass_qss(p) + f"""
QLabel {{ background: transparent; }}
#Tabs, #Segmented {{ background: {p.fill1}; border: none; border-radius: 10px; }}
QPushButton#Segment {{ background: transparent; color: {p.muted}; border: none; border-radius: 8px; min-height: 26px;
                       max-height: 26px; padding: 0 8px; font-size: 12px; font-weight: 600; text-align: center; }}
QPushButton#Segment:hover:!checked {{ background: {p.fill2}; color: {p.text}; }}
QPushButton#Segment:checked {{ background: {fill}; color: {on_fill}; font-weight: 700; }}
QFrame#Card {{ background: {p.fill1}; border: 1px solid transparent; border-radius: 12px; }}
QFrame#Card[lit="true"] {{ background: {_rgba(fill, 0.10)}; border: 1px solid {fill}; }}
#CardTitle {{ color: {p.text}; font-size: 13px; font-weight: 700; }}
#CardSub {{ color: {p.muted}; font-size: 12px; }}
#Caption {{ color: {p.muted}; font-size: 10px; font-weight: 700; padding: 2px 2px 0 2px; }}
#Text {{ color: {p.text}; font-size: 13px; }}
#Muted {{ color: {p.muted}; font-size: 13px; }}
#Hint {{ color: {p.muted}; font-size: 12px; }}
#Note {{ color: {p.muted}; font-size: 11px; }}
QLabel#Chip {{ color: {p.text}; background: {rim(0.10, p)}; {chip} }}
QLabel#ChipOn {{ color: {lit}; background: {_rgba(fill, 0.16)}; {chip} }}
QPushButton#Link {{ background: transparent; color: {lit}; border: none; border-radius: 0; min-height: 0;
                    padding: 1px 0; font-size: 12px; font-weight: 700; text-align: left; text-decoration: none; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QPushButton#Link:disabled {{ color: {p.muted}; }}
QPushButton#Primary {{ background: {fill}; color: {on_fill}; border: none; border-radius: 8px; min-height: 0;
                       padding: 5px 14px; font-size: 12px; font-weight: 700; text-align: center; }}
QPushButton#Primary:hover {{ background: {theme.qcolor(fill).lighter(112).name()}; }}
QPushButton#Primary:disabled {{ background: {p.fill1}; color: {p.muted}; }}
QPushButton#Small {{ background: {p.fill1}; color: {p.text}; border: none; border-radius: 7px; min-height: 0;
                     padding: 3px 10px; font-size: 12px; font-weight: 600; text-align: center; }}
QPushButton#Small:hover {{ background: {p.fill2}; }}
QLineEdit#SearchBox {{ border: 1px solid transparent; padding: 6px 8px; }}
QLineEdit#SearchBox:focus {{ border: 1px solid {fill}; }}
#BigStat {{ color: {p.text}; font-size: 20px; font-weight: 700; }}
#BigStatLabel {{ color: {p.muted}; font-size: 11px; font-weight: 700; }}
QFrame#Empty {{ background: {p.fill1}; border: none; border-radius: 12px; }}
#EmptyIcon {{ background: {p.fill2}; border-radius: {EMPTY_ICON // 2}px; }}
#EmptyTitle {{ color: {p.text}; font-size: 14px; font-weight: 600; }}
#EmptyHint {{ color: {p.muted}; font-size: 12px; }}
"""


def _label(text: str, name: str, wrap: bool = False) -> QLabel:
    w = QLabel(text, objectName=name)
    w.setWordWrap(wrap)
    return w


def clear(lay) -> None:
    """Every widget out of a layout (one a window fills again: widgets and stretches only)."""
    while lay.count():
        w = lay.takeAt(0).widget()
        if w is not None:
            w.hide()            # gone now: deleteLater alone left the old rows drawn under the new ones
            w.deleteLater()


class KeyBox(QLineEdit):
    """A tool window's typing box. Its window never takes the keyboard, so a click in here asks for it while the
    player types (wants_keys); Esc gives it back to the game (done), Enter is the window's to act on (entered).
    search: the magnifier before the words."""

    wants_keys = Signal()
    done = Signal()
    entered = Signal()

    def __init__(self, search: bool = True):
        super().__init__(objectName="SearchBox")
        self.setFocusPolicy(Qt.ClickFocus)          # never the focus a shown window hands its first box
        self._find = self.addAction(QIcon(), QLineEdit.LeadingPosition) if search else None

    def paint_icon(self, colour: str) -> None:
        """The magnifier in the glass's muted colour now (the white glass takes a dark one)."""
        if self._find is not None:
            self._find.setIcon(line_icon("search", colour))

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


class EmptyCard(QFrame):
    """A card with nothing to show yet: a line icon (assets/icons/toolbar) in its circle, a line in bold and what to
    do under it, and the button that does it (action: made with one)."""

    def __init__(self, action: bool = False):
        super().__init__(objectName="Empty")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(12)
        self.icon = QLabel(objectName="EmptyIcon", alignment=Qt.AlignCenter)
        self.icon.setFixedSize(EMPTY_ICON, EMPTY_ICON)
        self._icon_name = ""
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        self.title = _label("", "EmptyTitle", wrap=True)
        self.hint = _label("", "EmptyHint", wrap=True)
        v.addWidget(self.title)
        v.addWidget(self.hint)
        self.button: QPushButton | None = None
        if action:
            self.button = QPushButton(objectName="Primary")
            self.button.setCursor(Qt.PointingHandCursor)
            self.button.setFocusPolicy(Qt.NoFocus)
            v.addSpacing(6)
            v.addWidget(self.button, 0, Qt.AlignLeft)       # the leading edge (mirrored in Hebrew)
        h.addWidget(self.icon, 0, Qt.AlignTop)
        h.addLayout(v, 1)

    def say(self, icon: str, title: str, hint: str, rtl: bool, action: str = "") -> None:
        self._icon_name = icon
        self.title.setText(bidi.plain(title, rtl))
        self.hint.setText(bidi.plain(hint, rtl))
        self.hint.setVisible(bool(hint))
        if self.button is not None:
            self.button.setText(bidi.plain(action, rtl).replace("&", "&&"))
        self.paint_icon(palette().text)

    def paint_icon(self, colour: str) -> None:
        """The icon in the glass's text colour now, at the screen's own pixels."""
        if self._icon_name:
            icon = line_icon(self._icon_name, colour)
            self.icon.setPixmap(icon.pixmap(QSize(EMPTY_GLYPH, EMPTY_GLYPH), self.icon.devicePixelRatioF()))


class ToolWindow(EdgeResize, QWidget):
    """A tool window over the game, in the NPCs window's glass (the module's docstring has the whole of it). Clicks
    work (its tabs, its cards' buttons; the edges resize it) but it never takes the keyboard from the game, only
    while the player types in one of its boxes. Shows while settings[SHOW_KEY] is on; its place is kept in
    settings[GEOM_KEY]."""

    SHOW_KEY = ""                       # the setting it shows while on (= its key in gametoolbar.TOOLS)
    GEOM_KEY = ""                       # the setting its place and size are kept in: {"x","y","w","h"}
    TITLE_KEY = ""                      # its title's i18n key
    MIN_W, MIN_H = 360, 400             # the smallest the player can drag it to
    DEFAULT_W, DEFAULT_H = 420, 620     # what opens before it is ever resized
    NEEDS_CHARACTER = True              # its cards read the active character: without one, the add-a-character card
    TABS: tuple[tuple[str, str], ...] = ()     # its tabs as (value, i18n key), the first open first; () for none

    closed = Signal()                   # the ✕ turned its setting off: the bar's button follows

    def __init__(self, kb: KnowledgeBase, settings: Settings, profiles: Profiles, t: I18n):
        super().__init__(None, _flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)      # a tip or a picture's zoom while the game has the keyboard
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)          # hovering the rim shows the resize cursor
        self.setMinimumSize(self.MIN_W, self.MIN_H)
        self.resize(self.DEFAULT_W, self.DEFAULT_H)
        self.setWindowTitle("Maple Helper")
        self._kb, self._settings, self._profiles, self.t = kb, settings, profiles, t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self.tab = self.TABS[0][0] if self.TABS else ""     # the tab that shows
        self._tabs: Segmented | None = None
        self._typing = False                  # one of its boxes has the keyboard (_take_keys)
        self._keys_from = 0                   # ... and the window that had it before, the game (_give_keys)
        self._opacity = OPACITY_DEFAULT
        self._placed = False                  # geometry applied at least once: there is a place to remember
        self._under: QRect | None = None      # the toolbar's rect, where the window first opens
        self._geom = QTimer(self, singleShot=True, interval=GEOM_DEBOUNCE_MS, timeout=self._remember)
        self.setStyleSheet(self._sheet())
        self._build()
        self._build_body()
        self._retext()

    # ------------------------------------------------------------ the chrome

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
        # the tabs (made in _make_tabs: their words are the language's), then what stays in view over the cards
        self._tabs_slot = QVBoxLayout()
        self._tabs_slot.setContentsMargins(0, 0, 0, 0)
        col.addLayout(self._tabs_slot)
        self._top_box = QWidget()
        self.top = QVBoxLayout(self._top_box)
        self.top.setContentsMargins(0, 0, 0, 0)
        self.top.setSpacing(8)
        col.addWidget(self._top_box)
        self._scroll = QScrollArea(objectName="Body")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rows = _Body(objectName="Rows")
        self._rows = QVBoxLayout(rows)
        self._rows.setSpacing(0)
        # the add-a-character card, or the window's own cards (self.body), one of them shown
        self._no_char = EmptyCard(action=True)
        self._no_char.button.clicked.connect(lambda _=False: NAV.add_character_requested.emit())
        self._rows.addWidget(self._no_char)
        self._page = QWidget()
        self.body = QVBoxLayout(self._page)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        self._rows.addWidget(self._page)
        self._rows.addStretch(1)
        self._scroll.setWidget(rows)
        col.addWidget(self._scroll, 1)

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._opacity)

    # ------------------------------------------------------------ what a window builds on

    def _build_body(self) -> None:
        """The window's own widgets, made once: into self.top (stays in view) and self.body (scrolls). Runs inside
        ToolWindow.__init__, so it makes the state they need too."""

    def _rebuild(self) -> None:
        """The window's cards from the KB, the character (self.character) and the tab that shows (self.tab), in its
        language (self.t): every time the window opens, and while it shows when any of them changes."""

    def extra_qss(self) -> str:
        """The window's own style names, added after tool_qss (read the colours from palette() and accent_of here:
        it is built again on every refresh)."""
        return ""

    def open_with(self, arg: str) -> None:
        """The window on one thing (an item's name for Farm, a quest's key for Quests and Citizenship): each window
        its own. The app has shown the window first (NAV.tool_requested); by default it stays as it is."""

    @property
    def character(self):
        """The active character, or None."""
        return self._profiles.active

    # ------------------------------------------------------------ the contract (app.py wires exactly this)

    def refresh(self) -> None:
        """Shown while settings[SHOW_KEY] is on, in the look the ⚙ panel picks (accent, tint, opacity), out of screen
        captures; its cards read again each time it opens. Hidden when the setting is off."""
        if not self._settings[self.SHOW_KEY]:
            if self.isVisible():
                self.hide()
            return
        self._restyle()
        self._read_opacity()
        if not self.isVisible():
            self._fill()
            self._place()
            self.show()
            set_capturable(self, self._settings)
        self.raise_()
        self.update()                     # the glass repaints in the tint the settings now give

    def place_under(self, rect: QRect) -> None:
        """Where the window opens the first time (no place kept yet): just under the toolbar's rect."""
        self._under = QRect(rect) if isinstance(rect, QRect) else None

    def apply_language(self, t: I18n) -> None:
        """Every word again in the new language, right to left in Hebrew: the title, the tabs, the cards."""
        self.t = t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self._retext()
        self._refill()

    def set_kb(self, kb: KnowledgeBase) -> None:
        """A KB update swapped the KB: the cards read again from the new one."""
        self._kb = kb
        self._refill()

    def character_changed(self) -> None:
        """Another character (or one added, edited or deleted): the cards read again for it."""
        self._refill()

    # ------------------------------------------------------------ the body

    def _fill(self) -> None:
        """The add-a-character card while the window needs a character and there is none (the tabs and the row
        over the cards hidden with it), else the window's own cards (_rebuild), the scroll kept where it was."""
        need = self.NEEDS_CHARACTER and self._profiles.active is None
        self._no_char.setVisible(need)
        self._page.setVisible(not need)
        self._top_box.setVisible(not need and self.top.count() > 0)
        if self._tabs is not None:
            self._tabs.setVisible(not need)
        if need:
            return
        bar = self._scroll.verticalScrollBar()
        at = bar.value()
        self._rebuild()
        QTimer.singleShot(0, self, lambda: bar.setValue(at))

    def _refill(self) -> None:
        """Something the cards are read from changed: read again now when the window shows, else when it opens."""
        if self.isVisible():
            self._fill()

    def _set_tab(self, tab: str) -> None:
        """The window on this tab (the tab row lit on it), its cards read again from the top."""
        if tab not in {value for value, _ in self.TABS}:
            raise ValueError(f"no {type(self).__name__} tab {tab!r}")
        self.tab = tab
        if self._tabs is not None:
            self._tabs.set_value(tab)
        self._fill()
        self._to_top()

    def _tab_picked(self, tab) -> None:
        if tab != self.tab:
            self._set_tab(tab)

    def _to_top(self) -> None:
        bar = self._scroll.verticalScrollBar()
        QTimer.singleShot(0, self, lambda: bar.setValue(0))     # after the _fill's own keep-the-place

    # ------------------------------------------------------------ words (all of the chrome's, for apply_language)

    def _retext(self) -> None:
        t, rtl = self.t, self.t.rtl
        self._title.setText(bidi.plain(t(self.TITLE_KEY), rtl))
        self._close.setToolTip(t(CLOSE_KEY))
        self._close.setAccessibleName(t(CLOSE_KEY))
        self._make_tabs()
        self._no_char.say("users", t("tool_no_char_title"), t("tool_no_char_line"), rtl, t("add_character"))
        # the cards keep a little room on the scrollbar's side (right, or left in Hebrew, where Qt moves it)
        self._rows.setContentsMargins(GUTTER if rtl else 0, 0, 0 if rtl else GUTTER, 0)

    def _make_tabs(self) -> None:
        """The tab row, made again whenever its words change (another language)."""
        if not self.TABS:
            return
        t, rtl = self.t, self.t.rtl
        if self._tabs is not None:
            self._tabs_slot.removeWidget(self._tabs)
            self._tabs.hide()
            self._tabs.deleteLater()
        self._tabs = Segmented([(t(key), value) for value, key in self.TABS], self.tab, rtl)
        self._tabs.setObjectName("Tabs")
        self._tabs.set_label(t(self.TITLE_KEY))
        for b in self._tabs.group.buttons():
            b.setFocusPolicy(Qt.NoFocus)
        self._tabs.changed.connect(self._tab_picked)
        self._tabs_slot.addWidget(self._tabs)

    # ------------------------------------------------------------ the builders: every window's pieces alike

    def label(self, text: str, name: str = "Text", wrap: bool = False) -> QLabel:
        """A line in one of the style's names (Text, Muted, Hint, Note, CardTitle, CardSub...), in the reading order
        of the window's language (bidi.plain)."""
        return _label(bidi.plain(text, self.t.rtl), name, wrap)

    def caption(self, text: str) -> QLabel:
        """A section's small heading over its cards ("BEST FOR YOU"): capitals in English, Hebrew has none."""
        return _label(bidi.plain(text if self.t.rtl else text.upper(), self.t.rtl), "Caption")

    def card(self, lit: bool = False) -> tuple[QFrame, QVBoxLayout]:
        """A card on the glass and the column inside it; lit: in the accent (the best pick)."""
        card = QFrame(objectName="Card")
        if lit:
            card.setProperty("lit", True)
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 9, 12, 10)
        v.setSpacing(6)
        return card, v

    def chips(self, chips: list[tuple[str, str]]) -> QWidget:
        """A row of chips, each (text, its name: Chip, ChipOn or the window's own), that wraps onto more lines rather
        than widen the window; it runs from the right in Hebrew."""
        box = QWidget()
        flow = FlowLayout(box, spacing=4, line_spacing=4)
        for text, name in chips:
            flow.addWidget(_label(bidi.plain(text, self.t.rtl), name))
        return box

    def button(self, text: str, then, name: str = "Primary", tip: str = "") -> QPushButton:
        """A button in one of the style's names (Primary, Small, Link): a click runs then(); it never takes the
        keyboard."""
        b = QPushButton(bidi.plain(text, self.t.rtl).replace("&", "&&"), objectName=name)     # a lone "&": a shortcut
        b.setCursor(Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.NoFocus)
        if tip:
            b.setToolTip(tip)
        b.clicked.connect(lambda _=False: then())
        return b

    def stat(self, value: str, name: str) -> QWidget:
        """A big figure with its small name under it (BigStat over BigStatLabel), for a row of them in a card."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(_label(bidi.ltr_name(value, self.t.rtl), "BigStat"))     # one block, on the right in Hebrew
        v.addWidget(_label(bidi.plain(name, self.t.rtl), "BigStatLabel", wrap=True))
        return box

    def empty(self, icon: str, title: str, hint: str = "") -> EmptyCard:
        """A card saying there is nothing to show yet: a line icon's name (assets/icons/toolbar), what is missing in
        bold, what to do under it."""
        card = EmptyCard()
        card.say(icon, title, hint, self.t.rtl)
        return card

    def key_box(self, placeholder: str = "", search: bool = True) -> KeyBox:
        """A typing box (a search, with its magnifier unless search is off) that takes the keyboard from the game while
        it is typed in: Esc gives it back, and so does _give_keys() once the window is done (an Enter that picked)."""
        box = KeyBox(search)
        box.setPlaceholderText(bidi.plain(placeholder, self.t.rtl))
        box.setAccessibleName(placeholder)
        box.wants_keys.connect(lambda: self._take_keys(box))
        box.done.connect(self._give_keys)
        box.paint_icon(palette().muted)
        return box

    # ------------------------------------------------------------ the keyboard, only while a box is typed in

    def _take_keys(self, box: QLineEdit) -> None:
        """A box clicked: the one time this window takes the keyboard, while the player types in it. It goes back
        to the window that had it (the game) on Esc or _give_keys; a click on another window takes it there."""
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
        focused = self.focusWidget()
        if focused is not None:
            focused.clearFocus()
        _accept_keys(self, False)
        if back:
            _to_foreground(self._keys_from)
        self._keys_from = 0

    def changeEvent(self, e) -> None:
        if e.type() == QEvent.ActivationChange and self._typing and not self.isActiveWindow():
            self._give_keys(back=False)     # the player clicked another window: the keyboard is there already
        super().changeEvent(e)

    # ------------------------------------------------------------ look, closing

    def _sheet(self) -> str:
        return tool_qss(self._settings) + self.extra_qss()

    def _restyle(self) -> None:
        """The accent and the palette the settings pick, in the window's style sheet (set only when it changed: a
        restyle re-polishes every card), its line icons drawn again in the glass's colours."""
        sheet = self._sheet()
        if sheet != self.styleSheet():
            self.setStyleSheet(sheet)
            pal = palette()
            for card in self.findChildren(EmptyCard):
                card.paint_icon(pal.text)
            for box in self.findChildren(KeyBox):
                box.paint_icon(pal.muted)

    def _read_opacity(self) -> None:
        """The NPCs window's own slider sets it: the same glass, as see-through as the player asked."""
        try:
            self._opacity = min(OPACITY_MAX, max(OPACITY_MIN, float(self._settings["npc_overlay_opacity"])))
        except (TypeError, ValueError):
            self._opacity = OPACITY_DEFAULT

    def _close_clicked(self, _=False) -> None:
        """The ✕: the setting off (the bar's button follows), hidden until switched back on."""
        self._settings[self.SHOW_KEY] = False
        self.hide()
        self.closed.emit()

    def hideEvent(self, e) -> None:
        self._give_keys()
        if self._placed:            # hidden (the ✕, the bar, the app closing): keep the place now, not 400 ms later
            self._geom.stop()
            self._remember()
        super().hideEvent(e)

    # ------------------------------------------------------------ place, move, resize

    def _place(self) -> None:
        """Where the window opens: where the player left it, when that is still on a screen (a monitor since
        unplugged: under the toolbar again)."""
        screens = [s.geometry() for s in QGuiApplication.screens()]
        saved = self._settings[self.GEOM_KEY]
        size = QSize(self.width(), self.height())
        if isinstance(saved, dict) and isinstance(saved.get("w"), int) and isinstance(saved.get("h"), int):
            size = mapview.clamp_size(saved["w"], saved["h"], screens, self.minimumSize())
        spot = mapview.saved_spot(saved, size, screens)
        self.setGeometry(QRect(spot if spot is not None else self._default_spot(size), size))
        self._placed = True

    def _default_spot(self, size: QSize) -> QPoint:
        """Just under the toolbar (its Tools card opens this), kept on that screen; without one — the bar never
        placed, or gone — the primary screen's top-left corner."""
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
            self._settings[self.GEOM_KEY] = {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()}
