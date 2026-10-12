"""The crafting advisor over the game (the toolbar's Crafting button opens it), in two windows like the site it is
modelled on (maplestorycrafting.com/planner.html): inputs on one side, the Forge plan on the other.

"Crafting" (CraftAdvisor) takes the inputs on three tabs: what to craft — a table of the gear the class can hold
with its level, the class's attack stat, the recipe, the craft cost from raw mats and what crafting saves against
the NPC's price, a Make count each, the search finding every other recipe; the bag — what the plan uses plus what
is carried, a count each; the professions — the character's level, then a switch of the six professions (a tile
each, the character's level in it) and the picked one's card: its level and Mastery bar %, the EXP to its next
level and the character level that asks for, what that level opens, the crafting EXP table with the player's own
measured values; under it the profession's recipes (what the level allows, every one, one level; searched by a
recipe's or an ingredient's name; each ingredient's item page a click away, where it comes from on its row) or
its teacher, where to craft, and its first and master quests. A one-line summary under the title says where the
plan stands on every tab.

"Forge plan" (ForgePlanWindow) is a window of its own docked beside it: the plan craftplan.py makes of the inputs —
its totals, what to farm first and where it drops, then the crafts in order (materials, the profession level-ups
the plan needs, the final items), every number from the KB's tables or the player's own input. Ticking a step as
crafted moves its mats and products into the bag. It opens by itself once the plan has something to make, follows
the main window, hides with it, and its ✕ hides only the plan ("Show plan" brings it back).

Built like the bar's other windows: the NPCs window's glass at the opacity and in the colours the ⚙ panel
picks, a title row that drags each, the main window's place kept in craft_advisor_geom and the plan's size in
craft_plan_size. The main window takes the keyboard while its boxes are used (Esc or the ✕ gives it back), shows
while settings["craft_advisor"] is on, and its ✕ turns that off."""

from __future__ import annotations

import logging
import re
from html import escape

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import bidi, crafting, craftplan, itemterms, quests, tables
from ..craftplan import CATEGORY_ORDER, DEFAULT_MODE, DISCIPLINE_KEY, FarmItem, Plan, Row, Stage, Step
from ..i18n import NBSP, I18n
from ..kb import KnowledgeBase
from ..store import Character, Profiles, Settings
from . import mapview, theme
from .controls import BalancedRow, FlowLayout, Segmented
from .gamesearch import SCROLLBAR_W, _SearchBox, glass_qss, rim
from .glass import EdgeResize
from .lookpick import line_icon
from .npcoverlay import (
    BOTTOM,
    GEOM_DEBOUNCE_MS,
    OPACITY_DEFAULT,
    OPACITY_MAX,
    OPACITY_MIN,
    SIDE,
    TOP,
    _flags,
    _Header,
    _paint_glass,
    accent_of,
    dock_beside,
    ink,
    palette,
    set_capturable,
)
from .npcoverlay import keep_over_game
from .toolwindow import NAV
from .widgets import fit_picture, zoom_on_hover

log = logging.getLogger("maplehelper")

MIN_W, MIN_H = 440, 420  # the smallest the player can drag the main window to (the table's columns still fit)
DEFAULT_W, DEFAULT_H = 460, 640  # what opens under the toolbar before it is ever resized
PLAN_W, PLAN_H = 420, 700  # the plan window until the player resizes it (shorter when the plan is)
PLAN_MIN_W, PLAN_MIN_H = 340, 200
GAP = 8  # between the toolbar and the window that opens under it
SHOW_KEY, GEOM_KEY, PLAN_SIZE_KEY = "craft_advisor", "craft_advisor_geom", "craft_plan_size"
TYPE_DEBOUNCE_MS = 150  # a pause in a search before its rows are read again
EDIT_DEBOUNCE_MS = 350  # a pause in a number box before the character is saved and re-planned
ITEM_ROWS = 30  # item rows listed before the "and N more" line
BAG_FOUND = 12  # items a bag search offers to add
MAX_MAKE = 50  # the Make steppers' ceiling
PIC = 28  # the item pictures: the table, the bag, the farm list
STEP_PIC = 24  # a craft step's product picture
ROW_PAD = 8  # a table row's own padding, left and right
COL_GAP = 6  # between the table's columns
GUTTER = 4  # between the rows and the scrollbar
ITEM_MIN = 110  # the item column's width the Recipe column must leave before it gets a column of its own
TABS = ("items", "bag", "prof")
# the table's fixed-width columns after the item's own, start to end (the header and every row share their widths)
COLS = ("lv", "stat", "recipe", "cost", "shop", "make")
NUMERIC = {"lv", "stat", "cost", "shop"}  # right-aligned (mirrored in Hebrew), like the site's number columns
CAT_KEYS = {
    "ore": "cp_cat_ore",
    "gem": "cp_cat_gem",
    "material": "cp_cat_material",
    "drop": "cp_cat_drop",
    "other": "cp_cat_other",
}
KIND_KEYS = {
    "ore": "cp_kind_ore",
    "gem": "cp_kind_gem",
    "material": "cp_kind_material",
    "drop": "cp_kind_drop",
    "other": "cp_kind_other",
}
MODE_KEYS = (("least", "cp_mode_least"), ("cheapest", "cp_mode_cheapest"), ("highest", "cp_mode_highest"))
BADGE_KEYS = {"prep": "cp_badge_prep", "level": "cp_badge_level", "final": "cp_badge_final"}
LOSS = "#FF8A80"  # crafting dearer than the shop: a warm red that reads on every glass tint (ink: darker on white)
# the stage kinds' badges, readable on every glass whatever accent is picked (the accent lights what is chosen)
BADGE_COLORS = {"prep": "#64B5FF", "level": "#FFB066", "final": "#4CD07D"}
# the Professions tab: each profession's line icon (assets/icons/toolbar, Lucide's), and what the tab shows of it
PROF_ICONS = {
    "smithing": "hammer",
    "weaponcrafting": "sword",
    "tailoring": "shirt",
    "woodcrafting": "bow-arrow",
    "leatherworking": "footprints",
    "arcforge": "wand-sparkles",
}
# the switch under the profession's card, in the owner's order (the old crafting page's): its teacher and quests, then
# its recipes; it opens on the recipes
PROF_MODES = (("teacher", "craft_mode_teacher"), ("recipes", "craft_mode_recipes"))
TILE_ICON = 16  # a profession tile's line icon
TITLE_ICON = 18  # ... the picked profession's, on its card
GLYPH = 12  # the small line icon before where an ingredient comes from (a monster, a coin, a profession)
RECIPE_PIC = 36  # a recipe card's product
ING_PIC = 22  # an ingredient's picture, a quest need's
NEXT_PIC = 26  # what the next level opens, pictured on the profession's card
NPC_PIC = (48, 56)  # the teacher (NPCs stand taller than wide)
NEXT_PICS = 8  # the next level's products pictured before "+N"
RECIPES_SHOWN = 30  # recipe cards listed before "and N more"
BAR_H = 6  # the Mastery bar
EXP_COLOR = "#64B5FF"  # EXP chips: the Loot Log's EXP blue (ink: darker on the white glass)
WARN = BADGE_COLORS["level"]  # a level the character can't reach yet: the level-up badge's orange
LV_GAP = NBSP + "\u2006"  # Hebrew "רמה 1": with a plain space the 1's ink touched the word ("רמה1", TL2-16)


def _rgba(color: str, alpha: float) -> str:
    """A colour ("#RRGGBB" or "rgba(...)") at this opacity, for a tinted fill."""
    c = theme.qcolor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def qss(settings) -> str:
    """Both windows' own style at the accent the settings pick on the glass's palette (npcoverlay.palette: light
    text on the dark tints, dark on the white one): the lit tab and mode, the picked table rows, the savings, the
    ticked boxes (npcoverlay.ACCENTS; the glass itself is painted in the tint by _paint_glass). Rebuilt whenever
    the look is picked, so the windows follow with no more code of their own."""
    fill, on_fill = accent_of(settings)
    pal = palette()
    text, muted, fill1, fill2 = pal.text, pal.muted, pal.fill1, pal.fill2
    lit, loss = ink(fill), ink(LOSS)  # the accent and the red as text: darkened on the white glass
    badges = "\n".join(
        f"#Kind{kind.title()} {{ color: {ink(c)}; background: {_rgba(c, 0.16)}; border-radius: 6px; padding: 1px 7px;"
        f" font-size: 11px; font-weight: 700; }}"
        for kind, c in BADGE_COLORS.items()
    )
    chip = "border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700;"
    return (
        glass_qss()
        + f"""
QLabel {{ background: transparent; }}
#Sub {{ color: {muted}; font-size: 12px; }}
#Note {{ color: {muted}; font-size: 11px; }}
#Summary {{ color: {text}; font-size: 12px; }}
#Section {{ color: {text}; font-size: 15px; font-weight: 700; padding-top: 6px; }}
QPushButton#PlanBtn {{ background: {fill1}; color: {text}; border: none; border-radius: 8px; padding: 5px 12px;
                       font-size: 12px; font-weight: 600; text-align: center; }}
QPushButton#PlanBtn:hover {{ background: {fill2}; }}
#Segmented {{ background: {fill1}; border: none; border-radius: 10px; }}
QPushButton#Segment {{ background: transparent; color: {muted}; border: none; border-radius: 8px; min-height: 28px;
                       max-height: 28px; padding: 0 10px; font-size: 13px; font-weight: 600; text-align: center; }}
QPushButton#Segment:hover:!checked {{ background: {fill2}; color: {text}; }}
QPushButton#Segment:checked {{ background: {fill}; color: {on_fill}; font-weight: 700; }}
#ColHead {{ color: {muted}; font-size: 11px; font-weight: 600; }}
QFrame#ItemRow, QFrame#BagRow {{ background: transparent; border: none; border-radius: 8px; }}
QFrame#ItemRow:hover, QFrame#BagRow:hover {{ background: {fill1}; }}
QFrame#ItemRow[picked="true"] {{ background: {_rgba(fill, 0.16)}; }}
#ItemName {{ color: {text}; font-size: 13px; font-weight: 600; }}
#ItemType {{ color: {muted}; font-size: 11px; }}
#Cell {{ color: {text}; font-size: 13px; }}
#CellMuted {{ color: {muted}; font-size: 13px; }}
#Recipe {{ color: {text}; font-size: 12px; }}
#Saves {{ color: {lit}; font-size: 13px; font-weight: 700; }}
#SavesWord {{ color: {lit}; font-size: 11px; }}
#Loses {{ color: {loss}; font-size: 13px; font-weight: 700; }}
#LosesWord {{ color: {loss}; font-size: 11px; }}
#NotSold {{ color: {muted}; font-size: 11px; }}
#GroupName {{ color: {text}; font-size: 13px; font-weight: 700; padding-top: 6px; }}
#GroupMeta {{ color: {muted}; font-size: 11px; padding-top: 6px; }}
#InPlan {{ color: {lit}; border: 1px solid {lit}; border-radius: 6px; padding: 0 6px; font-size: 11px; font-weight: 600; }}
QLineEdit#Num {{ padding: 4px 6px; }}
QFrame#ProfCard {{ background: {fill1}; border: none; border-radius: 10px; }}
#ProfName {{ color: {text}; font-size: 13px; font-weight: 700; }}
#FieldName {{ color: {text}; font-size: 13px; font-weight: 600; }}
#FieldLabel {{ color: {muted}; font-size: 11px; font-weight: 600; }}
QFrame#FoldHead {{ background: {fill1}; border: none; border-radius: 8px; }}
QFrame#FoldHead:hover {{ background: {fill2}; }}
#FoldTitle {{ color: {text}; font-size: 13px; font-weight: 700; }}
#FoldMark {{ color: {muted}; font-size: 13px; font-weight: 700; }}
#Mine {{ color: {lit}; font-size: 11px; font-weight: 600; }}
#Stepper {{ background: {fill1}; border: none; border-radius: 8px; }}
QToolButton#StepBtn {{ background: transparent; color: {text}; border: none; border-radius: 6px; padding: 0;
                       min-width: 18px; max-width: 18px; min-height: 22px; max-height: 22px; font-size: 14px;
                       font-weight: 600; }}
QToolButton#StepBtn:hover {{ background: {fill2}; }}
QToolButton#StepBtn:disabled {{ color: {_rgba(muted, 0.28)}; }}
#StepNum {{ color: {text}; font-size: 13px; font-weight: 700; min-width: 16px; }}
#HeadBadge {{ color: {muted}; font-size: 12px; }}
QFrame#StatCard {{ background: {fill1}; border: none; border-radius: 10px; }}
#BigNum {{ color: {text}; font-size: 20px; font-weight: 700; }}
#CardLabel {{ color: {muted}; font-size: 11px; }}
QFrame#FarmRow {{ background: {fill1}; border: none; border-radius: 10px; }}
#Kind {{ color: {muted}; font-size: 11px; }}
#FarmCount {{ color: {text}; font-size: 18px; font-weight: 700; }}
#Muted {{ color: {muted}; font-size: 12px; }}
QFrame#Stage {{ background: {fill1}; border: none; border-radius: 12px; }}
#StageNo {{ color: {muted}; font-size: 11px; font-weight: 700; }}
#StageMeta {{ color: {muted}; font-size: 12px; }}
#StageTitle {{ color: {text}; font-size: 14px; font-weight: 700; }}
{badges}
QFrame#Step {{ background: transparent; border: none; border-top: 1px solid {rim(0.07)}; }}
#StepNo {{ color: {muted}; font-size: 12px; font-weight: 600; }}
#StepName {{ color: {text}; font-size: 13px; font-weight: 600; }}
#Fee {{ color: {text}; font-size: 12px; font-weight: 600; }}
QPushButton#Swap {{ background: {fill1}; color: {muted}; border: none; border-radius: 6px; padding: 2px 8px;
                   font-size: 11px; text-align: center; }}
QPushButton#Swap:hover {{ background: {fill2}; color: {text}; }}
QCheckBox {{ background: transparent; color: {text}; spacing: 0; }}
QCheckBox::indicator {{ background: {fill1}; border: 1px solid {rim(0.25)}; border-radius: 5px;
                        width: 14px; height: 14px; }}
QCheckBox::indicator:checked {{ background: {fill}; border-color: {fill}; }}
QPushButton#ProfTile {{ background: {fill1}; border: 1px solid transparent; border-radius: 10px; padding: 0;
                        min-height: 0; text-align: left; }}
QPushButton#ProfTile:hover:!checked {{ background: {fill2}; }}
QPushButton#ProfTile:checked {{ background: {_rgba(fill, 0.16)}; border: 1px solid {fill}; }}
#TileName {{ color: {text}; font-size: 12px; font-weight: 600; }}
#TileName[lit="true"] {{ color: {lit}; }}
#TileLv {{ color: {muted}; font-size: 11px; }}
QFrame#Card {{ background: {fill1}; border: 1px solid transparent; border-radius: 12px; }}
QFrame#Card[lit="true"] {{ background: {_rgba(fill, 0.10)}; border: 1px solid {fill}; }}
#ProfTitle {{ color: {text}; font-size: 15px; font-weight: 700; }}
#CardTitle {{ color: {text}; font-size: 13px; font-weight: 700; }}
#CardSub {{ color: {muted}; font-size: 12px; }}
#Caption {{ color: {muted}; font-size: 10px; font-weight: 700; padding: 4px 2px 0 2px; }}
#Text {{ color: {text}; font-size: 12px; }}
#Warn {{ color: {ink(WARN)}; font-size: 11px; font-weight: 600; }}
#CellOn {{ color: {lit}; font-size: 13px; font-weight: 700; }}
QLabel#Chip {{ color: {text}; background: {rim(0.10)}; {chip} }}
QLabel#ChipOn {{ color: {lit}; background: {_rgba(fill, 0.16)}; {chip} }}
QLabel#ChipExp {{ color: {ink(EXP_COLOR)}; background: {_rgba(EXP_COLOR, 0.16)}; {chip} }}
QLabel#ChipWarn {{ color: {ink(WARN)}; background: {_rgba(WARN, 0.16)}; {chip} }}
QPushButton#Scope {{ background: {fill1}; color: {muted}; border: 1px solid transparent; border-radius: 11px;
                     min-height: 22px; max-height: 22px; padding: 0 10px; font-size: 12px; font-weight: 600;
                     text-align: center; }}
QPushButton#Scope:hover:!checked {{ background: {fill2}; color: {text}; }}
QPushButton#Scope:checked {{ background: {_rgba(fill, 0.16)}; border: 1px solid {fill}; color: {lit}; }}
QPushButton#LvChip {{ background: {fill1}; color: {text}; border: 1px solid transparent; border-radius: 11px;
                      min-width: 20px; min-height: 22px; max-height: 22px; padding: 0 2px; font-size: 11px;
                      font-weight: 700; text-align: center; }}
QPushButton#LvChip[locked="true"] {{ color: {muted}; font-weight: 600; }}
QPushButton#LvChip:hover:!checked {{ background: {fill2}; color: {text}; }}
QPushButton#LvChip:checked {{ background: {_rgba(fill, 0.16)}; border: 1px solid {fill}; color: {lit}; }}
QPushButton#Link {{ background: transparent; color: {lit}; border: none; border-radius: 0; padding: 1px 0;
                    font-size: 12px; font-weight: 700; text-align: left; }}
QPushButton#Link:hover {{ background: transparent; text-decoration: underline; }}
QFrame#IngRow {{ background: transparent; border: none; border-radius: 8px; }}
QFrame#IngRow[link="true"]:hover {{ background: {fill2}; }}
#IngName {{ color: {text}; font-size: 12px; }}
#IngWhere {{ color: {muted}; font-size: 11px; }}
#Chevron {{ color: {muted}; font-size: 14px; }}
#NeedHead {{ color: {muted}; font-size: 11px; font-weight: 700; padding-top: 2px; }}
QFrame#FoldHead[flat="true"] {{ background: transparent; border: none; border-top: 1px solid {rim(0.08)};
                                border-radius: 0; }}
QFrame#FoldHead[flat="true"]:hover {{ background: transparent; }}
"""
    )


