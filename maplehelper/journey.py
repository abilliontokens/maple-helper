"""The way from where the player is standing right now to the map they are heading to.

A route (routes.Graph.route) is worked out once, from the map the player was on when they asked. The player then
walks: every read of the game's minimap (ui/minimapscan.py) says which map they are on now, and the way has to be
the way from *there* — one map fewer each time a portal is taken. `of` keeps that honest by holding the answer it
gave last beside the map the player is on now:

- the player's map is the one the last answer's first step led to: they took that step, so the rest of the legs are
  the way, one map shorter, and nothing was worked out again (`off` False). Standing still (still on the map the
  first step leaves from) is the same: the way has not changed.
- the player's map is anywhere else (a wrong portal, a hidden teleport, a cab, a scroll back to town): the old way
  says nothing about where they are, so a new one is worked out from their map, and `off` says so.
- no way at all from their map (or the graph never heard of one of the two maps): None, so what the player is shown
  is nothing rather than a way that no longer leads anywhere.

Pure: no Qt, no settings, no logging. One Graph.route call per answer at most, and none at all on the destination
map itself. The caller (ui/portaldots.py, where the route arrow works out its step) publishes what comes back with
LOCATION.set_journey.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Journey:
    """The way from the player's current map, as last worked out."""
    dest: str                 # the map the player is heading to
    legs: tuple               # routes.Leg, the way from the player's CURRENT map
    left: int                 # how many maps still to pass through (len(legs))
    off: bool                 # the player's map was not on the way as last known: this was worked out afresh
    arrived: bool             # the player is on the destination map


def _on_way(last: Journey | None, dest: str, here_map: str) -> bool:
    """Whether the map the player is on now is where the last answer left them: the map its first step leads to, or
    the one it leaves from (they have not moved yet). A first answer, or one to another destination, is neither."""
    if last is None or last.dest != dest or not last.legs:
        return False
    first = last.legs[0]
    return here_map in (first.to, first.frm)


def of(graph, here_map: str, dest: str, *, rides: bool, hidden: bool,
       last: Journey | None = None) -> Journey | None:
    """The way from `here_map` to `dest` for a player standing there, or None when there is none (or the graph does
    not know one of the maps). `rides` lets the way take cabs and the NPCs who carry the player somewhere; `hidden`
    lets it take a teleport the game's minimap never draws. `last` is the answer given before, which decides `off`."""
    if not here_map or not dest:
        return None
    if here_map == dest:
        return Journey(dest=dest, legs=(), left=0, off=False, arrived=True)
    off = last is not None and last.dest == dest and not _on_way(last, dest, here_map)
    route = graph.route(here_map, dest, taxi=rides, teleport=rides, hidden=hidden)
    if route is None or not route.legs:
        return None
    legs = tuple(route.legs)
    return Journey(dest=dest, legs=legs, left=len(legs), off=off, arrived=False)
