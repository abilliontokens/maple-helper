"""Blue dots on the game's own minimap where the map's invisible teleports are (press-up and touch portals the game
never draws), a green ring around the NPC the player asked to be guided to (LOCATION.guide: ui/npcoverlay.py, the
search's NPC page) with a green arrow pointing down at it, and an arrow pointing down at the next portal or NPC on
the way to the map the player picked a route to (LOCATION.route_dest). The minimap often shows only part of the map:
an NPC or a step off the part shown gets a bigger arrow just inside the edge of the part shown instead, pointing
toward it (the NPC no ring then). All of it on a click-through window laid over the minimap's box (LOCATION.box: the
game's minimap window found at its top left, else the box the player drew), and moved with it. The map comes from each
minimap read (ui/location.LOCATION.here), where its picture lies in the box from the fast follow between reads
(LOCATION.follow: the marks move with the minimap's scroll, and go the moment the picture stops matching, a teleport
or the loading screen). Hidden whenever there is nothing to place (no box, no read, a picture that doesn't match);
the portal dots also need their setting, the ring only a guide on the player's own map, the NPC's arrow that guide
and the arrows' setting (minimap_route_arrow), and the route's arrow that setting and a way known from the player's
map to another one, its first step on this map's minimap picture. The arrows look as the bar's ⚙ panel picks, read at
every refresh: the route's colour (minimap_arrow_color, a name in ARROW_COLORS: orange unless another is picked; the
NPC's is the ring's green whatever is picked, so it reads as the NPC and never as the route's step), their size
(minimap_arrow_size: the length in screen pixels, from ARROW_SIZE_MIN to ARROW_SIZE_MAX, both shapes scaled alike),
how solid they are drawn (minimap_arrow_opacity: ARROW_OPACITY_MIN to 1.0, the names beside them and the strip under
the box faded with them, so the way can be left showing over a minimap it would otherwise cover; the dots and the
ring stay solid), a small name beside each saying what to click there (minimap_arrow_label, in the app's language:
the map the route's portal leads to, or the NPC to talk to for a cab, a boat or an NPC's trip; the guided NPC's own
name, as the KB has it; on a pill in its arrow's colours, its letters sized with the arrow, just above the mark's
shaft or inward of the sign at the edge, all of it inside the panel) and whether they blink (minimap_arrow_flash:
both hidden and shown again together every FLASH_MS, their names with them, to catch the eye on a busy minimap; the
dots and the ring never blink). Both at once (a guide here while the route leads elsewhere): the NPC's is drawn
over the route's.

Under the minimap box, outside the game's own picture, a strip says where the player is heading and how many maps
are still to go (minimap_route_steps: the map they picked by name, then arrow_maps_left, arrow_maps_left_one on the
last one), and on the read after a wrong portal that the way was worked out again from where they stand
(route_off_track). It is drawn small, in the route's arrow's own colours on its dark rim, so it reads over whatever
the game draws under its minimap, and it blinks with the arrows when they blink: it is the route arrow's own word,
and a strip left steady beside a blinking arrow would read as something else's. The window grows down by exactly
the strip's height and keeps its top-left, so every mark over the box — the dots, the ring, the arrows — lands where
it did; a minimap at the foot of its screen puts the strip above the box instead, the window growing up and the marks
drawn that much down, which leaves them over the box just the same. Nothing to say draws nothing and grows nothing:
the switch off, no route armed, or the player already there. The count comes from LOCATION.journey, the way from the
player's CURRENT map to the map they picked: this window works it out (journey.of) where it works out the arrow's
own step and publishes it (LOCATION.set_journey), once for a map, a destination and the switches and never for a
follow frame, and clears it whenever the arrow guides nothing.

Guiding the whole way (minimap_route_follow, on unless it is turned off) decides what happens once the player
leaves the map the arrow was armed on: on, the map they picked stands and the way is worked out afresh from
wherever they are, map after map, which is what the journey gives; off, the arrow guides only on the map it was
armed from and goes quiet the moment they leave it."""
from __future__ import annotations

import logging
import math
import sys
from typing import NamedTuple

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QWidget

from .. import bidi, journey, routes
from ..i18n import I18n
from ..kb import KnowledgeBase
from ..minimap import Here, View
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
RING_RIM = QColor(8, 48, 24)        # its dark rim (mapview's), so the ring holds on any minimap; the guided NPC's
                                    # arrow and its name's pill take these two too, whatever colour the route's is in
# the route's arrow's colours, by the name its setting keeps (minimap_arrow_color), as the bar's ⚙ panel offers them:
# the name's i18n key, the fill, and the dark rim that holds it on any minimap. Orange, the default, is the next
# step's as the map windows mark a portal (mapview._mark_colors); the others are bright shades of the accents
# (theme.ACCENTS), each on its own dark rim
ARROW_COLORS = {"green": ("tbs_accent_green", "#4CD07D", "#083018"),
                "blue": ("tbs_accent_blue", "#64B5FF", "#082138"),
                "purple": ("tbs_accent_purple", "#A98BFF", "#180C2C"),
                "orange": ("tbs_accent_orange", "#F5B642", "#3A2A05"),
                "pink": ("tbs_accent_pink", "#FF7EB6", "#2F081A"),
                "teal": ("tbs_accent_teal", "#3FD9CF", "#062623")}
