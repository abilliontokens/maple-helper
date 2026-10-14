"""Where the player is, refreshed every few seconds from the game's minimap.

Every read finds the minimap first: the game's MINI MAP window always sits at the top left of the game's picture
(gamearea.GameArea), so one grab of that corner and minimapfind.find_window place it, whatever its size (it changes
with the map, and folds to its title strip inside a building). With no game window, or no minimap window in it,
there is nothing to read. The box a read used goes to LOCATION.box: the windows over the game place themselves by it.

A QTimer ticks on the GUI thread; the read itself (finding the window, the screenshot, then reading the minimap's
title for the map and aligning its picture for the dot) runs on a worker thread, so the chat never freezes on it.
The answer comes back through a signal, and the chat's character card and the map windows read it from
ui/location.LOCATION.

Between reads, while something draws on the game's minimap (the hidden-portal dots, the route's arrow, or the guided
NPC's ring), a fast follow (back to back while the minimap moves, every FOLLOW_IDLE_MS while it is still; no OCR)
grabs the last read's box and tracks where the aligned map's picture lies in it as the game scrolls the minimap, and
says at once when it stops matching (a teleport, the loading screen): LOCATION.followed. That loss starts a whole read
right away."""
from __future__ import annotations

import logging
import math
import threading
import time

from PIL import Image
from PySide6.QtCore import QObject, QTimer, Signal

from .. import capture, minimap, minimapfind, routes
from ..gamearea import GameArea
from ..kb import KnowledgeBase
from ..store import Settings
from .location import LOCATION

log = logging.getLogger("maplehelper")

MIN_INTERVAL = 0.2      # s: faster only burned CPU rereading the same picture
MAX_INTERVAL = 60.0     # s: slower, and the "where you are" line went stale
DEFAULT_INTERVAL = 1.0  # s, the setting's own default (store.DEFAULT_SETTINGS)
CONFIRM = 2             # reads in a row that must name a new map before the player counts as moved
FOLLOW_IDLE_MS = 150    # the fast follow's period while the minimap stands still; while it moves, each follow's answer
                        # starts the next (~20 ms apart): every 100 ms, then 50, the dots trailed each scroll step by
                        # 60 ms, snapping after it, and a jump read as the dots bouncing (live)
FOLLOW_HOLD_S = 1.0     # ... back to back until the minimap has stood still this long: the game scrolls it in 2-8 px
                        # steps, often a few hundred ms apart mid-jump
CORNER_W, CORNER_H = 0.6, 0.75  # the part of the game's picture searched for its minimap window: its left 60% and top
                                # 75% (the window always sits at the game's top left; one grab of that corner per read)


def _window_box(found: tuple[int, int, int, int], rect: tuple[int, int, int, int],
                size: tuple[int, int]) -> tuple[dict, tuple[int, int, int, int]]:
    """A window found at `found` (x, y, w, h in the pixels of a grab of the capture rect `rect`, a picture of `size`)
    as a box in capture pixels, with the part of the grab it covers. The edges are rounded to capture pixels first,
    so that part is the very picture a grab of the box alone gives (a Retina grab has more pixels than points): the
    fast follow grabs the box alone and only matches a picture of the read's size."""
    x, y, w, h = rect
    sx, sy = w / size[0], h / size[1]
    fx, fy, fw, fh = found
    left, top, right, bottom = round(fx * sx), round(fy * sy), round((fx + fw) * sx), round((fy + fh) * sy)
    return ({"x": x + left, "y": y + top, "w": right - left, "h": bottom - top},
            (round(left / sx), round(top / sy), round(right / sx), round(bottom / sy)))


