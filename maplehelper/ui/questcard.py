"""A quest as a card on the glass, the same in the Quests and the Citizenship windows (ui/questtool.py,
ui/citizenship.py), ported from the old Play tools' quest card and made for the glass:

- who gives it (their picture, large on hover; the NPC a link to their page in the toolbar's search), where, its level
  (the one it can be finished at: taken at 12 but done at 32 is a Lv. 32 quest), its EXP, Daily / Weekly (and when one
  marked done is back on the list), who it is finished with when that is someone else;
- the questline it is on (quests.chain_of): "Step 8 of 11 · Next: Maya's Second Collection", opening to the whole
  line, each step done, to do now or locked and why (quests.progress), a split's lines under it; a click on a step
  shows that quest (in this window, or the other one for a Citizenship quest); what it opens off its line;
- what to do (quests.task_text, in the UI's language), what it needs (each monster and item a link to its page) and
  who drops each item: the three droppers nearest the character's level, how each sits against it, the rest behind
  "Show all N", a link to the Farm window on it; one another quest hands over, that quest and its NPC a tap away;
  a crafted one, its recipes;
- what it gives: EXP, mesos, Fame and items (each a link to its page), the class's own pick, a random set, a
  gender's;
- what it asks first ("Opens once you finish X", a tap away), a level to finish it, a citizenship grade, a profession
  level, Fame, a fee and any other line of its page;
- Mark done / Back to the list (Character.quests_done, cycle_done; saved). Marking a step done whose earlier steps
  aren't marked offers to mark them too: the game lets no step be done before them.

A card lives in a QuestWindow (below: what both windows share around their cards, each setting open_quest(key) for
a step or a prerequisite clicked). card_qss() is the style a window adds to its own (extra_qss)."""
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import quote, unquote

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QToolTip, QVBoxLayout, QWidget

from .. import availability, bidi, crafting, dates, farm, glossary, quests
from ..quests import Quest
from . import terms
from .controls import FlowLayout
from .gamesearch import rim
from .npcoverlay import accent_of, ink, palette
from .toolwindow import NAV, _rgba
from .widgets import fit_picture, zoom_on_hover

MAX_QUESTS = 40         # cards a list makes before "Show more quests" (the cut ones are the lowest EXP)
DROPPERS_SHOWN = 3      # an item's droppers shown before "Show all N": the nearest the character's level
PIC_W, PIC_H = 52, 60   # the giver's picture
THING_PX = 22           # a monster's or an item's picture in a line of text
STEP_DOT = 18           # a chain step's number in its circle
BRANCH_INDENT = 14      # each split before a step moves it in this much
DONE_FADE = 0.6         # a done quest's card: there, but not something to do
SCROLL_TO_MS = 60       # after the cards are laid out (and the fill's keep-the-place): the lit card in view
SCROLL_MARGIN = 8       # above the lit card's top
# readable on every dark glass tint, darkened by ink() on the white one
GOOD, WARN = "#4CD07D", "#FFB547"
CHEVRON = {False: "\u25be", True: "\u25b4"}      # ▾ the chain to open, ▴ to close
CHECK = "\u2713"
_THING = re.compile(r"(Defeat |Collect )?(.+?) x ([\d,]+)( \([\d.]+%\))?( \(.+\))?")
_SLOT = "\ue000"        # holds a link's place in a sentence while the sentence is escaped


def card_qss(settings) -> str:
    """The card's own style names, added to its window's (extra_qss): the EXP chip, the chain strip and its steps,
    the offer to mark the earlier steps, a list's level or grade chips, the progress bar of a chain."""
    p = palette()
    fill, on_fill = accent_of(settings)
    lit, good = ink(fill), ink(GOOD)
    chip = "border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700;"
    return f"""
QLabel#ChipGood {{ color: {good}; background: {_rgba(good, 0.15)}; {chip} }}
#Detail {{ color: {p.text}; font-size: 12px; }}
QFrame#ChainStrip {{ background: {_rgba(fill, 0.10)}; border: none; border-radius: 8px; }}
QFrame#ChainStrip:hover {{ background: {_rgba(fill, 0.18)}; }}
#ChainStep {{ color: {lit}; font-size: 12px; font-weight: 700; }}
#ChainNext {{ color: {p.text}; font-size: 12px; }}
#Chevron {{ color: {lit}; font-size: 12px; font-weight: 700; }}
QWidget#ChainList {{ background: {rim(0.05, p)}; border-radius: 8px; }}
QLabel#StepDot {{ border-radius: {STEP_DOT // 2}px; font-size: 10px; font-weight: 700; }}
QLabel#StepDot[state="done"] {{ background: {_rgba(good, 0.22)}; color: {good}; }}
QLabel#StepDot[state="open"] {{ background: {fill}; color: {on_fill}; }}
QLabel#StepDot[state="locked"] {{ background: transparent; color: {p.muted}; border: 1px solid {rim(0.28, p)}; }}
#StepName {{ color: {p.text}; font-size: 12px; }}
#StepName[state="done"] {{ color: {p.muted}; }}
#StepThis {{ color: {p.text}; font-size: 12px; font-weight: 700; }}
#StepLv {{ color: {p.muted}; font-size: 11px; font-weight: 600; }}
#StepLv[high="true"] {{ color: {ink(WARN)}; }}
#StepWhy, #StepSplit {{ color: {p.muted}; font-size: 11px; }}
QFrame#Offer {{ background: {_rgba(fill, 0.10)}; border: 1px solid {_rgba(fill, 0.45)}; border-radius: 8px; }}
QPushButton#LevelChip {{ background: {rim(0.08, p)}; color: {p.text}; border: none; border-radius: 7px;
                         padding: 2px 9px; min-height: 0; font-size: 11px; font-weight: 600; }}
QPushButton#LevelChip:hover {{ background: {p.fill2}; }}
QPushButton#LevelChip:checked {{ background: {fill}; color: {on_fill}; font-weight: 700; }}
QProgressBar#ChainBar {{ background: {rim(0.10, p)}; border: none; border-radius: 3px; max-height: 6px;
                         min-height: 6px; }}
QProgressBar#ChainBar::chunk {{ background: {fill}; border-radius: 3px; }}
"""


