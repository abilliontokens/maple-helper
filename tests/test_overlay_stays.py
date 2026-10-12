"""Every window over the game stays up when the player clicks the game. macOS hides an app's tool windows whenever
another app is in front (NSWindow.hidesOnDeactivate, which Qt sets for Qt.Tool unless WA_MacAlwaysShowToolWindow
is set before the native window is made): a click on the game took the bar and its windows away (2026-10-11)."""
import os

import pytest
from PySide6.QtCore import QEvent, Qt

from maplehelper.i18n import I18n

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _windows(kb, s, profiles):
    """Each window that floats over the game, made as the app makes it (the companion windows through their owner)."""
    from maplehelper.ui.craftadvisor import CraftAdvisor, ForgePlanWindow
    from maplehelper.ui.gamesearch import DetailWindow, GameSearch
    from maplehelper.ui.gametoolbar import GameToolbar, _SettingsPanel
    from maplehelper.ui.gearadvisor import GearAdvisor
    from maplehelper.ui.grindbar import GrindBar
    from maplehelper.ui.grindwindow import GrindWindow
    from maplehelper.ui.lootoverlay import LootOverlay
    from maplehelper.ui.lootscan import LootScanner
    from maplehelper.ui.npcoverlay import GuideWindow, NpcOverlay
    from maplehelper.ui.portaldots import PortalDots
    from maplehelper.ui.scrollplanner import ScrollPlanner
    t = I18n("en")
    bar = GameToolbar(s, t)
    npc = NpcOverlay(kb, s, t)
    search = GameSearch(kb, s, t)
    craft = CraftAdvisor(kb, s, profiles, t)
    scanner = LootScanner(kb, profiles, s)
    made = {"bar": bar, "bar settings": _SettingsPanel(bar), "NPCs here": npc, "guide": GuideWindow(npc),
            "search": search, "search page": DetailWindow(search), "loot log": LootOverlay(scanner, s, kb, t),
            "scroll planner": ScrollPlanner(kb, s, profiles, t), "gear": GearAdvisor(kb, s, profiles, t),
            "crafting": craft, "forge plan": ForgePlanWindow(craft), "portal dots": PortalDots(kb, s),
            "grind bar": GrindBar(scanner, s, kb, profiles, t),
            "grind window": GrindWindow(kb, s, profiles, scanner, t)}
    return made, scanner


def test_every_window_over_the_game_stays_when_the_game_is_clicked(qapp, kb, isolated_store):
    made, scanner = _windows(kb, isolated_store.Settings(), isolated_store.Profiles())
    try:
        assert [name for name, w in made.items() if not w.testAttribute(Qt.WA_MacAlwaysShowToolWindow)] == []
        # and it is set before Qt made the native window, the only time Qt hands it on
        assert all(w.windowHandle() is None for w in made.values())
    finally:
        for w in made.values():
            w.hide()
            w.deleteLater()
        scanner.deleteLater()
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)
        qapp.processEvents()
