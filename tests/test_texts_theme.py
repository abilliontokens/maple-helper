"""Text contrast in every look (WCAG AA), the looks Settings picks (set_look), the menu rows' own states, Windows high
contrast, short English names kept whole in Hebrew, Mac wording (⌘V, System Settings, fn+F9) and the wording fixes of
the audit."""
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPointF  # noqa: E402
from PySide6.QtGui import QEnterEvent, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel  # noqa: E402

from maplehelper.i18n import NBSP, STRINGS, I18n  # noqa: E402
from maplehelper.ui import theme  # noqa: E402

REAL_HIGH_CONTRAST = theme.high_contrast


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _rgb(color: str, over=(255, 255, 255)):
    """'#RRGGBB' or 'rgba(r,g,b,a)' as an opaque color over a background."""
    if color.startswith("#"):
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b, a = (float(x) for x in re.findall(r"[\d.]+", color))
    return tuple(round(c * a + o * (1 - a)) for c, o in zip((r, g, b), over))


def _contrast(fg, bg) -> float:
    def lum(c):
        ch = [v / 255 for v in c]
        ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _menu(app):
    from maplehelper.ui.widgets import SplitMenu
    theme.set_look("white", "orange", 1.0)
    app.setStyleSheet(theme.stylesheet("Rubik", 14))
    menu = SplitMenu()
    menu.add_row("edit", "Edit character", lambda: None)
    menu.add_row("copy", "Copy the character card", lambda: None, enabled=False)
    rows = [w for w in menu.findChildren(QFrame) if w.objectName() == "MenuRow"]
    for r in rows:
        r.ensurePolished()
        r.findChild(QLabel, "MenuRowText").ensurePolished()
    return menu, rows


def _fg(label) -> str:
    group = QPalette.Active if label.isEnabled() else QPalette.Disabled
    return label.palette().color(group, label.foregroundRole()).name()


