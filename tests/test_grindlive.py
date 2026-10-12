"""The live grind numbers (grindlive.py): rates over active time, deaths, level-ups and potions from the HUD reads,
time to level, warnings, alerts, goals, the last drop's rate this run, and from the loot database the player's own
drop rates (per active hour on the maps where they were picked up), best spots and past runs. No kills anywhere: a
pickup message never says which monster gave it."""
import dataclasses
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


def _exp(t0: int, t1: int, step: int, amount: int, mid: str, level: int | None = None) -> list:
    return [Event(float(t), "exp", amount, map=mid, level=level) for t in range(t0, t1 + 1, step)]


def _read(t, mid, level=10, exp=1000, hp=500, hp_max=500, mp=100, mp_max=100, pct=None) -> HudSample:
    return HudSample(float(t), mid, level, exp, pct, hp, hp_max, mp, mp_max)


def _spawning(kb, mid: str) -> set[str]:
    """The keys of the monsters that spawn on a map."""
    return {k for k, *_ in gamelookup.map_monsters(kb, mid)}


# ---------------------------------------------------------------- a live replay

@needs_kb
def test_a_live_session_replayed_gives_its_exp_mesos_and_last_drop_per_active_hour(kb, rocky):
    """The 5 minutes of live reads (test_lootlog's) on Rocky Road II: every EXP line counts (20 lines, 358 EXP), the
    rates are the totals over the active time, and the last drop's rate is its count this run per active hour."""
    raw = json.loads((FIX / "loot_reads_live.json").read_text(encoding="utf-8"))
    tr = lootlog.Tracker(lootlog.item_names(kb))
    lg = lootlog.Log(start=0.0)
    for t in sorted(raw, key=float):
        lg.add(tr.read([tuple(r) for r in raw[t]], float(t)))
    for e in lg.events:
        e.map = rocky
    lines = [e.amount for e in lg.events if e.kind == "exp"]
    assert (len(lines), sum(lines)) == (20, 358)
    mesos = sum(e.amount for e in lg.events if e.kind == "mesos")
    shells = sum(e.amount for e in lg.events if e.key == RED_SNAIL_SHELL)
    assert mesos > 0 and shells > 0
    lv = grindlive.live(kb, lg, None, [], now=300.0)
    active = lv.session.active_s
    assert grindlive.MIN_RATE_S <= active <= 300
    assert lv.session.exp_h == round(358 * 3600 / active) and lv.session.mesos_h == round(mesos * 3600 / active)
    assert lv.map_name == "Rocky Road II" and lv.state == "running"
    assert lv.last_drop == ("Red Snail Shell", RED_SNAIL_SHELL, pytest.approx(shells * 3600 / active))
    assert grindlive.summary(kb, lg, None).exp == 358


@needs_kb
def test_the_last_drop_is_its_count_this_run_per_active_hour(kb, rocky):
    """Leaves, 1 then 2 at a time, and a Firewood between: the last drop is the Leaf, 4 of them over 10 minutes of
    active time (24 an hour); a pickup with no KB item counts by its name; under a minute of active time, no rate."""
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 600, 10, 30, rocky))
    lg.add([Event(100.0, "item", 1, "Leaf", LEAF, map=rocky), Event(200.0, "item", 1, "Firewood", FIREWOOD, map=rocky),
            Event(300.0, "item", 1, "Leaf", LEAF, map=rocky), Event(400.0, "item", 2, "Leaf", LEAF, map=rocky)])
    lv = grindlive.live(kb, lg, None, [], now=600.0)
    assert lv.session.active_s == pytest.approx(600)
    assert lv.last_drop == ("Leaf", LEAF, pytest.approx(4 * 3600 / 600))
    lg.add([Event(500.0, "item", 1, "Glowing Pebble", ""), Event(550.0, "item", 1, "Glowing Pebble", "")])
    assert grindlive.live(kb, lg, None, [], now=600.0).last_drop == ("Glowing Pebble", "", pytest.approx(2 * 3600 / 600))
    early = lootlog.Log(start=0.0)
    early.add(_exp(0, 50, 10, 30, rocky) + [Event(40.0, "item", 1, "Leaf", LEAF, map=rocky)])
    assert grindlive.live(kb, early, None, [], now=50.0).last_drop == ("Leaf", LEAF, None)


