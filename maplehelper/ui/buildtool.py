"""Build & Skills over the game (the toolbar's Tools card, ui/toolwindow.py): two tabs.

Build: the character's class guide's plan (buildplan.tables: AP, SP and gear tables, the row for the character's
level lit, a first job's table of both 2nd-job paths split into one a path), with where its numbers come from and the
full guide a click away; above it the community tier list's card for the job (sitedata.tiers_for: before the 2nd job,
one card a branch). In the SP tables each changed skill (sitedata.changes_for) gets its "Changed in COT2" chip once,
its changes on hover or a click; in the gear tables each item the KB knows is a link to its page in the toolbar's Items
search (NAV.item_requested: its prices and who drops it). A Beginner, with no tables, gets the way on instead: the
skills tab and the guides.

Skills: a pick of class line (Beginner, Warrior, Magician, Bowman, Thief) and, in it, of job (the 1st job and each 2nd
job), over that job's skill book (skillbook.book): each skill's picture, name, max level, what it does, what it needs
first, and what it does at level 1 and at its max level, in Hebrew when translated. It opens on the character's own job;
the job picked in each class line is kept while the app runs (another character: its own job again).

Every colour is the glass's (npcoverlay.palette, accent_of, ink), the build text's rich text too: it is built again
when the ⚙ panel picks another tint or accent."""
from __future__ import annotations

import html
import re
from urllib.parse import quote, unquote

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QTextOption, QTextTable
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QTextBrowser, QVBoxLayout, QWidget)

from .. import bidi, buildplan, glossary, guides, sitedata, skillbook, sources
from . import terms, theme
from .controls import BalancedRow, FlowLayout, clear
from .gamesearch import rim
from .guides import ImageZoom, fit_tables
from .npcoverlay import accent_of, ink, palette
from .toolwindow import NAV, ToolWindow, _rgba
from .widgets import changed_tag, fit_picture, source_tag, tip_html, updated_tag, zoom_on_hover

# the chips' colours, readable on every dark glass tint and darkened by ink() on the white one
CHANGED = "#64B5FF"         # a skill's "Changed in COT2"
GRADES = {"S": "#4CD07D", "A": "#FFC857"}      # a tier grade: the top third, the middle (the bottom: neutral)
GRADE_W = 28                # a tier grade chip's width: S, A, B and – in one column
PICTURE_BOX, PICTURE = 40, 32       # a skill's picture box, and the game's 32 px icon in it, pixel for pixel
HINT_BADGE = "#9A9AA0"      # the grey "?" after a tier column's name (its meaning on hover), on either glass
TABLE_PX = 12               # the build tables' text
_GEAR_NAME = re.compile(r"\[\[img:[^\]]+\]\]\s*([^\[]+?)(?=\s+[+\d(]|\s*,|\s*\[\[|$)")
_badges: dict[tuple[str, int], str] = {}


def _badge(color: str, px: int) -> str:
    """A "?" badge image (terms._badge_uri) in this colour, drawn once."""
    if (color, px) not in _badges:
        _badges[(color, px)] = terms._badge_uri(color, px) or ""
    return _badges[(color, px)]


