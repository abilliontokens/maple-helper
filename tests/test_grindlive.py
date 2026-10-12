"""The live grind numbers (grindlive.py): EXP lines matched to kills, rates over active time, deaths, level-ups and
potions from the HUD reads, time to level, spawn capacity, warnings, alerts, goals, and from the loot database the
player's own drop rates, best spots and past runs."""
import json
from pathlib import Path

import pytest

from maplehelper import combat, farm, gamelookup, grindlive, lootdb, lootlog, plan, tables
from maplehelper.grindlive import Goal, Rates
from maplehelper.lootlog import Event, HudSample
from maplehelper.store import Character

FIX = Path(__file__).resolve().parent / "fixtures"
REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
LEAF, FIREWOOD, RED_SNAIL_SHELL = "item/358", "item/362", "item/351"


@pytest.fixture(scope="module")
def kb():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


def _mob(kb, name: str) -> dict:
    return next(r for r in tables.rows(kb, "monsters") if r["monster"] == name)


def _on_maps(kb) -> dict[str, set[str]]:
    """Bare map id -> the names of the monsters that spawn there (the KB's spawns table)."""
    on: dict[str, set[str]] = {}
    for r in tables.rows(kb, "spawns"):
        on.setdefault(r["map_key"].removeprefix("map/"), set()).add(r["monster"])
    return on


def _map_with(kb, *names: str) -> str:
    """The first map (by id) whose spawns hold every named monster."""
    on = _on_maps(kb)
    return next(m for m in sorted(on) if set(names) <= on[m])


@pytest.fixture(scope="module")
def rocky(kb) -> str:
    """A Perion-area map with the live check's five monsters (Rocky Road II in the KB)."""
    return _map_with(kb, "Snail", "Red Snail", "Dark Stump", "Axe Stump", "Dark Axe Stump")


def _exp(t0: int, t1: int, step: int, amount: int, mid: str, monster: str = "", level: int | None = None) -> list:
    return [Event(float(t), "exp", amount, map=mid, monster=monster, level=level) for t in range(t0, t1 + 1, step)]


def _read(t, mid, level=10, exp=1000, hp=500, hp_max=500, mp=100, mp_max=100, pct=None) -> HudSample:
    return HudSample(float(t), mid, level, exp, pct, hp, hp_max, mp, mp_max)


# ---------------------------------------------------------------- matching kills

@needs_kb
def test_an_exp_line_is_the_monster_with_exactly_that_exp_on_the_map(kb, rocky):
    axe, dark = _mob(kb, "Axe Stump"), _mob(kb, "Dark Axe Stump")
    m = grindlive.Matcher(kb)
    assert m.monster(rocky, axe["exp"]) == axe["key"]
    assert m.monster("map/" + rocky, dark["exp"]) == dark["key"]          # a KB map key works too
    on = _on_maps(kb)
    elsewhere = next(mid for mid in sorted(on) if "Axe Stump" not in on[mid])
    assert m.monster(elsewhere, axe["exp"]) == ""                          # no Axe Stump spawns there
    assert m.monster("", axe["exp"]) == "" and m.monster(rocky, 0) == ""
    assert m.exact == 2


@needs_kb
def test_a_tie_goes_to_the_monster_that_spawns_most(kb, monkeypatch):
    """Jr. Boogie 1 and 2 give the same EXP: on a map with more of one, it is that one; where both spawn alike,
    always the same one (by name)."""
    b1, b2 = _mob(kb, "Jr. Boogie 1"), _mob(kb, "Jr. Boogie 2")
    assert b1["exp"] == b2["exp"]
    both = _map_with(kb, "Jr. Boogie 1", "Jr. Boogie 2")
    assert grindlive.Matcher(kb).monster(both, b1["exp"]) == b1["key"]
    real = gamelookup.map_monsters
    monkeypatch.setattr(gamelookup, "map_monsters", lambda k, mid: [(b1["key"], b1["monster"], 21, 2),
                                                                     (b2["key"], b2["monster"], 21, 7)]
                        if mid == "999000001" else real(k, mid))
    assert grindlive.Matcher(kb).monster("999000001", b1["exp"]) == b2["key"]


