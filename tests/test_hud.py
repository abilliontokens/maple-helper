"""The bottom bar read on this computer (hud.py)."""
from pathlib import Path

import pytest
from PIL import Image

from maplehelper import hud

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = {9: 1242, 10: 1716, 11: 2360, 30: 98000}


def _scene() -> Image.Image:
    """A 2562x1440 play area: plain backdrop, the live bar at the bottom."""
    bar = Image.open(FIXTURES / "hud_bar_live.png").convert("RGB")
    img = Image.new("RGB", (2562, 1440), (110, 140, 190))
    img.paste(bar, (0, 1440 - bar.height))
    return img


def test_level_comes_from_the_exp_not_the_stylized_digits():
    # 194 points at 11.31%: the level needs ~1715 EXP, the table's level 10 (the digits read "00")
    rows = [("Rogue", 700, 50), ("Kalimero", 700, 75), ("LV.", 560, 60), ("00", 640, 60),
            ("HP[444/444]", 1000, 50), ("MP[363/363]", 1250, 50), ("EXP. 194[11.31%]", 1500, 50)]
    got = hud.parse(rows, TABLE)
    assert (got.level, got.job, got.name, got.exp, got.exp_pct) == (10, "Rogue", "Kalimero", 194, 11.31)
    assert got.hp == (444, 444) and got.mp == (363, 363)


def test_a_pet_name_is_no_job_and_a_tiny_percentage_no_level():
    rows = [("Brown Kitty", 700, 20), ("Kalimero", 700, 75), ("EXP. 3[0.17%]", 1500, 50), ("HP[1/2]", 1000, 50)]
    got = hud.parse(rows, TABLE)
    assert got.job is None and got.name is None          # no job line: the name under it isn't sure either
    assert got.level is None and got.exp_pct == 0.17     # 0.17% is too coarse to tell the level


def test_not_the_bar_is_no_read():
    assert hud.parse([("CASH SHOP", 10, 10), ("hello", 20, 20)], TABLE) is None


def test_the_live_bar_reads():
    pytest.importorskip("rapidocr")
    got = hud.read(_scene(), TABLE)
    assert got is not None
    assert (got.level, got.job, got.name) == (10, "Rogue", "Kalimero")
    assert got.exp == 219 and got.exp_pct == 12.76 and got.hp == (431, 444)


def test_exp_points_with_a_thousands_separator_read_whole():
    """Past 999 points the bar writes 10,371, which OCR reads as "10.371": the points stopped at "10" and the
    whole EXP read failed, so no level either (live strip, Lv. 22 Magician, 2026-10-12)."""
    rows = [("LV.", 613, 59), ("22", 680, 59), ("Magician", 782, 44), ("HP[486/536]", 1071, 43),
            ("EXP 10.371[35.79%]", 1553, 42), ("formatme", 786, 71)]
    got = hud.parse(rows, {22: 28980})
    assert (got.level, got.exp, got.exp_pct) == (22, 10371, 35.79)
    assert hud.parse([("EXP 1,204[4.20%]", 1553, 42)], {}).exp == 1204
    pytest.importorskip("rapidocr")
    live = hud.read_strip(Image.open(FIXTURES / "hud_strip_lv22_live.png"), {22: 28980})
    assert (live.level, live.exp, live.exp_pct, live.hp) == (22, 10371, 35.79, (486, 536))
