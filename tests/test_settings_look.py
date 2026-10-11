"""Settings' look of the app's own windows (ui/dialogs.py, with ui/lookpick.py's pickers): the six glass tints as
tiles and the six accents as dots, the saved ones checked and named; a pick and a click on the opacity slider are
saved with the rest on Save, into app_tint / app_accent / app_opacity; in Hebrew the tiles run from the right and the
slider starts there (offscreen Qt, no real CLI, no sign-in)."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(qapp, isolated_store, kb, monkeypatch):
    from maplehelper import providers, voice
    for p in providers.PROVIDERS.values():
        monkeypatch.setattr(type(p), "account", lambda self: {"status": "not_installed", "email": None, "method": None})
        monkeypatch.setattr(type(p), "status", lambda self: "not_installed")
        monkeypatch.setattr(type(p), "models", lambda self: [(None, "")])
        monkeypatch.setattr(type(p), "read_limits", lambda self, *a, **k: None)
        monkeypatch.setattr(type(p), "find_exe", lambda self: None)
    monkeypatch.setattr(voice, "input_devices", lambda: [])
    s = isolated_store.Settings()
    s["language"] = "en"
    s["provider"] = "claude"
    before = set(threading.enumerate())
    yield s, isolated_store.Profiles(), kb, isolated_store
    # the dialog's account checks run on threads: they end before the dialog is freed
    for th in set(threading.enumerate()) - before:
        th.join(timeout=5)


def _settings(env, shown: bool = False):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from maplehelper.ui.dialogs import SettingsDialog
    s, profiles, kb, _ = env
    dlg = SettingsDialog(s, profiles, kb, lambda *_: "")
    if shown:                                   # laid out at its own width: the slider's percents have their places
        dlg.setAttribute(Qt.WA_DontShowOnScreen)
        dlg.show()
        QApplication.processEvents()
    return dlg


def _swatches(row) -> dict:
    from maplehelper.ui.lookpick import Swatch
    return {b.property("key"): b for b in row.findChildren(Swatch)}


def test_the_six_tints_and_accents_show_with_the_saved_ones_checked(env):
    from maplehelper.ui import theme
    s = env[0]
    s["app_tint"], s["app_accent"], s["app_opacity"] = "forest", "teal", 0.75
    dlg = _settings(env)
    try:
        tiles, dots = _swatches(dlg.look_tints), _swatches(dlg.look_accents)
        assert list(tiles) == list(theme.TINTS) and list(dots) == list(theme.ACCENTS) and len(tiles) == len(dots) == 6
        assert [k for k, b in tiles.items() if b.isChecked()] == ["forest"]
        assert [k for k, b in dots.items() if b.isChecked()] == ["teal"]
        assert tiles["forest"]._ring.name() == theme.ACCENTS["teal"][1].lower()      # ringed in the picked accent
        assert dlg.look_tint_name.text() == "Forest" and dlg.look_accent_name.text() == "Teal"
        assert dlg.look_opacity.value() == 0.75 and dlg.look_opacity_value.text() == "75%"
        assert not dlg.unsaved()
    finally:
        dlg.close()


def test_a_stale_look_shows_the_default_one(env):
    s = env[0]
    s["app_tint"], s["app_accent"] = "plaid", "neon"            # names the catalog no longer has
    dlg = _settings(env)
    try:
        assert [k for k, b in _swatches(dlg.look_tints).items() if b.isChecked()] == ["white"]
        assert [k for k, b in _swatches(dlg.look_accents).items() if b.isChecked()] == ["orange"]
    finally:
        dlg.close()


def test_picks_and_the_slider_are_saved_with_save(env):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    s, isolated_store = env[0], env[3]
    dlg = _settings(env, shown=True)
    try:
        tiles, dots = _swatches(dlg.look_tints), _swatches(dlg.look_accents)
        tiles["white"].click()                                   # the picked one again: it stays picked
        assert tiles["white"].isChecked() and not dlg.unsaved()
        tiles["midnight"].click()
        dots["blue"].click()
        sl = dlg.look_opacity
        QTest.mouseClick(sl, Qt.LeftButton, pos=QPoint(round(sl._x(0.6)), sl.height() // 2))
        assert [k for k, b in tiles.items() if b.isChecked()] == ["midnight"]
        assert [k for k, b in dots.items() if b.isChecked()] == ["blue"]
        assert dlg.look_tint_name.text() == "Midnight blue" and dlg.look_opacity_value.text() == "60%"
        assert dlg.unsaved() and s["app_tint"] == "white"          # nothing is saved before Save
        dlg.save_btn.click()
        assert (s["app_tint"], s["app_accent"], s["app_opacity"]) == ("midnight", "blue", 0.6)
        again = isolated_store.Settings()                          # written to the file too
        assert (again["app_tint"], again["app_accent"], again["app_opacity"]) == ("midnight", "blue", 0.6)
        assert "appearance" not in again.data
    finally:
        dlg.close()


def test_six_tiles_fit_the_window_at_36_px_or_more(env):
    dlg = _settings(env, shown=True)
    try:
        row = dlg.look_tints
        tiles = list(_swatches(row).values())
        assert all(b.width() >= 36 and b.height() == 36 for b in tiles)
        assert tiles[0].x() >= 0 and tiles[-1].geometry().right() < row.width()
        dots = list(_swatches(dlg.look_accents).values())
        assert dots[-1].geometry().right() < dlg.look_accents.width()
    finally:
        dlg.close()


def test_the_keyboard_moves_the_slider_and_picks_a_tile(env):
    """The old dark/light buttons took the keyboard: so do the tiles, the dots and the slider (the ⚙ panel's never
    take it, over the game)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    dlg = _settings(env, shown=True)
    try:
        sl = dlg.look_opacity
        assert sl.focusPolicy() & Qt.TabFocus
        QTest.keyClick(sl, Qt.Key_Left)
        assert sl.value() == 0.99 and dlg.look_opacity_value.text() == "99%"
        QTest.keyClick(sl, Qt.Key_PageDown)
        assert sl.value() == 0.89
        QTest.keyClick(sl, Qt.Key_Home)
        assert sl.value() == 0.3
        tile = _swatches(dlg.look_tints)["slate"]
        assert tile.focusPolicy() & Qt.TabFocus
        QTest.keyClick(tile, Qt.Key_Space)
        assert dlg._values()["app_tint"] == "slate" and dlg.look_tint_name.text() == "Slate"
    finally:
        dlg.close()