@needs_kb
def test_a_bonus_ratio_is_learned_after_five_exact_matches(kb, rocky):
    """A 20% bonus on three monsters (25, 38, 52: no monster's own EXP): once five lines matched exactly, three lines
    that agree on one ratio from different monsters teach it, and lines that fit it are those monsters' kills."""
    ds, ax, dax = (_mob(kb, n) for n in ("Dark Stump", "Axe Stump", "Dark Axe Stump"))
    bonus = [round(r["exp"] * 1.2) for r in (ds, ax, dax)]
    early = grindlive.Matcher(kb)
    assert early.monster(rocky, ds["exp"]) and early.monster(rocky, ax["exp"])
    assert [early.monster(rocky, v) for v in bonus * 3] == [""] * 9       # two exact matches: nothing learned
    m = grindlive.Matcher(kb)
    for r in (ds, ax, dax, ds, ax):
        assert m.monster(rocky, r["exp"]) == r["key"]
    assert [m.monster(rocky, v) for v in bonus] == ["", "", dax["key"]]
    assert m.ratio == pytest.approx(1.2, abs=0.02)
    assert [m.monster(rocky, v) for v in bonus] == [ds["key"], ax["key"], dax["key"]]


@needs_kb
def test_an_exp_line_that_matches_no_monster_is_no_kill(kb, rocky):
    """The live check's 18, 30 and 1 match no monster there; one value seen again and again teaches no ratio (it would
    fit one to every monster)."""
    m = grindlive.Matcher(kb)
    for name in ("Dark Stump", "Axe Stump", "Snail", "Red Snail", "Dark Axe Stump", "Dark Stump"):
        assert m.monster(rocky, _mob(kb, name)["exp"])
    assert [m.monster(rocky, v) for v in (18, 30, 1, 18, 18, 18)] == [""] * 6
    assert m.ratio is None


@needs_kb
def test_a_live_session_counts_its_stump_lines_as_kills(kb, rocky):
    """The 5 minutes of live reads (test_lootlog's) on a map whose spawns hold those monsters: each line with a
    monster's exact EXP is its kill (Axe Stump 32, Dark Stump 21, Dark Axe Stump 43, Red Snail 8, Snail 2), the 18s,
    30 and 1 are EXP but no kill. Tagged as the scanner does, or matched afterwards in a run that has no tags."""
    raw = json.loads((FIX / "loot_reads_live.json").read_text(encoding="utf-8"))
    tr = lootlog.Tracker(lootlog.item_names(kb))
    lg = lootlog.Log(start=0.0)
    for t in sorted(raw, key=float):
        lg.add(tr.read([tuple(r) for r in raw[t]], float(t)))
    for e in lg.events:
        e.map = rocky
    lines = [e.amount for e in lg.events if e.kind == "exp"]
    assert (len(lines), sum(lines)) == (20, 358)
    untagged = grindlive.live(kb, lg, None, [], now=300.0)
    want = {"Dark Stump": 5, "Snail": 5, "Axe Stump": 2, "Dark Axe Stump": 2, "Red Snail": 1}
    assert {k.name: k.count for k in untagged.kills} == want
    assert [k.name for k in untagged.kills][:2] == ["Dark Stump", "Snail"]          # most first
    m = grindlive.Matcher(kb)
    for e in lg.events:
        if e.kind == "exp":
            e.monster = m.monster(e.map, e.amount)
    tagged = grindlive.live(kb, lg, None, [], now=300.0)
    assert tagged.kills == untagged.kills
    assert tagged.session.kills_h == round(15 * 3600 / tagged.session.active_s)
    assert tagged.map_name == "Rocky Road II" and tagged.state == "running"
    assert tagged.last_drop[:2] == ("Red Snail Shell", RED_SNAIL_SHELL)


