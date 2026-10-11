"""Settings' look shown live (ui/dialogs.py look_previewed, app.py preview_look): a tile, a dot or the slider shows
on the open windows at once, while the settings file keeps the saved look until Save; closing Settings without
saving puts the saved look back, once; Save keeps the picked one and writes it (offscreen Qt, no real CLI, no
sign-in)."""
import os
import threading
from types import SimpleNamespace

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
    from maplehelper.ui import theme
    for p in providers.PROVIDERS.values():
        monkeypatch.setattr(type(p), "account", lambda self: {"status": "not_installed", "email": None, "method": None})
        monkeypatch.setattr(type(p), "status", lambda self: "not_installed")
        monkeypatch.setattr(type(p), "models", lambda self: [(None, "")])
        monkeypatch.setattr(type(p), "read_limits", lambda self, *a, **k: None)
        monkeypatch.setattr(type(p), "find_exe", lambda self: None)
    monkeypatch.setattr(voice, "input_devices", lambda: [])
    monkeypatch.setattr(theme, "high_contrast", lambda: None)      # the picked look, whatever the desktop's is
    s = isolated_store.Settings()
    s["language"] = "en"
    s["provider"] = "claude"
    s["app_tint"], s["app_accent"], s["app_opacity"] = "forest", "teal", 0.75
    sheet = qapp.styleSheet()
    before = set(threading.enumerate())
    yield s, isolated_store.Profiles(), kb, isolated_store
    # the dialog's account checks run on threads: they end before the dialog is freed
    for th in set(threading.enumerate()) - before:
        th.join(timeout=5)
    qapp.setStyleSheet(sheet)
    theme._use("white", "orange", theme.OPACITY_MAX, None)        # the module's own default look, for later tests


def _app(env):
    """What preview_look needs of the app: its settings, the QApplication and the font, in the saved look (as
    App.style() sets it at start: the theme and the app's style sheet)."""
    from PySide6.QtWidgets import QApplication

    from maplehelper import app
    from maplehelper.ui import theme
    s = env[0]
    fake = SimpleNamespace(settings=s, qapp=QApplication.instance(), font_family="Rubik", _look=app._look_of(s))
    theme.set_look(s["app_tint"], s["app_accent"], s["app_opacity"])
    fake.qapp.setStyleSheet(theme.stylesheet(fake.font_family, s["font_size"]))
    return fake