ARROW_SIZE_MIN, ARROW_SIZE_MAX = 12, 40     # the arrow's length its size setting may pick, in screen pixels
ARROW_SIZE_PX = 22      # how long the shapes below are drawn (the default size): a size scales them by size / this
# how solid the route's and the guided NPC's arrows, the names beside them and the strip under the box are drawn
# (minimap_arrow_opacity): 1.0 as they always were, down to ARROW_OPACITY_MIN, where the game's own minimap still
# reads through them. The hidden portals' blue dots and the guided NPC's ring are never faded, as they are never
# blinked: they mark the map itself, not the way
ARROW_OPACITY_MIN, ARROW_OPACITY = 0.2, 1.0
# an arrow on its spot (the route's next step's portal or NPC, or the guided NPC), in screen pixels from it: the tip
# there, the head 14 px wide, the shaft up to 15 px above it, pointing down at it
ARROW_PX = ((0, 1), (-7, -7), (-3, -7), (-3, -15), (3, -15), (3, -7), (7, -7))
# an arrow while its spot is off the part of the map the minimap shows, in screen pixels from its tip: a sign at the
# panel's edge rather than a mark on a spot, so longer and bolder (22 px, the head 18 px wide, the shaft 8), drawn
# here pointing down and turned about its tip toward the spot (_aim). Both shapes are at the default size, drawn
# scaled about their origin (the spot, the tip) to the size the setting picks (_size_scale)
EDGE_ARROW_PX = ((0, 0), (-9, -10), (-4, -10), (-4, -22), (4, -22), (4, -10), (9, -10))
EDGE_GAP_PX = 3     # how far inside the panel's edge all of it stays: its dark rim whole, a sliver of map off the frame
FLASH_MS = 550      # the arrows' blink, with their flash setting on: shown this long, then hidden as long
# the name beside an arrow (minimap_arrow_label), saying what to click there, on a pill in its colours
TAG_FONT_K, TAG_FONT_MIN_PX = 0.45, 9   # its letters' size: this much of the arrow's length, never under 9 px
TAG_CHARS = 18                  # a name longer than this many characters is cut short with "…" to about their width
TAG_PAD_X, TAG_PAD_Y = 0.5, 0.1     # the pill's room around its words, across and above/below, in its letters' size
TAG_ALPHA = 0.85                # how opaque the pill's fill (the arrow's rim) is, the minimap a touch through it
TAG_GAP_PX = 2                  # how far clear of the arrow it stays, in screen pixels
# the strip under the minimap box (minimap_route_steps, _make_strip): where the player is heading and how many maps
# are still to go, in the route arrow's own colours on its dark rim, outside the game's picture
STRIP_FONT_PX = 11          # its letters in screen pixels: small, and the same whatever size the arrows are set
                            # to, so how far the window grows below the box never moves with another setting
STRIP_PAD_X, STRIP_PAD_Y = 0.6, 0.25    # its backing's room around the words, across and above/below, in letters
STRIP_ALPHA = 0.92          # how opaque that backing is: the game draws its own panels under the minimap, and the
                            # words must read over whatever is there
STRIP_SEP = " · "           # between the map the player is heading to and how many maps are still to go

def _name(graph, mid: str) -> str:
    """A map's name for the log and the name beside the arrow; its id when the graph doesn't know it."""
    try:
        return graph.name(mid)
    except Exception:  # noqa: BLE001 - a log line or the arrow's name must never break a redraw
        return mid


class _Aim(NamedTuple):
    """Where an arrow goes (_aim), in box pixels: on its spot for ARROW_PX, the tip for EDGE_ARROW_PX."""
    x: float
    y: float
    angle: float    # the degrees it turns clockwise from pointing down, about that point: 0 as the shapes are drawn
    edge: bool      # the spot is off the part shown, and the arrow points toward it from the panel's edge


class _Tag(NamedTuple):
    """The name beside an arrow (PortalDots._make_tag), in the window's pixels."""
    text: str       # what it says: its glyph and the name, cut short and kept one block (bidi.ltr_block)
    rect: QRectF    # its pill (_tag_rect)
    font: QFont
    rtl: bool       # its language reads right to left (Hebrew): its words laid out so


class _Strip(NamedTuple):
    """The strip under (or over) the minimap box (PortalDots._make_strip), in the window's pixels."""
    text: str       # the map the player is heading to and how many maps are still to go (STRIP_SEP between them)
    rect: QRectF    # its dark backing, as wide as the words need and never wider than the box
    font: QFont
    rtl: bool       # its language reads right to left (Hebrew): its words laid out so



def _box_px(view: View, spot: tuple[float, float]) -> tuple[float, float]:
    """A spot on the map's picture (fractions of its size, as routes.Leg.spot) in box pixels, shown or not: View.at
    without its check that the panel shows it."""
    return view.x + spot[0] * view.w, view.y + spot[1] * view.h


def _inset(lo: float, hi: float) -> tuple[float, float]:
    """A span with EDGE_GAP_PX taken off each end; just its middle when too short for that."""
    lo, hi = lo + EDGE_GAP_PX, hi - EDGE_GAP_PX
    return (lo, hi) if lo <= hi else ((lo + hi) / 2, (lo + hi) / 2)


def _arrow_colors(settings) -> tuple[QColor, QColor]:
    """The arrow's fill and rim in the colour its setting names (ARROW_COLORS); orange's for a name it doesn't know."""
    name = settings["minimap_arrow_color"]
    entry = ARROW_COLORS.get(name) if isinstance(name, str) else None
    _, fill, rim = entry if entry is not None else ARROW_COLORS["orange"]
    return QColor(fill), QColor(rim)