# ---------------------------------------------------------------- rates and state

@needs_kb
def test_rates_count_active_time_only(kb, rocky):
    """Ten minutes of kills, ten idle, ten more: each gap counts up to IDLE_S; the recent rates are the last five
    minutes of active time."""
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 600, 10, 30, rocky) + _exp(1200, 1800, 10, 30, rocky))
    lv = grindlive.live(kb, lg, None, [], now=1800.0)
    assert lv.session.active_s == pytest.approx(600 + grindlive.IDLE_S + 600)
    assert lv.session.exp_h == round(122 * 30 * 3600 / 1320) and lv.wall_s == 1800
    assert lv.recent.active_s == grindlive.RECENT_S and lv.recent.exp_h == round(30 * 30 * 3600 / 300)
    assert lv.state == "running" and lv.running
    assert grindlive.live(kb, lg, None, [], now=1800.0 + grindlive.IDLE_S + 1).state == "paused"
    assert grindlive.live(kb, lg, None, [], now=59.0).session == Rates(active_s=59.0)   # under a minute: no rates


@needs_kb
def test_a_manual_pause_is_not_counted(kb, rocky):
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 600, 10, 30, rocky) + _exp(900, 1500, 10, 30, rocky))
    lg.pause(600.0)
    lg.resume(900.0)
    assert grindlive.live(kb, lg, None, [], now=1500.0).session.active_s == pytest.approx(1200)
    lg.pause(1500.0)
    lv = grindlive.live(kb, lg, None, [], now=1560.0)
    assert lv.state == "paused" and lv.session.active_s == pytest.approx(1200)
    lg.ended = 1600.0
    lv = grindlive.live(kb, lg, None, [], now=5000.0)
    assert (lv.state, lv.running, lv.wall_s, lv.session.exp_h) == ("stopped", False, 1600.0, round(122 * 30 * 3600 / 1200))


@needs_kb
def test_a_long_runs_rates_are_over_the_pickups_its_log_still_holds(kb, rocky, monkeypatch):
    """A log keeps its newest MAX_EVENTS pickups: its rates and active time are those of the kept ones, though the HUD
    reads go further back; its totals are all of it."""
    monkeypatch.setattr(lootlog, "MAX_EVENTS", 100)
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 1990, 10, 30, rocky))                    # 200 lines: the first 100 let go
    for t in range(0, 1992, 2):
        lg.add_sample(_read(t, rocky, exp=1000 + t))
    assert (len(lg.events), lg.base["exp"]) == (100, 3000)
    lv = grindlive.live(kb, lg, None, [], now=1990.0)
    assert lv.session.active_s == pytest.approx(990)
    assert lv.session.exp_h == round(100 * 30 * 3600 / 990)
    assert grindlive.summary(kb, lg, None).exp == 6000


@needs_kb
def test_no_run_is_stopped_with_zeros(kb):
    c = Character("c1", "Kiwi", "Warrior", "Fighter", 30, exp_pct=40.0)
    lv = grindlive.live(kb, None, c, [Goal("level", 31), Goal("mesos", 100)])
    assert (lv.running, lv.state, lv.session, lv.recent, lv.kills, lv.deaths, lv.potions) == (
        False, "stopped", Rates(), Rates(), [], 0, 0)
    assert (lv.level, lv.exp_pct, lv.last_drop, lv.capacity_h, lv.move_on) == (30, 40.0, None, None, None)
    assert [(g.have, g.done, g.eta_s) for g in lv.goals] == [(30, False, None), (0, False, None)]
    assert grindlive.alerts(kb, None, c, [], [], 0.3, 0.0) == []


# ---------------------------------------------------------------- the HUD reads

