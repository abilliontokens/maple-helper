"""Quests for the player's level, straight from the KB's quest pages: who gives them, what they ask,
what they pay, and the questlines their prerequisites make (chain_of, progress, chains_for). Done quests are kept
per character (Character.quests_done)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import availability

WINDOW_BELOW = 200    # every quest under you that isn't done (a Lv. 13 one skipped at 31 must still show: the
                      # owner); best EXP first, so the old cheap ones sit at the end
WINDOW_ABOVE = 4      # and these coming soon


@dataclass
class Quest:
    key: str
    name: str
    level: int                          # to take it ("Minimum Level"; a page without one: level 1)
    npc: str = ""
    area: str = ""
    exp: int = 0
    mesos: int = 0
    job: str = ""                       # "Beginner only", "Warrior" ... ("" = any)
    afters: list[str] = field(default_factory=list)     # every quest that must be done first ("Quest Complete")
    needs: list[str] = field(default_factory=list)      # "Green Mushroom Cap x 20", "Defeat Blue Snail x 10"
    rewards: list[str] = field(default_factory=list)    # items you surely get (EXP, mesos and fame are separate)
    fame: int = 0
    # "Pick one (class-specific)": the choices per class ("Warrior" -> [...], "Any Class" -> [...]); you pick one
    class_rewards: dict[str, list[str]] = field(default_factory=dict)
    # "Random reward - one of:": the set per class, each with its odds ("Bronze Ore x 7 (16.7%)"); you get one
    random_rewards: dict[str, list[str]] = field(default_factory=dict)
    complete_level: int = 0             # "Level 52+ to complete": taken earlier, finished only from this level
    grade: tuple[str, int] | None = None                # ("Henesys", 9): the citizenship grade it asks
    profession: tuple[str, int] | None = None           # ("Smithing", 5): "Profession Smithing Lv. 5+"
    # a reward that depends on the character's gender, written on the flat Rewards line with the gender before it
    # (pages/quest/10508.md "Male Blue Sauna Robe x 1 Female Red Sauna Robe x 1"): "Male" -> ["Blue Sauna Robe x 1"]
    gender_rewards: dict[str, list[str]] = field(default_factory=dict)
    min_fame: int = 0                   # "Fame 10 +" (pages/quest/10401.md): the Fame it takes to accept
    accept_cost: int = 0                # "Pay 1,000 mesos to accept." (pages/quest/10303.md)
    # any other pre-requisite line, kept word for word so it is never lost ("Must not already have: ...")
    notes: list[str] = field(default_factory=list)
    self_start: bool = False            # "Self-Starting": it opens on its own, no NPC hands it out
    task: str = ""                      # what to do, the game's quest journal ("Arthur asked me to greet Rina ...")
    turn_in: str = ""                   # who it is finished with, when not its giver ("Start: Arthur · Turn in: Roxy")
    cycle: str = ""                     # "daily" / "weekly": done again every day / week (the page's "Daily")

    def matches(self, query: str) -> bool:
        """The quest search: every word of the query in its name, NPC, area, what it asks or what it gives."""
        text = " ".join([self.name, self.npc, self.area, *self.needs, *self.rewards,
                         *(r for rs in self.class_rewards.values() for r in rs),
                         *(r for rs in self.gender_rewards.values() for r in rs)]).lower()
        return all(w in text for w in query.lower().split())

    @property
    def after(self) -> str:
        """The quests to do first, as one line ("A, B")."""
        return ", ".join(self.afters)

    def _for_class(self, table: dict[str, list[str]], base_class: str) -> list[str]:
        own = table.get(base_class, []) if base_class else []
        return own + [x for x in table.get("Any Class", []) if x not in own]

    def rewards_pick(self, base_class: str) -> list[str]:
        """The class-specific reward choices for this class, and the ones for any class (pick one)."""
        return self._for_class(self.class_rewards, base_class)

    def rewards_random(self, base_class: str) -> list[str]:
        """The random reward set for this class, and the one for any class (you get one of them)."""
        return self._for_class(self.random_rewards, base_class)

    def rewards_gender(self, t) -> list[str]:
        """The gender-dependent rewards, each marked with the gender that gets it (the profile has no gender)."""
        return [t(f"q_gender_{g}", item=item) for g, items in self.gender_rewards.items() for item in items]

    def prereq_hints(self, t) -> list[str]:
        """The pre-requisites the card lists beside grade and profession: Fame, a fee to accept, and any line
        the parser has no field for (kept as the KB writes it)."""
        out = []
        if self.min_fame:
            out.append(t("q_min_fame", n=self.min_fame))
        if self.accept_cost:
            out.append(t("q_accept_cost", n=f"{self.accept_cost:,}"))
        return out + self.notes

    def opens_at(self) -> int:
        """The level it can be done at: to take it, and to complete it."""
        return max(self.level, self.complete_level)


def _section(lines: list[str], head: str, stops=("Pre-requisites", "Requirements", "Rewards", "Description",
                                                  "On Acceptance", "Random reward - one of:")) -> list[str]:
    if head not in lines:
        return []
    out = []
    for ln in lines[lines.index(head) + 1:]:
        if ln in stops:
            break
        if ln:
            out.append(ln)
    return out


# "Defeat Dark Axe Stump x 100 Dexterity Potion x 5": each name runs up to its own " x <count>"
# (a lowercase x inside a name, "Axe" or "Dexterity", is part of the name)
_ITEM = re.compile(r"((?:Defeat |Collect )?\S.*?) x ([\d,]+)(?!\S)")
# a random reward with its odds: "Bronze Ore x 7 16.7 %"
_ODDS_ITEM = re.compile(r"(\S.*?) x ([\d,]+) ([\d.]+) %")
# the class headers inside a reward block ("Any Class" and "Beginner" too)
CLASSES = ("Warrior", "Magician", "Bowman", "Thief", "Pirate", "Beginner", "Any Class")
_GRADE = re.compile(r"^(.+?): Citizenship grade (\d+)\s*")
_COMPLETE_LV = re.compile(r"Level (\d+)\+ to complete")
_PROFESSION = re.compile(r"^Profession (\w+) Lv\. (\d+)\+")
_FAME = re.compile(r"^Fame ([\d,]+) ?\+$")                       # "Fame 10 +"
_ACCEPT_COST = re.compile(r"^Pay ([\d,]+) mesos to accept\.?$")    # "Pay 1,000 mesos to accept."
_MIN_LEVEL = re.compile(r"^Level Lv\. \d+\+$")                   # the level line (props "Minimum Level" has it)
GENDERS = ("Male", "Female")


def _split_owner(kb, item: str) -> tuple[str, str] | None:
    """A flat Rewards item that names its class or gender first ("Warrior Dark Knuckle x 1", "Male Blue Sauna
    Robe x 1", pages/quest/10007.md and 10508.md): (owner, "Dark Knuckle x 1"), when the rest is a KB item and the
    whole name is not one ("Warrior Potion" is an item of its own)."""
    owner, _, rest = item.partition(" ")
    if owner not in GENDERS and (owner not in CLASSES or owner == "Any Class"):
        return None
    name = rest.rsplit(" x ", 1)[0].strip().lower()
    items = getattr(kb, "_item_by_name", {})
    if name in items and item.rsplit(" x ", 1)[0].strip().lower() not in items:
        return owner, rest
    return None


def _rewards_by_class(lines: list[str], head: str, parse) -> dict[str, list[str]]:
    """A "Pick one (class-specific):" / "Random reward - one of:" block: class header lines, then their items."""
    out: dict[str, list[str]] = {}
    if head not in lines:
        return out
    cls = "Any Class"
    for ln in lines[lines.index(head) + 1:]:
        if ln in CLASSES:
            cls = ln
            continue
        items = parse(ln)
        if not items:
            break                    # the next section ("Description", "On Acceptance", ...)
        out.setdefault(cls, []).extend(items)
    return out


@lru_cache(maxsize=1024)
def _quest(kb, key: str) -> Quest | None:
    e = kb.get(key)
    if not e or e.get("category") != "quest":
        return None
    p = e.get("props") or {}
    lv = p.get("Minimum Level")
    if not isinstance(lv, (int, float)):
        lv = 1                       # no level line ("Bringing a Mirror to Heena"): anyone can take it
    lines = [ln.strip() for ln in kb.page(key).split("\n---", 2)[-1].splitlines()]
    q = Quest(key, e["name"], int(lv), str(p.get("NPC") or ""), str(p.get("Area") or ""),
              int(p.get("EXP Reward") or 0), int(p.get("Meso Reward") or 0))
    for ln in _section(lines, "Pre-requisites"):
        # "Henesys: Citizenship grade 5 Level 32+ to complete Quest Complete First Greeting with Chief Stan"
        g = _GRADE.match(ln)
        if g:
            q.grade = (g.group(1), int(g.group(2)))
            ln = ln[g.end():]
        c = _COMPLETE_LV.search(ln)
        if c:
            q.complete_level = int(c.group(1))
            ln = ln[c.end():].strip()
        pr = _PROFESSION.match(ln)
        fame, cost = _FAME.match(ln), _ACCEPT_COST.match(ln)
        if ln.startswith("Job "):
            q.job = ln[4:].strip()
        elif ln.startswith("Quest Complete "):
            q.afters.append(ln[len("Quest Complete "):].strip())
        elif pr:
            q.profession = (pr.group(1), int(pr.group(2)))
        elif fame:
            q.min_fame = int(fame.group(1).replace(",", ""))
        elif cost:
            q.accept_cost = int(cost.group(1).replace(",", ""))
        elif ln and not _MIN_LEVEL.match(ln):
            q.notes.append(ln)
    for ln in _section(lines, "Requirements"):
        q.needs += [f"{name.strip()} x {n}" for name, n in _ITEM.findall(ln)] or [ln]
    head = lines[:lines.index("Pre-requisites")] if "Pre-requisites" in lines else lines[:12]
    q.self_start = "Self-Starting" in head
    q.cycle = "daily" if "Daily" in head else "weekly" if "Weekly" in head else ""
    for ln in head:
        m = re.search(r"Turn in: (.+?)(?:\s+·|$)", ln)
        if m:
            q.turn_in = m.group(1).strip()
        m = re.search(r"Start: (.+?)(?:\s+·|$)", ln)
        if m and not q.npc:
            q.npc = m.group(1).strip()
    # the journal's step that says what to do ("02 ..."), else the description's first line ("01 ...")
    for ln in lines:
        if ln.startswith("Quest journal"):
            m = re.search(r"\b02 (.+?)$", ln)
            if m:
                q.task = m.group(1).strip()
            break
    if not q.task:
        first = next((ln for ln in lines if ln.startswith("01 ")), "")
        q.task = first[3:].strip()
    q.task = re.sub(r"^(?:⌄\s*)?(?:\d\d\s+)?", "", q.task).strip()      # "⌄ 02 I met Heena": the page's markers
    pick = False                     # inside "Pick one (class-specific):"
    for ln in _section(lines, "Rewards"):
        fame = re.search(r"\+ ?(\d+) Fame", ln)
        if fame:
            q.fame = int(fame.group(1))
        if re.fullmatch(r"([\d,]+ EXP)?\s*([\d,]+ Mesos)?\s*(\+ ?\d+ Fame)?", ln):
            continue
        if ln.startswith("Pick one (class-specific)"):
            pick = True
            break
        for item in (f"{name.strip()} x {n}" for name, n in _ITEM.findall(ln)):
            owned = _split_owner(kb, item)
            if not owned:
                q.rewards.append(item)
            elif owned[0] in GENDERS:
                q.gender_rewards.setdefault(owned[0], []).append(owned[1])
            else:                    # the class's own item: shown only to that class, under "pick one"
                q.class_rewards.setdefault(owned[0], []).append(owned[1])
    if pick:
        picked = _rewards_by_class(
            lines, next(ln for ln in lines if ln.startswith("Pick one (class-specific)")),
            lambda ln: [f"{name.strip()} x {n}" for name, n in _ITEM.findall(ln)])
        for cls, items in picked.items():
            q.class_rewards.setdefault(cls, []).extend(items)
    q.random_rewards = _rewards_by_class(
        lines, "Random reward - one of:",
        lambda ln: [f"{name.strip()} x {n} ({pct}%)" for name, n, pct in _ODDS_ITEM.findall(ln)])
    return q


# when a daily / weekly quest comes back: the KB names no reset time, so nothing here claims one. A daily quest
# marked done is back the next calendar day on the player's clock, a weekly one seven days after it was marked
# (the owner: "be airtight, don't make things up")


def back_at(cycle: str, done_at: float) -> float:
    """When a daily / weekly quest marked done at done_at is on the list again."""
    from datetime import datetime, timedelta
    if cycle == "weekly":
        return done_at + 7 * 86400
    day = datetime.fromtimestamp(done_at).replace(hour=0, minute=0, second=0, microsecond=0)
    return (day + timedelta(days=1)).timestamp()


def expire_cycles(kb, c, now: float | None = None) -> bool:
    """A daily / weekly quest marked done whose time is up is to do again: off the done list. True if any."""
    import time
    now = time.time() if now is None else now
    changed = False
    for key, when in list((c.cycle_done or {}).items()):
        q = quest(kb, key)
        if q is None or not q.cycle or not isinstance(when, (int, float)) or now >= back_at(q.cycle, when):
            c.cycle_done.pop(key, None)
            if key in c.quests_done:
                c.quests_done.remove(key)
            changed = True
    return changed


def mark_done(kb, c, keys, now: float | None = None) -> list[str]:
    """These quests marked done for the character (Character.quests_done, in this order: the last is the newest): a
    daily / weekly one with when (cycle_done: it comes back after the reset), each leaving the chat's started quests
    (Character.finish_quest: done here is done for the AI too). The keys newly marked; the caller saves."""
    import time
    now = time.time() if now is None else now
    out = []
    for key in keys:
        if key in c.quests_done:
            continue
        c.quests_done.append(key)
        out.append(key)
        q = quest(kb, key)
        if q and q.cycle:
            c.cycle_done[key] = now
        if q:
            c.finish_quest(q.name)
    return out


def unmark(c, key: str) -> bool:
    """A quest marked done by mistake (or a donation to do again) back on the lists. True if it was marked."""
    if key not in c.quests_done:
        return False
    c.quests_done.remove(key)
    c.cycle_done.pop(key, None)
    return True


_TASKS_HE: dict | None = None


def task_text(q: Quest, lang: str, kb=None) -> str:
    """What to do, in the player's language: the Hebrew of assets/quest_tasks/he.json while its English is still
    the page's (a changed journal line falls back to the English until it is translated again)."""
    global _TASKS_HE
    if lang != "he" or not q.task:
        return q.task
    from . import translations
    made = translations.he(getattr(kb, "root", None), "quest_tasks", q.key, q.task)
    if made:
        return made
    if _TASKS_HE is None:
        path = Path(__file__).resolve().parent.parent / "assets" / "quest_tasks" / "he.json"
        try:
            _TASKS_HE = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _TASKS_HE = {}
    row = _TASKS_HE.get(q.key) or {}
    return row.get("he") if row.get("en") == q.task and row.get("he") else q.task


def _required(kb) -> set[str]:
    """Every quest name another quest asks to be done first ("Quest Complete First Greeting with Rina")."""
    got = kb.__dict__.get("_quests_required")
    if got is None:
        got = set()
        for k, e in kb.entities.items():
            if e.get("category") == "quest":
                q = _quest(kb, k)
                if q:
                    got.update(" ".join(a.split()) for a in q.afters)
        kb.__dict__["_quests_required"] = got
    return got


def _asked_after(kb) -> set[str]:
    """Every X of an "Asking After X" quest: its "First Greeting with X" is the step done once before it."""
    got = kb.__dict__.get("_quests_asked_after")
    if got is None:
        got = set()
        for e in kb.entities.values():
            name = " ".join(str(e.get("name", "")).split()).rstrip(".") if e.get("category") == "quest" else ""
            if name.startswith("Asking After "):
                got.add(name.removeprefix("Asking After "))
        kb.__dict__["_quests_asked_after"] = got
    return got


def quest(kb, key: str) -> Quest | None:
    q = _quest(kb, key)
    # the board's "Daily" tag on a quest another one asks for first is a step done once ("First Greeting with
    # Rina" opens the repeatable "Asking After Rina"), not one to do again every day (the owner)
    name = " ".join(q.name.split()).rstrip(".") if q is not None else ""
    if q is not None and q.cycle and name in _required(kb):
        q.cycle = ""
    # "Asking After Athena Pierce" is the one whose page names no prerequisite: its First Greeting stayed daily
    # (audit GAM-7)
    if q is not None and q.cycle and (name.startswith("First Greeting with ")
                                      and name.removeprefix("First Greeting with ") in _asked_after(kb)):
        q.cycle = ""
    return q


def job_fits(q: Quest, base_class: str, job: str) -> bool:
    beginner = base_class == "Beginner" or (job or "") == "Beginner"
    # Maple Island is behind a one-way boat: once a job is taken its quests can't be done (one of them stayed in
    # the list of a Lv. 31 Assassin's skipped quests, the owner)
    if q.area == "Maple Island" and base_class and not beginner:
        return False
    if not q.job:
        return True
    if q.area == "Job Advancement" and job:
        # the 2nd job's quests ("The Warrior's Next Journey") are for the class's 1st job only: a Fighter 35 had
        # them under missed quests, a Beginner 30 under now (audit GAM-2)
        from .jobs import JOBS
        tiers = JOBS.get(base_class) or []
        if job in {j for js in JOBS.values() for j, _ in js}:
            return len(tiers) > 1 and job == tiers[1][0] and base_class.lower() in q.job.lower()
    j = q.job.lower()
    if "beginner" in j:
        # a character still a Beginner, whatever class they plan (the profile's class can be set ahead)
        return beginner
    return base_class.lower() in j or (job or "").lower() in j


def craft_fits(q: Quest, crafts: dict | None) -> bool:
    """A "Profession X Lv. N+" quest: the character's level in that profession reaches N (Character.crafts)."""
    if not q.profession or crafts is None:
        return True
    name, lv = q.profession
    return int(crafts.get(name.lower(), 0) or 0) >= lv


def for_level(kb, level: int, base_class: str = "", job: str = "", done: list[str] | None = None,
              crafts: dict | None = None) -> dict:
    """{"now": quests you can take (best EXP first), "level": those opening at this level, "missed": those from
    earlier levels not done, "soon": unlocking at the next level, "later": every one after it,
    "town": the citizenship donations (repeatable, 100 items each), "done": count}.

    A quest finished only from a higher level ("Level 52+ to complete") counts at that level; one that asks a
    profession level the character doesn't have (crafts given) is left out."""
    # worked out once per character state and KB object: the Quests window, its search and a click to a quest each
    # asked for the same lists again (~1 s on a cold open, TL1-4); fresh lists each time, so a caller can't spoil them
    state = (level, base_class, job, frozenset(done or []), tuple(sorted((crafts or {}).items())) if crafts else None)
    cache = getattr(kb, "_quests_for_level", None)
    if cache is None:
        cache = {}
        try:
            kb._quests_for_level = cache
        except AttributeError:     # a KB stand-in that takes no attributes: worked out each time
            pass
    if state not in cache:
        if len(cache) >= 16:
            cache.pop(next(iter(cache)))
        cache[state] = _for_level(kb, level, base_class, job, done, crafts)
    return {k: list(v) if isinstance(v, list) else v for k, v in cache[state].items()}


def _for_level(kb, level: int, base_class: str, job: str, done: list[str] | None, crafts: dict | None) -> dict:
    done_set = set(done or [])
    now, future, town = [], [], []
    open_ = availability.of(kb)
    for k, e in kb.entities.items():
        # only quests the KB confirms are in the game: none in Ossyria, no event the KB marks "Ended"
        if e.get("category") != "quest" or not open_.quest_open(k):
            continue
        q = quest(kb, k)
        if not q or (base_class and not job_fits(q, base_class, job)) or not craft_fits(q, crafts):
            continue
        if k in done_set:
            continue
        lv = q.opens_at()
        if level - WINDOW_BELOW <= lv <= level:
            (town if q.area == "Citizenship" else now).append(q)
        elif lv > level and q.area != "Citizenship":
            future.append(q)
    now.sort(key=lambda q: (-q.exp, q.level))
    future.sort(key=lambda q: (q.opens_at(), -q.exp))
    # the Quests window's tabs (the owner's): the next level alone is "coming up", every level after it "later"; one
    # level up, each list moves along (32's become this level's, 33's come up next)
    soon = [q for q in future if q.opens_at() == level + 1]
    later = [q for q in future if q.opens_at() > level + 1]
    town.sort(key=lambda q: -q.exp)
    # the Quests window's two lists (the owner's): the quests that open at this very level, and every one from a level
    # before it that isn't done, newest level first (a Lv. 31 quest left undone moves there at 32)
    at_level = [q for q in now if q.opens_at() == level]
    missed = sorted((q for q in now if q.opens_at() < level), key=lambda q: (-q.opens_at(), -q.exp))
    return {"now": now, "level": at_level, "missed": missed, "soon": soon, "later": later, "town": town,
            "done": len(done_set)}


def closed_areas(kb) -> list[str]:
    """The areas whose quests the KB doesn't confirm are in the game yet ("El Nath"), most quests first."""
    from collections import Counter
    open_ = availability.of(kb)
    found = Counter()
    for k, e in kb.entities.items():
        if e.get("category") == "quest" and not open_.quest_open(k):
            q = quest(kb, k)
            if q and q.area and "event" not in q.area.lower():      # an ended event is no area to open
                found[q.area] += 1
    return [a for a, _ in found.most_common()]


# ------------------------------------------------------------------ citizenship

TOWNS = ("Henesys", "Kerning City")          # the towns with citizenship (their donation boards in the KB)


def town_of(kb, q: Quest) -> str:
    """The citizenship town a quest belongs to: the town whose citizenship grade it requires, its board's town,
    the town its name invites you to (the openers, "To Henesys, the Prairie Town" pages/quest/506000.md, and
    "To the Gray City, Kerning City" 506100.md, handed out by Henesys' Arthur), else where its NPC stands
    (Jake and Mr. Goldstein's pages name no town, their quests ask Kerning's grade)."""
    if q.grade and q.grade[0] in TOWNS:
        return q.grade[0]
    m = re.search(r"\((.+)\)", q.npc or "")
    if m and m.group(1) in TOWNS:
        return m.group(1)
    named = [t for t in TOWNS if re.search(rf"\b{re.escape(t)}\b", q.name)]
    if len(named) == 1:
        return named[0]
    key = kb._npc_by_name.get((q.npc or "").lower())
    page = kb.page(key) if key else ""
    hits = [(page.find(t), t) for t in TOWNS if t in page]
    return min(hits)[1] if hits else ""


def citizenship(kb, town: str, level: int, done: list[str] | None = None) -> list[Quest]:
    """The town's citizenship quests (donations and the rest) you can do now, best EXP first
    (one you can take but only complete at a higher level, "Level 52+ to complete", waits for that level)."""
    done_set = set(done or [])
    out = []
    open_ = availability.of(kb)
    for k, e in kb.entities.items():
        if e.get("category") != "quest" or k in done_set or not open_.quest_open(k):
            continue
        q = quest(kb, k)
        if q and q.area == "Citizenship" and q.opens_at() <= level and town_of(kb, q) == town:
            out.append(q)
    return sorted(out, key=lambda q: (-q.exp, q.level))


# ------------------------------------------------------------------ quest chains
# A quest's page names the quests to finish first ("Quest Complete Delivering the Weird Medicine"), by name. Read
# backwards they are the game's questlines: each quest follows the deepest of them (the longest way back to a quest
# that asks none), so it sits on one line, at the step its page says ("Questline · Step 8 of 11": Maya's First
# Collection, pages/quest/10115.md), and a line splits where several quests follow one ("Line splits here.": after
# Delivering the Weird Medicine, Maya's collections, Old Gladius and An Unknown Savior). Any other quest a step asks
# stays a prerequisite of it (An Unknown Savior also asks First Greeting with Maya, a step of no line of its own),
# never a step: a reason it is locked.


def _name_key(name: str) -> str:
    """A quest's name as the prerequisites are matched by it: spaces collapsed as _required does, a closing period
    and the case aside ("Asking After Mrs. Ming Ming, the Town Resident." is its page's name)."""
    return " ".join(str(name).split()).rstrip(".").casefold()


@dataclass
class _Links:
    """Every quest's prerequisites as keys, worked out once per KB (_links)."""
    parents: dict[str, list[str]]       # quest -> the quests to finish first (resolved names, the page's order)
    depth: dict[str, int]               # quest -> its step on its line: 1 + the deepest prerequisite's
    prev: dict[str, str]                # quest -> the prerequisite whose line it continues ("" for a line's first)
    kids: dict[str, list[str]]          # quest -> the quests continuing its line, the lowest level first
    firsts: dict[str, str]              # another first step of a line -> the step it opens there (The Stump Horror
                                        # Story -> I Need to Find My Daughter 1)


def _links(kb) -> _Links:
    got = kb.__dict__.get("_quest_links")
    if got is not None:
        return got
    qs = {k: q for k, e in kb.entities.items() if e.get("category") == "quest" and (q := _quest(kb, k))}
    by_name: dict[str, list[str]] = {}
    for k, q in qs.items():
        by_name.setdefault(_name_key(q.name), []).append(k)
    parents: dict[str, list[str]] = {}
    for k, q in qs.items():
        out: list[str] = []
        for name in q.afters:
            hits = [h for h in by_name.get(_name_key(name), []) if h != k]
            if len(hits) > 1:
                # a name two quests share ("Becoming a Citizen of Honor", Henesys' and Kerning City's): the one of
                # the asking quest's own town, else of its area
                town = town_of(kb, q)
                hits = ([h for h in hits if town and town_of(kb, qs[h]) == town]
                        or [h for h in hits if qs[h].area == q.area] or hits)[:1]
            out += [h for h in hits if h not in out]
        parents[k] = out
    depth: dict[str, int] = {}

    def deep(k: str, path: set) -> int:
        if k not in depth:
            path.add(k)
            # (a loop the KB should never have is cut where it closes)
            depth[k] = 1 + max((deep(p, path) for p in parents[k] if p not in path), default=0)
            path.discard(k)
        return depth[k]
    for k in qs:
        deep(k, set())
    prev: dict[str, str] = {}
    kids: dict[str, list[str]] = {}
    for k, ps in parents.items():
        # the deepest prerequisite; a tie: one off the Citizenship board (Camila's Gem, not First Greeting with
        # Camila: A Gift for Pia continues Camila's story), then the page's order
        below = [p for p in ps if depth[p] < depth[k]]
        best = max(below, key=lambda p: (depth[p], qs[p].area != "Citizenship", -ps.index(p)), default="")
        prev[k] = best
        if best:
            kids.setdefault(best, []).append(k)
    for ks in kids.values():
        ks.sort(key=lambda k: (qs[k].opens_at(), qs[k].name))
    # a line's first quest tied with another first quest (I Need to Find My Daughter 1 asks both The Reason Behind the
    # Mushroom Studies and The Stump Horror Story, each a line's first step): the one left with no line of its own is
    # the other first step of that line, as its page says ("Questline · Step 1 of 3", pages/quest/10411.md)
    firsts: dict[str, str] = {}
    for k, ps in parents.items():
        best = prev[k]
        for p in ps:
            if best and p != best and depth[p] == depth[best] == 1 and p not in kids and p not in firsts:
                firsts[p] = k
    got = _Links(parents, depth, prev, kids, firsts)
    kb.__dict__["_quest_links"] = got
    return got


@dataclass
class Chain:
    """A questline from the quest that starts it (root), as a character can do it: only the quests the KB confirms
    are in the game and that fit the character's job, a step left out with every step after it. order: every step,
    each followed by the steps after it (a split's lines the lowest level first; another first step, _Links.firsts,
    right after the root); prev: the step each follows ("" for a first); nexts: the steps right after it (two or more:
    the line splits there); step: its number on its line; also: the other quests a step asks first, off the line."""
    root: str
    order: list[str]
    prev: dict[str, str]
    nexts: dict[str, list[str]]
    step: dict[str, int]
    also: dict[str, list[str]]

    def __contains__(self, key: str) -> bool:
        return key in self.step

    def __len__(self) -> int:
        return len(self.order)

    def line(self, key: str) -> list[str]:
        """The line a step is on: back to the chain's first step, then on until the line ends or splits."""
        back = [key]
        while self.prev.get(back[-1]):
            back.append(self.prev[back[-1]])
        out = back[::-1]
        while len(self.nexts.get(out[-1], [])) == 1:
            out.append(self.nexts[out[-1]][0])
        return out

    def at(self, key: str) -> tuple[int, int]:
        """(the step's number, how many steps its line has): "Step 8 of 11"."""
        return self.step[key], len(self.line(key))

    def before(self, key: str) -> list[str]:
        """The steps before this one on its line, the first first."""
        out = []
        while self.prev.get(key):
            key = self.prev[key]
            out.append(key)
        return out[::-1]

    def branch(self, key: str) -> int:
        """How many splits lie before this step (0 on the first line): how far in a list of the chain it sits."""
        return sum(1 for k in self.before(key) if len(self.nexts.get(k, [])) > 1)


def chain_of(kb, key: str, base_class: str = "", job: str = "") -> Chain | None:
    """The questline a quest is on, for a character of this class and job (none given: every class's), or None when
    it is on none: no other quest asks it, it asks none, or the character can't do two of its steps."""
    links = _links(kb)
    if key not in links.prev:
        return None
    root = links.firsts.get(key, key)
    while links.prev[root]:
        root = links.prev[root]
    open_ = availability.of(kb)

    def fits(k: str) -> bool:
        q = quest(kb, k)
        return q is not None and open_.quest_open(k) and (not base_class or job_fits(q, base_class, job))
    if not fits(root):
        return None
    order: list[str] = []
    prev, nexts, step, also = {root: ""}, {}, {root: 1}, {}
    todo = [root]
    while todo:
        k = todo.pop()
        order.append(k)
        also[k] = [p for p in links.parents[k] if p != prev[k]]
        nexts[k] = [c for c in links.kids.get(k, []) if fits(c)]
        for c in nexts[k]:
            prev[c], step[c] = k, step[k] + 1
        todo += reversed(nexts[k])          # depth first: a line, then the next line of a split
    for first, opens in links.firsts.items():
        if opens in step and step[opens] == 2 and fits(first):
            order.insert(1, first)
            prev[first], nexts[first], step[first], also[first] = "", [opens], 1, list(links.parents[first])
    if len(order) < 2 or key not in step:
        return None
    return Chain(root, order, prev, nexts, step, also)


def _before(links: _Links, keys) -> set[str]:
    """Every quest before these: their prerequisites, and theirs."""
    seen: set[str] = set()
    todo = [p for k in keys for p in links.parents.get(k, [])]
    while todo:
        k = todo.pop()
        if k not in seen:
            seen.add(k)
            todo += links.parents.get(k, [])
    return seen


def prerequisites(kb, key: str) -> list[str]:
    """The quests this one asks to finish first, as keys (its "Quest Complete" names resolved, the page's order)."""
    return list(_links(kb).parents.get(key, []))


def opens(kb, key: str) -> list[str]:
    """The quests that ask this one first: what finishing it opens."""
    return [k for k, ps in _links(kb).parents.items() if key in ps]


def _item_givers(kb) -> dict[str, list[str]]:
    """An item's key -> the quests that surely hand it over, worked out once per KB (the rewards table's "sure"
    rows: a pick-one choice or a random roll is no promise the item will be there)."""
    got = kb.__dict__.get("_quest_item_givers")
    if got is None:
        from . import tables
        got = {}
        for r in tables.rows(kb, "rewards"):
            if r.get("kind") != "sure":
                continue
            item, giver = str(r.get("item_key") or ""), str(r.get("quest_key") or "")
            if item and giver and giver not in got.setdefault(item, []):
                got[item].append(giver)
        kb.__dict__["_quest_item_givers"] = got
    return got


def item_givers(kb, item_key: str, key: str = "") -> list[str]:
    """The quests that hand this item over, as keys: an item a quest asks for that no monster drops comes from one
    of these (Arcon's Blood is Manji's reward for "Arcon's Blood?", and "Getting Arcon's Blood" asks for it).

    The quest the player on `key` would actually do comes first: one `key` asks to finish first, then an earlier
    step of its line, then another step of the same line, then the rest, the lowest level first. `key` itself is
    never one of them (a quest that gives what it asks for is no source to go to)."""
    givers = [k for k in _item_givers(kb).get(item_key, []) if k != key]
    if not givers or not key:
        return givers
    parents = set(prerequisites(kb, key))
    before = set(earlier_steps(kb, key))
    chain = chain_of(kb, key)
    line = set(chain.order) if chain else set()

    def place(k: str) -> tuple:
        q = quest(kb, k)
        near = 0 if k in parents else 1 if k in before else 2 if k in line else 3
        return near, (q.opens_at() if q else 0), (q.name if q else k)
    return sorted(givers, key=place)


def earlier_steps(kb, key: str) -> list[str]:
    """Every quest done before this one can be: its prerequisites and theirs, the first first (what to mark done
    with it: the game never lets a step be done before them)."""
    links = _links(kb)
    return sorted(_before(links, [key]) - {key}, key=lambda k: (links.depth.get(k, 0), k))


def done_with_earlier(kb, done) -> set[str]:
    """The quests marked done and every quest before one of them: the game lets no quest be done before the ones it
    asks, marked or not."""
    return set(done or []) | _before(_links(kb), done or [])


@dataclass
class ChainState:
    """Where a character stands on a chain. done: the steps done (marked, or before a step marked: the game lets no
    step be done before the ones it asks); open: the steps to do now, in the chain's order; why: each other step's
    reasons, (kind, value) in this order: ("level", 47) opens at that level, ("after", key) that quest first,
    ("profession", ("Smithing", 5)) that profession's level; exp_left: the EXP of the steps not done."""
    chain: Chain
    done: set[str]
    open: list[str]
    why: dict[str, list[tuple[str, object]]]
    exp_left: int

    def state(self, key: str) -> str:
        """"done", "open" (can be done now) or "locked"."""
        return "done" if key in self.done else "open" if key in self.open else "locked"

    @property
    def total(self) -> int:
        return len(self.chain)

    @property
    def status(self) -> str:
        """"done" (every step), "progress" (some done), "start" (none, the first can be done now) or "later"."""
        n = len(self.done)
        return "done" if n == self.total else "progress" if n else "start" if self.open else "later"

    @property
    def next(self) -> str:
        """The step to do next: the first that can be done now, else the first not done (locked); "" when all are."""
        return next(iter(self.open), next((k for k in self.chain.order if k not in self.done), ""))


def progress(kb, chain: Chain, level: int, done: list[str] | None = None, crafts: dict | None = None) -> ChainState:
    """Each step of the chain for a character at this level who marked these quests done (Character.quests_done);
    crafts (Character.crafts, when the player set them) locks a step that asks a profession level not reached."""
    links = _links(kb)
    did = done_with_earlier(kb, done)
    opened, why, left = [], {}, 0
    for k in chain.order:
        if k in did:
            continue
        q = quest(kb, k)
        left += q.exp if q else 0
        reasons: list[tuple[str, object]] = []
        if q and q.opens_at() > level:
            reasons.append(("level", q.opens_at()))
        reasons += [("after", p) for p in links.parents.get(k, []) if p not in did]
        if q and crafts is not None and not craft_fits(q, crafts):
            reasons.append(("profession", q.profession))
        if reasons:
            why[k] = reasons
        else:
            opened.append(k)
    return ChainState(chain, did & set(chain.order), opened, why, left)


def chains_for(kb, level: int, base_class: str = "", job: str = "", done: list[str] | None = None,
               crafts: dict | None = None, citizenship: bool = False) -> dict[str, list[ChainState]]:
    """The questlines a character can do, by where they stand: {"progress": started, the ones with a step to do now
    first, then the most done; "start": none done yet, the first step open now, the ones opening nearest the level
    first; "later": the first step still locked, the soonest first; "done": every step done}. citizenship: the lines
    that start on the Citizenship board (First Greeting with Maya -> Asking After Maya), else every other line."""
    links = _links(kb)
    out: dict[str, list[ChainState]] = {"progress": [], "start": [], "later": [], "done": []}
    for root, kids in links.kids.items():
        if links.prev.get(root) or not kids:
            continue
        q = quest(kb, root)
        if q is None or (q.area == "Citizenship") != citizenship:
            continue
        chain = chain_of(kb, root, base_class, job)
        if chain is not None:
            s = progress(kb, chain, level, done, crafts)
            out[s.status].append(s)

    def opens(s: ChainState) -> int:
        r = quest(kb, s.chain.root)
        return r.opens_at() if r else 0
    out["progress"].sort(key=lambda s: (not s.open, -len(s.done) / s.total, opens(s)))
    out["start"].sort(key=lambda s: (-opens(s), -s.exp_left))
    out["later"].sort(key=lambda s: (opens(s), -s.exp_left))
    out["done"].sort(key=lambda s: opens(s))
    return out
