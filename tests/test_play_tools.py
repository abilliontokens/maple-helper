"""The modules behind the tool windows: combat math (checked against NiaMeowDB's own numbers), training spots, build
tables, stats read from a screenshot, the crafting pages, NPC and market prices, the guides for you."""
import re
from pathlib import Path

import pytest

from maplehelper import availability, buildplan, combat, plan

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
# The real-KB tests below run on the KB the nightly is about to publish: they check what holds whatever tonight's
# numbers are (a balance patch or a new recipe must not hold the KB back); exact parses run on frozen page copies.

# pages/crafting/efficiency__smithing.md as the real KB wrote it (Lv. 2 and the head of Lv. 3), frozen
SMITHING = """---
{}
---
68 recipes 1 profitable to grind
Lv. 2
needs 115 EXP · char Lv. 10 + ( 2 recipes )
# | Recipe / Ingredients | EXP | Catalyst | Mat value | Mat Craft Value | Sell-back | Net | EXP / meso | Mats
1 | Juno
2 x Iron Ingot 2 x Processed Leather 6 x Screw
| 40 | 1,200 | + 226 | + 600 | + 1,200 | -226 | 0.177 | Farm only
2 | Steel Helmet
1 x Bronze Helmet 2 x Iron Ingot
| 40 | 1,000 | + 900 | + 200 | + 750 | -1,150 | 0.035 | Mixed
Lv. 3
needs 199 EXP · char Lv. 15 + ( 1 recipes )
# | Recipe / Ingredients | EXP | Catalyst | Mat value | Mat Craft Value | Sell-back | Net | EXP / meso | Mats
1 | Steel Fingerless Gloves
3 x Iron Ingot 2 x Processed Leather 9 x Screw
| 60 | 1,800 | + 329 | + 700 | + 1,800 | -329 | 0.182 | Farm only
"""


def test_accuracy_to_never_miss_matches_the_site():
    # Zombie Mushroom (Lv 24, Avoid 14): the monster page lists 47 / 56 / 65 ACC at levels 24 / 19 / 14
    assert [combat.acc_needed(lv, 24, 14) for lv in (24, 19, 14)] == [47, 56, 65]
    assert combat.hit_chance(47, 24, 24, 14) == 1.0 and combat.hit_chance(30, 24, 24, 14) < 0.5


def test_base_accuracy_and_damage():
    assert combat.base_acc("Warrior", 30, dex=30, luk=4) == 49
    assert combat.acc_per_point("Warrior") == pytest.approx(0.48)
    m = combat.Monster("monster/1", "Test", level=30, hp=1000, exp=50, pdef=0)
    assert combat.hits_to_kill(100, 300, m, 30) == (10, 5.0)
    assert combat.level_scale(30, 35) < 1 and combat.level_scale(30, 25) == 1
    assert combat.landed(10**6, 0, 1, 1) == 99_999 and combat.landed(0.2, 50, 1, 1) == 1     # the game's clamp (GAM-15)


@needs_kb
def test_training_spots_are_reachable_and_ranked():
    from maplehelper.kb import KnowledgeBase
    kb = KnowledgeBase(REAL_KB)
    from maplehelper import availability
    rows = combat.spots(kb, 30, acc=73, dmg=(140, 300), n=6)
    assert rows and all(combat.grind_map(kb, s.map) for s in rows)
    assert not any("Warrior's" in s.map for s in rows)
    assert availability.of(kb).place_open("Orbis") or not any("Orbis" in s.map for s in rows)    # not out: not shown
    assert rows == sorted(rows, key=lambda s: -s.score)


@needs_kb
def test_build_tables_follow_the_level():
    from maplehelper.kb import KnowledgeBase
    kb = KnowledgeBase(REAL_KB)
    key, tables = buildplan.tables(kb, "Warrior", "Warrior", 22, "en")
    assert key == "guide/warrior-class-guide"
    kinds = [t.kind for t in tables]
    assert "ap" in kinds and "sp" in kinds
    ap = next(t for t in tables if t.kind == "ap")
    assert re.search(r"\d+-\d+", ap.heading) and ap.current is not None      # "10-30": the guide's level range
    assert buildplan.current_row([["Level"], ["10"], ["11-12"], ["20"]], 15) == 2


