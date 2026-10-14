"""Which hidden teleports to take across one map, worked out from its real ground.

`routes.Graph.shortcut_path` used to score pads by the straight line between two spots on the
minimap picture. On a platform maze that line is a lie: the player cannot walk it, and the pads
are how the map is crossed at all. This module is the honest version. Given a map's footholds
and ropes (NiaMeowDB's terrain for the map, stored in the KB's terrain.json) and the map's
hidden teleports, `Walk.pads` names the teleports the cheapest real walk uses, in order.

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
   end and 2 below Utah's span at y=-805 at its top: solid contact at both ends. Climbing
   costs the vertical distance between the two spans.
4. Falling. From a few probe points along a span the player drops onto the first span
   below (greater y) whose ground is within FALL_REACH sideways and whose drop no wall
   (rule 2) crosses. Falling is one way and nearly free. Probing, rather than solving
   every drop line exactly, is the one deliberate simplification: a lower span that only
   ever passes under a span between two probes is missed, and in a map of hundreds of
   spans that has not been seen to matter.
5. Jumping up. A character jumps: from anywhere along a lower span they can land on a
   higher span that sits over it — the higher span's x range must overlap the lower one's
   (touching at an end counts: that is a ledge whose foot is the lower span's end) — and
   that is at most JUMP_HEIGHT above it over that overlap, so a lower span joins (one way,
   upward only) every higher span that sits over it within one jump. A span merely near
   above, offset sideways past the lower span's end, is not a jump: the character cannot
   drift sideways onto ground that is not over where they jumped from. The height is
   measured from the map, not assumed: on Utah's Pig Farm, joining fragments into
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
   itself, and a long ladder of jumps loses to a pad that skips the ladder.
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

`pads` returns the teleports on the cheapest walk, in the order taken: effort, not
pad-count, decides. Walking into a span costs its horizontal length, a rope the height
climbed, a fall a flat FALL_COST, a jump its height plus JUMP_EFFORT, and a teleport a
flat TELEPORT_COST — about nothing, since the teleport itself is instant, but not zero,
so a pad that only ties a walk or a fall is not named for it. [] is returned only when
that cheapest walk uses no teleport at all: a pad is named exactly when it makes the
way cheaper than walking, climbing, falling and jumping do without it, however many
jumps that walk takes. Within a span the exact entry and exit points are not tracked,
so costs are map-unit estimates good enough to order ways, not exact distances.

Cost, by counting rather than by benchmark: the model is built once per map (`Walk.of`).
Utah's Pig Farm, among the largest maps, gives 355 spans, 297 walls and 11 ropes; the
walls sit in the same x-bin index as the spans, so each join or fall probe tests the few
walls in its neighbourhood rather than scanning them all. Joining, rope, fall and jump
edges are a few per span (the jump pass compares every pair of spans — some 126k pairs —
but keeps only the few that come within a jump of each other), so a query's Dijkstra
search visits a few hundred nodes and relaxes a few thousand edges, and jump ends are
snapped once and remembered by their points.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

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
# how high (map units) a character can jump onto a span above (rule 5): one platform tier —
# the nearest overlapping higher platform on Utah's Pig Farm is 57–68 up, the next tiers
# 120 and more, so 70 climbs one tier and never two (see rule 5)
JUMP_HEIGHT = 70.0
# the fixed effort of one jump up, on top of its height (rule 5): a jump is slow to line
# up and land, so one tier's jump costs some 320 all-in — a ladder of them loses to a pad
JUMP_EFFORT = 250.0
# what a hidden teleport costs: about nothing (it is instant), but not nothing, so a
# pad that only ties a walk or a fall is not named for it
TELEPORT_COST = 5.0
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


class Walk:
    """One map's walkable ground, built once (`Walk.of`) and asked per query (`pads`)."""

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
        edges: list[dict[int, float]] = [dict() for _ in self._spans]
        self._edges = edges
        self._join_fragments()
        self._join_ropes(lr or [])
        self._join_falls()
        self._join_jumps()
        self._base = [sorted(e.items()) for e in edges]
        self._snapped: dict[tuple, tuple[int, int] | None] = {}

    @classmethod
    def of(cls, fh, lr) -> "Walk":
        """The walk model of one map's ground: its `fh` footholds and `lr` ropes (terrain.json)."""
        return cls(fh, lr)

    # ------------------------------------------------------------ building

    def _add(self, i: int, j: int, cost: float, both: bool = True) -> None:
        if i == j:
            return
        if cost < self._edges[i].get(j, math.inf):
            self._edges[i][j] = cost
        if both and cost < self._edges[j].get(i, math.inf):
            self._edges[j][i] = cost

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
                    self._add(i, j, self._spans[j].width, both=False)
                    self._add(j, i, s.width, both=False)

    def _join_ropes(self, lr) -> None:
        """Every span a rope crosses, ends near, or passes beside joins every other, both
        ways (rule 3), at the cost of the height between them at the rope's x."""
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
                    joined.append((i, y))    # crossed, or within a jump past an end
                elif side <= ROPE_SIDE_DIST and top <= y <= bottom:
                    joined.append((i, y))    # passed beside, between the ends: a jump on or off sideways
            for a, (i, yi) in enumerate(joined):
                for j, yj in joined[a + 1:]:
                    self._add(i, j, abs(yi - yj) + 1.0)

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
                        self._add(i, j, FALL_COST + abs(xb - xa), both=False)
                        break

    def _join_jumps(self) -> None:
        """A one-way jump up from a lower span to every higher span that sits over it
        within one jump (rule 5): the higher span's x range overlaps the lower one's
        (touching at an end counts), the rise over that overlap is at most JUMP_HEIGHT,
        and the jump costs its height plus JUMP_EFFORT. The lowest rise over the overlap
        is the jump on offer — the player walks along the lower span to the best spot
        before jumping."""
        for i, lo in enumerate(self._spans):
            for j, hi in enumerate(self._spans):
                if i == j:
                    continue
                overlap_lo, overlap_hi = max(lo.x0, hi.x0), min(lo.x1, hi.x1)
                if overlap_lo > overlap_hi:
                    continue        # not over the lower span: no jump lands there (rule 5)
                rise = min(lo.y_at(overlap_lo) - hi.y_at(overlap_lo),
                           lo.y_at(overlap_hi) - hi.y_at(overlap_hi))
                if 1.0 < rise <= JUMP_HEIGHT:
                    self._add(i, j, JUMP_EFFORT + rise, both=False)

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

    def _snap_jump(self, jump) -> tuple[int, int] | None:
        """A jump's (from span, to span), remembered by its end points; None when either end
        snaps to nothing, which leaves that jump out without spoiling the query (rule 6)."""
        key = (tuple(jump.frm), tuple(jump.to))
        if key not in self._snapped:
            frm, to = self._snap(jump.frm), self._snap(jump.to)
            self._snapped[key] = (frm, to) if frm is not None and to is not None else None
        return self._snapped[key]

    def pads(self, you, target, jumps) -> list | None:
        """The hidden teleports the cheapest real walk from `you` to `target` takes, in the
        order taken: the very objects passed in `jumps` (each with `.frm`, `.to` and `.name`,
        all in map units). [] when the cheapest walk, climb, fall and jump there uses no
        teleport at all. None when either end cannot be snapped to the ground, or no walk
        reaches the target at all: the ground cannot answer, and the caller falls back to
        its own heuristic."""
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
        # Dijkstra over spans by effort alone (see the module docstring): every edge —
        # walk, rope, fall, jump up or teleport — pays its own cost, and the teleports
        # on the cheapest path are the answer, so a pad is named only when it beats
        # every pad-free way, and a long climb of jumps can lose to a pad that skips it
        best: dict[int, float] = {start: 0.0}
        came: dict[int, tuple[int, object]] = {}
        queue = [(0.0, 0, start)]
        n = 0
        while queue:
            cost, _, here = heapq.heappop(queue)
            if cost != best.get(here):
                continue
            if here == goal:
                break
            for nxt, step in self._base[here]:
                key = cost + step
                if nxt not in best or key < best[nxt]:
                    best[nxt], came[nxt] = key, (here, None)
                    n += 1
                    heapq.heappush(queue, (key, n, nxt))
            for nxt, jump in teleports[here]:
                key = cost + TELEPORT_COST
                if nxt not in best or key < best[nxt]:
                    best[nxt], came[nxt] = key, (here, jump)
                    n += 1
                    heapq.heappush(queue, (key, n, nxt))
        if goal not in best:
            return None
        out, at = [], goal
        while at != start:
            at, jump = came[at][0], came[at][1]
            if jump is not None:
                out.append(jump)
        return out[::-1]