def test_live_carries_no_kill_fields():
    """A Live, a Rates, a Spot and a Summary are made of the contract's fields alone: nothing counts kills."""
    rates = Rates(exp_h=18_000, mesos_h=9_000, loot_h=6_000, potions_h=1_000, profit_h=14_000, active_s=600.0)
    spot = grindlive.Spot(map_id="104040000", map_name="Henesys Hunting Ground I", active_s=900.0, exp_h=20_000,
                          profit_h=12_000, sessions=2)
    lv = grindlive.Live(running=True, state="running", map_id="104040000", map_name="Henesys Hunting Ground I",
                        wall_s=700.0, session=rates, recent=rates, level=20, exp_pct=12.5, to_level_s=1800.0,
                        last_drop=("Leaf", LEAF, 24.0), warnings=[], deaths=0, potions=3, potion_cost=150,
                        level_ups=[], goals=[], move_on=spot)
    sm = grindlive.Summary(log_id=1, start=0.0, end=700.0, active_s=600.0, exp=3000, mesos=1500, loot=1000,
                           potion_cost=150, profit=2350, levels=(20, 20), deaths=0, maps=[], top_drops=[],
                           exp_h=18_000, profit_h=14_100)
    fields = {c: {f.name for f in dataclasses.fields(c)} for c in (grindlive.Live, Rates, grindlive.Spot,
                                                                     grindlive.Summary, grindlive.DropRate)}
    for names in fields.values():
        assert not {n for n in names if "kill" in n or n in ("capacity_h", "one_in")}
    assert (lv.last_drop[2], lv.move_on.exp_h, sm.exp_h) == (24.0, 20_000, 18_000)
    assert not hasattr(grindlive, "Matcher") and not hasattr(grindlive, "Kill")


# ---------------------------------------------------------------- rates and state