def _size_scale(settings) -> float:
    """How many times its drawn size (ARROW_PX, EDGE_ARROW_PX: ARROW_SIZE_PX long) the arrow's size setting makes
    it: the length kept within ARROW_SIZE_MIN..ARROW_SIZE_MAX, and the drawn size for a setting holding no number
    (an old or hand-edited settings file)."""
    size = settings["minimap_arrow_size"]
    if isinstance(size, bool) or not isinstance(size, (int, float)) or size != size:     # size != size: NaN
        size = ARROW_SIZE_PX
    return min(max(size, ARROW_SIZE_MIN), ARROW_SIZE_MAX) / ARROW_SIZE_PX


def _opacity(settings) -> float:
    """How solid the arrows, the names beside them and the strip under the box are drawn (the player's
    minimap_arrow_opacity), kept within ARROW_OPACITY_MIN..ARROW_OPACITY; solid for a settings file that has no
    number there (an old one, or a hand-edited one), as they were drawn before the setting existed."""
    try:
        value = settings["minimap_arrow_opacity"]
    except (KeyError, TypeError):
        return ARROW_OPACITY
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:   # value != value: NaN
        return ARROW_OPACITY
    return min(max(float(value), ARROW_OPACITY_MIN), ARROW_OPACITY)


def _switch(settings, name: str) -> bool:
    """One of the player's switches the arrows' ways follow (game_rides); off when the settings can't say."""
    try:
        return bool(settings[name])
    except (KeyError, TypeError):
        return False


def _on(settings, name: str) -> bool:
    """One of the player's navigation switches that is on unless they turn it off (minimap_route_follow,
    minimap_route_steps); on when the settings can't say, as they default."""
    try:
        value = settings[name]
    except (KeyError, TypeError):
        return True
    return True if value is None else bool(value)


def _shape(points, scale: float) -> QPolygonF:
    """One of the arrow's shapes (ARROW_PX, EDGE_ARROW_PX) scaled about its origin."""
    return QPolygonF([QPointF(x * scale, y * scale) for x, y in points])


def _aim(view: View, target: tuple[float, float], spot: tuple[float, float] | None, scale: float) -> _Aim:
    """An arrow for a spot on the map's picture (`target`: the route's next step, or the guided NPC): on it,
    pointing down, when the window shows it. Else it is off the part of the map shown
    (the game's minimap often shows only part: Kerning City's way to Henesys starts at its far left, left of the
    panel, live), and the arrow sits at the panel's edge, on the line from the player's dot (`spot`, the read's; the
    panel's middle when the read saw none or the window doesn't show it) toward it, turned to point out along it, its
    tip pulled in just far enough that all of it, head and shaft, stays inside the panel whichever way it turns, at
    the size it is drawn (`scale`, _size_scale: a bigger arrow sits further in)."""
    on = view.at(target)
    if on is not None:
        return _Aim(on[0], on[1], 0.0, False)
    x0, y0, x1, y1 = view.panel
    me = view.at(spot) if spot is not None else None
    ox, oy = me if me is not None else ((x0 + x1) / 2, (y0 + y1) / 2)
    bx, by = _box_px(view, target)
    dx, dy = bx - ox, by - oy
    # the line's own angle less down's (90: y grows down the screen), the turn from pointing down
    angle = (math.degrees(math.atan2(dy, dx)) - 90.0) % 360.0
    # where the tip may go: the panel less how far the arrow, turned so at its size, reaches past its tip on each side
    reach = QTransform().rotate(angle).map(_shape(EDGE_ARROW_PX, scale)).boundingRect()
    lo_x, hi_x = _inset(x0 - reach.left(), x1 - reach.right())
    lo_y, hi_y = _inset(y0 - reach.top(), y1 - reach.bottom())
    # from the player's dot (moved in there when nearer the edge) along the line toward the target, as far as it goes
    ox, oy = min(max(ox, lo_x), hi_x), min(max(oy, lo_y), hi_y)
    ends = [((hi_x if dx > 0 else lo_x) - ox) / dx] if dx else []
    if dy:
        ends.append(((hi_y if dy > 0 else lo_y) - oy) / dy)
    t = min(ends, default=0.0)
    return _Aim(min(max(ox + t * dx, lo_x), hi_x), min(max(oy + t * dy, lo_y), hi_y), angle, True)




def _steps_words(settings, j) -> tuple[str, dict] | None:
    """What the strip under the minimap box says of the way (minimap_route_steps, LOCATION.journey), an i18n key
    and what it carries: how many maps are still to pass through (arrow_maps_left; arrow_maps_left_one on the last
    one), or that the way was worked out again from where the player stands after they strayed off it
    (route_off_track, the read after). None with the switch off, with no journey published, and on the map they
    picked: there is nothing left to count, and nothing to say draws no strip."""
    if j is None or not _on(settings, "minimap_route_steps"):
        return None
    if j.off:
        return "route_off_track", {}
    if j.arrived or j.left < 1:
        return None
    return ("arrow_maps_left_one", {}) if j.left == 1 else ("arrow_maps_left", {"n": j.left})


