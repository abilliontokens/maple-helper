"""Blue dots on the game's own minimap where the map's invisible teleports are (press-up and touch portals the game
never draws), a green ring around the NPC the player asked to be guided to (LOCATION.guide: ui/npcoverlay.py, the
search's NPC page) with a green arrow pointing down at it, and an arrow pointing down at the next portal or NPC on
the way to the map the player picked a route to (LOCATION.route_dest). Either arrow points at the pad of a hidden
teleport on the player's own map instead when one cuts their walk to its spot (routes.Graph.shortcut_path: its blue dot,
where to stand), the guided NPC's ring staying on the NPC. When that cheapest way takes more than one pad in a row,
every later pad shown gets a smaller numbered marker in the arrow's colours (2, 3, 4, …: every pad of the chain,
however many), so the whole chain reads in order on the player's own map; a later pad off the part shown, or one
the arrow's name pill would cover, is left out. The minimap often shows only part of the map: an NPC, a
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
the next pad. A read that finds them standing on another of the map's pads names that one instead, with its own
chain numbered after it, while a way through it reaches the spot within PAD_UNDERFOOT_BAND of the cheapest way's
cost: the walk to it is already paid, so a way a few percent dearer through the pad under their feet beats a
cheaper way starting across the map, while a pad that would throw them back to where they started costs far more
than that band and is passed over as ever. A pad once named stays named past a cheaper rival too, while the player has not really
moved and a way through it still reaches its spot (_held_chain): on ground, still on the joined platform
it was picked from and beaten by no more than the ground model's own resolution (terrain.MODEL_RESOLUTION);
off ground, within the flat switch margin (SHORTCUT_SWITCH_MARGIN) — so a wobble about a tie, their dot
jumping about one platform, the cheapest pad flipping cell to cell, never changes the arrow's mind. It
gives the pad up on arriving on another platform (that platform seen on ARRIVE_READS reads in a
row; one read crossing it in a fall or a jump, the arrow keeping what it had, is not arrival),
for a way that beats it past its branch's margin, for none through it from where they stand, or
once taking it has been witnessed: they were seen on the pad and are now on its landing side, or
their dot moved in one read from the pad's neighbourhood to its landing — nearer the landing
alone, true of most of a map for most pads, is no witness and leaves the per-cell asking untouched. Once witnessed, the pad stays given up while they remain on that
side, however far they walk on, the fresh chain deciding there — and naming that same pad again only when
it genuinely does. The arrows look as
the bar's ⚙ panel picks, read at every refresh: the route's colour
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
the NPC's is drawn over the route's.

Under either arrow the walking path the ground model works out is drawn along its points
(minimap_path_line, on unless it is turned off: routes.Graph.walk_path from the player's own dot to what that arrow
guides to — the route's next step, the guided NPC), in its arrow's own colours but quieter: this is the trail, the
arrow is the instruction, and the trail never competes with it. Only the part of the map the minimap shows is drawn:
a point off it (View.at) breaks the line clean rather than cutting a stroke across the panel. A pad of the way is a
jump in the line, not a walk across the map — its teleport is a dotted hop from the pad to where it lands. The path
costs a ground search, so it is asked where the arrow's own answer is asked, once a read has the player's dot in
another of the picture's cells (SHORTCUT_CELLS, as the pad chain's own asking), and never for a follow frame; it
blinks with its arrow and is drawn under it and under the numbered markers.

Under the minimap box, outside the game's own picture, a strip says where the player is heading and how many maps
are still to go (minimap_route_steps: the map they picked by name, then arrow_maps_left, arrow_maps_left_one on the
last one), and on the read after a wrong portal that the way was worked out again from where they stand
(route_off_track). It is drawn small, in the route's arrow's own colours on its dark rim, so it reads over whatever
the game draws under its minimap, and it blinks with the arrows when they blink: it is the route arrow's own word,
and a strip left steady beside a blinking arrow would read as something else's. The window grows down by exactly
the strip's height and keeps its top-left, so every mark over the box — the dots, the ring, the arrows, the
numbered markers, the paths — lands where it did; a minimap at the foot of its screen puts the strip above the box
instead, the window growing up and the marks drawn that much down, which leaves them over the box just the same.
Nothing to say draws nothing and grows nothing: the switch off, no route armed, or the player already there. The
count comes from LOCATION.journey, the way from the player's CURRENT map to the map they picked: this window works
it out (journey.of) where it works out the arrow's own step and publishes it (LOCATION.set_journey), once for a
map, a destination and the switches and never for a follow frame, and clears it whenever the arrow guides nothing.

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

from .. import bidi, journey, routes, terrain
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
# the strip under the minimap box (minimap_route_steps, _make_strip): where the player is heading and how many maps
# are still to go, in the route arrow's own colours on its dark rim, outside the game's picture
STRIP_FONT_PX = 11          # its letters in screen pixels: small, and the same whatever size the arrows are set
                            # to, so how far the window grows below the box never moves with another setting
STRIP_PAD_X, STRIP_PAD_Y = 0.6, 0.25    # its backing's room around the words, across and above/below, in letters
STRIP_ALPHA = 0.92          # how opaque that backing is: the game draws its own panels under the minimap, and the
                            # words must read over whatever is there
STRIP_SEP = " · "           # between the map the player is heading to and how many maps are still to go
# the walking path under an arrow (minimap_path_line, _path_segs): a line along routes.Graph.walk_path's points in
# the arrow's own fill, thinner than the arrow and this see-through, so it reads as the trail and never competes
# with the instruction; a pad of the way is a dotted hop from the pad to where it lands, never a walk across the map
PATH_PEN_PX = 2.0
PATH_ALPHA = 0.55
# a later pad of a chain (_chain_marks), numbered in the arrow's colours beside the first pad's arrow
CHAIN_MARK_PX = 14                  # its marker's width in screen pixels: smaller than the arrow (ARROW_SIZE_PX
                                    # long), wider than a blue dot, its bright fill on its dark rim and its order
                                    # number in the rim inside it, so it reads on a busy minimap
# an arrow's shortcut (_ask_shortcut: the route's toward its next step, the guided NPC's toward the NPC):
# routes.Graph.shortcut_path asked from the player's own spot (LOCATION.here.spot) by the cell it falls in, this
# many across and down the map's picture: asked again only once a read has their dot in another cell (it moves a
# every read, and never on the follow frames between)
SHORTCUT_CELLS = 50
# ... and the pad picked kept, nothing asked, while their spot is this near it either way (fractions of the picture:
# two cells) and not past the jump (_on_pad): standing on it, their dot jitters about it as they press up there, and
# the arrow must not flicker between the pad and the portal or the NPC
PAD_NEAR = 2 / SHORTCUT_CELLS
# a pad the player is standing on (_on_pad) is named ahead of a pad somewhere else while a way through it
# reaches the spot within this share of the cheapest way's cost (_underfoot_chain): they have already paid
# the walk to it, and it is the one pad they can act on without walking anywhere, so a way a few percent
# dearer through it is worth more to them than a cheaper way starting across the map. Measured on the live
# KB, 2026-10-14, standing on every pad of all 34 maps that have both ground and pads, toward up to ten of
# each map's portals and NPCs (289 stands): the picker passes over the pad underfoot in 117 of them, and
# their cost over the cheapest runs 0.2% to 151x. The few-percent cases the owner reports are Utah's Pig
# Farm's t002 (+4.2%) and t006 (+6.1%) toward Utah, and the KB-wide census has nothing at all between
# +6.1% and +8.1%, the one empty gap under the pads that throw the player back to where they started —
# Utah's nine h pads, all landing at its west entrance, at +23.7% and worse, and elsewhere +250% to
# +500%. 7.5% sits in that gap: it clears t006 with room and stays more than three times under the
# cheapest pad that undoes the walk.
PAD_UNDERFOOT_BAND = 0.075
# a pad once named stays named while the player has not really moved (_held_chain, _ask_shortcut): on a map
# with real ground (routes.Graph.standing_platform, terrain.Walk.platform) they are still standing on the
# joined platform the chain was picked from, and a way through its first pad still reaches the spot. What
# counts as "not really moved" is measured per branch, each in its own measure:
# - the real-ground branch: same platform, and the fresh cheapest way beats the held way by no more than
#   terrain.MODEL_RESOLUTION (0.034) of the cheapest cost — the model's own resolution, how much a way's
#   computed cost moves for spots on the same joined platform (terrain rule 9), so within one platform a
#   bigger lead is a real difference and the rival takes over, a smaller one is the model's noise from
#   where on the platform they stand. Reaching a different platform ends the hold at once, however the
#   costs run: the player has really moved, and the fresh cheapest wins.
# - the straight-line branch (no ground in the KB, so no platforms to ask): the flat SHORTCUT_SWITCH_MARGIN
#   below, in shortcut_costs' straight-line measure. Measured on the live KB, 2026-10-14, spots converted
#   to picture fractions exactly as Graph.shortcut_path converts them to map units, fed spot by spot over
#   300x300-unit patches: toward a spot on Marr's Forest (patch about (0, 250), toward (-217, -306), 361
#   spots) a held pad's cost over the cheapest ran to 989 at worst, and on Kerning City (patch about
#   (0, 0), toward (2030, 309)) to 469, the cheapest way's lead over the next way running median 360/149
#   and 90th 507/322 there — so 2200 still clears the whole straight-line tie band.
# A cost through the kept pad past its branch's margin, or no cost through it at all (no way through it
# reaches the spot from here), lets it go; a read the ground cannot place keeps it too (no new answer).
SHORTCUT_SWITCH_MARGIN = 2200
# a different joined platform than the pick's takes over only once the player has arrived on it
# (_ask_shortcut's pending): ARRIVE_READS reads in a row standing on it. Read off the live app,
# 2026-10-14: its minimap reads are set 0.5 s apart (the minimap_scan_interval setting) and the npc
# arrow's re-picks in its log at 13:22:13.660, 13:22:14.603 and 13:22:16.089 stand 0.94 s and 1.49 s
# apart, so a platform the dot only crosses in a fall or a jump — from one tier to the next in
# under a read's span — shows for one read and only one, while a platform the player has landed
# on shows again on the next read. Two in a row is therefore arrival, counted in reads
# themselves: no clock needed.
ARRIVE_READS = 2


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


class _Mark(NamedTuple):
    """A later pad of a chain (PortalDots._chain_marks), in the window's pixels: where its marker goes and the
    order number it carries (2 for the second pad taken, and so on)."""
    at: QPointF
    n: int


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


def _on(settings, name: str) -> bool:
    """One of the player's navigation switches that is on unless they turn it off (minimap_route_follow,
    minimap_route_steps, minimap_path_line); on when the settings can't say, as they default."""
    try:
        value = settings[name]
    except (KeyError, TypeError):
        return True
    return True if value is None else bool(value)


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


