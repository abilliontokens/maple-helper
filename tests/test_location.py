"""The guide and route destination LOCATION is pointing at (ui/location.py): every change is logged at INFO
(and only a change), so a player's log says whether anything was guiding them."""
import logging
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def clean_location(qapp):
    from maplehelper.ui.location import LOCATION
    old = LOCATION.guide, LOCATION.route_dest
    LOCATION.guide, LOCATION.route_dest = None, None
    yield LOCATION
    LOCATION.guide, LOCATION.route_dest = old


def _logged(caplog):
    return [record.getMessage() for record in caplog.records if record.name == "maplehelper"]


def test_guide_logs_only_on_change(clean_location, caplog):
    guide = ("010001082", (0.5, 0.5), "npc/1012")
    with caplog.at_level(logging.INFO, logger="maplehelper"):
        clean_location.set_guide(guide)
        clean_location.set_guide(guide)
        clean_location.set_guide(None)
    assert _logged(caplog) == ["guide: npc/1012 on 010001082", "guide: none"]


def test_guide_logs_an_odd_shape_without_raising(clean_location, caplog):
    with caplog.at_level(logging.INFO, logger="maplehelper"):
        clean_location.set_guide(("010001082",))
    assert _logged(caplog) == ["guide: ('010001082',)"]


def test_route_dest_logs_only_on_change(clean_location, caplog):
    with caplog.at_level(logging.INFO, logger="maplehelper"):
        clean_location.set_route_dest("010001000")
        clean_location.set_route_dest("010001000")
        clean_location.set_route_dest(None)
    assert _logged(caplog) == ["route: to 010001000", "route: none"]