def _settings(env, fake):
    """Settings shown as App.open_settings opens it: its own copy of the app's style sheet, its look_previewed wired
    to the app's preview_look."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from maplehelper import app
    from maplehelper.ui.dialogs import SettingsDialog
    s, profiles, kb, _ = env
    dlg = SettingsDialog(s, profiles, kb, lambda *_: app.MapleHelperApp.style(fake))
    seen = []
    dlg.look_previewed.connect(lambda *a: seen.append(a))
    dlg.look_previewed.connect(lambda *a: app.MapleHelperApp.preview_look(fake, *a))
    dlg.setAttribute(Qt.WA_DontShowOnScreen)
    dlg.show()
    QApplication.processEvents()
    return dlg, seen


def _swatches(row) -> dict:
    from maplehelper.ui.lookpick import Swatch
    return {b.property("key"): b for b in row.findChildren(Swatch)}


def _saved(env) -> tuple:
    again = env[3].Settings()                                   # what the file holds
    return again["app_tint"], again["app_accent"], again["app_opacity"]


def test_a_tile_shows_its_glass_at_once_and_saves_nothing(env):
    from maplehelper import app
    from maplehelper.ui import theme
    s = env[0]
    fake = _app(env)
    dlg, seen = _settings(env, fake)
    try:
        saved_css = fake.qapp.styleSheet()
        assert dlg.styleSheet() == saved_css                   # built in the app's style sheet (style())
        box = dlg.toolbar_hotkey.styleSheet()
        _swatches(dlg.look_tints)["midnight"].click()
        assert seen == [("midnight", "teal", 0.75)]
        assert theme.TINT == theme.TINTS["midnight"][1] and theme.MODE == "dark"
        css = theme.stylesheet(fake.font_family, s["font_size"])
        assert dlg.styleSheet() == css != saved_css           # Settings itself restyled
        assert fake.qapp.styleSheet() == saved_css             # the app's own (every widget re-polished) on Save only
        assert s["app_tint"] == "forest" and _saved(env) == ("forest", "teal", 0.75)
        assert fake._look == app._look_of(s)                   # Save will still see a new look
        assert dlg.unsaved()                                   # the X asks about it
        # a window built meanwhile (the X's question) is built in the look on screen, not the saved one
        assert app.MapleHelperApp.style(fake) == css and theme.TINT == theme.TINTS["midnight"][1]
        assert fake.qapp.styleSheet() == saved_css
        _swatches(dlg.look_tints)["midnight"].click()          # the same tile again: nothing new to show
        assert len(seen) == 1
        _swatches(dlg.look_accents)["blue"].click()
        assert seen[-1] == ("midnight", "blue", 0.75) and theme.ACCENT == theme.ACCENTS["blue"][1]
        assert dlg.toolbar_hotkey.styleSheet() != box          # Settings' key box (a sheet of its own) follows too
    finally:
        dlg.close()


def test_the_slider_shows_every_percent_without_restyling(env):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from maplehelper.ui import theme
    fake = _app(env)
    dlg, seen = _settings(env, fake)
    try:
        css = fake.qapp.styleSheet()
        sl = dlg.look_opacity
        QTest.keyClick(sl, Qt.Key_Left)
        assert seen == [("forest", "teal", 0.74)] and theme.OPACITY == 0.74
        QTest.mouseClick(sl, Qt.LeftButton, pos=QPoint(round(sl._x(0.6)), sl.height() // 2))
        assert seen[-1] == ("forest", "teal", 0.6) and theme.OPACITY == 0.6
        assert theme.P()["solid_alpha"] == 0.6                # what paint_glass paints with
        assert fake.qapp.styleSheet() == css                  # the opacity alone: no restyle
        assert env[0]["app_opacity"] == 0.75 and _saved(env)[2] == 0.75
    finally:
        dlg.close()


def test_closing_without_saving_puts_the_saved_look_back_once(env, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    from maplehelper.ui import dialogs, theme
    s = env[0]
    fake = _app(env)
    css = fake.qapp.styleSheet()
    chat = QWidget()                                           # another open window in the app's style sheet + its own
    chat.setStyleSheet(css + "#Mine {}")
    chat.setAttribute(Qt.WA_DontShowOnScreen)
    chat.show()
    dlg, seen = _settings(env, fake)
    try:
        _swatches(dlg.look_tints)["midnight"].click()
        _swatches(dlg.look_accents)["pink"].click()
        dlg.look_opacity.set_value(0.5)
        dlg._preview_look()
        assert (theme.TINT, theme.ACCENT, theme.OPACITY) == (theme.TINTS["midnight"][1], theme.ACCENTS["pink"][1], 0.5)
        assert chat.styleSheet() == theme.stylesheet(fake.font_family, s["font_size"]) + "#Mine {}"
        # the X asks (a look pick is a change) and the player doesn't save
        monkeypatch.setattr(dialogs.ConfirmDialog, "exec", lambda self: setattr(self, "choice", "no") or 0)
        dlg._close_clicked()
        assert seen[-1] == ("forest", "teal", 0.75)
        assert (theme.TINT, theme.ACCENT, theme.OPACITY) == (theme.TINTS["forest"][1], theme.ACCENTS["teal"][1], 0.75)
        assert chat.styleSheet() == css + "#Mine {}" and fake.qapp.styleSheet() == css
        assert fake._preview is None and fake._preview_css is None
        n = len(seen)
        dlg.reject()                                           # closed again: nothing more to put back
        assert len(seen) == n
        assert (s["app_tint"], s["app_accent"], s["app_opacity"]) == _saved(env) == ("forest", "teal", 0.75)
    finally:
        dlg.close()
        chat.close()
        chat.deleteLater()


def test_closing_with_nothing_previewed_sends_nothing(env):
    fake = _app(env)
    dlg, seen = _settings(env, fake)
    dlg.close()
    assert seen == []


def test_save_keeps_the_picked_look_and_writes_it(env):
    from maplehelper import app
    from maplehelper.ui import theme
    s = env[0]
    fake = _app(env)
    dlg, seen = _settings(env, fake)
    try:
        _swatches(dlg.look_tints)["midnight"].click()
        dlg.look_opacity.set_value(0.6)
        dlg._preview_look()
        n = len(seen)
        dlg.save_btn.click()
        assert len(seen) == n                                  # not put back
        assert theme.TINT == theme.TINTS["midnight"][1] and theme.OPACITY == 0.6
        assert (s["app_tint"], s["app_accent"], s["app_opacity"]) == _saved(env) == ("midnight", "teal", 0.6)
        assert app._look_of(s) != fake._look                   # on_settings_changed restyles everything
    finally:
        dlg.close()