class MinimapScanner(QObject):
    """Reads the game's minimap every few seconds (its window, found at the game's top left) and reports it through
    LOCATION, with the box read.

    The Locator is built lazily once per KB and kept between reads (it holds the OCR engine, the header rows and
    its lock on the picture); a KB update drops it so the next read rebuilds it, and a read of another box than the
    last one (a map change resizes the window) drops its lock. A read still going when the timer ticks skips that
    tick (no pile-up). A read with no recognizable title, or nothing to read, backs off (a wasted read costs most of
    a second of CPU); a hit reads every interval again, as does a restart (a new interval)."""

    _found = Signal(object, object)   # (Here | None, the box read | None): a read's answer, from the worker thread
    _failed = Signal(str, object)     # a read's error as text ("Kind: message") and the box it had found (or None)
    _followed = Signal(object)        # a fast follow's answer: (map, View | None) | None, from the worker thread

    def __init__(self, kb: KnowledgeBase, settings: Settings, parent=None):
        super().__init__(parent)
        self._kb = kb
        self._settings = settings
        self._locator: minimap.Locator | None = None
        self._graph: routes.Graph | None = None
        self._box: dict | None = None         # the box the last read used, published; the fast follow grabs it
        # the reads' own, worker thread only (one read at a time): the game's picture, the last box read (another
        # one drops the locator's lock), and what was logged (a game window there, the minimap window's last size)
        self._game = GameArea()
        self._read_box: dict | None = None
        self._game_seen = False
        self._window_size: tuple[int, int] | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._follow_timer = QTimer(self)
        self._follow_timer.timeout.connect(self._follow_tick)
        self._following = False               # a fast follow is running (under _guard, like _reading)
        self._follow_lost = False             # the last follow lost the picture (one whole read per loss)
        self._moved_at = -math.inf            # monotonic time the last follow found the minimap moved
        self._guard = threading.Lock()
        self._reading = False
        self._cooldown_until = 0.0    # monotonic deadline before the next read (0: no backoff)
        self._miss_since: float | None = None   # when the current run of misses began (None: the last read hit)
        self._last_map: str | None = None     # the last map logged at INFO (None: none yet)
        self._logged_errors: set[str] = set()  # error texts already logged: each distinct one logs once
        self._pending: tuple[str | None, int] = (None, 0)   # another map read, and how many reads in a row
        self._miss_logged = False             # the current run of misses was logged once already
        self._found.connect(self._deliver)
        self._failed.connect(self._complain)
        self._followed.connect(self._on_followed)

    def set_kb(self, kb: KnowledgeBase) -> None:
        """A KB update: the locator is rebuilt from it on the next read."""
        self._kb = kb
        self._locator = None
        self._graph = None

    def reset_locator(self) -> None:
        """Drop the locator's lock on the picture (another box read, a restart): the next read locks on again."""
        if self._locator is not None:
            try:
                self._locator.reset()
            except Exception as e:  # noqa: BLE001 - a failed reset just locks on again at the next read
                log.debug("minimap locator reset failed: %r", e)

    def restart(self) -> None:
        """Settings changed (the interval): pick it up, and read right away."""
        self.reset_locator()
        self._cooldown_until = 0.0     # a new interval: read right away, don't keep an old backoff
        self._miss_since = None
        self._pending = (None, 0)
        LOCATION.set_follow(None)
        self._timer.start(int(self._interval() * 1000))
        self._follow_timer.start(FOLLOW_IDLE_MS)

    def stop(self) -> None:
        """No read while the app goes (a read on its way finishes on its own)."""
        self._timer.stop()
        self._follow_timer.stop()

    def _interval(self) -> float:
        """The setting's seconds between reads, inside [MIN_INTERVAL, MAX_INTERVAL]."""
        try:
            interval = float(self._settings["minimap_scan_interval"])
        except (TypeError, ValueError):
            return DEFAULT_INTERVAL
        if not math.isfinite(interval):
            return DEFAULT_INTERVAL
        return min(MAX_INTERVAL, max(MIN_INTERVAL, interval))

    def _tick(self) -> None:
        if time.monotonic() < self._cooldown_until:
            return          # no minimap read lately: a cold search costs seconds of CPU, don't run it every tick
        with self._guard:
            if self._reading:
                return          # the last read is still going: skip this tick, don't pile up
            self._reading = True
        threading.Thread(target=self._read, daemon=True).start()

    def _locator_for(self) -> tuple:
        if self._locator is None:
            self._graph = routes.of(self._kb)
            self._locator = minimap.Locator(self._graph)
        return self._locator, self._graph

    def _read(self) -> None:
        """One read, on the worker thread: the minimap window found at the game's top left. A box other than the last
        one read (a map change resizes the window, the game moved) drops the locator's lock on the picture, once: the
        same box keeps it."""
        box = None
        try:
            locator, _ = self._locator_for()
            found = self._window()
            if found is not None:
                box, img = found
            else:
                img = None          # no minimap window: nothing to read, a miss
            if box is not None and box != self._read_box:
                self._read_box = box
                self.reset_locator()
            here = locator.locate(img) if img is not None else None
        except Exception as e:      # noqa: BLE001 - a bad read is "unknown", never a crash
            with self._guard:
                self._reading = False
            self._failed.emit(f"{type(e).__name__}: {e}", box)
            return
        with self._guard:
            self._reading = False
        self._found.emit(here, box)

    def _window(self) -> tuple[dict, Image.Image] | None:
        """The game's minimap window: its box in capture pixels and its picture, from one grab of the top-left corner
        of the game's picture; None with no game window, or no minimap window in it. The game window coming and going
        logs once, and so does each new size of the minimap window (another map's)."""
        play = self._game.find()
        if (play is not None) != self._game_seen:
            self._game_seen = play is not None
            if play is None:
                log.info("minimap: the game's window is gone")
            else:
                log.info("minimap: found the game's window, its picture at %d,%d (%dx%d)", *play)
        if play is None:
            return None
        x, y, w, h = play
        rect = (x, y, max(1, round(w * CORNER_W)), max(1, round(h * CORNER_H)))
        corner = capture.grab_image(*rect)
        found = minimapfind.find_window(corner)
        if found is None:
            return None
        box, crop = _window_box(found, rect, corner.size)
        if (box["w"], box["h"]) != self._window_size:
            self._window_size = (box["w"], box["h"])
            log.info("minimap: found the minimap window at %d,%d (%dx%d)", box["x"], box["y"], box["w"], box["h"])
        return box, corner.crop(crop)

    def _wants_follow(self) -> bool:
        """The fast follow runs while something on the game's minimap moves with its scroll: the hidden-portal
        dots (the setting on, the player's map has hidden portals), the route's arrow (the setting on, a route picked
        to another map than the player's: LOCATION.route_dest) or the guided NPC's ring (a guide set for the player's
        own map, ui/npcoverlay.py)."""
        here = LOCATION.here
        if here is None or self._graph is None:
            return False
        if self._settings["minimap_hidden_portals"] and self._graph.hidden_spots(here.map):
            return True
        dest = LOCATION.route_dest
        if self._settings["minimap_route_arrow"] and dest and dest != here.map:
            return True
        guide = LOCATION.guide
        return guide is not None and guide[0] == here.map

    def _follow_tick(self) -> None:
        if self._box is None or self._locator is None or not self._wants_follow():
            return
        with self._guard:
            if self._following:
                return          # the last follow is still going: skip this tick
            self._following = True
        threading.Thread(target=self._follow, args=(self._locator, dict(self._box)), daemon=True).start()

    def _follow(self, locator, box: dict) -> None:
        try:
            got = locator.follow(capture.grab_image(box["x"], box["y"], box["w"], box["h"]))
        except Exception as e:      # noqa: BLE001 - a bad follow is no answer; the reads go on
            log.debug("minimap follow failed: %r", e)
            got = None
        with self._guard:
            self._following = False
        self._followed.emit(got)

    def _on_followed(self, got) -> None:
        """A fast follow's answer, back on the GUI thread. Nothing locked (or a failed follow) clears the follow: a
        stale one kept the dots where it last left them while the minimap scrolled on. Losing the picture starts a
        whole read at once (once per loss): it is what names the map the player arrived on."""
        if self._box is None:
            return
        now = time.monotonic()
        if got is not None and got != LOCATION.follow:
            self._moved_at = now
        LOCATION.set_follow(got)
        # a moving minimap is followed back to back until it has stood still a while (the dots trail each scroll
        # step by the time to the next follow), a still one at the timer's gentler pace (each match costs CPU)
        if got is not None and got[1] is not None and now - self._moved_at < FOLLOW_HOLD_S:
            self._follow_tick()
        if got is None:
            return
        lost = got[1] is None
        if lost and not self._follow_lost:
            self._cooldown_until = 0.0
            self._tick()
        self._follow_lost = lost

    def _grace(self) -> float:
        """How long a known map outlives reads that find no title: max(3 s, 3 reads). A single frame can hide it
        (a chat bubble over the header, the loading screen between two maps), and the card flipped to "not
        recognized" and back on its own while the player stood still (live)."""
        return max(3.0, 3.0 * self._interval())

    def _miss(self) -> None:
        """A read with no recognizable title, or nothing to read (no minimap window found). A known map
        is never dropped for it (the owner's, 2026-10-08: the card flipped to "not recognized" and back every few
        seconds and reset the way shown mid-walk): it stays until a read names another map. Misses past the grace (or
        with no map known yet) only slow the reads to max(2 s, 2 x interval) with a map kept, max(5 s, 5 x interval)
        with none: a wasted read costs most of a second of CPU (a try without the game, little, but it need not run
        every second either); without this it ran back-to-back forever. With no map known at all the card says "not
        recognized"."""
        now = time.monotonic()
        if self._miss_since is None:
            self._miss_since = now
        if LOCATION.here is not None and now - self._miss_since < self._grace():
            return
        if LOCATION.here is not None:
            # a known map kept: slow down less, so a real map change after a long run of misses shows soon
            self._cooldown_until = now + max(2.0, 2.0 * self._interval())
            if not self._miss_logged:
                self._miss_logged = True
                log.info("minimap: no title for %.1f s, keeping the last map", now - self._miss_since)
            return
        self._cooldown_until = now + max(5.0, 5.0 * self._interval())
        LOCATION.set_state("unknown")

    def _use_box(self, box: dict | None) -> None:
        """The box a read used, back on the GUI thread (None: no minimap window found): published, and
        grabbed by the fast follow from now on. Another box than the last drops the follow, whose placing was in the
        old one: the read's own placing starts it again in the new one."""
        LOCATION.set_box(box)
        if box != self._box:
            self._box = box
            LOCATION.set_follow(None)

    def _deliver(self, here, box) -> None:
        """A read's answer and the box it read, back on the GUI thread. The box goes out first: what places itself by
        it (the dots, the NPC window) sits on the right box when the answer lands. Another map than the known one
        counts only once CONFIRM reads in a row name it: one misread (the street line read alone, "Victoria Road",
        is a map's name too) must not move the player and reset the way shown."""
        self._use_box(box)
        if here is None:
            self._miss()
            return
        self._miss_since = None
        self._miss_logged = False
        self._cooldown_until = 0.0     # found: back to reading every interval
        known = LOCATION.here
        if known is not None and here.map != known.map:
            seen = self._pending[1] + 1 if self._pending[0] == here.map else 1
            self._pending = (here.map, seen)
            if seen < CONFIRM:
                return
        self._pending = (None, 0)
        LOCATION.set(here)
        LOCATION.set_state("")
        # the dots draw from the follow only: a read that placed its map starts it there when nothing live follows
        # this map yet (the first read, a map just confirmed, a follow that lost it). A live follow is newer than
        # the read's half-second-old picture: overwriting it jumped the dots back mid-walk
        follow = LOCATION.follow
        if here.view is not None and (follow is None or follow[0] != here.map or follow[1] is None):
            LOCATION.set_follow((here.map, here.view))
        if here.map != self._last_map:
            self._last_map = here.map
            try:
                name = self._graph.name(here.map) if self._graph is not None else here.map
            except Exception:  # noqa: BLE001 - a name lookup must not lose the location
                name = here.map
            log.info("minimap: %s", name)

    def _complain(self, error: str, box) -> None:
        """A read's error and the box it had found (None: it failed before one), back on the GUI thread: the box goes
        out as a read's does, the error is logged once per distinct error, then a miss like an unrecognized read
        (often the same cause)."""
        self._use_box(box)
        if error not in self._logged_errors:
            if len(self._logged_errors) > 100:
                self._logged_errors.clear()     # pathological: new errors every read must not grow forever
            self._logged_errors.add(error)
            log.warning("minimap read failed: %s", error)
        self._miss()