def test_stats_from_a_screenshot_read(tmp_path, monkeypatch):
    from maplehelper import store
    monkeypatch.setattr(store.Profiles, "path", tmp_path / "profiles.json")
    p = store.Profiles()
    p.add("Kiwi", "Warrior", "Fighter", 34)
    changed = p.apply_update({"stats": {"acc": 78, "dmg_min": 340, "dmg_max": 160, "bogus": 5, "hp": -3}})
    assert p.active.stats == {"acc": 78, "dmg_min": 160, "dmg_max": 340}      # min/max swapped back, junk dropped
    assert changed and changed[0][0] == "stats"
    assert p.apply_update({"stats": {"acc": 78}}) == []                         # nothing new


def test_crafting_page_rows_read_exactly():
    from maplehelper import crafting
    crafting._levels.cache_clear()
    lv2, lv3 = crafting._levels(SMITHING)
    juno = next(r for r in lv2.recipes if r.name == "Juno")
    assert (juno.level, juno.exp, juno.catalyst, juno.net, juno.exp_per_meso, juno.mats) == \
        (2, 40, 1200, -226, 0.177, "Farm only")
    assert juno.ingredients == [(2, "Iron Ingot"), (2, "Processed Leather"), (6, "Screw")]
    assert (lv2.level, len(lv2.recipes)) == (2, 2)
    assert (lv3.level, [r.name for r in lv3.recipes]) == (3, ["Steel Fingerless Gloves"])
    crafting._levels.cache_clear()


@needs_kb
def test_crafting_recipes_by_profession_level():
    from maplehelper import crafting
    from maplehelper.kb import KnowledgeBase
    kb = KnowledgeBase(REAL_KB)
    smithing = crafting.levels(kb, "smithing")
    total = re.search(r"(\d+) recipes", kb.page("crafting/efficiency__smithing"))
    assert sum(len(lv.recipes) for lv in smithing) == int(total.group(1))      # the page's own "68 recipes"
    assert all(crafting.levels(kb, p) for p in crafting.PROFESSIONS)


@needs_kb
def test_npc_prices_from_the_item_page():
    from maplehelper import market
    from maplehelper.kb import KnowledgeBase
    kb = KnowledgeBase(REAL_KB)
    key = kb._item_by_name["red potion"]
    red = market.npc_prices(kb, key)
    # the page's own sell-back line (the exact parse is pinned on tests/test_tables.py's frozen Red Potion page)
    back = re.search(r"NPC Sell-back(?: \(per unit\))? ([\d,]+) mesos", kb.page(key))
    assert red.sell_back == int(back.group(1).replace(",", "")) and red.shops
    assert all(isinstance(s[2], int) and s[2] > 0 for s in red.shops)
    assert red.shops == sorted(red.shops, key=lambda s: s[2])


def test_free_market_summary_keeps_the_exact_item():
    from maplehelper import market
    rows = [{"itemName": "Work Gloves", "priceEach": 1000, "createdAt": "2026-10-21T10:00:00Z"},
            {"itemName": "Work Gloves", "priceEach": 3000},
            {"itemName": "Work Gloves (Blue)", "priceEach": 5}]
    m = market.summarize(rows, "Work Gloves")
    assert (m.count, m.median, m.low, m.high) == (2, 2000, 1000, 3000) and m.latest
    assert market.summarize([], "Work Gloves").count == 0


def test_an_odd_market_answer_still_parses():
    """int() on what the site sent ("n/a", a list) raised in the lookup thread, and the price card never got an
    answer (audit SEC-7)."""
    from maplehelper import market
    m = market.parse_item_market({"priceChecks": "n/a", "forSale": [1], "windowDays": None, "usual": True,
                                  "finishedTrades": 3},
                                 {"points": [{"day": "2026-10-01", "median": 10, "count": "x"}]},
                                 {"listings": [{"priceEach": 5, "quantity": "lots"}], "summary": {"activeCount": {}}})
    assert (m.checks, m.trades, m.for_sale, m.window, m.usual) == (0, 3, 0, 14, None)
    assert m.listings[0].quantity == 1 and m.volume == 0


def test_damage_range_typed_by_hand():
    assert combat.damage_range(200, 10) == (10, 200)          # min above max: swapped
    assert combat.damage_range(50, 0) == (50, 50)             # no max: the min
    assert combat.damage_range(0, 100) is None and combat.damage_range(None, None) is None