def short_skill_icons(rows: list[list[str]], icons: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """("Booster", its icon) for each full skill name the table uses ("Claw Booster"), when its last word names
    only that one skill there: a cell may name a skill short ("Booster 9" beside "Claw Booster +2")."""
    text = " ".join(" ".join(r) for r in rows)
    used = [(name, uri) for name, uri in icons if " " in name and name in text]
    by_last: dict[str, list[tuple[str, str]]] = {}
    for name, uri in used:
        by_last.setdefault(name.rsplit(" ", 1)[1], []).append((name, uri))
    return [(last, hits[0][1]) for last, hits in by_last.items() if len({n for n, _ in hits}) == 1]


def with_skill_icon(cell: str, icons: list[tuple[str, str]]) -> str:
    """Icons of the skills a table cell names ("Rush +1", "Power Strike 20, Slash Blast 3"), three at most."""
    if "[[img:" in cell:
        return ""
    found, taken = [], cell
    for name, uri in icons:
        at = re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", taken)
        if at and uri not in (u for _, u in found):
            found.append((at.start(), uri))
            taken = taken[:at.start()] + " " * len(name) + taken[at.end():]
    return "".join(f"<img src='{uri}' height='20' style='vertical-align: middle'> " for _, uri in sorted(found)[:3])


class _BuildText(QTextBrowser):
    """The build tables' rich text, as tall as its text inside the window's scrolling cards: the wheel over it
    scrolls the cards, never the text inside its box (it moved the text up and cut the first heading); a table still
    too wide at the smallest font scrolls sideways (fit_tables), the bar under it counted in the height. Its tables
    are fitted again whenever its width changes."""

    def __init__(self, scroll):
        super().__init__(objectName="BuildText")
        self._scroll = scroll
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.NoFocus)
        self.viewport().setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # breaks between words only, a wide table in a smaller font, as in the guides reader ("crafti" / "ng 1")
        self.setWordWrapMode(QTextOption.WordWrap)
        self.document().setDocumentMargin(2)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self.horizontalScrollBar().rangeChanged.connect(self._fit_height)
        self.verticalScrollBar().valueChanged.connect(lambda at: at and self.verticalScrollBar().setValue(0))

    def _fit_height(self, *_) -> None:
        bar = self.horizontalScrollBar()
        under = bar.sizeHint().height() + 2 if (self.horizontalScrollBarPolicy() != Qt.ScrollBarAlwaysOff
                                                 and bar.maximum() > 0) else 0
        self.setFixedHeight(int(self.document().size().height()) + 4 + under)

    def fit(self) -> None:
        """The tables in the width there is (once on screen: the view has no width before), the height after."""
        fit_tables(self)
        QTimer.singleShot(0, self, self._fit_height)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if e.size().width() != e.oldSize().width() and e.oldSize().width() > 0:
            QTimer.singleShot(0, self, self.fit)

    def wheelEvent(self, e) -> None:
        if abs(e.angleDelta().x()) > abs(e.angleDelta().y()):
            super().wheelEvent(e)            # sideways: a wide table
        else:
            QApplication.sendEvent(self._scroll.viewport(), e)


