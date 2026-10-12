"""Tools > Cash shop (ui/cashshop.py, its pieces ui/shoppage.py): what the game's Cash Shop sells now in the game's tabs
and their sections (OSMS stubbed), the crate's chances (MesoWatch stubbed), loading and offline, the pets guide's
switch and its links (sitedata stubbed), a newer list followed only while the window shows, Hebrew mirrored."""
import os
import re
import time

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from maplehelper import mesowatch, osms, sitedata
from maplehelper.i18n import I18n

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ITEMS = [osms.Item(1007098, "Kuniragi Hat", "Equipment", "Hat", 1200, days=10),
         osms.Item(1007039, "Goggled Black Cap", "Equipment", "Hat", 900, days=10),
         osms.Item(1072001, "Sneakers", "Equipment", "Shoes", 700),
         osms.Item(5150000, "Mystery Hair Coupon", "Coupon", "", 5500, days=14, description="Random hair."),
         osms.Item(5070000, "Megaphone", "Megaphone", "", 350, days=90),
         osms.Item(5000000, "Brown Kitty", "Pet", "", 3500),
         osms.Item(5222001, "Founder's Mystery Fashion Crate", "Other", "", 3500, days=7)]
PETS = {"pets": [
    {"key": "item/p1", "name": "Brown Kitty", "lifespan": "30 days", "hunger": 2, "level": 30, "commands": 25000,
     "commands_text": "~25.0k", "availability": "In Cash Shop", "sold": True},
    {"key": "item/p2", "name": "Black Pig", "lifespan": "30 days", "hunger": 3, "level": 30, "commands": 9000,
     "commands_text": "~9.0k", "availability": "Not sold right now", "sold": False},
    {"key": "item/p3", "name": "Snail", "lifespan": "5 hours", "hunger": 1, "level": 30, "commands": None,
     "commands_text": "", "availability": "Not sold right now", "sold": False}]}
PAGES = {"item/p1": "Tradeable once\nPets range from 1 to 5\nFastest to level: sit / bad at Lv 1-9 (0.40 per try)\n"
                    "Cash Shop\n3,500 NX\n",
         "item/p2": "Untradeable\n", "item/p3": ""}


def bare(text: str) -> str:
    """A label's text without its direction marks."""
    return re.sub("[\u200e\u200f\u202a-\u202e\u2066-\u2069\u2060]", "", text)


class FakeKB:
    root = None

    def __init__(self):
        self.entities = {"item/1560": {"name": "Kuniragi Hat", "type": "Cash Equip / Cash Hat"},
                         "item/1511": {"name": "Mystery Hair Coupon", "type": "Cash / Coupon"},
                         "item/p1": {"name": "Brown Kitty", "type": "Cash / Pet"},
                         "item/p2": {"name": "Black Pig", "type": "Cash / Pet"},
                         "item/p3": {"name": "Snail", "type": "Cash / Pet"}}

    def get(self, key):
        return self.entities.get(key)

    def picture(self, key):
        return None

    def page(self, key):
        return PAGES.get(key, "")


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _dark_look():
    from maplehelper.ui import npcoverlay
    npcoverlay.apply_look(None)
    yield
    npcoverlay.apply_look(None)


@pytest.fixture
def stubs(monkeypatch):
    snap = mesowatch.Snapshot("Windia", time.time(), {
        1022047: mesowatch.Sales(1022047, "Black Sunglasses", crate_odds=1.0),
        1002723: mesowatch.Sales(1002723, "Patissier Hat", crate_odds=3.0)})
    monkeypatch.setattr(osms, "items", lambda refresh=True, timeout=30: ITEMS)
    monkeypatch.setattr(osms, "thumbnail_file", lambda item, timeout=10: None)
    monkeypatch.setattr(mesowatch, "snapshot", lambda refresh=True, timeout=30: snap)
    monkeypatch.setattr(sitedata, "_file", lambda kb, name: PETS if name == sitedata.PETS else {})
    return snap


def pump(app, until=lambda: False, secs=3.0):
    end = time.time() + secs
    while not until() and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


