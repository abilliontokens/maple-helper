"""Blue dots on the game's own minimap where the map's invisible teleports are (press-up and touch portals the game
never draws), a green ring around the NPC the player asked to be guided to (LOCATION.guide: ui/npcoverlay.py, the
search's NPC page) with a green arrow pointing down at it, and an arrow pointing down at the next portal or NPC on
the way to the map the player picked a route to (LOCATION.route_dest). Either arrow points at the pad of a hidden
teleport on the player's own map instead when one cuts their walk to its spot (routes.Graph.shortcut: its blue dot,
where to stand), the guided NPC's ring staying on the NPC. The minimap often shows only part of the map: an NPC, a
step or a pad off the part shown gets a bigger arrow just inside the edge of the part shown instead, pointing toward
it (the NPC no ring then). All of it on a click-through window laid over the minimap's box (LOCATION.box: the game's
minimap window found at its top left, else the box the player drew), and moved with it. The map comes from each
minimap read (ui/location.LOCATION.here), where its picture lies in the box from the fast follow between reads
(LOCATION.follow: the marks move with the minimap's scroll, and go the moment the picture stops matching, a teleport
or the loading screen). Hidden whenever there is nothing to place (no box, no read, a picture that doesn't match);
the portal dots also need their setting, the ring only a guide on the player's own map, the NPC's arrow that guide
and the arrows' setting (minimap_route_arrow), and the route's arrow that setting and a way known from the player's
map to another one, its first step on this map's minimap picture. A shortcut's pad, the route's or the NPC's, needs
the player's Hidden teleport routes switch too (route_hidden_teleports: off, neither arrow ever takes one, the NPC's
on the NPC as ever) and their own dot read (LOCATION.here.spot): the graph is asked again only for another way or
guide, or once a read has the dot in another of the picture's cells (SHORTCUT_CELLS each way; never for a follow
frame), and the pad stays picked while they stand on it (PAD_NEAR), so the arrow never flickers back to the portal
or the NPC before they take the jump; the read that lands them past it points at the portal or the NPC again, or at
the next pad. The arrows look as the bar's ⚙ panel picks, read at every refresh: the route's colour
(minimap_arrow_color, a name in ARROW_COLORS: orange unless another is picked; the NPC's is the ring's green whatever
is picked, so it reads as the NPC and never as the route's step), their size (minimap_arrow_size: the length in
screen pixels, from ARROW_SIZE_MIN to ARROW_SIZE_MAX, both shapes scaled alike), a small name beside each saying what
to click there (minimap_arrow_label, in the app's language: the map the route's portal leads to, a hidden teleport's
in words of its own (a shortcut's pad's too, with the map its step leads to), or the NPC to talk to for a cab, a boat
or an NPC's trip; the guided NPC's own name, as the KB has it, in the hidden teleport's words at its pad, so the pad
never reads as the NPC itself; on a pill in its arrow's colours, its letters sized with the arrow, just above the
mark's shaft or inward of the sign at the edge, all of it inside the panel) and whether they blink
(minimap_arrow_flash: both hidden and shown again together every FLASH_MS, their names with them, to catch the eye
on a busy minimap; the dots and the ring never blink). Both at once (a guide here while the route leads elsewhere):
the NPC's is drawn over the route's."""
from __future__ import annotations

import logging
import math
import sys
from typing import NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QWidget

from .. import bidi, routes
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
# an arrow's shortcut (_ask_shortcut: the route's toward its next step, the guided NPC's toward the NPC):
# routes.Graph.shortcut asked from the player's own spot (LOCATION.here.spot) by the cell it falls in, this many
# across and down the map's picture: asked again only once a read has their dot in another cell (it moves a little on
# every read, and never on the follow frames between)
SHORTCUT_CELLS = 50
# ... and the pad picked kept, nothing asked, while their spot is this near it either way (fractions of the picture:
# two cells) and not past the jump (_on_pad): standing on it, their dot jitters about it as they press up there, and
# the arrow must not flicker between the pad and the portal or the NPC
PAD_NEAR = 2 / SHORTCUT_CELLS


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


def _switch(settings, name: str) -> bool:
    """One of the player's switches the arrows' ways follow (game_rides, route_hidden_teleports); off when the
    settings can't say."""
    try:
        return bool(settings[name])
    except (KeyError, TypeError):
        return False