def _at_landing(you: tuple[float, float], jump: routes.Jump) -> bool:
    """The player's spot is on a shortcut's landing (Jump.to: where its pad puts them), or within PAD_NEAR of
    it either way, and not back toward the pad: nearer the landing than the pad (Jump.frm), so standing on the
    pad itself never counts as having taken it."""
    return (abs(you[0] - jump.to[0]) <= PAD_NEAR and abs(you[1] - jump.to[1]) <= PAD_NEAR
            and math.dist(you, jump.to) < math.dist(you, jump.frm))


def _on_landing_side(you: tuple[float, float], jump: routes.Jump) -> bool:
    """The player's spot is nearer a shortcut's landing (Jump.to) than its pad (Jump.frm). Geography alone,
    never a witness that the pad was taken — it is true of most of a map for most pads (a player at (0.31,
    0.31) is nearer the landing (0.55, 0.5) than the pad (0.9, 0.9) of a pad they have never touched) — so
    it only counts with one (_ask_shortcut: seen on the pad, or a read that jumped pad to landing), where
    it says the taken pad stays taken, however far past its landing they have walked: Utah's Pig Farm's
    t001 taken and walked on from, at (-1104, -713), is still on the landing side of pad (-1463, -205) and
    landing (-1480, -637) (383 units from the landing, 622 from the pad, far outside PAD_NEAR)."""
    return math.dist(you, jump.to) < math.dist(you, jump.frm)