def _tag_words(graph, leg: routes.Leg) -> tuple[str, str]:
    """What the name beside the route's arrow says for its step, an i18n key and the name it carries: the map a
    portal leads to (arrow_tag_hidden for a teleport the game's minimap never draws), or the NPC to talk to for a
    cab, a boat or an NPC's trip (Leg.via)."""
    if leg.kind == "portal":
        return ("arrow_tag_hidden" if leg.hidden else "arrow_tag_portal"), _name(graph, leg.to)
    return "arrow_tag_npc", leg.via


def _npc_name(kb, key: str) -> str:
    """The guided NPC's name as the KB has it, for the name beside its arrow and the log; the id its key carries
    (npc/<id>) when the KB has none."""
    name = (kb.get(key) or {}).get("name")
    return str(name) if name else key.rpartition("/")[2]


def _npc_words(kb, key: str) -> tuple[str, str]:
    """What the name beside the guided NPC's arrow says, as _tag_words for the route's: arrow_tag_npc and the NPC's
    name (_npc_name)."""
    return "arrow_tag_npc", _npc_name(kb, key)


def _say(arrow: str, what: str, key: object, aim: _Aim | None, said: tuple | None) -> tuple | None:
    """One line in the log for an arrow (`arrow`, which) whenever it moves between its spot and the panel's edge
    (`what` it points at can be off the part of the map the window shows), and for each new thing it points at
    (`key`): a player's report says where it was, and nothing is logged while it isn't placed. What the log has said
    now, handed back (`said`) the next time."""
    if aim is None:
        return None
    now = (key, aim.edge)
    if now != said:
        log.info("%s: %s", arrow, f"pointing from the edge: {what} is off the part shown" if aim.edge
                 else "on the minimap")
    return now


def _tag_rect(at: QPointF, angle: float, back: float, front: float, w: float, h: float,
              box: tuple[float, float, float, float], gap: float, flip: bool) -> QRectF:
    """Where the name beside an arrow goes, its pill (w x h) in the window's pixels: on the arrow's line
    just behind its tail (`back` behind its point `at`, the arrow turned `angle` degrees from pointing down, as
    drawn), `gap` clear of it, so above the shaft of the mark on a spot and inward of the sign at the panel's edge.
    Its top-left corner kept in `box` (lo_x, hi_x, lo_y, hi_y: the room the panel leaves it); when that pushes it
    back against the arrow (the sign by a corner of the panel), slid along the line of places just clear of the
    tail to the nearest one that fits. With no room behind the tail at all, past the tip (`front` ahead of `at`)
    when `flip` allows it; else where the box puts it, the arrow drawn over it."""
    a = math.radians(angle)
    ux, uy = -math.sin(a), math.cos(a)          # the way the arrow points: down, turned as it is drawn
    lo_x, hi_x, lo_y, hi_y = box
    fallback = None
    for side, end in ((-1.0, back), (1.0, front))[:2 if flip else 1]:
        dx, dy = side * ux, side * uy           # out from the arrow's point, past this end of it
        reach = end + gap + (abs(dx) * w + abs(dy) * h) / 2     # to the pill's middle, its near side `gap` clear
        x, y = at.x() + reach * dx - w / 2, at.y() + reach * dy - h / 2
        cx, cy = min(max(x, lo_x), hi_x), min(max(y, lo_y), hi_y)
        if fallback is None:
            fallback = QRectF(cx, cy, w, h)
        # its nearest corner still `gap` past this end, along the arrow?
        if (cx - at.x()) * dx + (cy - at.y()) * dy + min(0.0, dx * w) + min(0.0, dy * h) >= end + gap - 1e-6:
            return QRectF(cx, cy, w, h)
        lo, hi = -math.inf, math.inf            # along the places just clear of it, (x - s dy, y + s dx): in the box
        for p, step, low, high in ((x, -dy, lo_x, hi_x), (y, dx, lo_y, hi_y)):
            if abs(step) > 1e-9:
                s1, s2 = sorted(((low - p) / step, (high - p) / step))
                lo, hi = max(lo, s1), min(hi, s2)
            elif not low <= p <= high:
                lo, hi = math.inf, -math.inf
        if lo <= hi:
            s = min(max(0.0, lo), hi)
            return QRectF(x - s * dy, y + s * dx, w, h)
    return fallback


def _strip_above(rect: QRect, screens: list[tuple[QRect, float]], h: int) -> bool:
    """Whether the strip goes above the minimap box instead of under it, where it belongs (PortalDots.refresh): a
    minimap at the foot of its screen has no room under it, and a strip drawn off the screen's edge says nothing.
    The screen is the one holding the box's middle, as the box's own placing picks it (regionpick.from_capture).
    Under the box with no screen to ask, with none holding its middle, and when there is no room above it either
    (a box taller than its screen): nothing better is to be had there."""
    for geo, _ratio in screens:
        if geo.contains(rect.center()):
            return rect.y() + rect.height() + h > geo.y() + geo.height() and rect.y() - h >= geo.y()
    return False