@needs_kb
def test_training_spots_never_come_back_empty_for_stats():
    from maplehelper.kb import KnowledgeBase
    kb = KnowledgeBase(REAL_KB)
    mage = combat.spots(kb, 30, acc=70, dmg=(15, 40), magic=True, n=6)       # the staff swing isn't a spell
    assert mage and all(s.hits is None for s in mage)
    weak = combat.spots(kb, 30, acc=73, dmg=(1, 2), n=6)                     # nothing dies in 12 basic hits
    assert weak and not any(s.fits for s in weak) and weak == sorted(weak, key=lambda s: -s.score)
    for lv in (1, 5, 10, 15):
        assert not any(combat.special_monster(s.monster.name) for s in combat.spots(kb, lv, n=20))


@needs_kb
def test_crafting_lists_every_recipe_up_to_your_level():
    from maplehelper import crafting
    from maplehelper.kb import KnowledgeBase
    kb = KnowledgeBase(REAL_KB)
    rows = crafting.up_to(kb, "smithing", 3)
    by_level = {lv.level: len(lv.recipes) for lv in crafting.levels(kb, "smithing")}
    assert len(rows) == sum(n for lv, n in by_level.items() if lv <= 3)
    assert {r.level for r in rows} == {lv for lv in by_level if lv <= 3}
    assert [r.level for r in rows] == sorted((r.level for r in rows), reverse=True)     # newest first


@needs_kb
def test_guides_for_you_and_third_job_build():
    from maplehelper import guides
    from maplehelper.kb import KnowledgeBase
    from maplehelper.store import Character
    kb = KnowledgeBase(REAL_KB)
    hollow = "guide/forgotten-hollow-the-new-endgame-area"
    # picked from Lv. 39, unless the release guide says the Hollow is closed (Founder's Access)
    closed = "Forgotten Hollow" in availability.of(kb).closed_areas
    assert (hollow in guides.for_you(kb, Character("1", "A", "Warrior", "Fighter", 39))) is not closed
    assert hollow not in guides.for_you(kb, Character("1", "A", "Warrior", "Fighter", 38))
    assert plan.class_guide(kb, "Warrior", "Crusader") == "guide/fighter-class-guide"
    assert plan.class_guide(kb, "Magician", "Priest") == "guide/cleric-class-guide"


@needs_kb
def test_a_closed_hollow_is_not_picked_for_you(monkeypatch):
    # Founder's Access (10-06): "Forgotten Hollow is closed", so a Lv. 45 player isn't sent to its guide
    from types import SimpleNamespace

    from maplehelper import guides
    from maplehelper.kb import KnowledgeBase
    from maplehelper.store import Character
    kb = KnowledgeBase(REAL_KB)
    hollow = "guide/forgotten-hollow-the-new-endgame-area"
    monkeypatch.setattr(availability, "of", lambda _kb: SimpleNamespace(closed_areas=["Forgotten Hollow"]))
    assert hollow not in guides.for_you(kb, Character("1", "A", "Thief", "Assassin", 45))
    monkeypatch.setattr(availability, "of", lambda _kb: SimpleNamespace(closed_areas=[]))
    assert hollow in guides.for_you(kb, Character("1", "A", "Thief", "Assassin", 45))


@needs_kb
def test_profession_info_names_teacher_town_and_quests():
    from maplehelper import crafting
    from maplehelper.kb import KnowledgeBase
    KB = KnowledgeBase(REAL_KB)
    from maplehelper import availability
    a = availability.of(KB)
    # Silas Irons in Perion, Lv. 10 to 25 tonight: whoever the KB names, a real NPC with a town, a start before the
    # mastery, and work stations only in towns that are out (no El Nath while Ossyria isn't)
    for prof in crafting.PROFESSIONS:
        i = crafting.info(KB, prof)
        assert i.teacher and KB.get(i.teacher_key) and i.teacher_town, prof
        assert i.start_quest and i.master_quest and 0 < i.start_level < i.master_level, prof
        assert i.station_towns and all(a.place_open(t) for t in i.station_towns), prof
    assert crafting.info(KB, "leatherworking").start_quest       # no "in Need of an Apprentice": the first one


def test_the_calculators_hp_hint_explains_the_monsters_hp():
    """The "?" beside a monster's HP explained the player's HP / MP and levels (the owner's report)."""
    from maplehelper import glossary
    from maplehelper.ui import terms
    tip = terms.tip_html("Monster HP", "he")
    assert "להרוג את המפלצת" in tip and "<b style" in tip and ">HP<" in tip
    assert "MP" not in glossary.explain("Monster HP", "he")