def _witnessed_take(you: tuple[float, float], last: tuple[float, float] | None, seen: routes.Jump | None,
                    jump: routes.Jump) -> bool:
    """A read witnesses that the player took a named pad (`jump`): they were seen on it (`seen`, _on_pad, on
    an earlier read of this held chain) and this read has them on its landing side (_on_landing_side); or
    their dot moved in one read from its pad's neighbourhood (`last` on it, _on_pad) to its landing
    (_at_landing, PAD_NEAR) — a jump no walk between reads makes. Neither is a spot merely nearer the
    landing than the pad, which most spots are, nor a landing spot reached with no pad read before it."""
    return ((seen is not None and seen.name == jump.name and _on_landing_side(you, jump))
            or (last is not None and _on_pad(last, jump) and _at_landing(you, jump)))


def _standing(graph, here: Here, you: tuple[float, float]) -> tuple[bool, int | None]:
    """Where the player's spot stands, as the graph tells it (routes.Graph.standing_platform): (the map has
    real ground, the joined platform the spot stands on there). A graph that cannot say (a stand-in) has
    no ground for this: (False, None), and the straight-line branch of _held_chain decides."""
    standing = getattr(graph, "standing_platform", None)
    if not callable(standing):
        return False, None
    grounded, platform = standing(here.map, you)
    return bool(grounded), platform


def _held_chain(graph, here: Here, you: tuple[float, float], target: tuple[float, float], chain: list,
                anchor: int | None = None, standing: tuple[bool, int | None] | None = None,
                arrived: bool = False) -> list | None:
    """The chain already named, kept though the cheapest way now starts another way, when the player has
    not really moved and a way through its first pad still reaches the spot from here
    (routes.Graph.shortcut_costs: both costs of that one call, in its one measure). Which measure decides
    is the branch's own (at their constants): on real ground (routes.Graph.standing_platform) the player
    must still stand on the joined platform the chain was picked from (`anchor`, terrain.Walk.platform) —
    a different platform lets it go only once the player has arrived there (`arrived`: that platform
    seen on ARRIVE_READS reads in a row, _ask_shortcut's pending; until then the chain is kept, the
    player only crossing that platform), and none known for the pick lets it go at once, the fresh
    cheapest winning there —
    and on that one platform a fresh rival takes over only when it beats the held way by more than
    terrain.MODEL_RESOLUTION of the cheapest cost, the ground model's own resolution for where on a
    platform a player stands (terrain rule 9); a read the ground cannot place (its platform None) has no
    new answer and keeps the chain. Without ground there are no platforms, so the flat
    SHORTCUT_SWITCH_MARGIN in the straight-line measure decides, as it always has there. None — the
    cheapest way stands — when the graph cannot cost the ways (a stand-in with only Graph.shortcut or
    shortcut_path: its fresh answer has no rival to set it against), or when no way through the named pad
    reaches the spot from here at all (its name missing from the costs: never hold a pad the player
    cannot reach)."""
    costs = getattr(graph, "shortcut_costs", None)
    if not callable(costs):
        return None
    got = costs(here.map, you, target)
    if not got:
        return None
    best, via = got
    kept = via.get(chain[0].name) if isinstance(via, dict) else None
    if kept is None or math.isinf(kept):
        return None
    grounded, platform = standing if standing is not None else _standing(graph, here, you)
    if grounded:
        if platform is None:
            return chain            # the ground cannot place them: no new answer, the named pad stays
        if anchor is None:
            return None             # none known for the pick: the fresh cheapest wins
        if platform != anchor:
            return None if arrived else chain     # arrived there: really moved; only crossing it: kept
        return chain if kept - best <= terrain.MODEL_RESOLUTION * best else None
    return chain if kept - best <= SHORTCUT_SWITCH_MARGIN else None


def _shortcut_path(graph, here: Here, you: tuple[float, float], target: tuple[float, float]) -> list:
    """The pads of the cheapest way across the player's map to `target`, in order (routes.Graph.shortcut_path);
    a graph that only knows Graph.shortcut (a stand-in) gives its one pad, or none. The one search the first pad
    and every later numbered marker come from: no extra routing for the chain."""
    path = getattr(graph, "shortcut_path", None)
    if callable(path):
        return list(path(here.map, you, target) or [])
    jump = graph.shortcut(here.map, you, target)
    return [jump] if jump is not None else []


def _pad_underfoot(graph, here: Here, you: tuple[float, float]) -> routes.Jump | None:
    """The map's hidden teleport the player is standing on (_on_pad, routes.Graph.hidden_jumps), the nearest
    of them when their spot is on more than one; None off every pad, and on a graph that cannot list a map's
    pads (a stand-in). This is the opposite case to a pad witnessed taken (_witnessed_take): there the player
    is past the jump, on its landing side, and here they are on the pad itself, with the jump still to take."""
    jumps = getattr(graph, "hidden_jumps", None)
    if not callable(jumps):
        return None
    under = [j for j in jumps(here.map) or () if _on_pad(you, j)]
    return min(under, key=lambda j: math.dist(you, j.frm)) if under else None


def _underfoot_chain(graph, here: Here, you: tuple[float, float], target: tuple[float, float]) -> list | None:
    """The whole chain to name for the pad the player is standing on (_pad_underfoot): that pad, then the pads
    of the cheapest way on from where it puts them (_shortcut_path from Jump.to), so taking the pad underfoot
    still numbers the markers of everything after it. None when they stand on no pad, when the graph cannot
    cost its ways (a stand-in: nothing to set the pad against), when no way through that pad reaches the spot
    from here at all, or when the way through it costs more than PAD_UNDERFOOT_BAND of the cheapest way over
    it — a pad that would throw them back to where they started is far past that band and stays unnamed."""
    pad = _pad_underfoot(graph, here, you)
    if pad is None:
        return None
    costs = getattr(graph, "shortcut_costs", None)
    if not callable(costs):
        return None
    got = costs(here.map, you, target)
    if not got:
        return None
    best, via = got
    through = via.get(pad.name) if isinstance(via, dict) else None
    if through is None or math.isinf(through) or through - best > PAD_UNDERFOOT_BAND * best:
        return None
    return [pad, *_shortcut_path(graph, here, pad.to, target)]


