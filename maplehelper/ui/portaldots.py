"""Blue dots on the game's own minimap where the map's invisible teleports are (press-up and touch portals the game
never draws), a green ring around the NPC the player asked to be guided to (ui/npcoverlay.py), and an orange arrow
pointing down at the next portal or NPC on the way to the map the player picked a route to (LOCATION.route_dest), or,
while that step is off the part of the map the minimap shows (it often shows only part), a bigger one just inside
the edge of the part shown, pointing toward the step: a click-through window laid over the minimap's box
(LOCATION.box: the game's minimap window found at its top left, else the box the player drew), and moved with it.
The map comes from each minimap read (ui/location.LOCATION.here), where its picture lies in the box from the fast
follow between reads (LOCATION.follow: the marks move with the minimap's scroll, and go the moment the picture stops
matching, a teleport or the loading screen). Hidden whenever there is nothing to place (no box, no read, a picture
that doesn't match); the portal dots also need their setting, the ring only a guide on the player's own map, and the
arrow its setting (minimap_route_arrow) and a way known from the player's map to another one, its first step on this
map's minimap picture."""
from __future__ import annotations

import logging
import math
import sys
from typing import NamedTuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QWidget

from .. import routes
from ..kb import KnowledgeBase
from ..minimap import View
from ..store import Settings
from . import theme
from .location import LOCATION
from .npcoverlay import keep_over_game, set_capturable
from .regionpick import from_capture

log = logging.getLogger("maplehelper")

DOT_PX = 7                          # the dot's width in screen pixels: a little smaller than the player's own dot,
                                    # so standing on one still shows its yellow around it
FILL = QColor(40, 130, 255)
OUTLINE = QColor(10, 20, 45)        # the dark rim the game gives its own dots
RING_PX = 7                         # the guided NPC's ring radius: wider than the dots, so it reads as the target
RING_PEN = 2.0                      # the green stroke's width, the dark rim drawn a little wider under it
RING_FILL = QColor(theme.GOOD_TEXT_LIGHT)   # the NPC green, as the map windows dot an NPC (mapview._mark_colors)
RING_RIM = QColor(8, 48, 24)        # its dark rim (mapview's), so the ring holds on any minimap
ARROW_FILL = QColor(245, 182, 66)   # the next step's orange, as the map windows mark a portal (mapview._mark_colors)
ARROW_RIM = QColor(58, 42, 5)       # its dark rim (mapview's), so the arrow holds on any minimap
# the route's arrow, in screen pixels from its step's spot: the tip there, the head 14 px wide, the shaft up to 15 px
# above it, pointing down at the step's portal or NPC
ARROW_PX = ((0, 1), (-7, -7), (-3, -7), (-3, -15), (3, -15), (3, -7), (7, -7))
# the arrow while the step is off the part of the map the minimap shows, in screen pixels from its tip: a sign at the
# panel's edge rather than a mark on a spot, so longer and bolder (22 px, the head 18 px wide, the shaft 8), drawn
# here pointing down and turned about its tip toward the step (_aim)
EDGE_ARROW_PX = ((0, 0), (-9, -10), (-4, -10), (-4, -22), (4, -22), (4, -10), (9, -10))
EDGE_GAP_PX = 3     # how far inside the panel's edge all of it stays: its dark rim whole, a sliver of map off the frame


def _name(graph, mid: str) -> str:
    """A map's name for the log; its id when the graph doesn't know it."""
    try:
        return graph.name(mid)
    except Exception:  # noqa: BLE001 - a log line must never break a redraw
        return mid


class _Aim(NamedTuple):
    """Where the route's arrow goes (_aim), in box pixels: the step's spot for ARROW_PX, the tip for EDGE_ARROW_PX."""
    x: float
    y: float
    angle: float    # the degrees it turns clockwise from pointing down, about that point: 0 as the shapes are drawn
    edge: bool      # the step is off the part shown, and the arrow points toward it from the panel's edge


def _box_px(view: View, spot: tuple[float, float]) -> tuple[float, float]:
    """A spot on the map's picture (fractions of its size, as routes.Leg.spot) in box pixels, shown or not: View.at
    without its check that the panel shows it."""
    return view.x + spot[0] * view.w, view.y + spot[1] * view.h


def _inset(lo: float, hi: float) -> tuple[float, float]:
    """A span with EDGE_GAP_PX taken off each end; just its middle when too short for that."""
    lo, hi = lo + EDGE_GAP_PX, hi - EDGE_GAP_PX
    return (lo, hi) if lo <= hi else ((lo + hi) / 2, (lo + hi) / 2)


