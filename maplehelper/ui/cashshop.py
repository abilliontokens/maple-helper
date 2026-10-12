"""Tools > Cash shop: what the game's Cash Shop sells right now and for how many NX, over the game in the glass of the
other tool windows (ui/toolwindow.py), in the game's own tabs (osms.TABS: Special, Fashion, Beauty, Pets, Utility) and
each tab's sections (osms.SECTIONS) on a switch under them. Its items, pictures and the crate's tiles are
ui/shoppage.py's; where they come from (OSMS Data Explorer, MesoWatch) is said on a source chip, with the credit OSMS's
terms ask for under the list.

The Pets tab's last section is the pets guide (NiaMeowDB, sitedata.py): every pet's lifespan, hunger, commands to
Lv 30, the fastest commands and its Cash Shop price, sold now / easiest to level / all, and the Cash Shop's pet
skills. A pet that trades has a Price link (its item page in the toolbar's Items search, NAV.item_requested).

The lists load in the background the first time the window opens; while it shows, it looks every minute for a newer
list (the app checks OSMS hourly and MesoWatch every 15 minutes) and follows it. No character needed."""
from __future__ import annotations

import html
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .. import bidi, mesowatch, osms, sitedata, sources
from .controls import Segmented, clear
from .gamesearch import TONES, rim
from .npcoverlay import accent_of, ink, palette
from .shoppage import CRATE_COLUMNS, GUIDE, PIC, TILE_PIC, Catalog, CrateTile, ShopRow, picture_box
from .toolwindow import NAV, ToolWindow, _rgba
from .widgets import fit_picture, source_tag, tip_html, updated_tag, zoom_on_hover

POLL_MS = 60 * 1000            # while it shows, how often it looks for a newer list (the checks: hourly / 15 minutes)
PET_PIC, PET_BOX = 40, 48      # a pet's picture, and its tile
SKILL_PIC, SKILL_BOX = 32, 40  # a pet skill's
PET_FILTERS = (("sold", "pets_sold"), ("easy", "pets_easy"), ("all", "pets_all"))
GOOD = TONES["safe"]           # "In Cash Shop": the glass's green
CLOSED = TONES["keep"]         # a closed-test value's mark: the warning orange
BADGE = "#8E8E93"              # the "?" by a pet's line (its tip explains it): grey on either glass