def test_menu_rows_show_enabled_disabled_and_hover(app):
    menu, (on, off) = _menu(app)
    on_label, off_label = on.findChild(QLabel, "MenuRowText"), off.findChild(QLabel, "MenuRowText")
    # one rule used to paint every label grey: an enabled and a disabled row looked the same
    assert _fg(on_label) == theme.P()["text"].lower()
    assert _fg(off_label) != _fg(on_label)
    theme.install_focus_ring()
    QApplication.sendEvent(on, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    assert on_label.property("hover") is True and _fg(on_label) == theme.ON_ACCENT.lower()
    QApplication.sendEvent(on, QEvent(QEvent.Leave))
    assert not on_label.property("hover") and _fg(on_label) == theme.P()["text"].lower()
    QApplication.sendEvent(off, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    assert not off_label.property("hover")                  # a disabled row doesn't light up
    menu.deleteLater()
    app.setStyleSheet("")


def test_windows_high_contrast_wins_over_the_look(monkeypatch):
    monkeypatch.setattr(theme, "high_contrast", lambda: "dark")
    theme.set_look("white", "orange", 0.5)
    assert theme.MODE == "dark" and theme.HIGH_CONTRAST
    assert theme.TINT == theme.TINTS["dark"][1] and theme.OPACITY == 1.0     # glass of its own, nothing seen through
    assert theme.P()["muted"] == theme.P()["text"]          # no see-through grey text
    assert "rgba(255,255,255,0.07)" not in theme.stylesheet("Rubik", 14)   # firmer hairlines
    theme.set_look("midnight", "orange", 0.5)
    assert theme.TINT == theme.TINTS["midnight"][1]         # a dark tint suits its light text: kept
    monkeypatch.setattr(theme, "high_contrast", lambda: None)
    theme.set_look("white", "orange", 0.5)
    assert theme.MODE == "light" and not theme.HIGH_CONTRAST and theme.OPACITY == 0.5
    assert {k: theme.P()[k] for k in theme.PALETTES["light"]} == theme.PALETTES["light"]


def test_a_look_is_the_tint_the_accent_and_the_opacity():
    theme.set_look("midnight", "blue", 0.6)
    c = theme.P()
    assert theme.MODE == "dark" and c["text"] == theme.PALETTES["dark"]["text"]      # light text on the dark glass
    assert c["glass"] == theme.TINT == theme.TINTS["midnight"][1] and theme.dialog_background() == "#11182B"
    assert c["solid_alpha"] == c["glass_alpha"] == theme.OPACITY == 0.6               # paint_glass: see-through
    assert (theme.ACCENT, theme.ON_ACCENT) == theme.ACCENTS["blue"][1:]
    assert theme.qcolor(theme.ACCENT_DEEP).valueF() < theme.qcolor(theme.ACCENT).valueF()
    assert theme.accent_rgba(0.5) == "rgba(61,139,214,0.5)"
    css = theme.stylesheet("Rubik", 14).upper()
    assert theme.ACCENTS["blue"][1] in css
    assert not any(orange in css for orange in ("#FF9533", "#F07A12", "#FFA24A", "#F58A2A"))   # the old brand orange


def test_the_white_glass_takes_dark_text_and_darker_accent_text():
    theme.set_look("white", "teal", 1.0)
    assert theme.MODE == "light" and theme.P()["text"] == theme.PALETTES["light"]["text"]
    assert theme.P()["glass"] == theme.TINTS["white"][1]
    assert theme.qcolor(theme.accent_text()).valueF() < theme.qcolor(theme.ACCENT).valueF()


def test_a_name_the_catalog_doesnt_know_and_an_opacity_out_of_range():
    theme.set_look("neon", "gold", 0.05)
    assert theme.TINT == theme.TINTS["white"][1] and theme.ACCENT == theme.ACCENTS["orange"][1]
    assert theme.OPACITY == theme.OPACITY_MIN
    theme.set_look("dark", "green", 7)
    assert theme.OPACITY == theme.OPACITY_MAX


@pytest.mark.parametrize("tint", list(theme.TINTS))
def test_the_accent_as_text_reads_on_every_glass(tint):
    """Links and the accent's chips' text, in every accent, plain and deep: >= 4.5:1 on a card of that glass (darkened
    on the white one, the accent itself or lighter on the dark ones: purple on slate was too dark)."""
    for accent in theme.ACCENTS:
        theme.set_look(tint, accent, 1.0)
        card = _rgb(theme.P()["fill1"], over=theme.TINT)
        for deep in (False, True):
            assert _contrast(_rgb(theme.accent_text(deep)), card) >= 4.5, (tint, accent, deep)


def test_the_real_high_contrast_check_answers_without_failing():
    assert REAL_HIGH_CONTRAST() in (None, "dark", "light")


def test_short_english_names_stay_whole_in_hebrew():
    he, en = I18n("he"), I18n("en")
    plan = he("ob_need_plan")
    assert f"Claude{NBSP}Code" in plan          # (the plan line names Claude Code since UX-10)
    assert f"Free{NBSP}Market" in he("sell_why_no_price")
    assert "Claude Code" in en("ob_need_plan")                    # English lines wrap normally
    # a name through a placeholder; a long KB name stays as spelled (bidi keeps it whole by that spelling)
    assert f"Red{NBSP}Snail" in he("other_char_switch", name="Red Snail")
    assert "Tree Dungeon, Monkey Forest I" in he("other_char_switch", name="Tree Dungeon, Monkey Forest I")
    from maplehelper.i18n import keep_names_whole
    assert keep_names_whole("שלום Copy to Clipboard עכשיו") == f"שלום Copy{NBSP}to{NBSP}Clipboard עכשיו"
    long_run = "ראו One Two Three Four כאן"
    assert keep_names_whole(long_run) == long_run              # a longer English run may still wrap
    assert keep_names_whole("בין 10 20 לבין") == "בין 10 20 לבין"   # numbers alone are not a name


@pytest.fixture
def mac(monkeypatch):
    monkeypatch.setattr(I18n, "mac", True)


def test_mac_gets_mac_paths_and_shortcuts(mac):
    for lang in ("he", "en"):
        t = I18n(lang)
        assert "⌘V" in t("copied") and "Ctrl" not in t("copied")
        assert "Windows" not in t("voice_mic_failed")
        # no keys to press: the chat opens from the menu bar icon (the tray on Windows)
        for key in ("close_chat", "ob_done_hint", "tour_close_body", "tour_done_body", "tour_min_body"):
            assert "F9" not in t(key) and "fn+" not in t(key) and "Windows" not in t(key), key
        assert t("update_available", version="1") != t("update_available_mac")   # its own Mac line, not swapped


def test_windows_wording_is_unchanged(monkeypatch):
    monkeypatch.setattr(I18n, "mac", False)
    en = I18n("en")
    assert "Ctrl+V" in en("copied") and "Windows Settings" in en("voice_mic_failed") and "fn" not in en("close_chat")


def test_hebrew_addresses_the_player_in_plural():
    assert "שלכם" in I18n("he")("q_no_match") and "שלך." not in I18n("he")("q_no_match")


@pytest.mark.parametrize("key", ["appearance_dark", "appearance_light", "q_needs", "q_gets"])
def test_unused_audit_strings_are_gone(key):
    assert key not in STRINGS


def test_no_default_key_letters_the_kb_does_not_give():
    # the KB says key layouts can be rebound (pages/guide/controls-and-settings.md) and names no Stat/Inventory key
    from maplehelper import glossary
    texts = [v[lang] for k in ("inv_not_found", "my_stats_hint", "sell_body") for v in [STRINGS[k]] for lang in v]
    texts += list(glossary.APP["ACC"])
    assert not any(re.search(r"\(\**[SI]\** key\)|מקש \**[SI]\b", s) for s in texts)


def test_every_text_key_the_code_asks_for_exists():
    """A string lost while editing i18n.py showed its key on screen ("calc_default", the owner's report)."""
    import re
    from pathlib import Path

    from maplehelper.i18n import STRINGS
    root = Path(__file__).resolve().parent.parent / "maplehelper"
    asked = set()
    for f in root.rglob("*.py"):
        asked |= set(re.findall(r'(?<![\w.])(?:self\.)?t\(\s*"([a-z][a-z0-9_]*)"', f.read_text(encoding="utf-8")))
    missing = sorted(k for k in asked if k not in STRINGS)
    assert missing == []


def test_right_click_menu_speaks_the_ui_language(app):
    """COPY-08: a text field's own menu (Undo, Copy, Paste) was English, "&" marks and all, in the Hebrew app."""
    from PySide6.QtWidgets import QLineEdit

    from maplehelper.app import qt_texts

    def words():
        edit = QLineEdit()             # the menu is the field's child: keep the field alive while reading it
        return " ".join(a.text() for a in edit.createStandardContextMenu().actions())
    try:
        qt_texts(app, "he")
        assert re.search("[\u0590-\u05ff]", words()) and "Paste" not in words()
        qt_texts(app, "en")
        assert "Paste" in words()
    finally:
        qt_texts(app, "en")
