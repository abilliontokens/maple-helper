"""The bar over the game (ui/gametoolbar.py): shown from its own setting, its NPCs-here button flipping the
NPCs window's setting (the window follows the signal), its search buttons naming their search, the mode lit back
on the button that opened it, the ✕ turning the bar off (and saying so, for the app's how-to-bring-it-back toast),
and its place on the screen — above the minimap's box (LOCATION.box) and with it, at the saved spot, and the spot
kept after a drag. Its width is the player's too: the buttons wrap into as many rows as the width leaves room for.
Every button has its line icon in its text's colours; in icons mode the icon alone. The ⚙ panel's choices (the glass
tint, the accent, the transparency, icons instead of words, the bar's key, the Minimap switches, Reset) are written
and followed live; the panel is no taller than its screen, its sections scrolling under its title row."""
import os

import pytest
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QPushButton
from PySide6.QtTest import QTest

from maplehelper import bidi
from maplehelper.i18n import I18n

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _todays_look():
    """The glass tint every window paints is module state: a test that picks a preset puts today's dark back,
    or the next test file's windows paint midnight."""
    from maplehelper.ui import npcoverlay
    yield
    npcoverlay.apply_look({"overlay_tint": "dark"})


@pytest.fixture
def bar(qapp, isolated_store):
    from maplehelper.ui import gametoolbar
    from maplehelper.ui.location import LOCATION
    old, LOCATION.box = LOCATION.box, None
    s = isolated_store.Settings()
    w = gametoolbar.GameToolbar(s, I18n("en"))
    yield w, s
    LOCATION.boxed.disconnect(w._box_moved)
    LOCATION.box = old
    w.close()
    if w._panel is not None:
        w._panel.close()


# ------------------------------------------------------------ its setting

def test_it_shows_only_while_the_setting_is_on(bar):
    w, s = bar
    s["game_toolbar"] = False
    w.refresh()
    assert not w.isVisible()
    s["game_toolbar"] = True
    w.refresh()
    assert w.isVisible()


def test_the_npcs_here_button_flips_the_windows_setting_both_ways(bar):
    w, s = bar
    s["npc_overlay"] = False
    w.refresh()
    assert w._npcs.isChecked() is False
    w._npcs.click()
    assert s["npc_overlay"] is True and w._npcs.isChecked() is True
    w._npcs.click()
    assert s["npc_overlay"] is False and w._npcs.isChecked() is False


def test_flipping_the_npcs_here_button_signals_it(bar):
    w, _ = bar
    w.refresh()
    seen = []
    w.npc_toggled.connect(lambda: seen.append(True))
    w._npcs.click()
    assert seen == [True]


def test_refresh_keeps_the_button_in_step_with_the_setting(bar):
    """The window's own ✕ turned the setting off (its closed signal refreshes the bar): the button follows."""
    w, s = bar
    w.refresh()
    w._npcs.click()                     # on, by the button itself
    s["npc_overlay"] = False            # ...then off somewhere else
    w.refresh()
    assert w._npcs.isChecked() is False


def test_cabs_and_teleports_is_a_switch_in_the_gear_panel_off_at_first(bar):
    """Off on a new install: the way to a found NPC walks until the player turns cabs and NPC teleports on, in the ⚙
    panel's Directions (no button on the bar any more); each flip is written and said with the bar's rides_toggled,
    which the app follows."""
    w, s = bar
    w.refresh()
    assert "tb_rides" not in [key for _, key in w._buttons()]
    seen = []
    w.rides_toggled.connect(lambda: seen.append(s["game_rides"]))
    w._gear.click()
    p = w._panel
    assert p._way_head.text() == "DIRECTIONS" and p._rides_label.text() == "Cabs & Teleports"
    assert p._rides.isChecked() is False and s["game_rides"] is False
    p._rides.click()
    p._rides.click()
    assert seen == [True, False]
    s["game_rides"], s["overlay_accent"] = True, "pink"     # kept from last time: the switch opens on
    w.refresh()
    assert p._rides.isChecked() is True and p._reset.isEnabled()
    p._reset.click()                    # no look: Reset leaves it
    assert s["game_rides"] is True and s["overlay_accent"] == "green"


# ------------------------------------------------------------ the searches

@pytest.mark.parametrize("kind,text", [("monster_npc", "Monsters & NPCs"), ("map", "Maps"), ("item", "Items"),
                                       ("sell", "Safe To Sell")])
def test_each_search_button_names_its_search(bar, kind, text):
    w, _ = bar
    assert w._search[kind].text().replace("&&", "&") == text      # ("&&": Qt shows one "&", not a shortcut)
    seen = []
    w.search_requested.connect(seen.append)
    w._search[kind].click()
    assert seen == [kind]


def test_the_search_buttons_in_order(bar):
    """Monsters and NPCs one button, then Maps, Items and Safe to sell?, in that order on the bar."""
    w, _ = bar
    assert list(w._search) == ["monster_npc", "map", "item", "sell"]


