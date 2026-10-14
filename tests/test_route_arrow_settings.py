"""The route arrow's Settings switch (Minimap section): on by default, and Save stores it."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_the_switch_is_on_by_default_and_saves(qapp, isolated_store, kb, monkeypatch):
    from maplehelper import providers
    from maplehelper.ui.dialogs import SettingsDialog
    for name in ("claude", "codex"):
        monkeypatch.setattr(type(providers.get(name)), "account",
                            lambda self: {"status": "logged_out", "email": None, "method": None})
        monkeypatch.setattr(type(providers.get(name)), "status", lambda self: "logged_out")
    s = isolated_store.Settings()
    s["language"] = "en"
    s["provider"] = "claude"
    assert s["minimap_route_arrow"] is True
    dlg = SettingsDialog(s, isolated_store.Profiles(), kb, lambda *_: "")
    try:
        assert dlg.route_arrow.isChecked() and not dlg.unsaved()
        dlg.route_arrow.setChecked(False)
        assert dlg.unsaved()
        dlg._save()
        assert s["minimap_route_arrow"] is False
    finally:
        dlg.close()
