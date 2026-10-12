"""The Free Market details window (ui/marketview.py): MesoWatch's item card laid out in the app, and the live sources
kept fresh by the app (the Cash shop window's own tests: test_cashshop.py)."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from maplehelper import mesowatch  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


class FakeKB:
    root = None

    def __init__(self, items):
        self.entities = {k: {"name": n, "url": ""} for k, n in items.items()}

    def get(self, key):
        return self.entities.get(key)

    def picture(self, key):
        return None

    def page(self, key):
        return ""


KB = FakeKB({"item/3198": "Black Cat Beanie", "item/414": "Iron Ore", "item/1": "Work Gloves"})


def hat(now):
    return mesowatch.Sales(
        1007145, "Black Cat Beanie", 229000, 99999, 265000, 19, False, 299999, mw_id="cash:01007145", asks=111,
        listing_shops=62, days=4, last3=299999, cash=True, cash_on_sale=False, category="Cash Shop",
        shops=[mesowatch.Shop("", 499999, seen=now - 1800, seller="Countdown"),
               mesowatch.Shop("Free Market 1", 399999, seen=now - 3600, seller="Tagged")],
        recent=[mesowatch.Sale(250000, 1, "", now - 6 * 3600, "Space Ghost"),
                mesowatch.Sale(349999, 1, "Free Market 2", now - 7 * 3600, "ShadowBlade")],
        history=[mesowatch.Day("2026-10-08", 74999, 50000, 75000, 5), mesowatch.Day("2026-10-09", 199999, 199999, 221750, 6),
                 mesowatch.Day("2026-10-10", 299999, 265000, 349999, 7)])


def market(now):
    items = {1007145: hat(now),
             4010001: mesowatch.Sales(4010001, "Iron Ore", 375, 299, 499, 2243, False, category="Etc",
                                      history=[mesowatch.Day("2026-10-06", 499, sold=9)]),
             1082002: mesowatch.Sales(1082002, "Work Gloves", 2222, sold=556, low_data=False, category="Equips",
                                      history=[mesowatch.Day(time.strftime("%Y-%m-%d", time.localtime(now)), 2222, sold=3)]),
             1302000: mesowatch.Sales(1302000, "Sword", 900, sold=12, low_data=True, category="Equips")}
    return mesowatch.Snapshot("Windia", now - 600, items,
                              by_name={"black cat beanie": 1007145, "iron ore": 4010001, "work gloves": 1082002})


@pytest.mark.parametrize("lang", ["en", "he"])
def test_the_details_window_shows_mesowatchs_card(app, monkeypatch, lang):
    from PySide6.QtWidgets import QLabel

    from maplehelper.ui.marketview import MarketDetailsDialog
    now = time.time()
    snap = market(now)
    monkeypatch.setattr(mesowatch, "snapshot", lambda refresh=True, timeout=30: snap)
    monkeypatch.setattr(mesowatch, "face_file", lambda snap_, who, timeout=10: None)
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    d = MarketDetailsDialog(KB, lang, "", None, None)
    d.show_item("item/3198")
    texts = " ".join(w.text() for w in d.findChildren(QLabel))
    for want in ("229,000", "250,000", "299,999", "111", "Countdown", "Tagged", "Space Ghost"):
        assert want in texts
    # where to buy: cheapest first, then the newest sales on the other tab
    names = [w.text() for w in d.buy_list.findChildren(QLabel, "MwRowName")]
    assert "Tagged" in names[0] and "Countdown" in names[1]
    assert d.buy_list.isVisibleTo(d) and not d.sold_list.isVisibleTo(d)
    d.tabs.group.buttons()[1].click()
    assert d.sold_list.isVisibleTo(d) and not d.buy_list.isVisibleTo(d)
    assert not hasattr(d, "chart")                       # no charts (the owner)
    d.site.click()
    assert opened == ["https://meso.watch/?item=cash:01007145"]
    d.close()
    d.deleteLater()           # (no window left behind for the next tests to restyle)


def test_a_sellers_picture_replaces_the_initial(app, monkeypatch, tmp_path):
    from PySide6.QtGui import QColor, QImage

    from maplehelper.ui.marketview import MarketDetailsDialog
    now = time.time()
    snap = market(now)
    face = tmp_path / "f.png"
    img = QImage(34, 66, QImage.Format_ARGB32)
    img.fill(QColor("#336699"))
    img.save(str(face))
    monkeypatch.setattr(mesowatch, "snapshot", lambda refresh=True, timeout=30: snap)
    monkeypatch.setattr(mesowatch, "face_file", lambda snap_, who, timeout=10: face if who == "Tagged" else None)
    d = MarketDetailsDialog(KB, "en", "", None, None)
    d.show_item("item/3198")
    d._on_face("Tagged", face)
    tagged = d._avatars["Tagged"][0]
    assert tagged.text() == "" and not tagged.pixmap().isNull()
    assert d._avatars["Countdown"][0].text() == "C"
    d.close()
    d.deleteLater()           # (no window left behind for the next tests to restyle)


def test_an_item_nobody_sold_says_so(app, monkeypatch):
    from PySide6.QtWidgets import QLabel

    from maplehelper.ui.marketview import MarketDetailsDialog
    snap = mesowatch.Snapshot("Windia", time.time(), {})
    monkeypatch.setattr(mesowatch, "snapshot", lambda refresh=True, timeout=30: snap)
    d = MarketDetailsDialog(KB, "en", "", None, None)
    d.show_item("item/414")
    note = [w for w in d.findChildren(QLabel) if "hasn't seen" in w.text()]
    assert note and "**" not in note[0].text() and note[0].objectName() == "DialogBody"      # plain, body size
    monkeypatch.setattr(mesowatch, "snapshot", lambda refresh=True, timeout=30: None)
    d.show_item("item/414")
    assert any("couldn't reach" in w.text().lower() for w in d.findChildren(QLabel))
    d.close()
    d.deleteLater()           # (no window left behind for the next tests to restyle)


def test_an_open_window_follows_a_newer_market(app, monkeypatch):
    from maplehelper.ui.marketview import MarketDetailsDialog
    now = time.time()
    snap = market(now)
    monkeypatch.setattr(mesowatch, "snapshot", lambda refresh=True, timeout=30: snap)
    monkeypatch.setattr(mesowatch, "face_file", lambda snap_, who, timeout=10: None)
    d = MarketDetailsDialog(KB, "en", "", None, None)
    d.show_item("item/3198")
    d.tabs.group.buttons()[1].click()                   # the player is on "Recent sales"
    shown = []
    real = d.show_item
    monkeypatch.setattr(d, "show_item", lambda key: (shown.append(key), real(key)))
    d._follow()
    assert shown == []                                  # nothing newer
    monkeypatch.setattr(mesowatch, "version", lambda: d._version + 1)
    d._follow()
    assert shown == ["item/3198"] and d.tabs.value() == "sold"
    d.close()
    d.deleteLater()           # (no window left behind for the next tests to restyle)


def test_a_sellers_picture_is_the_whole_character(app, tmp_path):
    from PySide6.QtGui import QColor, QImage

    from maplehelper.ui.marketview import face_pixmap
    img = QImage(34, 66, QImage.Format_ARGB32)
    img.fill(QColor("#336699"))
    path = tmp_path / "f.png"
    img.save(str(path))
    out = face_pixmap(path, 40).toImage()
    # the figure's feet are drawn too (the bottom of the picture), not cut to the head
    blue = [y for y in range(out.height()) if out.pixelColor(out.width() // 2, y).blue() > 120]
    assert blue and max(blue) > out.height() * 0.85 and min(blue) < out.height() * 0.15


def test_the_app_keeps_both_live_sources_fresh_by_itself(app, monkeypatch):
    """At start, then every 15 minutes (MesoWatch) and every hour (OSMS), with no one asking."""
    from types import SimpleNamespace

    from maplehelper import app as app_module
    from maplehelper import osms
    warmed = []
    monkeypatch.setattr(mesowatch, "warm", lambda: warmed.append("mesowatch"))
    monkeypatch.setattr(osms, "warm", lambda: warmed.append("osms"))
    fake = SimpleNamespace()
    app_module.MapleHelperApp._start_live_data(fake)
    assert sorted(warmed) == ["mesowatch", "osms"]                     # right as the app opens
    assert fake._mesowatch_timer.isActive() and fake._mesowatch_timer.interval() == 15 * 60 * 1000
    assert fake._osms_timer.isActive() and fake._osms_timer.interval() == 60 * 60 * 1000
    warmed.clear()
    fake._mesowatch_timer.timeout.emit()
    fake._osms_timer.timeout.emit()
    assert sorted(warmed) == ["mesowatch", "osms"]                     # and again on each tick
    fake._mesowatch_timer.stop()
    fake._osms_timer.stop()


def test_a_new_publish_reaches_what_is_open_by_itself(app, monkeypatch, tmp_path):
    """End to end with the real refresh code: the site publishes a newer market, the app's timer checks, and the
    open details window shows the new numbers with nobody clicking anything."""
    import json

    from PySide6.QtWidgets import QLabel

    from maplehelper.ui.marketview import MarketDetailsDialog
    for name, value in (("_snap", None), ("_loaded", False), ("_checked", 0.0), ("_failed", False)):
        monkeypatch.setattr(mesowatch, name, value)
    monkeypatch.setattr(mesowatch, "_file", lambda: tmp_path / "mw.json")
    monkeypatch.setattr(mesowatch, "face_file", lambda snap_, who, timeout=10: None)
    now = time.time()
    site = {"price": 229000.0, "at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 600))}  # 10 min ago

    def doc():
        return {"version": 1, "market": "Classic World", "preview": False, "generated_at": site["at"],
                "items": [{"id": "cash:01007145", "name": "Black Cat Beanie", "price": site["price"], "sold": 19,
                           "lowData": False, "history": [], "listings": [], "category": "Cash Shop"}], "sales": []}

    def request(url, etag="", timeout=30):
        if url == mesowatch.INDEX_URL:
            return 200, json.dumps({"markets": [{"id": "Classic World", "label": "Windia",
                                                 "updated": site["at"]}]}).encode(), ""
        if url == mesowatch.FACES_URL:
            return 200, b'{"faces": {}}', ""
        return 200, json.dumps(doc()).encode(), '"' + site["at"] + '"'
    monkeypatch.setattr(mesowatch, "_request", request)
    kb = FakeKB({"item/3198": "Black Cat Beanie"})
    mesowatch.snapshot()
    d = MarketDetailsDialog(kb, "en", "", None, None)
    d.show_item("item/3198")
    assert any("229,000" in w.text() for w in d.findChildren(QLabel))
    # the site publishes a newer market; 15 minutes later the app's timer checks (mesowatch.warm -> snapshot)
    site["price"], site["at"] = 251000.0, time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now))
    mesowatch._snap.fetched -= mesowatch.REFRESH_SECONDS
    mesowatch._checked -= mesowatch.REFRESH_SECONDS
    mesowatch.snapshot()
    d._follow()                                          # the window's own poll (every minute)
    assert any("251,000" in w.text() for w in d.findChildren(QLabel))
    d.close()
    d.deleteLater()           # (no window left behind for the next tests to restyle)
