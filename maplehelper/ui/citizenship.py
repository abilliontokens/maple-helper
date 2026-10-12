"""Citizenship over the game (the toolbar's Tools card, ui/toolwindow.py), ported from the old Play tools' town page.

The tabs are the towns with citizenship (quests.TOWNS: Henesys, Kerning City); the one picked is the character's
(Character.town, saved), the class guide's town until one is picked (buildplan.citizenship_advice). Under them: the
guide's advice for the character's job (the town it recommends, where to sign up: the town's clerk, a tap away; why
that town, the citizen grades and towns in bold, each NPC with the town it stands in), what citizenship is; then the
town's citizenship quests the character can do now (quests.citizenship), grade by grade (a chip a grade: that grade's
only), with when the next grade's quests open, "Show quests marked done" (donations repeat: one marked done comes
back), 40 cards at a time. The search above looks through the town's quests by name or item. Under level 12 there
is one card: when citizenship opens. A quest's card is ui/questcard.py's, shared with the Quests window.

open_with(key): that quest's town (quests.town_of, saved as the character's), every grade, the search set to its
name, its card lit."""
from __future__ import annotations

import html
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .. import bidi, buildplan, crafting, guides, quests
from .controls import clear
from .npcoverlay import accent_of, ink
from .questcard import CHEVRON, MAX_QUESTS, QuestCard, QuestWindow, card_qss
from .toolwindow import NAV, ToolWindow

OPENS_AT = 12           # citizenship's level (the game's, the guides')
SEARCH_MS = 200         # a pause in the search's typing before the cards are read again
# the citizen grades the guides name: they stand out in the advice, as the towns do
CITIZEN_GRADES = ("Helpful Stranger", "Distinguished Citizen", "Guardian of the Village")
_CLERK = re.compile(r"^(Town Clerk|City Clerk)$", re.M)
# a sentence of the guide that only says what to pick or where to sign up: the card says that itself
_PICK = re.compile(r"best|הכי טוב|הטובה|ממליץ|Pick |\bsign|נרשמ|להירשם|תבחרו|תירשמו", re.I)


def bold_names(text: str) -> str:
    """Citizen grades and the towns stand out in a long piece of advice."""
    for name in CITIZEN_GRADES + quests.TOWNS:
        text = re.sub(rf"(?<!\*)\b{re.escape(name)}\b(?!\*)", f"**{name}**", text)
    return text


def grade(q: quests.Quest) -> int:
    """The citizenship grade a quest asks (0: none)."""
    return q.grade[1] if q.grade else 0


