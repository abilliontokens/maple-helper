"""The loot log's reads: the game's pickup messages, read every READ_INTERVAL seconds while a log runs.

Where they are is found on its own: the game's picture (gamearea.GameArea: its window without the black bars a 16:9
game draws on an ultrawide screen), and lootlog.auto_box in it. That follows the window when it moves, and any
resolution or window size, since the game's interface scales with it. A box the player drew ("loot_region") is used
instead when there is one. A QTimer ticks on the GUI thread; finding the window, the grab and the OCR run on a worker
thread (the chat never freezes on them), and the read lines come back through a signal to lootlog.Tracker, which
turns them into the log's events. Nothing reads while no log runs. The running log is kept here, live, and saved to
loot.json every few seconds and when it ends (a log outlives the tools window and an app restart); each pickup, once
no later read can correct it, also goes into the loot database for good (lootdb.py)."""
from __future__ import annotations

import logging
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from .. import capture, lootdb, lootlog
from ..gamearea import GameArea, valid_region
from ..kb import KnowledgeBase
from ..store import Profiles, Settings

log = logging.getLogger("maplehelper")

READ_INTERVAL = 0.5     # s: a message stays ~6 s and a kill writes up to 3 at once; two reads a second follow them
SAVE_EVERY_MS = 5000    # the running log goes to disk this often while it counts (and at once when it ends)
SETTLE_S = lootlog.LIFETIME_S + 3   # a pickup older than this is final (no read corrects it): it goes in the database


class LootScanner(QObject):
    changed = Signal()            # the log counted something, started or ended
    _read_done = Signal(object, float, object)   # (lines read or None, the read's time, (the box read, its state))
    _failed = Signal(str)

    def __init__(self, kb: KnowledgeBase, profiles: Profiles, settings: Settings, parent=None):
        super().__init__(parent)
        self.kb = kb
        self._profiles = profiles
        self._settings = settings
        self.store = lootlog.Store()
        self._tracker = lootlog.Tracker(lootlog.item_names(kb))
        self._game = GameArea()
        self._cid: str | None = None          # whose log runs
        self._log: lootlog.Log | None = None  # ... live
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._save_timer = QTimer(self, singleShot=True)
        self._save_timer.timeout.connect(self._save)
        self._guard = threading.Lock()
        self._reading = False
        self._logged: set[str] = set()
        self._box_size: tuple[int, int] | None = None     # the size of the last box read: another one starts over
        self.state = "ok"                     # the last read: "ok", "no_game", "covered" or "no_reader" (the page
                                              # and the card say why nothing counts)
        self.last_read: float | None = None   # when a read last found a message line
        self._read_done.connect(self._deliver)
        self._failed.connect(self._complain)
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
        self._tracker = lootlog.Tracker(lootlog.item_names(kb))

    def resume(self) -> None:
        """A log running when the app last closed goes on (and gets its database row if it had none)."""
        cid = self.store.running_any()
        if cid is not None:
            self._cid, self._log = cid, self.store.running(cid)
            self._save()
        self.restart()

    def restart(self) -> None:
        """The box changed (or a log started / ended): read, from a clean start, while a log runs."""
        self._tracker.reset()
        self._box_size = None
        if self._log is not None:
            self._timer.start(int(READ_INTERVAL * 1000))
        else:
            self._timer.stop()

    def stop(self) -> None:
        """No read while the app goes; the running log is saved as it is (it goes on at the next start), and every
        pickup it counted goes into the database now."""
        self._timer.stop()
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
        if self._log is not None:
            self.end()
        cid = self.cid()
        self._cid, self._log = cid, self.store.start(cid, self.kb)
        self.last_read = None
        self.state = "ok"
        self._save()                        # (its database row, at once)
        self.restart()
        self.changed.emit()

    def end(self) -> dict | None:
        if self._log is None:
            return None
        cid, lg = self._cid, self._log
        rec = self.store.end(cid, self.kb, lg)
        self._to_db(lg, final=True)         # the rest of its pickups, and its end
        self.store.put(cid, lg)             # (which of them are in the database)
        self._cid, self._log = None, None
        self._save_timer.stop()
        self.restart()
        self.changed.emit()
        return rec

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

    # ---------------------------------------------------------------- reading

    def _tick(self) -> None:
        if self._log is None:
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
        if self._log is None:
            return
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
        if any(lootlog.parse(r[0]) for r in rows):
            self.last_read = at
        if evs:
            self._log.add(evs)
            log.debug("loot: %s", ", ".join(f"{e.kind} {e.amount} {e.name}".strip() for e in evs))
            if not self._save_timer.isActive():
                self._save_timer.start(SAVE_EVERY_MS)
        # (a later read may correct an earlier event's value: redraw on every read with a message in it)
        if evs or self.last_read == at:
            self.changed.emit()

    def _complain(self, error: str) -> None:
        if error not in self._logged:
            self._logged.add(error)
            log.warning("loot read failed: %s", error)
