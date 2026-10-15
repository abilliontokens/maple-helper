"""Which hidden teleports to take across one map, worked out from its real ground.

`routes.Graph.shortcut_path` used to score pads by the straight line between two spots on the
minimap picture. On a platform maze that line is a lie: the player cannot walk it, and the pads
are how the map is crossed at all. This module is the honest version. Given a map's footholds
and ropes (NiaMeowDB's terrain for the map, stored in the KB's terrain.json) and the map's
hidden teleports, `Walk.pads` names the teleports the cheapest real walk uses, in order, and
`Walk.path` gives that very walk step by step.

Qt-free and KB-free on purpose: the caller (`routes.Graph`) owns reading terrain.json, turning
picture fractions into map units, and falling back to its straight-line heuristic when this
module can say nothing. Everything here is in map units, in the game's own coordinates, where
y grows downward (a smaller y is higher up).

The model — every line of this is an assumption fitted to the data, not a fact about the game:

1. Standable ground. A foothold (`fh`, `[x1, y1, x2, y2]`) stands a player up when it is not
   too steep: `|dy| <= STAND_SLOPE * |dx|`. Vertical footholds are walls and never standable.
   On Utah's Pig Farm (map 010001082, the map that forced this work) 355 of its 652 footholds
   pass that cut and every non-vertical one has `|dy| <= 0.875 * |dx|`, so a cut of 1.0 keeps
   every real slope and drops only walls. Foothold fragments that touch end to end (the site
   splits one platform into many short segments) join into one walk: a player walks freely
   along joined spans, at a cost of the horizontal length walked.
2. Walls. A foothold too steep to stand on (rule 1's discards, vertical ones included) is
   a wall: in this game a vertical foothold blocks sideways movement, so the discarded
   footholds are kept as wall segments. A wall blocks two moves. It blocks a fragment
   join it stands on — a wall rising through the point where two fragments touch splits
   the walk there, the way a cliff face rising from the floor stops a player walking
   along that floor — and it blocks a fall whose drop line passes through it or past
   its foot (its lowest point); a drop that only runs along a wall's face, or lands
   against that face, is not blocked, and a fall stopped by a wall face lands on the
   next span below whose drop is clear. Ropes are not tested against walls (a rope is
   climbed against a face), and neither are jumps. Utah's Pig Farm shows why walls
   matter: a vertical foothold at x=-1119 runs from the floor at y=155 up to y=-240,
   right beside the small west platform at y≈91, so that platform's floor cannot be
   walked east past it, however continuous the floor's footholds look.
3. Ropes and ladders. An `lr` entry is `[x, y_a, y_b]`: a vertical climb at `x` between the
   two y values, in either order. The site does not document that; it is read from its data.
   The third value cannot be a height: on map 010001081 `[-3885, -1343, -1147]` as a height
   would end at y=-2490, above that map's whole view rectangle, while as an end it is a
   196-unit rope from the span at y≈-1345 toward the one at y≈-1105; on Utah's Pig Farm
   `[1964, -803, 85]` as a height ends at y=-718 on nothing, and as an end it lands on the
   span at y≈87. A rope joins, both ways, every span it crosses plus any span ending within
   one jump past either end (ROPE_END_DIST = JUMP_HEIGHT, rule 5's measured one-tier jump):
   past the bottom end the player jumps up and grabs the rope, and past the top end they
   jump off the rope onto the span above, so either reach is the same jump. A span farther
   past an end than one jump is not served by that rope, however near it looks on the
   picture: on Utah's Pig Farm the rope at x=1453 ([1453, -189, 105]) stops 76 units short
   of the span at y=-265 above it, and the rope at x=-1185 ([-1185, -301, 35]) stops 84
   short of the span at y=-385, both past one jump, so neither rope climbs to those
   spans. A rope is not only its two ends, either: it also joins every span that passes
   beside it — a span whose nearest point sits within one jump sideways of the rope's
   line (ROPE_SIDE_DIST = JUMP_HEIGHT) at a height between the rope's ends, which the
   player reaches by jumping off the rope sideways, or grabs the rope mid-way from by
   jumping at it. On Utah's Pig Farm the rope at x=-1185 passes 36 units east of the
   span at y=-145 and the rope at x=1453 passes 38 west of the span at y=-25, and
   across every map in the KB the nearest beside-platform distance per rope holds
   steady out to about 64 units and then drops away — the same one-jump reach. The
   rope at x=1964, by contrast, ends 2 units above the span at y≈87 at its bottom
   end and 2 below Utah's span at y=-805 at its top: solid contact at both ends. A
   climb is priced per unit of height by rule 8, not at walking's 1 per unit, and each of
   the two ends is priced for what making it costs. An end at the rope's own line — the
   rope crossing the span, or stopping within a jump of its end — is the ordinary top or
   bottom join — mostly solid contact: across the KB's 1697 rope ends that meet a span
   at all, the end-to-span gap has a median of 2 — and keeps the half of
   the flat 1 the edge has always paid. A beside end is not that: the player jumps at the
   rope to grab it, or jumps off it sideways, which is a jump by rule 5 and is charged as
   one, JUMP_EFFORT plus the sideways reach. Without that the model priced a lateral hop
   across a shaft at less than walking a single unit: on Utah's Pig Farm the rope at
   x=-991 passes 50 from the span (-1119..-1041, y=-445) and 52 from the span
   (-939..-861, y=-445), the same height, so crossing the 102 units between them cost
   1.0 — the whole edge price, no climb at all. It now costs 602.0 (two jumps, 250 of
   effort plus 50 and 52 of reach), and the map's other two beside-to-beside crossings
   go 301.0 -> 902.0 (x=-539, 60 of climb) and 601.0 -> 1202.0 (x=1003, 120 of climb).
4. Falling. From a few probe points along a span the player drops onto the first span
   below (greater y) whose ground is within FALL_REACH sideways and whose drop no wall
   (rule 2) crosses. Falling is one way and nearly free (priced by rule 8). Probing, rather than solving
   every drop line exactly, is the one deliberate simplification: a lower span that only
   ever passes under a span between two probes is missed, and in a map of hundreds of
   spans that has not been seen to matter.
5. Jumping up. A character jumps: from anywhere along a lower span they can land on a
   higher span that sits over it — the higher span's x range must overlap the lower one's
   (touching at an end counts: that is a ledge whose foot is the lower span's end) — and
   that is at most JUMP_HEIGHT above it over that overlap, so a lower span joins (one way,
   upward only) every higher span that sits over it within one jump. A ledge that sits
   just past the lower span's end counts too, within JUMP_SIDE_DIST sideways of it: a
   jump is airborne the way a fall is, and drifts as far sideways (FALL_REACH, rule 4)
   before it lands, the rise then measured between the spans' nearest ends. That drift
   is measured, not assumed: joining fragments into platforms across the KB and taking,
   for each platform, the nearest higher platform one tier up (50–70) gives 521 that sit
   over the lower one, 154 that sit within 30 past its end — 105 of those within 12 —
   and only 34 that sit 31–70 past it, so tier ledges past an end concentrate inside
   the drift and thin out beyond it. Utah's Pig Farm has the pattern twice, at its two
   cut-off tower platforms: the span at (231–309, -445) jumps 60 up and 12 east onto
   the span at (321–399, -505) toward t005, and the span at (681–759, -385) jumps the
   same 60 up and 12 east onto the span at (771–849, -445) toward h006; with overlap
   alone neither platform is reached from anywhere, however near it looks on the
   picture. A span farther past the end than the drift is not a jump: the character
   cannot drift sideways onto ground that is well past where they jumped from. The
   height is measured from the map, not assumed: on Utah's Pig Farm, joining fragments into
   platforms and taking, for each platform, the rise to the nearest higher platform that
   overlaps it in x gives one platform tier of 57–68 units for 22 of its 49 platforms,
   and the next rises up are 120, then 168–180, then 230–240 — two and three tiers.
   JUMP_HEIGHT = 70 therefore climbs exactly one tier, never two. Utah's Pig Farm shows
   why the rule is needed at all: the player stands on a span at y≈-690 and Utah stands
   on one at y=-805, about 113 units higher, with no rope serving Utah's ledge from below
   (the nearest rope, at x=1964, hangs 164 units past that span's east end at x=1800, and
   serves it only from the map's floor far below). No single jump spans that 113 either —
   JUMP_HEIGHT is deliberately under it — but without any jumping the player's span
   connects upward to nothing, while with it the player can climb in steps (the first onto
   the span at y=-625, some 65 up) and work across and around to that far rope. A jump
   costs its height plus JUMP_EFFORT: a jump is slow to line up and land compared with
   walking the same rise on a slope, so the fixed part is priced well above the height
   itself, and a long ladder of jumps loses to a pad that skips the ladder (rule 8
   says why the height part itself stays at walking's 1 per unit). A jump at a rope, or
   off one sideways, is this same jump and costs the same (rule 3): the rope's beside
   ends are priced here, not given away, so a lateral hop across a shaft on a rope can
   no longer undercut a walk. What that repricing did, measured against the live KB
   (old price -> new price), on Utah's Pig Farm (010001082) with Utah as the target:
     - the pad chain from the owner's spot (-1191, -220): t001, t003, t004 -> unchanged;
       from t001's landing (-1480, -637): t003, t004 -> unchanged.
     - from that landing, t003's lead over t002 widens: t002 9606.0 vs t003 8231.0
       (16.7% of t003) -> t002 11095.5 vs t003 8697.5 (27.6%).
     - KB-wide, 103 maps have ground and 97 of them answer a pad query, before and
       after alike; the 44 of 688 queries that go unanswered are the same 44 either way,
       so no map that answered stops answering.
     - on this map, 43 of its 355 standing spots (one per span, at its middle) change
       their answer, every one of them from "walk there" to naming a pad, or from a
       chain to a longer one: the free hop had been standing in for a real crossing.
6. Hidden teleports. A jump (a hidden teleport; `Jump` to the engine, `jumps` in `pads`)
   connects the span under its `frm` to the span under its `to`, one way, at a flat
   TELEPORT_COST. Either end that cannot be snapped to a span (rule 7) makes that jump
   unusable, never the whole query.
7. Snapping. The player, the target, and the jumps' ends are points that should be standing
   on the ground, so each stands on the ground beneath it: the first standable span at or
   below the point (no higher, a greater y) within SNAP_DOWN, whose x range covers the point
   to within FALL_REACH sideways. A point with no such span — standing at the very bottom of
   a map, or a little under its ground — falls back to the nearest span within SNAP_DIST,
   and that fallback never overrides a reachable span below. An end that snaps to nothing
   means the ground data cannot speak for where that point is.
8. Prices. Walking sets the scale: one unit sideways costs 1 (rule 1). The other moves
   are priced against it by how a player actually does them, not by straight-line
   distance. A rope climb costs CLIMB_WEIGHT (5) per unit of height, the same number
   — and for the same reason — as `routes.SHORTCUT_CLIMB`, the straight-line model's
   climb weight (`routes` imports this module, so the number is restated here rather
   than imported; the two must move together). There, a player crosses a map on foot
   but cannot walk upward at all: they climb it by ladders, ropes and platform jumps,
   while a pad moves them up or down for free; priced at 2.5 the walk was nearly
   straight-line and the pads on Utah's Pig Farm were never named from its lower
   floors, and at 5, 18 of its 29 spawn points named a pad in that census. This model
   used to charge a climb the height itself (1 per unit, as if climbing were walking
   sideways), so the 960-unit climb on Pig Farm's rope at x=1964 cost 961 and the
   pad-free way through it beat the way through t007 from (140, -493); at 5 per unit
   that climb alone costs some 4800, so wherever a pad actually skips a long climb
   it is named, as it is in play. From (140, -493) itself every way to Utah shares
   that final climb, and t007 only cuts short a fall and a floor walk its landing
   is already beside, so its way (7832) stays behind the pad-free way (7581) by
   251 — pricing a climb both ways share cannot separate them; rule 9, the model's
   own resolution, is what names it there. The
   same weight applies down a rope: a ladder down is still climbed, rung by rung,
   and where a player would simply drop, rule 4's fall edge is the cheap way
   instead. A fall itself stays flat FALL_COST plus its sideways drift at walking
   price: gravity does the vertical work and a drop is over in a moment however far
   it falls, so a fall's height is charged nothing — the opposite of a climb, not an
   oversight. A jump's height part likewise stays at 1 per unit on top of JUMP_EFFORT,
   and is not inconsistent with CLIMB_WEIGHT: a jump only ever rises one tier
   (57–68 on Pig Farm, at most JUMP_HEIGHT), so its all-in price of 307–320 for a tier
   already sits inside the 285–340 a rope charges for that same rise at 5 per unit —
   the fixed effort does the climb-pricing work. Charging the height at 5 as well
   would price one jump at some 550–590, near twice the rope for the same rise, for
   a single airborne motion that is not a sustained climb.
9. Resolution and ties. Within a span the exact entry and exit points are not
   tracked (see the summary below), so a cost is an estimate whose last few percent
   the model itself cannot stand behind: where exactly along their platform the
   player stands, and where along the target's platform the target stands, moves
   the real effort while the computed cost steps by whole fragments. Measured
   on the live KB (2026-10-14, ground from terrain.json for 108 maps): for spots
   on the same
   joined platform (rule 1's fragments joined into one walk) — the player moved
   along it, and separately the target moved along its own — the computed cheapest
   cost moved by a median of 90 map units (one span's width: span widths across
   those maps run a median of 50, 90 at the 75th percentile). As a share of the
   way's cost that spread is meaningless on a trivial way, so it is read off the
   1478 platform ways costing at least 1000 (median way 3028): there the spread's
   median share is 3.44% of the way's cost. That share is MODEL_RESOLUTION. Inside
   it two ways are indistinguishable to this model, and the tie goes to the pad:
   the player asked to be shown the teleports, and a pad way that ties is the one
   a player takes. Outside it the pad-free way still wins outright — this is a
   tie-break at the model's own resolution, not a thumb on the scale. On Utah's
   Pig Farm that means t007 is named from (140, -493): its way loses by 251 on
   7581, 3.3%, inside the band; a pad way losing by more is still not named, and
   [] still means exactly that — no teleport is worth taking. Standing at Utah's
   own spot the pad-free way costs 0, the band around it is 0 wide, and nothing
   is named. The 28 spawn points of that map (the site's maps.json spawns toward
   Utah) name a pad from 13 of them before this rule and 18 after — the five
   added are four t007 ways and one t005 way, losing by 228–251 (3.1–3.4%) —
   not from nearly all: a band read off a wider part of the spread (its
   75th-percentile share, 9%) would name 27 of the 28, which is how a too-wide
   band would show itself.
10. A named pad must advance. Rule 9's band is wide enough to let a way be named for
   tying, so what it names must still be a way worth taking: a pad is worth naming
   only where taking it carries the player forward. What remains of the walk from a
   span is the whole pad-free way less what reaching that span cost without pads, and
   the search has both already settled in its first layer, so the test is one lookup
   per named pad and no second search. A pad whose landing the pad-free walk reaches
   for no more than the band of rule 9 leaves as much walk as the player already
   faces where they stand: it puts them back where they effectively are, or behind,
   and its way is the pad-free way with a loop bolted on. Measured on the live KB
   (2026-10-15), Utah's Pig Farm toward Utah at (1766, -809): standing on t004's own
   landing (-5, -630) — a fresh read after a restart, or arriving by another way —
   the pad-free walk costs 8040.5 and the way through t004 costs 8089.5, 0.61%
   dearer and well inside the band of 273.4, so rule 9 named t004: the player walks
   the 44 back down to its dot at (-141, 36), teleports, and arrives where they
   already stood. Its landing is where they stand, settled at 0, so rule 10 drops it
   and no pad is named there — the one way through a pad that rule 9 would have
   named is dropped whole, rather than the next-dearest tie hunted for after the
   search has stopped. The ties rule 9 is for are untouched: from (140, -493) the way
   through t007 costs 8119.5 against 7868.5, 3.19% inside a band of 267.5, and its
   landing sits 2642.5 along that walk, ten times the band past where the player
   stands, so t007 is still named. What is deliberately not the measure is the pad's
   own dot. The walk on from the dot takes a second search, and would name the loop:
   nothing climbs back up from t004's dot, which the player reaches by a one-way
   fall, so the walk from the dot reaches Utah not at all while the walk from its
   landing reaches it for 8040.5, and every such pad would look like progress. The
   dot's cost from the player is settled and no help either — it would unname t007,
   whose dot sits 246 further along the walk than its own landing (2888.5 against
   2642.5), the climb the pad gives back. Where no pad-free way reaches the goal at
   all there is nothing to measure against, and the pad way, being the only way
   there, stands. What the rule moves, on that map toward Utah: asked from each of
   its 16 pads' own landings, t004 was the only pad naming itself (t005's and t006's
   landings name t007, the nine h pads' shared landing names t001, t003, t004 — all
   unchanged, as are (-1191, -220) -> t001, t003, t004 and t001's landing -> t003,
   t004). Standing at the middle of each of its 355 spans, a pad is named from 263
   spots before this rule and 244 after; all 19 that change stand within the band of
   the landing of the pad they named (t005's or t007's) and all 19 change to naming
   none. KB-wide (115 maps with ground, 2237 queries from span middles toward each
   map's pad landings) the same 2106 queries answer before and after, from the same
   114 maps: a rule that only ever returns [] in place of a chain cannot stop a map
   answering.

`pads` returns the teleports on the cheapest walk, in the order taken: effort, not
pad-count, decides. Walking into a span costs its horizontal length, a rope
CLIMB_WEIGHT per unit of height climbed (plus what each of its two ends costs: half
the old flat 1 at an ordinary end, a jump's price at one taken sideways), a fall a
flat FALL_COST (plus its sideways
drift), a jump its height plus JUMP_EFFORT (and its sideways
drift, when it lands past the lower span's end), and a teleport a flat TELEPORT_COST
— about nothing, since the teleport itself is instant, but not zero, so it still
counts in a way's cost. The teleports returned are those of the cheapest pad-using
way when that way wins outright, and also when it only ties the cheapest pad-free
way within the model's resolution (rule 9, MODEL_RESOLUTION of the pad-free cost) —
in either case only while every pad in it carries the player forward (rule 10);
[] is returned when every pad-using way loses by more than that, when the cheapest
one only loops back to where the player already effectively stands, or when none
reaches at all: no teleport is worth taking. However many jumps a way takes
does not decide it; effort does. Within a span the exact entry and exit points
are not tracked, so costs are map-unit estimates good enough to order ways
clearly apart, not to separate ways a few percent apart — rule 9 again.

Cost, by counting and by timing: the model is built once per map (`Walk.of`).
Utah's Pig Farm, among the largest maps, gives 355 spans, 297 walls and 11 ropes; the
walls sit in the same x-bin index as the spans, so each join or fall probe tests the few
walls in its neighbourhood rather than scanning them all. Joining, rope, fall and jump
edges are a few per span (the jump pass compares every pair of spans — some 126k pairs —
but keeps only the few that come within a jump of each other), so a query's Dijkstra
search visits a few hundred nodes and relaxes a few thousand edges, and jump ends are
snapped once and remembered by their points. Rule 9 does not add a second search: it
adds the pad-using layer to that same search, walked only as far as the band can
reach (states past it are never pushed, and the search stops when the pad-using
layer settles at the goal). Timed on that map against the live KB (2026-10-14,
500-query averages, this machine), a query from (140, -493) toward Utah took
0.27 ms before this rule and 0.57 ms after it — the second layer costs about
0.3 ms on the largest map; a pad-winning spot took 0.31 ms before and 0.45 ms
after, and standing at the target itself is unchanged at some 0.02 ms.
Rule 10 adds no search either: the first layer writes its settled cost as each span
comes off the queue (one dictionary store per settled span), and a named chain is
judged by one lookup per pad in it. Timed the same way on the same map (2026-10-15,
best of three 2000-query runs, this machine, with the rope-end prices in): the
(140, -493) tie took 0.673 ms before rule 10 and 0.694 ms after, standing on t004's
landing 0.690 ms and 0.695 ms, the three-pad chain from (-1191, -220) 0.512 ms and
0.504 ms, and standing at the target itself 0.017 ms and 0.018 ms — at most 0.02 ms
on the largest map, which is inside the spread between runs.

`path` reads that same search out as the way itself, step by step — one point per span the
way passes through, how the way got onto it, and a pad's name where a pad did — so `pads`
is `path`'s teleports and neither answer costs a second search. What each move is (a walk,
a fall, a rope, a jump up) and where it lands on the span it reaches are worked out once
per map, while the edges are built, so a query reads them off rather than deriving them,
and a query that asks for no way back — every `pads` query — never even reads the way's
spans. Timed on Utah's Pig Farm against the live KB (2026-10-15, best of five 2000-query
runs, both models built from the same ground in one process): the three-pad chain from
(-1191, -220) cost 0.545 ms before this and 0.536 ms after, the (140, -493) tie 0.755 ms
and 0.758 ms, standing at the target itself 0.020 ms and 0.020 ms — the difference is
inside the spread between runs, and the after side is the faster one as often as not.
Building a map's model keeps one tuple per edge where it kept a float, which costs it about
the same or a little more (60.7 ms against 64.4 ms for that map's 355 spans on the quietest
run, the two indistinguishable on busier ones), once per map. KB-wide (115 maps with ground,
33,899 queries from span middles toward each map's pad landings) `pads` answers exactly what
it answered before, and each of the 33,464 ways it answers has a path whose pads are that
answer.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import NamedTuple

# a foothold stands a player up when its rise over its run is at most this (see rule 1 above)
STAND_SLOPE = 1.0
# a point this far (map units) from a standable span still counts as standing on it when it
# has no ground below it to stand on (rule 7)
SNAP_DIST = 60.0
# how far below a point (map units) the ground it stands on may lie (rule 7): a character is
# a few tens of units tall, so its minimap dot sits that far above its feet, and a pad's dot
# is drawn 50 units above its own point (routes.PORTAL_MARK_RISE), so a point can sit some
# 120 units above the foothold under it — the live Pig Farm player read was 113 above theirs;
# 160 covers that with room to spare
SNAP_DOWN = 160.0
# foothold fragments this close end to end are one walk (rule 1)
JOIN_DIST = 2.0
# how far sideways a falling player can drift onto the span below (rule 4)
FALL_REACH = 30.0
# what a fall costs: nearly nothing, but not nothing, so a walk on the same level can win
FALL_COST = 1.0
# what one unit of height on a rope or ladder costs, in units walked sideways (rule 8):
# the same climb weight, and the same reasoning, as routes.SHORTCUT_CLIMB (routes imports
# this module, so it is restated here rather than imported — the two must move together)
CLIMB_WEIGHT = 5.0
# how far sideways (map units) a jump up may land past the lower span's end (rule 5):
# a player airborne in a jump drifts sideways as one falling does (FALL_REACH, rule 4),
# so a ledge starting within that drift of the lower span's end is still landed on, and
# one farther past it is not — on Utah's Pig Farm both cut-off tower platforms sit
# exactly 12 past the span below them (see rule 5), well inside this, and the ledge
# 40 past its span in the tests sits outside it
JUMP_SIDE_DIST = FALL_REACH
# how high (map units) a character can jump onto a span above (rule 5): one platform tier —
# the nearest overlapping higher platform on Utah's Pig Farm is 57–68 up, the next tiers
# 120 and more, so 70 climbs one tier and never two (see rule 5)
JUMP_HEIGHT = 70.0
# the fixed effort of one jump up, on top of its height (rule 5): a jump is slow to line
# up and land, so one tier's jump costs some 320 all-in — a ladder of them loses to a pad
# that skips it (rule 8: that all-in price is already the climb price of one tier, so
# the height part stays at walking's 1 per unit)
JUMP_EFFORT = 250.0
# what a hidden teleport costs: about nothing (it is instant), but not nothing, so it
# still counts in a way's cost (rule 9 decides the ties that leaves)
TELEPORT_COST = 5.0
# the model's resolution (rule 9): two ways at most this share of the pad-free way's
# cost apart are indistinguishable to a model that does not track where within a span
# a way enters or leaves it — measured as the median share (3.44%) by which the
# computed cheapest cost moves for spots on the same joined platform, across the KB's
# maps with ground, on ways costing at least 1000 (see rule 9)
MODEL_RESOLUTION = 0.034
# a span this far past a rope's end still counts as served by that rope (rule 3): one jump
# (JUMP_HEIGHT, rule 5's measured tier) — the player jumps up to grab the bottom end, and
# jumps off the top end onto the span above, so a span farther past an end than one jump
# is not served by that rope at all
ROPE_END_DIST = JUMP_HEIGHT
# a rope this far sideways of a span's end still crosses that span (the site's rope x can sit
# a few units past the last foothold fragment of the platform it hangs over)
ROPE_X_DIST = 10.0
# how far sideways of a rope's line a span it passes — its y between the rope's ends —
# still counts as served by that rope (rule 3): one jump sideways (JUMP_HEIGHT), off the
# rope onto the platform beside it or at the rope from that platform to grab on mid-way
ROPE_SIDE_DIST = JUMP_HEIGHT
# x-bin width of the span and wall index that keeps snapping and fall probes off a full scan
# per query
_BIN = 128.0
# where along a span falling is probed from: both ends and the quarters between (rule 4)
_FALL_PROBES = (0.0, 0.25, 0.5, 0.75, 1.0)


def _nums(row, count: int) -> tuple[float, ...] | None:
    """A terrain row's first `count` values as floats, or None when it hasn't got them."""
    try:
        values = tuple(float(v) for v in row[:count])
    except (TypeError, ValueError):
        return None
    return values if len(values) == count else None


@dataclass(frozen=True)
class _Span:
    """One standable foothold fragment: (x0, y0) to (x1, y1), x0 <= x1, y downward."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    def y_at(self, x: float) -> float:
        """The ground's height at x (x clamped into the span before asking)."""
        return self.y0 + (self.y1 - self.y0) * (x - self.x0) / self.width

    def closest(self, px: float, py: float) -> tuple[float, float]:
        """The point of this fragment nearest a point (the projection `dist` measures)."""
        t = max(0.0, min(1.0, ((px - self.x0) * self.width + (py - self.y0) * (self.y1 - self.y0))
                         / (self.width ** 2 + (self.y1 - self.y0) ** 2)))
        return self.x0 + t * self.width, self.y0 + t * (self.y1 - self.y0)

    def dist(self, px: float, py: float) -> float:
        """Distance from a point to this fragment, end to end."""
        qx, qy = self.closest(px, py)
        return math.hypot(px - qx, py - qy)


