"""routes.json from NiaMeowDB's map data (the file its Pathfinder reads): every map's portals and NPCs with their
minimap spots, the invisible teleports the app marks on the game's minimap ("hidden", one within the map with the
point it lands on), and for a map with no minimap (a shop) the frame of its room picture ("scene").

The nightly scrape (tools/scrape_meowdb.py) builds it with this, and so does the app itself (refresh): a KB built
before routes.json carried the hidden teleports gave a player no dots at all, with nothing to tell them why (0.18.0's
KB, 2026-10-11, on macOS too), so the app rebuilds that file from the site when the KB it loaded lacks them. It does
so, once, for a file without their landing points too (no LANDINGS mark: every KB built before 2026-10-14), which the
app needs to say which pad to take on a map full of them (Utah's Pig Farm), and once more for a file built before
every pad was kept (no ALL_PADS mark: the type-4 warps and the second pad on a shared spot were dropped)."""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path

BASE = "https://meowdb.com"
MAPS_DATA = f"{BASE}/_data/maps.json"
# A map with no minimap (a shop, the hospital) has its whole room as its picture: the site's full render, framed by
# the map's view rectangle ("vr": left, top, right, bottom in map units) in its terrain file. That frame places the
# room's NPCs on the picture (the map page's own NPC markers use it), where the game itself folds the minimap.
MAP_TERRAIN = f"{BASE}/_data/map-terrain/{{id}}.json"
ROUTES = "routes.json"
SOURCE = "NiaMeowDB (meowdb.com) map data, as its Pathfinder reads it"
MAP_ID = re.compile(r"^\d{9}$")
# the game's portal kinds (the map data's "type"): 2 is drawn on the minimap (the blue ring), 1 is invisible (stand on it
# and press up), 3 is a touch teleport (walk or fall into it) and 4 is a same-map warp with no ring drawn either (the
# site's only ones are the "join00" pads of the fitness-test rooms); the site draws each of 1, 3 and 4 as a warp, and
# the app draws the invisible ones on the game's minimap
HIDDEN_PORTAL_TYPES = (1, 3, 4)
# routes_data's mark on the file: its hidden teleports carry where each one within the map lands ("to_x", "to_y").
# A file without it was built before they did, and the app rebuilds it once (outdated)
LANDINGS = "landings"
# routes_data's mark that its hidden list is every hidden teleport the site records (the type-4 warps, and each pad
# on a spot more than one pad stands on: built before it, a shared spot kept only the first). A file without it
# predates that, and the app rebuilds it once (outdated)
ALL_PADS = "all_pads"
APP_PAUSE = 0.5         # seconds between the app's own requests to the site (the nightly scrape waits 1 s)
APP_UA = "MapleHelper (MapleStory Classic companion app; used with NiaMeowDB permission)"

log = logging.getLogger("maplehelper")


def hidden_portals(m: dict) -> list[dict]:
    """The map's invisible teleports, to other maps and within it (the hidden passages: "hide01" to "hide01_1"), every
    one of them: two on one spot are two teleports (Up and Up's "np04", "np05" and "np06" all stand at (461, 610) and
    land in three places), so no spot is ever deduped away. One within the map (the site's intraPortals: "t001" to
    "st00") keeps the point it lands on as "to_x", "to_y": the landing point is what lets the app say which pad to
    take to the next step on a map full of them (Utah's Pig Farm has 16). One to another map lands on no point of
    this one: its name, x and y alone."""
    out = []
    for p in [*(m.get("portals") or []), *(m.get("intraPortals") or [])]:
        if p.get("type") in HIDDEN_PORTAL_TYPES:
            x, y = p.get("x") or 0, p.get("y") or 0
            row = {"name": p.get("name") or "", "x": x, "y": y}
            if p.get("toX") is not None and p.get("toY") is not None:
                row["to_x"], row["to_y"] = p["toX"], p["toY"]
            out.append(row)
    return out


def routes_data(maps: list[dict], taxi: list[str], scenes: dict[str, list] | None = None) -> dict:
    """What the app routes with, from the site's map data: ids, names, portals and NPCs with their minimap spots, and
    the invisible teleports it marks on the game's minimap, with where each one within the map lands and every pad
    kept (the file marked LANDINGS and ALL_PADS). `scenes`: for maps with no minimap, the frame of their room
    picture ([width, height, x offset, y offset], scene_frame), kept as "scene"."""
    out, ids = [], {str(m.get("id") or "") for m in maps}
    for m in maps:
        mid = str(m.get("id") or "")
        if not MAP_ID.match(mid):
            continue
        mm = None
        if m.get("hasMinimapImage") and m.get("minimapWidth") and m.get("minimapHeight"):
            mm = [m["minimapWidth"], m["minimapHeight"], m.get("miniMapCenterX") or 0, m.get("miniMapCenterY") or 0]
        portals = [{"to": p["toMapId"], "name": p.get("name") or "", "x": p.get("x") or 0, "y": p.get("y") or 0}
                   for p in m.get("portals") or [] if str(p.get("toMapId") or "") in ids and p["toMapId"] != mid]
        npcs = [{"id": str(n.get("id")), "name": n.get("name") or "", "x": n.get("x") or 0, "y": n.get("y") or 0}
                for n in m.get("npcs") or [] if n.get("id")]
        row = {"id": mid, "name": m.get("name") or mid, "street": m.get("streetName") or "",
               "region": m.get("region") or "", "town": bool(m.get("isTown")), "return": m.get("returnMap") or "",
               "minimap": mm, "portals": portals, "npcs": npcs, "hidden": hidden_portals(m)}
        if mm is None and (scenes or {}).get(mid):
            row["scene"] = scenes[mid]
        out.append(row)
    return {"source": SOURCE, "taxi": taxi, LANDINGS: True, ALL_PADS: True, "maps": out}