class CashShop(ToolWindow):
    SHOW_KEY = "cash_shop"
    GEOM_KEY = "cash_shop_geom"
    TITLE_KEY = "tb_shop"
    MIN_W, MIN_H = 380, 420
    DEFAULT_W, DEFAULT_H = 460, 680
    NEEDS_CHARACTER = False
    TABS = tuple((tab, f"shop_tab_{tab}") for tab in osms.TABS)

    ready = Signal(object, object)          # (OSMS's items or None, MesoWatch's snapshot or None)
    picture_ready = Signal(object, object)  # (label, path): an OSMS picture is on disk

    def _build_body(self) -> None:
        self.tab = "fashion"                 # the game's Cash Shop opens on its fashion; Special is the crate alone
        self.sections = {tab: secs[0] for tab, secs in osms.SECTIONS.items()}     # each tab's section, kept
        self.items: list[osms.Item] | None = None
        self.snap = None
        self._loaded = self._loading = False
        self._versions = (-1, -1)
        self.pet_mode = "sold"
        self._catalog: Catalog | None = None
        self._wanted: list[tuple[QLabel, osms.Item]] = []
        self.seg: Segmented | None = None           # the open tab's sections (none for a one-section tab)
        self.pet_filter: Segmented | None = None    # the pets guide's sold now / easiest / all
        self.credit: QLabel | None = None
        self.ready.connect(self._on_ready)
        self.picture_ready.connect(self._set_picture)
        self.timer = QTimer(self, interval=POLL_MS, timeout=self._poll)
        host = QWidget()
        self._secs = QVBoxLayout(host)
        self._secs.setContentsMargins(0, 0, 0, 0)
        self.top.addWidget(host)

    @property
    def section(self) -> str:
        return self.sections[self.tab]

    # ------------------------------------------------------------ the data

    def load(self) -> None:
        """Both lists in the background (the first of a run may download them)."""
        self._loading = True

        def run():
            try:
                found = osms.items()
            except Exception:      # noqa: BLE001 - shown as "couldn't load"
                found = None
            try:
                snap = mesowatch.snapshot()
            except Exception:      # noqa: BLE001 - no crate chances
                snap = None
            try:
                self.ready.emit(found, snap)
            except RuntimeError:
                pass                # the window is gone meanwhile
        threading.Thread(target=run, daemon=True, name="shop").start()

    def _poll(self) -> None:
        """A different list came in (OSMS's hourly check, MesoWatch's 15-minute one): the window follows it."""
        if not self._loading and (osms.version(), mesowatch.version()) != self._versions:
            self.load()

    def _on_ready(self, found, snap) -> None:
        self._versions = (osms.version(), mesowatch.version())
        self.items, self.snap = found, snap
        self._loaded, self._loading = True, False
        self._refill()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.timer.start()          # it looks for a newer list only while it shows

    def hideEvent(self, e) -> None:
        self.timer.stop()
        super().hideEvent(e)

    def rows(self) -> list[osms.Item]:
        """The open section's items, cheapest first."""
        return sorted((i for i in self.items or [] if osms.place(i) == (self.tab, self.section)),
                      key=lambda i: (i.nx, i.name))

    # ------------------------------------------------------------ pictures

    def picture(self, label: QLabel, key: str | None, item: osms.Item | None, px: int) -> None:
        """The KB's picture of the item; else OSMS's, fetched in the background."""
        label.setProperty("px", px)
        path = self._kb.picture(key) if key else None
        if path:
            pm = QPixmap(str(path))
            if not pm.isNull():
                label.setPixmap(fit_picture(pm, px, px, label))
                return
        if item is not None and item.thumbnail:
            self._wanted.append((label, item))

    def _fetch_pictures(self) -> None:
        wanted, self._wanted = self._wanted, []
        if not wanted:
            return

        def run():
            for label, item in wanted:
                path = osms.thumbnail_file(item)
                if path is not None:
                    try:
                        self.picture_ready.emit(label, path)
                    except RuntimeError:
                        return
        threading.Thread(target=run, daemon=True, name="osms-pictures").start()

    @staticmethod
    def _set_picture(label: QLabel, path) -> None:
        try:
            pm = QPixmap(str(path))
            if not pm.isNull():
                px = label.property("px") or PIC
                label.setPixmap(fit_picture(pm, px, px, label))
        except RuntimeError:
            pass                    # that card was redrawn meanwhile

    # ------------------------------------------------------------ the tabs and their sections

    def pick(self, tab: str, section: str | None = None) -> None:
        """The window on this tab, at this section (none: the one it was on), from the top."""
        if section is not None:
            if section not in osms.SECTIONS[tab]:
                raise ValueError(f"no Cash Shop section {section!r} in {tab!r}")
            self.sections[tab] = section
        if tab != self.tab:
            self._set_tab(tab)
        else:
            self._fill()
            self._to_top()

    def open_with(self, arg: str) -> None:
        """The window on a tab, or a tab's section: "pets", "pets/guide", "special/crate" (anything else: as it is)."""
        tab, _, section = str(arg or "").partition("/")
        if tab in osms.SECTIONS and (not section or section in osms.SECTIONS[tab]):
            self.pick(tab, section or None)

    def _sections_row(self) -> None:
        """The open tab's sections on a switch over the cards; a tab of one section (Special) has none."""
        t = self.t
        clear(self._secs)
        self.seg = None
        secs = osms.SECTIONS[self.tab]
        if len(secs) > 1:
            seg = Segmented([(t(f"shop_sec_{s}"), s) for s in secs], self.section, t.rtl)
            seg.setObjectName("Sections")
            seg.set_label(t(f"shop_tab_{self.tab}"))
            for b in seg.group.buttons():
                b.setFocusPolicy(Qt.NoFocus)
            seg.changed.connect(lambda s, tab=self.tab: self.pick(tab, s) if s != self.sections[tab] else None)
            self._secs.addWidget(seg)
            self.seg = seg
        self._top_box.setVisible(self.seg is not None)

    # ------------------------------------------------------------ the cards

    def _rebuild(self) -> None:
        if self._catalog is None or self._catalog.kb is not self._kb or self._catalog.t is not self.t:
            self._catalog = Catalog(self._kb, self.t)
        if not self._loaded and not self._loading:
            self.load()
        self._sections_row()
        clear(self.body)
        self.credit = self.pet_filter = None
        if self.section == GUIDE:
            self._guide()
        else:
            self._listing()
        self._fetch_pictures()

    def _listing(self) -> None:
        """The open section's items (the crate's tiles under it on Special), or why there are none yet."""
        t = self.t
        if not self._loaded:
            self.body.addWidget(self.empty("gem", t("shop_loading")))
            return
        if self.items is None:
            self.body.addWidget(self.empty("gem", t("shop_offline")))
            return
        self.body.addWidget(self.label(t("shop_intro"), "Hint", wrap=True))
        self.body.addWidget(self._source_row(self.label(t("shop_status", n=len(self.items)), "Muted"),
                                             sources.OSMS))
        rows = self.rows()
        cat = self._catalog
        for item in rows:
            key = cat.key_of(item.name)
            row = ShopRow(item, key, cat.name_of(key, item.name), cat.describe(item.name, item.description,
                                                                              item.game_id), t)
            self.picture(row.pic, key, item, PIC)
            self.body.addWidget(row)
        if self.section == "crate":
            self._crate()
        elif not rows:
            self.body.addWidget(self.empty("gem", t("shop_empty")))
        self.body.addSpacing(2)
        self.body.addWidget(self._credit())

    def _crate(self) -> None:
        """What the crate can give, likeliest first, each with its chance (MesoWatch: Nexon's published rates)."""
        t = self.t
        self.body.addSpacing(4)
        self.body.addWidget(self._source_row(self.caption(t("shop_crate_head")), sources.MESOWATCH))
        inside = mesowatch.crate(self.snap)
        if not inside:
            self.body.addWidget(self.label(t("shop_crate_none"), "Hint", wrap=True))
            return
        holder = QWidget()
        grid = QGridLayout(holder)       # mirrored in Hebrew with the window: the first tile on the reading side
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        cat = self._catalog
        for n, s in enumerate(inside):
            key = cat.key_of(s.name)
            tile = CrateTile(s, key, cat.name_of(key, s.name), t)
            self.picture(tile.pic, key, None, TILE_PIC)
            grid.addWidget(tile, n // CRATE_COLUMNS, n % CRATE_COLUMNS)
        for c in range(CRATE_COLUMNS):
            grid.setColumnStretch(c, 1)
        self.body.addWidget(holder)

    def _source_row(self, lead: QWidget, source: str, wide: bool = True) -> QWidget:
        """A line with where its data comes from on a chip at the far end, the two in one widget."""
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(lead, 1 if wide else 0)
        if not wide:                    # at its own width (a switch), the chip still at the far end
            row.addStretch(1)
        row.addWidget(source_tag(self.t, source), 0, Qt.AlignVCenter)
        return box

    def _credit(self) -> QLabel:
        """The credit and link OSMS's terms ask for, wherever its data shows (a label: a button laid the Hebrew words
        out reversed)."""
        t = self.t
        fill, _ = accent_of(self._settings)
        before = html.escape(t("shop_credit", link="@LINK@")).split("@LINK@")
        credit = QLabel(objectName="Note")
        credit.setTextFormat(Qt.RichText)
        credit.setOpenExternalLinks(True)
        credit.setWordWrap(True)
        credit.setText(f'<p dir="{"rtl" if t.rtl else "ltr"}">{before[0]}'
                       f'<a href="{osms.SITE}" style="color:{ink(fill)}; text-decoration:none; font-weight:600;">'
                       f'<span dir="ltr">{html.escape(osms.CREDIT)}</span></a>{before[-1]}</p>')
        self.credit = credit
        return credit

    # ------------------------------------------------------------ the pets guide (Pets > Pets guide)

    def pets_shown(self) -> list[sitedata.Pet]:
        """The guide's pets under its switch: sold now (the site's order), easiest to level first, or all."""
        every = sitedata.pets(self._kb)
        if self.pet_mode == "sold":
            return [p for p in every if p.sold]
        return sitedata.easiest(every) if self.pet_mode == "easy" else every

    def _pick_pets(self, mode) -> None:
        if mode != self.pet_mode:
            self.pet_mode = mode
            self._fill()

    def _guide(self) -> None:
        """Every pet (sitedata.py): lifespan, hunger, commands to Lv 30, the fastest commands, its Cash Shop price
        and trading, sold now first; then the Cash Shop's pet skills."""
        t = self.t
        every = sitedata.pets(self._kb)
        if every:
            self.body.addWidget(self.label(t("pets_intro"), "Hint", wrap=True))
            self.pet_filter = Segmented([(t(key), value) for value, key in PET_FILTERS], self.pet_mode, t.rtl)
            self.pet_filter.set_label(t("pets_title"))
            for b in self.pet_filter.group.buttons():
                b.setFocusPolicy(Qt.NoFocus)
            self.pet_filter.changed.connect(self._pick_pets)
            self.body.addWidget(self._source_row(self.pet_filter, sources.MEOWDB, wide=False))
            shown = self.pets_shown()
            if not shown:
                self.body.addWidget(self.empty("gem", t("pets_none_sold")))
            for p in shown:
                self.body.addWidget(self._pet_card(p))
        skills = sitedata.pet_skills(self._kb)
        if skills:
            self.body.addSpacing(4)
            self.body.addWidget(self.caption(t("pet_skills_title")))
            self.body.addWidget(self.label(t("pet_skills_intro"), "Hint", wrap=True))
            for s in skills:
                self.body.addWidget(self._skill_card(s))
        if not every:                       # a KB from before the pets guide
            self.body.addWidget(self.empty("gem", t("pets_empty")))

    def _pet_card(self, p: sitedata.Pet) -> QWidget:
        """One pet: its picture, name and links (Price when it trades, Ask in chat), then a line a detail, each
        named with a "?" that explains it on hover."""
        t, kb = self.t, self._kb
        card, v = self.card()
        card.setProperty("pet", p.key)
        row = QHBoxLayout()
        row.setSpacing(12)
        pic = picture_box(PET_BOX)
        path = kb.picture(p.key)
        pm = QPixmap(str(path)) if path else QPixmap()
        if not pm.isNull():
            pic.setPixmap(fit_picture(pm, PET_PIC, PET_PIC, pic))
            zoom_on_hover(pic, path)
        row.addWidget(pic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(QLabel(bidi.ltr_name(p.name, t.rtl), objectName="CardTitle"), 0, Qt.AlignVCenter)
        head.addStretch(1)
        trade = sitedata.trade(kb, p.key)
        if trade in ("once", "tradeable"):      # a pet players trade has prices: its item page
            head.addWidget(self.button(t("go_price"), lambda k=p.key: NAV.item_requested.emit(k), "Link"))
        head.addWidget(self.button(t("ask_short"), lambda n=p.name: NAV.ask_requested.emit(t("cs_pet_ask", name=n)),
                                   "Link"))
        col.addLayout(head)
        closed = set(p.closed_test or [])
        if p.lifespan:
            self._pet_line(col, "pet_line_life", sitedata.lifespan_text(t, p), "pet_life_tip",
                           t("pet_closed_mark") if "lifespan" in closed else "")
        if p.hunger is not None:
            top = sitedata.hunger_top(kb, p.key)
            self._pet_line(col, "pet_line_hunger", t("pet_hunger_of", n=p.hunger, top=top) if top else str(p.hunger),
                           "pet_hunger_tip")
        if isinstance(p.commands, int):
            self._pet_line(col, "pet_line_commands", t("pet_commands_n", n=f"{p.commands:,}", level=p.level),
                           "pet_commands_tip")
        fast = sitedata.fastest_commands(kb, p.key)
        if fast:
            # a range a line, the commands one English block ("sit / bad / stupid" read backwards otherwise)
            self._pet_line(col, "pet_line_fastest",
                           "\n".join(t("pet_fast_at", cmds=bidi.ltr_block(c, t.rtl), lv=bidi.ltr_block(lv, t.rtl))
                                     for c, lv in fast), "pet_fastest_tip")
        nx = sitedata.cash_price(kb, p.key)
        shop = (t("pet_nx", n=f"{nx[0]:,}") + (" " + t("pet_closed_mark") if nx[1] else "")) if nx and p.sold \
            else t("pet_not_sold")
        self._pet_line(col, "pet_line_shop", shop, "pet_shop_tip")
        if trade:
            self._pet_line(col, "pet_line_trade", t(f"pet_trade_{trade}"), f"pet_trade_{trade}_tip")
        updated = updated_tag(t, kb, p.key)
        if updated:
            chip = QHBoxLayout()
            chip.addWidget(updated)
            chip.addStretch(1)                              # at the reading start (the right in Hebrew)
            col.addLayout(chip)
        row.addLayout(col, 1)
        v.addLayout(row)
        return card

    def _pet_line(self, col: QVBoxLayout, name_key: str, value: str, tip_key: str, extra: str = "") -> None:
        """ "Lifespan ?: 7 days": the name bold with its "?" (the explanation on hover), then the value; a value of
        several lines, each its own line under the name."""
        from . import terms
        t = self.t
        badge = terms._badge_uri(BADGE, 12)
        side = "dir='rtl'" if t.rtl else "dir='ltr'"
        name = f"<b>{html.escape(t(name_key))}</b>"
        if badge:
            name += f"&nbsp;<img src='{badge}' width='12' height='12' style='vertical-align: middle'>"
        lines = value.split("\n")
        tail = f" <span style='color:{ink(CLOSED)}'>{html.escape(extra)}</span>" if extra else ""
        if len(lines) == 1:
            body = f"<p {side} style='margin:0'>{name}: {html.escape(bidi.plain(value, t.rtl))}{tail}</p>"
        else:
            body = f"<p {side} style='margin:0'>{name}:</p>"
        lb = QLabel(body, objectName="PetLine")
        lb.setTextFormat(Qt.RichText)
        lb.setWordWrap(True)
        lb.setToolTip(tip_html(t(tip_key, level=30), t.rtl))
        col.addWidget(lb)
        for one in lines if len(lines) > 1 else ():
            col.addWidget(self.label(one, "PetMore", wrap=True))

    def _skill_card(self, s: sitedata.PetSkill) -> QWidget:
        """A pet skill: its picture, name, what it does and its Cash Shop price (or that it isn't sold now)."""
        t, kb = self.t, self._kb
        card, v = self.card()
        row = QHBoxLayout()
        row.setSpacing(12)
        pic = picture_box(SKILL_BOX)
        path = kb.picture(s.key)
        pm = QPixmap(str(path)) if path else QPixmap()
        if not pm.isNull():
            pic.setPixmap(fit_picture(pm, SKILL_PIC, SKILL_PIC, pic))
        row.addWidget(pic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(QLabel(bidi.ltr_name(s.name, t.rtl), objectName="CardTitle"), 1)
        if s.sold and s.nx:
            trade = sitedata.trade(kb, s.key)
            tip = t("pet_shop_tip") + (" " + t("pet_nx_closed") if s.closed_test else "") \
                + (" " + t(f"pet_trade_{trade}_tip") if trade else "")
            head.addWidget(self._chip(t("pet_nx", n=f"{s.nx:,}"), "Good", tip), 0, Qt.AlignTop)
        else:
            head.addWidget(self._chip(t("pet_not_sold"), "Chip", t("pet_not_sold_tip")), 0, Qt.AlignTop)
        col.addLayout(head)
        col.addWidget(self.label(sitedata.pet_skill_text(s, t.lang, kb), "Muted", wrap=True))
        row.addLayout(col, 1)
        v.addLayout(row)
        return card

    def _chip(self, text: str, name: str, tip: str) -> QLabel:
        lb = QLabel(bidi.plain(text, self.t.rtl), objectName=name)
        lb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        lb.setToolTip(tip_html(tip, self.t.rtl))
        return lb

    # ------------------------------------------------------------ look

    def _restyle(self) -> None:
        """The credit's link and the closed-test marks carry the accent's and the glass's colours in their own
        words: drawn again when the look changes while the window shows."""
        before = self.styleSheet()
        super()._restyle()
        if self.styleSheet() != before and self.isVisible():
            self._fill()

    def extra_qss(self) -> str:
        p = palette()
        fill, _ = accent_of(self._settings)
        lit = ink(fill)
        chip = "border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700;"
        return f"""
QFrame#Card[click="true"]:hover {{ background: {p.fill2}; }}
#Pic {{ background: {rim(0.06, p)}; border-radius: 10px; }}
#ShopName {{ color: {p.text}; font-size: 13px; font-weight: 700; }}
#ShopPrice {{ color: {lit}; font-size: 14px; font-weight: 700; }}
#ShopLasts {{ color: {p.muted}; font-size: 11px; }}
#ShopTile {{ color: {p.text}; font-size: 12px; font-weight: 600; }}
#ShopOdds {{ color: {lit}; font-size: 12px; font-weight: 700; }}
#PetLine {{ color: {p.text}; font-size: 12px; }}
#PetMore {{ color: {p.muted}; font-size: 12px; padding-left: 10px; padding-right: 10px; }}
QLabel#Good {{ color: {ink(GOOD)}; background: {_rgba(GOOD, 0.16)}; {chip} }}
QLabel#SourceTag {{ color: {lit}; background: transparent; border: 1px solid {_rgba(fill, 0.6)}; border-radius: 5px;
                   padding: 0 4px; font-size: 9px; font-weight: 700; }}
QLabel#UpdatedTag {{ color: {lit}; background: {_rgba(fill, 0.14)}; border: 1px solid {_rgba(fill, 0.45)};
                    border-radius: 7px; padding: 1px 6px; font-size: 10px; font-weight: 700; }}
QFrame#Sections {{ background: transparent; border: 1px solid {rim(0.12, p)}; border-radius: 10px; }}
#Sections QPushButton#Segment {{ font-size: 12px; }}
#Sections QPushButton#Segment:checked {{ background: {p.fill2}; color: {p.text}; }}
"""