def test_set_search_mode_lights_only_that_button(bar):
    w, _ = bar
    w.set_search_mode("item")
    assert [w._search[k].property("on") for k in ("monster_npc", "item", "sell")] == [False, True, False]
    w.set_search_mode("")
    assert [w._search[k].property("on") for k in ("monster_npc", "item", "sell")] == [False, False, False]


def test_the_loot_log_button_is_the_loot_windows_setting(bar):
    """As NPCs here is its window's: the button flips settings["loot_overlay"] and says so; refresh follows the
    setting (the window's ✕, or a log starting, changed it)."""
    w, s = bar
    seen = []
    w.loot_toggled.connect(lambda: seen.append(s["loot_overlay"]))
    assert w._loot.text() == "Loot Log" and not w._loot.isChecked()
    w._loot.click()
    assert seen == [True] and s["loot_overlay"] is True
    w._loot.click()
    assert seen == [True, False]
    s["loot_overlay"] = True
    w.refresh()
    assert w._loot.isChecked()


TOOL_NAMES = ["Grind spots", "Farm", "Quests", "Citizenship", "Build & skills", "Gear", "Scrolls", "Crafting",
              "Cash shop"]


@pytest.mark.parametrize("key,name", [("grind_spots", "Grind spots"), ("farm_tool", "Farm"), ("quest_tool", "Quests"),
                                      ("citizenship", "Citizenship"), ("build_tool", "Build & skills"),
                                      ("gear_advisor", "Gear"), ("scroll_planner", "Scrolls"),
                                      ("craft_advisor", "Crafting"), ("cash_shop", "Cash shop")])
def test_each_tool_in_the_tools_card_is_its_windows_setting(bar, key, name):
    """Each tool in the Tools card flips its window's setting and names it in tool_toggled, and refresh follows the
    setting (the window's ✕ turned it off), the button lit while it is on."""
    from maplehelper.ui import gametoolbar
    w, s = bar
    w.refresh()
    seen = []
    w.tool_toggled.connect(lambda k: seen.append((k, s[k])))
    b = w._tools[key]
    assert b.accessibleName() == name and b.text() == name.replace("&", "&&")   # "&" alone: Qt's shortcut mark
    assert b.toolTip() == w.t(gametoolbar.TOOLS[key] + "_tip") and not b.isChecked()
    b.click()
    b.click()
    assert seen == [(key, True), (key, False)]
    s[key] = True
    w.refresh()
    assert b.isChecked()
    assert [k for k in w._tools if w._tools[k].isChecked()] == [key]     # the other ones stay off


def test_tools_opens_its_card_under_the_bar_and_a_pick_tools_again_or_a_move_closes_it(bar):
    """Tools, after Loot Log and Grind, lit while its card is up; the card under the lying bar holds the nine tools.
    It goes on a pick (the window opening), on Tools again, and when the bar is dragged away."""
    from maplehelper.ui import gametoolbar
    w, s = bar
    w.refresh()
    keys = [key for _, key in w._buttons()]
    at = keys.index("tb_loot")
    assert keys[at + 1:at + 3] == ["tb_grind", "tb_tools"] and w._tools_btn.text() == "Tools"
    assert [b.accessibleName() for b in w._tools.values()] == TOOL_NAMES and not w._menu.isVisible()
    w._tools_btn.click()
    m = w._menu
    assert m.isVisible() and w._tools_btn.property("on") is True
    assert m.y() + gametoolbar.SHADOW > w.y() + w.height() - gametoolbar.SHADOW     # its glass below the bar's
    w._tools["gear_advisor"].click()
    assert not m.isVisible() and s["gear_advisor"] is True and w._tools_btn.property("on") is False
    w._tools_btn.click()
    w._tools_btn.click()
    assert not m.isVisible()
    w._tools_btn.click()
    w.move(w.x() + 5, w.y())
    assert not m.isVisible()


def test_the_tools_card_stands_beside_an_upright_bar(bar):
    from maplehelper.ui import gametoolbar
    w, s = bar
    s["game_toolbar_vertical"] = True
    w.refresh()
    w._tools_btn.click()
    m = w._menu
    assert m.x() + gametoolbar.SHADOW > w.x() + w.width() - gametoolbar.SHADOW      # at its side, not under it
    assert abs(m.y() + gametoolbar.SHADOW - w._tools_btn.mapToGlobal(QPoint(0, 0)).y()) <= 8


@pytest.mark.parametrize("lang", ["en", "he"])
def test_the_tools_card_reads_in_rows_from_the_leading_edge_all_one_width(qapp, isolated_store, lang):
    """The nine tools in TOOLS' order, MENU_COLS a row read from the leading edge (the right, in Hebrew), every
    button as wide as the widest whatever the language's words."""
    from maplehelper.ui import gametoolbar
    w = gametoolbar.GameToolbar(isolated_store.Settings(), I18n(lang))
    try:
        w.refresh()
        w._tools_btn.click()
        t, cols = I18n(lang), gametoolbar.MENU_COLS
        buttons = list(w._tools.values())
        assert [b.accessibleName() for b in buttons] == [t(name) for name in gametoolbar.TOOLS.values()]
        assert len({b.width() for b in buttons}) == 1
        for i, b in enumerate(buttons):
            row, col = divmod(i, cols)
            assert b.y() == buttons[row * cols].y() and (row == 0 or b.y() > buttons[(row - 1) * cols].y())
            if col:
                before = buttons[i - 1]
                assert b.x() < before.x() if lang == "he" else b.x() > before.x()
    finally:
        w.close()


