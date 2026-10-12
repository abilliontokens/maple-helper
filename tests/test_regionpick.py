"""A capture-coordinates box back to logical pixels (pure, no widget needed)."""
import pytest
from PySide6.QtCore import QRect

from maplehelper.ui.regionpick import from_capture

PRIMARY = (QRect(0, 0, 2560, 1440), 1.5)
# Windows places each screen at its native origin: right of a 3840-px primary at 150% the next one starts at 3840
BESIDE = (QRect(3840, 0, 1920, 1080), 1.0)
BESIDE_SCALED = (QRect(3840, 0, 1536, 864), 1.25)


@pytest.mark.parametrize("box,screens,rect,ratio", [
    ({"x": 150, "y": 150, "w": 300, "h": 225}, [PRIMARY], QRect(100, 100, 200, 150), 1.5),
    ({"x": 3900, "y": 100, "w": 200, "h": 150}, [PRIMARY, BESIDE], QRect(3900, 100, 200, 150), 1.0),
    ({"x": 3915, "y": 125, "w": 250, "h": 185}, [PRIMARY, BESIDE_SCALED], QRect(3900, 100, 200, 148), 1.25),
    ({"x": 150, "y": 150, "w": 300, "h": 225}, [PRIMARY, BESIDE_SCALED], QRect(100, 100, 200, 150), 1.5),
])
def test_each_screen_scales_from_its_own_origin(box, screens, rect, ratio):
    """The windows over the game lie over the box a read found: capture coordinates back to that logical box, with
    the ratio of the screen holding its centre."""
    assert from_capture(box, screens) == (rect, ratio)


def test_a_straddling_box_follows_its_centre():
    # it starts on the primary but its middle is past x=3840: the second screen's ratio wins
    assert from_capture({"x": 3800, "y": 100, "w": 200, "h": 150}, [PRIMARY, BESIDE]) == (QRect(3800, 100, 200, 150), 1.0)


def test_no_scaling_passes_through():
    assert from_capture({"x": 2600, "y": 100, "w": 200, "h": 150}, [PRIMARY, BESIDE_SCALED], scale=False) == (
        QRect(2600, 100, 200, 150), 1.0)