@needs_kb
def test_deaths_level_ups_and_potions_from_the_hud_reads(kb, rocky):
    """A hit then +100 HP (a Red Potion); the EXP down at the same level, twice (a death) and the revive (no potion);
    a level-up (a new max HP: no potion); MP refilled by 200 (a Blue Potion)."""
    lg = lootlog.Log(start=0.0)
    for s in (_read(0, rocky), _read(2, rocky, exp=1100, hp=300), _read(4, rocky, exp=1100, hp=400),
              _read(6, rocky, exp=1150, hp=400), _read(8, rocky, exp=990, hp=0), _read(10, rocky, exp=990, hp=0),
              _read(12, rocky, exp=990, hp=250), _read(30, rocky, exp=1500, hp=250),
              _read(32, rocky, level=11, exp=5, hp=600, hp_max=600), _read(34, rocky, level=11, exp=20, hp=600,
                                                                          hp_max=600, mp=100, mp_max=300),
              _read(36, rocky, level=11, exp=20, hp=600, hp_max=600, mp=300, mp_max=300),
              _read(38, rocky, level=11, exp=40, hp=600, hp_max=600, mp=300, mp_max=300)):
        lg.add_sample(s)
    buy = {r["item"]: r["buy"] for r in tables.rows(kb, "consumables")}
    lv = grindlive.live(kb, lg, None, [], now=40.0)
    assert (lv.deaths, lv.level_ups, lv.level) == (1, [(32.0, 11)], 11)
    assert (lv.potions, lv.potion_cost) == (2, buy["Red Potion"] + buy["Blue Potion"])
    assert grindlive.live(kb, lg, None, [], now=15.0).state == "dead"
    sm = grindlive.summary(kb, lg, None)
    assert (sm.deaths, sm.potion_cost, sm.levels) == (1, buy["Red Potion"] + buy["Blue Potion"], (10, 11))


@needs_kb
def test_one_misread_is_no_death_and_no_level_up(kb, rocky):
    lg = lootlog.Log(start=0.0)
    for s in (_read(0, rocky, exp=1000), _read(2, rocky, exp=100), _read(4, rocky, exp=1010),     # a digit slipped
              _read(6, rocky, level=11, exp=1020), _read(8, rocky, exp=1030), _read(10, rocky, exp=1040)):
        lg.add_sample(s)
    lv = grindlive.live(kb, lg, None, [], now=12.0)
    assert (lv.deaths, lv.level_ups, lv.level) == (0, [], 10)


@needs_kb
@pytest.mark.parametrize("exp,pct", [(716, None), (None, 50.0)])
def test_time_to_level_at_the_recent_rate(kb, rocky, exp, pct):
    """50 EXP every 10 s: 18,000 an hour over the last five minutes; the EXP left from the HUD's points (or %)."""
    need = plan.exp_table(kb)[10]
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 600, 10, 50, rocky))
    lg.add_sample(_read(600, rocky, exp=exp, pct=pct))
    lv = grindlive.live(kb, lg, None, [], now=600.0)
    left = need - exp if exp is not None else need * (1 - pct / 100)
    assert lv.recent.exp_h == 18000
    assert lv.to_level_s == pytest.approx(left / 18000 * 3600)
    assert lv.exp_pct == pytest.approx(pct if pct is not None else exp * 100 / need, abs=0.01)


# ---------------------------------------------------------------- the map

@needs_kb
def test_capacity_from_the_maps_spawn_rows(kb, rocky):
    """Each spawns row's count x mob rate (1 when none) every respawn seconds, summed; the share is this map's kills
    an hour of it."""
    rows = [r for r in tables.rows(kb, "spawns") if r["map_key"] == f"map/{rocky}" and r["respawn"]]
    want = round(sum(r["count"] * (r["mob_rate"] or 1) * 3600 / r["respawn"] for r in rows))
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 600, 3, 21, rocky, _mob(kb, "Dark Stump")["key"]))
    lv = grindlive.live(kb, lg, None, [], now=600.0)
    assert lv.capacity_h == want
    assert lv.kill_share == pytest.approx(lv.session.kills_h / want)