def _side(rtl: bool) -> str:
    return "dir='rtl' align='right'" if rtl else "dir='ltr' align='left'"


_badges: dict[str, str] = {}


def _badge(color: str) -> str:
    """The glossary's "?" badge (terms._badge_uri) in this colour, drawn once."""
    if color not in _badges:
        _badges[color] = terms._badge_uri(color, terms.BADGE_PX) or ""
    return _badges[color]


# ------------------------------------------------------------------ pictures and names (ported from Play tools)

def picture_uri(kb, kind: str, name: str) -> str | None:
    """The KB picture of an NPC / item / monster by its name, as a file URI ("Arrows for Bows x 500": the item)."""
    n = name.strip().lower()
    if kind == "npc":
        key = kb.npc_key(name)
    elif kind == "item":
        key = kb._item_by_name.get(n)
    else:
        key = next(iter(kb.monster_keys(name)), None)
    path = kb.picture(key) if key else None
    if not path and re.search(r" x ?[\d,]+$", n):
        return picture_uri(kb, kind, re.sub(r" x ?[\d,]+$", "", name.strip()))
    return Path(path).resolve().as_uri() if path else None


def journal_npc(kb, q: Quest) -> str:
    """The first NPC a quest's page names ("Arthur, the Town Clerk I met at Henesys Town Hall")."""
    for name in re.findall(r"[A-Z][\w'.]+(?: [A-Z][\w'.]+)*", kb.page(q.key).split("NPC Dialogue")[0]):
        for n in (name, name.split(" ")[0]):
            if kb._npc_by_name.get(n.lower()):
                return n
    return ""


def finish_with(kb, q: Quest) -> str:
    """Who a quest is finished with, when that's not who gives it: its page's "Turn in", else (a quest that starts on
    its own) the NPC its journal names."""
    if q.turn_in and q.turn_in != q.npc:
        return q.turn_in
    if q.self_start or not q.npc:
        return journal_npc(kb, q)
    return ""


def quest_picture(kb, q: Quest) -> str | None:
    """The quest's NPC, or the quest picture when the KB names none ("To Henesys" showed a blank)."""
    for name in (q.npc, journal_npc(kb, q) if not q.npc or not kb.npc_key(q.npc) else ""):
        key = kb.npc_key(name) if name else None
        path = kb.picture(key) if key else None
        if path:
            return str(path)
    from ..kb import FALLBACK_DIR
    path = FALLBACK_DIR / "quest.png"
    return str(path) if path.exists() else None


def quest_town(kb, q: Quest) -> str:
    """The town a quest is in: its NPC's, its citizenship town, else its area (not "Citizenship" or "Crafting")."""
    npc = kb.npc_key(q.npc) if q.npc else None
    return ((crafting._town(kb, npc) if npc else "") or quests.town_of(kb, q)
            or (q.area if q.area not in ("Citizenship", "Crafting") else ""))


def quest_name(kb, key: str) -> str:
    return (kb.get(key) or {}).get("name", key)


def whole_name(name: str, rtl: bool) -> str:
    """A name inside a sentence: one left-to-right block in a Hebrew one (bidi.ltr_block), and a short one never
    wraps inside ("Maya's Second" / "Collection", "To Henesys, the Prairie" / "Town" over two lines): it goes to the
    next line whole."""
    return bidi.ltr_block(name.replace(" ", "\u00a0") if len(name) <= bidi.KEEP_TOGETHER else name, rtl)


# ------------------------------------------------------------------ the card

