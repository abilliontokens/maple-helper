"""The loot log's reads: the game's pickup messages, read every READ_INTERVAL seconds while a log runs.

Where they are is found on its own: the game's picture (gamearea.GameArea: its window without the black bars a 16:9
game draws on an ultrawide screen), and lootlog.auto_box in it. That follows the window when it moves, and any
resolution or window size, since the game's interface scales with it. A box the player drew ("loot_region") is used
instead when there is one. A QTimer ticks on the GUI thread; finding the window, the grab and the OCR run on a worker
thread (the chat never freezes on them), and the read lines come back through a signal to lootlog.Tracker, which
turns them into the log's events. The running log is kept here, live, and saved to loot.json every few seconds and
when it ends (a log outlives the tools window and an app restart); each pickup, once no later read can correct it,
also goes into the loot database for good (lootdb.py).

The running log is the grind's run too (the grind bar and window, grindlive.py). Each pickup gets the map the player
is on (the minimap reads' ui/location.LOCATION, taken when the read comes back) and the player's level (the latest
bottom bar read that showed it, else the character's). Every HUD_INTERVAL seconds another worker grabs just the
bottom bar (hud.STRIP of the game's picture) and reads it into the log's samples: level, EXP, HP and MP (the OCR
engine is one, shared: hud._engine_lock). The player may pause the run: nothing is read or counted until it
resumes. Nothing reads while no log runs, except with the grind bar on (settings["grind_bar"]): then the messages are
watched, and the first EXP gain read starts a log, as its first pickup (mesos or an item alone never start one).

Items logged as one no pickup names (a Cash item a cut-off read was matched to) are named again when the scanner
starts and when the KB changes (`_repair`: the database, the live log and loot.json)."""
from __future__ import annotations

import logging
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from .. import capture, hud, lootdb, lootlog, plan
from ..gamearea import GameArea, valid_region
from ..kb import KnowledgeBase
from ..store import Profiles, Settings
from .location import LOCATION

log = logging.getLogger("maplehelper")

READ_INTERVAL = 0.5     # s: a message stays ~6 s and a kill writes up to 3 at once; two reads a second follow them
HUD_INTERVAL = 2.0      # s: the bottom bar's read (~0.5 s of OCR) while a log counts: level, EXP, HP, MP
SAVE_EVERY_MS = 5000    # the running log goes to disk this often while it counts (and at once when it ends)
SETTLE_S = lootlog.LIFETIME_S + 3   # a pickup older than this is final (no read corrects it): it goes in the database