def _match(name: str, query: str) -> bool:
    """A row for this query: every word of it in the item's name, case aside (the searches' own rule)."""
    words = [w for w in query.lower().split() if w]
    n = str(name).lower()
    return not words or all(w in n for w in words)


def _mesos(v: int) -> str:
    return f"{int(v):,}"


def _type_word(kb, key: str, lang: str) -> str:
    """The item's type word ("Wand", "Crafting Material") from its KB type ("Equip / Wand"), in the UI's language."""
    typ = str((kb.get(key) or {}).get("type") or "") if key else ""
    last = re.split(r"\s*[/·]\s*", typ)[-1].strip() if typ else ""
    return itemterms.kind(last, lang) if last else ""


def _clear(lay) -> None:
    """Every widget out of a layout (the layouts this file clears hold widgets and stretches only)."""
    while lay.count():
        w = lay.takeAt(0).widget()
        if w is not None:
            w.hide()  # gone now: deleteLater alone left the old rows drawn under the new ones
            w.deleteLater()


def _scroller() -> tuple[QScrollArea, QVBoxLayout]:
    """A body that scrolls, in the overlay's own look: its rows' layout for the caller to fill."""
    scroll = QScrollArea(objectName="Body")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    rows = QWidget(objectName="Rows")
    lay = QVBoxLayout(rows)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    scroll.setWidget(rows)
    return scroll, lay


def _label(text: str, name: str, wrap: bool = False, align=None) -> QLabel:
    w = QLabel(text, objectName=name)
    w.setWordWrap(wrap)
    if align is not None:
        w.setAlignment(align)
    return w


def _button_words(words: str, rtl: bool) -> str:
    """A button's words (bidi.button: one right-to-left isolate in Hebrew), a lone "&" kept, not a shortcut's mark."""
    return bidi.button(words, rtl).replace("&", "&&")


def _rename(w: QWidget, name: str) -> None:
    """Another of the style's names for a widget, its look re-polished (only when it changed: a polish is not free)."""
    if w.objectName() != name:
        w.setObjectName(name)
        w.style().unpolish(w)
        w.style().polish(w)


def _min_width(w: QWidget) -> int:
    """The width a cell needs: a wrapping label (a column's header) its longest word, anything else its own hint."""
    if isinstance(w, QLabel) and w.wordWrap():
        fm = w.fontMetrics()
        return max((fm.horizontalAdvance(word) for word in w.text().split()), default=0) + 2
    return w.sizeHint().width()


def _pieces(items, rtl: bool, sep: str = ", ") -> str:
    """English pieces for one line ("6 Mithril Ingot, 4 Aquamarine"): a line wraps between them, never inside one
    ("2" at one line's end, "Iron Ingot" on the next); a long one keeps at least its count with its first word. In
    Hebrew each is a left-to-right block of its own, so the list reads right to left — one block across a Hebrew
    line's wrap had its start cut off and its brackets mirrored."""
    out = []
    for p in items:
        p = str(p)
        p = p.replace(" ", NBSP) if len(p) <= bidi.KEEP_TOGETHER else p.replace(" ", NBSP, 1)
        # its trailing count stays with the name: "Bronze Ore" / "×10" across a Hebrew wrap read "10×"
        head, sp, tail = p.rpartition(" ")
        p = head + NBSP + tail if sp and len(tail) <= 6 else p
        out.append(bidi.ltr_block(p, rtl))
    return sep.join(out)


class _Pictures:
    """Each item's sprite, fitted once per size: the table, the bag and the plan are drawn again on every edit, and
    each row would read its sprite from disk and scale it again."""

    def __init__(self, kb):
        self._kb = kb
        self._paths: dict[str, object] = {}
        self._fitted: dict[tuple[str, int, int, float], QPixmap] = {}

    def label(self, key: str, size: int, h: int | None = None, caption: str = "") -> QLabel:
        """The picture in a fixed box, size wide and h tall (a square by default; an item with no KB key: the box
        empty, the columns still line up), shown large on hover with its caption under it."""
        h = size if h is None else h
        pic = QLabel(objectName="Pic")
        pic.setFixedSize(size, h)
        pic.setAlignment(Qt.AlignCenter)
        if not key:
            return pic
        if key not in self._paths:
            self._paths[key] = self._kb.picture(key)
        path = self._paths[key]
        if not path:
            return pic
        dpr = pic.devicePixelRatioF()
        pm = self._fitted.get((key, size, h, dpr))
        if pm is None:
            raw = QPixmap(str(path))
            pm = fit_picture(raw, size, h, pic) if not raw.isNull() else QPixmap()
            self._fitted[(key, size, h, dpr)] = pm
        if not pm.isNull():
            pic.setPixmap(pm)
            zoom_on_hover(pic, path, caption)
        return pic


class _Stepper(QFrame):
    """A small − n + counter in the overlay's own look: a spin box's arrows don't survive the dark glass, and the
    counts are usually small clicks. Its − and + grey out at its floor and ceiling."""

    changed = Signal(int)

    def __init__(self, value: int = 0, hi: int = MAX_MAKE, lo: int = 0):
        super().__init__(objectName="Stepper")
        self._lo, self._hi = lo, hi
        self._v = lo
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)
        self._minus = QToolButton(objectName="StepBtn", text="\u2212")
        self._num = QLabel(objectName="StepNum", alignment=Qt.AlignCenter)
        self._plus = QToolButton(objectName="StepBtn", text="+")
        for b, d in ((self._minus, -1), (self._plus, 1)):
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, d=d: self.setValue(self._v + d))
        row.addWidget(self._minus)
        row.addWidget(self._num)
        row.addWidget(self._plus)
        self.setValue(value)

    def value(self) -> int:
        return self._v

    def set_top(self, hi: int) -> None:
        """Another ceiling (a profession's top level, from the KB): the count kept under it."""
        self._hi = max(self._lo, int(hi))
        self.setValue(self._v)

    def setValue(self, v: int) -> None:
        v = min(self._hi, max(self._lo, int(v)))
        self._v = v
        self._num.setText(str(v))
        self._minus.setEnabled(v > self._lo)
        self._plus.setEnabled(v < self._hi)
        self.changed.emit(v)


class _FoldHead(QFrame):
    """A foldable section's title row: its name and a +/– mark; a click folds or unfolds what is under it."""

    clicked = Signal()

    def __init__(self, flat: bool = False):
        super().__init__(objectName="FoldHead")
        self.setCursor(Qt.PointingHandCursor)
        if flat:
            self.setProperty("flat", True)  # at a card's foot: no fill of its own, a hairline over it
        row = QHBoxLayout(self)
        row.setContentsMargins(*((0, 9, 0, 1) if flat else (10, 7, 10, 7)))
        row.setSpacing(6)
        self.title = QLabel(objectName="FoldTitle")
        self.mark = QLabel(objectName="FoldMark")
        row.addWidget(self.title, 1)
        row.addWidget(self.mark)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class _Glyph(QLabel):
    """A small line icon (assets/icons/toolbar, lookpick.line_icon) in one of the glass's colours, its tone "muted",
    "text" or "lit" (the accent's): drawn again whenever the glass or the accent changes (CraftAdvisor._paint_glyphs),
    in the colours it was last given."""

    def __init__(self, name: str, px: int, tone: str = "muted"):
        super().__init__(objectName="Glyph", alignment=Qt.AlignCenter)
        self.icon_name, self.px, self.tone = name, px, tone
        self._colours: dict[str, str] = {}
        self.setFixedSize(px, px)

    def paint(self, colours: dict[str, str] | None = None) -> None:
        if colours is not None:
            self._colours = colours
        if self._colours:
            icon = line_icon(self.icon_name, self._colours[self.tone])
            self.setPixmap(icon.pixmap(QSize(self.px, self.px), self.devicePixelRatioF()))


class _Bar(QWidget):
    """The Mastery bar: the track in the glass's own fill, the part earned in the accent, filled from the reading end
    (the right, in Hebrew), like the grind window's bars."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(BAR_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.frac, self.colour = 0.0, ""

    def set(self, frac: float, colour: str) -> None:
        frac = min(1.0, max(0.0, float(frac)))
        if (frac, colour) != (self.frac, self.colour):
            self.frac, self.colour = frac, colour
            self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        rad = r.height() / 2
        p.setBrush(theme.qcolor(palette().fill2))  # read at paint: the white glass's track is dark
        p.drawRoundedRect(r, rad, rad)
        if self.frac > 0 and self.colour:
            w = max(r.height(), r.width() * self.frac)
            p.setBrush(theme.qcolor(self.colour))
            p.drawRoundedRect(QRectF(r.right() - w if self.isRightToLeft() else r.left(), r.top(), w, r.height()), rad, rad)
        p.end()


class _ProfTile(QPushButton):
    """One profession in the Professions tab's switch: its line icon over its name and the character's level in it,
    lit in the accent while it is the one shown (a checkable button of the switch's exclusive group). Upright, so three
    fit a row at the window's narrowest in the app's own font (Rubik's "Weaponcrafting" is 104 px)."""

    def __init__(self, prof: str):
        super().__init__(objectName="ProfTile")
        self.prof = prof
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 7, 6, 6)
        v.setSpacing(2)
        self.glyph = _Glyph(PROF_ICONS[prof], TILE_ICON)
        self.name = QLabel(objectName="TileName", alignment=Qt.AlignCenter)
        self.level = QLabel(objectName="TileLv", alignment=Qt.AlignCenter)
        v.addWidget(self.glyph, 0, Qt.AlignHCenter)
        v.addSpacing(1)
        v.addWidget(self.name)
        v.addWidget(self.level)
        for w in (self.glyph, self.name, self.level):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)  # the tile takes the click and the hover
        self.toggled.connect(self._lit)

    def sizeHint(self) -> QSize:
        return self.layout().sizeHint()  # its labels', not a text button's

    def minimumSizeHint(self) -> QSize:
        return self.layout().minimumSize()

    def _lit(self, on: bool) -> None:
        self.name.setProperty("lit", on)
        self.name.style().unpolish(self.name)
        self.name.style().polish(self.name)
        self.glyph.tone = "lit" if on else "muted"
        self.glyph.paint()


