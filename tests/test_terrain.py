"""The terrain walk model (maplehelper/terrain.py): which hidden teleports a real walk across
a map takes, from hand-built ground only — no KB, no network, no site data.

Coordinates are map units with y growing downward, as in the module: a smaller y is a higher
platform. `lr` entries are [x, y_a, y_b], the two ends of a rope or ladder (see the module
docstring for the measurements that reading comes from).
"""
from dataclasses import dataclass

from maplehelper.terrain import Walk


@dataclass(frozen=True)
class Jump:
    """A hidden teleport as routes.Jump hands it to the engine: both ends in map units."""

    frm: tuple
    to: tuple
    name: str


def test_walking_along_one_platform_needs_no_pad():
    walk = Walk.of([[0, 100, 200, 100]], [])
    assert walk.pads((10, 100), (190, 100), []) == []


def test_walking_across_joined_fragments_needs_no_pad():
    # the site splits one platform into fragments that touch end to end: still one walk
    walk = Walk.of([[0, 100, 100, 100], [100, 100, 200, 100]], [])
    assert walk.pads((10, 100), (190, 100), []) == []


def test_a_higher_platform_with_no_rope_needs_the_pad_that_lands_there():
    pad = Jump((50, 200), (50, 100), "t001")
    walk = Walk.of([[0, 200, 200, 200], [0, 100, 200, 100]], [])
    # falling back down is free, but nothing connects the lower platform upward but the pad
    assert walk.pads((10, 200), (150, 100), [pad]) == [pad]
    assert walk.pads((150, 100), (10, 200), [pad]) == []


def test_a_chain_of_two_pads_is_returned_in_order():
    first = Jump((40, 300), (40, 200), "t001")
    second = Jump((160, 200), (160, 100), "t002")
    ground = [[0, 300, 200, 300], [0, 200, 200, 200], [0, 100, 200, 100]]
    walk = Walk.of(ground, [])
    # the order in the list handed over is not the order they are taken in
    assert walk.pads((10, 300), (180, 100), [second, first]) == [first, second]


def test_a_rope_climbs_without_a_pad_and_a_pad_that_saves_the_climb_is_named():
    pad = Jump((50, 200), (50, 100), "t001")
    ground = [[0, 200, 200, 200], [0, 100, 200, 100]]
    walk = Walk.of(ground, [[100, 200, 100]])   # a rope at x=100 between the two levels
    # the rope alone gets the player up (100 up is past a jump, so the rope is the way)
    assert walk.pads((10, 200), (150, 100), []) == []
    # but effort decides, not pad-count: teleporting costs about nothing next to
    # climbing the rope's 100, so the pad that skips the climb is the one named
    assert walk.pads((10, 200), (150, 100), [pad]) == [pad]


def test_a_target_reachable_by_falling_needs_no_pad():
    pad = Jump((20, 100), (200, 200), "t009")
    ground = [[0, 100, 120, 100], [80, 200, 240, 200]]
    walk = Walk.of(ground, [])
    assert walk.pads((10, 100), (220, 200), [pad]) == []


def test_a_ledge_a_jump_above_is_reached_without_a_pad():
    """One platform tier (60 units, the tier measured on Utah's Pig Farm) up, with the
    ledge over the ground below: inside one jump, so no pad is named. The old version
    of this premise used 80 up, which assumed the old 90-unit jump height; a tier is
    what a jump climbs now, not 80."""
    walk = Walk.of([[0, 200, 200, 200], [0, 140, 200, 140]], [])
    assert walk.pads((10, 200), (150, 140), []) == []


def test_a_ledge_offset_sideways_past_the_lower_span_is_not_a_jump():
    """The same tier up, but the ledge starts 40 units past the lower span's end: it is
    not over the ground the player jumps from, so no jump lands on it. The old rule
    allowed this (a 60-unit sideways gap at up to 90 up); sideways offset is not a jump
    any more, only ground that sits over the lower span is. Without a pad the ledge is
    unreachable, and the pad that lands there is the way."""
    pad = Jump((50, 200), (200, 140), "t001")
    gapped = Walk.of([[0, 200, 100, 200], [140, 140, 240, 140]], [])
    assert gapped.pads((10, 200), (200, 140), []) is None
    assert gapped.pads((10, 200), (200, 140), [pad]) == [pad]


def test_a_wall_rising_from_the_floor_splits_the_walk():
    """A vertical foothold is a wall (rule 2): the two floor fragments touch at its
    foot, but the wall rising through that join means they are not one walk, so the
    far fragment cannot be reached on foot at all."""
    ground = [[0, 200, 100, 200], [100, 200, 200, 200], [100, 200, 100, 100]]
    walk = Walk.of(ground, [])
    assert walk.pads((10, 200), (190, 200), []) is None