@pytest.fixture
def make(qapp, isolated_store, stubs):
    made = []

    def make_window(lang="en", show=True):
        from maplehelper.ui.cashshop import CashShop
        s = isolated_store.Settings()
        s["cash_shop"] = True
        w = CashShop(FakeKB(), s, isolated_store.Profiles(), I18n(lang))
        made.append(w)
        if show:
            w.refresh()
            pump(qapp, lambda: w._loaded)
        return w
    yield make_window
    for w in made:
        w.timer.stop()
        w.hide()
        w.deleteLater()
    qapp.processEvents()


def body(w) -> list:
    return [w.body.itemAt(i).widget() for i in range(w.body.count()) if w.body.itemAt(i).widget() is not None]


def rows(w) -> list[str]:
    from maplehelper.ui.shoppage import ShopRow
    return [r.item.name for r in body(w) if isinstance(r, ShopRow)]


def pets(w) -> list[str]:
    return [c.property("pet") for c in body(w) if isinstance(c, QFrame) and c.property("pet")]


def click(widget):
    widget.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5), QPointF(5, 5), Qt.LeftButton,
                                       Qt.LeftButton, Qt.NoModifier))


@pytest.mark.parametrize("lang", ["en", "he"])
def test_the_tabs_and_sections_lay_out_the_games_cash_shop(make, lang):
    from maplehelper.ui.widgets import ITEM_REQUESTS
    w = make(lang)
    assert w.layoutDirection() == (Qt.RightToLeft if lang == "he" else Qt.LeftToRight)
    # it opens on Fashion > Hats, cheapest first, with NX and how long it lasts
    assert (w.tab, w.section) == ("fashion", "hats") and w.seg.value() == "hats"
    assert rows(w) == ["Goggled Black Cap", "Kuniragi Hat"]
    texts = bare(" ".join(lb.text() for r in body(w) for lb in r.findChildren(QLabel)))
    assert "1,200 NX" in texts and "900 NX" in texts and "10" in texts
    # the section switch under the tabs: Shoes, then another tab and back keeps Shoes
    w.seg.group.buttons()[osms.SECTIONS["fashion"].index("shoes")].click()
    assert w.section == "shoes" and rows(w) == ["Sneakers"]
    w._tabs.group.buttons()[osms.TABS.index("beauty")].click()          # the tab row: Beauty > Hairstyles
    assert (w.tab, w.section) == ("beauty", "hair") and rows(w) == ["Mystery Hair Coupon"]
    asked = []
    ITEM_REQUESTS.requested.connect(asked.append)
    try:
        click(next(r for r in body(w) if getattr(r, "item", None)))     # its details window
    finally:
        ITEM_REQUESTS.requested.disconnect(asked.append)
    assert asked == ["item/1511"]
    w.pick("fashion")
    assert w.section == "shoes"
    w.pick("utility", "social")
    assert rows(w) == ["Megaphone"] and w.seg.value() == "social"
    w.pick("beauty", "faces")                                            # nothing there
    assert rows(w) == [] and any(type(x).__name__ == "EmptyCard" for x in body(w))
    # Special: the crate alone (no section switch), what it can give with its chance, likeliest first
    w.pick("special")
    assert w.seg is None and rows(w) == ["Founder's Mystery Fashion Crate"]
    from maplehelper.ui.shoppage import CrateTile
    tiles = [t for x in body(w) for t in x.findChildren(CrateTile)]
    assert [t.sales.name for t in tiles] == ["Patissier Hat", "Black Sunglasses"]
    assert "3%" in " ".join(lb.text() for lb in tiles[0].findChildren(QLabel))
    # the credit OSMS's terms ask for, wherever its data shows
    assert "OSMS Data Explorer by ohmi" in w.credit.text() and osms.SITE in w.credit.text()
    w.open_with("pets/guide")
    assert (w.tab, w.section) == ("pets", "guide") and w.seg.value() == "guide" and rows(w) == []
    w.open_with("pets/pets")
    assert rows(w) == ["Brown Kitty"]