class Citizenship(QuestWindow, ToolWindow):
    """The Citizenship window (the module's docstring)."""

    SHOW_KEY = "citizenship"
    GEOM_KEY = "citizenship_geom"
    TITLE_KEY = "tb_town"
    MIN_W, MIN_H = 380, 440
    DEFAULT_W, DEFAULT_H = 440, 680
    TABS = tuple((town, town) for town in quests.TOWNS)    # a town's in-game name, in both languages

    # ------------------------------------------------------------ made once

    def _build_body(self) -> None:
        self._quests_state()
        self._limit = MAX_QUESTS            # cards the list shows ("Show more quests" adds 40)
        self._grade_pick = None             # the grade picked by its chip (None: every grade)
        self._why_open = False              # the guide's reasons for its town, shown
        self.search = self.key_box(self.t("town_search"))
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=SEARCH_MS, timeout=self._searched)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        self.search.entered.connect(self._searched)
        self.top.addWidget(self.search)

    def _retext(self) -> None:
        super()._retext()
        t = self.t
        self.search.setPlaceholderText(bidi.plain(t("town_search"), t.rtl))
        self.search.setAccessibleName(t("town_search"))

    def extra_qss(self) -> str:
        return card_qss(self._settings)

    def _set_tab(self, tab: str) -> None:
        """A town picked: the character's citizenship town from now on (saved), its list from the top, every grade."""
        c = self.character
        if c is not None and c.town != tab:
            c.town = tab
            self._profiles.save()
        self._grade_pick = None
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
        """A Citizenship quest's key: its town (saved as the character's), every grade, the search set to its name
        (one marked done: among the done ones it finds; one above the character's level: apart, with when it
        opens), its card lit. Any other quest: the Quests window on it."""
        q = quests.quest(self._kb, arg)
        if q is None:
            return
        if q.area != "Citizenship":
            NAV.tool_requested.emit("quest_tool", arg)
            return
        if self.character is None:
            return
        self.lit = arg
        self.search.blockSignals(True)
        self.search.setText(q.name)
        self.search.blockSignals(False)
        self._set_tab(quests.town_of(self._kb, q) or self.tab)
        self.scroll_to_lit()

    def open_quest(self, key: str) -> None:
        """A step of a chain or a prerequisite clicked on a card: that quest (open_with)."""
        self.open_with(key)

    # ------------------------------------------------------------ filled

    def _rebuild(self) -> None:
        self._look = self._look_now()
        self.expire_cycles()
        t, c, kb = self.t, self.character, self._kb
        clear(self.body)
        locked = c.level < OPENS_AT
        # under level 12, one card: when it opens. A town to pick and a search over no list asked for what can't be
        # done yet (TOOL-18, TL2-12)
        self.search.setVisible(not locked)
        if self._tabs is not None:
            self._tabs.setVisible(not locked)
        if locked:
            n = OPENS_AT - c.level
            self.body.addWidget(self.empty("landmark", t("ct_locked_title", lv=OPENS_AT), t("ct_locked_hint", n=n)))
            return
        rec, paras = buildplan.citizenship_advice(kb, c.base_class, c.job, t.lang)
        town = c.town if c.town in quests.TOWNS else rec or quests.TOWNS[0]
        if town != self.tab:
            self.tab = town
            if self._tabs is not None:
                self._tabs.set_value(town)
        query = self.search.text().strip()
        if not query:
            self.body.addWidget(self._advice(rec, paras, town))
        self._fill_town(town, query)

    def _advice(self, rec: str | None, paras: list[str], town: str) -> QFrame:
        """The class guide's word on citizenship: the town it recommends for the job, where to sign up in the town
        picked (its clerk), why that town (a tap away), and what citizenship is."""
        t, c, kb, rtl = self.t, self.character, self._kb, self.t.rtl
        card, v = self.card()
        v.addWidget(self.caption(t("town_title")))
        if rec:
            v.addWidget(self.label(t("town_recommended_short", town=rec, job=c.job or c.base_class), "CardTitle",
                                   wrap=True))
        else:
            v.addWidget(self.label(t("town_no_advice"), "Text", wrap=True))
        clerk = next(((k, e["name"], crafting._town(kb, k)) for k, e in kb.entities.items()
                      if e.get("category") == "npc" and crafting._town(kb, k).startswith(town)
                      and _CLERK.search(kb.page(k))), None)
        if clerk:
            key, name, place = clerk
            color = ink(accent_of(self._settings)[0])
            link = (f"<a href='{key}' style='color:{color}; text-decoration:none'>{bidi.LRE}{html.escape(name)}"
                    f"{bidi.PDF}</a>")
            text = html.escape(t("town_sign", npc="\ue000", place=bidi.ltr_block(place, rtl))).replace("\ue000", link)
            side = "dir='rtl' align='right'" if rtl else "dir='ltr' align='left'"
            sign = _link_label(f"<p {side} style='margin:0'>{text}</p>", "CardSub")
            sign.linkActivated.connect(NAV.npc_requested.emit)
            v.addWidget(sign)
        reasons = self._reasons(paras) if rec else []
        if reasons:
            box = QWidget()
            col = QVBoxLayout(box)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(4)
            # the town one block, so a Hebrew question mark ends the sentence, not the name ("Kerning City?")
            why = self.button(f"{t('ct_why', town=bidi.ltr_block(rec, rtl))} {CHEVRON[self._why_open]}",
                              self._toggle_why, "Link")
            col.addWidget(why, 0, Qt.AlignLeft)
            if self._why_open:
                col.addWidget(self.rich("\n".join("• " + bold_names(self._npc_towns(x)) for x in reasons), "Detail"))
            v.addWidget(box)
        v.addWidget(self.rich(t("town_basics"), "Note"))
        return card

    def _toggle_why(self) -> None:
        self._why_open = not self._why_open
        self._refill()

    @staticmethod
    def _reasons(paras: list[str]) -> list[str]:
        """The guide's sentences on why its town, without the ones that only say to pick it or where to sign up."""
        sentences = [x.strip() for para in paras[:2]
                     for x in re.split(r"(?<=[.!?])\s+", guides._ICON.sub("", para).strip()) if x.strip()]
        return [x for x in (re.sub(r"\*\*", "", s) for s in sentences) if not _PICK.search(x)]

    def _npc_towns(self, text: str) -> str:
        """Each NPC a sentence names, with the town it stands in: "Raymond (in Henesys) sells ..." ("Raymond" alone
        said nothing: the owner)."""
        kb, done = self._kb, set()

        def one(m):
            name = m.group(0)
            key = kb._npc_by_name.get(name.lower())
            if not key or name in done:
                return name
            done.add(name)
            town = crafting._town(kb, key)
            return f"{name} ({self.t('in_town', town=town)})" if town and town not in text and town != name else name
        return re.sub(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)?\b", one, text)

    def _fill_town(self, town: str, query: str) -> None:
        """The town's quests the character can do now: the head, a chip a grade, when the next grade's open, the
        ones marked done, then the cards grade by grade, 40 at a time. Searched: what matches, the ones marked done
        that match after them."""
        t, c, kb = self.t, self.character, self._kb
        rows = sorted(quests.citizenship(kb, town, c.level, c.quests_done), key=lambda q: (grade(q), -q.exp))
        mine = [k for k in c.quests_done
                if (q := quests.quest(kb, k)) and q.area == "Citizenship" and quests.town_of(kb, q) == town]
        # the quest this window was opened on when it isn't open at the character's level yet (a step of a chain):
        # when it opens, and its card, apart
        lit = quests.quest(kb, self.lit) if self.lit else None
        if lit is None or lit.key in c.quests_done or lit.opens_at() <= c.level or quests.town_of(kb, lit) != town:
            lit = None
        if query:
            rows = [q for q in rows if q.matches(query)]
            done = [q for k in reversed(mine) if (q := quests.quest(kb, k)) and q.matches(query)]
            n = len(rows) + len(done) + (lit is not None)
            if not n:
                self.body.addWidget(self.empty("search", t("qt_no_match"), t("ct_no_match_hint", town=town)))
                return
            self.body.addWidget(self.rich(t("qt_found", n=n)))
            self._lit_card(lit)
            self._cards(rows)
            if done:
                self.body.addWidget(self.caption(f"{t('q_done_head')} · {len(done)}"))
                for q in done[:MAX_QUESTS]:
                    self.body.addWidget(QuestCard(self, q, done=True, lit=q.key == self.lit))
            return
        grades: dict[int, int] = {}
        for q in rows:
            grades[grade(q)] = grades.get(grade(q), 0) + 1
        if self._grade_pick not in grades:
            self._grade_pick = None
        self.body.addWidget(self.rich(t("town_head", n=len(rows), town=town)))
        if len(grades) > 1:
            # "Grade 2" on the chip: the window is citizenship already; the full name on hover (three rows of
            # "Citizenship grade N" chips, TOOL-16)
            options = [(None, t("town_all_grades"), "")] + [
                (g, t("town_grade_chip", n=g), t("town_grade_group", n=g)) if g else (g, t("town_no_grade"), "")
                for g in sorted(grades)]
            self.body.addWidget(self.pick_chips(options, self._grade_pick, self._pick_grade))
        # the next grade's quests: from which level (only the grades open at this level have chips: "is there only
        # one grade?", the owner)
        top = max(grades, default=0)
        later = sorted((q.grade[1], q.opens_at()) for k, e in kb.entities.items() if e.get("category") == "quest"
                       for q in [quests.quest(kb, k)] if q and q.area == "Citizenship" and q.grade
                       and quests.town_of(kb, q) == town and q.grade[1] > top)
        if later:
            self.body.addWidget(self.label(t("town_next_grade", n=later[0][0], lv=later[0][1], last=later[-1][0]),
                                           "Note", wrap=True))
        if self._grade_pick is not None:
            rows = [q for q in rows if grade(q) == self._grade_pick]
        if mine:
            # donations repeat: one marked done comes back. Under the head: after 38 cards it was out of reach
            self.body.addWidget(self.done_link(len(mine)), 0, Qt.AlignLeft)
            self.add_done(mine)
        self._lit_card(lit)
        if not rows and lit is None:
            self.body.addWidget(self.empty("landmark", t("q_none")))
        self._cards(rows)

    def _lit_card(self, q: quests.Quest | None) -> None:
        if q is not None:
            self.body.addWidget(self.caption(self.t("qt_chain_opens_at", n=q.opens_at())))
            self.body.addWidget(QuestCard(self, q, lit=True))

    def _cards(self, rows: list[quests.Quest]) -> None:
        """The quests grade by grade (as the Quests window's are level by level), 40 at a time."""
        t = self.t
        last = None
        for q in rows[:self._limit]:
            if grade(q) != last:
                last = grade(q)
                self.body.addWidget(self.caption(t("town_grade_group", n=last) if last else t("town_no_grade")))
            self.body.addWidget(QuestCard(self, q, lit=q.key == self.lit))
        self.more_quests(len(rows), self._limit, self._more)

    def _pick_grade(self, g) -> None:
        self._grade_pick = g
        self._limit = MAX_QUESTS
        self._fill()
        self._to_top()

    def _more(self) -> None:
        self._limit += MAX_QUESTS
        self._refill()


def _link_label(text: str, name: str) -> QLabel:
    """A rich-text line whose links act (the clerk's name)."""
    lb = QLabel(text, objectName=name)
    lb.setTextFormat(Qt.RichText)
    lb.setWordWrap(True)
    lb.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
    return lb