class _LinkRow(QFrame):
    """A row a click opens a page from (an ingredient's item page, a quest need's monster or item): lit under the
    mouse, a chevron at its end. Without a page to open it is a plain row."""

    clicked = Signal()

    def __init__(self, link: bool):
        super().__init__(objectName="IngRow")
        self._link = link
        self.setProperty("link", link)
        if link:
            self.setAttribute(Qt.WA_Hover, True)
            self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if self._link and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class CraftAdvisor(EdgeResize, QWidget):
    """The main window, "Crafting": the summary strip under the title, the three tabs (what to craft, the bag, the
    professions), and the Forge plan in a window of its own beside it (plan_window, made the first time it shows).
    It owns the plan: every edit here or there plans again and both windows follow."""

    closed = Signal()  # the ✕ turned the setting off: the toolbar's Crafting button unchecks

    def __init__(self, kb: KnowledgeBase, settings: Settings, profiles: Profiles, t: I18n):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setMouseTracking(True)  # hovering the rim shows the resize cursor
        self.setMinimumSize(MIN_W, MIN_H)
        self.resize(DEFAULT_W, DEFAULT_H)
        self._kb = kb
        self._settings = settings
        self._profiles = profiles
        self.t = t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self._pics = _Pictures(kb)
        self._pool: list[tuple[str, str]] | None = None  # every item the recipes use or make: the bag search's list
        self._c: Character | None = None
        self._rows: tuple[Row, ...] = ()
        self._plan: Plan | None = None
        self._had_plan = False  # the last plan had something to make (the plan window opens when it starts to)
        self._mode = DEFAULT_MODE
        self._choices: dict[str, int] = {}  # product name casefold -> the recipe number the player swapped to
        self._tab = TABS[0]
        self._tabs: Segmented | None = None
        self._cols: dict[str, list[QWidget]] = {}  # the table's cells per fixed column, the header's first
        self._col_w: dict[str, int] = {}
        self._types: list[tuple[QLabel, str, str]] = []  # each row's type line: (label, with the recipe, without)
        self._wide = False  # the Recipe column of its own (a wide window), else under each item's name
        self._recipe_placed = False  # the table filled since the Recipe column was last placed
        self._has_stat = False  # the class has an attack stat column (a Beginner's gear has none to rank by)
        self._item_rows: dict[str, QFrame] = {}  # an item row by its KB key (its Make stepper lights it)
        self._bag_boxes: dict[str, _SearchBox] = {}
        self._exp_boxes: dict[int, _SearchBox] = {}
        self._exp_marks: dict[int, QLabel] = {}
        self._exp_words: dict[int, QLabel] = {}  # each EXP row's "Lv. 3 → Lv. 4" (the picked profession's lit)
        self._exp_folded = True  # the EXP table folded on the profession's card until the player opens it
        self._prof = crafting.PROFESSIONS[0]  # the profession the Professions tab shows
        self._prof_for = ""  # ... picked for this character's id (another character: their own highest)
        self._prof_mode = "recipes"  # its recipes, or its teacher and quests (PROF_MODES)
        self._scope: str | int = "now"  # the recipes: what the level allows ("now"), every one ("all"), or one level
        self._prof_tabs: Segmented | None = None  # the Teacher & quests / Recipes switch (made with its words)
        self._recipes_in = palette()  # the palette the recipe cards were drawn in (a name's muted aside is in its html)
        self._infos: dict[str, crafting.Info] = {}  # each profession's teacher, stations and quests, once per KB
        self._econ: dict[str, dict] = {}  # ... its recipes' NiaMeowDB numbers (crafting.economy), once per KB
        self._quest_keys: dict[str, str] | None = None  # a quest's name (case and a closing "!" aside) -> its key
        self._quest_needs: dict[str, list[dict]] | None = None  # a quest's key -> its quest_reqs rows
        self._npc_maps: dict[str, str] | None = None  # an NPC's key -> the map it stands on
        self._opacity = OPACITY_DEFAULT
        self._placed = False  # geometry applied at least once: there is a place to remember
        self._under: QRect | None = None  # the toolbar's rect, where the window first opens
        self.plan_window: ForgePlanWindow | None = None
        self._geom = QTimer(self, singleShot=True, interval=GEOM_DEBOUNCE_MS, timeout=self._remember)
        self._typing = QTimer(self, singleShot=True, interval=TYPE_DEBOUNCE_MS, timeout=self._fill_items)
        self._bag_typing = QTimer(self, singleShot=True, interval=TYPE_DEBOUNCE_MS, timeout=self._fill_bag)
        self._rec_typing = QTimer(self, singleShot=True, interval=TYPE_DEBOUNCE_MS, timeout=self._fill_recipes)
        self._edit = QTimer(self, singleShot=True, interval=EDIT_DEBOUNCE_MS, timeout=self._edits_saved)
        self.setStyleSheet(qss(self._settings))
        self._build()

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
        self._close.clicked.connect(self._close_clicked)
        hrow.addWidget(self._title, 1)
        hrow.addWidget(self._close, 0, Qt.AlignTop)
        col.addWidget(head)
        strip = QHBoxLayout()
        strip.setSpacing(8)
        self._summary = QLabel(objectName="Summary", wordWrap=True)
        self._plan_btn = QPushButton(objectName="PlanBtn")
        self._plan_btn.setCursor(Qt.PointingHandCursor)
        self._plan_btn.setFocusPolicy(Qt.NoFocus)
        self._plan_btn.clicked.connect(self._plan_btn_clicked)
        strip.addWidget(self._summary, 1)
        strip.addWidget(self._plan_btn, 0, Qt.AlignVCenter)
        col.addLayout(strip)
        self._tabs_slot = QVBoxLayout()
        self._tabs_slot.setContentsMargins(0, 0, 0, 0)
        col.addLayout(self._tabs_slot)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_items())
        self._stack.addWidget(self._build_bag())
        self._stack.addWidget(self._build_prof())
        col.addWidget(self._stack, 1)
        self._clear_of_scrollbar()

    def _build_items(self) -> QWidget:
        """What to craft: the search box, the table's header (it stays put while the rows scroll) and the rows."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self._search = _SearchBox(objectName="Search")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _t: self._typing.start())
        v.addWidget(self._search)
        self._head = QWidget()
        self._head_lay = QHBoxLayout(self._head)
        self._head_lay.setSpacing(COL_GAP)
        v.addWidget(self._head)
        self._items_scroll, self._items_lay = _scroller()
        bar = self._items_scroll.verticalScrollBar()
        bar.rangeChanged.connect(lambda _a, _b: QTimer.singleShot(0, self, self._head_inset))
        v.addWidget(self._items_scroll, 1)
        return page

    def _build_bag(self) -> QWidget:
        """The bag: a hint, the search that adds anything else, the groups (filled by _fill_bag)."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self._bag_hint = _label("", "Note", wrap=True)
        self._bag_search = _SearchBox(objectName="Search")
        self._bag_search.setClearButtonEnabled(True)
        self._bag_search.textChanged.connect(lambda _t: self._bag_typing.start())
        self._bag_scroll, self._bag_lay = _scroller()
        v.addWidget(self._bag_hint)
        v.addWidget(self._bag_search)
        v.addWidget(self._bag_scroll, 1)
        return page

    def _build_prof(self) -> QWidget:
        """The professions, top to bottom: the character level; the switch (a tile a profession, the character's
        level in each); the picked profession's card (its level, the Mastery bar, the EXP to the next level and the
        character level it asks for, what that level opens, the EXP table folded at its foot); then its recipes, or
        its teacher and quests (a switch). Built once; _show_prof fills it from the character."""
        scroll, lay = _scroller()
        self._prof_lay = lay
        lay.setSpacing(8)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        self._char_word = _label("", "FieldName")
        self._lv_box = _SearchBox(objectName="Num", maxLength=3)
        self._lv_box.setFixedWidth(56)
        self._lv_box.setAlignment(Qt.AlignCenter)
        self._lv_box.textChanged.connect(lambda _t: self._edit.start())
        h.addWidget(self._char_word)
        h.addWidget(self._lv_box)
        h.addStretch(1)
        lay.addWidget(row)
        # the six on one row when they fit, else two rows of three (never one alone on a row of its own)
        self._prof_group = QButtonGroup(self)
        self._prof_group.setExclusive(True)
        self._tiles: dict[str, _ProfTile] = {}
        for prof in crafting.PROFESSIONS:
            tile = _ProfTile(prof)
            tile.clicked.connect(lambda _=False, p=prof: self._prof_pick(p))
            self._prof_group.addButton(tile)
            self._tiles[prof] = tile
        lay.addWidget(BalancedRow(list(self._tiles.values()), spacing=6))
        lay.addWidget(self._build_prof_card())
        self._prof_tabs_slot = QVBoxLayout()
        self._prof_tabs_slot.setContentsMargins(0, 2, 0, 0)
        lay.addLayout(self._prof_tabs_slot)
        lay.addWidget(self._build_recipes())
        lay.addWidget(self._build_teacher())
        lay.addStretch(1)
        self._prof_scroll = scroll
        return scroll

    def _build_prof_card(self) -> QFrame:
        """The picked profession's card: its icon and name with the level stepper, what it makes, the Mastery bar
        with its % box, the way to the next level, what that level opens, and the EXP table folded at its foot."""
        card = QFrame(objectName="Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 8)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        self._prof_glyph = _Glyph(PROF_ICONS[self._prof], TITLE_ICON, "lit")
        self._prof_name = _label("", "ProfTitle")
        self._step_word = _label("", "FieldLabel")
        self._step = _Stepper(1, craftplan.LEVEL_CAP, lo=1)  # its top: the KB's (_show_prof)
        self._step.changed.connect(self._prof_level_set)
        top.addWidget(self._prof_glyph, 0, Qt.AlignVCenter)
        top.addWidget(self._prof_name, 1, Qt.AlignVCenter)
        top.addWidget(self._step_word, 0, Qt.AlignVCenter)
        top.addWidget(self._step, 0, Qt.AlignVCenter)
        v.addLayout(top)
        self._prof_makes = _label("", "Muted", wrap=True)
        v.addWidget(self._prof_makes)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 4, 0, 0)
        bar.setSpacing(8)
        self._bar = _Bar()
        self._pct_word = _label("", "FieldLabel")
        self._pct_box = _SearchBox(objectName="Num", maxLength=3)
        self._pct_box.setFixedWidth(46)
        self._pct_box.setAlignment(Qt.AlignCenter)
        self._pct_box.setPlaceholderText("0")
        self._pct_box.textChanged.connect(lambda _t: self._edit.start())
        bar.addWidget(self._bar, 1, Qt.AlignVCenter)
        bar.addWidget(self._pct_word, 0, Qt.AlignVCenter)
        bar.addWidget(self._pct_box, 0, Qt.AlignVCenter)
        v.addLayout(bar)
        self._exp_line = _label("", "Text", wrap=True)
        self._exp_line.setTextFormat(Qt.RichText)  # the EXP figures in bold
        self._req_line = _label("", "Note", wrap=True)
        v.addWidget(self._exp_line)
        v.addWidget(self._req_line)
        # what the next level opens: its words and a link to its recipes, their products' pictures under them
        self._next_box = QWidget()
        nv = QVBoxLayout(self._next_box)
        nv.setContentsMargins(0, 4, 0, 0)
        nv.setSpacing(4)
        nh = QHBoxLayout()
        nh.setSpacing(10)
        self._next_words = _label("", "FieldLabel")
        self._next_link = QPushButton(objectName="Link")
        self._next_link.setCursor(Qt.PointingHandCursor)
        self._next_link.setFocusPolicy(Qt.NoFocus)
        self._next_link.clicked.connect(self._see_next)
        nh.addWidget(self._next_words, 0, Qt.AlignVCenter)
        nh.addWidget(self._next_link, 0, Qt.AlignVCenter)
        nh.addStretch(1)
        nv.addLayout(nh)
        self._next_pics = QHBoxLayout()
        self._next_pics.setSpacing(6)
        nv.addLayout(self._next_pics)
        v.addWidget(self._next_box)
        # the EXP table: one for every profession, the plan's numbers (the player's measured ones replace the KB's)
        self._exp_head = _FoldHead(flat=True)
        self._exp_head.clicked.connect(self._fold_exp)
        v.addWidget(self._exp_head)
        self._exp_body = QWidget()
        self._exp_lay = QVBoxLayout(self._exp_body)
        self._exp_lay.setContentsMargins(0, 0, 0, 4)
        self._exp_lay.setSpacing(2)
        self._exp_body.setVisible(not self._exp_folded)
        v.addWidget(self._exp_body)
        self._prof_card = card
        return card

    def _build_recipes(self) -> QWidget:
        """The Recipes side: the search (a recipe's name or an ingredient's), the scope chips (what the level allows,
        every recipe, one level), the line saying what shows, then the cards level by level (_fill_recipes)."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self._rec_search = _SearchBox(objectName="Search")
        self._rec_search.setClearButtonEnabled(True)
        self._rec_search.textChanged.connect(lambda _t: self._rec_typing.start())
        v.addWidget(self._rec_search)
        # what the level allows / every recipe, then a chip a level (the one level's recipes)
        self._scope_box = QWidget()
        self._scope_flow = FlowLayout(self._scope_box, spacing=4, line_spacing=4)
        v.addWidget(self._scope_box)
        levels = QHBoxLayout()
        levels.setContentsMargins(0, 0, 0, 0)
        levels.setSpacing(8)
        self._levels_word = _label("", "FieldLabel")
        self._levels_word.setContentsMargins(0, 4, 0, 0)  # level with the first row of chips
        self._levels_box = QWidget()
        self._levels_flow = FlowLayout(self._levels_box, spacing=4, line_spacing=4)
        levels.addWidget(self._levels_word, 0, Qt.AlignTop)
        levels.addWidget(self._levels_box, 1)
        v.addLayout(levels)
        self._rec_head = _label("", "Sub", wrap=True)
        self._rec_head.setTextFormat(Qt.RichText)
        v.addWidget(self._rec_head)
        self._rec_lay = QVBoxLayout()
        self._rec_lay.setContentsMargins(0, 0, 0, 0)
        self._rec_lay.setSpacing(8)
        v.addLayout(self._rec_lay)
        self._rec_box = box
        return box

    def _build_teacher(self) -> QWidget:
        """The Teacher side: who teaches the profession and where to craft, then its first and master quests
        (_fill_teacher)."""
        self._teach_box = QWidget()
        self._teach_lay = QVBoxLayout(self._teach_box)
        self._teach_lay.setContentsMargins(0, 0, 0, 0)
        self._teach_lay.setSpacing(8)
        return self._teach_box

    def _clear_of_scrollbar(self) -> None:
        """The bodies keep a little room on their scrollbar's side (right, or left in Hebrew, where Qt moves it), and
        the table's header follows the rows' inset."""
        rtl = self.t.rtl
        for lay in (self._items_lay, self._bag_lay, self._prof_lay):
            lay.setContentsMargins(GUTTER if rtl else 0, 0, 0 if rtl else GUTTER, 0)
        self._head_inset()

    def _head_inset(self) -> None:
        """The header's columns over the rows' own: as far in as the rows sit, the scrollbar's width (the QSS's)
        counted while the scroll area shows it (with no scrollbar the rows reach the scroll area's edge)."""
        shown = self._items_scroll.verticalScrollBar().isVisibleTo(self._items_scroll)
        side = GUTTER + (SCROLLBAR_W if shown else 0)
        rtl = self.t.rtl
        self._head_lay.setContentsMargins(ROW_PAD + (side if rtl else 0), 0, ROW_PAD + (0 if rtl else side), 0)

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._opacity)

    # ------------------------------------------------------------ the contract (app.py wires exactly this)

    def refresh(self) -> None:
        """Shown while settings["craft_advisor"] is on; the character is read again every time it shows. The look
        (accent, tint, opacity) is taken by both windows every time."""
        if bool(self._settings[SHOW_KEY]):
            self._restyle()
            try:
                self._opacity = min(OPACITY_MAX, max(OPACITY_MIN, float(self._settings["npc_overlay_opacity"])))
            except (TypeError, ValueError):
                self._opacity = OPACITY_DEFAULT
            if not self.isVisible():
                self._rebuild()
                self._place()
                self.show()
                set_capturable(self, self._settings)
                self._sync_plan(opening=True)
            self.raise_()
            self.update()  # the glass repaints in the tint the settings pick (npcoverlay.apply_look)
            if self.plan_window is not None and self.plan_window.isVisible():
                self.plan_window.raise_()
                self.plan_window.update()
        elif self.isVisible():
            self.hide()

    def _restyle(self) -> None:
        """The accent the settings pick, in both windows' style sheets (their glass is painted in the tint by
        _paint_glass); skipped when it is the same — a restyle re-polishes every row. The line icons and the Mastery
        bar take the new colours, and the recipe cards are drawn again on another glass (a name's muted aside is in
        its html)."""
        sheet = qss(self._settings)
        if sheet != self.styleSheet():
            self.setStyleSheet(sheet)
            self._paint_glyphs()
            self._bar.set(self._bar.frac, accent_of(self._settings)[0])
            shown = self.isVisible() and self._c is not None and self._prof_mode == "recipes"
            if shown and self._recipes_in != palette():  # (a hidden window draws them again as it opens)
                self._fill_recipes()
        if self.plan_window is not None:
            self.plan_window.restyle(sheet)

    def place_under(self, rect: QRect) -> None:
        """Where the window opens the first time (no place kept yet): just under the toolbar's rect."""
        self._under = QRect(rect) if isinstance(rect, QRect) else None

    def apply_language(self, t: I18n) -> None:
        self.t = t
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        if self.plan_window is not None:
            self.plan_window.apply_language(t)  # its direction and words first: the rebuild draws its plan again
        self._clear_of_scrollbar()
        self._rebuild()

    def set_kb(self, kb: KnowledgeBase) -> None:
        """A new KB: its pictures, recipes and prices; both windows drawn again from it."""
        self._kb = kb
        self._pics = _Pictures(kb)
        self._pool = None
        self._choices = {}
        self._infos, self._econ, self._quest_keys, self._quest_needs, self._npc_maps = {}, {}, None, None, None
        self._rebuild()

    def character_changed(self) -> None:
        self._choices = {}
        self._rebuild()

    def open_with(self, arg: str) -> None:
        """NAV.tool_requested("craft_advisor", <a profession>): the Professions tab on it ("smithing" or "Smithing").
        Anything else leaves the window as it is (the app has shown it already)."""
        prof = str(arg or "").strip().lower()
        if prof not in self._tiles or self._c is None:
            return
        self._tabs.set_value("prof")
        self._tab_set("prof")
        self._prof_pick(prof)

    # ------------------------------------------------------------ everything again (apply_language is just this)

    def _rebuild(self) -> None:
        """Every tab and the plan again, from the active character."""
        self._c = self._profiles.active
        self._retext_chrome()
        c = self._c
        self._tabs.setVisible(c is not None)
        self._stack.setVisible(c is not None)
        if c is None:
            self._rows = ()
            self._fill_items()
            self._fill_exp()
            self._replan()
            return
        self._rows = craftplan.craftable(self._kb, c)
        if c.id != self._prof_for:  # another character: the tab opens on the profession they are highest in
            self._prof_for, self._prof, self._scope = c.id, self._top_prof(c), "now"
        self._fill_exp()
        self._show_prof()
        self._fill_items()
        self._replan()
        QTimer.singleShot(0, self, self._show_picked)

    def _show_picked(self) -> None:
        """The table scrolled to its first picked item, its Make count in view (the class's gear runs ~80 rows): how
        the window opens."""
        c = self._c
        first = next((self._item_rows[k] for k in (c.craft_targets if c else ()) if k in self._item_rows), None)
        if first is not None:
            self._items_scroll.ensureWidgetVisible(first, 0, 60)

    def _retext_chrome(self) -> None:
        """The words that are not rows: the title, the tabs, the boxes' hints, the professions' labels."""
        t, rtl = self.t, self.t.rtl
        self._title.setText(bidi.plain(t("cp_title"), rtl))
        self._close.setAccessibleName(t("cp_close"))
        self._close.setToolTip(t("cp_close"))
        self._plan_btn.setToolTip(t("cp_plan_btn_tip"))
        self._retext_plan_btn()
        if self._tabs is not None:
            self._tabs_slot.removeWidget(self._tabs)
            self._tabs.hide()
            self._tabs.deleteLater()
        words = {"items": "cp_items", "bag": "cp_bag", "prof": "cp_tab_prof"}
        self._tabs = Segmented([(t(words[k]), k) for k in TABS], self._tab, rtl)
        self._tabs.set_label(t("cp_tabs_a11y"))
        for b in self._tabs.group.buttons():
            b.setFocusPolicy(Qt.NoFocus)
        self._tabs.changed.connect(self._tab_set)
        self._tabs_slot.addWidget(self._tabs)
        self._stack.setCurrentIndex(TABS.index(self._tab))
        self._search.setPlaceholderText(bidi.plain(t("cp_search_ph"), rtl))
        self._bag_search.setPlaceholderText(bidi.plain(t("cp_bag_search_ph"), rtl))
        self._bag_hint.setText(bidi.plain(t("cp_bag_hint"), rtl))
        self._char_word.setText(bidi.plain(t("cp_char"), rtl))
        self._lv_box.setAccessibleName(t("cp_char"))
        self._lv_box.setToolTip(t("cp_char_tip"))
        for prof, tile in self._tiles.items():
            name = crafting.NAMES[prof]
            tile.name.setText(bidi.ltr_name(name, rtl))  # the game's own word, in English in Hebrew too
            tile.setAccessibleName(name)
            tile.setAccessibleDescription(t("craft_profession"))
        self._step_word.setText(bidi.plain(t("cp_prof_lv"), rtl))
        self._pct_word.setText(bidi.plain(t("cp_bar"), rtl))
        self._pct_box.setAccessibleName(t("cp_bar_tip"))
        self._pct_box.setToolTip(t("cp_bar_tip"))
        self._rec_search.setPlaceholderText(bidi.plain(t("craft_search"), rtl))
        if self._prof_tabs is not None:
            self._prof_tabs_slot.removeWidget(self._prof_tabs)
            self._prof_tabs.hide()
            self._prof_tabs.deleteLater()
        # "Teacher & quests": a lone "&" would be a shortcut's mark on a button
        modes = [(t(key).replace("&", "&&"), mode) for mode, key in PROF_MODES]
        self._prof_tabs = Segmented(modes, self._prof_mode, rtl)
        self._prof_tabs.set_label(t("cp_tabs_a11y"))
        for b in self._prof_tabs.group.buttons():
            b.setFocusPolicy(Qt.NoFocus)
        self._prof_tabs.changed.connect(self._prof_mode_set)
        self._prof_tabs_slot.addWidget(self._prof_tabs)
        self._exp_head.title.setText(bidi.plain(t("cp_exp_table"), rtl))
        self._exp_head.mark.setText("+" if self._exp_folded else "\u2013")
        self._paint_glyphs()

    def _retext_summary(self) -> None:
        """The strip under the title: the job, the level, how many items the plan makes and what it costs."""
        t, rtl = self.t, self.t.rtl
        c = self._c
        if c is None:
            self._summary.setText(bidi.plain(t("cp_no_character"), rtl))
            return
        parts = [bidi.ltr_block(c.job_label or c.base_class, rtl), t("lv_short", n=c.level)]
        n = len(c.craft_targets)
        if not n:
            parts.append(t("cp_sum_none"))
        else:
            parts.append(t("cp_sum_targets", n=n))
            if self._plan is not None and self._plan.stages:
                parts.append(t("cp_mesos", n=bidi.ltr_block(_mesos(self._plan.cost), rtl)))
        self._summary.setText(bidi.plain(" · ".join(parts), rtl))

    def _retext_plan_btn(self) -> None:
        shown = self.plan_window is not None and self.plan_window.isVisible()
        self._plan_btn.setText(bidi.plain(self.t("cp_hide_plan" if shown else "cp_show_plan"), self.t.rtl))

    def _tab_set(self, key: str) -> None:
        self._tab = key
        self._stack.setCurrentIndex(TABS.index(key))

    # ------------------------------------------------------------ what to craft: the table

    def _fill_items(self) -> None:
        """The table for what is typed, each row's Make stepper wired to the character's craft_targets. Nothing typed:
        the class's gear — its weapons first (the stat column is theirs), then the rest, each by level as the site
        lists them — up to ITEM_ROWS, then "and N more" (the search finds them); a picked item the cut left out goes
        on top, so it can still be unpicked. The rows are filled again on typing without a rebuild, so the keyboard
        stays in the search box."""
        t, rtl = self.t, self.t.rtl
        bar = self._items_scroll.verticalScrollBar()
        at = bar.value()
        _clear(self._items_lay)
        _clear(self._head_lay)
        self._cols = {k: [] for k in COLS}
        self._types = []
        self._item_rows = {}
        c = self._c
        if c is None:
            return
        query = self._search.text().strip()
        if query:
            rows = [r for r in self._rows if _match(r.name, query)]
            shown = rows[:ITEM_ROWS]
        else:
            gear = sorted((r for r in self._rows if r.equip), key=lambda r: not isinstance(r.stat, int))
            cut = {r.key for r in gear[:ITEM_ROWS]}
            picked = [r for r in self._rows if r.key in c.craft_targets and r.key not in cut]
            rows, shown = picked + gear, picked + gear[:ITEM_ROWS]
        stat_word = next((r.stat_word for r in self._rows if r.stat_word), "")
        self._has_stat = bool(stat_word)
        self._fill_head(stat_word)
        for r in shown:
            row = self._item_row(r, self._has_stat)
            self._item_rows[r.key] = row
            self._items_lay.addWidget(row)
        if len(rows) > len(shown):
            self._items_lay.addWidget(_label(bidi.plain(t("cp_more", n=len(rows) - len(shown)), rtl), "Note"))
        if query and not rows:
            self._items_lay.addWidget(_label(bidi.plain(t("cp_nothing_found"), rtl), "Sub", wrap=True))
        self._items_lay.addSpacing(6)
        self._items_lay.addWidget(_label(bidi.plain(t("cp_items_hint"), rtl), "Note", wrap=True))
        self._items_lay.addStretch(1)
        if not self._has_stat:
            for w in self._cols["stat"]:
                w.setVisible(False)  # a class with no attack stat to rank by: no column for it
        self._measure_cols()
        if not query:
            QTimer.singleShot(0, self, lambda: bar.setValue(at))

    def _fill_head(self, stat_word: str) -> None:
        """The header row: the column names, muted and small, aligned as their columns are."""
        t, rtl = self.t, self.t.rtl
        spacer = QWidget()
        spacer.setFixedWidth(PIC)
        self._head_lay.addWidget(spacer)
        self._head_lay.addWidget(_label(bidi.plain(t("cp_col_item"), rtl), "ColHead", align=Qt.AlignBottom), 1)
        words = {
            "lv": bidi.plain(t("cp_col_lv"), rtl),
            "stat": bidi.ltr_name(stat_word, rtl) if stat_word else "",
            "recipe": bidi.plain(t("cp_col_recipe"), rtl),
            "cost": bidi.plain(t("cp_col_cost"), rtl),
            "shop": bidi.plain(t("cp_col_shop"), rtl),
            "make": bidi.plain(t("cp_make"), rtl),
        }
        for k in COLS:
            align = Qt.AlignRight if k in NUMERIC else Qt.AlignHCenter if k == "make" else Qt.AlignLeft
            w = _label(words[k], "ColHead", wrap=True, align=align | Qt.AlignBottom)
            self._cols[k].append(w)
            self._head_lay.addWidget(w)

    def _item_row(self, r: Row, has_stat: bool) -> QFrame:
        """One row: the picture, the name over its type word, the level, the class's stat, the recipe, the craft
        cost, what it saves against the shop, and the Make stepper (a picked row lit in the accent)."""
        t, rtl = self.t, self.t.rtl
        row = QFrame(objectName="ItemRow")
        row.setAttribute(Qt.WA_Hover, True)
        row.setProperty("picked", self._c.craft_targets.count(r.key) > 0)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(ROW_PAD, 8, ROW_PAD, 8)
        lay.setSpacing(COL_GAP)
        lay.addWidget(self._pics.label(r.key, PIC), 0, Qt.AlignVCenter)
        item = QWidget()
        iv = QVBoxLayout(item)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(1)
        iv.addWidget(_label(bidi.ltr_name(r.name, rtl), "ItemName", wrap=True))
        kind = _type_word(self._kb, r.key, t.lang)
        recipe = f"{r.discipline} {r.prof_lv}"
        kind_txt = bidi.plain(kind, rtl) if kind else ""
        narrow = bidi.plain(" · ".join(x for x in (kind_txt, bidi.ltr_block(recipe, rtl)) if x), rtl)
        type_lab = _label(narrow, "ItemType", wrap=True)
        self._types.append((type_lab, narrow, kind_txt))
        iv.addWidget(type_lab)
        lay.addWidget(item, 1)
        num = Qt.AlignRight | Qt.AlignVCenter

        def cell(text: str, muted: bool = False) -> QLabel:
            return _label(bidi.ltr_block(text, rtl), "CellMuted" if muted else "Cell", align=num)

        lv_ok = isinstance(r.lv, int)
        stat_ok = has_stat and isinstance(r.stat, int)
        cells = {
            "lv": cell(str(r.lv) if lv_ok else "\u2014", muted=not lv_ok),
            "stat": cell(str(r.stat) if stat_ok else "\u2014", muted=not stat_ok),
            "recipe": _label(bidi.ltr_name(recipe, rtl), "Recipe", align=Qt.AlignLeft | Qt.AlignVCenter),
            "cost": cell(_mesos(r.cost)),
            "shop": self._shop_cell(r),
        }
        step = _Stepper(self._c.craft_targets.count(r.key))
        step.setToolTip(t("cp_make_tip"))
        step.setAccessibleName(t("cp_make_tip"))
        step.changed.connect(lambda v, k=r.key: self._make_set(k, v))
        cells["make"] = step
        for k in COLS:
            self._cols[k].append(cells[k])
            lay.addWidget(cells[k], 0, Qt.AlignVCenter)
        return row

    def _shop_cell(self, r: Row) -> QWidget:
        """vs shop: what crafting saves against the NPC's price (in the accent), what it loses (a warm red), or that
        no NPC sells it (muted) — the word over the number, so the column stays narrow."""
        t, rtl = self.t, self.t.rtl
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        align = Qt.AlignRight | Qt.AlignVCenter
        if r.save is None:
            v.addWidget(_label(bidi.plain(t("cp_not_sold"), rtl), "NotSold", align=align))
            return box
        saves = r.save >= 0
        word, num = ("cp_saves", "Saves") if saves else ("cp_loses", "Loses")
        v.addWidget(_label(bidi.plain(t(word), rtl), num + "Word", align=align))
        v.addWidget(_label(bidi.ltr_block(_mesos(abs(r.save)), rtl), num, align=align))
        return box

    def _measure_cols(self) -> None:
        """Every fixed column as wide as its widest cell (the header's word counted), so the header and the rows
        line up; then the Recipe column placed for the window's width."""
        self._col_w = {}
        for k in COLS:
            cells = self._cols[k]
            for w in cells:
                w.ensurePolished()
            self._col_w[k] = max((_min_width(w) for w in cells), default=0)
            for w in self._cols[k]:
                w.setFixedWidth(self._col_w[k])
        self._recipe_placed = False
        self._place_recipe()

    def _place_recipe(self) -> None:
        """The Recipe column gets a column of its own when the window is wide enough to leave the item's name
        ITEM_MIN of room; narrower, the recipe joins the type word under the name ("Wand · Arcforge 6") — at the
        default width the eight columns left the name ~70 px."""
        if not self._col_w:
            return
        shown = [k for k in COLS if k != "recipe" and (k != "stat" or self._has_stat)]
        fixed = PIC + sum(self._col_w[k] for k in shown) + COL_GAP * (len(shown) + 1)
        room = self.width() - 2 * SIDE - SCROLLBAR_W - GUTTER - 2 * ROW_PAD
        wide = room - fixed - self._col_w["recipe"] - COL_GAP >= ITEM_MIN
        if self._recipe_placed and wide == self._wide:
            return  # (a drag-resize calls this on every step)
        self._wide, self._recipe_placed = wide, True
        for w in self._cols["recipe"]:
            w.setVisible(wide)
        for lab, narrow, kind in self._types:
            text = kind if wide else narrow
            lab.setText(text)
            lab.setVisible(bool(text))

    def _make_set(self, key: str, v: int) -> None:
        """The Make stepper: craft_targets holds a key once per make (duplicates are the count); the row lights
        while it is picked, and the plan follows."""
        c = self._profiles.active
        if c is None:
            return
        have = c.craft_targets.count(key)
        if v == have:
            return
        if v > have:
            c.craft_targets.extend([key] * (v - have))
        else:
            for _ in range(have - v):
                c.craft_targets.remove(key)
        self._profiles.save()
        row = self._item_rows.get(key)
        if row is not None:
            row.setProperty("picked", v > 0)
            row.style().unpolish(row)
            row.style().polish(row)
        self._replan()

    # ------------------------------------------------------------ the plan (both windows follow it)

    def _replan(self) -> None:
        """The plan made again from the character: the summary, the bag (its "in plan" marks) and the plan window
        follow."""
        self._plan = None
        c = self._c
        if c is not None and c.craft_targets:
            try:
                self._plan = craftplan.plan(
                    self._kb,
                    c,
                    list(c.craft_targets),
                    dict(c.craft_bag),
                    self._mode,
                    self._settings["craft_exp_table"],
                    self._choices,
                )
            except Exception:  # a plan must never take the window down
                log.warning("craft plan failed", exc_info=True)
                self._plan = None
        self._retext_summary()
        self._fill_bag()
        self._sync_plan()

    def _has_plan(self) -> bool:
        return self._plan is not None and any(st.steps for st in self._plan.stages)

    def _sync_plan(self, opening: bool = False) -> None:
        """The plan window opens by itself when the plan starts to have something to make (or the main window opens
        on one); otherwise, shown, it is drawn again. The player's ✕ on it holds until then."""
        has = self._has_plan()
        win = self.plan_window
        if self.isVisible() and has and (opening or not self._had_plan):
            self._open_plan()
        elif win is not None and win.isVisible():
            win.redraw()
        self._had_plan = has

    def _open_plan(self) -> None:
        if self.plan_window is None:
            self.plan_window = ForgePlanWindow(self)
        self.plan_window.redraw()
        self.plan_window.show_beside()

    def _plan_btn_clicked(self, _=False) -> None:
        """Show plan / Hide plan: the plan window, whatever the plan holds (an empty plan says what to do)."""
        if self.plan_window is not None and self.plan_window.isVisible():
            self.plan_window.hide()
        else:
            self._open_plan()

    def _key_of(self, name: str, fallback: str = "") -> str:
        """An item's KB key: the recipes table's product key, else the KB's own name lookup."""
        for rec in craftplan.recipes(self._kb).get(name.casefold(), ()):
            if rec.key:
                return rec.key
        got = getattr(self._kb, "_item_by_name", {}).get(name.lower(), "")
        return f"item/{got}" if got else fallback

    def _ticked(self, s: Step, on: bool) -> None:
        """A step ticked as crafted: its ingredients leave the bag (what is there of them), its products enter it,
        and the plan follows — its shapes shrink around the new bag, like the site's."""
        c = self._profiles.active
        if c is None or not on:
            return
        for ing in s.ingredients:
            key = ing.key or self._key_of(ing.name)
            if not key:
                continue
            have = int(c.craft_bag.get(key, 0) or 0)
            used = min(have, ing.qty * s.crafts)
            if used:
                left = have - used
                if left > 0:
                    c.craft_bag[key] = left
                else:
                    c.craft_bag.pop(key, None)
        pkey = s.key or self._key_of(s.name)
        if pkey:
            c.craft_bag[pkey] = c.craft_bag.get(pkey, 0) + s.crafts * s.makes
        self._profiles.save()
        self._replan()

    def _swap(self, s: Step) -> None:
        """The Swap button: the next of this product's recipes (round the ring), the plan follows."""
        variants = craftplan.recipes(self._kb).get(s.name.casefold(), ())
        if len(variants) < 2:
            return
        nums = [v.num for v in variants]
        cur = self._choices.get(s.name.casefold())
        if cur not in nums:
            cur = next((v.num for v in variants if v.discipline == s.discipline and v.prof_lv == s.prof_lv), nums[0])
        self._choices[s.name.casefold()] = nums[(nums.index(cur) + 1) % len(nums)]
        self._replan()

    def _mode_set(self, mode: str) -> None:
        self._mode = mode
        self._replan()

    # ------------------------------------------------------------ the bag

    def _bag_pool_items(self) -> list[tuple[str, str]]:
        """Every item a recipe uses or makes (name, KB key), by name: what the bag search can add — anything else the
        plan would never spend."""
        if self._pool is None:
            seen: dict[str, tuple[str, str]] = {}
            for variants in craftplan.recipes(self._kb).values():
                for rec in variants:
                    if rec.key:
                        seen.setdefault(rec.product.casefold(), (rec.product, rec.key))
                    for ing in rec.ingredients:
                        if ing.key:
                            seen.setdefault(ing.name.casefold(), (ing.name, ing.key))
            self._pool = sorted(seen.values(), key=lambda p: p[0].casefold())
        return self._pool

    def _fill_bag(self) -> None:
        """The bag: what the plan uses plus what is carried, in the site's groups (ores, gem ores, refined materials,
        mob drops, other), a count box each; what the search finds above them, to add. The box being typed in keeps
        the keyboard across the refill."""
        t, rtl = self.t, self.t.rtl
        focus = next(((k, b.cursorPosition()) for k, b in self._bag_boxes.items() if b.hasFocus()), None)
        bar = self._bag_scroll.verticalScrollBar()
        at = bar.value()
        _clear(self._bag_lay)
        self._bag_boxes = {}
        c = self._c
        if c is None:
            return
        entries: dict[str, tuple[str, str, bool]] = {}  # name casefold -> (name, KB key, in the plan)
        if self._plan is not None:
            for f in self._plan.farm:
                entries.setdefault(f.name.casefold(), (f.name, f.key, True))
            for st in self._plan.stages:
                for s in st.steps:
                    if not s.final:
                        entries.setdefault(s.name.casefold(), (s.name, s.key or self._key_of(s.name), True))
        for k, n in c.craft_bag.items():
            name = str((self._kb.get(k) or {}).get("name") or "")
            if name and int(n or 0) > 0:
                entries.setdefault(name.casefold(), (name, k, False))
        query = self._bag_search.text().strip()
        if query:
            found = [(n, k) for n, k in self._bag_pool_items() if n.casefold() not in entries and _match(n, query)]
            self._bag_lay.addWidget(_label(bidi.plain(t("cp_bag_found"), rtl), "GroupName"))
            if not found:
                self._bag_lay.addWidget(_label(bidi.plain(t("cp_bag_none_found"), rtl), "Sub", wrap=True))
            for name, key in found[:BAG_FOUND]:
                self._bag_lay.addWidget(self._bag_row(name, key, False))
        if not entries and not query:
            self._bag_lay.addWidget(_label(bidi.plain(t("cp_bag_empty"), rtl), "Sub", wrap=True))
        cats = craftplan.categories(self._kb)
        groups: dict[str, list[tuple[str, str, bool]]] = {}
        for name, key, in_plan in entries.values():
            if key:  # (the bag holds KB keys: an item the KB has no page for can't be counted)
                groups.setdefault(cats.get(name.casefold(), "other"), []).append((name, key, in_plan))
        for cat in sorted(groups, key=lambda g: CATEGORY_ORDER.get(g, 9)):
            items = sorted(groups[cat], key=lambda g: g[0].casefold())
            self._bag_lay.addWidget(self._group_head(cat, items))
            for name, key, in_plan in items:
                self._bag_lay.addWidget(self._bag_row(name, key, in_plan))
        self._bag_lay.addStretch(1)
        if focus is not None and focus[0] in self._bag_boxes:
            box = self._bag_boxes[focus[0]]
            box.setFocus()
            box.setCursorPosition(focus[1])
        QTimer.singleShot(0, self, lambda: bar.setValue(at))

    def _group_head(self, cat: str, items: list[tuple[str, str, bool]]) -> QWidget:
        """A group's name and its counts: "Ores  3 items · 3 in plan · 2 in bag"."""
        t, rtl = self.t, self.t.rtl
        bag = self._c.craft_bag
        head = QWidget()
        h = QHBoxLayout(head)
        h.setContentsMargins(0, 4, 0, 0)
        h.setSpacing(8)
        h.addWidget(_label(bidi.plain(t(CAT_KEYS.get(cat, "cp_cat_other")), rtl), "GroupName"))
        bits = [t("cp_targets", n=len(items)), t("cp_g_plan", n=sum(1 for i in items if i[2]))]
        carried = sum(1 for i in items if int(bag.get(i[1], 0) or 0) > 0)
        if carried:
            bits.append(t("cp_g_bag", n=carried))
        h.addWidget(_label(bidi.plain(" · ".join(bits), rtl), "GroupMeta"), 1)
        return head

    def _bag_row(self, name: str, key: str, in_plan: bool) -> QWidget:
        """One bag item: its picture, its name, "in plan" when the plan uses it, and its count box."""
        t, rtl = self.t, self.t.rtl
        row = QFrame(objectName="BagRow")
        row.setAttribute(Qt.WA_Hover, True)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(ROW_PAD, 5, ROW_PAD, 5)
        lay.setSpacing(8)
        lay.addWidget(self._pics.label(key, PIC), 0, Qt.AlignVCenter)
        lay.addWidget(_label(bidi.ltr_name(name, rtl), "ItemName", wrap=True), 1)
        if in_plan:
            lay.addWidget(_label(bidi.plain(t("cp_in_plan"), rtl), "InPlan"), 0, Qt.AlignVCenter)
        box = _SearchBox(objectName="Num", maxLength=6)
        box.setFixedWidth(64)
        box.setAlignment(Qt.AlignCenter)
        have = int(self._c.craft_bag.get(key, 0) or 0)
        box.setText(str(have) if have else "")
        box.setPlaceholderText("0")
        box.setToolTip(t("cp_bag_tip"))
        box.setAccessibleName(t("cp_bag_tip"))
        box.textChanged.connect(lambda _t: self._edit.start())
        self._bag_boxes[key] = box
        lay.addWidget(box, 0, Qt.AlignVCenter)
        return row

    # ------------------------------------------------------------ the professions: the switch and the card

    def _top_prof(self, c: Character) -> str:
        """The profession a character is highest in (the first of a tie; Smithing when none is learned yet): where
        the tab opens for them."""
        crafts = c.crafts or {}
        return max(crafting.PROFESSIONS, key=lambda p: (int(crafts.get(p, 0) or 0), -crafting.PROFESSIONS.index(p)))

    def _glyph_colours(self) -> dict[str, str]:
        pal = palette()
        return {"muted": pal.muted, "text": pal.text, "lit": ink(accent_of(self._settings)[0])}

    def _paint_glyphs(self) -> None:
        """Every line icon in the glass's and the accent's colours now (another look: drawn again)."""
        colours = self._glyph_colours()
        for g in self.findChildren(_Glyph):
            g.paint(colours)

    def _glyph(self, name: str, px: int = GLYPH, tone: str = "muted") -> _Glyph:
        g = _Glyph(name, px, tone)
        g.paint(self._glyph_colours())
        return g

    def _lv_words(self, key: str, n: int) -> str:
        """ "Lv. 3", "Level 3" (key: lv_short, craft_lv_tag, craft_level_group) for a chip or a heading: in Hebrew
        with a gap the digit's ink keeps clear of the word ("רמה1" read as one word, TL2-16)."""
        words = self.t(key, n=n)
        return words.replace(" ", LV_GAP, 1) if self.t.rtl else words

    def _show_prof(self) -> None:
        """The picked profession on the tab: the character level box, its tile lit, its card's stepper and bar % box
        read from the character (signals off: a re-read is not the player's edit), then all that follows them."""
        c = self._c
        if c is None:
            return
        t, rtl, prof = self.t, self.t.rtl, self._prof
        name = crafting.NAMES[prof]
        self._lv_box.blockSignals(True)
        self._lv_box.setText(str(c.level) if c.level else "")
        self._lv_box.blockSignals(False)
        self._tiles[prof].setChecked(True)
        self._prof_glyph.icon_name = PROF_ICONS[prof]
        self._prof_glyph.paint()
        self._prof_name.setText(bidi.ltr_name(name, rtl))
        self._prof_makes.setText(bidi.plain(t(f"craft_makes_{prof}"), rtl))
        self._step.blockSignals(True)
        self._step.set_top(craftplan.top_level(self._kb))  # the + greys out at the KB's own cap
        self._step.setValue(craftplan.progress(self._kb, c, prof).level)  # a saved 50 shows as the top (TL1-6)
        self._step.blockSignals(False)
        self._step.setToolTip(t("cp_prof_tip", disc=name))
        self._step.setAccessibleName(t("cp_prof_tip", disc=name))
        pct = (c.craft_pct or {}).get(prof)
        self._pct_box.blockSignals(True)
        self._pct_box.setText(str(pct) if pct else "")
        self._pct_box.blockSignals(False)
        self._refresh_prof()
        self._fill_mode()

    def _refresh_prof(self) -> None:
        """All that follows the levels and the bar %: each tile's level line, the picked profession's bar, its EXP to
        the next level and the character level that one asks for, what it opens, the EXP table's row lit."""
        c = self._c
        if c is None:
            return
        t, rtl = self.t, self.t.rtl
        table = self._settings["craft_exp_table"]
        for prof, tile in self._tiles.items():
            p = craftplan.progress(self._kb, c, prof, table)
            words = self._lv_words("lv_short", p.level) + (f" · {p.pct}%" if p.pct else "")
            tile.level.setText(bidi.plain(words, rtl))
        pr = craftplan.progress(self._kb, c, self._prof, table)
        self._bar.set(pr.pct / 100, accent_of(self._settings)[0])
        if pr.next is None:
            line = t("cp_prog_top", prof=crafting.NAMES[self._prof])
        elif pr.exp is None:
            line = t("cp_prog_unknown", lv=t("lv_short", n=pr.next))
        else:
            line = t("cp_prog", have=_mesos(pr.have), need=_mesos(pr.exp), left=_mesos(pr.left), lv=t("lv_short", n=pr.next))
            if pr.measured:
                line += f" ({t('cp_exp_yours')})"
        self._exp_line.setText(bidi.paragraph_html(line, "rtl" if rtl else "ltr", style="margin:0;"))
        asks = pr.next is not None and bool(pr.char_level)
        if asks:
            nxt, short = t("lv_short", n=pr.next), pr.char_level - int(c.level or 0)
            words = (
                t("cp_req_short", lv=nxt, char=pr.char_level, n=short)
                if short > 0
                else t("cp_req_ok", lv=nxt, char=pr.char_level)
            )
            self._req_line.setText(bidi.plain(words, rtl))
            _rename(self._req_line, "Warn" if short > 0 else "Note")
        self._req_line.setVisible(asks)
        self._fill_next(pr)
        self._mark_exp()

    def _fill_next(self, pr: craftplan.Progress) -> None:
        """What the next level opens, on the profession's card: "Lv. 4 unlocks 6 recipes", a link to them, their
        products' pictures (each named on hover). Hidden at the cap, or when that level opens nothing."""
        t, rtl = self.t, self.t.rtl
        _clear(self._next_pics)
        opens = [r for r in craftplan.profession_recipes(self._kb, self._prof) if pr.next and r.prof_lv == pr.next]
        self._next_box.setVisible(bool(opens))
        if not opens:
            return
        self._next_words.setText(bidi.plain(t("cp_next_unlocks", lv=t("lv_short", n=pr.next), n=len(opens)), rtl))
        self._next_link.setText(_button_words(t("cp_next_see", n=len(opens)), rtl))
        keys: dict[str, str] = {}  # each product once, though it has two recipes at that level
        for r in opens:
            keys.setdefault(r.product, r.key)
        for name, key in list(keys.items())[:NEXT_PICS]:
            self._next_pics.addWidget(self._pics.label(key or self._key_of(name), NEXT_PIC, caption=name))
        if len(keys) > NEXT_PICS:
            self._next_pics.addWidget(_label(bidi.plain(f"+{len(keys) - NEXT_PICS}", rtl), "Note"), 0, Qt.AlignVCenter)
        self._next_pics.addStretch(1)

    def _see_next(self) -> None:
        """The card's link to the next level's recipes: the Recipes side on that level, scrolled up to them."""
        c = self._c
        if c is None:
            return
        pr = craftplan.progress(self._kb, c, self._prof, self._settings["craft_exp_table"])
        if pr.next is None:
            return
        self._scope, self._prof_mode = pr.next, "recipes"
        self._fill_mode()
        bar = self._prof_scroll.verticalScrollBar()
        QTimer.singleShot(
            0, self, lambda: bar.setValue(self._prof_tabs.mapTo(self._prof_scroll.widget(), QPoint(0, 0)).y() - 4)
        )

    def _prof_pick(self, prof: str) -> None:
        """A tile clicked (or open_with): the tab on that profession. A bar % still being typed is saved first, to
        the profession it was typed for; one level picked among the recipes goes back to what the level allows."""
        if prof not in self._tiles or self._c is None:
            return
        if self._edit.isActive():
            self._edit.stop()
            self._edits_saved()
        self._prof = prof
        if isinstance(self._scope, int):
            self._scope = "now"
        self._show_prof()

    def _prof_level_set(self, v: int) -> None:
        """The level stepper: the character's level in the profession, saved at once (Character.crafts); its tile, its
        card and its recipes follow now, the plan once the clicks pause."""
        c = self._profiles.active
        if c is None:
            return
        c.crafts = {**(c.crafts or {}), self._prof: int(v)}
        self._profiles.save()
        self._refresh_prof()
        self._fill_mode()  # the recipes it allows now, or the quests' profession chips
        self._edit.start()

    def _prof_mode_set(self, mode: str) -> None:
        """The Recipes / Teacher & quests switch."""
        if mode != self._prof_mode:
            self._prof_mode = mode
            self._fill_mode()

    def _fill_mode(self) -> None:
        """The side the switch shows, filled for the picked profession (the other waits, hidden, until picked)."""
        recipes = self._prof_mode == "recipes"
        if self._prof_tabs is not None:
            self._prof_tabs.set_value(self._prof_mode)
        self._rec_box.setVisible(recipes)
        self._teach_box.setVisible(not recipes)
        if recipes:
            self._fill_recipes()
        else:
            self._fill_teacher()

    # ------------------------------------------------------------ the professions: the recipes

    def _scope_set(self, scope) -> None:
        self._scope = scope
        self._fill_recipes()

    def _fill_recipes(self) -> None:
        """The recipes in the scope picked — what the level allows (the newest level first, its best value on top),
        every one (by level, the next one and the locked ones marked), or one level — with the search's words in a
        recipe's name or an ingredient's ("Garnet Ore" finds what it goes into), as cards level by level (in a level,
        the fewest mesos burned per EXP first: NiaMeowDB's numbers), RECIPES_SHOWN of them before "and N more". Only
        the cards change: the search box keeps the keyboard."""
        self._recipes_in = palette()
        _clear(self._rec_lay)
        _clear(self._scope_flow)
        _clear(self._levels_flow)
        c = self._c
        if c is None:
            return
        t, rtl, prof = self.t, self.t.rtl, self._prof
        name = crafting.NAMES[prof]
        level = craftplan.progress(self._kb, c, prof).level
        every = craftplan.profession_recipes(self._kb, prof)
        levels = sorted({r.prof_lv for r in every})
        if self._scope not in ("now", "all") and self._scope not in levels:
            self._scope = "now"
        scope = self._scope
        self._levels_word.setText(bidi.plain(t("cp_prof_lv"), rtl))
        for value, words in (("now", t("craft_mode_now")), ("all", t("craft_mode_all"))):
            self._scope_flow.addWidget(self._scope_chip(value, words, "Scope"))
        for lv in levels:
            chip = self._scope_chip(lv, str(lv), "LvChip")
            chip.setProperty("locked", lv > level)  # past the character's level: muted
            chip.setToolTip(t("cp_level_tip", lv=t("lv_short", n=lv)))
            chip.setAccessibleName(t("lv_short", n=lv))
            self._levels_flow.addWidget(chip)
        if prof not in self._econ:  # (the search refills the cards on every pause: the page is read once)
            self._econ[prof] = crafting.economy(self._kb, prof)
        econ = self._econ[prof]

        def worth(r: craftplan.Recipe) -> crafting.Recipe | None:
            return econ.get((r.product.casefold(), r.prof_lv, r.makes))

        def order(r: craftplan.Recipe) -> tuple:  # in a level: the fewest mesos burned per EXP, then the most EXP
            e = worth(r)
            return (crafting.burn_per_exp(e) if e is not None else float("inf"), -r.exp, r.product.casefold(), r.num)

        if scope == "now":
            shown = sorted((r for r in every if r.prof_lv <= level), key=lambda r: (-r.prof_lv, *order(r)))
            head = t("craft_head", n=len(shown), prof=name, lv=level)
        elif scope == "all":
            shown = sorted(every, key=lambda r: (r.prof_lv, *order(r)))
            head = t("craft_head_all", n=len(shown), prof=name)
        else:
            shown = sorted((r for r in every if r.prof_lv == scope), key=order)
            head = t("cp_head_level", n=len(shown), prof=name, lv=scope)
            if scope > level:
                head += " " + t("cp_head_locked", lv=level)
        self._rec_head.setText(bidi.paragraph_html(head, "rtl" if rtl else "ltr", style="margin:0;"))
        query = self._rec_search.text().strip()
        if query:
            shown = [r for r in shown if _match(r.product, query) or any(_match(i.name, query) for i in r.ingredients)]
        if not shown:
            self._rec_lay.addWidget(_label(bidi.plain(t("craft_no_match" if query else "craft_none"), rtl), "Sub", wrap=True))
            return
        # the best value: what the level allows, the newest level's first (the old crafting page's own pick)
        top = worth(shown[0])
        best = shown[0] if scope == "now" and not query and top is not None and top.exp > 0 else None
        last = None
        for r in shown[:RECIPES_SHOWN]:
            if r.prof_lv != last:
                last = r.prof_lv
                self._rec_lay.addWidget(self._level_caption(r.prof_lv, level, scope == "all"))
            self._rec_lay.addWidget(self._recipe_card(r, worth(r), r is best, r.prof_lv > level))
        if len(shown) > RECIPES_SHOWN:
            more = f"{t('cp_more', n=len(shown) - RECIPES_SHOWN)} · {t('cp_rec_more')}"
            self._rec_lay.addWidget(_label(bidi.plain(more, rtl), "Note", wrap=True))

    def _scope_chip(self, value, words: str, name: str) -> QPushButton:
        """A chip that picks what the recipes show: lit while it is the one picked."""
        chip = QPushButton(_button_words(words, self.t.rtl), objectName=name)
        chip.setCheckable(True)
        chip.setChecked(value == self._scope)
        chip.setCursor(Qt.PointingHandCursor)
        chip.setFocusPolicy(Qt.NoFocus)
        chip.clicked.connect(lambda _=False, v=value: self._scope_set(v))
        return chip

    def _caption(self, text: str) -> QLabel:
        """A section's small heading over its cards: capitals in English, Hebrew has none."""
        rtl = self.t.rtl
        return _label(bidi.plain(text if rtl else text.upper(), rtl), "Caption")

    def _level_caption(self, lv: int, level: int, marks: bool) -> QLabel:
        """A level's heading over its recipes ("LEVEL 4 · NEXT"); marks: the one past the character's level says so,
        the ones after it that they are locked (every recipe shows)."""
        words = self._lv_words("craft_level_group", lv)
        if marks and lv == level + 1:
            words += f" · {self.t('cp_lv_next')}"
        elif marks and lv > level + 1:
            words += f" · {self.t('cp_lv_locked')}"
        return self._caption(words)

    @staticmethod
    def _card(lit: bool = False) -> tuple[QFrame, QVBoxLayout]:
        """A card on the glass and the column inside it; lit: in the accent (the best pick)."""
        card = QFrame(objectName="Card")
        if lit:
            card.setProperty("lit", True)
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        return card, v

    def _chips(self, chips: list[tuple[str, str, str]]) -> QWidget:
        """A row of chips, each (its words, its name: Chip, ChipOn, ChipExp, ChipWarn, its tip), wrapping rather than
        widening the card; it runs from the right in Hebrew."""
        box = QWidget()
        flow = FlowLayout(box, spacing=4, line_spacing=4)
        for words, name, tip in chips:
            chip = _label(bidi.plain(words, self.t.rtl), name)
            if tip:
                chip.setToolTip(tip)
            flow.addWidget(chip)
        return box

    def _links(self, acts: list) -> QWidget:
        """A card's links in a row (wrapping when narrow), each (its words, what a click does)."""
        box = QWidget()
        flow = FlowLayout(box, spacing=14, line_spacing=2)
        for words, then in acts:
            b = QPushButton(_button_words(words, self.t.rtl), objectName="Link")
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, then=then: then())
            flow.addWidget(b)
        return box

    def _recipe_card(self, r: craftplan.Recipe, worth: crafting.Recipe | None, best: bool, locked: bool) -> QFrame:
        """One recipe: the product's picture and name (what one craft makes muted beside it), its chips — the best
        value, the level (orange while locked), the EXP, the fee — then a row an ingredient, and at the foot what a
        craft gains or burns at NPC prices (NiaMeowDB's numbers, when it has them) and Ask in chat."""
        t, rtl = self.t, self.t.rtl
        card, v = self._card(lit=best)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._pics.label(r.key or self._key_of(r.product), RECIPE_PIC, caption=r.product), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(5)
        # "Screw (makes 10)": one label, the aside muted in it (two labels side by side wrapped the name early)
        name = escape(bidi.ltr_name(r.product, rtl))
        if r.makes > 1:
            aside = escape(bidi.plain(f"({t('cp_makes', n=r.makes)})", rtl))
            name += f' <span style="color:{palette().muted}; font-size:12px; font-weight:400">{aside}</span>'
        title = _label(name, "CardTitle", wrap=True)
        title.setTextFormat(Qt.RichText)
        col.addWidget(title)
        chips = [
            (self._lv_words("craft_lv_tag", r.prof_lv), "ChipWarn" if locked else "Chip", ""),
            (f"+{r.exp:,} EXP", "ChipExp", ""),
            (t("cp_fee", n=_mesos(r.fee)), "Chip", ""),
        ]
        if best:
            chips.insert(0, (t("craft_best"), "ChipOn", t("cp_best_tip")))
        col.addWidget(self._chips(chips))
        for ing in r.ingredients:
            col.addWidget(self._ing_row(ing))
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 2, 0, 0)
        foot.setSpacing(12)
        if worth is not None:
            net = t("cp_net_gain", n=_mesos(worth.net)) if worth.net >= 0 else t("cp_net_loss", n=_mesos(-worth.net))
            line = _label(bidi.paragraph_html(net, "rtl" if rtl else "ltr", style="margin:0;"), "Muted", wrap=True)
            line.setTextFormat(Qt.RichText)
            foot.addWidget(line, 1)
        else:
            foot.addStretch(1)
        foot.addWidget(self._links([(t("ask_short"), lambda: NAV.ask_requested.emit(t("craft_ask_recipe", item=r.product)))]),
                       0, Qt.AlignTop)
        col.addLayout(foot)
        top.addLayout(col, 1)
        v.addLayout(top)
        return card

    def _ing_row(self, ing: craftplan.Ingredient) -> QFrame:
        """One ingredient: its picture, how many of what, where it comes from at the end (the profession that makes
        it, the monster that drops it, or an NPC's price; every source on hover); a click opens its item page."""
        t, rtl = self.t, self.t.rtl
        key = ing.key or self._key_of(ing.name)
        row = _LinkRow(bool(key))
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 3, 6, 3)
        h.setSpacing(8)
        h.addWidget(self._pics.label(key, ING_PIC), 0, Qt.AlignVCenter)
        h.addWidget(_label(bidi.ltr_name(f"{ing.qty}× {ing.name}", rtl), "IngName", wrap=True), 1)
        if ing.optional:
            h.addWidget(_label(bidi.plain(t("cp_optional"), rtl), "Chip"), 0, Qt.AlignVCenter)
        icon, short, tip = self._where(ing.name, key)
        if short:
            h.addWidget(self._glyph(icon), 0, Qt.AlignVCenter)
            h.addWidget(_label(bidi.plain(short, rtl), "IngWhere"), 0, Qt.AlignVCenter)
        if key:
            h.addWidget(_label("\u2039" if rtl else "\u203a", "Chevron"), 0, Qt.AlignVCenter)
            row.clicked.connect(lambda k=key: NAV.item_requested.emit(k))
        row.setToolTip("\n".join(x for x in (tip, t("cp_ing_tip") if key else "") if x))
        return row

    def _where(self, name: str, key: str) -> tuple[str, str, str]:
        """Where an ingredient comes from, as (its line icon, a short word for the row's end, every source for its tip):
        the end names the profession that makes it (its lowest-level recipe), else the monster that drops it (the
        players' first, and how many more), else an NPC's price; the tip lists them all. ("", "", "") when the KB knows
        none."""
        t = self.t
        variants = craftplan.recipes(self._kb).get(name.casefold(), ())
        mobs = list(self._kb.droppers.get(key, [])) if key else []
        sells = craftplan.sources(self._kb).sellers.get(name.casefold(), ())
        tips = []
        if variants:
            made = sorted({(v.prof_lv, v.discipline) for v in variants})
            tips.append(t("cp_ing_crafted", list=", ".join(f"{d} {lv}" for lv, d in made)))
        if mobs:
            named = []
            for m in mobs[: craftplan.DROPPERS_SHOWN]:
                e = self._kb.get(m) or {}
                lv = (e.get("props") or {}).get("Level")
                named.append(f"{e.get('name', m)} ({t('lv_short', n=lv)})" if lv else str(e.get("name", m)))
            if len(mobs) > craftplan.DROPPERS_SHOWN:
                named.append(t("cp_more", n=len(mobs) - craftplan.DROPPERS_SHOWN))
            tips.append(t("cp_drops_from", list=", ".join(named)))
        if sells:
            npc, place, price = sells[0]
            tips.append(t("cp_buy_at", who=" · ".join(x for x in (npc, place, t("cp_mesos", n=_mesos(price))) if x)))
        tip = "\n".join(tips)
        if variants:
            low = min(variants, key=lambda v: (v.prof_lv, v.num))
            return PROF_ICONS.get(DISCIPLINE_KEY.get(low.discipline, ""), "hammer"), f"{low.discipline} {low.prof_lv}", tip
        if mobs:
            first = str((self._kb.get(mobs[0]) or {}).get("name", ""))
            return "ghost", first + (f" +{len(mobs) - 1}" if len(mobs) > 1 else ""), tip
        if sells:
            return "coins", t("cp_mesos", n=_mesos(sells[0][2])), tip
        return "", "", ""

    # ------------------------------------------------------------ the professions: the teacher and its quests

    def _fill_teacher(self) -> None:
        """The Teacher side: the teacher's card, then the profession's first and master quests (Done when the
        character marked them)."""
        _clear(self._teach_lay)
        c = self._c
        if c is None:
            return
        t, prof = self.t, self._prof
        if prof not in self._infos:
            self._infos[prof] = crafting.info(self._kb, prof)
        i = self._infos[prof]
        self._teach_lay.addWidget(self._caption(t("craft_teacher_head")))
        self._teach_lay.addWidget(self._teacher_card(prof, i))
        for name, lv, head in ((i.start_quest, i.start_level, "craft_start"), (i.master_quest, i.master_level, "craft_master")):
            q = self._quest_named(name)
            if q is None:
                continue
            self._teach_lay.addWidget(self._caption(t(head, lv=lv or q.opens_at())))
            self._teach_lay.addWidget(self._quest_card(q, q.key in (c.quests_done or ())))

    def _teacher_card(self, prof: str, i: crafting.Info) -> QFrame:
        """Who teaches the profession: their picture, name and town, what the profession makes, from what level they
        teach it, what a craft costs, where to craft it; the way to them, their NPC page, Ask in chat."""
        t, rtl = self.t, self.t.rtl
        name = crafting.NAMES[prof]
        card, v = self._card()
        top = QHBoxLayout()
        top.setSpacing(12)
        if i.teacher_key:
            top.addWidget(self._pics.label(i.teacher_key, NPC_PIC[0], NPC_PIC[1], caption=i.teacher), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(_label(bidi.ltr_name(i.teacher or name, rtl), "CardTitle", wrap=True))
        sub = t("cp_teacher_sub", prof=name, town=i.teacher_town or "?") if i.teacher else t("cp_no_teacher")
        col.addWidget(_label(bidi.plain(sub, rtl), "CardSub", wrap=True))
        col.addWidget(_label(bidi.plain(t(f"craft_makes_{prof}"), rtl), "Text", wrap=True))
        facts = []
        if i.teacher and i.start_level:
            facts.append(t("cp_learn_from", n=i.start_level))
        fees = [r.fee for r in craftplan.profession_recipes(self._kb, prof)]
        if fees and max(fees) > 0:
            facts.append(t("cp_fees", lo=_mesos(min(fees)), hi=_mesos(max(fees))))
        if i.station_towns:
            towns = (" וב-" if rtl else ", ").join(i.station_towns)
            facts.append(t("craft_station", station=i.station, towns=towns))
        for fact in facts:
            line = _label(bidi.paragraph_html(fact, "rtl" if rtl else "ltr", style="margin:0;"), "Muted", wrap=True)
            line.setTextFormat(Qt.RichText)
            col.addWidget(line)
        acts = []
        where = self._npc_map(i.teacher_key) if i.teacher_key else ""
        if where:
            acts.append((t("craft_go_teacher"), lambda: NAV.map_requested.emit(where)))
        if i.teacher_key:
            acts.append((t("cp_teacher_info"), lambda: NAV.npc_requested.emit(i.teacher_key)))
        acts.append((t("ask_short"), lambda: NAV.ask_requested.emit(t("craft_ask", prof=name))))
        col.addSpacing(2)
        col.addWidget(self._links(acts))
        top.addLayout(col, 1)
        v.addLayout(top)
        return card

    def _quest_card(self, q: quests.Quest, done: bool) -> QFrame:
        """A profession's quest: its name; its level, EXP and Done chips; who gives it and what must come first (a
        quest, a fee); what it needs, a row each (the monster's or the item's page a click away); what it pays; and
        Open in Quests, where the whole quest card is."""
        t, rtl = self.t, self.t.rtl
        card, v = self._card()
        v.addWidget(_label(bidi.ltr_name(q.name, rtl), "CardTitle", wrap=True))
        c = self._c
        lv = q.opens_at()
        chips = [(self._lv_words("craft_lv_tag", lv), "ChipWarn" if c is not None and c.level < lv else "Chip", "")]
        if q.profession:
            disc, plv = q.profession
            short = c is not None and int((c.crafts or {}).get(disc.lower(), 0) or 0) < plv
            chips.append((f"{disc} {plv}", "ChipWarn" if short else "Chip", t("cp_quest_prof_tip", prof=disc, lv=plv)))
        if q.exp:
            chips.append((f"+{q.exp:,} EXP", "ChipExp", ""))
        if q.cycle in ("daily", "weekly"):
            chips.append((t(f"q_{q.cycle}"), "Chip", t(f"q_{q.cycle}_tip")))
        if done:
            chips.append((t("cp_quest_done"), "ChipOn", ""))
        v.addWidget(self._chips(chips))
        lines = [t("q_from_npc", npc=bidi.ltr_block(q.npc, rtl))] if q.npc else []
        if q.afters:
            lines.append(t("q_after", name=", ".join(bidi.ltr_block(a, rtl) for a in q.afters)))
        lines += q.prereq_hints(t)
        for line in lines:
            v.addWidget(_label(bidi.plain(line, rtl), "Muted", wrap=True))
        needs = self._needs_of(q)
        if needs:
            v.addWidget(_label(bidi.plain(t("q_needs_head"), rtl), "NeedHead"))
            for kind, target, count, key in needs:
                v.addWidget(self._need_row(kind, target, count, key))
        pays = ([t("cp_mesos", n=_mesos(q.mesos))] if q.mesos else []) + list(q.rewards)
        if pays:
            v.addWidget(_label(bidi.plain(f"{t('q_gets_head')} {_pieces(pays, rtl, ' · ')}", rtl), "Muted", wrap=True))
        v.addWidget(self._links([(t("cp_open_quest"), lambda: NAV.tool_requested.emit("quest_tool", q.key))]))
        return card

    def _need_row(self, kind: str, target: str, count: int, key: str) -> QFrame:
        """One thing a quest needs: its picture, how many of what, "defeat" or "collect" at the end; a monster's or an
        item's page a click away."""
        t, rtl = self.t, self.t.rtl
        page = key.partition("/")[0]
        row = _LinkRow(page in ("monster", "item"))
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 3, 6, 3)
        h.setSpacing(8)
        h.addWidget(self._pics.label(key, ING_PIC, caption=target), 0, Qt.AlignVCenter)
        h.addWidget(_label(bidi.ltr_name(f"{count}× {target}" if count else target, rtl), "IngName", wrap=True), 1)
        does = {"defeat": ("swords", "cp_need_defeat"), "collect": ("backpack", "cp_need_collect")}.get(kind)
        if does:
            h.addWidget(self._glyph(does[0]), 0, Qt.AlignVCenter)
            h.addWidget(_label(bidi.plain(t(does[1]), rtl), "IngWhere"), 0, Qt.AlignVCenter)
        if page in ("monster", "item"):
            h.addWidget(_label("\u2039" if rtl else "\u203a", "Chevron"), 0, Qt.AlignVCenter)
            signal = NAV.monster_requested if page == "monster" else NAV.item_requested
            row.clicked.connect(lambda k=key, s=signal: s.emit(k))
        return row

    def _quest_named(self, name: str) -> quests.Quest | None:
        """A quest of the KB by its name ("A Blacksmith in My Own Right!": case and a closing "!" aside)."""
        if self._quest_keys is None:
            self._quest_keys = {}
            for k, e in self._kb.entities.items():
                if e.get("category") == "quest":
                    self._quest_keys.setdefault(str(e.get("name") or "").rstrip("!").strip().lower(), k)
        key = self._quest_keys.get((name or "").rstrip("!").strip().lower())
        return quests.quest(self._kb, key) if key else None

    def _needs_of(self, q: quests.Quest) -> list[tuple[str, str, int, str]]:
        """What a quest needs, each (its kind: "defeat", "collect" or another, its name, how many, its KB key): the
        quest_reqs table's rows (the keys resolved there), else the quest page's own lines."""
        if self._quest_needs is None:
            self._quest_needs = {}
            for r in tables.rows(self._kb, "quest_reqs"):
                self._quest_needs.setdefault(str(r.get("quest_key") or ""), []).append(r)
        rows = self._quest_needs.get(q.key)
        if rows:
            return [
                (str(r.get("kind") or ""), str(r.get("target") or ""), int(r.get("count") or 0), str(r.get("target_key") or ""))
                for r in rows
            ]
        out = []
        for need in q.needs:
            m = re.match(r"(Defeat |Collect )?(.+?) x ([\d,]+)$", need)
            if m is None:
                out.append(("", need, 0, ""))
                continue
            defeat, target, count = bool(m.group(1) == "Defeat "), m.group(2).strip(), int(m.group(3).replace(",", ""))
            mob = self._kb.monster_keys(target) if defeat else []
            key = mob[0] if mob else ("" if defeat else self._key_of(target))
            out.append(("defeat" if defeat else "collect", target, count, key))
        return out

    def _npc_map(self, npc_key: str) -> str:
        """The map an NPC stands on (the npcs table), "" when the KB doesn't say."""
        if self._npc_maps is None:
            self._npc_maps = {}
            for r in tables.rows(self._kb, "npcs"):
                if r.get("key") and r.get("map_key"):
                    self._npc_maps.setdefault(str(r["key"]), str(r["map_key"]))
        return self._npc_maps.get(npc_key, "")

    # ------------------------------------------------------------ the professions' EXP table

    def _fill_exp(self) -> None:
        """One row per crafting level below the cap, at the foot of the profession's card: the EXP to the next (a box
        — the player's measured value replaces the KB's; empty where neither says, to be typed) and whose number it
        is, saved to settings["craft_exp_table"]; the picked profession's level lit."""
        t, rtl = self.t, self.t.rtl
        _clear(self._exp_lay)
        self._exp_boxes = {}
        self._exp_marks = {}
        self._exp_words = {}
        self._exp_lay.addWidget(_label(bidi.plain(t("cp_exp_hint"), rtl), "Note", wrap=True))
        arrow = "\u2190" if rtl else "\u2192"  # the way the levels read: right to left in Hebrew
        exps = {e.level: e.exp for e in craftplan.exp_needs(self._kb, self._settings["craft_exp_table"])}
        for lv in range(1, craftplan.top_level(self._kb)):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 2, 0, 2)
            h.setSpacing(8)
            words = _label(bidi.plain(f"{t('lv_short', n=lv)} {arrow} {t('lv_short', n=lv + 1)}", rtl), "Cell")
            self._exp_words[lv] = words
            h.addWidget(words, 1)
            box = _SearchBox(objectName="Num", maxLength=6)
            box.setFixedWidth(72)
            box.setAlignment(Qt.AlignCenter)
            box.setText(str(exps[lv]) if exps.get(lv) else "")
            box.setPlaceholderText("?")
            box.setToolTip(t("cp_exp_tip"))
            box.setAccessibleName(t("cp_exp_tip"))
            box.textChanged.connect(lambda _t: self._edit.start())
            mark = _label("", "Note")
            self._exp_boxes[lv] = box
            self._exp_marks[lv] = mark
            h.addWidget(box)
            h.addWidget(mark)
            self._exp_lay.addWidget(row)
        if self._exp_marks:
            # every mark as wide as the wider of its two words (bold, as the player's own is), so the boxes line up
            probe = next(iter(self._exp_marks.values()))
            probe.ensurePolished()
            bold = QFont(probe.font())
            bold.setBold(True)
            fm = QFontMetrics(bold)
            width = max(fm.horizontalAdvance(bidi.plain(t(k), rtl)) for k in ("cp_exp_kb", "cp_exp_yours")) + 4
            for mark in self._exp_marks.values():
                mark.setFixedWidth(width)
        self._mark_exp()

    def _mark_exp(self) -> None:
        """Each EXP row's mark: the player's own number (in the accent), the KB's, or none where neither has one; the
        row of the picked profession's level lit."""
        t, rtl = self.t, self.t.rtl
        rows = craftplan.exp_needs(self._kb, self._settings["craft_exp_table"])
        mine = {e.level for e in rows if e.measured}
        known = {e.level for e in rows if e.exp}
        for lv, mark in self._exp_marks.items():
            word = "cp_exp_yours" if lv in mine else "cp_exp_kb" if lv in known else ""
            mark.setText(bidi.plain(t(word), rtl) if word else "")
            _rename(mark, "Mine" if lv in mine else "Note")
        now = craftplan.progress(self._kb, self._c, self._prof).level if self._c is not None else None
        for lv, words in self._exp_words.items():
            _rename(words, "CellOn" if lv == now else "Cell")

    def _fold_exp(self) -> None:
        self._exp_folded = not self._exp_folded
        self._exp_body.setVisible(not self._exp_folded)
        self._exp_head.mark.setText("+" if self._exp_folded else "\u2013")

    # ------------------------------------------------------------ the player's own numbers

    def _edits_saved(self) -> None:
        """The pause held: the character level box, the picked profession's bar % box, the bag counts and the EXP
        boxes saved (an empty box unsets), then what follows them on the profession's card and the plan made again.
        Nothing is rebuilt under the box being typed in."""
        c = self._profiles.active
        if c is None:
            return
        v = self._lv_box.text().strip()
        if v.isdigit() and 0 < int(v) <= 250:
            c.level = int(v)
        key, b = self._prof, self._pct_box.text().strip()
        if b.isdigit() and 0 <= int(b) <= 100:
            c.craft_pct[key] = int(b)
        elif key in c.craft_pct:
            c.craft_pct.pop(key, None)
        for key, box in self._bag_boxes.items():
            n = box.text().strip()
            if n.isdigit() and int(n) > 0:
                c.craft_bag[key] = int(n)
            else:
                c.craft_bag.pop(key, None)
        table = dict(self._settings["craft_exp_table"] or {})
        kb_exp = {e.level: e.exp for e in craftplan.exp_needs(self._kb, None)}
        for lv, box in self._exp_boxes.items():
            n = box.text().strip()
            if n.isdigit() and int(n) > 0 and int(n) != kb_exp.get(lv):
                table[str(lv)] = int(n)
            else:
                table.pop(str(lv), None)
        self._settings["craft_exp_table"] = table or None
        self._profiles.save()
        self._refresh_prof()
        if self._prof_mode == "teacher":
            self._fill_teacher()  # its quests' level chips follow the character level
        self._replan()

    # ------------------------------------------------------------ closing

    def _close_clicked(self, _=False) -> None:
        """The ✕: the setting off (the bar's Crafting button follows), hidden until switched back on."""
        self._settings[SHOW_KEY] = False
        self.hide()
        self.closed.emit()

    def hideEvent(self, e) -> None:
        for timer in (self._typing, self._bag_typing, self._rec_typing, self._edit):  # nothing fires once hidden
            timer.stop()
        if self.plan_window is not None:
            self.plan_window.hide()  # the plan goes with it (not the player's ✕: it opens again with it)
        if self._placed:  # hidden (the toolbar, Esc, the ✕): keep the place now, not 400 ms later
            self._geom.stop()
            self._remember()
        super().hideEvent(e)

    # ------------------------------------------------------------ place, move, resize

    def _place(self) -> None:
        """Where the window opens: where the player left it, when that is still on a screen (a monitor since
        unplugged: under the toolbar again)."""
        screens = [s.geometry() for s in QGuiApplication.screens()]
        saved = self._settings[GEOM_KEY]
        size = (
            mapview.clamp_size(saved["w"], saved["h"], screens, self.minimumSize())
            if isinstance(saved, dict) and isinstance(saved.get("w"), int) and isinstance(saved.get("h"), int)
            else QSize(self.width(), self.height())
        )
        spot = mapview.saved_spot(saved, size, screens)
        self.setGeometry(QRect(spot if spot is not None else self._default_spot(size), size))
        self._placed = True

    def _default_spot(self, size: QSize) -> QPoint:
        """Just under the toolbar (the bar's Crafting button opens this), kept on that screen; without one — the bar
        never placed, or gone — the primary screen's top-left corner."""
        primary = QGuiApplication.primaryScreen().availableGeometry()
        screens = [s.geometry() for s in QGuiApplication.screens()]
        under = self._under
        if isinstance(under, QRect) and not under.isNull():
            screen = next((g for g in screens if g.intersects(under)), primary)
            x = min(max(under.left(), screen.left()), max(screen.left(), screen.right() - size.width() + 1))
            y = min(max(under.bottom() + 1 + GAP, screen.top()), max(screen.top(), screen.bottom() - size.height() + 1))
            return QPoint(x, y)
        return primary.topLeft() + QPoint(12, 12)

    def _dock_plan(self) -> None:
        if self.plan_window is not None and self.plan_window.isVisible():
            self.plan_window.dock()  # the plan follows the main window

    def moveEvent(self, e) -> None:
        self._geom.start()
        self._dock_plan()
        super().moveEvent(e)

    def resizeEvent(self, e) -> None:
        self._geom.start()
        self._dock_plan()  # a left-edge drag moves the main window's left side
        self._place_recipe()
        super().resizeEvent(e)

    def _remember(self) -> None:
        if self._placed:
            self._settings[GEOM_KEY] = {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()}