class LootScanner(QObject):
    changed = Signal()            # the log counted something (a pickup, a bar read), started, ended, paused or resumed
    _read_done = Signal(object, float, object)   # (lines read or None, the read's time, (the box read, its state))
    _hud_done = Signal(object, float)            # (the bottom bar read: hud.Hud, the grab's time)
    _failed = Signal(str)

    def __init__(self, kb: KnowledgeBase, profiles: Profiles, settings: Settings, parent=None):
        super().__init__(parent)
        self.kb = kb
        self._profiles = profiles
        self._settings = settings
        self.store = lootlog.Store()
        self._tracker = self._new_tracker(kb)
        self._game = GameArea()
        self._hud_game = GameArea()           # the bar reads' own (a GameArea is one worker thread's)
        self._cid: str | None = None          # whose log runs
        self._log: lootlog.Log | None = None  # ... live
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._hud_timer = QTimer(self)
        self._hud_timer.timeout.connect(self._hud_tick)
        self._save_timer = QTimer(self, singleShot=True)
        self._save_timer.timeout.connect(self._save)
        self._guard = threading.Lock()
        self._reading = False
        self._hud_reading = False
        self._logged: set[str] = set()
        self._box_size: tuple[int, int] | None = None     # the size of the last box read: another one starts over
        self.state = "ok"                     # the last read: "ok", "no_game", "covered" or "no_reader" (the page
                                              # and the card say why nothing counts)
        self.last_read: float | None = None   # when a read last found a message line
        self._read_done.connect(self._deliver)
        self._hud_done.connect(self._hud_deliver)
        self._failed.connect(self._complain)
        self._repair()                        # (before the running log is taken up: loot.json is fixed first)
        self.resume()

    # ---------------------------------------------------------------- whose log, which box

    def cid(self) -> str:
        """The active character's id ("" with none: the log works without a character)."""
        c = self._profiles.active
        return c.id if c else ""

    def region(self) -> dict | None:
        """The box the player drew, when there is one (None: the messages are found on their own)."""
        r = self._settings["loot_region"]
        return {k: int(r[k]) for k in ("x", "y", "w", "h")} if valid_region(r) else None

    def set_kb(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        self._tracker = self._new_tracker(kb)
        self._repair()

    @staticmethod
    def _new_tracker(kb: KnowledgeBase) -> lootlog.Tracker:
        return lootlog.Tracker(lootlog.item_names(kb), lootlog.drop_keys(kb))

    def _repair(self) -> None:
        """Items logged as one no pickup names (a Cash item a cut-off read was matched to: "Green Mushroom Hat" for
        59 Green Mushroom Caps, seen live) named again by this KB's tracker: in the live log, loot.json and the
        database. A few rows: on the GUI thread."""
        from .. import farm
        n = 0
        try:
            bad, resolve, kb = lootlog.unpickable_keys(self.kb), self._tracker.resolve, self.kb
            if self._log is not None and self._cid is not None:
                fixed = self._log.repair(resolve, bad)
                if fixed:
                    self.store.put(self._cid, self._log)
                    n += fixed
            n += self.store.repair(resolve, bad)
            n += lootdb.repair_items(resolve, bad, price=lambda k: (v.price if (v := farm.value(kb, k)) else None))
        except Exception as e:  # noqa: BLE001 - a repair that fails leaves the names as they were, never the app
            self._complain(f"loot repair: {type(e).__name__}: {e}")
        if n:
            log.info("loot: repaired %d item names", n)

    def resume(self) -> None:
        """A log running when the app last closed goes on (and gets its database row if it had none)."""
        cid = self.store.running_any()
        if cid is not None:
            self._cid, self._log = cid, self.store.running(cid)
            self._save()
        self.restart()

    def restart(self) -> None:
        """The box changed (or a log started / ended / resumed, or the grind bar was switched): read, from a clean
        start, while a log counts, or while the grind bar watches for the next one."""
        self._tracker.reset()
        self._box_size = None
        self._timers()

    def _timers(self) -> None:
        """The messages are read while a log counts or the grind bar watches; the bottom bar while a log counts."""
        counting = self._counting()
        for timer, on, interval in ((self._timer, counting or self._watching(), READ_INTERVAL),
                                    (self._hud_timer, counting, HUD_INTERVAL)):
            if not on:
                timer.stop()
            elif not timer.isActive():
                timer.start(int(interval * 1000))

    def _counting(self) -> bool:
        """A log runs and isn't paused: its pickups and the bottom bar are read."""
        return self._log is not None and not self._log.paused

    def _watching(self) -> bool:
        """The grind bar is on and no log runs: the messages are read for the first EXP gain, which starts one."""
        return self._log is None and bool(self._settings["grind_bar"])

    def stop(self) -> None:
        """No read while the app goes; the running log is saved as it is (it goes on at the next start), and every
        pickup it counted goes into the database now."""
        self._timer.stop()
        self._hud_timer.stop()
        self._save(final=True)

    # ---------------------------------------------------------------- the log

    def log_for(self, cid: str) -> lootlog.Log | None:
        """A character's log: the live one while it runs, else the last one saved."""
        if cid == self._cid and self._log is not None:
            return self._log
        return self.store.log(cid)

    def running(self, cid: str) -> bool:
        return cid == self._cid and self._log is not None

    def start(self) -> None:
        self._open()
        self.restart()
        self.changed.emit()

    def _open(self, at: float | None = None) -> None:
        """A new log for the active character, from `at` (now): one still running ends first. Its database row at
        once."""
        if self._log is not None:
            self.end()
        cid = self.cid()
        self._cid, self._log = cid, self.store.start(cid, self.kb, now=at)
        self.last_read = None
        self.state = "ok"
        self._save()                        # (its database row, at once)

    def end(self) -> dict | None:
        if self._log is None:
            return None
        cid, lg = self._cid, self._log
        rec = self.store.end(cid, self.kb, lg)      # (a pause still on ends with it)
        self._to_db(lg, final=True)         # the rest of its pickups, and its end
        self.store.put(cid, lg)             # (which of them are in the database)
        self._cid, self._log = None, None
        self._save_timer.stop()
        self.restart()
        self.changed.emit()
        return rec

    def pause(self) -> None:
        """The player paused the running log: nothing is read (the messages nor the bottom bar) or counted until
        resume_run()."""
        if self._log is None or self._log.paused:
            return
        self._log.pause(time.time())
        self._timers()
        self._save()
        self.changed.emit()

    def resume_run(self) -> None:
        """The paused log counts again; what is on screen now came during the pause (a new baseline)."""
        if self._log is None or not self._log.paused:
            return
        self._log.resume(time.time())
        self.restart()
        self._save()
        self.changed.emit()

    def paused(self) -> bool:
        return self._log is not None and self._log.paused

    def _save(self, final: bool = False) -> None:
        """To loot.json, and the settled pickups to the database; again in a while when some aren't settled yet."""
        lg = self._log
        if lg is None or self._cid is None:
            return
        self._to_db(lg, final)
        self.store.put(self._cid, lg)
        if not final and any(not e.saved for e in lg.events) and not self._save_timer.isActive():
            self._save_timer.start(SAVE_EVERY_MS)

    def _to_db(self, lg: lootlog.Log, final: bool) -> None:
        """The log's row (made on its first save) and its pickups that no read can change any more (SETTLE_S after
        they came; `final`: all of them). A database that can't be written keeps them for the next try."""
        try:
            if lg.db_id is None:
                name = next((c.name for c in self._profiles.characters if c.id == self._cid), "")
                lg.db_id = lootdb.open_log(self._cid or "", name, lg.start)
            cut = time.time() - SETTLE_S
            ready = [e for e in lg.events if not e.saved and (final or e.t <= cut)]
            lootdb.add_events(lg.db_id, ready, self.kb)
            for e in ready:
                e.saved = True
            if lg.ended is not None:
                lootdb.end_log(lg.db_id, lg.ended)
        except Exception as e:  # noqa: BLE001 - a missed save keeps the pickups for the next try (also at quit)
            self._complain(f"loot database: {type(e).__name__}: {e}")

    # ---------------------------------------------------------------- reading the messages

    def _tick(self) -> None:
        if not (self._counting() or self._watching()):
            return
        with self._guard:
            if self._reading:
                return          # the last read is still going: skip this tick, don't pile up
            self._reading = True
        threading.Thread(target=self._read, args=(self.region(),), daemon=True).start()

    def _read(self, drawn: dict | None) -> None:
        try:
            if drawn is None:
                play = self._game.find()
                box = lootlog.auto_box(play) if play else None
            else:
                box = drawn
            rows, state = None, "ok"
            if box is None:
                state = "no_game"
            elif self._game.covered(box):
                state = "covered"           # another app's window over the messages: its text is never read
            else:
                img = capture.grab_image(box["x"], box["y"], box["w"], box["h"])
                rows = lootlog.ocr_rows(np.asarray(img))
                state = "ok" if rows is not None else "no_reader"
        except Exception as e:      # noqa: BLE001 - a bad read is a missed read, never a crash
            with self._guard:
                self._reading = False
            self._failed.emit(f"{type(e).__name__}: {e}")
            return
        with self._guard:
            self._reading = False
        self._read_done.emit(rows, time.time(), (box, state))

    def _deliver(self, rows, at: float, read) -> None:
        if not (self._counting() or self._watching()):
            return          # the log ended or was paused, or the grind bar went off, while the read was on its way
        box, state = read
        if state != self.state:
            self.state = state
            self.changed.emit()             # the page and the card say why nothing counts
        if state == "covered":
            # what is on screen when the game comes back in front is a new baseline (the messages moved meanwhile)
            self._tracker.reset()
            return
        if not rows:
            return
        size = (box["w"], box["h"])
        if size != self._box_size:
            # another size of box (the game resized, a box drawn): rows and their spacing start over, and what is
            # on screen now is the new baseline
            if self._box_size is not None:
                self._tracker.reset()
            self._box_size = size
        evs = self._tracker.read(rows, at)
        if self._log is None:
            # the grind bar watching: the first EXP gain starts a log, as its first pickup (what came before it in
            # this read, and mesos or items alone, start nothing). The tracker goes on: the next read isn't a baseline
            first = next((i for i, e in enumerate(evs) if e.kind == "exp"), None)
            if first is None:
                return
            evs = evs[first:]
            self._open(evs[0].t)
            self._timers()
        if any(lootlog.parse(r[0]) for r in rows):
            self.last_read = at
        if evs:
            self._tag(evs)
            self._log.add(evs)
            log.debug("loot: %s", ", ".join(f"{e.kind} {e.amount} {e.name}".strip() for e in evs))
            if not self._save_timer.isActive():
                self._save_timer.start(SAVE_EVERY_MS)
        # (a later read may correct an earlier event's value: redraw on every read with a message in it)
        if evs or self.last_read == at:
            self.changed.emit()

    # ---------------------------------------------------------------- the grind's tags

    @staticmethod
    def _map() -> str:
        """The map the minimap reads say the player is on ("" while they don't know)."""
        here = LOCATION.here
        return here.map if here is not None else ""

    def _level(self) -> int | None:
        """The player's level: the latest bottom bar read that showed it, else the active character's."""
        level = next((s.level for s in reversed(self._log.samples) if s.level is not None), None)
        if level is None and self._profiles.active is not None:
            level = self._profiles.active.level
        return level

    def _tag(self, evs: list[lootlog.Event]) -> None:
        """New pickups of the live log: the map they came on and the player's level."""
        map_id, level = self._map(), self._level()
        for e in evs:
            e.map, e.level = map_id, level

    # ---------------------------------------------------------------- reading the bottom bar

    def _hud_tick(self) -> None:
        if not self._counting():
            return
        with self._guard:
            if self._hud_reading:
                return          # the last bar read is still going: skip this tick, don't pile up
            self._hud_reading = True
        threading.Thread(target=self._hud_read, args=(self.kb,), daemon=True).start()

    def _hud_read(self, kb: KnowledgeBase) -> None:
        """A grab of just the bottom hud.STRIP of the game's picture, read (worker thread); nothing when there is no
        game, or another app's window is over the bar."""
        got, at = None, 0.0
        try:
            play = self._hud_game.find()
            if play is not None:
                x, y, w, h = play
                top = int(h * (1 - hud.STRIP))      # (where hud.read cuts a whole picture)
                box = {"x": x, "y": y + top, "w": w, "h": h - top}
                if not self._hud_game.covered(box):
                    at = time.time()
                    img = capture.grab_image(box["x"], box["y"], box["w"], box["h"])
                    got = hud.read_strip(img, plan.exp_table(kb))
        except Exception as e:      # noqa: BLE001 - a bad read is a missed sample, never a crash
            with self._guard:
                self._hud_reading = False
            self._failed.emit(f"HUD: {type(e).__name__}: {e}")
            return
        with self._guard:
            self._hud_reading = False
        if got is not None:
            self._hud_done.emit(got, at)

    def _hud_deliver(self, got: hud.Hud, at: float) -> None:
        """A bar read, back on the GUI thread: a sample of the live log, on the map the player is on now."""
        if not self._counting() or at < self._log.start:
            return          # the log ended or was paused while it was read (or it is older than this log)
        hp, mp = got.hp or (None, None), got.mp or (None, None)
        self._log.add_sample(lootlog.HudSample(at, self._map(), got.level, got.exp, got.exp_pct, *hp, *mp))
        self.changed.emit()

    def _complain(self, error: str) -> None:
        if error not in self._logged:
            self._logged.add(error)
            log.warning("loot read failed: %s", error)
