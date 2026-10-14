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
    # climbing the rope's 100 at CLIMB_WEIGHT a unit (some 500, rule 8), so the pad
    # that skips the climb is the one named
    assert walk.pads((10, 200), (150, 100), [pad]) == [pad]


def test_a_long_rope_climb_loses_to_a_pad_that_skips_it():
    """900 up on a rope at CLIMB_WEIGHT a unit is some 4500 of effort (rule 8 in the
    module: climbing is not walking sideways), so the pad that skips the whole climb
    is named; the rope alone still gets there, so without the pad no pad is named."""
    pad = Jump((50, 1000), (50, 100), "t001")
    ground = [[0, 1000, 200, 1000], [0, 100, 200, 100]]
    walk = Walk.of(ground, [[100, 100, 1000]])
    assert walk.pads((10, 1000), (150, 100), []) == []
    assert walk.pads((10, 1000), (150, 100), [pad]) == [pad]


def test_a_short_rope_climb_still_beats_a_faraway_pad():
    """100 up on the rope at the west end costs some 500 (100 at CLIMB_WEIGHT, rule 8).
    The pad sits at the far east end of both floors (each floor walked in 150-unit
    fragments, so reaching it costs the fragments walked): walking east to it, taking
    it and walking back west on top costs some 900, more than the short climb beside
    the start, so no pad is named."""
    pad = Jump((550, 300), (550, 200), "t001")
    ground = [[x, 300, x + 150, 300] for x in (0, 150, 300, 450)] + \
             [[x, 200, x + 150, 200] for x in (0, 150, 300, 450)]
    walk = Walk.of(ground, [[75, 200, 300]])
    assert walk.pads((10, 300), (20, 200), []) == []
    assert walk.pads((10, 300), (20, 200), [pad]) == []


def test_a_rope_stopping_one_jump_short_of_the_platform_above_still_climbs():
    # the rope's top end stops 70 short of the upper platform (and its bottom end 50
    # short of the lower one): one jump grabs the bottom end, and one jump off the
    # top end lands on the platform, so the rope still joins the two
    ground = [[0, 300, 200, 300], [0, 100, 200, 100]]
    walk = Walk.of(ground, [[100, 170, 250]])
    assert walk.pads((10, 300), (150, 100), []) == []


def test_a_rope_stopping_more_than_one_jump_short_of_the_platform_above_does_not_climb():
    """The same rope stopping 76 short of the upper platform — the measure of Utah's
    Pig Farm's rope at x=1453, which stops 76 short of the span at y=-265 (its rope
    at x=-1185 stops 84 short of y=-385): past one jump (rule 5), so the player
    cannot get off the rope onto that platform, and without the rope nothing else
    climbs there either. Falling back down the other way is still free."""
    ground = [[0, 300, 200, 300], [0, 100, 200, 100]]
    walk = Walk.of(ground, [[100, 176, 250]])
    assert walk.pads((10, 300), (150, 100), []) is None
    assert walk.pads((150, 100), (10, 300), []) == []


def test_a_platform_beside_a_rope_between_its_ends_is_a_mid_rope_exit():
    """A platform the rope runs past, not one it ends at: the span at y=175 starts
    38 units east of the rope at x=100 (the measure of Utah's Pig Farm, whose rope
    at x=-1185 passes 36 from the span at y=-145 and whose rope at x=1453 passes
    38 from the span at y=-25). The player climbs from the floor (50 below the
    rope's bottom end: a jump-grab) and gets off sideways onto that platform. Getting
    off sideways is a jump and is priced as one (JUMP_EFFORT plus the 38 of reach):
    the way is dearer than it used to be, but it is still the only way there."""
    ground = [[0, 300, 200, 300], [138, 175, 300, 175]]
    walk = Walk.of(ground, [[100, 100, 250]])
    assert walk.pads((10, 300), (200, 175), []) == []


def test_a_rope_can_be_grabbed_mid_way_from_a_platform_beside_it():
    # the same beside platform, this time as the start: jump at the rope from it,
    # grab on at y=175 (between the rope's ends), climb and jump off the top end
    # (50 short of the platform at y=50). The grab is a jump and costs one: it used
    # to be thrown in with the climb for the edge's flat 1, which is what made a
    # beside-to-beside hop cheaper than walking (see the shaft-crossing test below)
    ground = [[138, 175, 300, 175], [0, 50, 200, 50]]
    walk = Walk.of(ground, [[100, 100, 250]])
    assert walk.pads((200, 175), (150, 50), []) == []


