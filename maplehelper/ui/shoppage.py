"""The Cash shop window's pieces (ui/cashshop.py): what the Cash Shop sells right now, laid out as the game's own Cash
Shop is (the owner's screenshots, 2026-10-11): Special (the Founder's Mystery Fashion Crate and what it can give),
Fashion (Hats, Outfits, Tops, Bottoms, Shoes), Beauty (Hairstyles, Faces, Misc), Pets (Pets, Pet Equip, Pet Care, and
the pets guide) and Utility (Convenience, Social, Atmospheric Effect). Each item: its picture, name, what it is, its
NX price and how long it lasts; a click opens its details window (ITEM_REQUESTS, the item's ⓘ).

All of it follows the game by itself, from two sources the owner has permission for: the items and their prices from
OSMS Data Explorer (osms.py, the game client's own Cash Shop list, checked every hour), the crate's chances from
MesoWatch (mesowatch.py, every 15 minutes). An item the Cash Shop adds shows up, one it drops goes away.

Here: which KB item an OSMS name is and what an item is in the player's language (Catalog; tools/translate_kb.py reads
kb_names / kb_hebrew too), and an item's row and a crate tile in the glass's style names (cashshop.CashShop.extra_qss:
ShopName, ShopPrice, ShopLasts, ShopTile, Pic; Card, Muted, Note from ui/toolwindow.py)."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from .. import bidi, itemdetails, mesowatch, osms, translations
from .widgets import ITEM_REQUESTS

GUIDE = "guide"                # the Pets tab's pets guide (the old Pets page)
CRATE_COLUMNS = 4              # the crate's tiles a row (the owner)
PIC = 44                       # an item's picture, in its tile
PIC_BOX = 52                   # ... the tile behind it
TILE_PIC = 40                  # a crate tile's picture
TILE_BOX = 46


def fold(name: str) -> str:
    return " ".join(str(name or "").split()).lower()


def kb_names(kb) -> dict[str, list[str]]:
    """Folded item name -> every KB item of that name, Cash ones first (a name can be two items: a male and a female
    version, a Cash and a game one)."""
    seen: dict[str, list[str]] = {}
    for k, e in (getattr(kb, "entities", None) or {}).items():
        if k.startswith("item/"):
            seen.setdefault(fold(e.get("name")), []).append(k)
    cash = lambda k: str((kb.get(k) or {}).get("type") or "").startswith("Cash")      # noqa: E731
    return {n: sorted(ks, key=lambda k: not cash(k)) for n, ks in seen.items()}


def same_text(a: str, b: str) -> bool:
    """The same words, whatever the spacing, line breaks and punctuation."""
    norm = lambda t: re.sub(r"[^a-z0-9%]+", " ", str(t or "").lower()).strip()      # noqa: E731
    return norm(a) == norm(b)


def kb_hebrew(kb, root, keys: list[str], game_text: str = "") -> str | None:
    """The Hebrew of an item's KB description, from any KB item of its name that has one (the app's file or the
    KB's nightly translation, made from the KB's own English). With game_text (OSMS's words: the game's own), only a
    KB text that says the same: the KB's closed-test words can differ ("up to 24 items" where the game says 18)."""
    for k in keys:
        try:
            en = itemdetails.details(kb, k).description or ""
        except Exception:          # noqa: BLE001 - a page the parser didn't expect
            continue
        if not en or (game_text and not same_text(en, game_text)):
            continue
        he = translations.he(root, "item_desc", k, en)
        if he:
            return he
    return None


