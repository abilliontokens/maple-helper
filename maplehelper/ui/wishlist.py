"""The wishlist window: each wished item, who drops it (community-reported droppers first, then the reference
list, each lowest level first) and where they live. Its search box (EntityPicker) puts any item on the list."""
from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from .. import availability, bidi, farm, quick, sitedata, sources
from ..i18n import I18n
from ..kb import KnowledgeBase, memo
from . import theme
from .controls import FlowLayout, clear, follow_typing, rtl_buttons
from .glass import GlassDialog
from .patchnotes import gutter
from .widgets import (EntityCard, chip_row, fit_picture, info_tag, name_lv, source_tag, source_tags, updated_tag,
                      vote_tag, zoom_on_hover)

NAME_ROLE = Qt.UserRole + 1
PATH_ROLE = Qt.UserRole + 2
FIND_ROLE = Qt.UserRole + 3         # what the list filters on: the name, plus a misspelling it is close to


def item_rows(kb) -> list[tuple[str, str, object]]:
    """The search box's rows: every item once, by name, with its picture. Made once per KB: the window is made anew
    each time it opens, and the list read ~650 pages every time (PERF-05)."""
    cache = memo(kb, "_wishlist_rows")
    if "items" not in cache:
        seen = {}
        for k, e in kb.entities.items():
            if e.get("category") == "item" and e["name"].strip() and e["name"] not in seen:
                if str(e.get("type") or "").startswith("Cash") and sitedata.untradeable(kb, k):
                    continue          # a pet: the Cash Shop's NX only, no price to look up (the owner)
                seen[e["name"]] = k
        cache["items"] = [(name, name, kb.picture(k)) for name, k in sorted(seen.items(), key=lambda x: x[0].lower())]
    return cache["items"]


def _close(typed: str, name: str) -> bool:
    """A misspelt word of the search is close to a word of the name ("stelly" -> "Steely Throwing Knives")."""
    from difflib import SequenceMatcher
    words = [w for w in re.split(r"[\s:'().,-]+", name.lower()) if len(w) >= 3]
    asked = [w for w in re.split(r"\s+", typed.lower()) if w]
    if not asked or not words:
        return False
    return all(any(w.startswith(a) or (len(a) >= 4 and SequenceMatcher(None, a, w[:len(a) + 1]).ratio() >= 0.8)
                   or (len(a) >= 4 and SequenceMatcher(None, a, w).ratio() >= 0.8) for w in words) for a in asked)


class _LazyIcons(QStandardItemModel):
    """Pictures loaded when the list first shows their row: scaling ~3,000 item pictures up front took half a
    second of the window's opening."""

    def __init__(self, parent, size: int):
        super().__init__(parent)
        self._size = size
        self._icons: dict[str, QIcon] = {}

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DecorationRole:
            path = super().data(index, PATH_ROLE)
            if not path:
                return None
            if path not in self._icons:
                pm = QPixmap(path)
                self._icons[path] = QIcon(fit_picture(pm, self._size, self._size))
            return self._icons[path]
        return super().data(index, role)