def test_a_fall_through_a_wall_is_not_a_fall():
    """A drop whose line passes through a wall (rule 2) is not a fall to the far side:
    the lower platform sits beyond the wall from every probe the upper one offers,
    so it cannot be reached by dropping."""
    ground = [[0, 100, 100, 100], [110, 200, 210, 200], [105, 140, 105, 200]]
    walk = Walk.of(ground, [])
    assert walk.pads((10, 100), (150, 200), []) is None
    # without the wall the same drop (10 sideways of the last probe) is a plain fall
    assert Walk.of(ground[:2], []).pads((10, 100), (150, 200), []) == []


def test_a_ledge_too_high_to_jump_needs_its_pad():
    # 140 up is past a jump, so without the pad nothing reaches the ledge at all
    pad = Jump((50, 300), (50, 160), "t001")
    walk = Walk.of([[0, 300, 200, 300], [0, 160, 200, 160]], [])
    assert walk.pads((10, 300), (150, 160), []) is None
    assert walk.pads((10, 300), (150, 160), [pad]) == [pad]


def test_a_long_climb_of_many_jumps_loses_to_a_pad_that_skips_it():
    """Four ledges one tier (60 units) apart: each is one jump, so the climb is there
    to be walked — at a jump's height plus its fixed effort apiece (some 320 each) it
    costs far more than the pad. The old version spaced the ledges 80 apart, which
    assumed the old 90-unit jump height; one tier is the spacing a jump climbs now."""
    pad = Jump((50, 500), (50, 260), "t001")
    ground = [[0, y, 200, y] for y in (500, 440, 380, 320, 260)]
    walk = Walk.of(ground, [])
    assert walk.pads((10, 500), (150, 260), []) == []
    assert walk.pads((10, 500), (150, 260), [pad]) == [pad]


def test_a_pad_that_saves_nothing_is_not_named():
    # this pad lands where a fall already lands for next to nothing: taking it saves
    # no effort over dropping, so the cheapest way is the fall and names no pad
    pad = Jump((50, 100), (50, 200), "t009")
    walk = Walk.of([[0, 100, 200, 100], [0, 200, 200, 200]], [])
    assert walk.pads((10, 100), (150, 200), [pad]) == []


def test_a_steep_segment_is_a_wall_not_a_walk_up():
    # slope 2 (100 up over 50 across): too steep to stand on, so it joins nothing upward
    ground = [[0, 200, 100, 200], [100, 200, 150, 100], [150, 100, 250, 100]]
    walk = Walk.of(ground, [])
    assert walk.pads((10, 200), (200, 100), []) is None


def test_unsnappable_ends_return_none():
    walk = Walk.of([[0, 100, 200, 100]], [])
    assert walk.pads((1000, 1000), (100, 100), []) is None    # the player off the ground
    assert walk.pads((100, 100), (1000, 1000), []) is None    # the target off the ground
    assert walk.pads(None, (100, 100), []) is None


def test_a_point_high_above_its_platform_still_snaps_to_it():
    # 115 units above the ground (the live Pig Farm player read was 113): beyond the old
    # 60-unit nearest-span rule, but the ground below is still the ground they stand on
    walk = Walk.of([[0, 200, 200, 200]], [])
    assert walk.pads((100, 85), (150, 200), []) == []


def test_a_point_just_below_its_platform_still_snaps_to_it():
    # nothing lies below this point, so the nearest-span fallback stands it on the platform
    # just above it rather than giving up
    walk = Walk.of([[0, 100, 200, 100]], [])
    assert walk.pads((100, 110), (150, 100), []) == []


def test_a_point_snaps_to_the_ground_below_not_the_nearer_ground_above():
    # ground 30 above and 110 below: the point stands on the one below, so reaching the
    # platform above takes the pad (from the lower platform, only the pad goes up)
    pad = Jump((50, 210), (50, 70), "t001")
    walk = Walk.of([[0, 70, 200, 70], [0, 210, 200, 210]], [])
    assert walk.pads((100, 100), (150, 70), [pad]) == [pad]


def test_a_point_with_no_ground_below_within_reach_snaps_to_nothing():
    # 200 units of air under the point is beyond the downward reach, and too far for the
    # nearest-span fallback either: the ground cannot say where the point is
    walk = Walk.of([[0, 200, 200, 200]], [])
    assert walk.pads((100, 0), (150, 200), []) is None