@needs_kb
def test_rates_count_active_time_only(kb, rocky):
    """Ten minutes of EXP lines, ten idle, ten more: each gap counts up to IDLE_S; the recent rates are the last five
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
    assert (lv.running, lv.state, lv.session, lv.recent, lv.deaths, lv.potions) == (
        False, "stopped", Rates(), Rates(), 0, 0)
    assert (lv.level, lv.exp_pct, lv.last_drop, lv.move_on) == (30, 40.0, None, None)
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
def test_warnings_from_the_players_acc_and_what_was_seen(kb, rocky):
    """Only what is seen or known is warned of: the ACC the player typed, a death or low HP here; never a share of
    the map's spawns (kills can't be counted)."""
    ds = _mob(kb, "Dark Stump")
    lg = lootlog.Log(start=0.0)
    lg.add(_exp(0, 660, 3, ds["exp"], rocky))                    # 11 minutes here
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
    assert warn["gl_warn_low_hp"] == {"pct": 30} and set(warn) == {"gl_warn_acc", "gl_warn_low_hp"}
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
def test_drop_rates_are_per_active_hour_on_the_maps_where_it_was_picked_up(kb, rocky, isolated_store):
    """Three runs: 15 minutes on Rocky Road II, 10 on a map where nothing that drops a Leaf spawns, 5 on a third.
    Leaf: 4 on the first (one pickup of 2) and 2 on the second, 6 over their 25 minutes: 14.4 an hour, from the Dark
    Stumps of the first (a Leaf with no map isn't counted). Firewood: 3 over 15 minutes, from the droppers spawning
    there, the most spawned first. Red Snail Shell: 5 minutes of active time on its map is too few for a rate."""
    ds, ax, dax = (_mob(kb, n)["key"] for n in ("Dark Stump", "Axe Stump", "Dark Axe Stump"))
    on = _on_maps(kb)
    no_leaf = next(m for m in sorted(on) if m != rocky and not _spawning(kb, m) & set(kb.droppers[LEAF]))
    third = next(m for m in sorted(on) if m not in (rocky, no_leaf))

    def run(start: float, mid: str, minutes: int, items: list) -> None:
        n = minutes * 12                         # an EXP line every 5 s: `minutes` of active time
        _logged(kb, start, start + n * 5, [Event(start + i * 5, "exp", 20, map=mid) for i in range(n)] + items)

    run(0.0, rocky, 15, [Event(10.0, "item", 1, "Leaf", LEAF, map=rocky), Event(20.0, "item", 1, "Leaf", LEAF, map=rocky),
                         Event(30.0, "item", 2, "Leaf", LEAF, map=rocky), Event(40.0, "item", 1, "Leaf", LEAF)]
        + [Event(50.0 + i, "item", 1, "Firewood", FIREWOOD, map=rocky) for i in range(3)])
    run(10_000.0, no_leaf, 10, [Event(10_010.0 + i, "item", 1, "Leaf", LEAF, map=no_leaf) for i in range(2)])
    run(20_000.0, third, 5, [Event(20_010.0 + i, "item", 1, "Red Snail Shell", RED_SNAIL_SHELL, map=third)
                             for i in range(2)])
    got = grindlive.drop_rates(kb, "c1")
    assert [d.item_key for d in got] == [LEAF, FIREWOOD, RED_SNAIL_SHELL]          # the most picked up first
    leaf, wood, shell = got
    assert (leaf.item, leaf.count, leaf.active_s, leaf.monsters) == ("Leaf", 6, pytest.approx(1500), [ds])
    assert leaf.per_h == pytest.approx(6 * 3600 / 1500)
    spawns = {k: n for k, _name, _level, n in gamelookup.map_monsters(kb, rocky)}
    assert (wood.count, wood.active_s, wood.per_h) == (3, pytest.approx(900), pytest.approx(12.0))
    assert set(wood.monsters) == {ax, dax} and [spawns[k] for k in wood.monsters] == sorted(
        (spawns[k] for k in wood.monsters), reverse=True)
    assert (shell.count, shell.active_s, shell.per_h) == (2, pytest.approx(300), None)
    assert set(shell.monsters) == set(kb.droppers[RED_SNAIL_SHELL]) & _spawning(kb, third)
    assert grindlive.drop_rates(kb, "someone else") == []


@needs_kb
def test_best_spots_rank_maps_by_exp_an_hour_near_the_level(kb, rocky, isolated_store):
    """The maps the player grinded on for 10 minutes at least, by EXP an hour (no kills: a Spot has none)."""
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
    assert not any(hasattr(s, "kills_h") for s in spots)


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
    evs = [Event(i * 5.0, "exp", 21, map=rocky, level=20 if i < 110 else 21) for i in range(120)]
    evs += [Event(3.0, "mesos", 50, map=rocky, level=20), Event(4.0, "item", 2, "Leaf", LEAF, map=rocky, level=20)]
    lid = _logged(kb, 0.0, 600.0, evs)
    running = lootdb.open_log("c1", "Kiwi", 1000.0)
    lootdb.add_events(running, [Event(1001.0, "exp", 5, map=rocky)], kb)
    hist = grindlive.history(kb, "c1")
    assert [h.log_id for h in hist] == [lid]
    h = hist[0]
    price = farm.value(kb, LEAF).price
    assert (h.start, h.end, h.exp, h.mesos, h.levels, h.deaths) == (0.0, 600.0, 2520, 50, (20, 21), 0)
    assert (h.active_s, h.maps, h.top_drops) == (600.0, [(rocky, "Rocky Road II", 600.0)], [(LEAF, "Leaf", 2)])
    assert (h.loot, h.profit, h.exp_h) == (2 * price, 50 + 2 * price, 15120)
    assert grindlive.history(kb, "c1", limit=0) == []
    lg = lootlog.Log(start=0.0, ended=600.0, db_id=lid)
    lg.add(evs)
    sm = grindlive.summary(kb, lg, None)
    assert (sm.log_id, sm.exp, sm.levels, sm.loot, sm.top_drops) == (lid, 2520, (20, 21), 2 * price, [(LEAF, "Leaf", 2)])
    assert sm.maps == [(rocky, "Rocky Road II", 600.0)] and sm.exp_h == 15120