def _aim(view: View, step: tuple[float, float], spot: tuple[float, float] | None) -> _Aim:
    """The route's arrow for its next step (a spot on the map's picture): on the step itself, pointing down, when
    the window shows it. Else the step is off the part of the map shown (the game's minimap often shows only part:
    Kerning City's way to Henesys starts at its far left, left of the panel, live), and the arrow sits at the
    panel's edge, on the line from the player's dot (`spot`, the read's; the panel's middle when the read saw none
    or the window doesn't show it) toward the step, turned to point out along it, its tip pulled in just far enough
    that all of it, head and shaft, stays inside the panel whichever way it turns."""
    on = view.at(step)
    if on is not None:
        return _Aim(on[0], on[1], 0.0, False)
    x0, y0, x1, y1 = view.panel
    me = view.at(spot) if spot is not None else None
    ox, oy = me if me is not None else ((x0 + x1) / 2, (y0 + y1) / 2)
    bx, by = _box_px(view, step)
    dx, dy = bx - ox, by - oy
    # the line's own angle less down's (90: y grows down the screen), the turn from pointing down
    angle = (math.degrees(math.atan2(dy, dx)) - 90.0) % 360.0
    # where the tip may go: the panel less how far the arrow, turned so, reaches past its tip on each side
    reach = QTransform().rotate(angle).map(QPolygonF([QPointF(x, y) for x, y in EDGE_ARROW_PX])).boundingRect()
    lo_x, hi_x = _inset(x0 - reach.left(), x1 - reach.right())
    lo_y, hi_y = _inset(y0 - reach.top(), y1 - reach.bottom())
    # from the player's dot (moved in there when nearer the edge) along the line toward the step, as far as it goes
    ox, oy = min(max(ox, lo_x), hi_x), min(max(oy, lo_y), hi_y)
    ends = [((hi_x if dx > 0 else lo_x) - ox) / dx] if dx else []
    if dy:
        ends.append(((hi_y if dy > 0 else lo_y) - oy) / dy)
    t = min(ends, default=0.0)
    return _Aim(min(max(ox + t * dx, lo_x), hi_x), min(max(oy + t * dy, lo_y), hi_y), angle, True)