class EntityPicker(QLineEdit):
    """A search box that opens a list of names with pictures; typing narrows it down.
    rows: (shown text, name to put in the box, picture path or None)."""
    picked = Signal()

    def __init__(self, rows: list[tuple[str, str, object]], placeholder: str, icon: int = 36, rtl: bool = False):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setAccessibleName(placeholder)         # a placeholder isn't read as the field's name
        self._icon = icon
        model = self._model(rows)
        comp = QCompleter(self)
        comp.setCompletionRole(FIND_ROLE)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        comp.setMaxVisibleItems(9)
        comp.popup().setIconSize(QSize(icon, icon))
        comp.popup().setTextElideMode(Qt.ElideNone)       # a long name stays whole, on two lines
        comp.popup().setWordWrap(True)
        # every row's height from the first one: otherwise the list measures (and loads the picture of) all
        # ~2,500 rows before it shows nine
        comp.popup().setUniformItemSizes(True)
        c = theme.P()
        bg = "#2C2C2E" if theme.MODE == "dark" else "#FFFFFF"
        comp.popup().setStyleSheet(
            f"QListView {{ background: {bg}; color: {c['text']}; border: 1px solid {c['stroke']}; border-radius: 10px;"
            f" padding: 4px; outline: none; }}"
            f"QListView::item {{ padding: 4px 6px; border-radius: 8px; color: {c['text']}; }}"
            f"QListView::item:selected, QListView::item:hover {{ background: {theme.accent_rgba(0.22)}; color: {c['text']}; }}")
        comp.setModel(model)          # after the style: polishing a full list measured every row
        comp.activated.connect(lambda *_: QTimer.singleShot(0, self._chosen))
        self.setCompleter(comp)
        # as tall as its rows: a two-row list opened a nine-row box with a scrollbar into blank space (the owner)
        comp.popup().installEventFilter(self)
        cm = comp.completionModel()       # typing narrows the list: the box follows
        for sig in (cm.modelReset, cm.layoutChanged, cm.rowsInserted, cm.rowsRemoved):
            sig.connect(self._fit_soon)     # a method, not a lambda: cut off when the picker is deleted
        self.returnPressed.connect(self.picked.emit)
        # a misspelt name ("stelly") found nothing: the names close to it are offered (the owner)
        self.textEdited.connect(self._near_names)
        # a chevron says "this opens a list" before anyone clicks
        arrow = self.addAction(self._chevron(), QLineEdit.TrailingPosition)
        arrow.triggered.connect(self.open_list)
        # an X in the accent beside it while something is typed: Qt's own clear button didn't show (the owner)
        self._clear = self.addAction(self._cross(), QLineEdit.TrailingPosition)
        self._clear.triggered.connect(lambda: (self.clear(), self.setFocus()))
        self._clear.setVisible(False)
        self.textChanged.connect(lambda text: self._clear.setVisible(bool(text)))
        self.setMinimumHeight(34)
        follow_typing(self, rtl)

    def _model(self, rows: list[tuple[str, str, object]]):
        model = _LazyIcons(self, self._icon)
        for shown, name, path in rows:
            item = QStandardItem(shown)
            item.setData(name, NAME_ROLE)
            item.setData(name, FIND_ROLE)
            if path:
                item.setData(str(path), PATH_ROLE)      # the picture itself: when its row is first shown
            item.setEditable(False)
            model.appendRow(item)
        return model

    @staticmethod
    def _chevron() -> QIcon:
        from PySide6.QtGui import QColor, QPainter, QPen
        pm = QPixmap(20, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.accent_text(deep=True)), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPoint(5, 8), QPoint(10, 13), QPoint(15, 8)])
        p.end()
        return QIcon(pm)

    def _near_names(self, text: str) -> None:
        """No name holds what was typed: the names close to it hold it too, so the list shows them."""
        model = self.completer().model()
        typed = text.strip()
        rows = [model.item(i) for i in range(model.rowCount())]
        for it in rows:
            if it.data(FIND_ROLE) != it.data(NAME_ROLE):
                it.setData(it.data(NAME_ROLE), FIND_ROLE)
        if len(typed) < 4 or any(typed.lower() in str(it.data(NAME_ROLE)).lower() for it in rows):
            return
        for it in rows:
            if _close(typed, str(it.data(NAME_ROLE))):
                it.setData(f"{it.data(NAME_ROLE)}\u2063{typed}", FIND_ROLE)

    def setText(self, text: str) -> None:
        # set with its signals held back: the X still shows
        super().setText(text)
        self._clear.setVisible(bool(text))

    def clear(self) -> None:
        super().clear()
        self._clear.setVisible(False)

    @staticmethod
    def _cross() -> QIcon:
        from PySide6.QtGui import QColor, QPainter, QPen
        pm = QPixmap(20, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.accent_text(deep=True)), 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPoint(6, 6), QPoint(14, 14))
        p.drawLine(QPoint(14, 6), QPoint(6, 14))
        p.end()
        return QIcon(pm)

    def _chosen(self):
        # a close name picked: the box holds the name itself, not the misspelling it was found by
        text = self.text()
        if "\u2063" in text:
            self.setText(text.split("\u2063", 1)[0])
        self.setCursorPosition(0)              # a long name shows from its start
        self.picked.emit()

    def open_list(self):
        comp = self.completer()
        comp.setCompletionPrefix(self.text())
        comp.popup().setMinimumWidth(max(self.width(), 440))
        comp.complete()

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self.open_list()                      # a click shows the whole list, not only after typing

    def eventFilter(self, obj, e):
        comp = self.completer()
        if comp is not None and obj is comp.popup() and e.type() in (QEvent.Show, QEvent.Resize):
            QTimer.singleShot(0, self, self._fit_popup)     # with self: never fires once the picker is deleted
        return super().eventFilter(obj, e)

    def _fit_soon(self, *_) -> None:
        QTimer.singleShot(0, self, self._fit_popup)

    def _fit_popup(self) -> None:
        comp = self.completer()
        pop = comp.popup() if comp else None
        if pop is None or not pop.isVisible():
            return
        n = min(comp.completionCount(), comp.maxVisibleItems())
        if n <= 0:
            return
        rows = sum(pop.sizeHintForRow(i) for i in range(n))
        chrome = pop.height() - pop.viewport().height()       # frame, padding: what the rows don't fill
        h = rows + max(chrome, 2 * pop.frameWidth())
        if abs(pop.height() - h) > 1:
            pop.setFixedHeight(h)
        pop.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if comp.completionCount() > n else Qt.ScrollBarAlwaysOff)

    def event(self, e):
        if e.type() == QEvent.KeyPress and e.key() == Qt.Key_Down and not self.completer().popup().isVisible():
            self.open_list()
            return True
        return super().event(e)



