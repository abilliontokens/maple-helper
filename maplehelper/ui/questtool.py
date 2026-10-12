"""Quests over the game (the toolbar's Tools card, ui/toolwindow.py), ported from the old Play tools' quests page.

Tabs, each with its count: the character's level (the quests that open at it, best EXP first), Skipped (the earlier
levels' quests not done, newest level first), Coming up (the next level's), Later (every level after it) — those
from quests.for_level, the class's and job's only, those of a profession level the player hasn't reached left out —
and Chains: the questlines (quests.chains_for) the character is on, each with how far along it is, the EXP left and
the next step's whole card, then the ones to start, then the ones that open later, then the finished ones.

Skipped and Later have a chip a level (a tap: that level's quests); Later says which areas aren't in the game yet.
The search above the tabs looks through every quest at once (the tabs' lists, the ones marked done, and the
Citizenship ones, which open in their own window). Every list cuts at 40 cards with "Show more quests"; "Show quests
marked done" under each head. A quest's card is ui/questcard.py's, shared with the Citizenship window.
Daily and weekly quests marked done come back on open once their time is up (quests.expire_cycles).

open_with(key): that quest, on the tab it is on, its card lit and scrolled to; one marked done: in the done list; a
Citizenship quest: the Citizenship window on it (NAV.tool_requested)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from .. import availability, bidi, quests
from .controls import Segmented, clear
from .npcoverlay import SIDE
from .questcard import (CHEVRON, MAX_QUESTS, QuestCard, QuestWindow, card_qss, chain_list, quest_name, quest_town,
                        whole_name)
from .toolwindow import NAV, ToolWindow

LISTS = ("level", "missed", "soon", "later")       # the tabs of quest lists (quests.for_level's keys)
SEARCH_MS = 200         # a pause in the search's typing before the cards are read again
TAB_PAD = 16            # a tab's room around its words (the segment's own padding): five tabs and their counts


class _CountTabs(Segmented):
    """The tab row, each tab with its count: a tighter fit than Segmented's own (it keeps 30 px a tab)."""

    @staticmethod
    def _fit(b) -> None:
        b.ensurePolished()
        bold = b.font()
        bold.setBold(True)
        b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(b.text()) + TAB_PAD)