@needs_kb
def test_warnings_from_the_players_acc_and_what_was_seen(kb, rocky):
    ds = _mob(kb, "Dark Stump")
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 660, 3, ds["exp"], rocky, ds["key"]))       # 11 minutes here, far under the spawns' capacity
    for t, hp in ((600, 100), (602, 120), (604, 130), (606, 400)):
        lg.add_sample(_read(t, rocky, level=20, exp=1000 + t, hp=hp))
    keys = {k for k, *_ in gamelookup.map_monsters(kb, rocky)}
    needs = {r["monster"]: combat.acc_needed(20, r["level"], r["avoid"] or 0)
             for r in tables.rows(kb, "monsters") if r["key"] in keys}
    top = max(needs.values())
    c = Character("c1", "Kiwi", "Warrior", "Fighter", 20, stats={"acc": top - 1})
    lv = grindlive.live(kb, lg, c, [], now=660.0)
    warn = dict(lv.warnings)
    assert warn["gl_warn_acc"]["need"] == top and needs[warn["gl_warn_acc"]["name"]] == top
    assert warn["gl_warn_acc"]["acc"] == top - 1
    assert warn["gl_warn_low_hp"] == {"pct": 30} and "gl_warn_died" not in warn
    assert warn["gl_warn_share"] == {"pct": round(lv.kill_share * 100), "cap": f"{lv.capacity_h:,}"}
    c.stats = {"acc": top}
    assert "gl_warn_acc" not in dict(grindlive.live(kb, lg, c, [], now=660.0).warnings)
    # a death on this map: it hits hard (said once, not with the low HP)
    for s in (_read(640, rocky, level=20, exp=500, hp=0), _read(642, rocky, level=20, exp=500, hp=0)):
        lg.add_sample(s)
    warn = dict(grindlive.live(kb, lg, None, [], now=660.0).warnings)
    assert warn["gl_warn_died"] == {"n": 1} and "gl_warn_low_hp" not in warn and "gl_warn_acc" not in warn
    # ... and not once the player is on another map
    other = _map_with(kb, "Slime")
    lg.add(_exp(670, 700, 3, 10, other))
    assert "gl_warn_died" not in dict(grindlive.live(kb, lg, None, [], now=700.0).warnings)


# ---------------------------------------------------------------- goals and alerts

@needs_kb
def test_goals_progress_and_time_left(kb, rocky):
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 600, 10, 50, rocky))                                                      # 18,000 EXP an hour
    lg.add([Event(float(t), "mesos", 100, map=rocky) for t in range(5, 600, 20)])            # 3,000; 18,000 an hour
    lg.add([Event(float(t), "item", 1, "Leaf", LEAF, map=rocky) for t in range(15, 600, 60)])   # 10; 60 an hour
    lg.add_sample(_read(600, rocky, exp=716))
    table = plan.exp_table(kb)
    goals = [Goal("level", 12), Goal("item", 20, LEAF, "Leaf"), Goal("mesos", 12000), Goal("level", 10)]
    got = grindlive.live(kb, lg, None, goals, now=600.0).goals
    assert [(g.goal, g.have, g.done) for g in got] == [(goals[0], 10, False), (goals[1], 10, False),
                                                       (goals[2], 3000, False), (goals[3], 10, True)]
    assert got[0].eta_s == pytest.approx((table[10] - 716 + table[11]) / 18000 * 3600)
    assert got[1].eta_s == pytest.approx(10 / 60 * 3600)
    assert got[2].eta_s == pytest.approx(9000 / 18000 * 3600)
    assert got[3].eta_s == 0


def test_goals_round_trip_through_settings():
    goals = [Goal("level", 35), Goal("item", 100, LEAF, "Leaf"), Goal("mesos", 1_000_000)]
    assert [Goal.from_json(json.loads(json.dumps(g.to_json()))) for g in goals] == goals
    assert Goal("level", 35).to_json() == {"kind": "level", "target": 35}
    for bad in ({"kind": "exp", "target": 3}, {"kind": "level", "target": 0}, {"kind": "level", "target": True},
                {"kind": "item", "target": 5}, {"kind": "mesos", "target": "100"}, None, []):
        assert Goal.from_json(bad) is None