class BuildTool(ToolWindow):
    """The Build & Skills window (the module's docstring). open_with("build" | "skills") shows that tab."""

    SHOW_KEY = "build_tool"
    GEOM_KEY = "build_tool_geom"
    TITLE_KEY = "tb_build"
    DEFAULT_W, DEFAULT_H = 460, 660
    TABS = (("build", "build_tab_build"), ("skills", "build_tab_skills"))

    # ------------------------------------------------------------ made once

    def _build_body(self) -> None:
        self._look = None                   # the palette, accent and language the cards' rich text was built in
        self._build_key: str | None = None  # the class guide the Build tab shows
        self.build_view: QTextBrowser | None = None
        self.tier_cards: list[QFrame] = []
        self._icons: tuple[object, list[tuple[str, str]]] | None = None   # (the KB, its skills' pictures)
        self._skills_pick: tuple[str, str] | None = None      # (class line, job) the Skills tab shows
        self._skills_jobs: dict[str, str] = {}                # the job last picked in each class line
        self._skills_cid = object()                           # the character the Skills tab opened for
        # the Skills tab's picks, over its cards (they stay in view while the skills scroll)
        self._picker = QWidget()
        v = QVBoxLayout(self._picker)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.skills_class = QButtonGroup(self._picker)
        buttons = []
        for i, (cls, _) in enumerate(skillbook.class_jobs(self._kb)):
            b = QPushButton(cls, objectName="ClassChip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setProperty("value", cls)
            self.skills_class.addButton(b, i)
            buttons.append(b)
        self.skills_class.idClicked.connect(lambda i: self._pick_skills(self.skills_class.button(i).property("value"),
                                                                        None))
        v.addWidget(BalancedRow(buttons))       # five on a row when they fit, else three and two
        self._jobs_slot = QVBoxLayout()         # the class line's jobs (made again for each class line)
        self._jobs_slot.setContentsMargins(0, 0, 0, 0)
        v.addLayout(self._jobs_slot)
        self.top.addWidget(self._picker)

    def extra_qss(self) -> str:
        p = palette()
        fill, _ = accent_of(self._settings)
        lit, changed = ink(fill), ink(CHANGED)
        chip = "border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700;"
        grades = "".join(f'QLabel#Grade[grade="{g}"] {{ color: {ink(c)}; background: {_rgba(ink(c), 0.16)}; }}\n'
                         for g, c in GRADES.items())
        return f"""
QPushButton#ClassChip {{ background: {p.fill1}; color: {p.text}; border: 1px solid transparent; border-radius: 13px;
                         min-height: 24px; max-height: 24px; padding: 0 8px; font-size: 12px; font-weight: 600; }}
QPushButton#ClassChip:hover:!checked {{ background: {p.fill2}; }}
QPushButton#ClassChip:checked {{ background: {_rgba(fill, 0.16)}; color: {lit}; border: 1px solid {fill};
                                 font-weight: 700; }}
QLabel#Grade {{ color: {p.text}; background: {p.fill2}; border-radius: 6px; padding: 1px 0; font-size: 12px;
                font-weight: 800; }}
{grades}
QLabel#SourceTag {{ color: {p.muted}; background: transparent; border: 1px solid {_rgba(p.text, 0.22)};
                    border-radius: 5px; padding: 0 5px; font-size: 10px; font-weight: 700; }}
QLabel#ChangedTag {{ color: {changed}; background: {_rgba(changed, 0.16)}; {chip} }}
QLabel#UpdatedTag {{ color: {lit}; background: {_rgba(fill, 0.16)}; {chip} }}
QLabel#SkillPicture {{ background: {p.fill1}; border-radius: 8px; }}
QTextBrowser#BuildText {{ background: transparent; color: {p.text}; border: none; font-size: {TABLE_PX}px;
                          selection-background-color: {_rgba(fill, 0.35)}; }}
QTextBrowser#BuildText QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
QTextBrowser#BuildText QScrollBar::handle:horizontal {{ background: {rim(0.25, p)}; border-radius: 4px;
                                                       min-width: 30px; }}
QTextBrowser#BuildText QScrollBar::add-line:horizontal, QTextBrowser#BuildText QScrollBar::sub-line:horizontal
    {{ width: 0; }}
QTextBrowser#BuildText QScrollBar::add-page:horizontal, QTextBrowser#BuildText QScrollBar::sub-page:horizontal
    {{ background: transparent; }}
"""

    def refresh(self) -> None:
        """As every tool window's; the cards' rich text (the build tables, the "?" links) is built in the glass's
        colours, so another tint or accent picked while the window shows builds them again."""
        super().refresh()
        if self.isVisible() and self._look != self._look_now():
            self._fill()

    def open_with(self, arg: str) -> None:
        """"build" or "skills": the window on that tab (anything else leaves it as it is)."""
        if arg in {value for value, _ in self.TABS}:
            self._set_tab(arg)

    # ------------------------------------------------------------ filled

    def _look_now(self) -> tuple:
        return palette(), accent_of(self._settings), self.t.lang

    def _rebuild(self) -> None:
        self._look = self._look_now()
        clear(self.body)
        self.build_view = None
        self.tier_cards = []
        skills = self.tab == "skills"
        self._picker.setVisible(skills)
        self._top_box.setVisible(skills)
        if skills:
            self._fill_skills()
        else:
            self._fill_build()

    # ------------------------------------------------------------ pieces

    def _rich(self, text: str, name: str = "Text", seen: set | None = None) -> QLabel:
        """A wrapping label of a few lines (**bold**, each line its own paragraph in the reading order) whose game
        terms carry a "?" in the accent that explains them (glossary; seen: the terms already explained on the tab,
        one "?" each)."""
        d = "rtl" if self.t.rtl else "ltr"
        out = []
        for line in (text or "").split("\n"):
            if not line.strip():
                out.append("<p style='margin:0; font-size:5px;'>&nbsp;</p>")
                continue
            out.append(bidi.paragraph_html(line, d, style="margin:0 0 2px 0; line-height:120%;"))
        fill, _ = accent_of(self._settings)
        body = glossary.annotate("".join(out), self.t.lang, color=ink(fill), seen=seen)
        badge = _badge(fill, terms.BADGE_PX)
        if badge:       # the "?" in the glass's accent, not the app's
            body = body.replace(glossary.MARK, f"<img src='{badge}' width='{terms.BADGE_PX}' "
                                               f"height='{terms.BADGE_PX}' style='vertical-align: middle'>")
        lb = QLabel(body, objectName=name)
        lb.setTextFormat(Qt.RichText)
        lb.setWordWrap(True)
        return terms.watch(lb, self.t.lang)

    def _row(self, *widgets, stretch_after: int = -1) -> QHBoxLayout:
        """Widgets in a row from the reading start (mirrored in Hebrew); a stretch after the one at stretch_after."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for i, w in enumerate(widgets):
            row.addWidget(w, 0, Qt.AlignVCenter)
            if i == stretch_after:
                row.addStretch(1)
        if stretch_after < 0:
            row.addStretch(1)
        return row

    def _source_row(self, source: str) -> QHBoxLayout:
        """ "Data source: [COT2]", the chip's tooltip saying what that means."""
        return self._row(self.label(self.t("src_data"), "Note"), source_tag(self.t, source))

    # ------------------------------------------------------------ the Build tab

    def _fill_build(self) -> None:
        t, c, kb = self.t, self.character, self._kb
        key, tables = buildplan.tables(kb, c.base_class, c.job, c.level, t.lang)
        self._build_key = key
        head, v = self.card()
        # no tables (a Beginner): the head says so, with no "highlighted row" it doesn't have
        v.addWidget(self._rich(t("build_head", job=c.job_label or c.base_class, n=c.level) if tables
                               else t("build_none")))
        if tables:
            # the class guide's numbers: "use current COT2 data" on its page, else MeowDB's own
            row = self._source_row(sources.guide_source(kb, key) or sources.MEOWDB)
            if key:
                row.addWidget(self.button(t("build_open_guide"), lambda: NAV.guide_requested.emit(key), "Link"))
            v.addLayout(row)
        else:
            # not a card with one grey line: the way on, the skills and the guides (TOOL-19)
            beginner = next((k for k in kb.entities if k.startswith("guide/beginner")), None)
            links = QWidget()
            flow = FlowLayout(links, spacing=14, line_spacing=2)
            flow.addWidget(self.button(t("build_see_skills"), lambda: self._set_tab("skills"), "Link"))
            if beginner and not key:
                flow.addWidget(self.button(t("build_beginner_guide"), lambda: NAV.guide_requested.emit(beginner),
                                           "Link"))
            elif key:
                flow.addWidget(self.button(t("build_open_guide"), lambda: NAV.guide_requested.emit(key), "Link"))
            flow.addWidget(self.button(t("build_all_guides"), lambda: NAV.guide_requested.emit(""), "Link"))
            v.addWidget(links)
        self.body.addWidget(head)
        rows = sitedata.tiers_for(kb, c.base_class, c.job)
        for n, r in enumerate(rows):
            card = self._tier_card(r, legend=n == 0)
            self.tier_cards.append(card)
            self.body.addWidget(card)
        if tables:
            self.body.addWidget(self._build_text(tables))

    def _tier_card(self, r: sitedata.TierRow, legend: bool) -> QFrame:
        """The community tier list for one 2nd job, in plain words: a row a category, its grade (S / A / B: the
        upper, middle and lower third of the ten 2nd jobs) and its place among them; the value on the grade's
        hover, what the category measures on its name's."""
        t, rtl = self.t, self.t.rtl
        data = sitedata.tier_data(self._kb)
        level = data.get("level") or ""
        card, v = self.card()
        card.setProperty("tier", r.key)
        title = self.label(t("tier_title", job=bidi.ltr_block(r.name, rtl)), "CardTitle", wrap=True)
        src = source_tag(t, sources.COMMUNITY)
        src.setToolTip(tip_html(t("tier_tip", n=level), rtl))
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(title, 1)
        top.addWidget(src, 0, Qt.AlignTop)
        v.addLayout(top)
        if legend:
            v.addWidget(self._rich(t("tier_legend", n=level), "Hint"))
        grid = QVBoxLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setSpacing(5)
        badge = _badge(HINT_BADGE, 13)
        for col in data.get("columns") or []:
            cell = r.cells.get(col) or {}
            grade, value = cell.get("grade") or "", cell.get("value") or ""
            name, tip = self._tier_column(col)
            shown = value if value and value != "N/A" else t("tier_none")
            chip = QLabel(grade or "–", objectName="Grade", alignment=Qt.AlignCenter)
            chip.setProperty("grade", grade)
            chip.setFixedWidth(GRADE_W)
            chip.setToolTip(tip_html(f"{name}: {shown}", rtl))
            chip.setAccessibleName(f"{name}: {grade or '–'}, {shown}")
            text = html.escape(bidi.plain(name, rtl))
            if tip and badge:
                text += f"&nbsp;<img src='{badge}' width='13' height='13' style='vertical-align: middle'>"
            what = QLabel(text, objectName="Text")
            what.setTextFormat(Qt.RichText)
            if tip:
                what.setToolTip(tip_html(tip, rtl))
            place = r.ranks.get(col)
            where = self.label(t("tier_place", place=place[0], total=place[1]) if place else t("tier_none"), "Note")
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.addWidget(chip, 0, Qt.AlignVCenter)
            row.addWidget(what, 1, Qt.AlignVCenter)
            row.addWidget(where, 0, Qt.AlignVCenter)
            grid.addLayout(row)
        v.addLayout(grid)
        return card

    def _tier_column(self, col: str) -> tuple[str, str]:
        """A tier list column's short name and what it measures, in the UI language ("ST DPS" -> "Damage to one
        monster"); the site's own name when there are no words for it."""
        k = "tier_col_" + re.sub(r"[^a-z0-9]+", "_", col.lower()).strip("_")
        t = self.t
        return (t(k) if t(k) != k else col), (t(k + "_tip") if t(k + "_tip") != k + "_tip" else "")

    def _build_text(self, tables: list[buildplan.PlanTable]) -> QFrame:
        """The plan's tables in one rich text that grows to its full height in a card: the player's row lit in the
        accent, a skill's icon beside its name, a changed skill's chip, the gear's items as links."""
        t, c, kb = self.t, self.character, self._kb
        p = palette()
        fill, _ = accent_of(self._settings)
        he = t.lang != "en"
        line = _rgba(p.text, 0.16)
        icons = self._skill_icons()
        changed = sitedata.changes_for(kb, c.base_class, c.job)
        side = "dir='rtl' align='right'" if he else ""
        out = []
        split = [(path, part) for tb in tables for path, part in buildplan.split_paths(kb, tb)]
        for path, tb in split:
            heading = f"{tb.heading} · {path}" if path else tb.heading      # one table a 2nd-job path
            out.append(f"<h3 {side} style='margin: 6px 0 6px 0; font-size: 14px;'>"
                       f"{guides._rich(heading, he and bool(bidi._RTL.search(heading)))}</h3>")
            rows = tb.rows
            if tb.kind == "sp" and he:
                # Hebrew shows the table from the right: "spend SP on" first and its result in the middle, beside it
                rows = [[r[0], r[2], r[1], *r[3:]] if len(r) >= 3 else r for r in rows]
            names = icons + short_skill_icons(rows, icons) if tb.kind == "sp" else icons
            chips = self._change_chips(rows, changed) if tb.kind == "sp" else {}
            cells = []
            for n, row in enumerate(rows):
                tag = "th" if n == 0 else "td"
                weight = "font-weight:700;" if n == tb.current else ""
                parts = []
                for i, x in enumerate(row):
                    rtl_cell = he and bool(bidi._RTL.search(x))
                    rich = guides._rich(x, rtl_cell, 18)
                    if tb.kind == "gear" and n:
                        rich = self._gear_links(x, rich)
                    pic = with_skill_icon(x, names) if tb.kind == "sp" and n else ""
                    parts.append(f"<{tag}><p {'dir=rtl align=right' if rtl_cell else ''} "
                                 f"style='margin:0;{weight}'>{pic}{rich}{chips.get((n, i), '')}</p></{tag}>")
                cells.append("<tr>" + "".join(parts) + "</tr>")
            # one line between two cells (a border a cell drew two, side by side)
            out.append(f"<table {side} width='100%' cellspacing='0' cellpadding='5' border='1' "
                       f"style='border-collapse: collapse; border-color: {line}; border-style: solid; "
                       f"margin: 2px 0 10px 0;'>"
                       f"{''.join(cells)}</table>")
        card, v = self.card()
        v.setContentsMargins(8, 4, 8, 6)
        view = _BuildText(self._scroll)
        # a skill's "Changed in COT2" chip: its changes on hover, and on a click (touch); an item: its page
        view.highlighted.connect(lambda url: self._skill_change_tip(url.toString()))
        view.anchorClicked.connect(lambda url: self._build_link(url.toString()))
        view.setLayoutDirection(Qt.RightToLeft if he else Qt.LeftToRight)
        opt = view.document().defaultTextOption()
        opt.setTextDirection(Qt.RightToLeft if he else Qt.LeftToRight)
        view.document().setDefaultTextOption(opt)
        view.document().setDefaultStyleSheet(f"a {{ color: {ink(fill)}; text-decoration: none; }}")
        view.setHtml("\n".join(out))
        self._light_rows(view, [tb.current for _, tb in split], p, fill)
        ImageZoom(view)                 # a picture in the tables shows large on hover
        v.addWidget(view)
        self.build_view = view
        view.fit()                      # measured once the card is on screen
        return card

    @staticmethod
    def _light_rows(view: QTextBrowser, current: list[int | None], p, fill: str) -> None:
        """Each table's heading row in a faint fill and the player's row in the accent, see-through on the glass.
        Set on the cells themselves: a cell's background in the HTML was given to each paragraph in it too, a
        second see-through box over the first."""
        head, now = theme.qcolor(_rgba(p.text, 0.08)), theme.qcolor(_rgba(fill, 0.24))
        tabs = [f for f in view.document().rootFrame().childFrames() if isinstance(f, QTextTable)]
        for table, lit in zip(tabs, current):
            for r, color in ((0, head), (lit, now)):
                if r is None or r >= table.rows():
                    continue
                for c in range(table.columns()):
                    cell = table.cellAt(r, c)
                    fmt = cell.format().toTableCellFormat()
                    fmt.setBackground(color)
                    cell.setFormat(fmt)

    def _change_chips(self, rows: list[list[str]], changed: list) -> dict[tuple[int, int], str]:
        """(row, column) -> the "Changed in COT2" chips of the skills a SP table cell names, each skill only where
        the table first names it (a chip on every "Final Attack: Axe +n" row was noise). Only the "spend" and
        "result" columns (1 and 2, in either language's order) name skills; the reasons are prose."""
        fg = ink(CHANGED)
        bg = _rgba(fg, 0.18)
        out: dict[tuple[int, int], str] = {}
        done: set[str] = set()
        for n, row in enumerate(rows[1:], start=1):
            for i in (1, 2):
                cell = row[i] if i < len(row) else ""
                for ch in changed:
                    if ch.key in done or not re.search(rf"(?<![\w:]){re.escape(ch.name)}(?![\w:])", cell):
                        continue
                    done.add(ch.key)
                    label = html.escape(sitedata.chip_label(self.t, ch)).replace(" ", "&nbsp;")
                    out[(n, i)] = out.get((n, i), "") + (
                        f" <a href='change:{ch.key}' style='text-decoration: none;'><span style='color: {fg}; "
                        f"background-color: {bg}; font-size: 11px; font-weight: 700;'>&nbsp;{label}&nbsp;</span></a>")
        return out

    def _gear_links(self, raw: str, rendered: str) -> str:
        """A gear table cell with each item the KB knows a link: a click opens its page (its prices, who drops it)."""
        color = ink(accent_of(self._settings)[0])
        for m in _GEAR_NAME.finditer(raw):
            name = m.group(1).strip()
            if not self._kb._item_by_name.get(name.lower()):
                continue
            # an English name in a Hebrew cell is one block, its spaces no-break ones (guides._rich, bidi)
            escaped = [html.escape(name, quote=False), html.escape(name)]
            for shown in dict.fromkeys(escaped + [s.replace(" ", "\xa0") for s in escaped]):
                at = rendered.find(shown)
                if at >= 0 and rendered.rfind("<", 0, at) <= rendered.rfind(">", 0, at):      # text, not a tag
                    rendered = (rendered[:at] + f"<a href='item:{quote(name)}' style='color:{color}; "
                                f"text-decoration:none; font-weight:600;'>{shown}</a>" + rendered[at + len(shown):])
                    break
        return rendered

    def _build_link(self, link: str) -> None:
        """A click in the build tables: an item's page (NAV.item_requested), or a skill's changes."""
        if not link.startswith("item:"):
            self._skill_change_tip(link)
            return
        key = self._kb._item_by_name.get(unquote(link[5:]).lower())
        if key:
            terms.hide()
            NAV.item_requested.emit(key)

    def _skill_change_tip(self, link: str) -> None:
        """A changed skill's chip under the mouse: what changed, in the explanation card beside it."""
        if not link.startswith("change:"):
            terms.hide()
            return
        ch = sitedata.skill_change(self._kb, link.partition(":")[2])
        if ch:
            terms.show_html(bidi.to_html(sitedata.change_tip(self.t, ch, self._kb), "rtl" if self.t.rtl else "ltr"),
                            self.t.rtl)

    def _skill_icons(self) -> list[tuple[str, str]]:
        """(skill name, picture file URI) of every skill in the KB, longest names first so "Power Strike" wins over
        "Power"; read once a KB."""
        if self._icons is None or self._icons[0] is not self._kb:
            out = []
            for k, e in self._kb.entities.items():
                if e.get("category") == "skill":
                    path = self._kb.picture(k)
                    if path:
                        out.append((e["name"], path.as_uri()))
            self._icons = (self._kb, sorted(out, key=lambda x: -len(x[0])))
        return self._icons[1]

    # ------------------------------------------------------------ the Skills tab

    def _pick_skills(self, cls: str, job: str | None) -> None:
        """A class line (on the job last picked in it, else its 1st job) or one of its jobs; its list from the top."""
        shown = dict(skillbook.class_jobs(self._kb)).get(cls) or ["Beginner"]
        if job not in shown:
            job = self._skills_jobs.get(cls) if self._skills_jobs.get(cls) in shown else shown[0]
        self._skills_jobs[cls] = job
        self._skills_pick = (cls, job)
        self._fill()
        self._to_top()

    def _fill_skills(self) -> None:
        t, c, kb = self.t, self.character, self._kb
        cid = c.id if c else None
        if cid != self._skills_cid:
            # the character's own class line and job first (another character: theirs); the picks made by hand
            # stay while it is the same one
            self._skills_cid = cid
            cls, job = skillbook.default_tab(c.base_class if c else None, c.job if c else None, kb)
            self._skills_jobs = {cls: job}
            self._skills_pick = (cls, job)
        cls, job = self._skills_pick or ("Beginner", "Beginner")
        for b in self.skills_class.buttons():
            b.setChecked(b.property("value") == cls)
            b.setAccessibleDescription(t("skills_class_a11y"))
        clear(self._jobs_slot)
        jobs = dict(skillbook.class_jobs(kb)).get(cls) or []
        if len(jobs) > 1:
            self._jobs_slot.addWidget(self._job_tabs(cls, jobs, job))
        skills = skillbook.book(kb).get(job) or []
        head = QWidget()
        row = QHBoxLayout(head)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(6)
        row.addWidget(self._rich(t("skills_head", job=bidi.ltr_block(job, t.rtl), n=len(skills))), 1)
        if skills:
            row.addLayout(self._source_row(sources.MEOWDB))
        self.body.addWidget(head)
        if not skills:
            self.body.addWidget(self.empty("dumbbell", t("skills_none", job=bidi.ltr_block(job, t.rtl))))
            return
        seen: set = set()            # one "?" per game term on the tab, not one per card
        for s in skills:
            self.body.addWidget(self._skill_card(s, seen))

    def _job_tabs(self, cls: str, jobs: list[str], job: str) -> QFrame:
        """A class line's jobs as segments of one capsule, on one row when they fit, else two rows of two: a row of
        four ("Magician", "F/P Wizard", "I/L Wizard", "Cleric") squeezed its labels into each other."""
        t = self.t
        box = QFrame(objectName="Segmented")
        box.setAccessibleName(t("skills_job_a11y"))
        lay = QVBoxLayout(box)
        lay.setContentsMargins(2, 2, 2, 2)
        group = QButtonGroup(box)
        buttons = []
        for j in jobs:
            b = QPushButton(bidi.ltr_name(j, t.rtl), objectName="Segment")      # one block, no "/" joiner
            b.setCheckable(True)
            b.setChecked(j == job)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setProperty("value", j)
            b.setAccessibleDescription(t("skills_job_a11y"))
            group.addButton(b)
            buttons.append(b)
        group.buttonClicked.connect(lambda b, k=cls: self._pick_skills(k, b.property("value")))
        lay.addWidget(BalancedRow(buttons, spacing=2))
        return box

    def _skill_card(self, s: skillbook.Skill, seen: set) -> QFrame:
        """A skill: its picture, name, max level and chips, what it does, what it needs first, what it does at level
        1 and at its max level (all of it, always), and Ask in chat."""
        t, lang, rtl = self.t, self.t.lang, self.t.rtl
        card = QFrame(objectName="Card")
        card.setProperty("skill", s.key)
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)
        pic = QLabel(objectName="SkillPicture", alignment=Qt.AlignCenter)
        pic.setFixedSize(PICTURE_BOX, PICTURE_BOX)
        pm = QPixmap(str(s.picture)) if s.picture else QPixmap()
        if not pm.isNull():
            pic.setPixmap(fit_picture(pm, PICTURE, PICTURE, pic))         # the game's 32 px icon, pixel for pixel
            zoom_on_hover(pic, s.picture)
        row.addWidget(pic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        name = self.label("", "CardTitle", wrap=True)
        name.setText(bidi.ltr_name(s.name, rtl))                           # the game's English name
        col.addWidget(name)
        chips = QWidget()
        flow = FlowLayout(chips, spacing=4, line_spacing=4)
        if s.max_lv:
            flow.addWidget(QLabel(bidi.plain(t("skill_max_lv", n=s.max_lv), rtl), objectName="Chip"))
        for chip in (changed_tag(t, self._kb, s.key), updated_tag(t, self._kb, s.key)):
            if chip:
                flow.addWidget(chip)
        if flow.count():
            col.addWidget(chips)
        desc = self._rich(skillbook.text(self._kb, s, "desc", lang), "Text", seen)
        desc.setProperty("part", "desc")
        col.addWidget(desc)
        if s.prereq:
            # the skill's name one block in both languages: a "?" for "MP" split "MP Eater" in two (glossary.py
            # leaves an LRI block whole)
            need = self._rich(t("skill_requires", name=f"{bidi.LRI}{s.prereq[0]}{bidi.PDI}", n=s.prereq[1]), "Hint")
            need.setProperty("part", "needs")
            col.addWidget(need)
        for part, head in (("lv1", t("skill_lv1")), ("max", t("skill_lv_max", n=s.max_lv or "MAX"))):
            line = skillbook.text(self._kb, s, part, lang)
            if line:
                fx = self._rich(f"**{head}** {line}", "Hint", seen)
                fx.setProperty("part", part)
                col.addWidget(fx)
        # a question for the chat, plain text: the no-break spaces I18n keeps a short English name whole with in a
        # Hebrew line are for display only
        ask = self.button(t("ask_short"), lambda: NAV.ask_requested.emit(
            t("bt_ask_skill", name=s.name, job=s.job).replace("\xa0", " ")), "Link")
        col.addWidget(ask, 0, Qt.AlignLeft)         # the reading start (mirrored in Hebrew)
        row.addLayout(col, 1)
        return card