def test_a_platform_too_far_beside_a_rope_is_not_a_mid_rope_exit():
    # the same platform starting 80 units east of the rope: past one jump sideways,
    # so the rope does not serve it and nothing else climbs there
    ground = [[0, 300, 200, 300], [180, 175, 300, 175]]
    walk = Walk.of(ground, [[100, 100, 250]])
    assert walk.pads((10, 300), (200, 175), []) is None


def _west_floor(y):
    """A floor of 100-wide fragments running west from x=100, so a pad placed along it is
    reached by a walk whose length its x gives: walking into a span costs its width, so
    from x=50 the pad at x=-100 is 100 walked, the one at x=-300 some 300, the one at
    x=-800 some 800 — each good to one fragment, which is all the brackets below need."""
    return [[-800 + 100 * k, y, -700 + 100 * k, y] for k in range(9)]


def test_a_lateral_hop_across_a_shaft_on_a_rope_costs_two_jumps():
    """Both spans join the rope from beside it, at the same height: the player jumps at
    the rope, holds it, climbing nothing, and jumps off the other side. That is two jumps
    by rule 5 — JUMP_EFFORT plus 51 of reach each, some 602 for the 102-unit crossing —
    not the flat 1 the edge used to cost, which was less than walking a single unit.
    A pad is the yardstick: one reached by walking some 400 west still beats the
    crossing, so the crossing costs more than a jump of that reach would
    (JUMP_EFFORT + 102 = 352), while one some 800 west loses to it."""
    ground = [*_west_floor(0), [202, 0, 302, 0]]
    walk = Walk.of(ground, [[151, -50, 50]])          # rope 51 from each span's near end
    near = Jump((-100, 0), (250, 0), "t001")          # 100 walked: the crossing's own width
    mid = Jump((-400, 0), (250, 0), "t002")           # some 400 walked
    far = Jump((-800, 0), (250, 0), "t003")           # some 800 walked
    # the crossing loses to a walk of the same 102 and to a jump of that reach
    assert walk.pads((50, 0), (250, 0), [near]) == [near]
    assert walk.pads((50, 0), (250, 0), [mid]) == [mid]
    # but it is not boundless: a pad 800 of walking away is the worse way
    assert walk.pads((50, 0), (250, 0), [far]) == []


def test_a_straight_climb_up_a_rope_costs_its_height_and_nothing_at_the_ends():
    """The rope ends on the floor and at the platform above: both ends are ordinary
    joins, so the climb is its 100 of height at CLIMB_WEIGHT (some 501) as it always
    was. A pad reached by walking 300 west beats it; one 800 west does not."""
    ground = [*_west_floor(200), [50, 100, 250, 100]]
    walk = Walk.of(ground, [[100, 100, 200]])
    near = Jump((-100, 200), (150, 100), "t001")      # 100 walked
    mid = Jump((-300, 200), (150, 100), "t002")       # 300 walked
    far = Jump((-800, 200), (150, 100), "t003")       # 800 walked
    assert walk.pads((50, 200), (150, 100), [near]) == [near]
    assert walk.pads((50, 200), (150, 100), [mid]) == [mid]
    assert walk.pads((50, 200), (150, 100), [far]) == []


def test_an_ordinary_top_and_bottom_rope_join_is_priced_as_it_always_was():
    """The same rope stopping 50 short of the floor and 50 short of the platform — the
    ordinary join, where the rope's own end meets its span across a gap (a median of 2
    across the KB, well inside one jump). The ends are grabbed and left at the rope's
    end, not sideways, so they keep the flat 1 between them and the same pads win and
    lose as for the rope that touches both."""
    ground = [*_west_floor(200), [50, 100, 250, 100]]
    walk = Walk.of(ground, [[100, 150, 150]])
    mid = Jump((-300, 200), (150, 100), "t002")       # 300 walked
    far = Jump((-800, 200), (150, 100), "t003")       # 800 walked
    assert walk.pads((50, 200), (150, 100), [mid]) == [mid]
    assert walk.pads((50, 200), (150, 100), [far]) == []


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


def test_a_ledge_just_past_the_lower_spans_end_is_a_jump():
    """One platform tier (60 units) up, with the ledge starting 12 units past the
    lower span's end — the two cut-off tower platforms on Utah's Pig Farm sit
    exactly so (60 up, 12 past the span below) — so the player jumps up and drifts
    the 12 sideways onto it, and no pad is named. Sideways drift in the air is the
    fall's drift (30), and 12 is well inside it."""
    walk = Walk.of([[0, 200, 200, 200], [212, 140, 400, 140]], [])
    assert walk.pads((10, 200), (300, 140), []) == []