@needs_kb
def test_alerts_after_since(kb, rocky):
    """Everything after `since`, oldest first, each at its time: a tracked item, goals reached, low HP (once a minute
    at most, by the reads' times), a level-up, a death, and the run pausing itself after IDLE_S without EXP."""
    lg = lootlog.Log(start=0.0)
    lg.add([Event(5.0, "item", 1, "Leaf", LEAF, map=rocky), Event(50.0, "mesos", 500, map=rocky)])
    lg.add(_exp(100, 200, 5, 10, rocky))
    lg.add([Event(110.0, "item", 1, "Leaf", LEAF, map=rocky), Event(112.0, "item", 1, "Firewood", FIREWOOD, map=rocky),
            Event(120.0, "mesos", 600, map=rocky)])
    for s in (_read(100, rocky, exp=1600), _read(130, rocky, exp=1650, hp=100), _read(140, rocky, exp=1700, hp=120),
              _read(150, rocky, level=11, exp=10, hp=550, hp_max=550), _read(152, rocky, level=11, exp=30, hp=550, hp_max=550),
              _read(170, rocky, level=11, exp=5, hp=0, hp_max=550), _read(172, rocky, level=11, exp=5, hp=0, hp_max=550),
              _read(195, rocky, level=11, exp=40, hp=100, hp_max=550)):
        lg.add_sample(s)
    goals = [Goal("item", 2, LEAF, "Leaf"), Goal("mesos", 1000), Goal("level", 11), Goal("level", 30)]
    got = grindlive.alerts(kb, lg, None, goals, [LEAF], 0.3, since=100.0, now=400.0)
    assert [(a.kind, a.key, a.params, a.item_key, a.t) for a in got] == [
        ("wishlist", "gl_alert_wishlist", {"name": "Leaf"}, LEAF, 110.0),
        ("goal", "gl_alert_goal_item", {"n": "2", "name": "Leaf"}, LEAF, 110.0),
        ("goal", "gl_alert_goal_mesos", {"amount": "1,000"}, "", 120.0),
        ("low_hp", "gl_alert_low_hp", {"pct": 20}, "", 130.0),
        ("goal", "gl_alert_goal_level", {"level": 11}, "", 150.0),
        ("level", "gl_alert_level", {"level": 11}, "", 150.0),
        ("death", "gl_alert_death", {}, "", 170.0),
        ("low_hp", "gl_alert_low_hp", {"pct": 18}, "", 195.0),
        ("paused", "gl_alert_paused", {"n": 2}, "", 320.0)]
    # the low HP at 140 stays quiet whatever `since` (the one at 130 was said), the one at 195 is a minute later
    assert [a.params["pct"] for a in grindlive.alerts(kb, lg, None, [], [], 0.3, since=135.0, now=400.0)
            if a.kind == "low_hp"] == [18]
    assert not [a for a in grindlive.alerts(kb, lg, None, [], [], 0, since=0.0, now=400.0) if a.kind == "low_hp"]
    assert [a.kind for a in grindlive.alerts(kb, lg, None, goals, [LEAF], 0.3, since=200.0, now=300.0)] == []

    # a level-up (read at 150) and a death (at 170) count once the next read (152, 172) confirms them: they come while
    # that read is after `since`, at their own read's time, so a `since` that is already that read's time misses none
    def confirmed(since: float) -> list:
        return [(a.kind, a.t) for a in grindlive.alerts(kb, lg, None, goals, [], 0, since=since, now=400.0)
                if a.kind in ("goal", "level", "death")]

    assert confirmed(150.0) == [("goal", 150.0), ("level", 150.0), ("death", 170.0)]
    assert confirmed(152.0) == confirmed(170.0) == [("death", 170.0)]
    assert confirmed(172.0) == []


