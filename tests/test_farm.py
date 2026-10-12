"""Farming (farm.py, the Farm window's data): who drops an item and what pays at a level."""
from pathlib import Path

import pytest

from maplehelper import combat, farm, sources

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")


@pytest.fixture(scope="module")
def kb():
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


# ---------------------------------------------------------------- from the KB

@needs_kb
def test_farmable_items_are_the_ones_monsters_in_the_game_drop(kb):
    keys = farm.farmable(kb)
    assert keys and all(k in kb.droppers for k in keys)
    names = [kb.get(k)["name"] for k in keys]
    assert len(names) == len(set(names))                   # each name once
    assert names == sorted(names, key=str.lower)


@needs_kb
def test_droppers_put_community_sightings_first_and_say_how_they_fit(kb):
    key = farm.item_named(kb, "Bronze Ore")
    ds = farm.droppers(kb, key, 10)
    assert {d.key for d in ds} == set(kb.droppers[key])
    srcs = [d.source for d in ds]
    assert srcs == sorted(srcs, key=lambda s: s != sources.COMMUNITY)       # players' sightings first
    for d in ds:
        assert d.source == (kb.drop_source(d.key, key) or sources.MSEA)
        assert d.fit == farm.fit(10, d.level)
        if d.source == sources.COMMUNITY:
            assert d.vote == kb.community_vote(d.key, key)


@needs_kb
def test_a_monster_only_in_a_party_quest_says_where_it_is(kb):
    """King Slime lives only on KPQ's last stage: it was listed with no map as a farm (audit GAM-11)."""
    for item in ("item/429", "item/1368"):                       # Coupon, Squishy Shoes (the players' list)
        king = next(d for d in farm.droppers(kb, item, 25) if d.key == "monster/800003")
        assert king.closed and king.boss and "Accompaniment" in king.map


def test_fit_by_level():
    assert farm.fit(30, 30) == "easy" and farm.fit(30, 12) == "easy"
    assert farm.fit(30, 30 + combat.SPOT_ABOVE) == "range"
    assert farm.fit(30, 31 + combat.SPOT_ABOVE) == "hard"
    assert farm.fit(None, 50) == "range"                   # no level known: nothing is judged


@needs_kb
def test_targets_rank_by_the_best_npc_price_in_the_level_band(kb):
    level = 34
    rows = farm.targets(kb, level, n=8)
    assert rows
    assert [r.best for r in rows] == sorted((r.best for r in rows), reverse=True)
    for r in rows:
        m = combat.monster(kb, r.key)
        assert level - farm.FARM_BELOW <= r.level <= level + combat.SPOT_ABOVE
        assert m.maps and not m.boss and not combat.special_monster(r.name)
        assert r.drops and all(d.value and d.value.price == farm.value(kb, d.key).price for d in r.drops)
        assert all(d.key in kb.monster_drops(r.key) for d in r.drops)       # its own drop lists, nothing else
        prices = [d.value.price for d in r.drops]
        assert prices == sorted(prices, reverse=True)
    assert len({r.name for r in rows}) == len(rows)


@needs_kb
def test_value_is_the_item_pages_npc_sell_price(kb):
    from maplehelper import market
    key = farm.item_named(kb, "Bronze Ore")
    v = farm.value(kb, key)
    assert v and v.price == market.npc_prices(kb, key).sell_back
    assert v.source == sources.source_of(kb, key)
    assert farm.value(kb, None) is None and farm.value(kb, "item/does-not-exist") is None


# ---------------------------------------------------------------- worth farming

@pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
def test_worth_farming_puts_what_the_player_needs_first():
    # farming isn't only for an NPC's price (the owner): a drop a quest of the player's needs comes first, tagged
    from maplehelper.kb import KnowledgeBase
    kb = KnowledgeBase(REAL_KB)
    wanted = farm.needs(kb, 20, "Bowman", "Bowman", [], None, [])
    # some item a level-20 Bowman's quests ask for (Stirge Wing today): which one is the game's to change
    assert any(v[0] == "quest" for v in wanted.values())
    rows = farm.targets(kb, 20, n=6, wanted=wanted)
    assert rows and rows[0].needed >= 1 and rows[0].drops[0].need
    assert [r.needed for r in rows] == sorted((r.needed for r in rows), reverse=True)
    plain = farm.targets(kb, 20, n=6)                   # nothing wanted: by the NPC price, as before
    assert all(not d.need for r in plain for d in r.drops)