def test_a_ledge_at_the_edge_of_the_drift_is_still_a_jump():
    # the same tier up, the ledge starting the full drift (30 units) past the lower
    # span's end: still landed on, so still no pad
    walk = Walk.of([[0, 200, 200, 200], [230, 140, 400, 140]], [])
    assert walk.pads((10, 200), (300, 140), []) == []


def test_a_ledge_past_the_lower_spans_end_but_too_high_is_not_a_jump():
    # the same 12 past the end, but two tiers (120 units) up: past one jump however
    # near it sits sideways, so without a pad it is unreachable and the pad is named
    pad = Jump((50, 200), (300, 80), "t001")
    walk = Walk.of([[0, 200, 200, 200], [212, 80, 400, 80]], [])
    assert walk.pads((10, 200), (300, 80), []) is None
    assert walk.pads((10, 200), (300, 80), [pad]) == [pad]


def test_a_ledge_offset_sideways_past_the_lower_span_is_not_a_jump():
    """The same tier up, but the ledge starts 40 units past the lower span's end:
    past the sideways drift of a jump (30, the fall's drift), so no jump lands on
    it. Without a pad the ledge is unreachable, and the pad that lands there is
    the way."""
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


def test_a_pad_way_within_the_models_resolution_is_named():
    """A pad way that loses only inside the model's resolution (rule 9 in
    terrain.py: MODEL_RESOLUTION, 3.4% of the pad-free way's cost, measured from
    how far the computed cost moves for spots on the same joined platform) is a
    tie the model cannot tell apart, and the tie goes to the pad — so long as the
    pad carries the player forward (rule 10). The floor runs 2300 of walking east
    from where the player stands to the target, and the pad's dot sits 1250 west
    of them: walking out to it, teleporting, and walking the last 1100 east from
    where it lands costs 2355 against 2300, a loss of 55 inside the band of 78,
    so the pad is named though it does not win outright. It is worth naming
    because taking it really does leave less walk: its landing lies 1200 of
    walking further along than where the player stands, far past that band."""
    ground = [[x, 600, x + 100, 600] for x in range(0, 2400, 100)] + \
        [[x, 600, x + 50, 600] for x in range(-1400, 0, 50)]
    pad = Jump((-1175, 600), (1250, 600), "t001")
    walk = Walk.of(ground, [])
    assert walk.pads((10, 600), (2350, 600), [pad]) == [pad]


def test_a_pad_that_lands_the_player_where_they_stand_is_not_named():
    """Standing on a pad's own landing, that pad is a loop: the walk to its dot
    and the teleport put the player back where they already are, and the same
    2300 of walking east to the target follows from there. This is Utah's Pig
    Farm's t004 in miniature (terrain.py rule 10): the player stands on the floor
    the pad lands on, its dot sits on a ledge one fall below, so the way through
    it costs 2306 against the pad-free 2300 — 0.26%, well inside rule 9's band of
    78, which is why the band alone used to name it. Its landing is where they
    already stand, reached for 0, so it carries them nowhere and nothing is
    named: no teleport is worth taking."""
    ground = [[x, 400, x + 100, 400] for x in range(0, 2400, 100)] + [[0, 600, 200, 600]]
    pad = Jump((50, 600), (50, 400), "t001")
    walk = Walk.of(ground, [])
    assert walk.pads((50, 400), (2350, 400), [pad]) == []


def test_a_pad_way_losing_by_more_than_the_resolution_is_not_named():
    """A ledge over the west end of a long floor, and a pad off it landing 500
    units west of where a fall from that ledge lands: the player stands on the
    ledge and the target is 2350 east along the floor, so the pad's way pays that
    500 back again on top of the teleport, some 2705 against 2201 — a loss of
    about 23%, far past the model's resolution (rule 9), so the pad-free way wins
    outright and [] keeps its meaning: no teleport is worth taking."""
    ground = [[0, 400, 200, 400]] + \
        [[x, 600, x + 100, 600] for x in range(-400, 2400, 100)]
    pad = Jump((50, 400), (-350, 600), "t001")
    walk = Walk.of(ground, [])
    assert walk.pads((10, 400), (2350, 600), [pad]) == []


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