@dataclass(frozen=True)
class _Wall:
    """One foothold too steep to stand on (rule 2): (x0, y0) to (x1, y1), x0 <= x1, y downward."""

    x0: float
    y0: float
    x1: float
    y1: float

    def dist(self, px: float, py: float) -> float:
        """Distance from a point to this wall, end to end (a wall has length, never none)."""
        dx, dy = self.x1 - self.x0, self.y1 - self.y0
        t = max(0.0, min(1.0, ((px - self.x0) * dx + (py - self.y0) * dy) / (dx ** 2 + dy ** 2)))
        return math.hypot(px - (self.x0 + t * dx), py - (self.y0 + t * dy))


def _side(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    """Which side of the line a→b the point p is on (signed, zero on the line)."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def _on_segment(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> bool:
    """The point p lies on the segment a→b (the caller has it on the segment's line)."""
    return (min(ax, bx) - 1e-9 <= px <= max(ax, bx) + 1e-9
            and min(ay, by) - 1e-9 <= py <= max(ay, by) + 1e-9)


def _segments_cross(ax: float, ay: float, bx: float, by: float,
                    cx: float, cy: float, dx: float, dy: float) -> bool:
    """The segments a→b and c→d touch or cross, endpoints included."""
    d1, d2 = _side(cx, cy, dx, dy, ax, ay), _side(cx, cy, dx, dy, bx, by)
    d3, d4 = _side(ax, ay, bx, by, cx, cy), _side(ax, ay, bx, by, dx, dy)
    if ((d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9)) and \
            ((d3 > 1e-9 and d4 < -1e-9) or (d3 < -1e-9 and d4 > 1e-9)):
        return True
    return (abs(d1) <= 1e-9 and _on_segment(cx, cy, dx, dy, ax, ay)
            or abs(d2) <= 1e-9 and _on_segment(cx, cy, dx, dy, bx, by)
            or abs(d3) <= 1e-9 and _on_segment(ax, ay, bx, by, cx, cy)
            or abs(d4) <= 1e-9 and _on_segment(ax, ay, bx, by, dx, dy))


def _segments_properly_cross(ax: float, ay: float, bx: float, by: float,
                             cx: float, cy: float, dx: float, dy: float) -> bool:
    """The segments a→b and c→d cross at a point inside both (touching ends is not crossing)."""
    d1, d2 = _side(cx, cy, dx, dy, ax, ay), _side(cx, cy, dx, dy, bx, by)
    d3, d4 = _side(ax, ay, bx, by, cx, cy), _side(ax, ay, bx, by, dx, dy)
    return ((d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9)) and \
        ((d3 > 1e-9 and d4 < -1e-9) or (d3 < -1e-9 and d4 > 1e-9))


class Step(NamedTuple):
    """One point of a walk (`Walk.path`): where the way meets one span, in map units; how it
    got there ("walk", "fall", "rope", "jump" or "pad"); and the teleport's name on a "pad"
    step, "" on every other."""

    at: tuple[float, float]
    kind: str
    name: str


class Walk:
    """One map's walkable ground, built once (`Walk.of`) and asked per query (`pads`, `path`)."""

    def __init__(self, fh, lr):
        self._spans: list[_Span] = []
        self._walls: list[_Wall] = []
        for row in fh or []:
            seg = _nums(row, 4)
            if seg is None:
                continue
            x1, y1, x2, y2 = seg
            if x2 < x1:
                x1, y1, x2, y2 = x2, y2, x1, y1
            if x2 - x1 <= 0 or abs(y2 - y1) > STAND_SLOPE * (x2 - x1):
                # a point stands for nothing, but a wall or too-steep foothold is kept
                # as a wall (rule 2): it stands on nothing, yet it blocks movement
                if (x2 - x1) ** 2 + (y2 - y1) ** 2 > 0:
                    self._walls.append(_Wall(x1, y1, x2, y2))
                continue
            self._spans.append(_Span(x1, y1, x2, y2))
        # spans and walls by the x-bins they cover, so a snap or a fall probe reads its
        # neighbourhood
        self._by_x: dict[int, list[int]] = {}
        for i, s in enumerate(self._spans):
            for b in range(math.floor(s.x0 / _BIN), math.floor(s.x1 / _BIN) + 1):
                self._by_x.setdefault(b, []).append(i)
        self._walls_by_x: dict[int, list[int]] = {}
        for i, w in enumerate(self._walls):
            for b in range(math.floor(w.x0 / _BIN), math.floor(w.x1 / _BIN) + 1):
                self._walls_by_x.setdefault(b, []).append(i)
        # every move from a span: what it costs, what kind of move it is, and where on the span
        # it reaches it lands — the kind and the landing worked out once here, while the edges
        # are built, so that `path` costs a query nothing (`_base` is what a query reads)
        edges: list[dict[int, tuple[float, str, tuple[float, float]]]] = [dict() for _ in self._spans]
        self._edges = edges
        self._join_fragments()
        self._platform_of = self._joined_platforms()
        self._join_ropes(lr or [])
        self._join_falls()
        self._join_jumps()
        self._base = [sorted((j, move[0]) for j, move in e.items()) for e in edges]
        self._snapped: dict[tuple, tuple[int, int] | None] = {}

    @classmethod
    def of(cls, fh, lr) -> "Walk":
        """The walk model of one map's ground: its `fh` footholds and `lr` ropes (terrain.json)."""
        return cls(fh, lr)

    def _joined_platforms(self) -> list[int]:
        """Each span's joined platform (rule 1): fragments joined end to end are one platform, numbered in
        span order. Read off the fragment joins alone, before ropes, falls and jumps join spans the player
        cannot simply walk between, so two spans share a number only when the player walks freely between
        them along the ground."""
        neighbours: list[set[int]] = [set() for _ in self._spans]
        for i, edges in enumerate(self._edges):
            for j in edges:
                neighbours[i].add(j)
                neighbours[j].add(i)
        platform = [-1] * len(self._spans)
        nxt = 0
        for i in range(len(self._spans)):
            if platform[i] >= 0:
                continue
            stack = [i]
            platform[i] = nxt
            while stack:
                here = stack.pop()
                for j in neighbours[here]:
                    if platform[j] < 0:
                        platform[j] = nxt
                        stack.append(j)
            nxt += 1
        return platform


    # ------------------------------------------------------------ building

    def _add(self, i: int, j: int, cost: float, kind: str, at: tuple[float, float]) -> None:
        """Keep the cheapest move from span i to span j, with what kind of move it is and where
        on j it lands (`path`'s point for j when the way takes this move)."""
        if i == j:
            return
        if cost < self._edges[i].get(j, (math.inf,))[0]:
            self._edges[i][j] = (cost, kind, at)

    def _near(self, x_lo: float, x_hi: float) -> list[int]:
        """The spans covering any of the x-bins between two x values, each once."""
        out = set()
        for b in range(math.floor(x_lo / _BIN), math.floor(x_hi / _BIN) + 1):
            out.update(self._by_x.get(b, ()))
        return sorted(out)

    def _near_walls(self, x_lo: float, x_hi: float) -> list[int]:
        """The walls covering any of the x-bins between two x values, each once."""
        out = set()
        for b in range(math.floor(x_lo / _BIN), math.floor(x_hi / _BIN) + 1):
            out.update(self._walls_by_x.get(b, ()))
        return sorted(out)

    def _wall_stands_on(self, px: float, py: float) -> bool:
        """A wall rises through this ground point (rule 2): it passes through the point
        and reaches above it, so a walk along the ground cannot pass it there. A wall
        that only drops below the point (the face under a platform's edge) stands on
        nothing and blocks nothing."""
        return any(w.dist(px, py) <= 0.01 and min(w.y0, w.y1) < py - 0.01
                   for w in (self._walls[k] for k in self._near_walls(px, px)))

    def _wall_crosses(self, xa: float, ya: float, xb: float, yb: float) -> bool:
        """A wall crosses the drop line from (xa, ya) to (xb, yb) (rule 2). Running
        along a wall's face is not crossing it, and neither is landing against the
        face: a drop is blocked only when it passes through the wall, or past the
        wall's foot (the wall's lowest point, where passing the touch means passing
        the wall's base). A wall that only touches the line at its own start is not
        a crossing either — falling away from the edge you stand on does not cross
        the wall that edge belongs to — so the tests run from a hair past the start."""
        sx, sy = xa + (xb - xa) * 1e-6, ya + (yb - ya) * 1e-6
        walls = [self._walls[k] for k in self._near_walls(min(xa, xb), max(xa, xb))]
        for w in walls:
            if _segments_properly_cross(sx, sy, xb, yb, w.x0, w.y0, w.x1, w.y1):
                return True                     # through the wall, side to side
            if not _segments_cross(sx, sy, xb, yb, w.x0, w.y0, w.x1, w.y1):
                continue
            if abs(_side(sx, sy, xb, yb, w.x0, w.y0)) <= 1e-9 and \
                    abs(_side(sx, sy, xb, yb, w.x1, w.y1)) <= 1e-9:
                continue                        # along the wall's face, not through it
            # the drop only touches the wall, at the drop's end or at a wall's end:
            # blocked when that touch is at the wall's foot and no wall runs on below it
            for tx, ty in ((xb, yb), (w.x0, w.y0), (w.x1, w.y1)):
                if not (_on_segment(sx, sy, xb, yb, tx, ty)
                        and _on_segment(w.x0, w.y0, w.x1, w.y1, tx, ty)):
                    continue
                above = any(o.dist(tx, ty) <= 0.01 and min(o.y0, o.y1) < ty - 0.01
                            for o in walls)
                below = any(o.dist(tx, ty) <= 0.01 and max(o.y0, o.y1) > ty + 0.01
                            for o in walls)
                if above and not below:
                    return True
        return False

    def _join_fragments(self) -> None:
        """Fragments touching end to end (or end to middle) join into one walk (rule 1),
        unless a wall stands on the join (rule 2); walking into a fragment costs its
        horizontal length."""
        for i, s in enumerate(self._spans):
            for px, py in ((s.x0, s.y0), (s.x1, s.y1)):
                for j in self._near(px - JOIN_DIST, px + JOIN_DIST):
                    if j == i or self._spans[j].dist(px, py) > JOIN_DIST:
                        continue
                    qx, qy = self._spans[j].closest(px, py)
                    if (self._wall_stands_on(px, py) or self._wall_stands_on(qx, qy)
                            or any(_segments_properly_cross(px, py, qx, qy,
                                                            w.x0, w.y0, w.x1, w.y1)
                                   for w in (self._walls[k] for k in
                                             self._near_walls(min(px, qx), max(px, qx))))):
                        continue    # a wall stands on the join: not one walk (rule 2)
                    self._add(i, j, self._spans[j].width, "walk", (qx, qy))
                    self._add(j, i, s.width, "walk", (px, py))

    def _join_ropes(self, lr) -> None:
        """Every span a rope crosses, ends near, or passes beside joins every other, both
        ways (rule 3), at CLIMB_WEIGHT per unit of the height between them at the rope's
        x (rule 8), plus what each of the two ends costs to make. An ordinary end — the
        rope crossing the span or stopping within a jump of it, its line all but on the
        span's own x — keeps the half of the flat 1 it has always paid. An end the player
        reaches by jumping sideways at the rope, or leaves by jumping sideways off it,
        is a jump by rule 5 and is charged as one: JUMP_EFFORT plus the sideways reach."""
        for row in lr:
            rope = _nums(row, 3)
            if rope is None:
                continue
            x, ya, yb = rope
            top, bottom = min(ya, yb), max(ya, yb)
            joined = []
            for i, s in enumerate(self._spans):
                near_x = max(s.x0, min(s.x1, x))
                y = s.y_at(near_x)
                side = abs(x - near_x)
                if side <= ROPE_X_DIST and top - ROPE_END_DIST <= y <= bottom + ROPE_END_DIST:
                    joined.append((i, near_x, y, 0.5))   # crossed, or within a jump past an end
                elif side <= ROPE_SIDE_DIST and top <= y <= bottom:
                    # passed beside, between the ends: a jump on or off sideways (rule 5)
                    joined.append((i, near_x, y, JUMP_EFFORT + side))
            for a, (i, xi, yi, ci) in enumerate(joined):
                for j, xj, yj, cj in joined[a + 1:]:
                    cost = abs(yi - yj) * CLIMB_WEIGHT + ci + cj
                    self._add(i, j, cost, "rope", (xj, yj))
                    self._add(j, i, cost, "rope", (xi, yi))

    def _join_falls(self) -> None:
        """From each probe point along a span, a one-way cheap drop to the first span below
        within FALL_REACH sideways whose drop no wall crosses (rules 4 and 2): a fall
        stopped by a wall face slides down it, so the first span below whose drop is
        clear is the one landed on. An in-between span is itself that first span, so
        drops never tunnel."""
        for i, s in enumerate(self._spans):
            for frac in _FALL_PROBES:
                xa = s.x0 + frac * s.width
                ya = s.y_at(xa)
                below = []
                for j in self._near(xa - FALL_REACH, xa + FALL_REACH):
                    if j == i:
                        continue
                    t = self._spans[j]
                    xb = max(t.x0, min(t.x1, xa))
                    if abs(xb - xa) > FALL_REACH:
                        continue
                    yb = t.y_at(xb)
                    if yb > ya + 1.0:
                        below.append((yb, j, xb))
                for yb, j, xb in sorted(below):
                    if not self._wall_crosses(xa, ya, xb, yb):
                        self._add(i, j, FALL_COST + abs(xb - xa), "fall", (xb, yb))
                        break

    def _join_jumps(self) -> None:
        """A one-way jump up from a lower span to every higher span within one jump
        (rule 5): the higher span sits over the lower one (touching at an end counts)
        or just past its end, within JUMP_SIDE_DIST sideways of it; the rise — over
        the overlap, or between the spans' nearest ends when the higher span sits
        past the end — is at most JUMP_HEIGHT, and the jump costs its height plus
        JUMP_EFFORT plus any sideways drift. The lowest rise on offer is the jump —
        the player walks along the lower span to the best spot before jumping."""
        for i, lo in enumerate(self._spans):
            for j, hi in enumerate(self._spans):
                if i == j:
                    continue
                overlap_lo, overlap_hi = max(lo.x0, hi.x0), min(lo.x1, hi.x1)
                if overlap_lo <= overlap_hi:
                    rise_lo = lo.y_at(overlap_lo) - hi.y_at(overlap_lo)
                    rise_hi = lo.y_at(overlap_hi) - hi.y_at(overlap_hi)
                    # the lowest rise on offer is the jump, and its end of the overlap is
                    # where the player lands (`path`'s point for the higher span)
                    rise, land = (rise_lo, overlap_lo) if rise_lo <= rise_hi else (rise_hi, overlap_hi)
                    drift = 0.0
                else:
                    drift = overlap_lo - overlap_hi
                    if drift > JUMP_SIDE_DIST:
                        continue    # past the drift: no jump lands there (rule 5)
                    near_lo = lo.x1 if hi.x0 > lo.x1 else lo.x0
                    near_hi = hi.x0 if hi.x0 > lo.x1 else hi.x1
                    rise, land = lo.y_at(near_lo) - hi.y_at(near_hi), near_hi
                if 1.0 < rise <= JUMP_HEIGHT:
                    self._add(i, j, JUMP_EFFORT + rise + drift, "jump", (land, hi.y_at(land)))

    # ------------------------------------------------------------ asking

    def _snap(self, point) -> int | None:
        """The span a point stands on (rule 7): the first span at or below the point within
        SNAP_DOWN whose x range covers it (to within FALL_REACH sideways); failing that, the
        nearest span within SNAP_DIST, for a point at the bottom of a map or a little under
        its ground."""
        px, py = float(point[0]), float(point[1])
        below, below_y = None, math.inf
        for j in self._near(px - FALL_REACH, px + FALL_REACH):
            s = self._spans[j]
            xb = max(s.x0, min(s.x1, px))
            if abs(xb - px) > FALL_REACH:
                continue
            yb = s.y_at(xb)
            if py <= yb <= py + SNAP_DOWN and yb < below_y:
                below, below_y = j, yb
        if below is not None:
            return below
        best, best_d = None, SNAP_DIST
        for j in self._near(px - SNAP_DIST, px + SNAP_DIST):
            d = self._spans[j].dist(px, py)
            if d <= best_d and (best is None or d < best_d):
                best, best_d = j, d
        return best

    def platform(self, point) -> int | None:
        """The joined platform (rule 1, `_joined_platforms`) a point in map units stands on, snapped as
        `_snap` snaps it (rule 7); None when the point snaps to no span at all — the ground cannot say
        where it stands. Two points share a platform only when a player walks freely along joined
        fragments between them, never merely because a rope, a fall or a jump joins their spans."""
        snapped = self._snap(point)
        return self._platform_of[snapped] if snapped is not None else None


    def _snap_jump(self, jump) -> tuple[int, int] | None:
        """A jump's (from span, to span), remembered by its end points; None when either end
        snaps to nothing, which leaves that jump out without spoiling the query (rule 6)."""
        key = (tuple(jump.frm), tuple(jump.to))
        if key not in self._snapped:
            frm, to = self._snap(jump.frm), self._snap(jump.to)
            self._snapped[key] = (frm, to) if frm is not None and to is not None else None
        return self._snapped[key]

    def _ways(self, you, target, jumps):
        """One search from `you` to `target`, the single answer behind both `pads` and `path`:
        (the span `you` stands on, the span `target` stands on, how each state was reached,
        what the pad-free way settled at the goal, what the pad-using way settled at it, and
        what the pad-free way settled at, span by span). None when the ground cannot answer:
        either end off the ground, or no way reaching the target at all."""
        if you is None or target is None:
            return None
        start, goal = self._snap(you), self._snap(target)
        if start is None or goal is None:
            return None
        teleports: list[list[tuple[int, object]]] = [[] for _ in self._spans]
        for jump in jumps or []:
            snapped = self._snap_jump(jump)
            if snapped is not None:
                teleports[snapped[0]].append((snapped[1], jump))
        # One Dijkstra over spans in two layers — pad-free, and pad-using (a teleport
        # edge moves a way into the second layer, which keeps every later pad) — by
        # effort alone (see the module docstring): every edge — walk, rope, fall,
        # jump up or teleport — pays its own cost. The first layer settled at the
        # goal prices the band (rule 9): states past it are never pushed, and the
        # search stops as soon as the pad-using layer settles at the goal, so the
        # second layer is only ever walked as far as the tie could still reach.
        best: dict[tuple[int, int], float] = {(start, 0): 0.0}
        came: dict[tuple[int, int], tuple[tuple[int, int], object]] = {}
        queue = [(0.0, 0, start, 0)]
        n = 0
        free: float | None = None
        bound = math.inf
        pad_cost: float | None = None
        # what the pad-free walk has settled at, span by span (rule 10): the cost from
        # `you` to that span with no pad taken, filled in as the first layer settles
        reached: dict[int, float] = {}
        while queue:
            cost, _, here, used = heapq.heappop(queue)
            if cost != best.get((here, used)):
                continue
            if cost > bound:
                break
            if not used:
                reached[here] = cost
            if here == goal:
                if used:
                    pad_cost = cost
                    break
                free = cost
                bound = cost + MODEL_RESOLUTION * cost
                continue
            for nxt, step in self._base[here]:
                key = cost + step
                if key > bound:
                    continue
                state = (nxt, used)
                if state not in best or key < best[state]:
                    best[state], came[state] = key, ((here, used), None)
                    n += 1
                    heapq.heappush(queue, (key, n, nxt, used))
            for nxt, jump in teleports[here]:
                key = cost + TELEPORT_COST
                if key > bound:
                    continue
                state = (nxt, 1)
                if state not in best or key < best[state]:
                    best[state], came[state] = key, ((here, used), jump)
                    n += 1
                    heapq.heappush(queue, (key, n, nxt, 1))
        if free is None and pad_cost is None:
            return None
        return start, goal, came, free, pad_cost, reached

    @staticmethod
    def _chain(came, start: int, goal: int, used: int, whole: bool) -> tuple[list[tuple[int, object]], list]:
        """A way settled by `_ways`, read back out of its search: its teleports in the order
        taken, and — only where `whole` asks for it, since `pads` has no use for it and does
        not pay for it — every span of the way with the teleport that landed on it (None where
        a walk, a rope, a fall or a jump up did), in the order walked. One step per span of the
        way, and nothing at all to a query that never asks for a way back."""
        spans: list[tuple[int, object]] = []
        out: list = []
        at = (goal, used)
        while at != (start, 0):
            came_from, jump = came[at]
            if whole:
                spans.append((at[0], jump))
            if jump is not None:
                out.append(jump)
            at = came_from
        if whole:
            spans.append((start, None))
            spans.reverse()
        out.reverse()
        return spans, out

    def _loops(self, out: list, free: float, reached: dict[int, float]) -> bool:
        """Rule 10: a pad is worth naming only where taking it carries the player forward.
        What remains of the walk from a span is the whole pad-free way less what reaching
        that span pad-free cost — settled in `_ways`' first layer — so a landing the walk
        reaches for no more than the band (rule 9) leaves as much walk as the player already
        faces where they stand: the pad puts them back where they effectively are, and its
        way is the pad-free way with a loop bolted on. No teleport in such a way is worth
        taking. A landing the first layer never settles is past the band and carries the
        player on."""
        band = MODEL_RESOLUTION * free
        for jump in out:
            landed = reached.get(self._snap_jump(jump)[1])
            if landed is not None and landed <= band:
                return True
        return False

    def _taken(self, found, whole: bool) -> tuple[list[tuple[int, object]], list]:
        """The way `pads` names, out of one search's answer: its teleports in the order taken,
        and its spans with the teleport that landed on each where `whole` asks for them (what
        `path` reads). The pad-using way when one settled at the goal — outright cheapest (it
        settled before the pad-free way), the only way there, or within the band (rule 9) —
        and every pad in it carries the player forward (rule 10); else the pad-free way, with
        no pads. Where no pad-free way reaches the goal at all there is nothing to measure the
        pad way against, and it stands."""
        start, goal, came, free, pad_cost, reached = found
        if pad_cost is not None:
            spans, out = self._chain(came, start, goal, 1, whole)
            if free is None or not self._loops(out, free, reached):
                return spans, out
        return self._chain(came, start, goal, 0, whole)[0], []

    def pads(self, you, target, jumps) -> list | None:
        """The hidden teleports the cheapest real walk from `you` to `target` takes, in the
        order taken: the very objects passed in `jumps` (each with `.frm`, `.to` and `.name`,
        all in map units). The cheapest pad-using way is returned when it beats the
        cheapest pad-free way, and also when it only ties it within the model's
        resolution (rule 9) — either way only while every pad in it carries the
        player forward (rule 10); [] when every pad-using way loses by more than
        that, when the cheapest one only lands the player where they already
        effectively stand, or when none reaches at all — no teleport is worth
        taking. None when either end cannot be snapped to the ground, or no walk
        reaches the target at all: the ground cannot answer, and the caller falls
        back to its own heuristic. These are the pads of `path`, which walks the
        very same way."""
        found = self._ways(you, target, jumps)
        return None if found is None else self._taken(found, False)[1]

    def path(self, you, target, jumps) -> list[Step] | None:
        """The way `pads` names, walked step by step: one Step per span the way passes through,
        in the order walked, out of the same single search (`_ways`) that answers `pads`.

        A Step's `at` is where the way meets that span, in map units: where the player stands
        on the first span, where the target lies on the last, and in between where the move
        onto the span lands — a teleport's own landing point (`Jump.to`, the point the map
        draws it landing on), the rope's x at the span's height, the spot a fall or a jump up
        comes down on, the join a walk crosses. `kind` is how the way got there ("walk",
        "fall", "rope", "jump" or "pad"; the first span's is a "walk", nothing having got the
        player there), and `name` is the teleport's name on a "pad" step, "" on every other.

        The "pad" steps carry exactly `pads`' teleports, in the same order. None exactly when
        `pads` returns None — the ground cannot answer — and never []: a way with no pad in it
        still has a path, and a player standing where they are going has one step."""
        found = self._ways(you, target, jumps)
        if found is None:
            return None
        chain = self._taken(found, True)[0]
        last = len(chain) - 1
        steps: list[Step] = []
        for n, (span, jump) in enumerate(chain):
            if n == 0:
                kind, name, at = "walk", "", self._spans[span].closest(float(you[0]), float(you[1]))
            elif jump is not None:
                kind, name, at = "pad", jump.name, (float(jump.to[0]), float(jump.to[1]))
            else:
                _, kind, at = self._edges[chain[n - 1][0]][span]
                name = ""
            if n == last:
                at = self._spans[span].closest(float(target[0]), float(target[1]))
            steps.append(Step(at, kind, name))
        return steps