class PortalDots(QWidget):
    """The dots', the guided NPC's ring's and arrow's and the route's arrow's window over the minimap box. Never
    takes a click, the focus, or a place in the minimap reads. The route's arrow points at its way's next step
    (_next_step): the way routed once for the player's map, the route's map and the switches, no extra routing a
    frame. The guided NPC's points at the NPC, the ring staying on the NPC. Each refresh takes the arrows' look
    from the settings: the route's colour (minimap_arrow_color; the guided NPC's is the ring's green, whatever is
    picked), their size (minimap_arrow_size), the name beside each (minimap_arrow_label, in the language the app's
    settings pick: the window is made without one) and their blink (minimap_arrow_flash): one timer on the window
    hiding and showing both arrows and their names alone every FLASH_MS, together, while either is placed and the
    setting is on. The guided NPC's is drawn over the route's. Under the box a strip says where the player is
    heading and how many maps are still to go (minimap_route_steps, _steps_words, _make_strip) from the journey
    this window works out and publishes at the arrow's own cache point (_journey, LOCATION.journey): the window
    grows by exactly that strip's height, down from its top-left — or up, with the marks drawn that much down
    (_shift), for a minimap at the foot of its screen — so every mark over the box lands where it did. With Guide
    the whole way off (minimap_route_follow) the route's arrow guides only on the map it was armed on and goes
    quiet, journey, strip and all, once the player leaves it."""

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
        # the way _next_step last routed, (player's map, route's map, cabs & teleports), and its first step when
        # it has a spot on the minimap
        self._arrow_key: tuple[str, str, bool] | None = None
        self._arrow_leg: routes.Leg | None = None
        self._arrow_said: tuple | None = None   # what the log last said about the arrow's placing (_say)
        # the map the route was armed on, as (the map picked, the player's map then): with Guide the whole way off
        # (minimap_route_follow) the arrow guides on that map alone and goes quiet once they leave it
        self._armed: tuple[str, str] | None = None
        # what the journey last published to LOCATION was worked out for (_journey: the player's map, the map
        # picked and the switches; None while the arrow guides nothing), so a follow frame publishes nothing
        self._journey_key: tuple[str, str, bool] | None = None
        self._ratio = 1.0
        # the arrows' look, from the settings at each refresh: how many times their drawn size (_size_scale), how
        # solid they, their names and the strip are drawn (_opacity), and the route's fill and rim (_arrow_colors;
        # the guided NPC's are always the ring's, RING_FILL and RING_RIM)
        self._arrow_scale = 1.0
        self._arrow_opacity = _opacity(settings)
        self._arrow_fill, self._arrow_rim = _arrow_colors(settings)
        self._tag: _Tag | None = None   # the name beside the route's arrow (_make_tag) while placed, its setting on
        # the strip under the minimap box while the journey has something to say (_make_strip), and how far down
        # the box's own marks are drawn for it (0 unless the strip had to go above the box)
        self._strip: _Strip | None = None
        self._shift = 0.0
        # the guided NPC's arrow, placed as the route's is (_aim): on the NPC, inside the ring, or while the part
        # shown hasn't it, its tip at the panel's edge; its turn from pointing down, which it is, the name beside
        # it, and what the log last said about its placing (_say)
        self._npc_arrow: QPointF | None = None
        self._npc_arrow_angle = 0.0
        self._npc_arrow_edge = False
        self._npc_tag: _Tag | None = None
        self._npc_said: tuple | None = None
        # the arrows' blink while its flash setting is on (_flash): a beat of the timer hides both, the next shows
        # them again
        self._flash_on = True
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(FLASH_MS)
        self._flash_timer.timeout.connect(self._blink)
        LOCATION.changed.connect(self.refresh)
        LOCATION.followed.connect(self.refresh)
        LOCATION.guided.connect(self.refresh)
        LOCATION.routed.connect(self.refresh)     # a route picked to another map, or stopped: the arrow follows
        LOCATION.boxed.connect(self.refresh)      # the minimap window found elsewhere (or another size): over it

    def set_kb(self, kb: KnowledgeBase) -> None:
        self._kb = kb
        self._arrow_key = None      # another KB, another graph: the arrow's way routed again
        self._journey_key = None    # ... the journey worked out again
        self.refresh()

    def refresh(self, _what: object = None) -> None:
        """Place the dots, the guided NPC's ring and arrow and the route's arrow over LOCATION.box from the live
        follow of the player's map (a Qt slot too: LOCATION's signals carry what it re-reads), the arrows at the size
        their settings pick, the route's in the colour picked, with the names beside them or not and blinking or not:
        read here every time, so a change shows at the next refresh. Never from a read's own view: it can be the last
        map's while the reads wait to confirm a new one, and entering a shop flashed the street's dots back for a
        second (live)."""
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
        # the portal dots need their setting; the ring, only a guide for the map the player is on, its NPC in the
        # part shown; the NPC's arrow, that guide and the arrows' setting, the arrow on the NPC, the ring on the
        # NPC either way; the route's arrow, that setting and a way from this map with a first step on its minimap,
        # the arrow on that step (_next_step). Each arrow on its spot when the part shown has it, else at the
        # panel's edge pointing toward it (_aim)
        spots = graph.hidden_spots(here.map) if self._settings["minimap_hidden_portals"] else []
        at = [p for p in (view.at(s) for s in spots) if p is not None]
        guide = LOCATION.guide
        if guide is not None and guide[0] != here.map:
            guide = None                        # another map's guide: nothing of it here
        at_ring = view.at(guide[1]) if guide is not None else None
        leg = self._next_step(graph, here)
        npc = guide is not None and bool(self._settings["minimap_route_arrow"])
        scale = _size_scale(self._settings)     # the edge arrow's room in the panel depends on its size
        aim = _aim(view, leg.spot, here.spot, scale) if leg is not None else None
        npc_aim = _aim(view, guide[1], here.spot, scale) if npc else None
        self._arrow_said = _say("route arrow", "its next step", self._arrow_key, aim, self._arrow_said)
        self._npc_said = _say("npc arrow", "the NPC", guide, npc_aim, self._npc_said)
        # what the strip under the box has to say of the way, if anything (_steps_words): something to say is
        # something to show, even with every mark off the part the minimap shows
        note = _steps_words(self._settings, LOCATION.journey)
        if not at and at_ring is None and aim is None and npc_aim is None and note is None:
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
        self._npc_arrow = QPointF(npc_aim.x / ratio, npc_aim.y / ratio) if npc_aim is not None else None
        self._npc_arrow_angle, self._npc_arrow_edge = ((npc_aim.angle, npc_aim.edge) if npc_aim is not None
                                                       else (0.0, False))
        self._arrow_scale = scale
        self._arrow_opacity = _opacity(self._settings)
        self._arrow_fill, self._arrow_rim = _arrow_colors(self._settings)
        # the names beside them, with their setting on: placed by the arrows just placed, inside the panel shown
        label = self._settings["minimap_arrow_label"]
        self._tag = (self._make_tag(_tag_words(graph, leg), aim, view.panel)
                     if aim is not None and label else None)
        self._npc_tag = (self._make_tag(_npc_words(self._kb, guide[2]), npc_aim, view.panel)
                         if npc_aim is not None and label else None)
        self._flash((self._arrow is not None or self._npc_arrow is not None)
                    and bool(self._settings["minimap_arrow_flash"]))
        # the strip under the box (_make_strip): the window grows by exactly its height and keeps its top-left, so
        # every mark just placed lands where it did; a box at the foot of its screen takes the strip above it
        # instead, the window growing up and the marks drawn that much down (_shift) — over the box all the same
        strip = self._make_strip(note, graph, rect.width()) if note is not None else None
        h = 0 if strip is None else int(strip.rect.height())
        up = bool(h) and _strip_above(rect, screens, h)
        self._shift = float(h) if up else 0.0
        self._strip = (strip if strip is None or up
                       else strip._replace(rect=strip.rect.translated(0.0, float(rect.height()))))
        grown = QRect(rect.x(), rect.y() - (h if up else 0), rect.width(), rect.height() + h)
        if self.geometry() != grown:
            self.setGeometry(grown)
        if not self.isVisible():
            self.show()
            set_capturable(self, self._settings)     # off the minimap reads' shots, unless the player asked
        self.update()

    def _next_step(self, graph, here: Here) -> routes.Leg | None:
        """The first step of the way to the map the player picked (LOCATION.route_dest) when it has a spot on their
        map's minimap picture: its portal or NPC (routes.Leg.spot) and what the name beside the arrow says
        (_tag_words), None when none does. The way on foot, or with cabs and NPC teleports when the toolbar's
        switch says so (settings["game_rides"]), as the search's page and the ◎ window draw it. None with the
        arrow's setting off, no route picked or already on its map, no way known, or a first step with no spot on
        the minimap — and, with Guide the whole way off (minimap_route_follow), once the player has left the map
        the route was armed on: the arrow guides there and nowhere else then, while on (the default) the map they
        picked stands and the way is worked out from wherever they now are. Routed only when the player's map, the
        route's map or a switch changes, the step kept for the refreshes after (set_kb forgets it): refresh runs
        on the GUI thread for every follow frame while the minimap scrolls, and Graph.route is a Dijkstra search
        over the whole map graph. The journey behind the count beside the arrow is published at that same point
        and on that same key (_journey)."""
        dest = LOCATION.route_dest
        rides = _switch(self._settings, "game_rides")
        if not dest:
            self._armed = None
        elif self._armed is None or self._armed[0] != dest:
            self._armed = (dest, here.map)      # armed here: the map it guides on with Guide the whole way off
        quiet = self._armed is not None and here.map != self._armed[1] and not _on(self._settings,
                                                                                   "minimap_route_follow")
        self._journey(graph, here, dest, rides,
                      bool(dest) and bool(self._settings["minimap_route_arrow"]) and not quiet)
        if not self._settings["minimap_route_arrow"] or not dest or dest == here.map or quiet:
            return None
        key = (here.map, dest, rides)
        if key != self._arrow_key:
            route = getattr(graph, "route", None)     # a stand-in graph that can't route (an older test's): no arrow
            way = route(here.map, dest, taxi=rides, teleport=rides) if route is not None else None
            leg = way.legs[0] if way is not None and way.legs else None
            self._arrow_key, self._arrow_leg = key, leg if leg is not None and leg.spot is not None else None
            self._arrow_said = None
            log.info("route arrow: to %s, %s", _name(graph, dest),
                     f"next step: {getattr(leg, 'kind', '')} {getattr(leg, 'via', '')}".strip()
                     if leg is not None and leg.spot is not None
                     else "its first step has no spot on this minimap" if leg is not None
                     else "no way known from here")
        return self._arrow_leg

    def _journey(self, graph, here: Here, dest: str | None, rides: bool, guiding: bool) -> None:
        """Work out the whole way from the player's CURRENT map to the map they picked (journey.of: its legs from
        here, how many maps are still to go, and whether they strayed off the way it last knew) and publish it for
        everyone who shows it — the strip under this window's own box first of all (_steps_words, _make_strip,
        LOCATION.journey). Nobody else writes it. Worked out where the arrow's own step is worked out and on the
        same key (the player's map, the map picked, the switches), so the follow frames between reads publish
        nothing and nothing new is searched a frame; cleared (None) whenever the arrow guides nothing: no route
        picked, its setting off, or the player off the map it was armed on with Guide the whole way off."""
        key = (here.map, dest, rides) if guiding and dest else None
        if key == self._journey_key:
            return
        self._journey_key = key
        LOCATION.set_journey(journey.of(graph, here.map, dest, rides=rides, last=LOCATION.journey)
                             if key is not None else None)


    def _make_tag(self, words: tuple[str, str], aim: _Aim,
                  panel: tuple[float, float, float, float]) -> _Tag | None:
        """The name beside an arrow just placed at `aim` (settings["minimap_arrow_label"]), in the language the app's
        settings pick (Hebrew until one is): `words`, an i18n key and the name it carries (_tag_words: what to click
        there, for the route's; _npc_words: the NPC's own, for the guided NPC's). A game name, so one left-to-right
        block in a Hebrew line, cut short with "…" past about TAG_CHARS characters or what the panel's width leaves
        it, never its glyph. Its letters sized with the arrow, its pill just behind the arrow's tail (_tag_rect) and
        all of it EDGE_GAP_PX inside the panel (`panel`: the view's, in box pixels), as the sign at the edge keeps.
        None when there is no name or the panel no room for it."""
        t = I18n(self._settings["language"] or "he")
        key, name = words
        if not name:
            return None
        k = 1.0 / self._ratio       # screen pixels to the window's, as every measure here
        px = max(TAG_FONT_MIN_PX, TAG_FONT_K * self._arrow_scale * ARROW_SIZE_PX)     # in screen pixels
        font = theme.app_font(max(1, round(px * k)))
        font.setBold(True)
        fm = QFontMetricsF(font)
        pad_x, pad_y = TAG_PAD_X * font.pixelSize(), TAG_PAD_Y * font.pixelSize()
        x0, y0, x1, y1 = (c * k for c in panel)
        inset = EDGE_GAP_PX * k
        # the name's room: as wide as its first TAG_CHARS characters (a pixel spare, so a name that short is never
        # cut for a rounding), less in a panel too narrow for them beside its glyph
        room = min(fm.horizontalAdvance(name[:TAG_CHARS]) + 1,
                   x1 - x0 - 2 * inset - 2 * pad_x - fm.horizontalAdvance(t(key, name="")))
        shown = fm.elidedText(name, Qt.ElideRight, room) if room > 0 else ""
        if shown in ("", "…"):
            return None
        text = t(key, name=bidi.ltr_block(shown, t.rtl))
        w, h = fm.horizontalAdvance(text) + 2 * pad_x, fm.height() + 2 * pad_y
        box = (x0 + inset, x1 - inset - w, y0 + inset, y1 - inset - h)     # where its top-left corner may go
        if box[0] > box[1] or box[2] > box[3]:
            return None
        ys = [y * self._arrow_scale * k for _, y in (EDGE_ARROW_PX if aim.edge else ARROW_PX)]
        # the mark on a spot may have it below its tip instead (no room above it, by the panel's top); the sign at
        # the edge never: past its tip is the panel's edge
        rect = _tag_rect(QPointF(aim.x / self._ratio, aim.y / self._ratio), aim.angle, -min(ys), max(ys), w, h, box,
                         TAG_GAP_PX * k, flip=not aim.edge)
        return _Tag(text, rect, font, t.rtl)

    def _make_strip(self, note: tuple[str, dict], graph, width: float) -> _Strip | None:
        """The strip under the minimap box (`note`, _steps_words: what the way has to say), in the language the
        app's settings pick (Hebrew until one is): the map the player is heading to by name (LOCATION.journey.dest,
        a game name, so one left-to-right block in a Hebrew line) and, past STRIP_SEP, how many maps are still to
        go — or that the way was worked out again from where they stand. On a dark backing as wide as the words
        need and never wider than the box (`width`, the window's), its letters STRIP_FONT_PX whatever size the
        arrows are set to. Its rect sits at the window's top here; refresh drops it under the box unless the box
        is at the foot of its screen (_strip_above). None when the box is too narrow for a readable word of it:
        there is nothing to draw, and the window must not grow for nothing."""
        t = I18n(self._settings["language"] or "he")
        k = 1.0 / self._ratio       # screen pixels to the window's, as every measure here
        font = theme.app_font(max(1, round(STRIP_FONT_PX * k)))
        font.setBold(True)
        fm = QFontMetricsF(font)
        pad_x, pad_y = STRIP_PAD_X * font.pixelSize(), STRIP_PAD_Y * font.pixelSize()
        text = bidi.ltr_block(_name(graph, LOCATION.journey.dest), t.rtl) + STRIP_SEP + t(note[0], **note[1])
        room = width - 2 * pad_x
        shown = fm.elidedText(text, Qt.ElideRight, room) if room > 0 else ""
        if shown in ("", "…"):
            return None
        w = min(fm.horizontalAdvance(shown) + 2 * pad_x, float(width))
        h = float(math.ceil(fm.height() + 2 * pad_y))     # whole window pixels: the window grows by just this
        return _Strip(shown, QRectF((width - w) / 2, 0.0, w, h), font, t.rtl)

    def _clear(self) -> None:
        self._dots = []
        self._ring = None
        self._arrow = None
        self._arrow_angle = 0.0
        self._arrow_edge = False
        self._tag = None
        self._npc_arrow = None
        self._npc_arrow_angle = 0.0
        self._npc_arrow_edge = False
        self._npc_tag = None
        self._strip = None
        self._shift = 0.0
        self._flash(False)
        if self.isVisible():
            self.hide()

    def _flash(self, on: bool) -> None:
        """The arrows' blink (settings["minimap_arrow_flash"]), one beat for both: kept running while either is placed
        and the setting is on, never restarted by the refreshes meanwhile (they come with every follow frame while the
        minimap scrolls, faster than its beat); else stopped with them shown, so no redraw is left without them."""
        if not on:
            self._flash_timer.stop()
            self._flash_on = True
        elif not self._flash_timer.isActive():
            self._flash_timer.start()

    def _blink(self) -> None:
        """The flash timer's beat: both arrows, their names and the strip under the box hidden, or shown again
        (they alone: the dots and the ring stay)."""
        self._flash_on = not self._flash_on
        self.update()

    def paintEvent(self, e) -> None:
        shown = self._flash_on      # blinking (_flash): both arrows, their names and the strip under the box,
        route = shown and self._arrow is not None       # out and in every other beat
        npc = shown and self._npc_arrow is not None
        strip = self._strip if shown else None
        if not self._dots and self._ring is None and not route and not npc and strip is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # the way's own marks — both arrows, the names beside them and the strip — at the opacity the player picks
        # (minimap_arrow_opacity); the hidden portals' dots and the guided NPC's ring are drawn solid between them,
        # as they are never blinked either
        p.setOpacity(self._arrow_opacity)
        if strip is not None:
            self._draw_strip(p, strip)
        # ... and everything else measured from the box's own top-left, wherever the strip left the window's
        p.translate(0.0, self._shift)
        p.setOpacity(1.0)
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
        p.setOpacity(self._arrow_opacity)
        if route:
            self._draw_arrow(p, self._arrow, self._arrow_angle, self._arrow_edge, self._tag, self._arrow_fill,
                             self._arrow_rim)
        if npc:     # over the route's where they meet, in the ring's green: it reads as the NPC, never as a step
            self._draw_arrow(p, self._npc_arrow, self._npc_arrow_angle, self._npc_arrow_edge, self._npc_tag,
                             RING_FILL, RING_RIM)
        p.end()

    def _draw_strip(self, p: QPainter, strip: _Strip) -> None:
        """The strip under the minimap box (paintEvent, _make_strip): its words in the route arrow's fill on that
        arrow's dark rim, the backing STRIP_ALPHA opaque so they read over whatever the game draws there — the
        pill's own dark-on-bright treatment, outside the game's picture. Drawn and left out with the arrows
        (paintEvent's beat): it is the route arrow's own word.

        Its whole edge is drawn a full pen inside its rect, not straddling it as the name pill's does: the window
        grows by exactly the strip's height, so an edge on the rect's own line would hand the row next to it —
        the box's first or last — a sliver of the strip, and no row over the box is the strip's to touch."""
        line = 1.0 / self._ratio
        back = QColor(self._arrow_rim)
        back.setAlphaF(STRIP_ALPHA)
        p.setPen(QPen(self._arrow_fill, line))
        p.setBrush(back)
        box = strip.rect.adjusted(line, line, -line, -line)     # all of it, pen and all, inside its rect
        p.drawRoundedRect(box, box.height() / 4, box.height() / 4)
        p.setFont(strip.font)
        p.setLayoutDirection(Qt.RightToLeft if strip.rtl else Qt.LeftToRight)
        p.setPen(self._arrow_fill)
        p.drawText(strip.rect, Qt.AlignCenter, strip.text)

    def _draw_arrow(self, p: QPainter, at: QPointF, angle: float, edge: bool, tag: _Tag | None, fill: QColor,
                    rim: QColor) -> None:
        """One arrow (paintEvent), in its fill on its rim over the name beside it: the mark on a spot (ARROW_PX) or
        the sign at the panel's edge (EDGE_ARROW_PX, `edge`) at `at`, turned `angle` degrees from pointing down."""
        if tag is not None:
            # its name first (shown and left out with it), so the arrow is drawn whole over a pill the panel's edge
            # left nowhere else: the words in the arrow's fill on its rim a little see-through, edged in the fill,
            # laid out as their language reads whatever the window's direction
            line = 1.0 / self._ratio
            back = QColor(rim)
            back.setAlphaF(TAG_ALPHA)
            p.setPen(QPen(fill, line))
            p.setBrush(back)
            pill = tag.rect.adjusted(line / 2, line / 2, -line / 2, -line / 2)     # its edge inside its rect
            p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            p.setFont(tag.font)
            p.setLayoutDirection(Qt.RightToLeft if tag.rtl else Qt.LeftToRight)
            p.drawText(tag.rect, Qt.AlignCenter, tag.text)
        p.setPen(QPen(rim, 1.0 / self._ratio))
        p.setBrush(fill)
        # at the size its setting picks, in the window's pixels, about its own origin (its spot, the edge arrow's
        # tip), then turned about it: 0 leaves the mark pointing down
        shape = _shape(EDGE_ARROW_PX if edge else ARROW_PX, self._arrow_scale / self._ratio)
        p.drawPolygon(QTransform().rotate(angle).map(shape).translated(at))
