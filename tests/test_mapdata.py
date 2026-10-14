"""mapdata.hidden_portals against the site's own records: every hidden teleport meowdb lists for a map is kept,
with the landing the site records for it."""
from maplehelper import mapdata


def test_distinct_teleports_on_one_spot_all_survive():
    """Two (here three) different teleports standing on one spot are not one pad: Up and Up <Level 3>'s np04, np05
    and np06 all stand at (461, 610) on the site and land in three different places, so all three are kept, each
    with its own landing. The old reader kept only the first per (x, y)."""
    m = {"portals": [], "intraPortals": [
        {"name": "np04", "type": 1, "x": 461, "y": 610, "toName": "ch11", "toX": -94, "toY": -707},
        {"name": "np05", "type": 1, "x": 461, "y": 610, "toName": "ch01", "toX": -1895, "toY": -707},
        {"name": "np06", "type": 1, "x": 461, "y": 610, "toName": "ch05", "toX": -1173, "toY": -706}]}
    assert mapdata.hidden_portals(m) == [
        {"name": "np04", "x": 461, "y": 610, "to_x": -94, "to_y": -707},
        {"name": "np05", "x": 461, "y": 610, "to_x": -1895, "to_y": -707},
        {"name": "np06", "x": 461, "y": 610, "to_x": -1173, "to_y": -706}]


def test_a_teleports_landing_is_kept_as_the_site_records_it():
    """Utah's Pig Farm's t007, exactly as the site records it: pad (1584, -99), landing (1624, 150) — kept as
    to_x/to_y, neither recomputed nor dropped. A hidden portal to another map keeps no landing: it lands on no
    point of this map."""
    m = {"portals": [{"name": "hide00", "type": 1, "toMapId": "010001080", "x": 5, "y": 6}],
         "intraPortals": [{"name": "t007", "type": 1, "x": 1584, "y": -99, "toName": "st06",
                           "toX": 1624, "toY": 150}]}
    assert mapdata.hidden_portals(m) == [{"name": "hide00", "x": 5, "y": 6},
                                         {"name": "t007", "x": 1584, "y": -99, "to_x": 1624, "to_y": 150}]


def test_the_type4_warps_are_kept_and_the_drawn_ring_is_not():
    """The class the type filter used to drop: a type-4 same-map warp (the fitness-test rooms' "join00", the site's
    record for 090040000 below) is a hidden teleport the site draws as a warp, so it is kept with its landing. Type
    2 stays out, within a map as between maps: the game draws that blue ring itself."""
    m = {"portals": [{"name": "out00", "type": 2, "toMapId": "010001080", "x": 1469, "y": -808}],
         "intraPortals": [{"name": "join00", "type": 4, "x": 139, "y": 105, "toName": "join01",
                           "toX": -357, "toY": -140},
                          {"name": "in00", "type": 2, "x": 252, "y": -230, "toName": "out00",
                           "toX": -544, "toY": -521}]}
    assert mapdata.hidden_portals(m) == [{"name": "join00", "x": 139, "y": 105, "to_x": -357, "to_y": -140}]


def test_utahs_pig_farm_inventory_matches_the_site():
    """010001082 as the site records it (2026-10-14): 16 intraPortals, all type 1 — t001-t007 landing across the
    map, h001-h009 all landing on the west entrance (-1466, 147) — and our hidden list is exactly those 16, name,
    pad and landing. Its two portals are type 2 exits to another map and stay out. No pad and no landing is on
    Utah's ledge (the foothold span 1710..1800 at y -805, Utah at (1766, -809)): the nearest landing is t007's
    (1624, 150), the floor below."""
    m = {"portals": [{"name": "out00", "type": 2, "x": 1469, "y": -808, "toMapId": "010001080"},
                     {"name": "out01", "type": 2, "x": -1466, "y": 152, "toMapId": "010001080"}],
         "intraPortals": [
             {"name": "t001", "type": 1, "x": -1463, "y": -155, "toName": "st00", "toX": -1480, "toY": -637},
             {"name": "t002", "type": 1, "x": -338, "y": -456, "toName": "st01", "toX": -1165, "toY": -406},
             {"name": "t003", "type": 1, "x": -769, "y": -216, "toName": "st02", "toX": -272, "toY": -212},
             {"name": "t004", "type": 1, "x": -141, "y": 86, "toName": "st03", "toX": -5, "toY": -630},
             {"name": "t005", "type": 1, "x": 478, "y": -513, "toName": "st04", "toX": 627, "toY": -270},
             {"name": "t006", "type": 1, "x": 783, "y": -35, "toName": "st05", "toX": 267, "toY": -152},
             {"name": "t007", "type": 1, "x": 1584, "y": -99, "toName": "st06", "toX": 1624, "toY": 150},
             {"name": "h001", "type": 1, "x": -1320, "y": -455, "toName": "h000", "toX": -1466, "toY": 147},
             {"name": "h002", "type": 1, "x": -1132, "y": -695, "toName": "h000", "toX": -1466, "toY": 147},
             {"name": "h003", "type": 1, "x": -755, "y": -457, "toName": "h000", "toX": -1466, "toY": 147},
             {"name": "h004", "type": 1, "x": -102, "y": -156, "toName": "h000", "toX": -1466, "toY": 147},
             {"name": "h005", "type": 1, "x": 420, "y": 85, "toName": "h000", "toX": -1466, "toY": 147},
             {"name": "h006", "type": 1, "x": 927, "y": -454, "toName": "h000", "toX": -1466, "toY": 147},
             {"name": "h007", "type": 1, "x": 1235, "y": -157, "toName": "h000", "toX": -1466, "toY": 147},
             {"name": "h008", "type": 1, "x": -351, "y": -694, "toName": "h000", "toX": -1466, "toY": 147},
             {"name": "h009", "type": 1, "x": 128, "y": -393, "toName": "h000", "toX": -1466, "toY": 147}]}
    hidden = mapdata.hidden_portals(m)
    assert [h["name"] for h in hidden] == [f"t00{i}" for i in range(1, 8)] + [f"h00{i}" for i in range(1, 10)]
    assert hidden[6] == {"name": "t007", "x": 1584, "y": -99, "to_x": 1624, "to_y": 150}
    assert all(h["to_x"] == -1466 and h["to_y"] == 147 for h in hidden[7:])
    assert not any(1710 <= h.get("to_x", 0) <= 1800 and -830 <= h.get("to_y", 0) <= -780 for h in hidden)
    assert not any(1710 <= h["x"] <= 1800 and -830 <= h["y"] <= -780 for h in hidden)


def test_the_rebuild_mark_bumps_with_the_kept_pads():
    """routes_data now marks the file "all_pads": a routes.json with the older marks but not this one is outdated
    (rebuilt once), one with it is left alone. The nightly scrape writes the same shape: it builds with this very
    routes_data."""
    import scrape_meowdb
    assert scrape_meowdb.routes_data is mapdata.routes_data
    maps = [{"id": "000000001", "name": "A", "portals": [], "npcs": []}]
    data = mapdata.routes_data(maps, [])
    assert data[mapdata.ALL_PADS] is True and data[mapdata.LANDINGS] is True
    old = {"landings": True, "terrain": True, "maps": [{"id": "000000001", "hidden": []}]}
    assert mapdata.outdated(old)
    assert not mapdata.outdated(data)