# ---------------------------------------------------------------- the loot database

def _logged(kb, start: float, end: float, events: list, cid: str = "c1") -> int:
    lid = lootdb.open_log(cid, "Kiwi", start)
    lootdb.add_events(lid, events, kb)
    lootdb.end_log(lid, end)
    return lid


@needs_kb
def test_drop_rates_count_the_droppers_kills_where_it_drops(kb, rocky, isolated_store):
    """Leaf: 4 picked up where Dark Stumps spawn, 40 Dark Stump kills: 1 in 10 (a Leaf on a map with no Dark Stump
    isn't counted, nor are the other monsters' kills). Firewood: Axe Stump and Dark Axe Stump drop it."""
    ds, ax, dax, rs = (_mob(kb, n)["key"] for n in ("Dark Stump", "Axe Stump", "Dark Axe Stump", "Red Snail"))
    on = _on_maps(kb)
    no_stumps = next(m for m in sorted(on) if "Dark Stump" not in on[m])
    evs = [Event(float(i), "exp", 21, map=rocky, monster=ds) for i in range(40)]
    evs += [Event(100.0 + i, "exp", 32, map=rocky, monster=ax) for i in range(20)]
    evs += [Event(200.0 + i, "exp", 43, map=rocky, monster=dax) for i in range(10)]
    evs += [Event(250.0, "exp", 8, map=rocky, monster=rs)]
    evs += [Event(300.0 + i, "item", 1, "Leaf", LEAF, map=rocky) for i in range(4)]
    evs += [Event(310.0 + i, "item", 1, "Firewood", FIREWOOD, map=rocky) for i in range(3)]
    evs += [Event(320.0 + i, "item", 1, "Red Snail Shell", RED_SNAIL_SHELL, map=rocky) for i in range(2)]
    evs += [Event(330.0, "item", 1, "Leaf", LEAF, map=no_stumps), Event(331.0, "item", 1, "Leaf", LEAF)]
    _logged(kb, 0.0, 400.0, evs)
    got = grindlive.drop_rates(kb, "c1")
    assert [d.item_key for d in got] == [LEAF, FIREWOOD, RED_SNAIL_SHELL]          # the most picked up first
    rates = {d.item_key: d for d in got}
    assert (rates[LEAF].item, rates[LEAF].count, rates[LEAF].kills, rates[LEAF].one_in, rates[LEAF].monsters) == (
        "Leaf", 4, 40, 10, [ds])
    assert (rates[FIREWOOD].count, rates[FIREWOOD].kills, rates[FIREWOOD].one_in, rates[FIREWOOD].monsters) == (
        3, 30, 10, [ax, dax])
    assert (rates[RED_SNAIL_SHELL].kills, rates[RED_SNAIL_SHELL].one_in) == (1, None)   # fewer kills than drops
    assert grindlive.drop_rates(kb, "someone else") == []
    # the running log's last drop: its rate from every run, this one's newest pickups from memory
    lg = lootlog.Log(start=1000.0)
    lg.add(_exp(1000, 1019, 1, 21, rocky, ds) + [Event(1020.0, "item", 1, "Leaf", LEAF, map=rocky)])
    c = Character("c1", "Kiwi", "Warrior", "Fighter", 20)
    assert grindlive.live(kb, lg, c, [], now=1030.0).last_drop == ("Leaf", LEAF, 12)    # 60 kills, 5 Leaves


