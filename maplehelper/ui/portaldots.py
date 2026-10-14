"""Blue dots on the game's own minimap where the map's invisible teleports are (press-up and touch portals the game
never draws), a green ring around the NPC the player asked to be guided to (ui/npcoverlay.py), and an orange arrow
pointing down at the next portal or NPC on the way to the map the player picked a route to (LOCATION.route_dest): a
click-through window laid over the minimap's box (LOCATION.box: the game's minimap window found at its top left, else
the box the player drew), and moved with it. The map comes from each minimap read
(ui/location.LOCATION.here), where its picture lies in the box from the fast follow between reads (LOCATION.follow:
the marks move with the minimap's scroll, and go the moment the picture stops matching, a teleport or the loading
screen). Hidden whenever there is nothing to place (no box, no read, a picture that doesn't match); the portal dots
also need their setting, the ring only a guide on the player's own map, and the arrow its setting
(minimap_route_arrow) and a way known from the player's map to another one, its first step on this minimap."""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .. import routes
from ..kb import KnowledgeBase
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


def _name(graph, mid: str) -> str:
    """A map's name for the log; its id when the graph doesn't know it."""
    try:
        return graph.name(mid)
    except Exception:  # noqa: BLE001 - a log line must never break a redraw
        return mid


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
        self._arrow: QPointF | None = None    # the route's next step (its portal or NPC), once the follow places it
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
        # setting and a way from this map with a first step on its minimap
        spots = graph.hidden_spots(here.map) if self._settings["minimap_hidden_portals"] else []
        at = [p for p in (view.at(s) for s in spots) if p is not None]
        guide = LOCATION.guide
        at_ring = view.at(guide[1]) if guide is not None and guide[0] == here.map else None
        step = self._next_step(graph, here.map)
        at_arrow = view.at(step) if step is not None else None
        self._say_arrow(step, at_arrow)
        if not at and at_ring is None and at_arrow is None:
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
        self._arrow = QPointF(at_arrow[0] / ratio, at_arrow[1] / ratio) if at_arrow is not None else None
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

    def _say_arrow(self, step: tuple[float, float] | None, at_arrow: tuple[float, float] | None) -> None:
        """One line in the log whenever the arrow starts or stops being placed on the minimap shown (the way's next
        step can be off the part of the map the window shows): a player's report says which it was, and nothing is
        logged while no route is picked."""
        if step is None:
            self._arrow_said = None
            return
        said = (self._arrow_key, at_arrow is not None)
        if said != self._arrow_said:
            self._arrow_said = said
            log.info("route arrow: %s", "on the minimap" if at_arrow is not None
                     else "its next step is off the part of the minimap shown")

    def _clear(self) -> None:
        self._dots = []
        self._ring = None
        self._arrow = None
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
            p.drawPolygon(QPolygonF([self._arrow + QPointF(x / self._ratio, y / self._ratio) for x, y in ARROW_PX]))
        p.end()
