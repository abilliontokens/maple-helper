"""Where the player is right now, read from the game's minimap every few seconds (ui/minimapscan.py): the chat's
character card says it under the level, and the map windows draw the way from there."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..minimap import Here


class _Location(QObject):
    """The latest read. `changed` fires only when it differs (the map, or the player's dot moved). `followed` is the
    fast follow between reads (ui/minimapscan.py): where the last aligned map's picture lies in the box now, as
    (map, View | None), None when it no longer matches (another map, the loading screen). `guided` is the NPC the
    player asked to be guided to (ui/npcoverlay.py), as (map, spot on its minimap picture, NPC key) or None; the
    game-minimap overlay (ui/portaldots.py) rings it. `routed` (`route_dest`) is the map the player picked a route
    to, as its routes.Graph id (like "010003000") or None; the same overlay puts an orange arrow at the next portal
    or NPC on the way there. `boxed` is where the game's minimap window is on screen now, the box the reads and the
    follow grab ({"x","y","w","h"} in capture pixels), found on its own at the game's top left; None while it isn't
    there."""

    changed = Signal(object)          # Here | None
    status = Signal(str)              # "" (no read yet, or recognized), "unknown" (read, not recognized)
    followed = Signal(object)         # (map, View | None)
    guided = Signal(object)           # (map, (fx, fy), "npc/<id>") | None
    routed = Signal(object)           # str | None (destination map id)
    boxed = Signal(object)            # {"x","y","w","h"} | None

    def __init__(self):
        super().__init__()
        self.here: Here | None = None
        self.state = ""
        self.follow: tuple | None = None
        self.guide: tuple | None = None
        self.route_dest: str | None = None
        self.box: dict | None = None

    def set(self, here: Here | None) -> None:
        if here != self.here:
            self.here = here
            self.changed.emit(here)

    def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.status.emit(state)

    def set_follow(self, follow: tuple | None) -> None:
        if follow != self.follow:
            self.follow = follow
            self.followed.emit(follow)

    def set_guide(self, guide: tuple | None) -> None:
        if guide != self.guide:
            self.guide = guide
            self.guided.emit(guide)

    def set_route_dest(self, dest: str | None) -> None:
        if dest != self.route_dest:
            self.route_dest = dest
            self.routed.emit(dest)

    def set_box(self, box: dict | None) -> None:
        if box != self.box:
            self.box = box
            self.boxed.emit(box)


LOCATION = _Location()