def scene_frame(terrain: dict | None) -> list | None:
    """A terrain file's view rectangle as [width, height, x offset, y offset], the shape of a minimap frame; None
    without a usable one."""
    vr = (terrain or {}).get("vr")
    if not (isinstance(vr, list) and len(vr) == 4 and all(isinstance(v, (int, float)) for v in vr)):
        return None
    left, top, right, bottom = vr
    return [right - left, bottom - top, -left, -top] if right > left and bottom > top else None


def _scene_id(m: dict) -> str | None:
    mid = str(m.get("id") or "")
    return mid if MAP_ID.match(mid) and not m.get("hasMinimapImage") and m.get("npcs") else None


def _terrain_files(maps: list[dict], fetch, pause, ids: set[str]) -> dict[str, dict]:
    """The parsed terrain file of each wanted map, one request each (in map order): fetch(url) -> text or None,
    pause() between requests. A map whose file can't be fetched or parsed is simply left out."""
    out = {}
    for m in maps:
        mid = str(m.get("id") or "")
        if mid not in ids or mid in out:
            continue
        try:
            raw = fetch(MAP_TERRAIN.format(id=mid))
        except Exception:          # noqa: BLE001 - one map's frame missing: that map is simply left out
            raw = None
        pause()
        try:
            terrain = json.loads(raw) if raw else None
        except (json.JSONDecodeError, TypeError):
            terrain = None
        if isinstance(terrain, dict):
            out[mid] = terrain
    return out


def scene_frames(maps: list[dict], fetch, pause, terrain: dict[str, dict] | None = None) -> dict[str, list]:
    """The room frame of every map with NPCs and no minimap (about 40), one terrain file each: fetch(url) -> text or
    None, pause() between requests. `terrain`: terrain files already fetched (see _terrain_files), reused as-is."""
    if terrain is None:
        terrain = _terrain_files(maps, fetch, pause, {mid for m in maps if (mid := _scene_id(m))})
    out = {}
    for m in maps:
        mid = _scene_id(m)
        if mid and (frame := scene_frame(terrain.get(mid))):
            out[mid] = frame
    return out


def write_routes(path: Path, data: dict) -> None:
    """One map per line, like index.json: the AI greps the KB folder. Written whole, then swapped in: a reader (the
    app's tables, the route graph) never sees half a file."""
    head = json.dumps({k: v for k, v in data.items() if k != "maps"}, ensure_ascii=False)[:-1]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(head + ', "maps": [\n' + ",\n".join(json.dumps(m, ensure_ascii=False) for m in data["maps"])
                   + "\n]}\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- the app's own check

def _read(root: Path) -> dict | None:
    try:
        data = json.loads((Path(root) / ROUTES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def outdated(data: dict | None) -> bool:
    """routes.json built before it carried the invisible teleports (maps, and not one with a "hidden" list: a map with
    none has an empty one), before they carried where each one lands (no LANDINGS mark), or before every pad was kept
    (no ALL_PADS mark): rebuilt, once, since the file written has all three. No file or no maps is not this case:
    there is nothing to route with anyway."""
    data = data or {}
    maps = data.get("maps")
    if not isinstance(maps, list) or not maps:
        return False
    return (not data.get(LANDINGS) or not data.get(ALL_PADS)
            or not any(isinstance(m, dict) and "hidden" in m for m in maps))


def needs_refresh(root: Path) -> bool:
    return outdated(_read(root))


def _fetch(url: str, timeout: float = 30) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": APP_UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:          # noqa: BLE001 - offline, a timeout, an error page: the file we have stays
        return None


def refresh(root: Path, fetch=_fetch, pause=lambda: time.sleep(APP_PAUSE)) -> bool:
    """The KB's routes.json rebuilt from the site's map data when it lacks the hidden teleports or where they land
    (outdated); True when it was written. The taxi towns stay as the file had them (the nightly scrape reads those
    from the Pathfinder page). The site down, or its file unusable: nothing written, False (tried again on the next
    start or KB load)."""
    path = Path(root) / ROUTES
    old = _read(root)
    if not outdated(old):
        return False
    raw = fetch(MAPS_DATA)
    try:
        maps = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        maps = None
    if not isinstance(maps, list) or not maps:
        log.warning("routes: NiaMeowDB's map data not available, the hidden teleports wait for the next try")
        return False
    pause()
    wanted = {mid for m in maps if (mid := _scene_id(m))}
    frames = _terrain_files(maps, fetch, pause, wanted)
    data = routes_data(maps, [str(t) for t in (old or {}).get("taxi") or []],
                       scene_frames(maps, fetch, pause, frames))
    if not data["maps"] or not outdated(_read(root)):
        return False        # nothing usable, or a KB update brought a new file meanwhile: that one stays
    write_routes(path, data)
    log.info("routes: rebuilt from NiaMeowDB's map data (the KB's file lacked the hidden teleports, where they "
             "land or every pad): %d maps, %d with hidden teleports, %d with landing points, %d room frames",
             len(data["maps"]), sum(1 for m in data["maps"] if m["hidden"]),
             sum(1 for m in data["maps"] if any("to_x" in h for h in m["hidden"])),
             sum(1 for m in data["maps"] if "scene" in m))
    return True