def test_the_tools_card_goes_once_the_mouse_has_been_away_a_second(bar, monkeypatch):
    """It takes no focus to lose: the mouse off the card and the Tools button for AWAY_MS closes it, and the mouse
    back over either before that keeps it."""
    from types import SimpleNamespace

    from maplehelper.ui import gametoolbar
    w, _ = bar
    w.refresh()
    w._tools_btn.click()
    m = w._menu
    clock, where = [100.0], [m.frameGeometry().center()]
    monkeypatch.setattr(gametoolbar, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(gametoolbar, "QCursor", SimpleNamespace(pos=lambda: where[0]))
    m._check_away()
    where[0] = QPoint(-5000, -5000)
    m._check_away()
    clock[0] += 0.9
    m._check_away()
    assert m.isVisible()
    where[0] = w._tools_btn.mapToGlobal(QPoint(2, 2))           # back over the button: the wait starts over
    m._check_away()
    where[0] = QPoint(-5000, -5000)
    clock[0] += 0.5
    m._check_away()
    clock[0] += 0.9
    m._check_away()
    assert m.isVisible()
    clock[0] += gametoolbar.AWAY_MS / 1000
    m._check_away()
    assert not m.isVisible() and w._tools_btn.property("on") is False


def test_the_x_turns_the_setting_off_hides_and_says_so(bar):
    """closed is what the app's how-to-bring-it-back toast and the open Settings window's switch follow."""
    w, s = bar
    seen = []
    w.closed.connect(lambda: seen.append(s["game_toolbar"]))
    w.refresh()
    w._close.click()
    assert s["game_toolbar"] is False and not w.isVisible()
    assert seen == [False]


def test_apply_language_retexts_and_mirrors(bar):
    w, _ = bar
    w.apply_language(I18n("he"))
    assert w._npcs.text() == bidi.plain("דמויות כאן", True)
    assert w.layoutDirection() == Qt.RightToLeft
    w.apply_language(I18n("en"))
    assert w._npcs.text() == "NPCs Here" and w.layoutDirection() == Qt.LeftToRight


# ------------------------------------------------------------ its length (the buttons wrap, words become icons)

def _rows(w):
    return len({b.y() for b, _ in w._buttons()})


def _drag(w, width: int, height: int) -> None:
    """A drag of the bar's end: the size changes, and the other side follows just after (never inside the resize:
    that cancelled Windows' own drag)."""
    from PySide6.QtWidgets import QApplication
    w.resize(width, height)
    QApplication.processEvents()


def test_a_narrower_bar_wraps_its_buttons_into_rows(bar):
    """The buttons wrap into as many rows as the width leaves room for, the bar's height following; at the
    narrowest width it goes — its biggest single icon — a button or two a row, not all on one."""
    w, s = bar
    w.refresh()
    one_row = w.height()
    s["game_toolbar_width"] = w._limits()[0]
    w.refresh()
    assert _rows(w) >= 5
    assert w.height() > one_row


def test_the_bar_goes_narrower_than_one_row_of_words(bar):
    """Its side dragged in only ever made it wider: Qt on Windows refuses a system resize narrower than the width a
    window's height fits when its layout says its height follows its width (2026-10-11). The bar's never says so,
    and goes down to its biggest icon."""
    w, s = bar
    w.refresh()
    _, natural = w._limits()
    assert not w.layout().hasHeightForWidth() and not w._flow.hasHeightForWidth()
    assert w.minimumWidth() < natural // 4


def test_too_narrow_for_the_words_the_buttons_show_icons_alone_and_back(bar):
    """Words while they fit in WORD_LINES_MAX rows; narrower, each button shows its icon alone (its name in the
    tooltip), and widening brings the words back. The ⚙'s icons choice isn't touched."""
    from maplehelper.ui import gametoolbar
    w, s = bar
    w.refresh()
    _, natural = w._limits()
    words = [s_[0] for s_ in w._sizes[False]]
    room = lambda width: width - 2 * gametoolbar.SIDE         # noqa: E731
    # the narrowest width the words still take two rows at, found as the bar finds it
    two = next(x for x in range(natural, 0, -1) if gametoolbar._lines(words, room(x - 1), gametoolbar.FLOW_GAP) > 2)
    _drag(w, two, w.height())
    assert w._npcs.text() == "NPCs Here" and _rows(w) == gametoolbar.WORD_LINES_MAX
    _drag(w, two - 1, w.height())                              # one pixel less: three rows of words, so icons
    assert all(b.text() == "" and b.toolTip() == w.t(key) for b, key in w._buttons())
    assert w._npcs.iconSize() == QSize(gametoolbar.ICON_PX, gametoolbar.ICON_PX)
    assert w.height() == w._flow.extent(w.width() - 2 * gametoolbar.SIDE) + gametoolbar.TOP + gametoolbar.BOTTOM
    _drag(w, two, w.height())
    assert w._npcs.text() == "NPCs Here" and _rows(w) == 2 and s["game_toolbar_icons"] is False


def test_the_dragged_width_is_kept_and_reopened(bar):
    """A width dragged at the bar's side settles into game_toolbar_width, and the next bar opens at it."""
    from maplehelper.ui import gametoolbar
    w, s = bar
    w.refresh()
    w._lengths.stop()                   # the debounced save, as the 400 ms timer would fire it
    w.resize(420, w.height())
    w._remember_length()
    assert s["game_toolbar_width"] == 420
    again = gametoolbar.GameToolbar(s, I18n("en"))
    again.refresh()
    assert again.width() == 420
    again.close()


def test_the_width_clamps_to_the_screen(bar):
    w, s = bar
    screen = QGuiApplication.primaryScreen().geometry()
    s["game_toolbar_width"] = screen.width() * 2
    w.refresh()
    assert w.width() <= screen.width()


def test_the_width_clamps_to_the_biggest_single_icon(bar):
    from maplehelper.ui import gametoolbar
    w, s = bar
    s["game_toolbar_width"] = 1
    w.refresh()
    assert w.width() == w._limits()[0]
    assert w.width() >= w._npcs.width() + 2 * gametoolbar.SIDE      # the button fits, margins and all


# ------------------------------------------------------------ upright (the ◯ before the grip)

def test_the_circle_stands_the_bar_upright_and_lays_it_back(bar):
    """The ◯ sits before the grip's dots; it turns the bar into a column (its top and bottom the ends to drag, its
    width as its column), kept in game_toolbar_vertical, and back into a row at the width it had."""
    w, s = bar
    w.refresh()
    width, rows = w.width(), _rows(w)
    assert w._orient.x() < w._grip.x() and w._orient.toolTip() == "Stand the toolbar upright"
    w._orient.click()
    assert s["game_toolbar_vertical"] is True and w.height() > w.width()
    xs = {b.x() for b, _ in w._buttons()}
    ys = [b.y() for b, _ in w._buttons()]
    assert len(xs) == 1 and ys == sorted(ys)                       # one column, in the bar's order
    assert w._grip.width() > w._grip.height()                       # its dots across the column
    mid = QPoint(w.width() // 2, 3)
    assert w._edges_at(mid) == Qt.TopEdge and w._edges_at(QPoint(3, w.height() // 2)) == Qt.Edge(0)
    assert w._orient.toolTip() == "Lay the toolbar flat"
    w._orient.click()
    assert s["game_toolbar_vertical"] is False and w.width() == width and _rows(w) == rows


def test_an_upright_bar_shorter_wraps_into_columns_and_keeps_its_height(bar):
    """Dragged shorter, the column wraps into columns and the buttons show icons alone; the height is kept in
    game_toolbar_height and the next bar opens upright at it."""
    from maplehelper.ui import gametoolbar
    w, s = bar
    s["game_toolbar_vertical"] = True
    w.refresh()
    _, natural = w._limits()
    one_column = w.width()
    w._lengths.stop()
    _drag(w, w.width(), natural // 4)
    assert len({b.x() for b, _ in w._buttons()}) >= 3 and w.width() > one_column
    assert all(b.text() == "" for b, _ in w._buttons())
    w._remember_length()
    assert s["game_toolbar_height"] == natural // 4
    again = gametoolbar.GameToolbar(s, I18n("en"))
    again.refresh()
    assert again.height() == natural // 4 and again._flow.upright
    again.close()


# ------------------------------------------------------------ the ⚙ panel

def test_the_gear_button_toggles_the_settings_panel(bar):
    w, _ = bar
    w.refresh()
    w._gear.click()
    assert w._panel is not None and w._panel.isVisible()
    w._gear.click()
    assert not w._panel.isVisible()


def test_the_panels_esc_and_x_close_it(bar):
    w, _ = bar
    w.refresh()
    w._gear.click()
    QTest.keyClick(w._panel, Qt.Key_Escape)
    assert not w._panel.isVisible()
    w._gear.click()
    w._panel._close.click()
    assert not w._panel.isVisible()


def test_a_tint_choice_is_written_and_painted_by_the_glass(bar):
    """The tint every window's _paint_glass paints follows the choice at once (npcoverlay's module state)."""
    from maplehelper.ui import npcoverlay
    w, s = bar
    w.refresh()
    w._gear.click()
    w._panel._pick_tint("midnight")
    assert s["overlay_tint"] == "midnight"
    assert npcoverlay.current_tint() == npcoverlay.TINTS["midnight"][1]


def test_an_accent_choice_restyles_the_bar(bar):
    from maplehelper.ui import npcoverlay
    w, s = bar
    w.refresh()
    w._gear.click()
    w._panel._pick_accent("blue")
    assert s["overlay_accent"] == "blue"
    assert npcoverlay.ACCENTS["blue"][1] in w.styleSheet()           # the lit buttons' new colour


def test_the_panel_rings_the_chosen_swatches(bar):
    w, s = bar
    s["overlay_tint"], s["overlay_accent"] = "wine", "pink"
    w._gear.click()
    assert [b.property("key") for b in w._panel._tints.findChildren(QPushButton) if b.isChecked()] == ["wine"]
    assert [b.property("key") for b in w._panel._accents.findChildren(QPushButton) if b.isChecked()] == ["pink"]


def _colours(icon, size, state) -> set[str]:
    """The colours a line icon draws in where its strokes cover a pixel whole (anti-aliased edges left out)."""
    img = icon.pixmap(size, QIcon.Normal, state).toImage()
    return {img.pixelColor(x, y).name() for y in range(img.height()) for x in range(img.width())
            if img.pixelColor(x, y).alpha() == 255}


def test_every_button_has_its_line_icon_in_its_texts_colours(bar):
    """Beside the words too: each button's icon drawn in the text colour, and in the accent's own text colour while
    the button is lit, checked or its search mode on (an emoji kept its own colours on the lit green)."""
    from maplehelper.ui import gametoolbar, npcoverlay
    w, s = bar
    w.refresh()
    for b, key in w._buttons():
        assert not b.icon().isNull() and b.text(), key
    size = QSize(gametoolbar.WORD_ICON_PX, gametoolbar.WORD_ICON_PX)
    _, on_fill = npcoverlay.accent_of(s)
    assert npcoverlay.DARK.text.lower() in _colours(w._search["map"].icon(), size, QIcon.Off)
    assert on_fill.lower() in _colours(w._search["map"].icon(), size, QIcon.On)
    w.set_search_mode("map")                   # lit by its mode, not checked
    assert _colours(w._search["map"].icon(), size, QIcon.Off) == {on_fill.lower()}
    w.set_search_mode("")
    assert on_fill.lower() not in _colours(w._search["map"].icon(), size, QIcon.Off)
    s["overlay_accent"] = "blue"               # a new accent: the lit icons take its text colour
    w.look_followed()
    assert npcoverlay.ACCENTS["blue"][2].lower() in _colours(w._search["map"].icon(), size, QIcon.On)
    s["overlay_accent"] = "pink"               # picked elsewhere: the app's refresh is enough
    w.refresh()
    assert npcoverlay.ACCENTS["pink"][2].lower() in _colours(w._search["map"].icon(), size, QIcon.On)


def test_the_icons_choice_shows_each_icon_alone_with_its_name_in_the_tooltip(bar):
    """Icons mode: no word on any button, its icon at the larger size, the name in the tooltip and the accessible
    name; off again, the words and their tips are back."""
    from maplehelper.ui import gametoolbar
    w, s = bar
    w.refresh()
    w._gear.click()
    w._panel._icons.click()
    assert s["game_toolbar_icons"] is True
    for b, key in w._buttons():
        name = w.t(key)
        assert b.text() == "" and not b.icon().isNull(), key
        assert b.iconSize() == QSize(gametoolbar.ICON_PX, gametoolbar.ICON_PX)
        assert b.toolTip() == name and b.accessibleName() == name
    icons_wide = w.width()
    w._panel._icons.click()
    assert s["game_toolbar_icons"] is False
    assert w._npcs.text() == "NPCs Here" and w._npcs.toolTip() == w.t("tb_npcs_here_tip")
    assert w.width() > icons_wide              # the words take more room


def test_the_transparency_slider_takes_any_percent_and_writes_the_shared_setting(bar):
    """No steps: a click anywhere on the track sets the whole percent under it, written to npc_overlay_opacity and
    on the bar's and the panel's glass at once, its % beside it; every other window follows once the mouse lets go
    (look_changed), not at each percent of a drag."""
    w, s = bar
    seen = []
    w.look_changed.connect(lambda: seen.append(s["npc_overlay_opacity"]))
    w.refresh()
    w._gear.click()
    p = w._panel
    sl = p._slider
    assert sl.value() == 0.85
    at = QPoint(round(sl._x(0.57)), sl.height() // 2)
    QTest.mousePress(sl, Qt.LeftButton, pos=at)
    assert s["npc_overlay_opacity"] == 0.57 and seen == []
    assert w._opacity == 0.57 and p._opacity == 0.57 and p._opacity_value.text() == "57%"
    QTest.mouseRelease(sl, Qt.LeftButton, pos=at)
    assert seen == [0.57]
    QTest.mouseClick(sl, Qt.LeftButton, pos=QPoint(sl.width() - 1, sl.height() // 2))
    assert s["npc_overlay_opacity"] == 1.0 and p._opacity_value.text() == "100%" and seen == [0.57, 1.0]


def test_the_white_glass_turns_the_bar_its_card_and_the_panel_dark_on_light_and_back(bar):
    """White picked: the bar's, the Tools card's, the panel's and its key box's styles in the light palette's dark
    text, none of the dark glass's light text or white fills left, the icons drawn dark, the white tile's check
    dark on it; dark picked again, all of it back."""
    from maplehelper.ui import gametoolbar, npcoverlay
    w, s = bar
    w.refresh()
    w._gear.click()
    p = w._panel
    size = QSize(gametoolbar.WORD_ICON_PX, gametoolbar.WORD_ICON_PX)
    sheets = lambda: (w.styleSheet(), w._menu.styleSheet(), p.styleSheet(), p._hotkey.styleSheet())  # noqa: E731
    light, dark = npcoverlay.LIGHT, npcoverlay.DARK
    p._pick_tint("white")
    assert npcoverlay.current_tint() == npcoverlay.TINTS["white"][1] and npcoverlay.palette() is light
    for sheet in sheets():
        assert light.text in sheet and dark.text not in sheet and "255,255,255" not in sheet
    for icon in (w._search["map"].icon(), w._tools["gear_advisor"].icon()):
        assert light.text.lower() in _colours(icon, size, QIcon.Off)
    white = next(b for b in p._tints.findChildren(QPushButton) if b.property("key") == "white")
    assert _colours(white._check, QSize(16, 16), QIcon.Off) == {light.text.lower()}
    p._pick_tint("dark")
    for sheet in sheets():
        assert dark.text in sheet and light.text not in sheet
    assert dark.text.lower() in _colours(w._search["map"].icon(), size, QIcon.Off)


def test_each_look_choice_is_written_and_followed_live(bar):
    """A tint tile, an accent dot, the icons switch: each click writes its setting, restyles the bar, asks every
    window to follow (look_changed), and moves the panel's ring and the name beside its label."""
    from maplehelper.ui import npcoverlay
    w, s = bar
    seen = []
    w.look_changed.connect(lambda: seen.append(True))
    w.refresh()
    w._gear.click()
    p = w._panel
    swatch = lambda row, key: next(b for b in row.findChildren(QPushButton) if b.property("key") == key)  # noqa: E731
    swatch(p._tints, "wine").click()
    assert s["overlay_tint"] == "wine" and npcoverlay.current_tint() == npcoverlay.TINTS["wine"][1]
    assert p._tint_name.text() == "Wine" and swatch(p._tints, "wine").isChecked()
    assert not swatch(p._tints, "dark").isChecked()
    swatch(p._accents, "orange").click()
    assert s["overlay_accent"] == "orange" and npcoverlay.ACCENTS["orange"][1] in w.styleSheet()
    assert p._accent_name.text() == "Orange" and swatch(p._accents, "orange").isChecked()
    p._icons.click()
    assert s["game_toolbar_icons"] is True and w._npcs.text() == ""
    assert seen == [True, True, True]


def test_reset_puts_the_default_look_back_and_keeps_the_key(bar):
    from maplehelper.store import DEFAULT_SETTINGS
    from maplehelper.ui import gametoolbar, npcoverlay
    w, s = bar
    s["overlay_tint"], s["overlay_accent"], s["npc_overlay_opacity"], s["game_toolbar_icons"] = "slate", "pink", 0.3, True
    s["game_toolbar_hotkey"] = "Ctrl+Alt+T"
    w.refresh()
    w._gear.click()
    p = w._panel
    assert p._reset.isEnabled()
    p._reset.click()
    assert {k: s[k] for k in gametoolbar.LOOK_KEYS} == {k: DEFAULT_SETTINGS[k] for k in gametoolbar.LOOK_KEYS}
    assert s["game_toolbar_hotkey"] == "Ctrl+Alt+T"                      # the key is no look
    assert npcoverlay.current_tint() == npcoverlay.TINTS["dark"][1] and w._npcs.text() == "NPCs Here"
    assert w._opacity == 0.85
    assert not p._reset.isEnabled()                                        # nothing left to put back


def test_the_panels_key_box_sets_the_bars_key(bar):
    """Click the box, press a key with its modifiers: written at once, and hotkey_changed has the app bind it. A
    plain letter is refused (it would take that letter from every program) and the box goes on listening; its ✕
    takes the key away."""
    from maplehelper import keys
    w, s = bar
    seen = []
    w.hotkey_changed.connect(lambda: seen.append(s["game_toolbar_hotkey"]))
    w.refresh()
    w._gear.click()
    box = w._panel._hotkey
    assert box.box.text() == keys.label(s["game_toolbar_hotkey"]) and keys.usable(s["game_toolbar_hotkey"])
    QTest.mouseClick(box.box, Qt.LeftButton)
    assert box.listening() and box.box.text() == "Press keys…"
    QTest.keyClick(box.box, Qt.Key_T)
    assert box.listening() and box.box.text() == "Add Ctrl or Alt" and seen == []
    QTest.keyClick(box.box, Qt.Key_T, Qt.ControlModifier | Qt.AltModifier)
    assert not box.listening() and s["game_toolbar_hotkey"] == "Ctrl+Alt+T" and seen == ["Ctrl+Alt+T"]
    assert box.box.text() == keys.label("Ctrl+Alt+T")
    box.clear.click()
    assert s["game_toolbar_hotkey"] == "" and seen == ["Ctrl+Alt+T", ""] and box.box.text() == "None"


def test_a_listening_key_box_lets_the_app_take_its_key_back(bar):
    """While the box listens the app lets go of the bar's key (CAPTURE), or that key would never reach the box;
    Esc keeps the key and the panel open, and the panel closing mid-listen hands the key back too."""
    from maplehelper.ui.hotkeybox import CAPTURE
    w, s = bar
    heard = []

    def on(v):
        heard.append(v)
    CAPTURE.listening.connect(on)
    try:
        w.refresh()
        w._gear.click()
        before = s["game_toolbar_hotkey"]
        box = w._panel._hotkey
        QTest.mouseClick(box.box, Qt.LeftButton)
        QTest.keyClick(box.box, Qt.Key_Escape)
        assert heard == [True, False] and not box.listening() and s["game_toolbar_hotkey"] == before
        assert w._panel.isVisible()
        QTest.mouseClick(box.box, Qt.LeftButton)
        w._panel.hide()
        assert heard == [True, False, True, False] and not box.listening()
    finally:
        CAPTURE.listening.disconnect(on)


def test_the_panel_is_one_width_and_mirrors_in_hebrew(qapp, isolated_store):
    from maplehelper.ui import gametoolbar
    w = gametoolbar.GameToolbar(isolated_store.Settings(), I18n("he"))
    try:
        w.refresh()
        w._gear.click()
        p = w._panel
        assert p.width() == gametoolbar.PANEL_W and p.layoutDirection() == Qt.RightToLeft
        assert p._slider._x(0.3) > p._slider._x(1.0)                  # the most see-through end on the right
        tiles = p._tints.findChildren(QPushButton)
        assert tiles[0].x() > tiles[-1].x()                            # the tiles run from the right
        assert p._tint_name.text() == bidi.plain("כהה", True)
    finally:
        w.close()
        w._panel.close()


@pytest.mark.parametrize("lang", ["en", "he"])
def test_the_panel_is_no_taller_than_its_screen_and_its_sections_scroll(qapp, isolated_store, lang):
    """The sections need more height than the offscreen screen has: the panel stops inside the screen's room
    and the sections scroll under the title row, the last row (Reset) out of sight until scrolled to. Their scrollbar
    sits in the side margin (the left one in Hebrew), so they keep the place and width they have without it."""
    from maplehelper.ui import gametoolbar
    w = gametoolbar.GameToolbar(isolated_store.Settings(), I18n(lang))
    try:
        w.refresh()
        w._gear.click()
        p = w._panel
        assert p.height() <= QGuiApplication.primaryScreen().availableGeometry().height()
        view, sb = p._scroll.viewport(), p._scroll.verticalScrollBar()
        assert p._scroll.widget().height() > view.height() and sb.isVisibleTo(p) and sb.maximum() > 0
        side, x = gametoolbar.PANEL_SIDE, sb.mapTo(p, QPoint(0, 0)).x()
        assert x + sb.width() <= side if lang == "he" else x >= gametoolbar.PANEL_W - side
        assert p._tints.mapTo(p, QPoint(0, 0)).x() == side and p._tints.width() == gametoolbar.PANEL_W - 2 * side
        reset_bottom = lambda: p._reset.mapTo(view, QPoint(0, p._reset.height())).y()  # noqa: E731
        assert reset_bottom() > view.height()
        sb.setValue(sb.maximum())
        assert 0 < reset_bottom() <= view.height()
    finally:
        w.close()
        w._panel.close()


def test_with_room_for_every_section_the_panel_has_no_scrollbar(bar, monkeypatch):
    """A screen with the room (_room says so): the panel as tall as its sections need, with no scrollbar, nothing out
    of sight, and the sections in the same place and width as when they scroll."""
    from maplehelper.ui import gametoolbar
    monkeypatch.setattr(gametoolbar._SettingsPanel, "_room", lambda self, at=None: 5000)
    w, _ = bar
    w.refresh()
    w._gear.click()
    p = w._panel
    sb, side = p._scroll.verticalScrollBar(), gametoolbar.PANEL_SIDE
    assert p.height() > QGuiApplication.primaryScreen().availableGeometry().height()     # the room, not the screen
    assert not sb.isVisibleTo(p) and sb.maximum() == 0
    assert p._scroll.widget().height() == p._scroll.viewport().height()
    assert p._tints.mapTo(p, QPoint(0, 0)).x() == side and p._tints.width() == gametoolbar.PANEL_W - 2 * side


def test_a_panel_choice_signals_the_app_to_restyle_every_window(bar):
    w, _ = bar
    seen = []
    w.look_changed.connect(lambda: seen.append(True))
    w.refresh()
    w._gear.click()
    w._panel._pick_accent("teal")
    assert seen == [True]


def test_the_minimap_switches_are_in_the_gear_panel_and_signal_the_app(bar):
    """The ⚙ panel's Minimap section (Settings had these): the hidden portals' dots and the route's arrow on at first,
    the overlays in screenshots off. Each click writes its setting and says so with the bar's minimap_toggled (the app
    redraws the dots, the windows' captures and the pickers' pages); a setting changed elsewhere is back on its switch
    at the next refresh."""
    w, s = bar
    seen = []
    w.minimap_toggled.connect(lambda: seen.append((s["minimap_hidden_portals"], s["minimap_route_arrow"],
                                                   s["overlays_in_screenshots"])))
    w.refresh()
    w._gear.click()
    p = w._panel
    switches = (p._hidden_portals, p._route_arrow, p._overlay_shots)
    names = ["Hidden portals on the minimap", "Route arrow on the minimap", "Show the overlays in screenshots"]
    assert p._minimap_head.text() == "MINIMAP"
    assert [p._hidden_portals_label.text(), p._route_arrow_label.text(), p._overlay_shots_label.text()] == names
    assert [b.accessibleName() for b in switches] == names
    assert [b.isChecked() for b in switches] == [True, True, False]
    p._hidden_portals.click()
    assert s["minimap_hidden_portals"] is False and seen == [(False, True, False)]
    p._route_arrow.click()
    assert s["minimap_route_arrow"] is False and seen == [(False, True, False), (False, False, False)]
    p._overlay_shots.click()
    assert s["overlays_in_screenshots"] is True and seen == [(False, True, False), (False, False, False),
                                                             (False, False, True)]
    s["minimap_hidden_portals"], s["minimap_route_arrow"], s["overlays_in_screenshots"] = True, True, False
    w.refresh()                         # changed elsewhere: each switch follows
    assert [b.isChecked() for b in switches] == [True, True, False]


def test_the_default_look_is_todays(bar):
    """Nothing picked: today's dark glass, today's green lit buttons, today's words on the buttons."""
    from maplehelper.ui import npcoverlay
    w, _ = bar
    w.refresh()
    assert npcoverlay.current_tint() == npcoverlay.TINTS["dark"][1]
    assert npcoverlay.ACCENTS["green"][1] in w.styleSheet()
    assert w._npcs.text() == "NPCs Here"


# ------------------------------------------------------------ its place on the screen

def _spare_x(s):
    """An x the bar fits at on the offscreen screen (the whole bar at its natural one-row width is ~900 px,
    wider than the 800 px screen): the width it opens at is narrowed through its own setting now, so the
    place the test asks for is never the clamped one."""
    screen = QGuiApplication.primaryScreen().geometry()
    s["game_toolbar_width"] = 500
    room = screen.width() - 500
    assert room > 1
    return screen.left() + room // 2


def test_it_opens_just_above_the_minimap_box(bar):
    """Above LOCATION.box (the minimap window found at the game's top left)."""
    from maplehelper.ui import gametoolbar
    from maplehelper.ui.location import LOCATION
    w, s = bar
    x = _spare_x(s)
    LOCATION.set_box({"x": x, "y": 300, "w": 200, "h": 200})          # 1:1 on the offscreen screen
    w.refresh()
    assert w.pos() == QPoint(x, 300 - w.height() - gametoolbar.GAP)   # its left edge lined up with the box's


def test_a_box_found_later_moves_it_above_the_box_until_the_player_moves_it(bar):
    """Opened before the minimap window was found (the screen's top centre), it moves above the box once it comes
    and with the box when it moves; a bar the player dragged stays put, and so does one when the box goes."""
    from maplehelper.ui import gametoolbar
    from maplehelper.ui.location import LOCATION
    w, s = bar
    x = _spare_x(s)
    w.refresh()
    top = w.pos()
    LOCATION.set_box({"x": x, "y": 300, "w": 200, "h": 200})
    assert w.pos() == QPoint(x, 300 - w.height() - gametoolbar.GAP) != top
    LOCATION.set_box({"x": x + 20, "y": 280, "w": 180, "h": 220})     # the next map's minimap, another size
    assert w.pos() == QPoint(x + 20, 280 - w.height() - gametoolbar.GAP)
    LOCATION.set_box(None)                                          # the minimap closed: it stays
    assert w.pos() == QPoint(x + 20, 280 - w.height() - gametoolbar.GAP)
    w.move(x, 70)                                                   # the player's place
    LOCATION.set_box({"x": x, "y": 300, "w": 200, "h": 200})
    assert w.pos() == QPoint(x, 70)


def test_the_place_is_kept_when_moved_and_reopened_there(bar):
    w, s = bar
    x = _spare_x(s)
    w.refresh()
    w.move(x, 70)
    w._remember()                            # the debounced save, as the 400 ms timer would fire it
    assert s["game_toolbar_pos"] == {"x": x, "y": 70}
    w.hide()
    w.refresh()
    assert w.pos() == QPoint(x, 70)


def test_it_opens_at_a_saved_spot(bar):
    w, s = bar
    x = _spare_x(s)
    s["game_toolbar_pos"] = {"x": x, "y": 60}
    w.refresh()
    assert w.pos() == QPoint(x, 60)