def test_it_says_it_is_loading_then_offline(make, monkeypatch, qapp):
    from maplehelper.ui.toolwindow import EmptyCard

    def down(refresh=True, timeout=30):
        raise OSError("offline")
    monkeypatch.setattr(osms, "items", down)
    w = make(show=False)
    w.refresh()                                     # loading in the background: the card says so
    en = I18n("en")
    first = body(w)[0]
    assert isinstance(first, EmptyCard) and first.title.text() == en("shop_loading")
    pump(qapp, lambda: w._loaded)
    first = body(w)[0]
    assert isinstance(first, EmptyCard) and first.title.text() == en("shop_offline") and rows(w) == []


def test_the_pets_guide_filters_and_links(make, qapp):
    from maplehelper.ui.toolwindow import NAV
    w = make()
    w.pick("pets", "guide")
    assert pets(w) == ["item/p1"]                                   # sold now (the site's order)
    w.pet_filter.group.buttons()[1].click()                         # easiest to level: fewest commands first
    assert w.pet_mode == "easy" and pets(w) == ["item/p2", "item/p1", "item/p3"]
    w.pet_filter.group.buttons()[2].click()                         # all, as the site lists them
    assert pets(w) == ["item/p1", "item/p2", "item/p3"]
    w.pick("fashion")
    w.pick("pets")
    assert w.pet_mode == "all" and w.section == "guide"             # kept while the window lives
    cards = {c.property("pet"): c for c in body(w) if isinstance(c, QFrame) and c.property("pet")}
    lines = bare(" ".join(lb.text() for lb in cards["item/p1"].findChildren(QLabel)))
    assert "3,500 NX" in lines and "sit / bad" in lines and "2 of 5" in lines
    price = [b for b in cards["item/p1"].findChildren(QPushButton, "Link") if bare(b.text()) == "Price"]
    assert len(price) == 1
    assert not [b for b in cards["item/p2"].findChildren(QPushButton, "Link") if bare(b.text()) == "Price"]
    items, asks = [], []
    NAV.item_requested.connect(items.append)
    NAV.ask_requested.connect(asks.append)
    try:
        price[0].click()                                            # its item page with its prices
        next(b for b in cards["item/p1"].findChildren(QPushButton, "Link") if bare(b.text()) == "Ask in chat").click()
    finally:
        NAV.item_requested.disconnect(items.append)
        NAV.ask_requested.disconnect(asks.append)
    assert items == ["item/p1"] and len(asks) == 1 and "Brown Kitty" in asks[0]


def test_a_kb_without_pets_says_the_guide_comes_later(make, monkeypatch):
    from maplehelper.ui.toolwindow import EmptyCard
    monkeypatch.setattr(sitedata, "_file", lambda kb, name: {})
    w = make()
    w.pick("pets", "guide")
    assert w.pet_filter is None and pets(w) == []
    assert [x.title.text() for x in body(w) if isinstance(x, EmptyCard)] == [I18n("en")("pets_empty")]


def test_a_newer_list_is_followed_only_while_the_window_shows(make, monkeypatch, qapp):
    w = make()
    assert w.timer.isActive() and w.timer.interval() == 60 * 1000
    loads = []
    monkeypatch.setattr(w, "load", lambda: loads.append(1))
    w._poll()
    assert loads == []                                              # nothing newer
    monkeypatch.setattr(osms, "version", lambda: w._versions[0] + 1)
    w._poll()
    assert loads == [1]
    w._close_clicked()                                              # the ✕: hidden, the checks stop
    assert not w.isVisible() and not w.timer.isActive() and not w._settings["cash_shop"]
    w._settings["cash_shop"] = True
    w.refresh()
    assert w.timer.isActive()


def test_hebrew_reads_right_to_left_and_the_white_glass_keeps_its_names(make):
    from maplehelper.ui import npcoverlay
    w = make("he")
    assert bare(w._tabs.group.buttons()[0].text()) == I18n("he")("shop_tab_special")
    price = next(lb for r in body(w) for lb in r.findChildren(QLabel, "ShopPrice"))
    assert bare(price.text()) == "900 NX"
    npcoverlay.apply_look({"overlay_tint": "white"})
    w._settings["overlay_accent"] = "blue"
    w.refresh()
    # dark words on the white glass, the price and the source chips in the accent darkened for it
    assert npcoverlay.ink("#3D8BD6") in w.extra_qss() and npcoverlay.LIGHT.text in w.styleSheet()