class QuestTool(QuestWindow, ToolWindow):
    """The Quests window (the module's docstring)."""

    SHOW_KEY = "quest_tool"
    GEOM_KEY = "quest_tool_geom"
    TITLE_KEY = "tb_quests"
    MIN_W, MIN_H = 400, 440
    DEFAULT_W, DEFAULT_H = 460, 680
    TABS = (("level", "qt_tab_level"), ("missed", "qt_tab_missed"), ("soon", "q_soon"), ("later", "q_later"),
            ("chains", "qt_tab_chains"))

    # ------------------------------------------------------------ made once

    def _build_body(self) -> None:
        self._quests_state()
        self._limit = MAX_QUESTS            # cards a list shows ("Show more quests" adds 40)
        self._level_pick = None             # Skipped / Later: the level picked by its chip (None: every level)
        self._counts: dict[str, int] = {}
        self.search = self.key_box(self.t("q_search"))
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=SEARCH_MS, timeout=self._searched)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        self.search.entered.connect(self._searched)
        self.top.addWidget(self.search)

    def _retext(self) -> None:
        super()._retext()
        t = self.t
        self.search.setPlaceholderText(bidi.plain(t("q_search"), t.rtl))
        self.search.setAccessibleName(t("q_search"))

    def _make_tabs(self) -> None:
        """ToolWindow's tab row, each tab with its count (_tab_texts) in a tighter fit."""
        t, rtl = self.t, self.t.rtl
        if self._tabs is not None:
            self._tabs_slot.removeWidget(self._tabs)
            self._tabs.hide()
            self._tabs.deleteLater()
        self._tabs = _CountTabs([(t(key), value) for value, key in self.TABS], self.tab, rtl)
        self._tabs.setObjectName("Tabs")
        self._tabs.set_label(t(self.TITLE_KEY))
        for b in self._tabs.group.buttons():
            b.setFocusPolicy(Qt.NoFocus)
        self._tabs.changed.connect(self._tab_picked)
        self._tabs_slot.addWidget(self._tabs)
        self._tab_texts()

    def extra_qss(self) -> str:
        return card_qss(self._settings)

    def _set_tab(self, tab: str) -> None:
        """Another tab: its whole list from the top, every level, its first 40."""
        self._level_pick = None
        self._limit = MAX_QUESTS
        super()._set_tab(tab)

    def _tab_picked(self, tab) -> None:
        self.lit = ""                       # the player's own pick: no card stays lit from a quest opened before
        super()._tab_picked(tab)

    def _searched(self) -> None:
        """The search typed (or Enter): what it finds from the top, the first 40."""
        self._search_timer.stop()
        self.lit = ""
        self._limit = MAX_QUESTS
        self._fill()
        self._to_top()

    # ------------------------------------------------------------ the contract

    def open_with(self, arg: str) -> None:
        """A quest's key: that quest shown (the module's docstring)."""
        kb, c = self._kb, self.character
        q = quests.quest(kb, arg)
        if q is None:
            return
        if q.area == "Citizenship":
            NAV.tool_requested.emit("citizenship", arg)
            return
        if c is None:
            return
        self.lit = arg
        r = quests.for_level(kb, c.level, c.base_class, c.job, c.quests_done, crafts=c.crafts or None)
        tab = next((m for m in LISTS if any(x.key == arg for x in r[m])), None)
        self.search.blockSignals(True)
        if tab is not None:
            self.search.clear()
            self.search.blockSignals(False)
            rows = r[tab]
            at = next(i for i, x in enumerate(rows) if x.key == arg)
            self._set_tab(tab)              # (every level, its first 40)
            if at >= self._limit:
                self._limit = (at // MAX_QUESTS + 1) * MAX_QUESTS
                self._fill()
        else:
            # marked done, or on no list of the character's (its job, a profession level): the search shows it
            self.search.setText(q.name)
            self.search.blockSignals(False)
            self._limit = MAX_QUESTS
            self._fill()
        self.scroll_to_lit()

    def open_quest(self, key: str) -> None:
        """A step of a chain or a prerequisite clicked on a card: that quest (open_with)."""
        self.open_with(key)

    # ------------------------------------------------------------ filled

    def _tab_texts(self) -> None:
        """Each tab's words with its count ("Skipped · 23") once the lists are read, when the five fit the window's
        width (the heads still count each list); narrower, the words alone."""
        if self._tabs is None:
            return
        t, c = self.t, self.character
        words = [t(key, lv=c.level) if value == "level" and c is not None else t(key).replace("{lv}", "").strip()
                 for value, key in self.TABS]
        counted = [f"{w} · {self._counts[v]}" if v in self._counts else w for w, (v, _) in zip(words, self.TABS)]
        b = self._tabs.group.buttons()[0]
        b.ensurePolished()
        bold = b.font()
        bold.setBold(True)
        fm = QFontMetrics(bold)
        need = sum(fm.horizontalAdvance(x) + TAB_PAD for x in counted) + 2 * len(counted) + 4
        for i, text in enumerate(counted if need <= self.width() - 2 * SIDE else words):
            self._tabs.set_text(i, text)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if getattr(self, "_counts", None):        # (a resize before the body is made: nothing to count yet)
            self._tab_texts()

    def _rebuild(self) -> None:
        self._look = self._look_now()
        self.expire_cycles()
        kb, c = self._kb, self.character
        r = quests.for_level(kb, c.level, c.base_class, c.job, c.quests_done, crafts=c.crafts or None)
        chains = quests.chains_for(kb, c.level, c.base_class, c.job, c.quests_done, c.crafts or None)
        self._counts = {m: len(r[m]) for m in LISTS}
        self._counts["chains"] = len(chains["progress"]) + len(chains["start"])
        self._tab_texts()
        clear(self.body)
        query = self.search.text().strip()
        if query:
            self._fill_search(r, query)
        elif self.tab == "chains":
            self._fill_chains(chains)
        else:
            self._fill_list(r)

    def _done_keys(self) -> list[str]:
        """The quests marked done that are this window's (a Citizenship one is listed in its own)."""
        return [k for k in self.character.quests_done
                if (q := quests.quest(self._kb, k)) is not None and q.area != "Citizenship"]

    def _card(self, q: quests.Quest) -> QuestCard:
        return QuestCard(self, q, lit=q.key == self.lit)

    def _fill_list(self, r: dict) -> None:
        """A tab's list: its head, its level chips (Skipped, Later), the closed areas (Later), the quests marked
        done, then the cards (Skipped and Later under a heading a level), 40 at a time."""
        t, c, mode = self.t, self.character, self.tab
        rows = r[mode]
        levels: dict[int, int] = {}
        for q in rows:
            levels[q.opens_at()] = levels.get(q.opens_at(), 0) + 1
        by_level = mode in ("missed", "later")
        if not by_level or self._level_pick not in levels:
            self._level_pick = None
        if self._level_pick is not None:
            rows = [q for q in rows if q.opens_at() == self._level_pick]
            self.body.addWidget(self.rich(t(f"q_head_{mode}_at", n=len(rows), lv=self._level_pick)))
        else:
            self.body.addWidget(self.rich(t(f"q_head_{mode}", n=len(rows), lv=c.level)))
        if by_level and len(levels) > 1:
            # "Level 22", its count on hover ("22 (3)" read as a riddle: the owner)
            options = [(None, t("q_all_levels"), "")] + [
                (lv, t("q_level_group", lv=lv), t("q_level_count", n=n, lv=lv)) for lv, n in sorted(
                    levels.items(), reverse=mode == "missed")]
            self.body.addWidget(self.pick_chips(options, self._level_pick, self._pick_level))
        if mode == "later":
            # the quests where the game hasn't opened yet: said, not just missing (the owner)
            closed = quests.closed_areas(self._kb)
            if closed:
                self.body.addWidget(self.label(t("q_closed_note", areas=", ".join(closed)), "Note", wrap=True))
        done = self._done_keys()
        if done:
            self.body.addWidget(self.done_link(len(done)), 0, Qt.AlignLeft)
            self.add_done(done)
        if not rows:
            self.body.addWidget(self.empty("list-checks", t("q_none"), t(f"qt_none_{mode}")))
            return
        last = None
        for q in rows[:self._limit]:
            if by_level and q.opens_at() != last:
                last = q.opens_at()          # the quests not done, level by level (the owner)
                self.body.addWidget(self.caption(t("q_level_group", lv=last)))
            self.body.addWidget(self._card(q))
        self.more_quests(len(rows), self._limit, self._more)

    def _pick_level(self, lv) -> None:
        self._level_pick = lv
        self._limit = MAX_QUESTS
        self._fill()
        self._to_top()

    def _more(self) -> None:
        self._limit += MAX_QUESTS
        self._refill()

    # ------------------------------------------------------------ the search: every quest at once

    def _fill_search(self, r: dict, query: str) -> None:
        """What the search finds in every list, a group each with its count: the tabs' lists, the quests marked
        done, and the Citizenship quests (a row each, opening the Citizenship window)."""
        t, c, kb = self.t, self.character, self._kb
        groups = [(t("qt_tab_level", lv=c.level), r["level"]), (t("qt_tab_missed"), r["missed"]),
                  (t("q_soon"), r["soon"]), (t("q_later"), r["later"]),
                  (t("q_done_head"), [q for k in reversed(self._done_keys()) if (q := quests.quest(kb, k))])]
        found = [(head, [q for q in rows if q.matches(query)]) for head, rows in groups]
        town = self._town_hits(query)
        total = sum(len(rows) for _, rows in found) + len(town)
        lit = quests.quest(kb, self.lit) if self.lit else None
        if lit is not None and not any(q.key == lit.key for _, rows in found for q in rows):
            # the quest this window was opened on, on none of the character's lists (another job's, a profession
            # level not reached): said, and its card all the same
            self.body.addWidget(self.label(t("q_after_missing", name=bidi.ltr_block(lit.name, t.rtl)), "Hint",
                                           wrap=True))
            self.body.addWidget(QuestCard(self, lit, lit=True))
            if not total:
                return
        if not total:
            self.body.addWidget(self.empty("search", t("qt_no_match"), t("qt_no_match_hint")))
            return
        self.body.addWidget(self.rich(t("qt_found", n=total)))
        left = self._limit
        for i, (head, rows) in enumerate(found):
            if not rows:
                continue
            self.body.addWidget(self.caption(f"{head} · {len(rows)}"))
            for q in rows[:max(left, 0)]:
                self.body.addWidget(QuestCard(self, q, done=i == len(found) - 1, lit=q.key == self.lit))
            left -= len(rows)
        if town:
            self.body.addWidget(self.caption(f"{t('tb_town')} · {len(town)}"))
            for q in town:
                self.body.addWidget(self._town_row(q))
        shown = sum(len(rows) for _, rows in found)
        self.more_quests(shown, self._limit, self._more)

    def _town_hits(self, query: str) -> list[quests.Quest]:
        """The Citizenship quests in the game that match, the lowest level first."""
        kb = self._kb
        open_ = availability.of(kb)
        out = [q for k, e in kb.entities.items() if e.get("category") == "quest" and open_.quest_open(k)
               and (q := quests.quest(kb, k)) and q.area == "Citizenship" and q.matches(query)]
        return sorted(out, key=lambda q: (q.opens_at(), q.name))[:MAX_QUESTS]

    def _town_row(self, q: quests.Quest) -> QFrame:
        """A Citizenship quest the search found: its name, town and level, and the way to it in its window."""
        t, rtl = self.t, self.t.rtl
        card, v = self.card()
        head = QHBoxLayout()
        head.setSpacing(8)
        name = self.label("", "CardTitle", wrap=True)
        name.setText(bidi.ltr_name(q.name, rtl))
        head.addWidget(name, 1)
        head.addWidget(self.chips([(t("lv_short", n=q.opens_at()), "Chip")]), 0, Qt.AlignTop)
        v.addLayout(head)
        town = quests.town_of(self._kb, q)
        row = QHBoxLayout()
        row.setSpacing(12)
        if town:
            row.addWidget(self.label(t("ct_town_quest", town=town), "CardSub"))
        row.addWidget(self.button(t("qt_open_town"), lambda k=q.key: NAV.tool_requested.emit("citizenship", k),
                                  "Link"))
        row.addStretch(1)
        v.addLayout(row)
        return card

    # ------------------------------------------------------------ the chains

    def _fill_chains(self, chains: dict[str, list[quests.ChainState]]) -> None:
        """The questlines: started ones first (each with the next step's whole card), the ones to start, the later
        ones, then the finished ones, a heading each with its count."""
        t = self.t
        if not any(chains.values()):
            self.body.addWidget(self.empty("list-checks", t("qt_chains_none"), t("qt_chains_none_hint")))
            return
        now = len(chains["progress"]) + len(chains["start"])      # the tab's count
        self.body.addWidget(self.rich(t("qt_chains_head", n=now) if now else t("qt_chains_head_none")))
        for status in ("progress", "start", "later", "done"):
            rows = chains[status]
            if rows:
                self.body.addWidget(self.caption(f"{t(f'qt_chains_{status}')} · {len(rows)}"))
                for s in rows:
                    self.body.addWidget(self._chain_card(s))

    def _chain_card(self, s: quests.ChainState) -> QFrame:
        """One questline: its first quest's name, how many quests over which levels, where; how far along (a bar,
        "8 of 19 done · 123,280 EXP left"); then, started, the next step's whole card; else how to start it or when
        it opens, and its steps a tap away."""
        t, rtl, kb = self.t, self.t.rtl, self._kb
        chain = s.chain
        root = quests.quest(kb, chain.root)
        steps = [q for k in chain.order if (q := quests.quest(kb, k))]
        lo, hi = min(q.opens_at() for q in steps), max(q.opens_at() for q in steps)
        card, v = self.card(lit=chain.root == self.lit or self.lit in chain)
        card.setProperty("chain", chain.root)
        head = QHBoxLayout()
        head.setSpacing(8)
        name = self.label("", "CardTitle", wrap=True)
        name.setText(bidi.ltr_name(root.name, rtl))
        head.addWidget(name, 1)
        # the range one left-to-right block: in a Hebrew chip "21–50" read "50–21"
        levels = t("lv_short", n=lo) if lo == hi else t("qt_chain_levels", span=bidi.ltr_block(f"{lo}–{hi}", rtl))
        head.addWidget(self.chips([(levels, "Chip")]), 0, Qt.AlignTop)
        v.addLayout(head)
        where = quest_town(kb, root)
        sub = t("qt_chain_quests", n=len(chain)) + (f" · {where}" if where else "")
        exp = sum(q.exp for q in steps)
        if exp:
            sub += " · " + t("qt_chain_exp", n=f"{exp:,}")
        v.addWidget(self.label(sub, "CardSub", wrap=True))
        if s.status in ("progress", "done"):
            bar = QProgressBar(objectName="ChainBar")
            bar.setRange(0, s.total)
            bar.setValue(len(s.done))
            bar.setTextVisible(False)
            bar.setAccessibleName(t("qt_chain_progress", done=len(s.done), total=s.total))
            v.addWidget(bar)
            line = t("qt_chain_progress", done=len(s.done), total=s.total)
            if s.exp_left:
                line += " · " + t("qt_chain_exp_left", n=f"{s.exp_left:,}")
            v.addWidget(self.label(line, "Note"))
        if s.status == "progress" and s.next:
            nxt = quests.quest(kb, s.next)
            if not s.open and self._waits(s):
                v.addWidget(self.label(self._waits(s), "Hint", wrap=True))
            others = [k for k in s.open if k != s.next]
            if others:
                v.addWidget(self.label(t("qt_chain_also_open", names=", ".join(
                    whole_name(quest_name(kb, k), rtl) for k in others[:3])), "Hint", wrap=True))
            v.addWidget(self.caption(t("qt_chain_next_head")))
            v.addWidget(QuestCard(self, nxt, lit=nxt.key == self.lit))
            return card
        if s.status == "start":
            first = s.open[0] if s.open else chain.root
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(self.label(t("qt_chain_start", name=whole_name(quest_name(kb, first), rtl)), "Hint",
                                     wrap=True), 1)
            row.addWidget(self.button(t("qt_chain_show_first"), lambda k=first: self.open_with(k), "Link"), 0,
                          Qt.AlignTop)
            v.addLayout(row)
        elif s.status == "later" and self._waits(s):
            v.addWidget(self.label(self._waits(s), "Hint", wrap=True))
        v.addWidget(self._steps_toggle(s))
        return card

    def _waits(self, s: quests.ChainState) -> str:
        """What the next step waits for: a level ("opens at level 47"), else the quest it asks first."""
        t, rtl = self.t, self.t.rtl
        for kind, value in s.why.get(s.next, []):
            if kind == "level":
                return t("qt_chain_opens_at", n=value)
            if kind == "after":
                return t("qt_lock_after", name=whole_name(quest_name(self._kb, value), rtl))
            if kind == "profession":
                return t("qt_profession", prof=whole_name(value[0], rtl), n=value[1])
        return ""

    def _steps_toggle(self, s: quests.ChainState) -> QWidget:
        """ "Show all 19 steps ▾": the chain's steps under it (kept open over a refill, as a card's chain is)."""
        t, rtl = self.t, self.t.rtl
        key = "chain:" + s.chain.root
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        parts: dict[str, QWidget] = {}

        def show(on: bool) -> None:
            text = t("qt_chain_steps_hide") if on else t("qt_chain_steps_show", n=s.total)
            parts["btn"].setText(bidi.button(f"{text} {CHEVRON[on]}", rtl))
            if on and "steps" not in parts:
                parts["steps"] = chain_list(self, s.chain, s)
                v.addWidget(parts["steps"])
            if "steps" in parts:
                parts["steps"].setVisible(on)

        def flip() -> None:
            on = key not in self.open_chains
            if on:
                self.open_chains.add(key)
            else:
                self.open_chains.discard(key)
            show(on)
            self.settle()
        parts["btn"] = self.button("", flip, "Link")
        v.addWidget(parts["btn"], 0, Qt.AlignLeft)
        show(key in self.open_chains)
        return wrap