def test_hebrew_runs_the_tiles_and_the_slider_from_the_right(env):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLabel

    from maplehelper import bidi
    from maplehelper.ui import theme
    env[0]["language"] = "he"
    dlg = _settings(env, shown=True)
    try:
        tiles, dots = list(_swatches(dlg.look_tints).values()), list(_swatches(dlg.look_accents).values())
        assert tiles[0].x() > tiles[-1].x() and dots[0].x() > dots[-1].x()       # the first one on the right
        sl = dlg.look_opacity
        assert sl._x(theme.OPACITY_MIN) > sl._x(theme.OPACITY_MAX)               # the most see-through end on the right
        assert dlg.look_tint_name.text() == bidi.plain("לבן", True)
        label = dlg.look_tint_name.parentWidget().findChild(QLabel, "RowLabel")
        assert label.text() == bidi.plain("צבע הזכוכית", True) and label.x() > dlg.look_tint_name.x()
        QTest.keyClick(sl, Qt.Key_Right)                                          # → toward the start there
        assert sl.value() == 0.99
    finally:
        dlg.close()


@pytest.mark.parametrize("key", ["appearance_dark_short", "appearance_light_short"])
def test_the_old_dark_and_light_names_are_gone(key):
    from maplehelper.i18n import STRINGS
    assert key not in STRINGS
