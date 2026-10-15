"""The way from where the player is standing (journey.of): it shortens as they walk, says when they strayed off it
and had to be worked out again, and asks the graph for nothing once they have arrived. LOCATION.set_journey
(ui/location.py) passes it on only when it changes."""
import os

import pytest

from maplehelper import journey
from maplehelper.routes import Leg, Route

# a tiny map of the world: the way out of a town, with a wrong door off the second map
LINE = ["a", "b", "c", "d"]


class StandInGraph:
    """Answers route() along LINE, and from the wrong map "x" back onto it; counts every call."""

    def __init__(self, line=LINE):
        self.line = list(line)
        self.calls = []

    def route(self, start, end, taxi=True, teleport=True, hidden=False):
        self.calls.append((start, end, taxi, teleport, hidden))
        if start in self.line:
            maps = self.line
        elif start == "x":                       # the wrong door off "b": one portal back onto the line
            maps = ["x"] + self.line[self.line.index("b"):]
        else:
            return None                          # a map the graph never heard of
        if end not in maps:
            return None
        i, j = maps.index(start), maps.index(end)
        if j < i:                                # the portals only go one way
            return None
        return Route(start, end, [Leg(frm=maps[k], to=maps[k + 1], kind="portal", via=f"p{k}")
                                  for k in range(i, j)])


def test_the_way_from_here_counts_the_maps_left():
    g = StandInGraph()
    j = journey.of(g, "a", "d", rides=True, hidden=False)
    assert j.dest == "d"
    assert [leg.to for leg in j.legs] == ["b", "c", "d"]
    assert (j.left, j.off, j.arrived) == (3, False, False)
    assert g.calls == [("a", "d", True, True, False)]


def test_the_settings_reach_the_graph():
    g = StandInGraph()
    journey.of(g, "a", "d", rides=False, hidden=True)
    assert g.calls == [("a", "d", False, False, True)]


def test_stepping_onto_the_next_map_keeps_to_the_way():
    g = StandInGraph()
    first = journey.of(g, "a", "d", rides=True, hidden=False)
    second = journey.of(g, "b", "d", rides=True, hidden=False, last=first)
    assert second.off is False
    assert second.left == 2
    assert [leg.to for leg in second.legs] == ["c", "d"]


def test_standing_still_is_not_off_the_way():
    g = StandInGraph()
    first = journey.of(g, "a", "d", rides=True, hidden=False)
    again = journey.of(g, "a", "d", rides=True, hidden=False, last=first)
    assert again.off is False
    assert again.left == 3


def test_a_wrong_portal_works_the_way_out_again_from_there():
    g = StandInGraph()
    first = journey.of(g, "a", "d", rides=True, hidden=False)
    strayed = journey.of(g, "x", "d", rides=True, hidden=False, last=first)
    assert strayed.off is True
    assert strayed.legs[0].frm == "x"
    assert [leg.to for leg in strayed.legs] == ["b", "c", "d"]
    assert strayed.left == 3


def test_a_first_way_is_never_off():
    g = StandInGraph()
    assert journey.of(g, "x", "d", rides=True, hidden=False).off is False


def test_a_way_to_another_destination_is_never_off():
    g = StandInGraph()
    first = journey.of(g, "a", "c", rides=True, hidden=False)
    other = journey.of(g, "x", "d", rides=True, hidden=False, last=first)
    assert other.off is False


def test_arriving_asks_the_graph_for_nothing():
    g = StandInGraph()
    first = journey.of(g, "c", "d", rides=True, hidden=False)
    arrived = journey.of(g, "d", "d", rides=True, hidden=False, last=first)
    assert (arrived.arrived, arrived.left, arrived.legs, arrived.off) == (True, 0, (), False)
    assert g.calls == [("c", "d", True, True, False)]


def test_no_way_at_all_is_nothing():
    g = StandInGraph()
    assert journey.of(g, "d", "a", rides=True, hidden=False) is None


def test_a_map_the_graph_never_heard_of_is_nothing():
    g = StandInGraph()
    assert journey.of(g, "a", "zz", rides=True, hidden=False) is None
    assert journey.of(g, "zz", "d", rides=True, hidden=False) is None


# ----------------------------------------------------------------- LOCATION

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def clean_location():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from maplehelper.ui.location import LOCATION
    old = LOCATION.journey
    LOCATION.journey = None
    yield LOCATION
    LOCATION.journey = old


def test_set_journey_emits_once_per_change(clean_location):
    g = StandInGraph()
    first = journey.of(g, "a", "d", rides=True, hidden=False)
    second = journey.of(g, "b", "d", rides=True, hidden=False, last=first)
    seen = []
    clean_location.journeyed.connect(seen.append)
    try:
        clean_location.set_journey(first)
        clean_location.set_journey(first)
        clean_location.set_journey(second)
        clean_location.set_journey(None)
        clean_location.set_journey(None)
    finally:
        clean_location.journeyed.disconnect(seen.append)
    assert seen == [first, second, None]
    assert clean_location.journey is None