@needs_kb
def test_best_spots_rank_maps_by_exp_an_hour_near_the_level(kb, rocky, isolated_store):
    on = _on_maps(kb)
    a = rocky
    b, c, d = [m for m in sorted(on) if m != rocky][:3]

    def run(start: float, mid: str, amount: int, level: int | None, minutes: int) -> None:
        n = minutes * 12                         # a line every 5 s: amount x 720 an hour
        _logged(kb, start, start + n * 5, [Event(start + i * 5, "exp", amount, map=mid, level=level) for i in range(n)])

    run(0, a, 20, 20, 15)
    run(10_000, b, 30, 21, 12)
    run(20_000, c, 50, 40, 15)                   # far above level 20
    run(30_000, d, 90, 20, 5)                    # five minutes: too short to tell
    run(40_000, a, 20, None, 15)                 # level unknown: counts
    spots = grindlive.best_spots(kb, "c1", 20)
    assert [(s.map_id, s.exp_h, s.sessions) for s in spots] == [(b, 21600, 1), (a, 14400, 2)]
    assert spots[1].active_s == pytest.approx(1800) and spots[1].map_name == "Rocky Road II"
    assert [s.map_id for s in grindlive.best_spots(kb, "c1", None)] == [c, b, a]


@needs_kb
@pytest.mark.parametrize("amount,moves", [(30, True), (24, False)])
def test_move_on_when_another_map_paid_a_quarter_more(kb, rocky, isolated_store, amount, moves):
    """11 minutes here at 14,400 EXP an hour; another map gave amount x 720 an hour at this level."""
    there = next(m for m in sorted(_on_maps(kb)) if m != rocky)
    _logged(kb, 0.0, 900.0, [Event(i * 5.0, "exp", amount, map=there, level=20) for i in range(180)])
    lg = lootlog.Log(start=10_000.0)
    lg.add([Event(10_000.0 + i * 5, "exp", 20, map=rocky, level=20) for i in range(133)])
    c = Character("c1", "Kiwi", "Warrior", "Fighter", 20)
    lv = grindlive.live(kb, lg, c, [], now=10_660.0)
    assert lv.recent.exp_h == 14400
    assert (lv.move_on is not None) == moves
    if moves:
        assert (lv.move_on.map_id, lv.move_on.exp_h) == (there, amount * 720)
    assert grindlive.live(kb, lg, c, [], now=10_500.0).move_on is None      # under 10 minutes here: too soon


@needs_kb
def test_history_lists_finished_runs_and_summary_the_running_one(kb, rocky, isolated_store):
    ds = _mob(kb, "Dark Stump")
    evs = [Event(i * 5.0, "exp", 21, map=rocky, monster=ds["key"], level=20 if i < 110 else 21) for i in range(120)]
    evs += [Event(3.0, "mesos", 50, map=rocky, level=20), Event(4.0, "item", 2, "Leaf", LEAF, map=rocky, level=20)]
    lid = _logged(kb, 0.0, 600.0, evs)
    running = lootdb.open_log("c1", "Kiwi", 1000.0)
    lootdb.add_events(running, [Event(1001.0, "exp", 5, map=rocky)], kb)
    hist = grindlive.history(kb, "c1")
    assert [h.log_id for h in hist] == [lid]
    h = hist[0]
    price = farm.value(kb, LEAF).price
    assert (h.start, h.end, h.exp, h.mesos, h.kills, h.levels, h.deaths) == (0.0, 600.0, 2520, 50, 120, (20, 21), 0)
    assert (h.active_s, h.maps, h.top_drops) == (600.0, [(rocky, "Rocky Road II", 600.0)], [(LEAF, "Leaf", 2)])
    assert (h.loot, h.profit, h.exp_h) == (2 * price, 50 + 2 * price, 15120)
    assert grindlive.history(kb, "c1", limit=0) == []
    lg = lootlog.Log(start=0.0, ended=600.0, db_id=lid)
    lg.add(evs)
    sm = grindlive.summary(kb, lg, None)
    assert (sm.log_id, sm.exp, sm.kills, sm.levels, sm.loot, sm.top_drops) == (lid, 2520, 120, (20, 21), 2 * price,
                                                                               [(LEAF, "Leaf", 2)])
    assert sm.maps == [(rocky, "Rocky Road II", 600.0)] and sm.exp_h == 15120
