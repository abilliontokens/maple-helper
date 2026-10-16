"""Combat math for Grind spots and the search's Hit & damage: hit chance, accuracy needed, hits to kill, where to train.

Formulas from the KB's guide "Explaining the Damage Formula" (MapleStory Classic World, COT2):
  L = max(0, MobLevel - PlayerLevel);  A = TotalACC x 100 / (10 x L + 255);  D = A - MobAvoid
  f = 0.15 + 0.20 / (1 + exp(D / 12));  hit when A x R >= MobAvoid,  R ~ uniform(1 - f, 1 + f)
  defended hit = Raw x 100 / (DEF + 100);  higher-level target: x 1/(1 + Gap^2 x 0.005) (Gap 1-9),
  x 1/(1 + Gap x 0.05) (Gap >= 10)
Monster numbers (level, HP, EXP, avoid, defense, maps) come from the KB's monster pages.
Everything here is instant and local: no AI call.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import availability

# base accuracy per class: Common = 1.2 x DEX + 2 x Level + 0.6 x LUK
ACC_DIVISOR = {"Beginner": (2.5, 5), "Warrior": (2.5, 10), "Bowman": (4.8, 20), "Thief": (4.0, 15)}
MAGE = "Magician"


@dataclass
class Monster:
    key: str
    name: str
    level: int
    hp: int
    exp: int
    avoid: int = 0
    pdef: int = 0
    mdef: int = 0
    maps: list[tuple[str, int]] = field(default_factory=list)     # (map, how many spawn there)
    respawn: float = 0     # seconds until it comes back, the quickest of its maps (the page's "Respawn" column)

    @property
    def boss(self) -> bool:
        """A boss or a once-an-hour spawn (Mano, Jr. Balrog): nothing to train on."""
        return self.respawn >= BOSS_RESPAWN


def _num(text: str) -> int | None:
    m = re.match(r"\s*([\d,]+)", text or "")
    return int(m.group(1).replace(",", "")) if m else None


def _after(lines: list[str], label: str) -> int | None:
    """The number on the line after a stat label ("AVOID" -> "14")."""
    for i, ln in enumerate(lines[:-1]):
        if ln.strip() == label:
            return _num(lines[i + 1])
    return None


# maps nobody can simply walk to: job-advancement tests ("Thief's Construction Site", "Ant Tunnel For Bowman"),
# party quest stages, event rooms (the KB's own rule is availability.instance_map; this catches a bare name too)
_CLOSED_MAP = re.compile(r"^(Warrior|Thief|Magician|Bowman|Pirate)'s |\bFor (?:Warrior|Thief|Magician|Bowman|Pirate)\b|"
                         r"Accompaniment|KPQ|Party Quest|Test|Event|Exam", re.I)
# ... and the ones nobody grinds on (those, and hidden streets)
_NOT_GRIND = re.compile(_CLOSED_MAP.pattern + r"|Hidden Street$", re.I)
# a version of a monster nobody grinds on: an alternate or party-quest one, which the KB names in brackets
# ("Jr. Necki (alt) (KPQ)"), and the job tests' dummies. Not the KB's Fairy 1-4: those are the game's own Fairy,
# which NiaMeowDB splits per spawn region — a level 29 field monster (593 HP, 54 EXP, back in 7.5 s) that lives
# on open Victoria Island maps, and calling it special hid every one of them from the Monsters & NPCs search
# (live). The versions nobody can reach drop out on the data: Fairy 1 has no map the KB confirms, and Fairy 2's
# only one is a Hidden Street
_NOT_GRIND_MOB = re.compile(r"\(|Dummy", re.I)


# a spawn this slow is a boss (the KB monster pages' "Respawn" column: Mano "1h-1h 30m", Jr. Balrog "3h",
# Zombie Mushmom "1h-1h 30m"; field monsters come back in seconds, the slowest ones in 5-10m)
BOSS_RESPAWN = 30 * 60
# the training range: monsters this many levels below / above the player are training spots (spots(), and a KB
# update's monster changes that matter to the player, recent.py)
SPOT_BELOW, SPOT_ABOVE = 8, 6


def special_monster(name: str) -> bool:
    """Tutorial, event and job-test versions ("Tutorial Jr. Sentinel", "Jr. Necki (alt) (KPQ)")."""
    return bool(_NOT_GRIND_MOB.search(name)) or name.startswith("Tutorial")


# What is in the game comes from the KB alone (availability.py): a map counts only when the KB confirms its
# continent is out, so Ossyria (Orbis, El Nath) and anything the KB doesn't confirm stay out of every list.

def released(kb, place: str) -> bool:
    """A town or street the KB confirms is in the game ("El Nath" is not while Ossyria isn't out)."""
    return availability.of(kb).place_open(place)


def reachable_map(kb, name: str) -> bool:
    """A map a player can go to now: not a test/PQ/event room, and confirmed in the game by the KB."""
    a = availability.of(kb)
    return not _CLOSED_MAP.search(name) and a.map_open(name) and not a.instance_map(name)


def grind_map(kb, name: str) -> bool:
    a = availability.of(kb)
    return not _NOT_GRIND.search(name) and a.map_open(name) and not a.instance_map(name)


def respawn_seconds(text: str) -> float | None:
    """The page's respawn cell in seconds, its quickest end: "~7.5s", "1m + ~7.5s", "30s-2m", "1h-1h 30m"."""
    first = (text or "").split("-")[0]
    parts = re.findall(r"([\d.]+)\s*([hms])", first)
    if not parts:
        return None
    return sum(float(n) * {"h": 3600, "m": 60, "s": 1}[u] for n, u in parts)


def _map_rows(page: str) -> list[list[str]]:
    """The "Map Locations" table: "Map | Count | Share | Types | Mob Rate | Respawn" rows."""
    i = page.find("Map Locations")
    if i < 0:
        return []
    rows = []
    for line in page[i:].split("\n")[2:]:
        if " | " not in line:
            break
        cols = [c.strip() for c in line.split(" | ")]
        if len(cols) >= 2 and cols[1].isdigit():
            rows.append(cols)
    return rows


def _maps(kb, page: str, n: int = 4) -> list[tuple[str, int]]:
    return [(c[0], int(c[1])) for c in _map_rows(page) if grind_map(kb, c[0])][:n]


def _respawn(page: str) -> float:
    found = [s for c in _map_rows(page) if len(c) >= 6 and (s := respawn_seconds(c[-1])) is not None]
    return min(found) if found else 0


def monster(kb, key: str) -> Monster | None:
    return _monster(kb, key)


@lru_cache(maxsize=512)
def _monster(kb, key: str) -> Monster | None:
    e = kb.get(key)
    if not e or e.get("category") != "monster":
        return None
    p = e.get("props") or {}
    page = kb.page(key)
    lines = page.splitlines()
    level, hp, exp = p.get("Level"), p.get("HP"), p.get("EXP")
    if not all(isinstance(v, (int, float)) for v in (level, hp, exp)) or hp <= 0:
        return None
    return Monster(key, e["name"], int(level), int(hp), int(exp), _after(lines, "AVOID") or 0,
                   _after(lines, "P.DEF") or 0, _after(lines, "M.DEF") or 0, _maps(kb, page), _respawn(page))


def monsters(kb) -> list[Monster]:
    return [m for k, e in kb.entities.items() if e.get("category") == "monster" and (m := monster(kb, k))]


# ------------------------------------------------------------------ accuracy

def hit_chance(acc: float, player_level: int, mob_level: int, mob_avoid: int) -> float:
    """Chance that one attack hits (0..1)."""
    if mob_avoid <= 0:
        return 1.0
    gap = max(0, mob_level - player_level)
    a = acc * 100 / (10 * gap + 255)
    if a <= 0:
        return 0.0
    d = a - mob_avoid
    if d >= 25 + gap * (0.5 * player_level + 15):
        return 1.0
    f = 0.15 + 0.20 / (1 + math.exp(max(-50.0, min(50.0, d / 12))))
    q = mob_avoid / a
    if q <= 1 - f:
        return 1.0
    if q >= 1 + f:
        return 0.0
    return (1 + f - q) / (2 * f)


def acc_needed(player_level: int, mob_level: int, mob_avoid: int, target: float = 1.0) -> int:
    """The lowest total ACC that reaches `target` hit chance (1.0 = never miss)."""
    for acc in range(0, 2000):
        if hit_chance(acc, player_level, mob_level, mob_avoid) >= target - 1e-9:
            return acc
    return 2000


def base_acc(base_class: str, level: int, dex: int = 0, luk: int = 0, int_: int = 0) -> int:
    """Accuracy from stats and level alone (before gear, skills and potions)."""
    if base_class == MAGE:
        return math.floor((1.2 * int_ + 2 * level + 0.6 * luk) / 5.1 + 20)
    div, add = ACC_DIVISOR.get(base_class, ACC_DIVISOR["Beginner"])
    return math.floor((1.2 * dex + 2 * level + 0.6 * luk) / div + add)


def acc_per_point(base_class: str) -> float:
    """How much base ACC one point of DEX (INT for a Magician) adds."""
    if base_class == MAGE:
        return 1.2 / 5.1
    return 1.2 / ACC_DIVISOR.get(base_class, ACC_DIVISOR["Beginner"])[0]


# ------------------------------------------------------------------ damage

def level_scale(player_level: int, mob_level: int) -> float:
    gap = mob_level - player_level
    if gap <= 0:
        return 1.0
    return 1 / (1 + gap * gap * 0.005) if gap < 10 else 1 / (1 + gap * 0.05)


def landed(raw: float, defense: int, player_level: int, mob_level: int) -> float:
    """A hit's damage on this monster: defense, then the higher-level penalty."""
    # whole numbers, as the game deals them (the KB's damage guide truncates each hit), at most 99,999
    # (pages/formula/damage.md: "Final = trunc(clamp(value, 1, 99,999))", audit GAM-15)
    return float(min(99_999, max(1, int(raw * 100 / (defense + 100) * level_scale(player_level, mob_level)))))


def damage_range(dmg_min: int | None, dmg_max: int | None) -> tuple[int, int] | None:
    """The stat window's range as typed or read: swapped when min > max, a missing max taken as the min;
    None without a usable minimum."""
    lo, hi = int(dmg_min or 0), int(dmg_max or 0)
    if hi and lo > hi:
        lo, hi = hi, lo
    if lo <= 0:
        return None
    return lo, max(lo, hi)


def hits_to_kill(dmg_min: int, dmg_max: int, m: Monster, player_level: int, magic: bool = False) -> tuple[int, float]:
    """(hits that always kill, average hits), from the damage range in the stat window.

    That range is one basic attack, no skill multiplier (for a Magician it's the staff/wand swing, a physical
    hit), so the counts are for basic attacks; magic=True only switches the defense to M.DEF."""
    defense = m.mdef if magic else m.pdef
    lo = landed(dmg_min, defense, player_level, m.level)
    avg = landed((dmg_min + dmg_max) / 2, defense, player_level, m.level)
    return math.ceil(m.hp / lo), max(1.0, m.hp / avg)


# ------------------------------------------------------------------ where to train

@dataclass
class Spot:
    monster: Monster
    map: str
    hit: float             # hit chance 0..1 (None stats -> 1)
    hits: int | None       # hits that always kill (None without a damage range)
    avg_hits: float | None
    score: float           # EXP per swing: exp x hit / average hits
    acc_needed: int        # ACC to never miss at the player's level
    recommended: bool = False
    fits: bool = True      # False: too many misses or basic-attack hits; shown only when nothing fits


def spots(kb, level: int, acc: int | None = None, dmg: tuple[int, int] | None = None, magic: bool = False,
          below: int = SPOT_BELOW, above: int = SPOT_ABOVE, n: int = 8) -> list[Spot]:
    """The best monsters to train on, best first: EXP per swing with your accuracy and damage.

    Without stats, monsters are ranked by EXP per HP near the player's level. The stat window's damage is a
    basic attack (skills hit harder), so when no monster passes the miss/hits filters, the best of the rest
    come back anyway, marked fits=False. A Magician's range is the staff swing, not a spell: it isn't used."""
    from . import plan
    guide = {s.map.lower() for s in plan.spots_for(kb, level, 5)}
    if magic:
        dmg = None
    out, hard, seen = [], [], set()
    for m in sorted(monsters(kb), key=lambda m: -sum(c for _, c in m.maps)):
        if not (level - below <= m.level <= level + above) or not m.maps or special_monster(m.name) or m.boss:
            continue                      # bosses and hourly spawns (Mano, Jr. Balrog) are no training spot
        if m.name in seen:
            continue                      # the same monster again (another version of it)
        seen.add(m.name)
        hit = hit_chance(acc, level, m.level, m.avoid) if acc else 1.0
        fits = not (acc and hit < 0.6)    # too many misses to be worth it
        if dmg and dmg[0] > 0:
            hits, avg = hits_to_kill(dmg[0], max(dmg), m, level)
            fits = fits and hits <= 12    # takes too long to kill
            score = m.exp * hit / avg
        else:
            hits = avg = None
            score = m.exp * hit * level_scale(level, m.level) / max(1, m.hp) * 1000
        top_map, count = m.maps[0]
        score *= min(1.0, count / 20) ** 0.5   # a crowded map keeps you swinging; a sparse one makes you walk
        rec = any(mp.lower().startswith(g) or g.startswith(mp.lower()) for mp, _ in m.maps for g in guide)
        (out if fits else hard).append(Spot(m, top_map, hit, hits, avg, score, acc_needed(level, m.level, m.avoid),
                                            rec, fits))
    out = out or hard
    out.sort(key=lambda s: -s.score)
    return out[:n]


def kills_to_level(kb, level: int, exp_pct: float | None, m: Monster) -> int | None:
    from . import plan
    need = plan.exp_table(kb).get(level)
    if not need or not m.exp:
        return None
    left = need * (1 - (exp_pct or 0) / 100)
    return max(0, math.ceil(left / m.exp))


def map_key(kb, cell: str) -> str | None:
    """The KB key ("map/<id>") of a map as a monster page's map cell writes it ("Snail Hunting Ground I Maple Road":
    a Spot's map), for its page and the way there; else the one map of that bare name; None when the KB has neither."""
    cell = (cell or "").strip()
    if not cell:
        return None
    hit = next((k for k, c in availability.of(kb).map_cell.items() if c == cell), None)
    if hit:
        return hit
    named = [k for k, e in kb.entities.items() if e.get("category") == "map" and e.get("name") == cell]
    return named[0] if len(named) == 1 else None


# ------------------------------------------------------------------ one character on one monster

@dataclass(frozen=True)
class Matchup:
    """Hit & damage for a character on one monster (the toolbar search's monster page): each figure None where the
    character's typed stats can't give it."""
    acc_needed: int                      # total ACC to never miss at the character's level (0: it never dodges)
    acc_needed90: int                    # ... for a 90% hit chance
    hit: float | None                    # hit chance 0..1 with the typed ACC; None without one
    acc_short: int                       # ACC still missing for 100% (0: never misses, or no ACC typed)
    stat_points: int                     # points of `stat` that close that gap (base ACC per point)
    stat: str                            # what adds ACC: INT for a Magician, else DEX
    damage: tuple[int, int] | None       # the stat window's range as typed (damage_range); None without one
    landed: tuple[int, int] | None       # ... on this monster: after its P.DEF and the higher-level penalty
    hits: int | None                     # basic hits that always kill it
    avg_hits: float | None               # ... on average
    exp: int                             # EXP one kill gives
    kills: int | None                    # kills to the next level (None past the EXP table)


def matchup(kb, m: Monster, level: int, base_class: str, exp_pct: float | None, stats: dict | None) -> Matchup:
    """The Hit & damage figures for a character (its level, class, EXP bar and stat-window stats: acc, dmg_min,
    dmg_max) on monster m. The stat window's range is one basic attack — for a Magician the staff swing, a physical
    hit — so the damage is against P.DEF for every class, as the stat window deals it."""
    s = stats or {}
    acc = int(s.get("acc") or 0) or None
    dmg = damage_range(s.get("dmg_min"), s.get("dmg_max"))
    magic = base_class == MAGE
    need = acc_needed(level, m.level, m.avoid)
    hit = hit_chance(acc, level, m.level, m.avoid) if acc else None
    short = max(0, need - acc) if acc and hit is not None and hit < 0.999 else 0
    hits = avg = landed_range = None
    if dmg:
        hits, avg = hits_to_kill(dmg[0], dmg[1], m, level)
        landed_range = (int(landed(dmg[0], m.pdef, level, m.level)), int(landed(dmg[1], m.pdef, level, m.level)))
    return Matchup(need, acc_needed(level, m.level, m.avoid, 0.9), hit, short,
                   math.ceil(short / acc_per_point(base_class)) if short else 0, "INT" if magic else "DEX",
                   dmg, landed_range, hits, avg, m.exp, kills_to_level(kb, level, exp_pct, m))