def _ask_shortcut(graph, here: Here, target: tuple[float, float], kept: tuple) -> tuple:
    """The hidden teleports on the player's own map that cut their walk to a spot on it, in the order they are
    taken (`target`: the way's next step, PortalDots._shortcut; the guided NPC, PortalDots._npc_shortcut), as
    routes.Graph.shortcut_path picks them from their own spot (LOCATION.here.spot, the read's dot): an arrow
    points at the first pad (Jump.frm) then, the later pads get their numbered markers; [] when no teleport beats
    the walk. `kept` is the last chain, the cell of their spot it was asked from (SHORTCUT_CELLS each way;
    None: to be asked), the pad they were seen standing on (`seen`), the pad witnessed taken (`taken`),
    their last spot read (`last`), the joined platform the chain was picked from (`anchor`,
    terrain.Walk.platform by way of routes.Graph.standing_platform; None off ground, or when the ground
    could not place the pick), and a platform not yet arrived on (`pending`: its platform, how many
    reads in a row have stood on it, and the chain its first read offered; None once arrived, back
    on the anchor's platform, or off ground), handed back as they are now — a short `kept` counts
    the rest as none yet:
    asked only with their spot known (a read that didn't see the dot keeps the last chain), and again only
    once a read has it in another of the picture's cells, never for a follow frame, a read a step on or one
    while they stand on the first pad picked (_on_pad), where it stays picked so the arrow never flickers
    between the pad and the spot as their dot jitters about it. The first read off the pad asks again: the
    one that lands them past the jump gets the spot back (or the next pad), that jump saving nothing there.
    A player who has taken nothing — however near some pad's landing their spot happens to be — is asked
    once a cell as ever: no witness, no extra asks.

    A read that asks and finds them standing on some other pad than the one named (_pad_underfoot: any of the
    map's pads, _on_pad) names that pad and the chain on from where it puts them (_underfoot_chain), ahead of
    the cheapest chain and ahead of a held one, while a way through it reaches the spot within
    PAD_UNDERFOOT_BAND of the cheapest way's cost: the walk to it is already paid and it is the one pad they
    can take where they stand, so a way a few percent dearer through it beats a cheaper way starting across
    the map. A pad that would throw them back to where they started costs far more than that band and is
    passed over as it always was. This is the opposite case to a pad witnessed taken — there they are past
    the jump, here they are on it — and it never names a pad given up: the witness lapses only on the pad's
    own side, where this rule looks (_witnessed_take, _on_landing_side). It asks nothing extra per read: the
    cell's one ask decides it, and the read after, still on that pad, is the "standing on the pad picked"
    case above, which asks nothing at all.

    A pad once named stays named while the player has not really moved (_held_chain): a new cell's cheapest chain
    starting another way — or with no pad at all — takes over only once the player has arrived on a
    different joined platform than the pick's (on ground: that platform on ARRIVE_READS reads in a
    row — the first such read keeps the named pad and remembers the chain it offered, the next read
    in a row on that same platform, in its cell or a new one, takes that chain over without asking
    the graph again; a read on any other platform, the anchor's included, or one the ground cannot
    place breaks the row; off ground, only when its way costs more than the flat SHORTCUT_SWITCH_MARGIN
    over the cheapest), on the pick's own platform only when it beats the held way by more than
    terrain.MODEL_RESOLUTION of the cheapest cost, when no way through the named pad reaches
    the spot from here (even from a platform only being crossed: never hold an unreachable pad), or when taking it has been witnessed (_witnessed_take: seen on it and now on its landing side, or a dot moved in one
    read from its neighbourhood to its landing). Then it stays given up while
    they remain on that landing side, however far they walk on past the landing — asked again even in the
    cell the chain was last asked from — the fresh chain deciding there: naming that same pad again only
    when it starts there itself (which clears the witness: a pad named again is a pad to take again, its
    next taking to be witnessed anew), never holding it over a fresh chain that starts elsewhere. Back on
    its pad's side the witness lapses with the side. Nothing is held without a costing (a graph that cannot
    cost its ways keeps the fresh answer, as ever). A new map's or a new guide's chain is asked fresh, its
    caller having forgotten the old one — witness and all — before asking."""
    chain = kept[0]
    cell = kept[1] if len(kept) > 1 else None
    seen = kept[2] if len(kept) > 2 else None
    taken = kept[3] if len(kept) > 3 else None
    last = kept[4] if len(kept) > 4 else None
    anchor = kept[5] if len(kept) > 5 else None
    pending = kept[6] if len(kept) > 6 else None
    you = here.spot
    if you is None:
        return chain, cell, seen, taken, last, anchor, pending
    jump = chain[0] if chain else None
    if jump is not None and _on_pad(you, jump):
        return chain, None, jump, taken, you, anchor, None       # standing on it: seen; kept, first read off it asks again
    if jump is not None and _witnessed_take(you, last, seen, jump):
        taken = jump
    if taken is not None and not _on_landing_side(you, taken):
        taken = None                                # back on its pad's side: the given-up lapses with the side
    given_up = jump is not None and taken is not None and taken.name == jump.name
    now = _cell(you)
    if now == cell and not given_up:
        if pending is not None:
            there, reads, candidate = pending
            grounded, platform = _standing(graph, here, you)
            if grounded and platform == there and reads + 1 >= ARRIVE_READS:
                # arrived (ARRIVE_READS reads in a row here): the remembered chain takes over,
                # asked already, so the per-cell asking still asked the graph only once here
                if taken is not None and candidate and candidate[0].name == taken.name:
                    taken = None                    # named again by that chain itself: not given up
                seen = candidate[0] if candidate and _on_pad(you, candidate[0]) else (
                    seen if seen is not None and candidate and seen.name == candidate[0].name else None)
                return candidate, now, seen, taken, you, platform, None
            pending = ((there, reads + 1, candidate) if grounded and platform == there
                       else None if grounded else pending)     # another platform (or none): the row is broken
        return chain, cell, seen, taken, you, anchor, pending
    fresh = _shortcut_path(graph, here, you, target)
    standing = _standing(graph, here, you)
    grounded, platform = standing
    if not (fresh and _on_pad(you, fresh[0])):
        # a pad under their feet: the one pad they can take without walking anywhere, named ahead of any
        # pad across the map while a way through it stays within PAD_UNDERFOOT_BAND of the cheapest
        under = _underfoot_chain(graph, here, you, target)
        if under is not None:
            return under, now, under[0], taken, you, standing[1], None
    arrived = (pending is not None and grounded and platform is not None and platform == pending[0]
               and pending[1] + 1 >= ARRIVE_READS)
    if (jump is not None and not given_up and grounded and platform is not None and anchor is not None
            and platform != anchor and not arrived):
        held = _held_chain(graph, here, you, target, chain, anchor, standing)
        if held is not None:
            reads = pending[1] + 1 if pending is not None and platform == pending[0] else 1
            return held, now, seen, taken, you, anchor, (platform, reads, fresh)     # only crossing it: remembered, not yet arrived
    if jump is not None and not (fresh and fresh[0].name == jump.name) and not given_up:
        held = _held_chain(graph, here, you, target, chain, anchor, standing, arrived)
        if held is not None:
            return held, now, seen, taken, you, anchor, None
    if taken is not None and fresh and fresh[0].name == taken.name:
        taken = None                                # named again by the fresh chain itself: not given up
    seen = fresh[0] if fresh and _on_pad(you, fresh[0]) else (
        seen if seen is not None and fresh and seen.name == fresh[0].name else None)
    return fresh, now, seen, taken, you, standing[1] if fresh else None, None


