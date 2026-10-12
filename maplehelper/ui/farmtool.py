"""Tools > Farm (FarmTool): hunting a monster for what it drops rather than for its EXP, in a tool window over the
game (ui/toolwindow.py).

- The top, always in view: the item search over every item a monster in the game drops (farm.farmable), its rows
  under it while the player types (the item's picture, its name, how many monsters drop it, what an NPC pays), Enter
  taking the first; under it the character's tracked items (the wishlist's ⭐) that monsters drop, as one-click chips.
- The picked item (kept per character in settings["farm_target"]): its card (its picture, what an NPC pays and where
  that price comes from, Prices: its page in the toolbar's Items search), then who drops it (farm.droppers): each
  monster's picture, name and level, where it lives, how it sits against the character's level, the drop's list,
  the players' votes and mesos, Show the way (the map's page in the Maps search) and Monster info (its page).
- Your drop rates: how many of the picked item (of every item, with none picked) this character picked up per active
  hour on the maps where it dropped (grindlive.drop_rates: the loot database the Loot Log and the grind bar fill), as
  the grind window's Drops tab says them. The KB has no drop chances: these are the only rates shown.
- Worth farming at your level (farm.targets): the monsters around the level whose drops the character needs (a quest,
  a recipe, a tracked item) or an NPC pays most for, each drop a click that picks it.

open_with(name) picks an item by its name (farm.pick: exact, letter case, hyphens and spaces aside, else the
shortest item monsters drop whose name holds it): the wishlist's "Where to get it"."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .. import bidi, combat, farm, grindlive, quick, routes, wishlist
from ..i18n import NBSP
from . import theme
from .controls import FlowLayout, clear
from .gamesearch import monster_maps, rim
from .grindbar import per_hour
from .lootoverlay import _elapsed
from .npcoverlay import accent_of, ink, palette
from .toolwindow import NAV, ToolWindow
from .widgets import (fit_picture, mesos_text, mesos_tip, name_lv, source_tag, tip_html, updated_tag, vote_tag,
                      zoom_on_hover)

TYPE_DEBOUNCE_MS = 150      # a pause in the typing before the search's rows are read again
PICK_ROWS = 6               # rows the search lists under its box before "and N more"
ITEM_PIC, MOB_PIC, ROW_PIC, DROP_PIC = 52, 40, 30, 24   # the pictures: the item's card, a monster's, a row's, a drop's
WORTH_N = 6                 # monsters "Worth farming" lists
RATES_SHOWN = 8             # drop rates listed with no item picked, then "and N more"
MONSTERS_SHOWN = 3          # a drop rate's monsters named before "and N more"
RATE_NONE_W = 72            # "Not enough time yet" on a rate's end: two short lines, the monsters keep the room
DROP_WHOLE = 16             # a drop's name up to this long never wraps inside; a longer one may, between its words
# the fit chips' colours (farm.fit), each readable on every dark glass tint and darkened by ink() on the white one:
# easy green, a bit above plain, well above amber, a rare boss red; a vote green, a single report amber
TONES = {"easy": "#4CD07D", "hard": "#FFB066", "boss": "#FF8A80"}
GAIN, WARN = "#4CD07D", "#FFB066"


def _rgba(color: str, alpha: float) -> str:
    c = theme.qcolor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def _lb(text: str, name: str, wrap: bool = False) -> QLabel:
    w = QLabel(text, objectName=name)
    w.setWordWrap(wrap)
    return w


def _block(text: str, rtl: bool) -> str:
    """A short English piece ("Green Mushroom", "1,234 mesos") that a line never wraps inside, and in Hebrew one
    left-to-right block."""
    return bidi.ltr_block(text.replace(" ", NBSP) if len(text) <= bidi.KEEP_TOGETHER else text, rtl)


class _Press(QFrame):
    """A row that clicks (a search row, a drop of a monster worth farming, a drop rate)."""

    clicked = Signal()

    def __init__(self, name: str):
        super().__init__(objectName=name)
        self.setAttribute(Qt.WA_Hover, True)          # its QSS :hover
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class FarmTool(ToolWindow):
    """Who drops an item, where and at what level; the player's own drop rates; the monsters worth farming at the
    character's level (the module's docstring has the whole of it)."""

    SHOW_KEY = "farm_tool"
    GEOM_KEY = "farm_tool_geom"
    TITLE_KEY = "tb_farm"
    MIN_W, MIN_H = 360, 420
    DEFAULT_W, DEFAULT_H = 440, 680

    # ------------------------------------------------------------ built once

    def _build_body(self) -> None:
        self._farmable: tuple[object, list[tuple[str, str, str]]] | None = None   # (kb, [(folded, name, key)])
        self._paths: dict[str, object] = {}                 # key -> its picture's path (kb.picture)
        self._fitted: dict[tuple[str, int, float], QPixmap] = {}
        self._maps: dict[str, str] = {}                     # a dropper ("<monster>\n<map name>") -> "map/<id>" or ""
        self._searching = QTimer(self, singleShot=True, interval=TYPE_DEBOUNCE_MS, timeout=self._fill_results)
        self._box = self.key_box()
        self._box.setClearButtonEnabled(True)
        self._box.textEdited.connect(self._typed)
        self._box.textChanged.connect(lambda _t: self._align_box())
        self._box.entered.connect(self._enter)
        self._box.done.connect(self._close_results)
        self.top.addWidget(self._box)
        self._results_box = QWidget()
        self._results = QVBoxLayout(self._results_box)
        self._results.setContentsMargins(0, 0, 0, 0)
        self._results.setSpacing(3)
        self._results_box.hide()
        self.top.addWidget(self._results_box)
        self._wish_box = QWidget()
        self._wish = QVBoxLayout(self._wish_box)
        self._wish.setContentsMargins(0, 0, 0, 0)
        self._wish.setSpacing(4)
        self._wish_box.hide()
        self.top.addWidget(self._wish_box)

    def _retext(self) -> None:
        super()._retext()
        if "_box" in self.__dict__:         # the chrome's words come first, in ToolWindow.__init__
            t = self.t
            ph = t("ft_search_ph", n=f"{len(self._items()):,}")
            self._box.setPlaceholderText(bidi.plain(ph, t.rtl))
            self._box.setAccessibleName(ph)
            self._align_box()

    def _align_box(self) -> None:
        """In Hebrew the cursor waits on the right, by the hint; a name typed in English, as the game writes it, runs
        from the left (controls.follow_typing's rule, in the language the window has now)."""
        text = self._box.text()
        right = self.t.rtl and (not text or bool(bidi._RTL.search(text)))
        self._box.setAlignment((Qt.AlignRight if right else Qt.AlignLeft) | Qt.AlignAbsolute | Qt.AlignVCenter)

    def extra_qss(self) -> str:
        p = palette()
        fill, _ = accent_of(self._settings)
        lit, gain, warn = ink(fill), ink(GAIN), ink(WARN)
        chip = "border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700;"
        tones = "".join(f'QLabel#Fit[tone="{k}"] {{ color: {ink(c)}; background: {_rgba(ink(c), 0.15)}; }}\n'
                        for k, c in TONES.items())
        return f"""
QFrame#Row {{ background: {p.fill1}; border: none; border-radius: 10px; }}
QFrame#Row:hover {{ background: {p.fill2}; }}
QFrame#Line {{ background: {p.fill1}; border: 1px solid transparent; border-radius: 10px; }}
QFrame#Line[press="true"]:hover {{ background: {p.fill2}; }}
QFrame#Drop {{ background: {rim(0.05, p)}; border: none; border-radius: 8px; }}
QFrame#Drop:hover {{ background: {p.fill2}; }}
#Name {{ color: {p.text}; font-size: 13px; font-weight: 600; }}
#Sub {{ color: {p.muted}; font-size: 12px; }}
#DropName {{ color: {lit}; font-size: 12px; font-weight: 700; }}
#DropPrice {{ color: {p.text}; font-size: 11px; font-weight: 600; }}
#Rate {{ color: {lit}; font-size: 14px; font-weight: 700; }}
#RateNone {{ color: {p.muted}; font-size: 11px; }}
QPushButton#Wish {{ background: {rim(0.10, p)}; color: {p.text}; border: 1px solid transparent; border-radius: 9px;
                    min-height: 0; padding: 2px 10px; font-size: 12px; font-weight: 600; text-align: center; }}
QPushButton#Wish:hover {{ background: {p.fill2}; }}
QPushButton#Wish:checked {{ background: {_rgba(fill, 0.16)}; color: {lit}; border: 1px solid {fill}; }}
QLabel#Fit {{ color: {p.text}; background: {rim(0.10, p)}; {chip} }}
{tones}QLabel#Need {{ color: {gain}; font-size: 11px; font-weight: 600; }}
QLabel#SourceTag {{ color: {lit}; background: transparent; border: 1px solid {_rgba(fill, 0.6)}; border-radius: 5px;
                   padding: 0 4px; font-size: 10px; font-weight: 700; }}
QLabel#VoteTag {{ color: {gain}; background: transparent; font-size: 11px; font-weight: 600; padding: 0 1px; }}
QLabel#VoteTag[single="true"] {{ color: {warn}; }}
QLabel#UpdatedTag {{ color: {lit}; background: {_rgba(fill, 0.14)}; {chip} }}
"""

    def set_kb(self, kb) -> None:
        self._farmable = None
        self._paths.clear()
        self._fitted.clear()
        self._maps.clear()
        super().set_kb(kb)

    # ------------------------------------------------------------ what is picked

    def open_with(self, arg: str) -> None:
        """The window on an item by its name (the wishlist's "Where to get it"): picked as a typed name is
        (farm.pick); a name no monster's item has stays in the box, saying so."""
        name = str(arg or "").strip()
        if not name or self.character is None:
            return
        key = farm.pick(self._kb, name)
        if key:
            self._choose(key)
        else:
            self._box.setText(name)
            self._fill_results()

    def picked(self) -> str | None:
        """The item the active character farms for (settings["farm_target"]), when the KB has it."""
        c = self.character
        key = (self._settings["farm_target"] or {}).get(c.id) if c else None
        return key if key and self._kb.get(key) else None

    def _set_picked(self, key: str | None) -> None:
        c = self.character
        if c is None:
            return
        data = dict(self._settings["farm_target"] or {})
        if key:
            data[c.id] = key
        else:
            data.pop(c.id, None)
        self._settings["farm_target"] = data

    def _choose(self, key: str) -> None:
        """An item picked (a search row, Enter, a tracked item's chip, a drop, a rate, open_with): its card and
        droppers from the top, the box saying its name, the keyboard back to the game."""
        self._set_picked(key)
        self._searching.stop()
        self._results_box.hide()
        self._set_box((self._kb.get(key) or {}).get("name", ""))
        self._give_keys()
        self._fill()
        self._to_top()

    def _set_box(self, text: str) -> None:
        if self._box.text() != text:
            self._box.setText(text)
        self._box.setCursorPosition(0)

    # ------------------------------------------------------------ the search

    def _items(self) -> list[tuple[str, str, str]]:
        """Every item a monster drops, once per name, as (folded name, name, key), by name; kept per KB."""
        if self._farmable is None or self._farmable[0] is not self._kb:
            rows = [(farm.fold(e["name"]), e["name"].strip(), k)
                    for k in farm.farmable(self._kb) if (e := self._kb.get(k))]
            self._farmable = (self._kb, rows)
        return self._farmable[1]

    def search(self, query: str) -> list[str]:
        """The items whose name has all the query's words in it, letter case, hyphens and spaces aside: the exact
        name first, then the names the query starts, then the rest, each by name."""
        q = farm.fold(query)
        if not q:
            return []
        words = q.split(" ")
        ranked: list[list[tuple[str, str]]] = [[], [], []]
        for low, _name, key in self._items():
            if all(w in low for w in words):
                ranked[0 if low == q else 1 if low.startswith(q) else 2].append((low, key))
        return [key for bucket in ranked for _low, key in sorted(bucket)]

    def _typed(self, text: str) -> None:
        """The player typing: the rows follow once they pause; the box emptied (its ✕) puts the item down."""
        if text.strip():
            self._searching.start()
            return
        self._searching.stop()
        self._results_box.hide()
        if self.picked():
            self._set_picked(None)
            self._fill()
        else:
            self._wish_box.setVisible(self._wish.count() > 0)

    def _enter(self) -> None:
        """Enter: the first row; with none read yet, the item the words name (farm.pick)."""
        self._searching.stop()
        text = self._box.text().strip()
        if not text:
            return
        hits = self.search(text)
        key = hits[0] if hits else farm.pick(self._kb, text)
        if key:
            self._choose(key)
        else:
            self._fill_results()

    def _close_results(self) -> None:
        """Esc: the rows go and the box says the picked item's name again."""
        self._searching.stop()
        self._results_box.hide()
        key = self.picked()
        self._set_box((self._kb.get(key) or {}).get("name", "") if key else "")
        self._wish_box.setVisible(self._wish.count() > 0)

    def _fill_results(self) -> None:
        """The search's rows for what is typed, under the box (the tracked items hidden while they show)."""
        t, rtl = self.t, self.t.rtl
        clear(self._results)
        text = self._box.text().strip()
        if not text:
            self._results_box.hide()
            self._wish_box.setVisible(self._wish.count() > 0)
            return
        hits = self.search(text)
        for key in hits[:PICK_ROWS]:
            self._results.addWidget(self._result_row(key))
        if not hits:
            self._results.addWidget(_lb(bidi.plain(t("farm_none", name=bidi.ltr_block(text, rtl)), rtl), "Hint",
                                        wrap=True))
        elif len(hits) > PICK_ROWS:
            self._results.addWidget(_lb(bidi.plain(t("lk_more", n=len(hits) - PICK_ROWS), rtl), "Note"))
        self._results_box.show()
        self._wish_box.hide()

    def _result_row(self, key: str) -> _Press:
        """A search row: the item's picture, its name over how many monsters drop it and what an NPC pays."""
        t, rtl = self.t, self.t.rtl
        row = _Press("Row")
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 5, 10, 5)
        h.setSpacing(8)
        h.addWidget(self._pic(key, ROW_PIC, zoom=False), 0, Qt.AlignVCenter)
        v = QVBoxLayout()
        v.setSpacing(1)
        v.addWidget(_lb(bidi.ltr_name(self._kb.get(key)["name"], rtl), "Name", wrap=True))
        n = len(self._kb.droppers.get(key, ()))
        bits = [t("ft_dropped_by_one") if n == 1 else t("ft_dropped_by", n=n)]
        v_ = farm.value(self._kb, key)
        if v_:
            bits.append(_block(f"{v_.price:,} mesos", rtl))
        v.addWidget(_lb(bidi.plain(" · ".join(bits), rtl), "Sub", wrap=True))
        h.addLayout(v, 1)
        row.clicked.connect(lambda k=key: self._choose(k))
        return row

    # ------------------------------------------------------------ the cards

    def _rebuild(self) -> None:
        t, kb, c = self.t, self._kb, self.character
        clear(self.body)
        key = self.picked()
        if not (self._results_box.isVisible() and self._box.hasFocus()):
            self._set_box((kb.get(key) or {}).get("name", "") if key else "")
        self._fill_wish(key)
        if self._results_box.isVisible():
            self._fill_results()            # the rows in the language the window has now
        if key:
            self._item(key)
        else:
            self.body.addWidget(self.empty("sprout", t("farm_want"), t("farm_pick")))
        self._rates(key, c.id)
        self._worth(c)

    def _fill_wish(self, key: str | None) -> None:
        """The character's tracked items that monsters drop, as chips; the picked one lit."""
        t, kb, rtl = self.t, self._kb, self.t.rtl
        clear(self._wish)
        wished = [k for k in wishlist.items(self._settings, self.character.id) if k in kb.droppers and kb.get(k)]
        if wished:
            self._wish.addWidget(_lb(bidi.plain(t("farm_from_wishlist"), rtl), "Hint"))
            box = QWidget()
            flow = FlowLayout(box, spacing=4, line_spacing=4)
            for k in wished:
                b = QPushButton(bidi.ltr_name(kb.get(k)["name"], rtl), objectName="Wish")
                b.setCheckable(True)
                b.setChecked(k == key)
                b.setCursor(Qt.PointingHandCursor)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(lambda _=False, k=k: self._choose(k))
                flow.addWidget(b)
            self._wish.addWidget(box)
        self._wish_box.setVisible(bool(wished) and not self._results_box.isVisible())

    def _item(self, key: str) -> None:
        """The picked item's card (what an NPC pays, Prices), then every monster that drops it."""
        t, kb, rtl = self.t, self._kb, self.t.rtl
        e = kb.get(key)
        card, v = self.card(lit=True)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self._pic(key, ITEM_PIC), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        head = QWidget()
        flow = FlowLayout(head, spacing=6, line_spacing=2)
        flow.addWidget(_lb(bidi.ltr_name(e["name"], rtl), "CardTitle", wrap=True))
        updated = updated_tag(t, kb, key)
        if updated is not None:
            flow.addWidget(updated)
        col.addWidget(head)
        price = farm.value(kb, key)
        if price:
            line = QHBoxLayout()
            line.setSpacing(6)
            words = QLabel(objectName="Text")
            words.setTextFormat(Qt.RichText)
            words.setWordWrap(True)
            words.setText(bidi.paragraph_html(t("price_npc_buys", n=f"{price.price:,}"), "rtl" if rtl else "ltr",
                                              style="margin:0;"))
            line.addWidget(words, 1)
            line.addWidget(source_tag(t, price.source), 0, Qt.AlignVCenter)
            col.addLayout(line)
        else:
            col.addWidget(self.label(t("farm_no_npc_price"), "Hint", wrap=True))
        col.addWidget(self._links([("ft_prices", t("farm_fm_price"), lambda: NAV.item_requested.emit(key))]))
        top.addLayout(col, 1)
        v.addLayout(top)
        self.body.addWidget(card)
        ds = farm.droppers(kb, key, self.character.level)
        self.body.addSpacing(4)
        if not ds:
            self.body.addWidget(self.label(t("wish_no_droppers"), "Hint", wrap=True))
            return
        # each drop's list: one chip beside the heading when every dropper's drop is on the same one, else one on
        # each dropper's card (as the wishlist window does)
        mixed = len({d.source for d in ds}) > 1
        cap = QHBoxLayout()
        cap.setContentsMargins(0, 0, 0, 0)
        cap.setSpacing(6)
        cap.addWidget(self.caption(t("ft_droppers")), 0, Qt.AlignVCenter)
        if not mixed:
            cap.addWidget(source_tag(t, ds[0].source), 0, Qt.AlignVCenter)
        cap.addStretch(1)
        box = QWidget()
        box.setLayout(cap)
        self.body.addWidget(box)
        self.body.addWidget(self.label(quick.drops_note(t, [d.source for d in ds]), "Note", wrap=True))
        for d in ds:
            self.body.addWidget(self._dropper(d, mixed))

    def _dropper(self, d: farm.Dropper, mixed: bool) -> QFrame:
        """A monster that drops the item: its picture, name and level, where it lives, its chips (how it sits against
        the level, the drop's list when the droppers mix them, the players' votes and mesos), its links."""
        t, rtl = self.t, self.t.rtl
        card, v = self.card()
        h = QHBoxLayout()
        h.setSpacing(10)
        h.addWidget(self._pic(d.key, MOB_PIC), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(_lb(name_lv(d.name, d.level, t), "CardTitle", wrap=True))
        if d.map:
            col.addWidget(_lb(bidi.ltr_name(self._kb.map_label(d.map), rtl), "CardSub", wrap=True))
        col.addWidget(self._chips(self._fit(d.fit, d.boss),
                                  source_tag(t, d.source) if mixed else None,
                                  vote_tag(t, d.vote) if d.vote else None,
                                  self._mesos(d.mesos)))
        col.addWidget(self._mob_links(d.key, "" if d.closed else d.map))    # no way to walk where nobody walks in
        h.addLayout(col, 1)
        v.addLayout(h)
        return card

    def _rates(self, key: str | None, cid: str) -> None:
        """Your drop rates: the picked item's (every item's, with none picked), from the loot database."""
        t, rtl = self.t, self.t.rtl
        self.body.addSpacing(6)
        self.body.addWidget(self.caption(t("ft_rates")))
        rates = grindlive.drop_rates(self._kb, cid)
        if key:
            name = (self._kb.get(key) or {}).get("name", "")
            rates = [r for r in rates if r.item_key == key or farm.fold(r.item) == farm.fold(name)]
            if not rates:
                self.body.addWidget(self.label(t("ft_rates_item_none", item=bidi.ltr_block(name, rtl)), "Hint",
                                               wrap=True))
                return
        elif not rates:
            self.body.addWidget(self.empty("backpack", t("gw_drops_empty_title"), t("gw_drops_empty")))
            return
        else:
            self.body.addWidget(self.label(t("gw_drops_head"), "Note", wrap=True))
        for r in rates[:RATES_SHOWN]:
            self.body.addWidget(self._rate_row(r, picks=not key))
        if len(rates) > RATES_SHOWN:
            self.body.addWidget(self.label(t("lk_more", n=len(rates) - RATES_SHOWN), "Note"))

    def _rate_row(self, r: grindlive.DropRate, picks: bool) -> QFrame:
        """One item's rate, as the grind window's Drops tab: its picture, its name, how many were picked up in how
        long and from which monsters, and on the end how many come an hour, or that the time is too short yet.
        picks: a click picks the item (when a monster drops it)."""
        t, rtl, kb = self.t, self.t.rtl, self._kb
        picks = picks and r.item_key in kb.droppers
        row = _Press("Line") if picks else QFrame(objectName="Line")
        row.setProperty("press", picks)
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 7, 10, 8)
        h.setSpacing(10)
        h.addWidget(self._pic(r.item_key, ROW_PIC), 0, Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(2)
        v.addWidget(_lb(bidi.ltr_name(r.item, rtl), "Name", wrap=True))
        sub = t("gw_drop_sub_one", time=_elapsed(t, r.active_s)) if r.count == 1 else \
            t("gw_drop_sub", n=f"{r.count:,}", time=_elapsed(t, r.active_s))
        v.addWidget(_lb(bidi.plain(sub, rtl), "Sub", wrap=True))
        names: list[str] = []
        for m in r.monsters:
            n = str((kb.get(m) or {}).get("name") or m)
            if n not in names:
                names.append(n)
        if names:
            shown = ", ".join(_block(n, rtl) for n in names[:MONSTERS_SHOWN])
            if len(names) > MONSTERS_SHOWN:
                shown += " " + t("lk_more", n=len(names) - MONSTERS_SHOWN)
            v.addWidget(_lb(bidi.plain(t("gw_drop_from", list=shown), rtl), "Sub", wrap=True))
        h.addLayout(v, 1)
        if r.per_h is not None:
            rate = _lb(bidi.plain(t("gw_drop_per_h", n=_block(per_hour(r.per_h), rtl)), rtl), "Rate")
            rate.setToolTip(t("gw_drop_per_h_tip"))
        else:
            rate = _lb(bidi.plain(t("gw_not_enough"), rtl), "RateNone", wrap=True)
            rate.setFixedWidth(RATE_NONE_W)
            rate.setAlignment(Qt.AlignRight | Qt.AlignTop)       # the row's end (mirrored in Hebrew)
        h.addWidget(rate, 0, Qt.AlignTop)
        if picks:
            row.setToolTip(t("ft_rate_pick_tip", item=r.item))
            row.clicked.connect(lambda k=r.item_key: self._choose(k))
        return row

    def _worth(self, c) -> None:
        """Worth farming at your level: the monsters around it whose drops the character needs or an NPC pays most
        for (farm.targets), each drop a click that picks it."""
        t, kb = self.t, self._kb
        self.body.addSpacing(6)
        self.body.addWidget(self.caption(t("farm_worth")))
        self.body.addWidget(self.label(t("farm_worth_hint", lo=max(1, c.level - farm.FARM_BELOW),
                                         hi=c.level + combat.SPOT_ABOVE), "Note", wrap=True))
        wanted = farm.needs(kb, c.level, c.base_class, c.job, c.quests_done, c.crafts or None,
                            wishlist.items(self._settings, c.id))
        rows = farm.targets(kb, c.level, n=WORTH_N, wanted=wanted)
        if not rows:
            self.body.addWidget(self.label(t("farm_worth_none"), "Hint", wrap=True))
            return
        for r in rows:
            self.body.addWidget(self._target(r))

    def _target(self, r: farm.Target) -> QFrame:
        """A monster worth farming: its picture, name and level, its map, how it sits against the level and its
        mesos, its best drops (each a click that picks it: what an NPC pays, what the player needs it for, its
        list), its links."""
        t, rtl = self.t, self.t.rtl
        card, v = self.card()
        h = QHBoxLayout()
        h.setSpacing(10)
        h.addWidget(self._pic(r.key, MOB_PIC), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(_lb(name_lv(r.name, r.level, t), "CardTitle", wrap=True))
        col.addWidget(_lb(bidi.ltr_name(self._kb.map_label(r.map), rtl), "CardSub", wrap=True))
        col.addWidget(self._chips(self._fit(r.fit), self._mesos(r.mesos)))
        for d in r.drops:
            col.addWidget(self._drop(d))
        col.addWidget(self._mob_links(r.key, r.map))
        h.addLayout(col, 1)
        v.addLayout(h)
        return card

    def _drop(self, d: farm.Drop) -> _Press:
        """One drop of a monster worth farming, a click that picks it: its picture, its name and NPC price, what the
        player needs it for and the list it is on."""
        t, rtl = self.t, self.t.rtl
        row = _Press("Drop")
        row.setToolTip(t("farm_drop_tip", item=d.name))
        h = QHBoxLayout(row)
        h.setContentsMargins(6, 4, 8, 4)
        h.setSpacing(8)
        h.addWidget(self._pic(d.key, DROP_PIC, zoom=False), 0, Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(3)
        # the name on its own line, then its NPC price and its list in a row that wraps: the three in one row were
        # up to 368 px, wider than the cards at the window's narrowest (a test at MIN_W)
        name = d.name if len(d.name) > DROP_WHOLE else _block(d.name, rtl)     # a long one may wrap between words
        v.addWidget(_lb(bidi.ltr_name(name, rtl), "DropName", wrap=True))
        price = _lb(bidi.plain(_block(f"{d.value.price:,} mesos", rtl), rtl), "DropPrice") if d.value else None
        v.addWidget(self._chips(price, source_tag(t, d.source)))
        if d.need:
            # which quest or recipe it is for, whole: a line in the accent that wraps (a chip kept its whole width,
            # wider than the cards of a narrow window)
            kind, what = d.need
            need = _lb(bidi.plain(t(f"farm_need_{kind}_named", name=bidi.ltr_block(what, rtl)) if what
                                  else t(f"farm_need_{kind}"), rtl), "Need", wrap=True)
            if what:
                need.setToolTip(tip_html(t(f"farm_need_{kind}_tip", name=what), rtl))
            v.addWidget(need)
        h.addLayout(v, 1)
        row.clicked.connect(lambda k=d.key: self._choose(k))
        return row

    # ------------------------------------------------------------ pieces

    def _pic(self, key: str, size: int, zoom: bool = True) -> QLabel:
        """The KB's picture of a thing in a fixed square, fitted once per size; shown large on hover unless zoom is
        off (a row the whole of which is a click)."""
        pic = QLabel(objectName="Pic")
        pic.setFixedSize(size, size)
        pic.setAlignment(Qt.AlignCenter)
        if key not in self._paths:
            self._paths[key] = self._kb.picture(key) if key else None
        path = self._paths[key]
        if not path:
            return pic
        dpr = pic.devicePixelRatioF()
        pm = self._fitted.get((key, size, dpr))
        if pm is None:
            raw = QPixmap(str(path))
            pm = fit_picture(raw, size, size, pic) if not raw.isNull() else QPixmap()
            self._fitted[(key, size, dpr)] = pm
        if not pm.isNull():
            pic.setPixmap(pm)
            if zoom:
                zoom_on_hover(pic, path)
        return pic

    def _fit(self, fit: str, boss: bool = False) -> QLabel:
        """How a monster sits against the character's level (farm.fit), or a rare boss: a chip with its why."""
        t = self.t
        kind = "boss" if boss else fit
        chip = _lb(bidi.plain(t(f"farm_fit_{kind}"), t.rtl), "Fit")
        chip.setProperty("tone", kind)
        chip.setToolTip(tip_html(t(f"farm_fit_{kind}_tip"), t.rtl))
        return chip

    def _mesos(self, mesos) -> QLabel | None:
        """The mesos the players reported a kill drops, its why on hover; None with no reports."""
        if not mesos:
            return None
        t = self.t
        chip = _lb(bidi.plain(mesos_text(t, mesos), t.rtl), "Chip")
        chip.setToolTip(tip_html(mesos_tip(t, mesos), t.rtl))
        return chip

    def _chips(self, *chips) -> QWidget:
        """Chips in a row that wraps rather than widen the window (None: left out), from the leading edge."""
        box = QWidget()
        flow = FlowLayout(box, spacing=5, line_spacing=4)
        for c in chips:
            if c is not None:
                c.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
                flow.addWidget(c)
        return box

    def _links(self, acts: list[tuple[str, str, object]]) -> QWidget:
        """(text key, tip, action) as accent links in a row that wraps."""
        box = QWidget()
        flow = FlowLayout(box, spacing=14, line_spacing=2)
        flow.setContentsMargins(0, 2, 0, 0)
        for key, tip, then in acts:
            flow.addWidget(self.button(self.t(key), then, "Link", tip))
        return box

    def _mob_links(self, key: str, map_name: str) -> QWidget:
        """A monster's links: Show the way to the map it lives on (when the map is known), Monster info."""
        t = self.t
        acts = []
        mk = self._map_key(key, map_name) if map_name else ""
        if mk:
            acts.append(("gw_show_way", t("gw_show_way_tip"), lambda: NAV.map_requested.emit(mk)))
        acts.append(("ft_monster", t("lk_open_monster"), lambda: NAV.monster_requested.emit(key)))
        return self._links(acts)

    def _map_key(self, mob: str, map_name: str) -> str:
        """The KB key ("map/<id>") of the map a monster lives on, by the name its card shows (the route graph's
        find, as the wishlist's way there reads it), else its busiest map in the spawns table; "" when neither."""
        at = f"{mob}\n{map_name}"
        if at not in self._maps:
            mid = routes.of(self._kb).find(map_name)
            if mid:
                self._maps[at] = f"map/{mid}"
            else:
                spawns = monster_maps(self._kb, mob)
                self._maps[at] = spawns[0][0] if spawns else ""
        return self._maps[at]