class WishlistDialog(GlassDialog):
    ask_requested = Signal(str)          # a question for the chat (where to hunt a dropper)
    farm_requested = Signal(str)         # an item's droppers in the Farm tool window (by its name)
    route_requested = Signal(str)        # the way to a monster's map: its page in the bar's Maps search (its name)

    def __init__(self, keys: list[str], kb: KnowledgeBase, lang: str, stylesheet: str, level: int | None = None):
        """level: the character's, for how each dropper sits against it (the Farm window's chips) and their order."""
        self.t = t = I18n(lang or "he")
        super().__init__(t("wishlist"), t.rtl)
        self.setStyleSheet(stylesheet)
        self.resize(500, 640)
        self.kb = kb
        self.level = level
        rtl = t.rtl
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        # items added here too: the ☆ was only on cards in a chat answer, so an empty window led nowhere (#96)
        self.search = EntityPicker(item_rows(kb), bidi.plain(t("wish_search"), rtl), icon=32, rtl=rtl)
        self.search.picked.connect(self._add_searched)
        outer.addWidget(self.search)
        outer.addSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget(objectName="Feed")
        self.lay = lay = QVBoxLayout(body)
        lay.setContentsMargins(*gutter(rtl))          # the room before the scrollbar, on its side (left in Hebrew)
        lay.setSpacing(8)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._fill(keys)
        from .widgets import WISHLIST
        WISHLIST.changed.connect(self._refill)

        row = QHBoxLayout()
        row.setContentsMargins(0, 10, 0, 0)
        row.addStretch(1)
        ok = QPushButton(t("close"), objectName="Primary")
        ok.setCursor(Qt.PointingHandCursor)
        ok.setMinimumWidth(160)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        row.addStretch(1)
        outer.addLayout(row)
        rtl_buttons(self, rtl)

    def _fill(self, keys: list[str]) -> None:
        """The wished items and their droppers; run again whenever the wishlist changes (a star taken off here or
        on a card left its item in the window until it was reopened: the owner's report)."""
        t, kb, lay, rtl = self.t, self.kb, self.lay, self.t.rtl
        clear(lay)
        keys = [k for k in keys if kb.get(k)]
        if not keys:
            empty = QLabel(bidi.plain(t("wishlist_empty"), rtl), objectName="DialogBody")
            empty.setWordWrap(True)
            lay.addWidget(empty)
        self._align = (Qt.AlignRight if rtl else Qt.AlignLeft) | Qt.AlignAbsolute
        for k in keys:
            lay.addWidget(EntityCard(kb, k, t.lang))
            droppers = kb.droppers.get(k, [])
            head = QLabel(bidi.plain(t("wish_dropped_by") if droppers else t("wish_no_droppers"), rtl),
                          objectName="ToolHeader")
            head.setWordWrap(bool(not droppers))
            head.setAlignment(self._align)
            head.setContentsMargins(4, 4, 4, 0)
            # each drop's list (the MSEA reference list, players' Classic sightings): one chip beside "Dropped by"
            # when every dropper's drop is on the same list, else one on each dropper's row
            srcs = {m: kb.drop_source(m, k) or sources.MSEA for m in droppers}
            self._mixed = len(set(srcs.values())) > 1
            chips = [] if self._mixed else source_tags(t, srcs.values())
            if chips:
                lay.addLayout(chip_row(chips, head))
            else:
                lay.addWidget(head)
            item = (kb.get(k) or {}).get("name", k)
            if droppers:
                # the drop lists include the MSEA reference drops, not all confirmed for Classic: said here as the
                # instant answers say it under the same data
                note = QLabel(bidi.plain(quick.drops_note(t, srcs.values()), rtl), objectName="RowHint")
                note.setWordWrap(True)
                note.setAlignment(self._align)
                note.setContentsMargins(4, 0, 4, 0)
                lay.addWidget(note)
                # the item in the Farm window: its droppers with the way there, answered here and not by the AI
                # (TOOL-07)
                go = QPushButton(bidi.plain(t("wish_on_farm"), rtl), objectName="Link")
                go.setCursor(Qt.PointingHandCursor)
                go.setAutoDefault(False)
                go.clicked.connect(lambda _=False, n=item: self.farm_requested.emit(n))
                lay.addWidget(go, 0, Qt.AlignLeft)      # AlignLeft is the leading edge (mirrored in Hebrew)
            # each dropper as a row with its picture, level, map and a way to ask the chat about it (live feedback:
            # a small text list was hard to read and led nowhere)
            # every dropper ("and 4 more" hid them, and the window scrolls anyway: the owner's report)
            # with the character's level: the community's first as before, then the ones to farm now nearest the
            # level (Snail Lv 1 came first for a Lv 35 player), each with the Farm window's chip for its fit
            ds = farm.droppers(kb, k, self.level) if self.level else []
            if ds:
                ds.sort(key=lambda d: (d.source != sources.COMMUNITY, d.fit == "hard", d.boss,
                                       abs(self.level - d.level), d.level, d.name))
            fits = {d.key: d for d in ds}
            for m in ([d.key for d in ds] or droppers):
                lay.addWidget(self._dropper(m, item, srcs.get(m) if self._mixed else None, kb.community_vote(m, k),
                                            fits.get(m)))
            lay.addSpacing(10)
        lay.addStretch(1)

    def _add_searched(self) -> None:
        """The item picked in the search box goes on the list (one already on it stays: picking never unstars)."""
        from .widgets import WISHLIST
        name = self.search.text().strip()
        key = farm.item_named(self.kb, name) if name else None
        if key is None:
            return                     # a half-typed name: the box keeps it to finish
        if not WISHLIST.has(key):
            WISHLIST.toggle(key)
        self.search.clear()

    @Slot()
    def _refill(self) -> None:
        """After the wishlist's signal, not inside it: rebuilding while the signal ran (the star that sent it is in
        here) crashed the app later, when the old cards were deleted."""
        QTimer.singleShot(0, self, self._refill_now)

    def _refill_now(self) -> None:
        from .widgets import WISHLIST
        if self.isVisible():
            self._fill(WISHLIST.keys())

    def done(self, r: int) -> None:
        from .widgets import WISHLIST
        try:
            WISHLIST.changed.disconnect(self._refill)       # a closed window stays out of the wishlist's changes
        except (RuntimeError, TypeError):
            pass
        super().done(r)

    def _dropper(self, m: str, item: str, source: str | None = None, vote: dict | None = None,
                 d: farm.Dropper | None = None) -> QFrame:
        t, kb = self.t, self.kb
        e = kb.get(m) or {}
        name = e.get("name", m)
        lvl = (e.get("props") or {}).get("Level")
        # where it lives: its busiest map the KB confirms is in the game (kb.droppers already keeps only monsters
        # that are in the game, but one that lives in both regions listed its Orbis map first)
        open_ = availability.of(kb)
        maps = [mp for mp in kb.all_maps(m) if open_.map_open(mp)][:1]
        card = QFrame(objectName="Card")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)
        pic = QLabel()
        pic.setFixedSize(44, 44)
        pic.setAlignment(Qt.AlignCenter)
        path = kb.picture(m)
        if path:
            pm = QPixmap(str(path))
            if not pm.isNull():
                pic.setPixmap(fit_picture(pm, 44, 44, pic))
                zoom_on_hover(pic, path)
        row.addWidget(pic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        # "Snail · רמה 1": the level in the UI's words, as on every tool window's card
        title = QLabel(name_lv(name, lvl, t), objectName="CardName")
        title.setAlignment(self._align)
        # how it sits against the level (the Farm window's chip), this row's own drop list when the droppers mix them,
        # the players' votes when players reported it ("16 ✓"), and a KB update this week that changed the monster
        fit = []
        if d is not None:
            fit = [info_tag(t, t("farm_fit_boss"), t("farm_fit_boss_tip"), "TagWarn") if d.boss else
                   info_tag(t, t(f"farm_fit_{d.fit}"), t(f"farm_fit_{d.fit}_tip"),
                            {"easy": "TagGood", "range": "Tag", "hard": "TagWarn"}[d.fit])]
        chips = fit + ([source_tag(t, source)] if source else []) + ([vote_tag(t, vote)] if vote else []) \
            + [c for c in [updated_tag(t, kb, m)] if c]
        if chips:
            # a flow, not one row: name + Lv, "Community", "Single report" and "Updated" in one row were 570 px
            # and pushed the whole window wider than its 434 px view, clipping every row (the site's shot)
            flow = FlowLayout(spacing=6, line_spacing=2)
            for w in [title, *chips]:
                flow.addWidget(w)
            col.addLayout(flow)
        else:
            col.addWidget(title)
        if maps:
            where = QLabel(bidi.ltr_name(kb.map_label(maps[0]), t.rtl), objectName="CardSub")
            where.setWordWrap(True)
            where.setAlignment(self._align)
            col.addWidget(where)
        row.addLayout(col, 1)
        # the way to its map, worked out here, then the chat (the only action was the AI's, for what the app knows)
        links = FlowLayout(spacing=14, line_spacing=0)
        acts = [("farm_route", lambda: self.route_requested.emit(name))] if maps and not (d and d.closed) else []
        acts.append(("ask_short", lambda: self.ask_requested.emit(t("wish_ask", monster=name, item=item))))
        for key, then in acts:
            b = QPushButton(bidi.plain(t(key), t.rtl), objectName="Link")
            b.setCursor(Qt.PointingHandCursor)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _=False, f=then: f())
            links.addWidget(b)
        col.addLayout(links)
        return card
