"""Live grind numbers, measured on this computer from the loot log's run (lootlog.Log), and the player's own drop
rates, best spots and past runs from the loot database (lootdb.py). No AI and no Qt: the grind bar and window call
live() and alerts() on every scanner change (a 1-hour run takes a few milliseconds).

What it reads:
- the pickups the loot log counts (lootlog.Event): EXP, mesos and items, each with the map it came on, the player's
  level then and, for EXP, the monster it was matched to (Matcher; the scanner tags each line as it reads it);
- the HUD bar, read every 2 s while a run is live (lootlog.HudSample): level, EXP points and %, HP and MP.

How it counts:
- Active time: the gaps between consecutive signs of grinding (an EXP line, the HUD's EXP going up), each counted up
  to IDLE_S (the rest was idle), less the player's own pauses. Every rate is per active hour: the session's over all
  of it, the recent ones over its newest RECENT_S.
- Kills: EXP lines matched to a monster on the map, exactly first (the live check: 32, 21, 43, 8 and 2 were Axe
  Stump, Dark Stump, Dark Axe Stump, Red Snail and Snail to the point), then by a learned ratio (a party or event
  bonus). A line that matches nothing (18, 16, 30 there) is EXP but no kill.
- Deaths (the EXP going down at the same level) and level-ups (the level going up), each once two reads in a row
  agree: one misread is no death. Potions: HP or MP jumping by a potion's worth between two reads, priced as the
  consumable whose heal is closest to the jump.
- A map's spawn capacity: the kills an hour its spawns allow at most, from the KB's spawns table (an estimate)."""
from __future__ import annotations

import bisect
import logging
import math
import re
import sqlite3
import statistics
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import accumulate

from . import combat, farm, gamelookup, lootdb, plan, routes, tables
from .kb import memo

log = logging.getLogger("maplehelper")

IDLE_S = 120                # no EXP for this long: paused, the time past it not counted
RECENT_S = 300              # the recent rates: the newest 5 minutes of active time
MIN_RATE_S = 60             # under a minute of active time a rate means nothing (lootlog.per_hour's rule)
DEAD_S = 10.0               # "dead" this long after a death, and no potion counted then (a revive refills HP)
# matching kills (Matcher)
MIN_EXACT = 5               # exact matches a Matcher needs before it trusts a learned ratio
RATIO_TOL = 0.03            # how close an EXP line must be to the ratio x a monster's EXP
RATIO_SUPPORT = 3           # unmatched lines a ratio must explain, from 2+ different monsters, to be learned
RATIO_MIN_EXP = 10          # less EXP teaches no ratio: the game shows whole numbers (2 EXP x 1.2 still shows 2)
RATIO_KEPT = 20             # the newest unmatched lines a Matcher learns from
# the HUD reads
DEATH_PCT = 0.5             # with no EXP points read, the EXP % dropping more than this at the same level is a death
LEVEL_STEP = 2              # a level can rise this much between two reads at most (more is a misread)
POTION_SHARE = 0.6          # HP / MP rising by this share of the smallest Potion's heal is a potion ...
POTION_GAP_S = 6.0          # ... between two reads this close (a longer gap holds natural regeneration too)
# warnings
LOW_HP = 0.3                # "hits hard": HP under this share ...
LOW_HP_READS = 3            # ... in this many reads ...
LOW_HP_WINDOW = 600         # ... of the last 10 minutes on the map
LOW_HP_ALERT_S = 60         # a low-HP alert at most this often (the reads' own times)
SEGMENT_MIN_S = 600         # a map's active time before its kill share is judged, it is a best spot, or "move on"
SHARE_LOW = 0.35            # killing less than this share of the map's spawn capacity: warned
MOVE_ON = 1.25              # another map this much better than the recent EXP/h: time to move on
SPOT_LEVELS = 5             # best spots count the pickups within this many levels of the player's
TOP_DROPS = 5               # a summary's top drops
_CACHE = "_grindlive"       # the kb.memo key holding this module's per-KB lookups


# ---------------------------------------------------------------- what the windows get

@dataclass
class Rates:
    """Per active hour; None under MIN_RATE_S of active time."""
    exp_h: int | None = None
    kills_h: int | None = None
    mesos_h: int | None = None
    loot_h: int | None = None
    potions_h: int | None = None        # what the potions cost
    profit_h: int | None = None         # mesos + loot - potions
    active_s: float = 0.0


@dataclass
class Kill:
    monster_key: str
    name: str
    count: int


@dataclass
class DropRate:
    item_key: str
    item: str
    count: int                  # drops picked up on maps where a monster that drops it spawns
    kills: int                  # kills of those monsters
    one_in: int | None          # kills per drop (None until there are at least as many kills as drops)
    monsters: list[str]         # the monster keys counted, the most killed first


@dataclass
class Spot:
    map_id: str
    map_name: str
    active_s: float
    exp_h: int
    profit_h: int               # mesos + loot (the database keeps no potions)
    kills_h: int
    sessions: int               # runs that grinded there


@dataclass
class Goal:
    kind: str                   # "level" | "item" | "mesos"
    target: int
    item_key: str = ""
    item: str = ""

    @classmethod
    def from_json(cls, d) -> Goal | None:
        if not isinstance(d, dict) or d.get("kind") not in ("level", "item", "mesos"):
            return None
        target = d.get("target")
        if isinstance(target, float) and target.is_integer():
            target = int(target)
        if not isinstance(target, int) or isinstance(target, bool) or target <= 0:
            return None
        if d["kind"] != "item":
            return cls(d["kind"], target)
        key = str(d.get("item_key") or "")
        return cls("item", target, key, str(d.get("item") or key)) if key else None

    def to_json(self) -> dict:
        out = {"kind": self.kind, "target": self.target}
        if self.kind == "item":
            out |= {"item_key": self.item_key, "item": self.item}
        return out


@dataclass
class GoalProgress:
    goal: Goal
    have: int
    done: bool
    eta_s: float | None         # 0 once done; None while no rate tells


@dataclass
class Alert:
    kind: str                   # "wishlist" | "goal" | "low_hp" | "paused" | "level" | "death" | "move_on"
    key: str                    # its text (i18n, "gl_alert_...")
    params: dict
    item_key: str = ""
    t: float = 0.0              # when it happened: the pickup, the HUD read (the one that showed a death or a level-up),
                                # the run pausing itself