class _Press(QFrame):
    """A frame that clicks (the chain strip)."""

    clicked = Signal()

    def __init__(self, name: str):
        super().__init__(objectName=name)
        self.setAttribute(Qt.WA_Hover, True)          # its QSS :hover
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class QuestCard(QFrame):
    """One quest (the module's docstring). done: a quest marked done (muted, with Back to the list); lit: the one the
    window was opened on. key, chain (quests.Chain or None), state (quests.ChainState or None), strip (the chain strip
    or None), chain_box (the open chain's steps or None), act (Mark done / Back to the list), offer (the offer to mark
    the earlier steps, while it shows) are read by the tests."""

    def __init__(self, win, q: Quest, done: bool = False, lit: bool = False):
        super().__init__(objectName="Card")
        self.win, self.q, self.key, self.done = win, q, q.key, done
        self._kb, self.t = win._kb, win.t
        self._link = ink(accent_of(win._settings)[0])
        if lit:
            self.setProperty("lit", True)
        c = win.character
        self.chain = quests.chain_of(self._kb, q.key, c.base_class, c.job) if c else None
        self.state = (quests.progress(self._kb, self.chain, c.level, c.quests_done, c.crafts or None)
                      if self.chain and c else None)
        self.strip: _Press | None = None
        self.chain_box: QWidget | None = None
        self.offer: QFrame | None = None
        self._expanded: set[str] = set()        # the needed items whose every dropper shows
        self._droppers: QLabel | None = None
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(12)
        outer.addWidget(self._picture(), 0, Qt.AlignTop)
        self.col = QVBoxLayout()
        self.col.setSpacing(6)
        outer.addLayout(self.col, 1)
        self._head()
        if self.chain is not None:
            self._strip()
        self._opens()
        self._body()
        self._acts_box = QWidget()
        self._acts = QHBoxLayout(self._acts_box)
        self._acts.setContentsMargins(0, 2, 0, 0)
        self._acts.setSpacing(16)       # the link has no padding of its own: apart from the button
        self.col.addWidget(self._acts_box)
        self._actions()
        if done:
            fade = QGraphicsOpacityEffect(self)
            fade.setOpacity(DONE_FADE)
            self.setGraphicsEffect(fade)

    # ------------------------------------------------------------ pieces

    def _rich(self, text: str, name: str = "Detail") -> QLabel:
        """A rich-text label whose links act (_go) and whose pictures show large on hover."""
        lb = QLabel(text, objectName=name)
        lb.setTextFormat(Qt.RichText)
        lb.setWordWrap(True)
        lb.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        lb.linkActivated.connect(self._go)
        lb.linkHovered.connect(lambda href, w=lb: self._hover(href, w))
        return lb

    def _a(self, href: str, text: str) -> str:
        return f"<a href='{href}' style='color:{self._link}; text-decoration:none'>{text}</a>"

    def _caption(self, key: str) -> QLabel:
        """A section's heading inside the card: the key's words without their colon."""
        return self.win.caption(self.t(key).rstrip().rstrip(":"))

    def _hover(self, href: str, lb: QLabel) -> None:
        if href.startswith("zoom:"):
            QToolTip.showText(QCursor.pos(), f"<img src='{href[5:]}' height='96'>", lb)
        else:
            QToolTip.hideText()

    def _go(self, href: str) -> None:
        """A link in the card: a page in the toolbar's search, the Farm window, a quest, or every dropper of an item."""
        kind, _, arg = href.partition(":")
        arg = unquote(arg)
        if kind == "npc":
            NAV.npc_requested.emit(arg)
        elif kind == "monster":
            NAV.monster_requested.emit(arg)
        elif kind == "item":
            NAV.item_requested.emit(arg)
        elif kind == "farm":
            NAV.tool_requested.emit("farm_tool", arg)
        elif kind == "quest":
            self.win.open_quest(arg)
        elif kind == "all" and self._droppers is not None:
            self._expanded.add(arg)
            self._droppers.setText(self._droppers_html())
            self.win.settle()

    def _picture(self) -> QLabel:
        pic = QLabel(objectName="QuestPic")
        pic.setFixedSize(PIC_W, PIC_H)
        pic.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        path = quest_picture(self._kb, self.q)
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                pic.setPixmap(fit_picture(pm, PIC_W, PIC_H, pic))
                zoom_on_hover(pic, path)
        return pic

    def _thing(self, text: str) -> str:
        """ "Defeat Blue Snail x 10" / "Red Potion x 20" -> its picture and its name (a link to its page), one
        left-to-right block that never wraps inside; a note in the UI's language after it ("(male character)")."""
        m = _THING.fullmatch(text.strip())
        if not m:
            return html.escape(text)
        verb, name, n, odds, note = m.groups()
        n += odds or ""
        kb = self._kb
        kind = "monster" if verb == "Defeat " else "item"
        uri = picture_uri(kb, kind, name) or picture_uri(kb, "item" if kind == "monster" else "monster", name)
        img = (f"<a href='zoom:{uri}' style='text-decoration:none'><img src='{uri}' height='{THING_PX}' "
               f"style='vertical-align: middle'></a>&nbsp;") if uri else ""
        key = next(iter(kb.monster_keys(name)), None) if kind == "monster" else kb._item_by_name.get(name.lower())
        shown = self._a(f"{kind}:{key}", html.escape(name)) if key else html.escape(name)
        return (f"<span style='white-space: nowrap'>{bidi.LRE}{img}{shown} x{html.escape(n)}{bidi.PDF}{bidi.RLM}"
                f"</span>{html.escape(note or '')}")

    def _things(self, things: list[str]) -> QLabel:
        """One thing a line, each picture beside its own name."""
        side = _side(self.t.rtl)
        return self._rich("".join(f"<p {side} style='margin:0 0 3px 0;'>{self._thing(x)}</p>" for x in things))

    def _flow(self, things: list[str]) -> QWidget:
        """Things side by side, wrapping between them, never inside one (a quest's seven return scrolls, one a line,
        filled the window: TOOL-06)."""
        box = QWidget()
        flow = FlowLayout(box, spacing=12, line_spacing=3)
        for x in things:
            flow.addWidget(self._rich(f"<p {_side(self.t.rtl)} style='margin:0'>{self._thing(x)}</p>"))
        return box

    def _chip(self, text: str, name: str = "Chip", tip: str = "") -> QLabel:
        lb = QLabel(bidi.plain(text, self.t.rtl), objectName=name)
        if tip:
            lb.setToolTip(tip)
            lb.setAccessibleDescription(tip)
        return lb

    def _chips(self, chips: list[QLabel]) -> QWidget:
        box = QWidget()
        flow = FlowLayout(box, spacing=4, line_spacing=4)
        for lb in chips:
            flow.addWidget(lb)
        return box

    # ------------------------------------------------------------ the head

    def _head(self) -> None:
        t, rtl, q, kb = self.t, self.t.rtl, self.q, self._kb
        top = QHBoxLayout()
        top.setSpacing(8)
        # an English name is one block: "[Construction Site B1] Shumi's Lost Coin" keeps its brackets in place
        name = QLabel(bidi.ltr_name(q.name, rtl), objectName="CardTitle")
        name.setWordWrap(True)
        top.addWidget(name, 1)
        top.addWidget(self._chip(t("lv_short", n=q.opens_at())), 0, Qt.AlignTop)
        self.col.addLayout(top)
        # where, and how it is taken: an NPC (a link to their page), the board, or on its own
        side = _side(rtl)
        board = (q.npc or "").startswith("Community Board")
        if q.self_start or not q.npc:
            who = html.escape(t("q_self_start"))
        elif board:
            who = html.escape(t("q_from_board"))
        else:
            npc = kb.npc_key(q.npc)
            shown = f"{bidi.LRE}{html.escape(q.npc)}{bidi.PDF}"
            who = html.escape(t("q_from_npc", npc=_SLOT)).replace(
                _SLOT, self._a(f"npc:{npc}", shown) if npc else shown)
        town = quest_town(kb, q)
        where = f"{bidi.LRE}{html.escape(town)}{bidi.PDF} · " if town else ""
        lines = [f"<p {side} style='margin:0'>{where}{who}</p>"]
        end = finish_with(kb, q)
        if end:
            key = kb.npc_key(end)
            role = re.search(r"^(Town Clerk|City Clerk)$", kb.page(key), re.M) if key else None
            shown = f"{bidi.LRE}{html.escape(end)}{bidi.PDF}"
            text = (self._a(f"npc:{key}", shown) if key else shown) + (f", {html.escape(t('q_role_clerk'))}" if role
                                                                      else "")
            lines.append(f"<p {side} style='margin:2px 0 0 0'>{html.escape(t('q_finish_head'))} {text}</p>")
        self.col.addWidget(self._rich("".join(lines), "CardSub"))
        chips = []
        if q.exp:
            chips.append(self._chip(f"+{q.exp:,} EXP", "ChipGood"))
        if q.cycle:
            # the page's "Daily" / "Weekly"; the KB names no reset time, the tip says so
            chips.append(self._chip(t(f"q_{q.cycle}"), "ChipOn", t(f"q_{q.cycle}_tip")))
        c = self.win.character
        when = (c.cycle_done or {}).get(q.key) if self.done and q.cycle and c else None
        if isinstance(when, (int, float)):
            from datetime import datetime
            back = datetime.fromtimestamp(quests.back_at(q.cycle, when))
            chips.append(self._chip(t("q_back_at", when=dates.day(back, rtl)), "ChipOn"))
        if chips:
            self.col.addWidget(self._chips(chips))

    # ------------------------------------------------------------ the questline

    def _strip(self) -> None:
        """ "Step 8 of 11 · Next: Maya's Second Collection ▾": a click opens the whole line under it."""
        t, rtl, chain = self.t, self.t.rtl, self.chain
        n, total = chain.at(self.key)
        nexts = chain.nexts.get(self.key, [])
        name = quest_name(self._kb, nexts[0]) if len(nexts) == 1 else ""
        then = (t("qt_chain_next", name=_SLOT) if name else t("qt_step_split", n=len(nexts)) if nexts
                else t("qt_step_last"))
        step = t("qt_step", n=n, total=total)
        self.strip = _Press("ChainStrip")
        self.strip.setToolTip(t("qt_chain_tip"))
        self.strip.setAccessibleName(f"{step} · {then.replace(_SLOT, name)}")
        h = QHBoxLayout(self.strip)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(8)
        then_html = html.escape(then).replace(_SLOT, html.escape(whole_name(name, rtl)))
        line = QLabel(f"<p {_side(rtl)} style='margin:0'><span style='color:{self._link}; font-weight:700'>"
                      f"{html.escape(step)}</span>&nbsp; · &nbsp;{then_html}</p>", objectName="ChainNext")
        line.setTextFormat(Qt.RichText)
        line.setWordWrap(True)
        line.setAttribute(Qt.WA_TransparentForMouseEvents)      # the strip takes the click
        h.addWidget(line, 1)
        self._chevron = QLabel(objectName="Chevron")
        self._chevron.setAttribute(Qt.WA_TransparentForMouseEvents)
        h.addWidget(self._chevron, 0, Qt.AlignTop)
        self.strip.clicked.connect(self.toggle_chain)
        self.col.addWidget(self.strip)
        self._show_chain(self.key in self.win.open_chains)

    def toggle_chain(self) -> None:
        """The strip clicked: the line opens or closes (and stays so when the window fills again)."""
        on = self.key not in self.win.open_chains
        if on:
            self.win.open_chains.add(self.key)
        else:
            self.win.open_chains.discard(self.key)
        self._show_chain(on)
        self.win.settle()

    def _show_chain(self, on: bool) -> None:
        self._chevron.setText(CHEVRON[on])
        if on and self.chain_box is None:
            self.chain_box = chain_list(self.win, self.chain, self.state, self.key)
            self.col.insertWidget(self.col.indexOf(self.strip) + 1, self.chain_box)
        if self.chain_box is not None:
            self.chain_box.setVisible(on)

    def _opens(self) -> None:
        """What finishing it opens off its own line (First Greeting with Maya opens An Unknown Savior, a step of
        Maya's line): each a tap away, the quests in the game that fit the character. The steps of its own line are
        the strip's."""
        kb, t, rtl = self._kb, self.t, self.t.rtl
        c = self.win.character
        open_ = availability.of(kb)
        keys = [k for k in quests.opens(kb, self.key)
                if (self.chain is None or k not in self.chain) and open_.quest_open(k) and (q := quests.quest(kb, k))
                and (not c or quests.job_fits(q, c.base_class, c.job))]
        if not keys:
            return
        names = ", ".join(self._a(f"quest:{quote(k)}", html.escape(whole_name(quest_name(kb, k), rtl)))
                          for k in keys[:3])
        text = html.escape(t("qt_opens", names=_SLOT)).replace(_SLOT, names)
        self.col.addWidget(self._rich(f"<p {_side(rtl)} style='margin:0'>{text}</p>", "Hint"))

    # ------------------------------------------------------------ what to do, need and get

    def _body(self) -> None:
        t, rtl, q = self.t, self.t.rtl, self.q
        if q.task and not q.needs:
            # what to do when there is nothing to bring: the game's own quest journal, in Hebrew when translated
            task = quests.task_text(q, t.lang, self._kb)
            self.col.addWidget(self._caption("q_task_head"))
            if task != q.task or not rtl:
                lb = self.win.label(task, "Detail", wrap=True)
            else:
                # the English journal in the Hebrew window: a left-to-right paragraph, on the right
                lb = self._rich(f"<p dir='ltr' align='right' style='margin:0'>{html.escape(task)}</p>")
            self.col.addWidget(lb)
        if q.needs:
            # the whole list, nothing cut ("and 2 more" hid what was needed and who drops it: the owner)
            self.col.addWidget(self._caption("q_needs_head"))
            self.col.addWidget(self._things(q.needs))
            text = self._droppers_html()
            if text:
                self.col.addWidget(self._caption("q_droppers_head"))
                self._droppers = self._rich(text)
                self.col.addWidget(self._droppers)
        chips = [self._chip(f"{q.mesos:,} mesos")] if q.mesos else []
        if q.fame:
            chips.append(self._chip(f"+{q.fame} Fame"))
        if chips or q.rewards:
            self.col.addWidget(self._caption("q_gets_head"))
            if chips:
                self.col.addWidget(self._chips(chips))
            if q.rewards:
                self.col.addWidget(self._flow(q.rewards))
        # "Pick one (class-specific)": the player's own class's choices (and "Any Class"), not the first class listed
        c = self.win.character
        base = c.base_class if c else ""
        for head, things in (("q_pick_head", q.rewards_pick(base)), ("q_random_head", q.rewards_random(base))):
            if things:
                self.col.addWidget(self._caption(head))
                self.col.addWidget(self._flow(things))
        # a reward that depends on the character's gender: both listed, each marked (the profile has no gender)
        by_gender = q.rewards_gender(t)
        if by_gender:
            self.col.addWidget(self._caption("q_gender_head"))
            self.col.addWidget(self._things(by_gender))
        self._prerequisites()

    def _droppers_html(self) -> str:
        """Item by item: its name (its page) and the Farm window on it, then the monsters that drop it, the three
        nearest the character's level first, each with how it sits against the level (the Farm window's words), the
        rest behind "Show all N" (Iron Ingot listed nine monsters from Lv 2 to Lv 40: TOOL-06); the quest that hands
        it over, a tap away (_from_quest_html); or the recipes that make it ("Smithing Lv. 3: 10 x Tree Branch")."""
        kb, t, rtl = self._kb, self.t, self.t.rtl
        c = self.win.character
        side = _side(rtl)
        p = palette()
        fit_color = {"easy": ink(GOOD), "range": p.muted, "hard": ink(WARN)}

        def lv(m):
            return (kb.get(m) or {}).get("props", {}).get("Level") or 0
        blocks = []
        for x in self.q.needs:
            if x.startswith("Defeat "):
                continue                    # a monster to defeat is no item to get
            name = re.sub(r"\s*x\s*[\d,]+$", "", x).removeprefix("Collect ").strip()
            key = kb._item_by_name.get(name.lower())
            every = sorted(kb.droppers.get(key, []) if key else [], key=lv)
            mons = every
            if c and len(every) > DROPPERS_SHOWN:
                # nearest the level first, one well above it after the ones that can be farmed now
                near = sorted(every, key=lambda m: (farm.fit(c.level, lv(m)) == "hard", abs(c.level - lv(m)), lv(m)))
                top = near[:DROPPERS_SHOWN]
                mons = top + ([m for m in every if m not in top] if name in self._expanded else [])
            made = crafting.made_from(kb, name) if not mons else []
            # an item no one drops is often another quest's reward: the one to go do, not a drop to hunt (the owner
            # looked for Arcon's Blood, which only "Arcon's Blood?" hands over)
            givers = quests.item_givers(kb, key, self.key) if key else []
            if not mons and not made and not givers:
                continue
            # the item: its page (its prices, every dropper) in the text's own colour, bold, then the Farm window
            item = f"{bidi.LRE}<b>{html.escape(name)}</b>{bidi.PDF}"
            head = (f"<a href='item:{key}' style='color:{palette().text}; text-decoration:none'>{item}</a>" if key
                    else item)
            if mons:
                head += f"{bidi.RLM} · " + self._a(f"farm:{quote(name)}", html.escape(t("tool_farm")))
            rows = [f"<p {side} style='margin:6px 0 2px 0;'>{head}</p>"]
            for m in mons:
                path = kb.picture(m)
                uri = Path(path).resolve().as_uri() if path else ""
                img = (f"<a href='zoom:{uri}' style='text-decoration:none'><img src='{uri}' height='{THING_PX}' "
                       f"style='vertical-align: middle'></a>&nbsp;") if uri else ""
                mob = (kb.get(m) or {}).get("name", m)
                # the level in the UI's words: "רמה 5" in Hebrew, after the English block (HEB-14)
                who = (f"{bidi.LRE}{img}{self._a(f'monster:{m}', html.escape(mob))}{bidi.PDF}{bidi.RLM} "
                       f"({html.escape(t('lv_short', n=lv(m)))})" if rtl else
                       f"{img}{self._a(f'monster:{m}', html.escape(mob))} ({html.escape(t('lv_short', n=lv(m)))})")
                fit = farm.fit(c.level, lv(m)) if c else ""
                # whole, with its dot, on the next line when it doesn't fit ("ברמה שלכם" / "ומטה" split over two,
                # or a dot left at a line's end)
                tag = (f" <span style='white-space: nowrap'>· <span style='color:{fit_color[fit]}; font-weight:600'>"
                       f"{html.escape(bidi.plain(t(f'farm_fit_{fit}'), rtl))}</span></span>" if fit else "")
                rows.append(f"<p {side} style='margin:0 0 2px 0;'><span style='white-space: nowrap'>{who}{bidi.RLM}"
                            f"</span>{tag}</p>")
            hidden = len(every) - len(mons) if mons else 0
            if hidden > 0:
                rows.append(f"<p {side} style='margin:0 0 2px 0;'>"
                            + self._a(f"all:{quote(name)}", html.escape(bidi.plain(t("q_droppers_all", n=len(every)),
                                                                                    rtl))) + "</p>")
            if givers:
                rows.append(f"<p {side} style='margin:0 0 2px 0;'>{self._from_quest_html(givers)}</p>")
            if made:
                # a line in the UI's language, then each recipe's profession and its ingredients, one a line with
                # its picture (five ingredients in one line wrapped in the middle of a name: the owner)
                rows.append(f"<p {side} style='margin:0 0 2px 0;'>{html.escape(bidi.plain(t('q_made_from'), rtl))}</p>")
                for prof, plv, what in made[:2]:
                    head = (f"{bidi.LRE}<b>{html.escape(prof)}</b>{bidi.PDF}{bidi.RLM} "
                            f"<b>{html.escape(t('lv_short', n=plv))}</b>" if rtl else
                            f"<b>{html.escape(prof)} {html.escape(t('lv_short', n=plv))}</b>")
                    rows.append(f"<p {side} style='margin:2px 0 2px 0;'>{head}{bidi.RLM}:</p>")
                    for n, part in re.findall(r"(\d[\d,]*) x (.+?)(?=\s+\d[\d,]* x |$)", what):
                        rows.append(f"<p {side} style='margin:0 0 2px 0;'>{self._thing(f'{part.strip()} x {n}')}</p>")
            blocks.append("".join(rows))
        return "".join(blocks)

    def _from_quest_html(self, givers: list[str]) -> str:
        """The quest a needed item comes from (quests.item_givers put the one to do first): its name a tap away,
        who hands it over, and how many other quests give it too, rather than a list of them all."""
        kb, t, rtl = self._kb, self.t, self.t.rtl
        key = givers[0]
        q = quests.quest(kb, key)
        link = self._a(f"quest:{quote(key)}", html.escape(whole_name(quest_name(kb, key), rtl)))
        npc = q.npc if q else ""
        said = (t("q_from_quest", quest=_SLOT, npc=whole_name(npc, rtl)) if npc
                else t("q_from_quest_npcless", quest=_SLOT))
        text = html.escape(said).replace(_SLOT, link)
        if len(givers) > 1:
            more = (t("q_from_quest_more_one") if len(givers) == 2
                    else t("q_from_quest_more", n=len(givers) - 1))
            text += f"{bidi.RLM} · " + html.escape(bidi.plain(more, rtl))
        return text

    def _prerequisites(self) -> None:
        """What it asks first: each quest not done yet a tap away (done: nothing left to say, the owner), then the
        level to finish it, the citizenship grade, the profession, and the page's other lines."""
        kb, t, rtl, q = self._kb, self.t, self.t.rtl, self.q
        c = self.win.character
        did = quests.done_with_earlier(kb, c.quests_done) if c else set()
        side = _side(rtl)
        for k in quests.prerequisites(kb, q.key):
            if k in did:
                continue
            name = whole_name(quest_name(kb, k), rtl)
            text = html.escape(bidi.plain(t("q_after", name=name), rtl))
            self.col.addWidget(self._rich(f"<p {side} style='margin:0'>{text} · "
                                          f"{self._a(f'quest:{quote(k)}', html.escape(t('q_go_after')))}</p>", "Hint"))
        hints = []
        if q.complete_level > q.level:
            hints.append(t("q_complete_lv", n=q.complete_level, take=q.level))
        if q.grade:
            hints.append(t("q_grade", town=whole_name(q.grade[0], rtl), n=q.grade[1]))
        if q.profession:
            hints.append(t("qt_profession", prof=whole_name(q.profession[0], rtl), n=q.profession[1]))
        hints += q.prereq_hints(t)          # Fame, a fee to accept, any other pre-requisite line of the page
        for h in hints:
            self.col.addWidget(self.win.label(h, "Hint", wrap=True))

    # ------------------------------------------------------------ Mark done / Back to the list

    def _actions(self) -> None:
        t = self.t
        if self.done:
            # marked done by mistake (or a repeatable donation to do again): back to the list
            self.act = self.win.button(t("q_undo"), self._undo, "Small")
        else:
            self.act = self.win.button(t("q_mark_done"), self._mark, "Small")
        self._acts.addWidget(self.act)
        self._acts.addWidget(self.win.button(t("ask_short"), lambda: NAV.ask_requested.emit(
            t("qt_ask", name=self.q.name)), "Link"))
        self._acts.addStretch(1)

    def earlier(self) -> list[str]:
        """The quests before this one not marked done yet (quests.earlier_steps)."""
        c = self.win.character
        done = set(c.quests_done) if c else set()
        return [k for k in quests.earlier_steps(self._kb, self.key) if k not in done]

    def _mark(self) -> None:
        """Mark done: at once, or, with earlier steps not marked, the offer to mark them too."""
        earlier = self.earlier()
        if earlier:
            self._offer(earlier)
        else:
            self.win.mark_done([self.key])

    def _offer(self, earlier: list[str]) -> None:
        t, rtl = self.t, self.t.rtl
        self._acts_box.hide()
        self.offer = QFrame(objectName="Offer")
        v = QVBoxLayout(self.offer)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(6)
        v.addWidget(self.win.label(t("qt_mark_earlier", n=len(earlier)), "Detail", wrap=True))
        names = [quest_name(self._kb, k) for k in earlier]
        shown = names if len(names) <= 4 else names[:2] + ["…"] + names[-1:]
        v.addWidget(self.win.label(" · ".join(whole_name(n, rtl) for n in shown), "Note", wrap=True))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.win.button(t("qt_mark_all", n=len(earlier) + 1),
                                      lambda: self.win.mark_done(earlier + [self.key]), "Primary"))
        row.addWidget(self.win.button(t("qt_mark_this"), lambda: self.win.mark_done([self.key]), "Small"))
        row.addStretch(1)
        v.addLayout(row)
        self.col.addWidget(self.offer)
        self.win.settle()

    def _undo(self) -> None:
        self.win.unmark(self.key)