def _cell(spot: tuple[float, float] | None) -> tuple[int, int] | None:
    """Which of the picture's cells the player's dot falls in (SHORTCUT_CELLS each way), the measure every search
    this window pays for is asked by: their dot moves a little on every read and not at all between, so a cell it
    has not left is an answer already given. None without a dot read."""
    return None if spot is None else (int(spot[0] * SHORTCUT_CELLS), int(spot[1] * SHORTCUT_CELLS))


def _ask_path(graph, here: Here, target: tuple[float, float], kept: tuple) -> tuple:
    """The walking path from the player's own dot to a spot on their map (routes.Graph.walk_path: its points on the
    minimap picture, how each was reached and a pad's name), for the line drawn under the arrow that guides there
    (PortalDots._path_segs). `kept` is the last path and what it was asked for — (the map, the spot, the cell of
    their dot) — handed back as they are now: a ground search costs about what a pad chain's does, so it is asked
    on the same measure (_cell) and never for a follow frame, which leaves what it drew in place. [] from a graph
    that cannot answer one (an older stand-in) and from ground that has no way."""
    key = (here.map, target, _cell(here.spot))
    if key == kept[0]:
        return kept
    walk = getattr(graph, "walk_path", None)
    return key, (walk(here.map, here.spot, target) if walk is not None else [])


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
    takes a click, the focus, or a place in the minimap reads. The route's arrow points at its way's next step, or at
    the first pad of a hidden-teleport chain on the player's map that cuts the walk there (_next_step, _shortcut),
    its later pads numbered in order (_chain_marks): the way routed once for the player's map, the route's map and
    the switches, and the chain from that same cached answer, no extra routing a frame. The guided NPC's points at
    the NPC, or likewise at the first pad of a chain that cuts the walk to it (_npc_shortcut: the hidden teleport's
    words with the NPC's name beside it, the ring staying on the NPC), its later pads numbered too, its pick kept
    for the guide and the switch. Either chain is asked only with the Hidden teleport routes switch on and the
    player's dot read, and again only as that dot moves from cell to cell, never while they stand on its first pad
    (_ask_shortcut). Each refresh takes the arrows' look from the settings: the route's colour
    (minimap_arrow_color; the guided NPC's is the ring's green, whatever is picked), their size
    (minimap_arrow_size), the name beside each (minimap_arrow_label, in the language the app's settings pick: the
    window is made without one) and their blink (minimap_arrow_flash): one timer on the window hiding and showing
    both arrows, their names and their chains' numbered markers alone every FLASH_MS, together, while either is
    placed and the setting is on. The guided NPC's is drawn over the route's. Under each arrow its walking path is
    drawn (minimap_path_line, _ask_path, _path_segs: routes.Graph.walk_path toward that arrow's own spot, asked on
    the cell the pad chains are asked on and placed afresh each refresh, its pieces broken where the part shown
    ends and a pad's hop dotted). Under the box a strip says where the player is heading and how many maps are
    still to go (minimap_route_steps, _steps_words, _make_strip) from the journey this window works out and
    publishes at the arrow's own cache point (_journey, LOCATION.journey): the window grows by exactly that
    strip's height, down from its top-left — or up, with the marks drawn that much down (_shift), for a minimap at
    the foot of its screen — so every mark over the box lands where it did. With Guide the whole way off
    (minimap_route_follow) the route's arrow guides only on the map it was armed on and goes quiet, journey,
    strip and all, once the player leaves it."""

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
        # ... and its shortcut chain through hidden teleports on the player's map while one cuts the walk to that
        # step (_shortcut: its first pad, where the arrow points, kept as _arrow_jump too), with the cell of their
        # spot it was last asked from (SHORTCUT_CELLS; None: to be asked), the pad they were seen standing on
        # and the one witnessed taken and their last spot read (_ask_shortcut's kept, all forgotten with a new
        # way), and the later pads' numbered markers placed from it at each refresh (_chain_marks: _arrow_marks)
        self._arrow_jump: routes.Jump | None = None
        self._arrow_chain: list[routes.Jump] = []
        self._arrow_marks: list[_Mark] = []
        self._jump_cell: tuple[int, int] | None = None
        self._arrow_seen: routes.Jump | None = None
        self._arrow_taken: routes.Jump | None = None
        self._arrow_last: tuple[float, float] | None = None
        self._arrow_platform: int | None = None
        self._arrow_pending: tuple | None = None     # a platform not yet arrived on (_ask_shortcut's pending)
        self._arrow_said: tuple | None = None   # what the log last said about the arrow's placing (_say)
        # the map the route was armed on, as (the map picked, the player's map then): with Guide the whole way off
        # (minimap_route_follow) the arrow guides on that map alone and goes quiet once they leave it
        self._armed: tuple[str, str] | None = None
        # what the journey last published to LOCATION was worked out for (_journey: the player's map, the map
        # picked and the switches; None while the arrow guides nothing), so a follow frame publishes nothing
        self._journey_key: tuple[str, str, bool, bool] | None = None
        # the walking path drawn under each arrow (minimap_path_line, _ask_path): what routes.Graph.walk_path last
        # answered toward the arrow's spot and what it was asked for (the map, that spot, the cell of the player's
        # dot), and the segments placed from it at each refresh (_path_segs), each (from, to, a teleport's hop)
        self._path_key: tuple | None = None
        self._path_pts: list = []
        self._path: list[tuple[QPointF, QPointF, bool]] = []
        self._npc_path_key: tuple | None = None
        self._npc_path_pts: list = []
        self._npc_path: list[tuple[QPointF, QPointF, bool]] = []
        self._ratio = 1.0
        # the arrows' look, from the settings at each refresh: how many times their drawn size (_size_scale), and
        # the route's fill and rim (_arrow_colors; the guided NPC's are always the ring's, RING_FILL and RING_RIM)
        self._arrow_scale = 1.0
        self._arrow_fill, self._arrow_rim = _arrow_colors(settings)
        self._tag: _Tag | None = None   # the name beside the route's arrow (_make_tag) while placed, its setting on
        # the strip under the minimap box while the journey has something to say (_make_strip), and how far down
        # the box's own marks are drawn for it (0 unless the strip had to go above the box)
        self._strip: _Strip | None = None
        self._shift = 0.0
        # the guided NPC's arrow, placed as the route's is (_aim): on the NPC, inside the ring, or on the pad of a
        # hidden teleport that cuts the walk there (_npc_shortcut), or while the part shown hasn't it, its tip at the
        # panel's edge; its turn from pointing down, which it is, the name beside it, and what the log last said
        # about its placing (_say)
        self._npc_arrow: QPointF | None = None
        self._npc_arrow_angle = 0.0
        self._npc_arrow_edge = False
        self._npc_tag: _Tag | None = None
        self._npc_said: tuple | None = None
        # ... and its shortcut chain, as the route's (_npc_shortcut): what it was asked for (the guide, its map, the
        # NPC's spot and key, and the Hidden teleport routes switch), the pads picked while they cut the walk to the
        # NPC (its first kept as _npc_jump too), the later pads' numbered markers (_npc_marks), the cell of the
        # player's spot it was last asked from (SHORTCUT_CELLS; None: to be asked), and as the route's the pad
        # seen stood on, the one witnessed taken and their last spot read (all forgotten for a new guide)
        self._npc_key: tuple | None = None
        self._npc_jump: routes.Jump | None = None
        self._npc_chain: list[routes.Jump] = []
        self._npc_marks: list[_Mark] = []
        self._npc_cell: tuple[int, int] | None = None
        self._npc_seen: routes.Jump | None = None
        self._npc_taken: routes.Jump | None = None
        self._npc_last: tuple[float, float] | None = None
        self._npc_platform: int | None = None
        self._npc_pending: tuple | None = None       # as the route's, for the guided NPC's chain
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
        self._journey_key = None    # ... the journey worked out again
        self._path_key = self._npc_path_key = None      # ... and the walking paths asked again
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
        # the walking path under each arrow, toward what that arrow guides to (the way's next step, the NPC
        # itself: the trail is the whole walk, pads and all, not the walk to a pad): asked by the cell of the
        # player's dot, as the pad chains are, so a follow frame asks nothing (_ask_path)
        line = _on(self._settings, "minimap_path_line")
        self._path_key, self._path_pts = (_ask_path(graph, here, leg.spot, (self._path_key, self._path_pts))
                                          if leg is not None and line else (None, []))
        self._npc_path_key, self._npc_path_pts = (
            _ask_path(graph, here, guide[1], (self._npc_path_key, self._npc_path_pts)) if npc and line else (None, []))
        scale = _size_scale(self._settings)     # the edge arrow's room in the panel depends on its size
        aim = _aim(view, jump.frm if jump is not None else leg.spot, here.spot, scale) if leg is not None else None
        npc_aim = _aim(view, npc_jump.frm if npc_jump is not None else guide[1], here.spot, scale) if npc else None
        what = f"the hidden teleport {jump.name}" if jump is not None else "its next step"
        self._arrow_said = _say("route arrow", what, (self._arrow_key, jump), aim, self._arrow_said)
        what = f"the hidden teleport {npc_jump.name}" if npc_jump is not None else "the NPC"
        self._npc_said = _say("npc arrow", what, (guide, npc_jump), npc_aim, self._npc_said)
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
        self._arrow_fill, self._arrow_rim = _arrow_colors(self._settings)
        # the names beside them, with their setting on: placed by the arrows just placed, inside the panel shown
        label = self._settings["minimap_arrow_label"]
        self._tag = (self._make_tag(_tag_words(graph, leg, jump), aim, view.panel)
                     if aim is not None and label else None)
        self._npc_tag = (self._make_tag(_npc_words(self._kb, guide[2], npc_jump), npc_aim, view.panel)
                         if npc_aim is not None and label else None)
        # the later pads of each arrow's chain, numbered in order: only the ones the part shown has, and none the
        # arrow's name pill would cover (_chain_marks); a one-pad chain (or none) has none
        self._arrow_marks = self._chain_marks(view, self._arrow_chain, self._tag) if aim is not None else []
        self._npc_marks = self._chain_marks(view, self._npc_chain, self._npc_tag) if npc_aim is not None else []
        # ... and each arrow's path laid on the box, broken wherever the part shown hasn't a point (_path_segs)
        self._path = self._path_segs(view, self._path_pts) if aim is not None else []
        self._npc_path = self._path_segs(view, self._npc_path_pts) if npc_aim is not None else []
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

    def _next_step(self, graph, here: Here) -> tuple[routes.Leg, routes.Jump | None] | None:
        """The first step of the way to the map the player picked (LOCATION.route_dest) when it has a spot on their
        map's minimap picture: its portal or NPC (routes.Leg.spot) and what the name beside the arrow says
        (_tag_words); with it the first pad of the hidden-teleport chain on their own map that cuts the walk there
        (_shortcut: its pad, where the arrow points then, the chain kept in _arrow_chain for its numbered markers),
        None when none does. The way on foot, or with cabs and NPC teleports when the toolbar's switch says so
        (settings["game_rides"]), through the hidden teleports where they make it shorter when the player allows
        them (settings["route_hidden_teleports"], which the shortcut needs too: off, never a pad), as the search's
        page and the ◎ window draw it. None with the arrow's setting off, no route picked or already on its map, no
        way known, or a first step with no spot on the minimap — and, with Guide the whole way off
        (minimap_route_follow), once the player has left the map the route was armed on: the arrow guides there and
        nowhere else then, while on (the default) the map they picked stands and the way is worked out from
        wherever they now are. Routed only when the player's map, the route's map
        or a switch changes, the step kept for the refreshes after (set_kb forgets it) and its shortcut asked anew:
        refresh runs on the GUI thread for every follow frame while the minimap scrolls, and Graph.route is a
        Dijkstra search over the whole map graph. The journey behind the count beside the arrow is published at that
        same point and on that same key (_journey)."""
        dest = LOCATION.route_dest
        rides, hidden = _switch(self._settings, "game_rides"), _switch(self._settings, "route_hidden_teleports")
        if not dest:
            self._armed = None
        elif self._armed is None or self._armed[0] != dest:
            self._armed = (dest, here.map)      # armed here: the map it guides on with Guide the whole way off
        quiet = self._armed is not None and here.map != self._armed[1] and not _on(self._settings,
                                                                                   "minimap_route_follow")
        self._journey(graph, here, dest, rides, hidden,
                      bool(dest) and bool(self._settings["minimap_route_arrow"]) and not quiet)
        if not self._settings["minimap_route_arrow"] or not dest or dest == here.map or quiet:
            return None
        key = (here.map, dest, rides, hidden)
        if key != self._arrow_key:
            route = getattr(graph, "route", None)     # a stand-in graph that can't route (an older test's): no arrow
            way = route(here.map, dest, taxi=rides, teleport=rides, hidden=hidden) if route is not None else None
            leg = way.legs[0] if way is not None and way.legs else None
            self._arrow_key, self._arrow_leg = key, leg if leg is not None and leg.spot is not None else None
            self._arrow_jump, self._arrow_chain, self._jump_cell = None, [], None     # a new way: its chain asked anew
            self._arrow_seen, self._arrow_taken, self._arrow_last, self._arrow_platform, self._arrow_pending = None, None, None, None, None     # ... and no witness kept
            self._arrow_said = None
            log.info("route arrow: to %s, %s", _name(graph, dest),
                     f"next step: {getattr(leg, 'kind', '')} {getattr(leg, 'via', '')}".strip()
                     if leg is not None and leg.spot is not None
                     else "its first step has no spot on this minimap" if leg is not None
                     else "no way known from here")
        leg = self._arrow_leg
        if leg is None:
            return None
        if not hidden:
            self._arrow_jump, self._arrow_chain = None, []
            self._arrow_seen, self._arrow_taken, self._arrow_last, self._arrow_platform, self._arrow_pending = None, None, None, None, None
            return leg, None
        return leg, self._shortcut(graph, here, leg)

    def _journey(self, graph, here: Here, dest: str | None, rides: bool, hidden: bool, guiding: bool) -> None:
        """Work out the whole way from the player's CURRENT map to the map they picked (journey.of: its legs from
        here, how many maps are still to go, and whether they strayed off the way it last knew) and publish it for
        everyone who shows it — the strip under this window's own box first of all (_steps_words, _make_strip,
        LOCATION.journey). Nobody else writes it. Worked out where the arrow's own step is worked out and on the
        same key (the player's map, the map picked, the switches), so the follow frames between reads publish
        nothing and nothing new is searched a frame; cleared (None) whenever the arrow guides nothing: no route
        picked, its setting off, or the player off the map it was armed on with Guide the whole way off."""
        key = (here.map, dest, rides, hidden) if guiding and dest else None
        if key == self._journey_key:
            return
        self._journey_key = key
        LOCATION.set_journey(journey.of(graph, here.map, dest, rides=rides, hidden=hidden, last=LOCATION.journey)
                             if key is not None else None)

    def _shortcut(self, graph, here: Here, leg: routes.Leg) -> routes.Jump | None:
        """The first pad of the hidden-teleport chain on the player's own map that cuts their walk to the way's next
        step (`leg`), as _ask_shortcut picks the chain from their own spot: the route's arrow points at its first
        pad (Jump.frm) then, its later pads kept in _arrow_chain for their numbered markers, and the name beside it
        says it takes them toward the step's map; None when no teleport beats the walk. The log says when the arrow
        takes a shortcut — how many pads its chain has, when more than one — and when it goes back to the step. Kept
        with the way: _next_step asks anew for a new one."""
        kept = (self._arrow_chain, self._jump_cell, self._arrow_seen, self._arrow_taken, self._arrow_last,
                self._arrow_platform, self._arrow_pending)
        (chain, self._jump_cell, self._arrow_seen, self._arrow_taken, self._arrow_last, self._arrow_platform,
         self._arrow_pending) = _ask_shortcut(graph, here, leg.spot, kept)
        jump = chain[0] if chain else None
        if chain != self._arrow_chain:
            log.info("route arrow: %s", f"pointing at a shortcut, the hidden teleport {jump.name} toward "
                     f"{_name(graph, leg.to)}" + (f", the first of {len(chain)} pads" if len(chain) > 1 else "")
                     if jump is not None else "no shortcut from here, pointing at its next step")
        self._arrow_chain, self._arrow_jump = chain, jump
        return jump

    def _npc_shortcut(self, graph, here: Here, guide: tuple) -> routes.Jump | None:
        """The first pad of the hidden-teleport chain on the player's own map that cuts their walk to the guided NPC
        (`guide`: its map, the NPC's spot and key, LOCATION.guide on their map), as _ask_shortcut picks the chain
        from their own spot, the same as for the route's step (_shortcut): the NPC's arrow points at its first pad
        (Jump.frm) then, its later pads kept in _npc_chain for their numbered markers, the ring staying on the NPC,
        and the name beside it says it takes them toward the NPC (_npc_words). None when no teleport beats the walk,
        and with the Hidden teleport routes switch off (settings["route_hidden_teleports"]: the arrow on the NPC as
        ever, the graph never asked). Kept for the guide and the switch, asked anew for another guide or the switch
        flipped (set_kb forgets it too), and in between as the route's is: never for a follow frame, a read a step on
        or one while they stand on the first pad. The log says when the arrow takes a shortcut — how many pads its
        chain has, when more than one — and when it goes back to the NPC."""
        hidden = _switch(self._settings, "route_hidden_teleports")
        if (guide, hidden) != self._npc_key:
            self._npc_key, self._npc_jump, self._npc_chain, self._npc_cell = (guide, hidden), None, [], None
            self._npc_seen, self._npc_taken, self._npc_last, self._npc_platform, self._npc_pending = None, None, None, None, None     # a new guide: no witness kept
        if not hidden:
            self._npc_jump, self._npc_chain = None, []
            self._npc_seen, self._npc_taken, self._npc_last, self._npc_platform, self._npc_pending = None, None, None, None, None
            return None
        kept = (self._npc_chain, self._npc_cell, self._npc_seen, self._npc_taken, self._npc_last,
                self._npc_platform, self._npc_pending)
        (chain, self._npc_cell, self._npc_seen, self._npc_taken, self._npc_last, self._npc_platform,
         self._npc_pending) = _ask_shortcut(graph, here, guide[1], kept)
        jump = chain[0] if chain else None
        if chain != self._npc_chain:
            log.info("npc arrow: %s", f"pointing at a shortcut, the hidden teleport {jump.name} toward "
                     f"{_npc_name(self._kb, guide[2])}" + (f", the first of {len(chain)} pads" if len(chain) > 1 else "")
                     if jump is not None else "no shortcut from here, pointing at the NPC")
        self._npc_chain, self._npc_jump = chain, jump
        return jump

    def _chain_marks(self, view: View, chain: list, tag: _Tag | None) -> list[_Mark]:
        """The later pads of an arrow's chain (`chain`, _shortcut or _npc_shortcut), numbered from 2, as markers to
        draw at this refresh: every later pad, however many the chain has, each only when the part of the minimap
        shown has its spot (View.at), and left out when the arrow's name pill (`tag`, when its setting placed one)
        would cover its marker — the pill already names the way, and a number under it would only clutter the
        minimap. From the chain the one search already picked: no routing here."""
        marks: list[_Mark] = []
        r = CHAIN_MARK_PX / 2 / self._ratio
        for n, jump in enumerate(chain[1:], start=2):
            at = view.at(jump.frm)
            if at is None:
                continue
            mark = _Mark(QPointF(at[0] / self._ratio, at[1] / self._ratio), n)
            if tag is not None and QRectF(mark.at.x() - r, mark.at.y() - r, 2 * r, 2 * r).intersects(tag.rect):
                continue
            marks.append(mark)
        return marks

    def _path_segs(self, view: View, pts: list) -> list[tuple[QPointF, QPointF, bool]]:
        """The walking path (`pts`, _ask_path) as the pieces of line to draw at this refresh, in the window's
        pixels: one per step from the point before it, and only while the part of the minimap shown has both its
        ends (View.at) — a point off it drops its pieces, so the line breaks clean at the panel instead of cutting
        a stroke across it. A "pad" step is marked as the hop it is (its teleport, from the pad to where it lands),
        for the dotted mark _draw_path gives it: a teleport is a jump in the line, never a walk across the map.
        From the one path already asked for: no search here."""
        segs: list[tuple[QPointF, QPointF, bool]] = []
        last: QPointF | None = None
        for spot, kind, _n in pts:
            at = view.at(spot)
            now = QPointF(at[0] / self._ratio, at[1] / self._ratio) if at is not None else None
            if last is not None and now is not None:
                segs.append((last, now, kind == "pad"))
            last = now
        return segs

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
        self._arrow_marks = []
        self._path = []
        self._npc_arrow = None
        self._npc_arrow_angle = 0.0
        self._npc_arrow_edge = False
        self._npc_tag = None
        self._npc_marks = []
        self._npc_path = []
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
        """The flash timer's beat: both arrows, their names, their chains' numbered markers, their walking paths
        and the strip under the box hidden, or shown again (they alone: the dots and the ring stay)."""
        self._flash_on = not self._flash_on
        self.update()

    def paintEvent(self, e) -> None:
        shown = self._flash_on      # blinking (_flash): both arrows, their names, chain markers, paths and the
        route = shown and self._arrow is not None       # strip under the box, out and in every other beat
        npc = shown and self._npc_arrow is not None
        strip = self._strip if shown else None
        if not self._dots and self._ring is None and not route and not npc and strip is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if strip is not None:
            self._draw_strip(p, strip)
        # ... and everything else measured from the box's own top-left, wherever the strip left the window's
        p.translate(0.0, self._shift)
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
        # each arrow's trail first, under its arrow and its numbered markers: the line is never to be read over the
        # instruction, and it blinks with it
        if route:
            self._draw_path(p, self._path, self._arrow_fill)
        if npc:
            self._draw_path(p, self._npc_path, RING_FILL)
        if route:
            self._draw_arrow(p, self._arrow, self._arrow_angle, self._arrow_edge, self._tag, self._arrow_fill,
                             self._arrow_rim)
            for mark in self._arrow_marks:
                self._draw_mark(p, mark, self._arrow_fill, self._arrow_rim)
        if npc:     # over the route's where they meet, in the ring's green: it reads as the NPC, never as a step
            self._draw_arrow(p, self._npc_arrow, self._npc_arrow_angle, self._npc_arrow_edge, self._npc_tag,
                             RING_FILL, RING_RIM)
            for mark in self._npc_marks:
                self._draw_mark(p, mark, RING_FILL, RING_RIM)
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

    def _draw_mark(self, p: QPainter, mark: _Mark, fill: QColor, rim: QColor) -> None:
        """One later pad's numbered marker (paintEvent), in its arrow's colours: a smaller bright disc on its dark
        rim (CHAIN_MARK_PX across), its order number in the rim inside it — the pill's dark-on-bright treatment, so
        the number reads on a busy minimap. Drawn and left out with its arrow (paintEvent's beat)."""
        r = CHAIN_MARK_PX / 2 / self._ratio
        p.setPen(QPen(rim, 1.0 / self._ratio))
        p.setBrush(fill)
        p.drawEllipse(mark.at, r, r)
        font = theme.app_font(max(1, round(TAG_FONT_MIN_PX / self._ratio)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(rim)
        p.drawText(QRectF(mark.at.x() - r, mark.at.y() - r, 2 * r, 2 * r), Qt.AlignCenter, str(mark.n))

    def _draw_path(self, p: QPainter, segs: list, fill: QColor) -> None:
        """One arrow's walking path (paintEvent, _path_segs): a line along its points in the arrow's own fill,
        thinner than the arrow and PATH_ALPHA see-through, so it reads as the trail under the instruction. Each
        piece drawn on its own, so a point the part shown hasn't leaves a clean break and no stroke across the
        panel; a teleport's hop is dotted, the jump in the line it is."""
        if not segs:
            return
        colour = QColor(fill)
        colour.setAlphaF(PATH_ALPHA)
        pen = QPen(colour, PATH_PEN_PX / self._ratio)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setBrush(Qt.NoBrush)
        for a, b, pad in segs:
            pen.setStyle(Qt.DotLine if pad else Qt.SolidLine)
            p.setPen(pen)
            p.drawLine(a, b)

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