class ForgePlanWindow(EdgeResize, QWidget):
    """The Forge plan, a window of its own docked beside the main one (its left, or its right where the screen has
    no room): the totals, what to farm first, the crafts in order. It never takes the keyboard from the game (its
    boxes and buttons still click), moves and hides with the main window, and its ✕ hides only it. The size the
    player drags it to is kept (craft_plan_size); until then it is PLAN_W wide and as tall as the plan, up to
    PLAN_H, the body scrolling past that."""

    def __init__(self, owner: CraftAdvisor):
        super().__init__(None, _flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)  # hovering the rim shows the resize cursor
        self.setMinimumSize(PLAN_MIN_W, PLAN_MIN_H)
        self._owner = owner
        self._fit_size = QSize()  # the size the window last gave itself (a resize to it isn't the player's)
        self._sized = QTimer(self, singleShot=True, interval=GEOM_DEBOUNCE_MS, timeout=self._resized)
        self._drawn_in = palette()  # the palette the plan was last drawn in (a step's muted aside is in its html)
        self.setLayoutDirection(owner.layoutDirection())
        self.setStyleSheet(owner.styleSheet())
        col = QVBoxLayout(self)
        col.setContentsMargins(SIDE, TOP, SIDE, BOTTOM)
        col.setSpacing(8)
        self._head = _Header()
        hrow = QHBoxLayout(self._head)
        hrow.setContentsMargins(0, 0, 0, 0)
        hrow.setSpacing(8)
        self._title = QLabel(objectName="Title")
        self._badge = QLabel(objectName="HeadBadge")
        self._close = QToolButton(objectName="Close", text=theme.SYMBOL_ICONS["close"])
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.setFocusPolicy(Qt.NoFocus)
        self._close.clicked.connect(lambda _=False: self.hide())
        hrow.addWidget(self._title)
        hrow.addWidget(self._badge, 1, Qt.AlignVCenter)
        hrow.addWidget(self._close, 0, Qt.AlignTop)
        col.addWidget(self._head)
        self._scroll, self._rows_lay = _scroller()
        self._rows_lay.setSpacing(8)
        col.addWidget(self._scroll, 1)
        self._retext_chrome()
        self.resize(self._saved_size() or QSize(PLAN_W, PLAN_H))

    # ------------------------------------------------------------ the owner's calls

    def redraw(self) -> None:
        """The plan drawn again (its scroll kept): a new plan, the language, the KB."""
        bar = self._scroll.verticalScrollBar()
        at = bar.value()
        _clear(self._rows_lay)
        self._draw()
        self._rows_lay.addStretch(1)
        self._fit()
        QTimer.singleShot(0, self, lambda: bar.setValue(at))
        if self.isVisible():
            self.dock()
            self.update()

    def show_beside(self) -> None:
        """Shown (or kept) docked beside the main window."""
        self.dock()
        if not self.isVisible():
            self.show()
        set_capturable(self, self._owner._settings)
        self.raise_()
        self.update()

    def dock(self) -> None:
        dock_beside(self, self._owner)

    def restyle(self, sheet: str) -> None:
        if sheet != self.styleSheet():
            self.setStyleSheet(sheet)
        if self._drawn_in != palette():
            self.redraw()  # another glass: the steps' muted asides, written into their html, drawn again in it
        self.update()  # the tint

    def apply_language(self, t: I18n) -> None:
        """The new language's direction and title; the owner's rebuild then draws the plan in it (a hidden plan is
        drawn when it next shows)."""
        self.setLayoutDirection(Qt.RightToLeft if t.rtl else Qt.LeftToRight)
        self._retext_chrome()

    def _retext_chrome(self) -> None:
        t, rtl = self._owner.t, self._owner.t.rtl
        self._title.setText(bidi.plain(t("cp_plan"), rtl))
        self._close.setAccessibleName(t("cp_plan_close"))
        self._close.setToolTip(t("cp_plan_close"))
        rows_side = (GUTTER if rtl else 0, 0, 0 if rtl else GUTTER, 0)
        self._rows_lay.setContentsMargins(*rows_side)

    # ------------------------------------------------------------ the plan

    def _add(self, w: QWidget) -> QWidget:
        self._rows_lay.addWidget(w)
        return w

    def _text(self, text: str, name: str = "Sub") -> QLabel:
        return self._add(_label(bidi.plain(text, self._owner.t.rtl), name, wrap=True))

    def _draw(self) -> None:
        self._drawn_in = palette()
        o = self._owner
        t = o.t
        c, plan = o._c, o._plan
        n = len(c.craft_targets) if c is not None else 0
        self._badge.setText(bidi.plain(t("cp_targets", n=n), t.rtl) if n else "")
        if c is None:
            self._text(t("cp_no_character"))
            return
        if not o._has_plan():
            key = "cp_plan_empty" if not n else "cp_plan_failed" if plan is None else "cp_plan_done"
            self._text(t(key))
            return
        self._add(self._totals(plan))
        self._farm(plan)
        self._order(plan)
        if plan.leftovers:
            pairs = _pieces((f"{name} ×{q}" for name, q in plan.leftovers), t.rtl)
            self._text(t("cp_leftover", list=pairs))
        self._notes(plan)

    def _totals(self, plan: Plan) -> QWidget:
        """The three totals in a row: crafting cost, craft actions, equip level — a big number over a small word."""
        t, rtl = self._owner.t, self._owner.t.rtl
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for value, word in (
            (_mesos(plan.cost), "cp_total_cost"),
            (f"{plan.crafts:,}", "cp_total_crafts"),
            (str(plan.equip_lv) if plan.equip_lv else "\u2014", "cp_equip_lv"),
        ):
            card = QFrame(objectName="StatCard")
            v = QVBoxLayout(card)
            v.setContentsMargins(12, 9, 12, 9)
            v.setSpacing(0)
            v.addWidget(_label(bidi.ltr_block(value, rtl), "BigNum"))
            v.addWidget(_label(bidi.plain(t(word), rtl), "CardLabel", wrap=True))
            h.addWidget(card, 1)
        return box

    def _farm(self, plan: Plan) -> None:
        """1 · Farm these first: what is still missing, the total in brackets when the bag covers some, where each
        comes from; then what the bag gives."""
        t, rtl = self._owner.t, self._owner.t.rtl
        self._text(t("cp_farm"), "Section")
        farm = [f for f in plan.farm if f.farm > 0]
        if farm:
            self._text(t("cp_farm_hint"), "Note")
            for f in farm:
                self._add(self._farm_row(f))
        else:
            self._text(t("cp_farm_none"))
        if plan.bag_used:
            pairs = _pieces((f"{name} ×{q}" for name, q in plan.bag_used), rtl)
            self._text(t("cp_from_bag", list=pairs))

    def _farm_row(self, f: FarmItem) -> QWidget:
        """One raw mat to farm: its picture, its name and kind, its top droppers or the NPC selling it under them,
        and how many are still missing big on the end."""
        o = self._owner
        t, rtl = o.t, o.t.rtl
        row = QFrame(objectName="FarmRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)
        h.addWidget(o._pics.label(f.key, PIC), 0, Qt.AlignTop)
        mid = QVBoxLayout()
        mid.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(_label(bidi.ltr_name(f.name, rtl), "ItemName"))
        top.addWidget(_label(bidi.plain(t(KIND_KEYS.get(f.category, "cp_kind_other")), rtl), "Kind"), 1)
        mid.addLayout(top)
        bits = []
        if f.droppers:
            # each dropper whole ("Snail (Lv. 1)"): the line wraps between them, never between a name and its level
            drops = " · ".join(
                f"{bidi.ltr_block(m.replace(' ', NBSP), rtl)}{NBSP}({t('lv_short', n=lv).replace(' ', NBSP)})"
                for m, lv in f.droppers
            )
            bits.append(t("cp_drops_from", list=drops))
        if f.sellers:
            npc, place, price = f.sellers[0]
            bits.append(t("cp_buy_at", who=_pieces((npc, place, _mesos(price)), rtl, " · ")))
        if f.price is None and not f.droppers:
            bits.append(t("cp_no_price"))
        for bit in bits:
            mid.addWidget(_label(bidi.plain(bit, rtl), "Muted", wrap=True))
        h.addLayout(mid, 1)
        end = QVBoxLayout()
        end.setSpacing(0)
        end_align = Qt.AlignRight | Qt.AlignTop
        end.addWidget(_label(bidi.ltr_block(_mesos(f.farm), rtl), "FarmCount", align=end_align))
        if f.bag > 0:
            total = t("cp_farm_total", n=bidi.ltr_block(_mesos(f.need), rtl))
            end.addWidget(_label(bidi.plain(f"({total})", rtl), "Note", align=end_align))
        end.addStretch(1)
        h.addLayout(end)
        return row

    def _order(self, plan: Plan) -> None:
        """2 · Then craft in this order: how recipe variants are picked, then each stage as a card."""
        o = self._owner
        t, rtl = o.t, o.t.rtl
        self._text(t("cp_order"), "Section")
        mode = Segmented([(t(key), m) for m, key in MODE_KEYS], o._mode, rtl)
        mode.set_label(t("cp_mode_tip"))
        mode.setToolTip(t("cp_mode_tip"))
        for b in mode.group.buttons():
            b.setFocusPolicy(Qt.NoFocus)
        mode.changed.connect(o._mode_set)
        self._add(mode)
        stages = [st for st in plan.stages if st.steps]
        for i, st in enumerate(stages, 1):
            self._add(self._stage(i, st))

    def _stage(self, no: int, st: Stage) -> QWidget:
        """A stage's card: "Stage N", its kind's badge and "N crafts · X mesos" on top, its title, a level-up's reason
        and EXP, then its numbered steps."""
        o = self._owner
        t, rtl = o.t, o.t.rtl
        card = QFrame(objectName="Stage")
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 6)
        v.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(_label(bidi.plain(t("cp_stage_no", n=no), rtl), "StageNo"))
        top.addWidget(_label(bidi.plain(t(BADGE_KEYS[st.kind]), rtl), f"Kind{st.kind.title()}"))
        top.addStretch(1)
        fee = t("cp_free") if st.fee == 0 else t("cp_mesos", n=bidi.ltr_block(_mesos(st.fee), rtl))
        top.addWidget(_label(bidi.plain(f"{t('cp_crafts', n=st.crafts)} · {fee}", rtl), "StageMeta"))
        v.addLayout(top)
        v.addWidget(_label(self._stage_title(st), "StageTitle", wrap=True))
        for line in self._stage_lines(st):
            v.addWidget(_label(bidi.plain(line, rtl), "Muted", wrap=True))
        for i, s in enumerate(st.steps, 1):
            v.addWidget(self._step(i, s))
        return card

    def _stage_title(self, st: Stage) -> str:
        t, rtl = self._owner.t, self._owner.t.rtl
        if st.kind == "level":
            # the discipline and its levels one Latin block: as two islands a Hebrew line swapped their ends
            return bidi.plain(
                t("cp_stage_level", lv=bidi.ltr_block(f"{st.discipline} {st.level_from} → {st.level_to}", rtl)), rtl
            )
        if st.kind == "prep":
            return bidi.plain(t("cp_stage_prep"), rtl)
        finals = [s for s in st.steps if s.final]
        if len(finals) == 1:
            return bidi.plain(t("cp_stage_final_name", name=bidi.ltr_block(finals[0].name, rtl)), rtl)
        return bidi.plain(t("cp_stage_final", n=len(finals)), rtl)

    def _stage_lines(self, st: Stage) -> list[str]:
        """The muted lines under a stage's title: a level-up's reason (or what blocks it) and its recipe's EXP; the
        other stages' professions."""
        t, rtl = self._owner.t, self._owner.t.rtl
        if st.kind != "level":
            return [_pieces(st.disciplines, rtl, " · ")] if st.disciplines else []
        if st.blocked.startswith("char:"):
            return [t("cp_blocked_char", b=bidi.ltr_block(st.blocked.split(":", 1)[1], rtl))]
        if st.blocked == "exp":
            return [t("cp_blocked_exp")]
        lines = [f"{t('cp_needed_next')} · {t('cp_level_fees', n=bidi.ltr_block(_mesos(st.fee), rtl))}"]
        lift = next((s for s in st.steps if s.level_up), None)
        if lift is not None and st.exp_each:
            lines.append(f"{bidi.ltr_block(lift.name, rtl)} · {t('cp_exp_step', exp=st.exp_each)}")
        return lines

    def _step(self, i: int, s: Step) -> QWidget:
        """One craft: its number, the tick box (ticking it moves its mats and products into the bag), the product's
        picture, "13× Bronze Ingot" (what one craft makes muted beside it), the ingredients under it, the fee on the
        end and Swap when the product has more than one recipe."""
        o = self._owner
        t, rtl = o.t, o.t.rtl
        row = QFrame(objectName="Step")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 8, 0, 8)
        h.setSpacing(8)
        h.addWidget(_label(bidi.plain(f"{i}.", rtl), "StepNo"), 0, Qt.AlignTop)
        box = QCheckBox()
        box.setCursor(Qt.PointingHandCursor)
        box.setFocusPolicy(Qt.NoFocus)
        box.setToolTip(t("cp_step_tip"))
        box.setAccessibleName(t("cp_step_tip"))
        box.toggled.connect(lambda on, s=s: o._ticked(s, on))
        h.addWidget(box, 0, Qt.AlignTop)
        h.addWidget(o._pics.label(s.key or o._key_of(s.name), STEP_PIC), 0, Qt.AlignTop)
        mid = QVBoxLayout()
        mid.setSpacing(2)
        # "13× Bronze Ingot (makes 10)": one label, the aside muted in it — two labels side by side wrapped the name
        # early ("104× Processed" / "Parchment": a wrapping label's own width hint is short of its text)
        name = escape(bidi.ltr_name(f"{s.crafts}× {s.name}", rtl))
        if s.makes > 1:
            aside = escape(bidi.plain(f"({t('cp_makes', n=s.makes)})", rtl))
            name += f' <span style="color:{palette().muted}; font-size:12px; font-weight:400">{aside}</span>'
        title = _label(name, "StepName", wrap=True)
        title.setTextFormat(Qt.RichText)
        mid.addWidget(title)
        line = _pieces([f"{s.discipline} {s.prof_lv}"], rtl)
        if s.ingredients:
            line += " · " + _pieces((f"{ing.qty * s.crafts} {ing.name}" for ing in s.ingredients), rtl)
        mid.addWidget(_label(bidi.plain(line, rtl), "Muted", wrap=True))
        if s.optional:
            opts = _pieces((f"{ing.qty} {ing.name}" for ing in s.optional), rtl)
            mid.addWidget(_label(bidi.plain(f"{t('cp_optional')}: {opts}", rtl), "Note", wrap=True))
        h.addLayout(mid, 1)
        end = QVBoxLayout()
        end.setSpacing(4)
        fee = t("cp_free") if s.fee_total == 0 else bidi.ltr_block(_mesos(s.fee_total), rtl)
        end.addWidget(_label(bidi.plain(fee, rtl), "Fee", align=Qt.AlignRight | Qt.AlignTop), 0, Qt.AlignRight)
        if len(craftplan.recipes(o._kb).get(s.name.casefold(), ())) > 1:
            swap = QPushButton(bidi.plain(t("cp_swap"), rtl), objectName="Swap")
            swap.setCursor(Qt.PointingHandCursor)
            swap.setFocusPolicy(Qt.NoFocus)
            swap.setToolTip(t("cp_swap_tip"))
            swap.clicked.connect(lambda _=False, s=s: o._swap(s))
            end.addWidget(swap, 0, Qt.AlignRight)
        end.addStretch(1)
        h.addLayout(end)
        return row

    def _notes(self, plan: Plan) -> None:
        """The muted footer: the raw mats no NPC sells (counted at 0 mesos), recipe loops, how level-ups are picked."""
        t, rtl = self._owner.t, self._owner.t.rtl
        unpriced = [arg for code, arg in plan.notes if code == "no_price"]
        if unpriced:
            self._text(t("cp_note_unpriced", list=_pieces(unpriced, rtl)), "Note")
        for code, arg in plan.notes:
            if code == "cycle":
                self._text(t("cp_note_cycle", name=bidi.ltr_block(arg, rtl)), "Note")
        if any(st.kind == "level" and st.steps for st in plan.stages):
            self._text(t("cp_note_levelups"), "Note")

    # ------------------------------------------------------------ the panel

    def paintEvent(self, e) -> None:
        _paint_glass(self, self._owner._opacity)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._owner._retext_plan_btn()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._owner._retext_plan_btn()

    def _saved_size(self) -> QSize | None:
        """The size the player dragged the window to (craft_plan_size), kept inside the screens; None: never."""
        saved = self._owner._settings[PLAN_SIZE_KEY]
        if not (isinstance(saved, dict) and isinstance(saved.get("w"), int) and isinstance(saved.get("h"), int)):
            return None
        screens = [s.availableGeometry() for s in QGuiApplication.screens()]
        return mapview.clamp_size(saved["w"], saved["h"], screens, QSize(PLAN_MIN_W, PLAN_MIN_H))

    def _fit(self) -> None:
        """The player's size when they resized it (the body scrolls inside); else PLAN_W wide and as tall as the plan
        up to PLAN_H."""
        size = self._saved_size()
        if size is None:
            inner = PLAN_W - 2 * SIDE
            head = self._need(self._head, inner)
            body = self._need(self._rows_lay, inner - SCROLLBAR_W - GUTTER)
            size = QSize(PLAN_W, max(PLAN_MIN_H, min(PLAN_H, TOP + BOTTOM + 8 + head + body)))
        self._fit_size = size
        if self.size() != size:
            self.resize(size)

    @staticmethod
    def _need(item, width: int) -> int:
        """The height a widget or layout needs at this width: the wrapped way when it has one, else its hint."""
        h = item.heightForWidth(width)
        return h if h >= 0 else item.sizeHint().height()

    def resizeEvent(self, e) -> None:
        """The player dragging an edge: kept once it settles (_resized). The window's own sizing (_fit), and the
        resize Qt sends when it first shows, are not theirs."""
        if self.isVisible() and e.size() != self._fit_size:
            self._sized.start()
        super().resizeEvent(e)

    def _resized(self) -> None:
        """A drag settled: its size kept, and docked beside the main window again (a left-edge drag pulled its right
        side off it)."""
        self._owner._settings[PLAN_SIZE_KEY] = {"w": self.width(), "h": self.height()}
        self._fit_size = self.size()
        if self.isVisible():
            self.dock()