# ------------------------------------------------------------------ a chain's steps

def chain_list(win, chain: quests.Chain, state: quests.ChainState | None, this: str = "") -> QWidget:
    """A questline's steps in a box: how far along it the character is, then each step with its number in a circle
    (done: a check; to do now: lit; locked: a ring), its name (a link: that quest shown) and level, why a locked one
    waits when it isn't just the step before it, and where the line splits; each line of a split moved in. this: the
    quest the box is about (bold, no link)."""
    kb, t, rtl = win._kb, win.t, win.t.rtl
    c = win.character
    level = c.level if c else 0
    link = ink(accent_of(win._settings)[0])
    box = QWidget(objectName="ChainList")
    box.setAttribute(Qt.WA_StyledBackground, True)
    v = QVBoxLayout(box)
    v.setContentsMargins(8, 7, 8, 8)
    v.setSpacing(4)
    if state is not None:
        line = t("qt_chain_progress", done=len(state.done), total=state.total)
        if state.exp_left:
            line += " · " + t("qt_chain_exp_left", n=f"{state.exp_left:,}")
        v.addWidget(win.label(line, "Note"))

    def indented(widget: QWidget, depth: int, extra: int = 0) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        if depth * BRANCH_INDENT + extra:
            row.addSpacing(depth * BRANCH_INDENT + extra)       # at the reading start: mirrored in Hebrew
        row.addWidget(widget, 1)
        return row
    for k in chain.order:
        q = quests.quest(kb, k)
        if q is None:
            continue
        s = state.state(k) if state is not None else "locked"
        depth = chain.branch(k)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        if depth:
            row.addSpacing(depth * BRANCH_INDENT)
        dot = QLabel(CHECK if s == "done" else str(chain.step[k]), objectName="StepDot")
        dot.setProperty("state", s)
        dot.setFixedSize(STEP_DOT, STEP_DOT)
        dot.setAlignment(Qt.AlignCenter)
        dot.setToolTip(t(f"qt_state_{s}"))
        row.addWidget(dot, 0, Qt.AlignTop)
        if k == this:
            name = QLabel(bidi.ltr_name(q.name, rtl), objectName="StepThis")
        else:
            shown = f"{bidi.LRE}{html.escape(q.name)}{bidi.PDF}" if rtl else html.escape(q.name)
            color = palette().muted if s == "done" else link
            name = QLabel(f"<p {_side(rtl)} style='margin:0'><a href='{quote(k)}' style='color:{color}; "
                          f"text-decoration:none'>{shown}</a></p>", objectName="StepName")
            name.setProperty("state", s)
            name.setTextFormat(Qt.RichText)
            name.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
            name.linkActivated.connect(lambda href: win.open_quest(unquote(href)))
            name.setToolTip(t("qt_step_open"))
        name.setWordWrap(True)
        row.addWidget(name, 1)
        lv = QLabel(bidi.plain(t("lv_short", n=q.opens_at()), rtl), objectName="StepLv")
        lv.setProperty("high", s != "done" and q.opens_at() > level)
        row.addWidget(lv, 0, Qt.AlignTop)
        v.addLayout(row)
        why = _why(win, chain, state, k) if state is not None and s == "locked" else ""
        if why:
            v.addLayout(indented(win.label(why, "StepWhy", wrap=True), depth, STEP_DOT + 8))
        ways = len(chain.nexts.get(k, []))
        if ways > 1:
            v.addLayout(indented(win.label(t("qt_line_splits", n=ways), "StepSplit", wrap=True), depth,
                                 STEP_DOT + 8))
    return box