def _shape(points, scale: float) -> QPolygonF:
    """One of the arrow's shapes (ARROW_PX, EDGE_ARROW_PX) scaled about its origin."""
    return QPolygonF([QPointF(x * scale, y * scale) for x, y in points])


def _aim(view: View, target: tuple[float, float], spot: tuple[float, float] | None, scale: float) -> _Aim:
    """An arrow for a spot on the map's picture (`target`: the route's next step, the guided NPC, or the pad of a
    shortcut toward either): on it, pointing down, when the window shows it. Else it is off the part of the map shown
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


def _on_pad(you: tuple[float, float], jump: routes.Jump) -> bool:
    """The player's spot (LOCATION.here.spot) is on a shortcut's pad (Jump.frm: its blue dot), or within PAD_NEAR of
    it either way, and not past the jump: nearer the pad than where it lands (Jump.to), so the read after the jump
    never counts as still standing there."""
    return (abs(you[0] - jump.frm[0]) <= PAD_NEAR and abs(you[1] - jump.frm[1]) <= PAD_NEAR
            and math.dist(you, jump.frm) < math.dist(you, jump.to))


def _ask_shortcut(graph, here: Here, target: tuple[float, float], kept: tuple) -> tuple:
    """The hidden teleport on the player's own map that cuts their walk to a spot on it (`target`: the way's next
    step, PortalDots._shortcut; the guided NPC, PortalDots._npc_shortcut), as routes.Graph.shortcut picks it from
    their own spot (LOCATION.here.spot, the read's dot): an arrow points at its pad (Jump.frm) then; None when no
    teleport beats the walk. `kept` is the last pick and the cell of their spot it was asked from (SHORTCUT_CELLS
    each way; None: to be asked), both handed back as they are now: asked only with their spot known (a read that
    didn't see the dot keeps the last pick), and again only once a read has it in another of the picture's cells,
    never for a follow frame, a read a step on or one while they stand on the pad picked (_on_pad), where it stays
    picked so the arrow never flickers between the pad and the spot as their dot jitters about it. The first read
    off the pad asks again: the one that lands them past the jump gets the spot back (or the next pad), that jump
    saving nothing from there."""
    jump, cell = kept
    you = here.spot
    if you is None:
        return kept
    if jump is not None and _on_pad(you, jump):
        return jump, None       # standing on it: kept, and the first read off it asks again
    now = (int(you[0] * SHORTCUT_CELLS), int(you[1] * SHORTCUT_CELLS))
    return kept if now == cell else (graph.shortcut(here.map, you, target), now)


def _tag_words(graph, leg: routes.Leg, jump: routes.Jump | None = None) -> tuple[str, str]:
    """What the name beside the route's arrow says for its step, an i18n key and the name it carries: the map a
    portal leads to (arrow_tag_hidden for a teleport the game's minimap never draws), or the NPC to talk to for a
    cab, a boat or an NPC's trip (Leg.via). At a shortcut's pad instead (`jump`, PortalDots._shortcut: a hidden
    teleport on the player's own map that cuts the walk to the step), the hidden teleport's words with the map the
    step leads to: stand on it, it takes you toward there."""
    if jump is not None:
        return "arrow_tag_hidden", _name(graph, leg.to)
    if leg.kind == "portal":
        return ("arrow_tag_hidden" if leg.hidden else "arrow_tag_portal"), _name(graph, leg.to)
    return "arrow_tag_npc", leg.via


def _npc_name(kb, key: str) -> str:
    """The guided NPC's name as the KB has it, for the name beside its arrow and the log; the id its key carries
    (npc/<id>) when the KB has none."""
    name = (kb.get(key) or {}).get("name")
    return str(name) if name else key.rpartition("/")[2]


def _npc_words(kb, key: str, jump: routes.Jump | None = None) -> tuple[str, str]:
    """What the name beside the guided NPC's arrow says, as _tag_words for the route's: arrow_tag_npc and the NPC's
    name (_npc_name). At a shortcut's pad instead (`jump`, PortalDots._npc_shortcut: a hidden teleport on the
    player's own map that cuts the walk to the NPC), the hidden teleport's words with the NPC's name: stand on it, it
    takes you toward them; never the NPC's own, so the pad never reads as the NPC itself."""
    return ("arrow_tag_hidden" if jump is not None else "arrow_tag_npc"), _npc_name(kb, key)


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


class PortalDots(QWidget):
    """The dots', the guided NPC's ring's and arrow's and the route's arrow's window over the minimap box. Never
    takes a click, the focus, or a place in the minimap reads. The route's arrow points at its way's next step, or at
    the pad of a hidden teleport on the player's map that cuts the walk there (_next_step, _shortcut): the way routed
    once for the player's map, the route's map and the switches. The guided NPC's points at the NPC, or likewise at
    the pad of one that cuts the walk to it (_npc_shortcut: the hidden teleport's words with the NPC's name beside
    it, the ring staying on the NPC), its pick kept for the guide and the switch. Either shortcut is asked only with
    the Hidden teleport routes switch on and the player's dot read, and again only as that dot moves from cell to
    cell, never while they stand on the pad (_ask_shortcut). Each refresh takes the arrows' look from the settings:
    the route's colour (minimap_arrow_color; the guided NPC's is the ring's green, whatever is picked), their size
    (minimap_arrow_size), the name beside each (minimap_arrow_label, in the language the app's settings pick: the
    window is made without one) and their blink (minimap_arrow_flash): one timer on the window hiding and showing
    both arrows and their names alone every FLASH_MS, together, while either is placed and the setting is on. The
    guided NPC's is drawn over the route's."""

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
        # the route's arrow, once the follow places it (_aim): its next step's portal or NPC, or the pad of a hidden
        # teleport that cuts the walk there (or, that off the part shown, its tip at the panel's edge), the degrees it
        # turns clockwise from pointing down, and which it is
        self._arrow: QPointF | None = None
        self._arrow_angle = 0.0
        self._arrow_edge = False
        # the way _next_step last routed, (player's map, route's map, cabs & teleports, hidden teleports), and its
        # first step when it has a spot on the minimap
        self._arrow_key: tuple[str, str, bool, bool] | None = None
        self._arrow_leg: routes.Leg | None = None
        # ... and its shortcut through a hidden teleport on the player's map while one cuts the walk to that step
        # (_shortcut), with the cell of their spot it was last asked from (SHORTCUT_CELLS; None: to be asked)
        self._arrow_jump: routes.Jump | None = None
        self._jump_cell: tuple[int, int] | None = None
        self._arrow_said: tuple | None = None   # what the log last said about the arrow's placing (_say)
        self._ratio = 1.0
        # the arrows' look, from the settings at each refresh: how many times their drawn size (_size_scale), and
        # the route's fill and rim (_arrow_colors; the guided NPC's are always the ring's, RING_FILL and RING_RIM)
        self._arrow_scale = 1.0
        self._arrow_fill, self._arrow_rim = _arrow_colors(settings)
        self._tag: _Tag | None = None   # the name beside the route's arrow (_make_tag) while placed, its setting on
        # the guided NPC's arrow, placed as the route's is (_aim): on the NPC, inside the ring, or on the pad of a
        # hidden teleport that cuts the walk there (_npc_shortcut), or while the part shown hasn't it, its tip at the
        # panel's edge; its turn from pointing down, which it is, the name beside it, and what the log last said
        # about its placing (_say)
        self._npc_arrow: QPointF | None = None
        self._npc_arrow_angle = 0.0
        self._npc_arrow_edge = False
        self._npc_tag: _Tag | None = None
        self._npc_said: tuple | None = None
        # ... and its shortcut, as the route's (_npc_shortcut): what it was asked for (the guide, its map, the NPC's
        # spot and key, and the Hidden teleport routes switch), the pad picked while one cuts the walk to the NPC, and
        # the cell of the player's spot it was last asked from (SHORTCUT_CELLS; None: to be asked)
        self._npc_key: tuple | None = None
        self._npc_jump: routes.Jump | None = None
        self._npc_cell: tuple[int, int] | None = None
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
        self._arrow_key = None      # another KB, another graph: the arrow's way routed and its shortcut asked again
        self._npc_key = None        # ... and the guided NPC's shortcut asked again
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
        # part shown; the NPC's arrow, that guide and the arrows' setting, the arrow on the NPC or on the pad of a
        # hidden teleport that cuts the walk to it (_npc_shortcut), the ring on the NPC either way; the route's arrow,
        # that setting and a way from this map with a first step on its minimap, the arrow on that step or on the pad
        # of a hidden teleport that cuts the walk to it (_next_step). Each arrow on its spot when the part shown has
        # it, else at the panel's edge pointing toward it (_aim)
        spots = graph.hidden_spots(here.map) if self._settings["minimap_hidden_portals"] else []
        at = [p for p in (view.at(s) for s in spots) if p is not None]
        guide = LOCATION.guide
        if guide is not None and guide[0] != here.map:
            guide = None                        # another map's guide: nothing of it here
        at_ring = view.at(guide[1]) if guide is not None else None
        leg, jump = self._next_step(graph, here) or (None, None)
        npc = guide is not None and bool(self._settings["minimap_route_arrow"])
        npc_jump = self._npc_shortcut(graph, here, guide) if npc else None
        scale = _size_scale(self._settings)     # the edge arrow's room in the panel depends on its size
        aim = _aim(view, jump.frm if jump is not None else leg.spot, here.spot, scale) if leg is not None else None
        npc_aim = _aim(view, npc_jump.frm if npc_jump is not None else guide[1], here.spot, scale) if npc else None
        what = f"the hidden teleport {jump.name}" if jump is not None else "its next step"
        self._arrow_said = _say("route arrow", what, (self._arrow_key, jump), aim, self._arrow_said)
        what = f"the hidden teleport {npc_jump.name}" if npc_jump is not None else "the NPC"
        self._npc_said = _say("npc arrow", what, (guide, npc_jump), npc_aim, self._npc_said)
        if not at and at_ring is None and aim is None and npc_aim is None:
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
        self._arrow_fill, self._arrow_rim = _arrow_colors(self._settings)
        # the names beside them, with their setting on: placed by the arrows just placed, inside the panel shown
        label = self._settings["minimap_arrow_label"]
        self._tag = self._make_tag(_tag_words(graph, leg, jump), aim, view.panel) if aim is not None and label else None
        self._npc_tag = (self._make_tag(_npc_words(self._kb, guide[2], npc_jump), npc_aim, view.panel)
                         if npc_aim is not None and label else None)
        self._flash((self._arrow is not None or self._npc_arrow is not None)
                    and bool(self._settings["minimap_arrow_flash"]))
        if self.geometry() != rect:
            self.setGeometry(rect)
        if not self.isVisible():
            self.show()
            set_capturable(self, self._settings)     # off the minimap reads' shots, unless the player asked
        self.update()

    def _next_step(self, graph, here: Here) -> tuple[routes.Leg, routes.Jump | None] | None:
        """The first step of the way to the map the player picked (LOCATION.route_dest) when it has a spot on their
        map's minimap picture: its portal or NPC (routes.Leg.spot) and what the name beside the arrow says
        (_tag_words); with it the hidden teleport on their own map that cuts the walk there (_shortcut: its pad,
        where the arrow points then), None when none does. The way on foot, or with cabs and NPC teleports when the
        toolbar's switch says so (settings["game_rides"]), through the hidden teleports where they make it shorter
        when the player allows them (settings["route_hidden_teleports"], which the shortcut needs too: off, never a
        pad), as the search's page and the ◎ window draw it. None with the arrow's setting off, no route picked or
        already on its map, no way known, or a first step with no spot on the minimap. Routed only when the player's
        map, the route's map or a switch changes, the step kept for the refreshes after (set_kb forgets it) and its
        shortcut asked anew: refresh runs on the GUI thread for every follow frame while the minimap scrolls, and
        Graph.route is a Dijkstra search over the whole map graph."""
        dest = LOCATION.route_dest
        if not self._settings["minimap_route_arrow"] or not dest or dest == here.map:
            return None
        rides, hidden = _switch(self._settings, "game_rides"), _switch(self._settings, "route_hidden_teleports")
        key = (here.map, dest, rides, hidden)
        if key != self._arrow_key:
            route = getattr(graph, "route", None)     # a stand-in graph that can't route (an older test's): no arrow
            way = route(here.map, dest, taxi=rides, teleport=rides, hidden=hidden) if route is not None else None
            leg = way.legs[0] if way is not None and way.legs else None
            self._arrow_key, self._arrow_leg = key, leg if leg is not None and leg.spot is not None else None
            self._arrow_jump, self._jump_cell = None, None     # a new way: its shortcut asked anew
            self._arrow_said = None
            log.info("route arrow: to %s, %s", _name(graph, dest),
                     f"next step: {getattr(leg, 'kind', '')} {getattr(leg, 'via', '')}".strip()
                     if leg is not None and leg.spot is not None
                     else "its first step has no spot on this minimap" if leg is not None
                     else "no way known from here")
        leg = self._arrow_leg
        if leg is None:
            return None
        return leg, (self._shortcut(graph, here, leg) if hidden else None)

    def _shortcut(self, graph, here: Here, leg: routes.Leg) -> routes.Jump | None:
        """The hidden teleport on the player's own map that cuts their walk to the way's next step (`leg`), as
        _ask_shortcut picks it from their own spot: the route's arrow points at its pad (Jump.frm) then, and the name
        beside it says it takes them toward the step's map; None when no teleport beats the walk. The log says when
        the arrow takes a shortcut and when it goes back to the step. Kept with the way: _next_step asks anew for a
        new one."""
        jump, self._jump_cell = _ask_shortcut(graph, here, leg.spot, (self._arrow_jump, self._jump_cell))
        if jump != self._arrow_jump:
            log.info("route arrow: %s", f"pointing at a shortcut, the hidden teleport {jump.name} toward "
                     f"{_name(graph, leg.to)}" if jump is not None
                     else "no shortcut from here, pointing at its next step")
        self._arrow_jump = jump
        return jump

    def _npc_shortcut(self, graph, here: Here, guide: tuple) -> routes.Jump | None:
        """The hidden teleport on the player's own map that cuts their walk to the guided NPC (`guide`: its map, the
        NPC's spot and key, LOCATION.guide on their map), as _ask_shortcut picks it from their own spot, the same as
        for the route's step (_shortcut): the NPC's arrow points at its pad (Jump.frm) then, the ring staying on the
        NPC, and the name beside it says it takes them toward the NPC (_npc_words). None when no teleport beats the
        walk, and with the Hidden teleport routes switch off (settings["route_hidden_teleports"]: the arrow on the
        NPC as ever, the graph never asked). Kept for the guide and the switch, asked anew for another guide or the
        switch flipped (set_kb forgets it too), and in between as the route's is: never for a follow frame, a read a
        step on or one while they stand on the pad. The log says when the arrow takes a shortcut and when it goes
        back to the NPC."""
        hidden = _switch(self._settings, "route_hidden_teleports")
        if (guide, hidden) != self._npc_key:
            self._npc_key, self._npc_jump, self._npc_cell = (guide, hidden), None, None
        if not hidden:
            return None
        jump, self._npc_cell = _ask_shortcut(graph, here, guide[1], (self._npc_jump, self._npc_cell))
        if jump != self._npc_jump:
            log.info("npc arrow: %s", f"pointing at a shortcut, the hidden teleport {jump.name} toward "
                     f"{_npc_name(self._kb, guide[2])}" if jump is not None
                     else "no shortcut from here, pointing at the NPC")
        self._npc_jump = jump
        return jump

    def _make_tag(self, words: tuple[str, str], aim: _Aim, panel: tuple[float, float, float, float]) -> _Tag | None:
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
        """The flash timer's beat: both arrows and their names hidden, or shown again (they alone: the dots and the
        ring stay)."""
        self._flash_on = not self._flash_on
        self.update()

    def paintEvent(self, e) -> None:
        shown = self._flash_on      # blinking (_flash): both arrows, their names with them, left out every other beat
        route = shown and self._arrow is not None
        npc = shown and self._npc_arrow is not None
        if not self._dots and self._ring is None and not route and not npc:
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
        if route:
            self._draw_arrow(p, self._arrow, self._arrow_angle, self._arrow_edge, self._tag, self._arrow_fill,
                             self._arrow_rim)
        if npc:     # over the route's where they meet, in the ring's green: it reads as the NPC, never as a step
            self._draw_arrow(p, self._npc_arrow, self._npc_arrow_angle, self._npc_arrow_edge, self._npc_tag,
                             RING_FILL, RING_RIM)
        p.end()

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