class PortalDots(QWidget):
    """The dots', the guided NPC's ring's and the route's arrow's window over the minimap box. Never takes a click,
    the focus, or a place in the minimap reads."""

    def __init__(self, kb: KnowledgeBase, settings: Settings):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_over_game(self)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._kb = kb
        self._settings = settings
        self._dots: list[QPointF] = []
        self._ring: QPointF | None = None     # the guided NPC, once the follow places it
        # the route's arrow, once the follow places it (_aim): its next step's portal or NPC (or, that off the part
        # shown, its tip at the panel's edge), the degrees it turns clockwise from pointing down, and which it is
        self._arrow: QPointF | None = None
        self._arrow_angle = 0.0
        self._arrow_edge = False
        # the way _next_step last routed, (player's map, route's map, cabs & teleports), and its first step's spot
        self._arrow_key: tuple[str, str, bool] | None = None
        self._arrow_spot: tuple[float, float] | None = None
        self._arrow_said: tuple | None = None   # what the log last said about the arrow's placing (_say_arrow)
        self._ratio = 1.0
        LOCATION.changed.connect(self.refresh)
        LOCATION.followed.connect(self.refresh)
        LOCATION.guided.connect(self.refresh)
        LOCATION.routed.connect(self.refresh)     # a route picked to another map, or stopped: the arrow follows
        LOCATION.boxed.connect(self.refresh)      # the minimap window found elsewhere (or another size): over it

    def set_kb(self, kb: KnowledgeBase) -> None:
        self._kb = kb
        self._arrow_key = None      # another KB, another graph: the arrow's way is routed again
        self.refresh()

    def refresh(self, _what: object = None) -> None:
        """Place the dots, the guided NPC's ring and the route's arrow over LOCATION.box from the live follow of the
        player's map (a Qt slot too: LOCATION's signals carry what it re-reads). Never from a read's own view: it can
        be the last map's while the reads wait to confirm a new one, and entering a shop flashed the street's dots
        back for a second (live)."""
        region = LOCATION.box
        here = LOCATION.here
        if not isinstance(region, dict) or here is None:
            self._clear()
            return
        follow = LOCATION.follow
        # none, or one of another map (the box shows that one now, not the player's known map): nothing to place
        view = follow[1] if follow is not None and follow[0] == here.map else None
        if view is None:
            self._clear()
            return
        graph = routes.of(self._kb)
        # the portal dots need their setting; the ring, only a guide for the map the player is on; the arrow, its
        # setting and a way from this map with a first step on its minimap (shown, or pointed at from the edge)
        spots = graph.hidden_spots(here.map) if self._settings["minimap_hidden_portals"] else []
        at = [p for p in (view.at(s) for s in spots) if p is not None]
        guide = LOCATION.guide
        at_ring = view.at(guide[1]) if guide is not None and guide[0] == here.map else None
        step = self._next_step(graph, here.map)
        aim = _aim(view, step, here.spot) if step is not None else None
        self._say_arrow(aim)
        if not at and at_ring is None and aim is None:
            self._clear()
            return
        screens = [(s.geometry(), s.devicePixelRatio()) for s in QGuiApplication.screens()]
        try:
            rect, ratio = from_capture(region, screens, scale=sys.platform != "darwin")
        except (KeyError, TypeError, ValueError):
            self._clear()
            return
        self._ratio = ratio
        self._dots = [QPointF(x / ratio, y / ratio) for x, y in at]
        self._ring = QPointF(at_ring[0] / ratio, at_ring[1] / ratio) if at_ring is not None else None
        self._arrow = QPointF(aim.x / ratio, aim.y / ratio) if aim is not None else None
        self._arrow_angle, self._arrow_edge = (aim.angle, aim.edge) if aim is not None else (0.0, False)
        if self.geometry() != rect:
            self.setGeometry(rect)
        if not self.isVisible():
            self.show()
            set_capturable(self, self._settings)     # off the minimap reads' shots, unless the player asked
        self.update()

    def _next_step(self, graph, here_map: str) -> tuple[float, float] | None:
        """Where the way to the map the player picked (LOCATION.route_dest) starts on their map's minimap picture: its
        first step's portal or NPC (routes.Leg.spot). The way on foot, or with cabs and NPC teleports when the
        toolbar's switch says so (settings["game_rides"]), as the search's page and the ◎ window draw it. None with
        the arrow's setting off, no route picked or already on its map, no way known, or a first step with no spot
        on the minimap. Routed only when the player's map, the route's map or the switch changes, the step's spot
        kept for the refreshes after (set_kb forgets it): refresh runs on the GUI thread for every follow frame while
        the minimap scrolls, and Graph.route is a Dijkstra search over the whole map graph."""
        dest = LOCATION.route_dest
        if not self._settings["minimap_route_arrow"] or not dest or dest == here_map:
            return None
        try:
            rides = bool(self._settings["game_rides"])
        except (KeyError, TypeError):
            rides = False
        key = (here_map, dest, rides)
        if key != self._arrow_key:
            route = getattr(graph, "route", None)     # a stand-in graph that can't route (an older test's): no arrow
            way = route(here_map, dest, taxi=rides, teleport=rides) if route is not None else None
            leg = way.legs[0] if way is not None and way.legs else None
            self._arrow_key, self._arrow_spot = key, leg.spot if leg is not None else None
            self._arrow_said = None
            log.info("route arrow: to %s, %s", _name(graph, dest),
                     f"next step: {getattr(leg, 'kind', '')} {getattr(leg, 'via', '')}".strip()
                     if leg is not None and leg.spot is not None
                     else "its first step has no spot on this minimap" if leg is not None
                     else "no way known from here")
        return self._arrow_spot

    def _say_arrow(self, aim: _Aim | None) -> None:
        """One line in the log whenever the arrow moves between its step and the panel's edge (the way's next step
        can be off the part of the map the window shows), and for each new way: a player's report says where it
        was, and nothing is logged while no route is picked."""
        if aim is None:
            self._arrow_said = None
            return
        said = (self._arrow_key, aim.edge)
        if said != self._arrow_said:
            self._arrow_said = said
            log.info("route arrow: %s", "pointing from the edge: its next step is off the part shown" if aim.edge
                     else "on the minimap")

    def _clear(self) -> None:
        self._dots = []
        self._ring = None
        self._arrow = None
        self._arrow_angle = 0.0
        self._arrow_edge = False
        if self.isVisible():
            self.hide()

    def paintEvent(self, e) -> None:
        if not self._dots and self._ring is None and self._arrow is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(OUTLINE, 1.0 / self._ratio))
        p.setBrush(FILL)
        r = DOT_PX / 2 / self._ratio
        for c in self._dots:
            p.drawEllipse(c, r, r)
        if self._ring is not None:
            rr = RING_PX / self._ratio
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(RING_RIM, (RING_PEN + 2.0) / self._ratio))
            p.drawEllipse(self._ring, rr, rr)
            p.setPen(QPen(RING_FILL, RING_PEN / self._ratio))
            p.drawEllipse(self._ring, rr, rr)
        if self._arrow is not None:
            p.setPen(QPen(ARROW_RIM, 1.0 / self._ratio))
            p.setBrush(ARROW_FILL)
            shape = QPolygonF([QPointF(x / self._ratio, y / self._ratio)
                               for x, y in (EDGE_ARROW_PX if self._arrow_edge else ARROW_PX)])
            # turned about its own origin (the step's spot, the edge arrow's tip): 0 leaves the mark pointing down
            p.drawPolygon(QTransform().rotate(self._arrow_angle).map(shape).translated(self._arrow))
        p.end()