def _why(win, chain: quests.Chain, state: quests.ChainState, key: str) -> str:
    """Why a locked step waits, in a line, past what the list already says (its level's colour, the step before it):
    a quest off the line it asks first, a profession level."""
    t, rtl = win.t, win.t.rtl
    out = []
    for kind, value in state.why.get(key, []):
        if kind == "after" and value != chain.prev.get(key):
            out.append(t("qt_lock_after", name=whole_name(quest_name(win._kb, value), rtl)))
        elif kind == "profession" and value:
            out.append(t("qt_profession", prof=whole_name(value[0], rtl), n=value[1]))
    return " · ".join(out)


# ------------------------------------------------------------------ what a window of quest cards shares

class QuestWindow:
    """What the Quests and the Citizenship windows (ToolWindows) share around their cards: the chains left open,
    Mark done / Back to the list (saved, the cards read again where the player is reading), the "show quests marked
    done" link and its cards, the "Show more quests" under a long list, a row of level or grade chips. Each window
    sets open_quest(key)."""

    def _quests_state(self) -> None:
        """Made once (in _build_body)."""
        self.open_chains: set[str] = set()     # quest keys whose chain shows its steps
        self.show_done = False                 # the quests marked done listed
        self.lit = ""                          # the quest the window was opened on (open_with): its card lit
        self._look = None                      # the glass, accent and language the cards' rich text was made in

    def open_quest(self, key: str) -> None:
        raise NotImplementedError

    def _look_now(self) -> tuple:
        return palette(), accent_of(self._settings), self.t.lang

    def refresh(self) -> None:
        """As every tool window's; the cards' rich text (links, the droppers' colours) is made in the glass's colours,
        so another tint or accent picked while the window shows makes them again."""
        super().refresh()
        if self.isVisible() and self._look != self._look_now():
            self._fill()

    def settle(self) -> None:
        """A card grew in place (its chain opened, every dropper shown, the offer to mark the earlier steps): the
        scrolling cards ask for their height again a turn later, as ToolWindow._fill does after a fill (the wrapped
        lines' hints come in late)."""
        QTimer.singleShot(0, self, self._scroll.widget().fit)

    def scroll_to_lit(self) -> None:
        """The lit card's top at the top of the cards, once they are laid out and the fill's own keep-the-place and
        back-to-the-top have run (a tall card shown by its middle hid its name)."""
        def go() -> None:
            card = next((w for w in self.cards() if w.key == self.lit), None)
            if card is not None:
                top = card.mapTo(self._scroll.widget(), QPoint(0, 0)).y()
                self._scroll.verticalScrollBar().setValue(max(0, top - SCROLL_MARGIN))
        QTimer.singleShot(SCROLL_TO_MS, self, go)

    def rich(self, text: str, name: str = "Text") -> QLabel:
        """A wrapping label of a few lines (**bold**, each line its own paragraph in the reading order) whose game
        terms carry a "?" that explains them (glossary)."""
        d = "rtl" if self.t.rtl else "ltr"
        out = [bidi.paragraph_html(line, d, style="margin:0 0 2px 0; line-height:130%;") if line.strip() else
               "<p style='margin:0; font-size:5px;'>&nbsp;</p>" for line in (text or "").split("\n")]
        fill, _ = accent_of(self._settings)
        body = glossary.annotate("".join(out), self.t.lang, color=ink(fill))
        badge = _badge(fill)
        if badge:       # the "?" in the glass's accent, not the app's
            body = body.replace(glossary.MARK, f"<img src='{badge}' width='{terms.BADGE_PX}' "
                                               f"height='{terms.BADGE_PX}' style='vertical-align: middle'>")
        lb = QLabel(body, objectName=name)
        lb.setWordWrap(True)
        return terms.watch(lb, self.t.lang)

    def expire_cycles(self) -> None:
        """Daily / weekly quests done before the last reset come back (quests.expire_cycles)."""
        c = self.character
        if c is not None and c.cycle_done and quests.expire_cycles(self._kb, c):
            self._profiles.save()

    def mark_done(self, keys: list[str]) -> None:
        c = self.character
        if c is not None and quests.mark_done(self._kb, c, keys):
            self._profiles.save()
        self._refill()

    def unmark(self, key: str) -> None:
        c = self.character
        if c is not None and quests.unmark(c, key):
            self._profiles.save()
        if c is not None and not c.quests_done:
            self.show_done = False          # nothing left to show: the next one marked doesn't open the list
        self._refill()

    def done_link(self, n: int) -> QWidget:
        """ "Show quests marked done (3)" / "Hide quests marked done": right under a list's head (under a list of 50
        it was out of reach)."""
        t = self.t
        b = self.button(t("q_hide_done" if self.show_done else "q_show_done", n=n), self._toggle_done, "Link")
        b.setProperty("done_link", True)
        return b

    def _toggle_done(self) -> None:
        self.show_done = not self.show_done
        self._refill()

    def add_done(self, keys: list[str]) -> list[QuestCard]:
        """The quests marked done, newest first, muted, each with Back to the list, under their heading."""
        if not self.show_done:
            return []
        cards = [QuestCard(self, q, done=True, lit=k == self.lit) for k in reversed(keys[-MAX_QUESTS:])
                 if (q := quests.quest(self._kb, k))]
        if cards:
            self.body.addWidget(self.caption(self.t("q_done_head")))
            for card in cards:
                self.body.addWidget(card)
        return cards

    def more_quests(self, total: int, shown: int, then) -> None:
        """Under a list cut at `shown` cards: "Showing 40 of 56 quests" and "Show more quests" (the cut ones are the
        lowest EXP; without it only a search found them). The numbers are in the line, not on the button."""
        if total <= shown:
            return
        self.body.addWidget(self.label(self.t("q_shown", n=shown, total=total), "Note"), 0, Qt.AlignHCenter)
        self.body.addWidget(self.button(self.t("q_more"), then, "Small"), 0, Qt.AlignHCenter)

    def pick_chips(self, options: list[tuple[object, str, str]], picked, then) -> QWidget:
        """A row of chips to narrow a list (every level, or one: its quests only), each (value, text, tip); the
        picked one lit; a click runs then(value)."""
        from PySide6.QtWidgets import QPushButton
        box = QWidget()
        flow = FlowLayout(box, spacing=4, line_spacing=4)
        for value, text, tip in options:
            b = QPushButton(bidi.button(text, self.t.rtl), objectName="LevelChip")
            b.setCheckable(True)
            b.setChecked(value == picked)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            if tip:
                b.setToolTip(tip)
                b.setAccessibleName(tip)
            b.clicked.connect(lambda _=False, v=value: then(v))
            flow.addWidget(b)
        return box

    def cards(self) -> list[QuestCard]:
        """The quest cards in the body, top to bottom: the done ones too, and a chain's next step inside its chain's
        card (read from the body's layout, not from the window's children: the cards of the fill before are gone from
        it at once, deleted only later)."""
        out: list[QuestCard] = []
        for i in range(self.body.count()):
            w = self.body.itemAt(i).widget()
            if isinstance(w, QuestCard):
                out.append(w)
            elif w is not None:
                out += w.findChildren(QuestCard)
        return out