@dataclass
class Live:
    running: bool
    state: str                  # "running" | "paused" | "dead" | "stopped"
    map_id: str
    map_name: str
    wall_s: float
    session: Rates
    recent: Rates
    level: int | None
    exp_pct: float | None
    to_level_s: float | None
    kills: list[Kill]                                   # most first
    last_drop: tuple[str, str, int | None] | None       # (item name, item key, one_in)
    capacity_h: int | None                              # the kills an hour the map's spawns allow at most
    kill_share: float | None                            # 0-1: this map's kills an hour / its capacity
    warnings: list[tuple[str, dict]]                    # (i18n key "gl_warn_...", its params)
    deaths: int
    potions: int
    potion_cost: int
    level_ups: list[tuple[float, int]]                  # (when, the new level)
    goals: list[GoalProgress]
    move_on: Spot | None


@dataclass
class Summary:
    log_id: int | None
    start: float
    end: float | None
    active_s: float
    exp: int
    mesos: int
    loot: int
    potion_cost: int
    profit: int
    kills: int
    levels: tuple[int | None, int | None]               # (first, last)
    deaths: int
    maps: list[tuple[str, str, float]]                  # (map id, name, active seconds), most first
    top_drops: list[tuple[str, str, int]]               # (item key, item name, count), most first
    exp_h: int | None
    profit_h: int | None


# ---------------------------------------------------------------- the KB's side, built once per KB
# Every table is read only once the KB's tables are built (tables.rows build=False, tables.ready): this runs on every
# scanner change and for every EXP line, on the GUI thread, and must never build them or wait for a build (up to
# 5 s). Until then a lookup is empty and nothing is kept.

def _memo(kb) -> dict:
    return memo(kb, _CACHE)


def _kept(kb, cache: dict, name: str, value):
    """value, kept in the KB's cache unless the tables weren't built yet when it was read (gamelookup's rule)."""
    if tables.ready(kb):
        cache[name] = value
    return value


@lru_cache(maxsize=4096)
def _mid(map_id) -> str:
    """A map's bare id as the KB keys and routes write it ("010004070"), from "map/<id>" or an id without its zeros."""
    v = str(map_id or "").strip().removeprefix("map/")
    return v.zfill(9) if v.isdigit() else v


