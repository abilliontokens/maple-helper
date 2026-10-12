"""The wishlist: per character, toggled from item cards, flagged when a KB update touches it; its window's search box
(ui/wishlist.py EntityPicker)."""
import sys
from types import SimpleNamespace

import pytest

from maplehelper import wishlist


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


class FakeSettings(dict):
    def __getitem__(self, k):
        return self.get(k)


def test_toggle_is_per_character():
    s = FakeSettings(wishlist={})
    assert wishlist.toggle(s, "kiwi", "item/1") is True
    assert wishlist.items(s, "kiwi") == ["item/1"] and wishlist.items(s, "other") == []
    assert wishlist.toggle(s, "kiwi", "item/1") is False
    assert wishlist.items(s, "kiwi") == []


def test_kb_update_touching_a_wished_item_is_flagged():
    kb = SimpleNamespace(get=lambda k: {"item/1": {"name": "Blue Potion"}, "item/2": {"name": "Ilbi"}}.get(k))
    entries = [{"changed": [{"key": "monster/2", "name": "Snail", "drops_added": ["Blue Potion"]}],
                "added": [{"key": "item/2", "name": "Ilbi"}]}]
    assert set(wishlist.touched(entries, ["item/1", "item/2"], kb)) == {"Blue Potion", "Ilbi"}
    assert wishlist.touched(entries, [], kb) == []


def test_a_misspelt_search_offers_the_names_close_to_it(qapp):
    # "stelly" found nothing in a list holding Steely Throwing Knives (the owner)
    from PySide6.QtTest import QTest

    from maplehelper.ui.wishlist import EntityPicker
    names = ["Steely Throwing Knives", "Steel Ore", "Subi Throwing-Stars", "Blue Snail Shell"]
    p = EntityPicker([(n, n, None) for n in names], "x")
    p.show()
    p.setFocus()
    QTest.keyClicks(p, "stelly")
    qapp.processEvents()
    c = p.completer()
    assert [c.completionModel().index(i, 0).data() for i in range(c.completionCount())] == ["Steely Throwing Knives"]
    p.setText(c.completionModel().index(0, 0).data(c.completionRole()))
    p._chosen()
    assert p.text() == "Steely Throwing Knives"           # the name, not the misspelling it was found by
    p.close()


def test_the_search_box_x_shows_however_the_text_got_there(qapp):
    # text set with the box's signals held back: the X showed only after typing (the owner)
    from maplehelper.ui.wishlist import EntityPicker
    p = EntityPicker([("Bronze Helmet", "Bronze Helmet", None)], "x")
    p.blockSignals(True)
    p.setText("Bronze Helmet")
    p.blockSignals(False)
    assert p._clear.isVisible()
    p.blockSignals(True)
    p.clear()
    p.blockSignals(False)
    assert not p._clear.isVisible()


def test_a_deleted_picker_never_fits_its_list(qapp, monkeypatch):
    """An uncaught 'Internal C++ object (EntityPicker) already deleted' from a timer that outlived the picker."""
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QEvent

    from maplehelper.ui.wishlist import EntityPicker
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: errors.append(a))
    p = EntityPicker([("Fire Boar", "Fire Boar", None)], "Monster")
    p.setText("Fire")
    p.completer().complete()                 # the list shows: _fit_popup waits for the next turn of the loop
    p.completer().popup().show()
    shiboken6.delete(p)                      # its window closed meanwhile
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.processEvents()
    assert errors == []