class Catalog:
    """The KB's side of the Cash Shop's items, for one KB and one language: which KB item an OSMS name is (key_of),
    and what an item is, whole, in the player's language (describe, cached)."""

    def __init__(self, kb, t):
        self.kb, self.t = kb, t
        self._by_name = kb_names(kb)
        self._desc: dict[tuple[str, str], str] = {}

    def key_of(self, name: str) -> str | None:
        keys = self._by_name.get(fold(name)) or []
        return keys[0] if keys else None

    def name_of(self, key: str | None, fallback: str) -> str:
        """The KB's name of the item (its own spelling), else OSMS's."""
        return ((self.kb.get(key) or {}).get("name") if key else None) or fallback

    def describe(self, name: str, english: str = "", game_id: int | None = None) -> str:
        """What the item is, whole (the owner: never cut). The game's own words (OSMS) win over the KB's, which can be
        the closed test's: in Hebrew, the Hebrew made from OSMS's words (the app's file, then the KB's nightly
        "cash_desc"), or the KB's Hebrew of a text that says the same; for an item OSMS has no words for (most
        equips), the KB's Hebrew; else English. In the reading order of the language (bidi)."""
        cache = (name, english)
        if cache not in self._desc:
            keys = self._by_name.get(fold(name)) or []
            root = getattr(self.kb, "root", None)
            text = None
            if self.t.rtl:
                if english:
                    text = (translations.he(root, "cash_desc", f"cash/{game_id}", english) if game_id else None) \
                        or kb_hebrew(self.kb, root, keys, english)
                else:
                    text = kb_hebrew(self.kb, root, keys)
            if not text:
                text = english
                for k in keys:
                    if text:
                        break
                    try:
                        text = itemdetails.details(self.kb, k).description or ""
                    except Exception:      # noqa: BLE001 - a page the parser didn't expect: no description
                        text = ""
            text = " ".join(str(text or "").split())
            hebrew = any("\u0590" <= ch <= "\u05ff" for ch in text)
            self._desc[cache] = bidi.plain(text, self.t.rtl) if hebrew else bidi.ltr_block(text, self.t.rtl)
        return self._desc[cache]


def picture_box(size: int) -> QLabel:
    """The soft tile a sprite sits on (Pic), its picture set later (the KB's, or OSMS's once fetched)."""
    pic = QLabel(objectName="Pic")
    pic.setFixedSize(size, size)
    pic.setAlignment(Qt.AlignCenter)
    return pic


class _Clickable(QFrame):
    """A card that opens its item's details window on a click (ITEM_REQUESTS), lit under the mouse."""

    def __init__(self, key: str | None, t):
        super().__init__(objectName="Card")
        self.key = key
        if key:
            self.setProperty("click", True)
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip(t("shop_open_item"))

    def mousePressEvent(self, e):
        if self.key and e.button() == Qt.LeftButton:
            ITEM_REQUESTS.requested.emit(self.key)
        super().mousePressEvent(e)


class ShopRow(_Clickable):
    """One item: its picture, name and what it is on the reading side, the NX price and how long it lasts on the
    other. `pic` is filled by the window (CashShop.picture)."""

    def __init__(self, item: osms.Item, key: str | None, name: str, desc: str, t):
        super().__init__(key, t)
        self.item = item
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 10, 12, 10)
        row.setSpacing(12)
        self.pic = picture_box(PIC_BOX)
        row.addWidget(self.pic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setContentsMargins(0, 2, 0, 0)
        col.setSpacing(3)
        col.addWidget(QLabel(bidi.ltr_name(name, t.rtl), objectName="ShopName"))
        if desc:
            lb = QLabel(desc, objectName="Muted")
            lb.setWordWrap(True)
            col.addWidget(lb)
        col.addStretch(1)
        row.addLayout(col, 1)
        end = QVBoxLayout()
        end.setContentsMargins(0, 2, 0, 0)
        end.setSpacing(2)
        price = QLabel(bidi.ltr_block(f"{item.nx:,} NX", t.rtl), objectName="ShopPrice")
        price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)        # the far edge (the left in Hebrew)
        end.addWidget(price)
        lasts = QLabel(bidi.plain(t("shop_days", n=item.days) if item.days else t("shop_permanent"), t.rtl),
                       objectName="ShopLasts")
        lasts.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        end.addWidget(lasts)
        end.addStretch(1)
        row.addLayout(end, 0)


class CrateTile(_Clickable):
    """One thing the crate can give: its picture, name and chance. `pic` is filled by the window."""

    def __init__(self, s: mesowatch.Sales, key: str | None, name: str, t):
        super().__init__(key, t)
        self.sales = s
        col = QVBoxLayout(self)
        col.setContentsMargins(6, 10, 6, 9)
        col.setSpacing(4)
        self.pic = picture_box(TILE_BOX)
        col.addWidget(self.pic, 0, Qt.AlignHCenter)
        lb = QLabel(bidi.ltr_name(name, t.rtl), objectName="ShopTile")
        lb.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        lb.setWordWrap(True)
        col.addWidget(lb, 1)
        odds = QLabel(bidi.plain(t("shop_chance", pct=f"{s.crate_odds:g}%"), t.rtl), objectName="ShopOdds")
        odds.setAlignment(Qt.AlignCenter)
        col.addWidget(odds)