def _whole(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


@dataclass(frozen=True)
class _Mob:
    name: str
    level: int | None
    exp: int | None
    avoid: int


def _mobs(kb) -> dict[str, _Mob]:
    c = _memo(kb)
    if "mobs" in c:
        return c["mobs"]
    return _kept(kb, c, "mobs", {str(r["key"]): _Mob(str(r.get("monster") or r["key"]), _whole(r.get("level")),
                                                      _whole(r.get("exp")), _whole(r.get("avoid")) or 0)
                                  for r in tables.rows(kb, "monsters", build=False) if r.get("key")})


def _mob(kb, key: str) -> _Mob:
    m = _mobs(kb).get(key)
    if m is None:       # (a monster the table leaves out: its page's own numbers)
        e = kb.get(key) or {}
        p = e.get("props") or {}
        m = _Mob(str(e.get("name") or key), _whole(p.get("Level")), _whole(p.get("EXP")),
                 _whole(p.get("Avoidability")) or 0)
    return m


def _spawned(kb, mid: str) -> tuple[tuple[str, int], ...]:
    """(monster key, how many spawn) of every monster on a map, the most spawned first, then by name
    (gamelookup.map_monsters); () until the tables are built."""
    cache = _memo(kb).setdefault("spawned", {})
    hit = cache.get(mid)
    if hit is None:
        if not mid or not tables.ready(kb):
            return ()
        hit = cache[mid] = tuple((key, n) for key, _name, _level, n in gamelookup.map_monsters(kb, mid))
    return hit


def _on_map(kb, mid: str) -> tuple[dict[int, str], tuple[tuple[str, int, int], ...]]:
    """The monsters on a map with a known EXP: (EXP -> the monster it is exactly, the most spawned of a tie;
    ((key, EXP, how many spawn), ...) the most spawned first)."""
    cache = _memo(kb).setdefault("on_map", {})
    hit = cache.get(mid)
    if hit is None:
        spawned = _spawned(kb, mid)
        rows = sorted(((key, e, n) for key, n in spawned if (e := _mob(kb, key).exp) and e > 0), key=lambda r: -r[2])
        exact: dict[int, str] = {}
        for key, e, _ in rows:
            exact.setdefault(e, key)
        hit = (exact, tuple(rows))
        if spawned:
            cache[mid] = hit
    return hit


def _map_keys(kb, mid: str) -> frozenset[str]:
    """Every monster that spawns on a map."""
    return frozenset(key for key, _ in _spawned(kb, mid))


def _map_name(kb, mid: str) -> str:
    if not mid:
        return ""
    names = _memo(kb).setdefault("map_names", {})
    if mid not in names:
        name = routes.of(kb).name(mid)
        names[mid] = name if name != mid else str((kb.get(f"map/{mid}") or {}).get("name") or mid)
    return names[mid]


def _capacity(kb, mid: str) -> int | None:
    """The kills an hour a map's spawns allow at most: each spawns row's count x its mob rate (1 when none) every
    respawn seconds."""
    c = _memo(kb)
    caps = c.get("capacity")
    if caps is None:
        total: dict[str, float] = {}
        for r in tables.rows(kb, "spawns", build=False):
            m, n, rate, every = _mid(r.get("map_key")), r.get("count"), r.get("mob_rate"), r.get("respawn")
            if m and _whole(n) and n > 0 and isinstance(every, (int, float)) and every > 0:
                rate = rate if isinstance(rate, (int, float)) and rate > 0 else 1.0
                total[m] = total.get(m, 0.0) + n * rate * 3600 / every
        caps = _kept(kb, c, "capacity", {m: round(v) for m, v in total.items()})
    return caps.get(mid)


@dataclass(frozen=True)
class _Heal:
    """A consumable that heals HP (or MP): by `flat` points or by `share` of the maximum (Elixir "35%")."""
    key: str
    name: str
    flat: int | None
    share: float | None
    buy: int | None             # its cheapest NPC price; None when no NPC sells it
    potion: bool                # the table's type is Potion (food heals too)


_HEAL = re.compile(r"^\s*(\d+)\s*(%?)\s*$")


def _heals(kb) -> tuple[tuple[_Heal, ...], tuple[_Heal, ...], float | None, float | None]:
    """(the HP heals, the MP heals, the HP rise and the MP rise that count as a potion: POTION_SHARE of the smallest
    Potion's heal, Red Potion 100 / Blue Potion 200 in the KB; every heal's smallest when no Potion has one).
    Quest items heal too but are kept for their quests: left out."""
    c = _memo(kb)
    if "heals" in c:
        return c["heals"]
    hp: list[_Heal] = []
    mp: list[_Heal] = []
    for r in tables.rows(kb, "consumables", build=False):
        kind = str(r.get("type") or "")
        if kind == "Quest Item":
            continue
        buy = _whole(r.get("buy"))
        for col, out in (("hp", hp), ("mp", mp)):
            m = _HEAL.match(str(r.get(col) or ""))
            if m and int(m.group(1)) > 0:
                n = int(m.group(1))
                out.append(_Heal(str(r.get("key") or ""), str(r.get("item") or ""), None if m.group(2) else n,
                                 n / 100 if m.group(2) else None, buy if buy and buy > 0 else None, kind == "Potion"))

    def rise(rows: list[_Heal]) -> float | None:
        flats = [h.flat for h in rows if h.flat and h.potion] or [h.flat for h in rows if h.flat]
        return POTION_SHARE * min(flats) if flats else None

    return _kept(kb, c, "heals", (tuple(hp), tuple(mp), rise(hp), rise(mp)))


def _price(kb, key: str) -> int | None:
    """What one of an item is worth (farm.value), asked once per item."""
    if not key:
        return None
    prices = _memo(kb).setdefault("prices", {})
    if key not in prices:
        v = farm.value(kb, key)
        prices[key] = v.price if v else None
    return prices[key]


def _exp_table(kb) -> dict[int, int]:
    c = _memo(kb)
    if "exp_table" not in c:
        c["exp_table"] = plan.exp_table(kb)
    return c["exp_table"]


_acc_needed = lru_cache(maxsize=4096)(combat.acc_needed)


# ---------------------------------------------------------------- matching kills

class Matcher:
    """Which monster an EXP line was: one per run (the scanner tags each EXP event as it reads it).

    The line's EXP matched exactly among the monsters that spawn on the map, a tie going to the most spawned one.
    A line that matches no monster may carry a party or event bonus: once the run has MIN_EXACT exact matches (the
    map and its monsters are right), the unmatched lines teach a ratio when RATIO_SUPPORT of them, from at least two
    different monsters, fit one within RATIO_TOL (its value: the median of their observed / KB EXP), and a line that
    fits it within RATIO_TOL is that monster. One value seen again and again teaches nothing (it fits some ratio to
    every monster: the live check's 18 x3 would have made Dark Stump kills). Anything else is EXP but no kill."""

    def __init__(self, kb):
        self.kb = kb
        self.exact = 0                      # exact matches so far
        self.ratio: float | None = None     # the learned ratio, observed / KB EXP
        self._off: deque[tuple[str, int]] = deque(maxlen=RATIO_KEPT)    # (map, EXP) of the unmatched lines

    def monster(self, map_id: str, exp: int) -> str:
        """The monster key, or "" (no monster's EXP)."""
        mid = _mid(map_id)
        exact, mons = _on_map(self.kb, mid)
        if not mons or not isinstance(exp, int) or isinstance(exp, bool) or exp <= 0:
            return ""
        key = exact.get(exp)
        if key:
            self.exact += 1
            return key
        self._off.append((mid, exp))
        if self.exact < MIN_EXACT:
            return ""
        key = _by_ratio(mons, exp, self.ratio)
        if not key:
            self.ratio = self._learn()
            key = _by_ratio(mons, exp, self.ratio)
        return key

    def _learn(self) -> float | None:
        """The ratio the most unmatched lines agree on (each line: its observed / KB EXP to every monster on its
        map, in log space so a window is a share)."""
        cands = sorted((math.log(v / e), i, k) for i, (mid, v) in enumerate(self._off) if v >= RATIO_MIN_EXP
                       for k, e, _ in _on_map(self.kb, mid)[1] if e >= RATIO_MIN_EXP)
        width = math.log(1 + RATIO_TOL)
        best: tuple[tuple, list[float]] | None = None
        lo = hi = 0
        for x, _, _ in cands:
            while cands[lo][0] < x - width:
                lo += 1
            while hi < len(cands) and cands[hi][0] <= x + width:
                hi += 1
            near: dict[int, tuple[float, float, str]] = {}      # line -> its candidate closest to x
            for y, i, k in cands[lo:hi]:
                if i not in near or abs(y - x) < near[i][0]:
                    near[i] = (abs(y - x), y, k)
            kinds = len({k for _, _, k in near.values()})
            if len(near) < RATIO_SUPPORT or kinds < 2:
                continue
            score = (len(near), kinds, -abs(x))
            if best is None or score > best[0]:
                best = (score, [y for _, y, _ in near.values()])
        return math.exp(statistics.median(best[1])) if best else None


def _by_ratio(mons: tuple[tuple[str, int, int], ...], exp: int, ratio: float | None) -> str:
    """The monster whose EXP x ratio is within RATIO_TOL of `exp` (or half a point: the game shows whole numbers),
    the closest; a tie goes to the most spawned."""
    if not ratio:
        return ""
    best, gap = "", 0.0
    for key, e, _ in mons:
        want = ratio * e
        d = abs(exp - want)
        if d <= max(RATIO_TOL * want, 0.5) and (not best or d < gap):
            best, gap = key, d
    return best


def _tags(kb, evs: list) -> list[str]:
    """Each EXP event's monster: the scanner's tags; a run with none at all (an older log, read before kills were
    matched) is matched here, in the order it was read."""
    if any(e.monster for e in evs) or not any(e.map for e in evs):
        return [e.monster for e in evs]
    m = Matcher(kb)
    return [m.monster(e.map, e.amount) if e.map else "" for e in evs]


# ---------------------------------------------------------------- the HUD reads

def _down(a, b) -> bool | None:
    """The EXP went down from read a to read b (both at one level); None when the two can't be compared."""
    if a.exp is not None and b.exp is not None:
        return b.exp < a.exp
    if a.exp_pct is not None and b.exp_pct is not None:
        return a.exp_pct - b.exp_pct > DEATH_PCT
    return None


def _up(a, b) -> bool:
    if a.exp is not None and b.exp is not None:
        return b.exp > a.exp
    return a.exp_pct is not None and b.exp_pct is not None and b.exp_pct > a.exp_pct


def _reads(samples: list) -> tuple[list[tuple[float, float]], list[tuple[float, int, float]], list, object | None,
                                   object | None]:
    """((the read that showed it, the read that confirmed it) of each death, (showed, the new level, confirmed) of each
    level-up, the reads where the EXP went up, the first and the last read that stood), from the reads with a level.
    A death (the EXP down at the same level) or a level-up counts once the next read agrees: a misread the next read
    takes back is none. A read too high is skipped the same way (else the next real one would read as a death); a
    level that can't follow is a misread unless the next two reads agree on it."""
    lv = [s for s in samples if s.level is not None]
    deaths: list[tuple[float, float]] = []
    ups: list[tuple[float, int, float]] = []
    rises: list = []
    ref = first = None
    for i, s in enumerate(lv):
        if ref is None:
            ref = first = s
            continue
        nxt = lv[i + 1] if i + 1 < len(lv) else None
        if s.level == ref.level:
            down = _down(ref, s)
            if down is None:
                continue
            if down:
                if nxt is not None and nxt.level == s.level and _down(ref, nxt):
                    deaths.append((s.t, nxt.t))
                    ref = s
                continue
            if _up(ref, s):
                if nxt is not None and nxt.level == s.level and _down(s, nxt) and not _down(ref, nxt):
                    continue
                rises.append(s)
            ref = s
        elif 0 < s.level - ref.level <= LEVEL_STEP:
            if nxt is not None and nxt.level == s.level:
                ups.extend((s.t, n, nxt.t) for n in range(ref.level + 1, s.level + 1))
                rises.append(s)
                ref = s
        elif i + 2 < len(lv) and lv[i + 1].level == s.level == lv[i + 2].level:
            ref = s
    return deaths, ups, rises, first, ref


def _rise(a: int | None, a_max: int | None, b: int | None, b_max: int | None, least: float | None,
          from_zero: bool) -> int | None:
    """How much a gauge rose between two reads when that is a potion's worth; None otherwise (a gauge not read, a
    new maximum: gear or a level, a read past the maximum)."""
    if least is None or a is None or b is None or b - a < least:
        return None
    if a_max is None or a_max != b_max or not a_max or b > b_max or a > a_max or a < 0 or (a == 0 and not from_zero):
        return None
    return b - a


def _pick(heals: tuple[_Heal, ...], rise: int, top: int, full: bool) -> _Heal | None:
    """The consumable a rise was: the one whose heal is closest to it (a share of `top` for an Elixir). A gauge that
    ended full may have been healed more than it rose: then the smallest heal at least that big. A tie goes to a
    Potion over food, then to one an NPC sells, then the cheaper."""
    found = [(h.flat or h.share * top, h) for h in heals if h.flat or (h.share and top)]
    if full:
        found = [f for f in found if f[0] >= rise] or found
    if not found:
        return None
    return min(found, key=lambda f: (abs(f[0] - rise), not f[1].potion, f[1].buy is None, f[1].buy or 0,
                                     f[1].name))[1]


def _potions(samples: list, heals, deaths: list[float], ups: list[tuple[float, int]]) -> list[tuple[float, int]]:
    """(when, cost) of each potion: HP (or MP) rising by a potion's worth between two reads, never at a level-up or
    within DEAD_S of a death (the revive), never from 0 HP. One potion a rise (an Elixir raising both: one); its cost
    the consumable's NPC price (0 when no NPC sells it)."""
    hp_heals, mp_heals, least_hp, least_mp = heals
    up_times = [t for t, _ in ups]
    out: list[tuple[float, int]] = []
    prev = None
    for s in samples:
        if s.hp is None and s.mp is None:
            continue
        if prev is not None and s.t - prev.t <= POTION_GAP_S:
            h = _rise(prev.hp, prev.hp_max, s.hp, s.hp_max, least_hp, False)
            m = _rise(prev.mp, prev.mp_max, s.mp, s.mp_max, least_mp, True) if prev.hp is None or prev.hp > 0 else None
            if (h or m) and not _settled(prev, s, deaths, up_times):
                got = [g for g in (_pick(hp_heals, h, s.hp_max, s.hp >= s.hp_max) if h else None,
                                   _pick(mp_heals, m, s.mp_max, s.mp >= s.mp_max) if m else None) if g is not None]
                if len(got) == 2 and got[0].key == got[1].key:
                    got = got[:1]
                out.extend((s.t, g.buy or 0) for g in got)
        prev = s
    return out


def _settled(a, b, deaths: list[float], up_times: list[float]) -> bool:
    """Between reads a and b a level-up, or within DEAD_S of a death (the revive), explains a rise."""
    if a.level is not None and b.level is not None and b.level > a.level:
        return True
    i = bisect.bisect_right(up_times, a.t)
    if i < len(up_times) and up_times[i] <= b.t:
        return True
    j = bisect.bisect_right(deaths, b.t)
    return j > 0 and b.t - deaths[j - 1] <= DEAD_S


# ---------------------------------------------------------------- one run, read once a call

def _cum(values) -> list:
    return list(accumulate(values, initial=0))


def _t(x) -> float:
    return x.t


@dataclass
class _Run:
    end: float                          # the run's end: ended, else now
    window: float | None                # a long run's log keeps its newest pickups: since when (None: all of them)
    exp: list                           # (EXP event, its monster) by time
    exp_t: list[float]
    exp_cum: list[int]
    kill_cum: list[int]
    mesos: list
    mesos_t: list[float]
    mesos_cum: list[int]
    items: list                         # the item events by time
    item_t: list[float]
    item_cum: list[int]                 # what they are worth
    pot_t: list[float]
    pot_cum: list[int]
    samples: list
    sample_t: list[float]
    deaths: list[float]                 # when each death showed in a read ...
    death_known: list[float]            # ... and the next read, that confirmed it
    ups: list[tuple[float, int]]        # (when, the new level) of each level-up ...
    up_known: list[float]               # ... and the read that confirmed it
    first: object | None                # the first HUD read that stood
    last: object | None                 # the newest
    acts: list[tuple[float, str]]       # (when, map) of every sign of grinding
    marks: list[float]                  # when the idle clock last restarted: acts, the start, each resume
    spans: list[tuple[float, float, str]]   # the active time: (from, to, map of its activity), pauses cut out
    pauses: list[tuple[float, float]]
    active: float
    map: str                            # where the run is now ("" unknown)
    seg_start: float                    # when it came to this map

    @property
    def potion_cost(self) -> int:
        return self.pot_cum[-1]


def _analyse(kb, lg, now: float) -> _Run:
    end = lg.ended if lg.ended is not None else now
    exp_evs, mesos, items, where = [], [], [], []
    for e in lg.events:
        if e.t > end:
            continue
        if e.kind == "exp":
            exp_evs.append(e)
        elif e.kind == "mesos":
            mesos.append(e)
        else:
            items.append(e)
        if e.map:
            where.append((e.t, e.map))
    exp = sorted(zip(exp_evs, _tags(kb, exp_evs)), key=lambda p: p[0].t)
    mesos.sort(key=_t)
    items.sort(key=_t)
    samples = sorted((s for s in lg.samples if s.t <= end), key=_t)
    shown_deaths, shown_ups, rises, first, last = _reads(samples)
    deaths, ups = [t for t, _ in shown_deaths], [(t, n) for t, n, _ in shown_ups]
    pots = _potions(samples, _heals(kb), deaths, ups)
    # the active time: each sign of grinding counts up to IDLE_S until the next, the player's pauses cut out; in a log
    # that let its oldest pickups go (lootlog.MAX_EVENTS), only since the oldest one kept, the time its rates are over
    window = min((e.t for e in lg.events), default=lg.start) if lg.base["exp"] or lg.base["mesos"] or lg.base["items"] \
        else None
    acts = sorted([(e.t, _mid(e.map)) for e, _ in exp] + [(s.t, _mid(s.map)) for s in rises
                                                         if window is None or s.t >= window])
    pauses = sorted((float(p[0]), min(end, float(p[1]) if p[1] is not None else end)) for p in lg.pauses
                    if p and isinstance(p[0], (int, float)))
    pauses = [(a, b) for a, b in pauses if b > a]
    spans = []
    for i, (a, m) in enumerate(acts):
        stop = min(acts[i + 1][0] if i + 1 < len(acts) else end, a + IDLE_S, end)
        if stop > a:
            spans.append((a, stop, m))
    if pauses:
        spans = _unpaused(spans, pauses)
    marks = sorted([lg.start] + [a for a, _ in acts] + [float(p[1]) for p in lg.pauses
                                                       if p and isinstance(p[1], (int, float)) and p[1] <= end])
    # the map now, and since when the run is on it (a map change starts a new segment; an unknown map changes none)
    where += [(s.t, s.map) for s in samples if s.map]
    where.sort(key=lambda w: w[0])
    here, seg = "", lg.start
    if where:
        here = _mid(where[-1][1])
        for t, m in reversed(where):
            if _mid(m) != here:
                break
            seg = t
        else:
            seg = lg.start
    return _Run(end, window, exp, [e.t for e, _ in exp], _cum(e.amount for e, _ in exp), _cum(1 if k else 0 for _, k in exp),
                mesos, [e.t for e in mesos], _cum(e.amount for e in mesos),
                items, [e.t for e in items], _cum(e.amount * (_price(kb, e.key) or 0) for e in items),
                [t for t, _ in pots], _cum(c for _, c in pots), samples, [s.t for s in samples], deaths,
                [k for _, k in shown_deaths], ups, [k for *_, k in shown_ups], first, last, acts, marks, spans, pauses,
                sum(b - a for a, b, _ in spans), here, seg)


def _unpaused(spans: list[tuple[float, float, str]], pauses: list[tuple[float, float]]) -> list:
    out = []
    for a, b, m in spans:
        pieces = [(a, b)]
        for ps, pe in pauses:
            if ps >= b:
                break
            if pe <= a:
                continue
            cut = []
            for x, y in pieces:
                if pe <= x or ps >= y:
                    cut.append((x, y))
                    continue
                if x < ps:
                    cut.append((x, ps))
                if pe < y:
                    cut.append((pe, y))
            pieces = cut
        out.extend((x, y, m) for x, y in pieces if y > x)
    return out


def _cutoff(spans: list[tuple[float, float, str]], keep: float) -> float | None:
    """The time after which the newest `keep` seconds of active time lie; None when there is no more than that."""
    left = keep
    for a, b, _ in reversed(spans):
        if b - a > left:
            return b - left
        left -= b - a
    return None


def _since(ts: list[float], cum: list, t0: float | None, inclusive: bool):
    if t0 is None:
        return cum[-1]
    return cum[-1] - cum[bisect.bisect_left(ts, t0) if inclusive else bisect.bisect_right(ts, t0)]


def _rates(run: _Run, t0: float | None, inclusive: bool, active: float) -> Rates:
    """The rates of what came after t0 (all with None) over `active` seconds."""
    if active < MIN_RATE_S:
        return Rates(active_s=active)

    def per_h(v) -> int:
        return round(v * 3600 / active)

    mesos_h = per_h(_since(run.mesos_t, run.mesos_cum, t0, inclusive))
    loot_h = per_h(_since(run.item_t, run.item_cum, t0, inclusive))
    potions_h = per_h(_since(run.pot_t, run.pot_cum, t0, inclusive))
    return Rates(per_h(_since(run.exp_t, run.exp_cum, t0, inclusive)), per_h(_since(run.exp_t, run.kill_cum, t0, inclusive)),
                 mesos_h, loot_h, potions_h, mesos_h + loot_h - potions_h, active)


def _exp_left(table: dict[int, int], level: int | None, exp: int | None, pct: float | None, target: int) -> float | None:
    """EXP still to gain from (level, EXP points or %) to `target` level; None when the table or the read can't say."""
    if not level:
        return None
    if target <= level:
        return 0.0
    need = table.get(level)
    if not need:
        return None
    if exp is not None and 0 <= exp <= need:
        left = float(need - exp)
    elif pct is not None and 0 <= pct <= 100:
        left = need * (1 - pct / 100)
    else:
        return None
    for lv in range(level + 1, target):
        if not table.get(lv):
            return None
        left += table[lv]
    return left


# ---------------------------------------------------------------- the live numbers

def live(kb, lg, character, goals: list[Goal], now: float | None = None) -> Live:
    """The run's numbers now (`lg` None: no run, "stopped" and zeros)."""
    now = time.time() if now is None else now
    if lg is None:
        level = character.level if character is not None else None
        pct = character.exp_pct if character is not None else None
        return Live(False, "stopped", "", "", 0.0, Rates(), Rates(), level, pct, None, [], None, None, None, [], 0, 0, 0,
                    [], [_progress(kb, g, level, None, pct, 0, Counter(), Rates(), Counter(), 0.0) for g in goals],
                    None)
    run = _analyse(kb, lg, now)
    session = _rates(run, run.window, True, run.active)
    cut = _cutoff(run.spans, RECENT_S)
    recent_s = min(run.active, RECENT_S)
    recent = _rates(run, cut, False, recent_s)
    seg_s = sum(b - a for a, b, _ in run.spans if a >= run.seg_start)
    seg = _rates(run, run.seg_start, True, seg_s)
    level, exp, pct = _level_now(kb, run, character)
    rate = recent.exp_h if recent.exp_h is not None else session.exp_h
    left = _exp_left(_exp_table(kb), level, exp, pct, (level or 0) + 1)
    killed = Counter(k for _, k in run.exp if k)
    kills = sorted((Kill(k, _mob(kb, k).name, n) for k, n in killed.items()),
                   key=lambda k: (-k.count, k.name.casefold(), k.monster_key))
    cap = _capacity(kb, run.map) if run.map else None
    share = min(1.0, seg.kills_h / cap) if cap and seg.kills_h is not None else None
    cid = character.id if character is not None else ""
    last_drop = None
    if run.items:
        e = run.items[-1]
        one_in = None
        if e.key:
            past_kills, past_picks, _ = _db(kb, cid, lg.db_id, level, run.map)
            picks = dict(past_picks.get(e.key, {}))
            for x in run.items:
                if x.key == e.key and x.map:
                    picks[_mid(x.map)] = picks.get(_mid(x.map), 0) + 1
            one_in = _drop_rate(kb, e.key, lambda m: past_kills.get(m, 0) + killed.get(m, 0), picks)[2]
        last_drop = (e.name, e.key, one_in)
    _, mesos_total, got = lg.totals()
    have = Counter()
    for n, key in got.values():
        if key:
            have[key] += n
    recent_items = Counter()
    for e in run.items[bisect.bisect_right(run.item_t, cut) if cut is not None else 0:]:
        if e.key:
            recent_items[e.key] += e.amount
    move_on = None
    if seg_s >= SEGMENT_MIN_S and recent.exp_h:
        move_on = next((sp for sp in _db(kb, cid, lg.db_id, level, run.map)[2]
                        if sp.map_id != run.map and sp.exp_h >= MOVE_ON * recent.exp_h), None)
    return Live(lg.ended is None, _state(lg, run), run.map, _map_name(kb, run.map), max(0.0, run.end - lg.start),
                session, recent, level, pct, left / rate * 3600 if left is not None and rate else None, kills,
                last_drop, cap, share, _warnings(kb, run, character, level, seg_s, cap, share), len(run.deaths),
                len(run.pot_t), run.potion_cost, list(run.ups),
                [_progress(kb, g, level, exp, pct, mesos_total, have, recent, recent_items, recent_s) for g in goals],
                move_on)


def _state(lg, run: _Run) -> str:
    if lg.ended is not None:
        return "stopped"
    if lg.paused:
        return "paused"
    if run.deaths and 0 <= run.end - run.deaths[-1] < DEAD_S:
        return "dead"
    return "paused" if run.end - run.marks[-1] > IDLE_S else "running"


def _level_now(kb, run: _Run, character) -> tuple[int | None, int | None, float | None]:
    """(level, EXP points, EXP %) now: the newest HUD read that stood, else the character as saved."""
    r = run.last
    level = r.level if r is not None else (character.level if character is not None else None)
    exp = r.exp if r is not None else None
    pct = r.exp_pct if r is not None else None
    need = _exp_table(kb).get(level) if level else None
    if pct is None and exp is not None and need and 0 <= exp <= need:
        pct = round(exp * 100 / need, 2)
    if pct is None and character is not None and character.level == level:
        pct = character.exp_pct
    return level, exp, pct


def _warnings(kb, run: _Run, character, level: int | None, seg_s: float, cap: int | None,
              share: float | None) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    # can't hit: the ACC the player typed in My stats (the Hit & damage page's), below what a monster here needs
    acc = _whole(((character.stats if character is not None else None) or {}).get("acc"))
    if acc and acc > 0 and level and run.map:
        worst = None
        for key, _n in _spawned(kb, run.map):
            m = _mob(kb, key)
            if m.level is None:
                continue
            need = _acc_needed(level, m.level, m.avoid)
            if acc < need and (worst is None or need > worst[0]):
                worst = (need, m.name)
        if worst:
            out.append(("gl_warn_acc", {"name": worst[1], "need": worst[0], "acc": acc}))
    # hits hard, as seen: a death on this map, else HP low in several reads of the last 10 minutes here
    died = len(run.deaths) - bisect.bisect_left(run.deaths, run.seg_start)
    if died:
        out.append(("gl_warn_died", {"n": died}))
    else:
        i = bisect.bisect_left(run.sample_t, max(run.seg_start, run.end - LOW_HP_WINDOW))
        low = sum(1 for s in run.samples[i:] if s.hp is not None and s.hp_max and 0 <= s.hp < LOW_HP * s.hp_max)
        if low >= LOW_HP_READS:
            out.append(("gl_warn_low_hp", {"pct": round(LOW_HP * 100)}))
    if cap and share is not None and seg_s >= SEGMENT_MIN_S and share < SHARE_LOW:
        out.append(("gl_warn_share", {"pct": round(share * 100), "cap": f"{cap:,}"}))
    return out


def _progress(kb, g: Goal, level: int | None, exp: int | None, pct: float | None, mesos: int, have: Counter,
              recent: Rates, recent_items: Counter, recent_s: float) -> GoalProgress:
    """A goal against the run: the level now, the item's count, the mesos; its time left at the recent rate."""
    if g.kind == "level":
        n = level or 0
        left = _exp_left(_exp_table(kb), level, exp, pct, g.target)
        eta = left / recent.exp_h * 3600 if left is not None and recent.exp_h else None
    elif g.kind == "item":
        n = have.get(g.item_key, 0)
        per_h = recent_items.get(g.item_key, 0) * 3600 / recent_s if recent_s >= MIN_RATE_S else 0
        eta = (g.target - n) / per_h * 3600 if per_h else None
    else:
        n = mesos
        eta = (g.target - n) / recent.mesos_h * 3600 if recent.mesos_h else None
    done = n >= g.target
    return GoalProgress(g, n, done, 0.0 if done else eta)


# ---------------------------------------------------------------- alerts

def alerts(kb, lg, character, goals: list[Goal], wishlist_keys: list[str], low_hp: float, since: float,
           now: float | None = None) -> list[Alert]:
    """What happened after `since`, oldest first, each at its time (Alert.t): a tracked item picked up, a goal
    reached, HP under `low_hp` of the maximum (0: off; one alert a LOW_HP_ALERT_S at most, by the reads' own times),
    the run pausing on its own, a level-up, a death. A death or a level-up (a level goal too) counts only once the
    next HUD read confirms it: it comes when that read is after `since`, at the time of the read that showed it (which
    may be `since` or before). Pure: the same log and times give the same alerts."""
    if lg is None:
        return []
    run = _analyse(kb, lg, time.time() if now is None else now)
    found: list[Alert] = []
    wish = set(wishlist_keys or ())
    for e in run.items[bisect.bisect_right(run.item_t, since):] if wish else ():
        if e.key in wish:
            found.append(Alert("wishlist", "gl_alert_wishlist", {"name": e.name}, e.key, e.t))
    for g in goals:
        hit = _reached(run, lg, g)
        if hit is not None and hit[1] > since:
            found.append(_goal_alert(g, hit[0]))
    if low_hp > 0:
        found += [Alert("low_hp", "gl_alert_low_hp", {"pct": pct}, t=t) for t, pct in _low_hp(run.samples, low_hp)
                  if t > since]
    found += [Alert("paused", "gl_alert_paused", {"n": IDLE_S // 60}, t=t) for t in _idled(run, since)]
    found += [Alert("level", "gl_alert_level", {"level": n}, t=t)
              for (t, n), known in zip(run.ups, run.up_known) if known > since]
    found += [Alert("death", "gl_alert_death", {}, t=t) for t, known in zip(run.deaths, run.death_known) if known > since]
    found.sort(key=lambda a: a.t)
    return found


def _reached(run: _Run, lg, g: Goal) -> tuple[float, float] | None:
    """(when the run reached a goal, when that was known: a level-up's confirming read); None when it didn't in this
    run, or it was met before anything this run counted."""
    if g.kind == "level":
        return next(((t, known) for (t, n), known in zip(run.ups, run.up_known) if n == g.target), None)
    if g.kind == "item":
        n = sum(c for c, key in lg.base["items"].values() if key == g.item_key)
        evs = [(e.t, e.amount) for e in run.items if e.key == g.item_key]
    else:
        n = lg.base["mesos"]
        evs = [(e.t, e.amount) for e in run.mesos]
    if n >= g.target:
        return None
    for t, amount in evs:
        n += amount
        if n >= g.target:
            return t, t
    return None


def _goal_alert(g: Goal, t: float) -> Alert:
    if g.kind == "level":
        return Alert("goal", "gl_alert_goal_level", {"level": g.target}, t=t)
    if g.kind == "item":
        return Alert("goal", "gl_alert_goal_item", {"n": f"{g.target:,}", "name": g.item}, g.item_key, t)
    return Alert("goal", "gl_alert_goal_mesos", {"amount": f"{g.target:,}"}, t=t)


def _low_hp(samples: list, share: float) -> list[tuple[float, int]]:
    """(when, HP %) of each low-HP alert: a read under `share` of the maximum, then none for LOW_HP_ALERT_S."""
    out: list[tuple[float, int]] = []
    last = None
    for s in samples:
        if s.hp is None or not s.hp_max or not 0 < s.hp < share * s.hp_max:
            continue
        if last is None or s.t - last >= LOW_HP_ALERT_S:
            out.append((s.t, round(100 * s.hp / s.hp_max)))
            last = s.t
    return out


def _idled(run: _Run, since: float) -> list[float]:
    """When the run paused on its own after `since`: IDLE_S after a sign of grinding (the start, a resume) with
    nothing after it, outside the player's own pauses."""
    out = []
    marks = run.marks
    for i in range(bisect.bisect_right(marks, since - IDLE_S), len(marks)):
        at = marks[i] + IDLE_S
        if since < at <= run.end and (i + 1 == len(marks) or marks[i + 1] > at) \
                and not any(a <= at < b for a, b in run.pauses):
            out.append(at)
    return out


# ---------------------------------------------------------------- the loot database: drop rates, spots, history

def _book(rows) -> tuple[Counter, dict[str, dict[str, int]], dict[str, str]]:
    """(kills per monster, item key -> {map -> drops picked up there}, item key -> its name)."""
    kills: Counter = Counter()
    picks: dict[str, dict[str, int]] = {}
    names: dict[str, str] = {}
    for r in rows:
        if r.kind == "exp":
            if r.monster_key:
                kills[r.monster_key] += 1
        elif r.kind == "item" and r.item_key and r.map_key:
            m = _mid(r.map_key)
            by_map = picks.setdefault(r.item_key, {})
            by_map[m] = by_map.get(m, 0) + 1
            names.setdefault(r.item_key, r.item or r.item_key)
    return kills, picks, names


def _drop_rate(kb, key: str, kills: Callable[[str], int],
               picks: dict[str, int]) -> tuple[int, int, int | None, list[str]]:
    """(drops, kills, kills per drop, the monsters counted) of an item: its drops on maps where a monster that drops
    it spawns, and the kills of those monsters (kb.droppers on each such map)."""
    droppers = set(kb.droppers.get(key, ()))
    counted: set[str] = set()
    drops = 0
    for m, n in picks.items():
        here = droppers & _map_keys(kb, m)
        if here:
            counted |= here
            drops += n
    k = sum(kills(m) for m in counted)
    return (drops, k, round(k / drops) if drops and k >= drops else None,
            sorted(counted, key=lambda m: (-kills(m), _mob(kb, m).name.casefold(), m)))


def drop_rates(kb, character_id: str) -> list[DropRate]:
    """The player's own drop rates, from every run in the loot database: the most picked up first."""
    kills, picks, names = _book(lootdb.events(character_id))
    out = []
    for key, by_map in picks.items():
        drops, k, one_in, monsters = _drop_rate(kb, key, lambda m: kills.get(m, 0), by_map)
        if drops:
            out.append(DropRate(key, names[key], drops, k, one_in, monsters))
    out.sort(key=lambda d: (-d.count, d.item.casefold(), d.item_key))
    return out


def _gaps(exp: list, ended: float | None) -> list[float]:
    """Each EXP line's share of the active time: the gap to the next (to the end after the last), up to IDLE_S."""
    out = []
    for i, r in enumerate(exp):
        nxt = exp[i + 1].t if i + 1 < len(exp) else ended
        out.append(min(max(0.0, nxt - r.t), IDLE_S) if nxt is not None else 0.0)
    return out


def _worth(kb, r) -> int:
    price = _price(kb, r.item_key) if r.item_key else None
    return price if price is not None else (r.npc_price or 0)


@dataclass
class _Place:
    active: float = 0.0
    exp: int = 0
    mesos: int = 0
    loot: int = 0
    kills: int = 0
    logs: set = field(default_factory=set)


def _places(kb, rows, level: int | None) -> dict[str, _Place]:
    """What each map gave, per map id: active time (as a run counts it, from the EXP lines), EXP, mesos, loot,
    kills. With a level, only the pickups within SPOT_LEVELS of it (one with no level counts)."""
    by_log: dict[int, list] = {}
    for r in rows:
        if level is None or r.level is None or abs(r.level - level) <= SPOT_LEVELS:
            by_log.setdefault(r.log_id, []).append(r)
    out: dict[str, _Place] = {}
    for log_id, rs in by_log.items():
        exp = [r for r in rs if r.kind == "exp"]
        for r, gap in zip(exp, _gaps(exp, rs[0].ended)):
            m = _mid(r.map_key)
            if m:
                p = out.setdefault(m, _Place())
                p.active += gap
                p.exp += r.amount
                p.kills += 1 if r.monster_key else 0
                p.logs.add(log_id)
        for r in rs:
            m = _mid(r.map_key)
            if m and r.kind == "mesos":
                out.setdefault(m, _Place()).mesos += r.amount
            elif m and r.kind == "item":
                out.setdefault(m, _Place()).loot += r.amount * _worth(kb, r)
    return out


def _spots(kb, places: dict[str, _Place]) -> list[Spot]:
    out = []
    for m, p in places.items():
        if p.active >= SEGMENT_MIN_S:
            per_h = 3600 / p.active
            out.append(Spot(m, _map_name(kb, m), p.active, round(p.exp * per_h), round((p.mesos + p.loot) * per_h),
                            round(p.kills * per_h), len(p.logs)))
    out.sort(key=lambda s: (-s.exp_h, -s.profit_h, s.map_name.casefold(), s.map_id))
    return out


def best_spots(kb, character_id: str, level: int | None) -> list[Spot]:
    """The maps the player grinded on for SEGMENT_MIN_S at least, the most EXP an hour first; with a level, from the
    pickups within SPOT_LEVELS of it."""
    return _spots(kb, _places(kb, lootdb.events(character_id), level))


_db_cache: dict[tuple, tuple] = {}


def _db(kb, character_id: str, live_id: int | None, level: int | None, here: str) -> tuple[Counter, dict, list[Spot]]:
    """What live() needs from the loot database, read once per running log, level and map (the scanner adds only
    the running log's pickups meanwhile): the other runs' kills and drops (the running log's come from memory, newer)
    and the best spots of every run, this one's earlier maps too."""
    key = (id(kb), str(lootdb.PATH), character_id, live_id, level, here)
    hit = _db_cache.get(key)
    if hit is None:
        try:
            rows = lootdb.events(character_id)
        except (sqlite3.Error, OSError):
            log.debug("grind: the loot database couldn't be read", exc_info=True)
            rows = []
        kills, picks, _ = _book(r for r in rows if r.log_id != live_id)
        hit = (kills, picks, _spots(kb, _places(kb, rows, level)))
        _db_cache.clear()
        _db_cache[key] = hit
    return hit


def _rows_summary(kb, log_id: int, started: float, ended: float | None, rows: list) -> Summary:
    """A finished run from its database rows (no HUD reads are kept there: no deaths or potions)."""
    exp = [r for r in rows if r.kind == "exp"]
    gaps = _gaps(exp, ended)
    by_map: dict[str, float] = {}
    for r, gap in zip(exp, gaps):
        m = _mid(r.map_key)
        if m:
            by_map[m] = by_map.get(m, 0.0) + gap
    active = sum(gaps)
    mesos = sum(r.amount for r in rows if r.kind == "mesos")
    drops: dict[str, list] = {}
    loot = 0
    for r in rows:
        if r.kind == "item":
            loot += r.amount * _worth(kb, r)
            d = drops.setdefault(r.item_key or "\0" + r.item, [r.item_key, r.item, 0])
            d[2] += r.amount
    levels = [r.level for r in rows if r.level is not None]
    total = sum(r.amount for r in exp)
    return Summary(log_id, started, ended, active, total, mesos, loot, 0, mesos + loot,
                   sum(1 for r in exp if r.monster_key), (levels[0], levels[-1]) if levels else (None, None), 0,
                   _maps(kb, by_map), _top(d for d in drops.values()), _per_h(total, active),
                   _per_h(mesos + loot, active))


def _per_h(v: float, seconds: float) -> int | None:
    return round(v * 3600 / seconds) if seconds >= MIN_RATE_S else None


def _maps(kb, by_map: dict[str, float]) -> list[tuple[str, str, float]]:
    return sorted(((m, _map_name(kb, m), s) for m, s in by_map.items()), key=lambda r: (-r[2], r[1].casefold(), r[0]))


def _top(drops) -> list[tuple[str, str, int]]:
    return sorted(((k, name, n) for k, name, n in drops), key=lambda d: (-d[2], d[1].casefold(), d[0]))[:TOP_DROPS]


def history(kb, character_id: str, limit: int = 30) -> list[Summary]:
    """The character's finished runs, newest first (the running one: summary())."""
    logs = [g for g in lootdb.logs(character_id, limit=limit * 2 + 1) if g[2] is not None]
    if not logs:
        return []
    by_log: dict[int, list] = {}
    for r in lootdb.events(character_id, since=min(g[1] for g in logs)):
        by_log.setdefault(r.log_id, []).append(r)
    out = [_rows_summary(kb, log_id, started, ended, by_log[log_id]) for log_id, started, ended in logs
           if by_log.get(log_id)]
    return out[:limit]


def summary(kb, lg, character) -> Summary:
    """A run from the log itself (the running one, or one just ended): its totals, the HUD's deaths and potions. A run
    long enough that its log let its oldest pickups go: the totals are all of it, the active time, maps and rates
    those of the pickups it still holds."""
    run = _analyse(kb, lg, lg.ended if lg.ended is not None else time.time())
    exp, mesos, got = lg.totals()
    loot = sum(n * (_price(kb, key) or 0) for n, key in got.values())
    by_map: dict[str, float] = {}
    for a, b, m in run.spans:
        if m:
            by_map[m] = by_map.get(m, 0.0) + b - a
    levels = [e.level for e, _ in run.exp if e.level is not None]
    first = run.first.level if run.first is not None else (levels[0] if levels else None)
    last = run.last.level if run.last is not None else (levels[-1] if levels else None)
    if last is None and character is not None:
        last = character.level
    rates = _rates(run, run.window, True, run.active)
    return Summary(lg.db_id, lg.start, lg.ended, run.active, exp, mesos, loot, run.potion_cost,
                   mesos + loot - run.potion_cost, run.kill_cum[-1], (first, last), len(run.deaths), _maps(kb, by_map),
                   _top((key, name, n) for name, (n, key) in got.items()), rates.exp_h, rates.profit_h)
