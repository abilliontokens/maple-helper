"""Loot log: the game's pickup messages read into EXP, mesos and items, each message once (lootlog.py)."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from maplehelper import lootlog

FIX = Path(__file__).resolve().parent / "fixtures"
REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
# the two Cash hats the live KB has and cut-off reads were matched to (59 Green Mushroom Caps logged as the hat): a KB
# from before them gets them as the live one has them
LIVE_HATS = {"item/3551": "Green Mushroom Hat", "item/3285": "Blue Mushroom Hat"}
GREEN_CAP = "item/360"


@pytest.fixture(scope="module")
def kb():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


@pytest.fixture(scope="module")
def live_kb():
    """The real KB with the live KB's Cash hats (its own copy: the other tests' KB stays as it is)."""
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    kb = KnowledgeBase(REAL_KB)
    for key, name in LIVE_HATS.items():
        kb.entities.setdefault(key, {"key": key, "id": key.split("/")[1], "name": name, "category": "item",
                                     "type": "Cash Equip / Cash Hat"})
    return kb


def _items(**names: str) -> dict[str, str]:
    """item_names' shape for a few names: {lower name: key, "\\0" + lower: name}."""
    out = {}
    for key, name in names.items():
        out[name.lower()] = key.replace("_", "/")
        out["\0" + name.lower()] = name
    return out


def _live_reads() -> dict[float, list]:
    """Every read (2 a second for 5 minutes) of a live session's messages box: OCR rows (text, y centre, height)."""
    raw = json.loads((FIX / "loot_reads_live.json").read_text(encoding="utf-8"))
    return {float(t): [tuple(r) for r in rows] for t, rows in raw.items()}


def _replay(kb, reads: dict, step: int = 1) -> lootlog.Log:
    tr = lootlog.Tracker(lootlog.item_names(kb), lootlog.drop_keys(kb))
    lg = lootlog.Log(start=0)
    for t in sorted(reads)[::step]:
        lg.add(tr.read(reads[t], t))
    return lg


@pytest.mark.parametrize("text,kind,value", [
    ("You received EXP (+21)", "exp", 21),
    ("You recelved ExP (+18)", "exp", 18),
    ("Youreceived EXP (+2)", "exp", 2),
    ("You have gained mesos (+27)", "mesos", 27),
    ("You have gained mesgs (+5)", "mesos", 5),
    ("You have qained mesos (+28)", "mesos", 28),
    ("Leaf x1 earned. (Etc)", "item", "Leaf"),
    ("Firewood x1 eamned. (Etc)", "item", "Firewood"),
    ("Leafxd eamed. (Etc)", "item", "Leaf"),
    ("Red Snail Shell x1 earned. (Etc)", "item", "Red Snail Shell"),
])
def test_reads_each_kind_of_message_as_ocr_spells_it(text, kind, value):
    line = lootlog.parse(text)
    assert line is not None and line.kind == kind
    assert (line.name if kind == "item" else line.amount) == value


@pytest.mark.parametrize("text", ["Brown Kitty", "Shweeet", "THLI", "Marlu : [Angel Wand] B>White Label Ring"])
def test_other_text_in_the_box_is_no_message(text):
    """Name tags and chat bubbles pass behind the box."""
    assert lootlog.parse(text) is None


@pytest.mark.parametrize("size,lines", [
    # each live window size: where its message lines were read (left, top, right, bottom, fractions of the window)
    ((1368, 800), [(0.863, 0.721, 0.999, 0.820)]),
    ((1922, 1112), [(0.865, 0.735, 0.999, 0.815)]),
    ((2734, 1568), [(0.873, 0.734, 0.999, 0.811)]),
])
def test_the_messages_box_holds_the_messages_at_every_window_size(size, lines):
    """Measured live at three window sizes: every message line falls inside the box found for the window, wherever
    the window is on screen."""
    w, h = size
    box = lootlog.auto_box((100, 50, w, h))
    for left, top, right, bottom in lines:
        assert box["x"] <= 100 + left * w and 100 + right * w <= box["x"] + box["w"]
        assert box["y"] <= 50 + top * h and 50 + bottom * h <= box["y"] + box["h"]
    assert box["y"] > 50 + 0.4 * h          # under the chat bubbles over the player


def test_a_small_box_is_enlarged_for_the_reader_and_read_back_in_its_own_pixels(monkeypatch):
    from maplehelper import hud
    seen = []

    def engine(arr, use_cls):
        seen.append(arr.shape)
        return type("R", (), {"txts": ["You received EXP (+8)"],
                              "boxes": np.array([[[0, 300], [10, 300], [10, 340], [0, 340]]])})()
    monkeypatch.setattr(hud, "_ocr", lambda: engine)
    rows = lootlog.ocr_rows(np.zeros((150, 200, 3), np.uint8))
    assert seen[0][0] == lootlog.OCR_MIN_H and seen[0][1] == 600
    assert rows == [("You received EXP (+8)", pytest.approx(320 / 3), pytest.approx(40 / 3))]


def test_a_misread_plus_is_no_sure_amount():
    """While a line fades, OCR reads "(+43)" as "(443)": the same message, not 443 EXP."""
    a, b = lootlog.parse("You received EXP (+43)"), lootlog.parse("You received ExP (443h")
    assert a.sure and lootlog.agree(a, b)
    assert not lootlog.agree(a, lootlog.parse("You received EXP (+21)"))


@needs_kb
def test_a_live_session_counts_every_message_once(kb):
    """Five minutes of live reads: each message stays on screen for ~6 s (a dozen reads) and moves up a row with
    every new one, yet each is counted once, with the value its clear reads agree on."""
    lg = _replay(kb, _live_reads())
    exp, mesos, items = lg.totals()
    assert (exp, mesos) == (358, 327)
    assert {n: v[0] for n, v in items.items()} == {"Firewood": 5, "Snail Shell": 2, "Tree Branch": 2, "Leaf": 2,
                                                  "Red Snail Shell": 1}
    assert all(v[1] for v in items.values())        # every item is the KB's


@needs_kb
@pytest.mark.parametrize("step", [2, 3])
def test_slower_reads_count_the_same(kb, step):
    """Reading every 1 or 1.5 s instead of 0.5 s: the same totals (a message stays long enough)."""
    exp, mesos, items = _replay(kb, _live_reads(), step).totals()
    assert (exp, mesos, {n: v[0] for n, v in items.items()}) == (
        358, 327, {"Firewood": 5, "Snail Shell": 2, "Tree Branch": 2, "Leaf": 2, "Red Snail Shell": 1})


@needs_kb
def test_a_small_window_counts_too(kb):
    """Live at 1368x800, the box the window gives, enlarged for the reader: 87 EXP, 91 mesos and 3 Red Snail Shells,
    what the frames show (read at the window's own size, half the messages were missed)."""
    raw = json.loads((FIX / "loot_reads_small_live.json").read_text(encoding="utf-8"))
    lg = _replay(kb, {float(t): [tuple(r) for r in rows] for t, rows in raw.items()})
    exp, mesos, items = lg.totals()
    assert (exp, mesos, {n: v[0] for n, v in items.items()}) == (87, 91, {"Red Snail Shell": 3})


@needs_kb
def test_a_small_window_frame_reads_every_line():
    """A 301x232 box of a 1368x800 window: the five clear messages read whole (the faded one on top is left out)."""
    pytest.importorskip("rapidocr")
    rows = lootlog.ocr_rows(np.asarray(Image.open(FIX / "loot_small_live.png").convert("RGB")))
    lines = [ln for r in rows if (ln := lootlog.parse(r[0]))]
    assert [(ln.kind, ln.name if ln.kind == "item" else ln.amount) for ln in lines] == [
        ("exp", 10), ("item", "Red Snail Shell"), ("exp", 10), ("exp", 10), ("mesos", 14)]


def test_what_is_on_screen_when_the_log_starts_isnt_counted():
    tr = lootlog.Tracker()
    rows = [("You received EXP (+21)", 100.0, 14.0), ("You have gained mesos (+27)", 128.0, 14.0)]
    assert tr.read(rows, 0.0) == []
    assert tr.read(rows, 0.5) == []
    new = tr.read(rows[1:] + [("Leaf x1 earned. (Etc)", 156.0, 14.0)], 1.0)
    assert [(e.kind, e.name) for e in new] == [("item", "Leaf")]


def test_the_same_amount_twice_in_a_row_is_two_messages():
    """Two kills of the same monster: "+2" then "+2" again, the first pushed up a row."""
    tr = lootlog.Tracker()
    tr.read([("You received EXP (+30)", 128.0, 14.0)], 0.0)
    assert [e.amount for e in tr.read([("You received EXP (+30)", 100.0, 14.0),
                                       ("You received EXP (+2)", 128.0, 14.0)], 0.5)] == [2]
    assert [e.amount for e in tr.read([("You received EXP (+30)", 72.0, 14.0), ("You received EXP (+2)", 100.0, 14.0),
                                       ("You received EXP (+2)", 128.0, 14.0)], 1.0)] == [2]


def test_a_cut_off_amount_is_counted_once_it_is_read():
    tr = lootlog.Tracker()
    tr.read([("You received EXP (+30)", 128.0, 14.0)], 0.0)
    assert tr.read([("You received EXP (+30)", 100.0, 14.0), ("You have gained mes", 128.0, 14.0)], 0.5) == []
    new = tr.read([("You received EXP (+30)", 100.0, 14.0), ("You have gained mesos (+41)", 128.0, 14.0)], 1.0)
    assert [(e.kind, e.amount) for e in new] == [("mesos", 41)]


@needs_kb
def test_live_frames_read_with_the_app_reader(kb):
    """The OCR the app uses, on two live captures of the box: four messages stacked, and three fading (the top one
    mid-fade read "(243)" for "(+43)" by the angle classifier, which stays off)."""
    pytest.importorskip("rapidocr")
    stack = lootlog.ocr_rows(np.asarray(Image.open(FIX / "loot_stack_live.png").convert("RGB")))
    lines = [ln for r in stack if (ln := lootlog.parse(r[0]))]
    assert [(ln.kind, ln.amount if ln.kind != "item" else ln.name) for ln in lines] == [
        ("exp", 32), ("exp", 18), ("mesos", 35), ("item", "Firewood")]
    fading = lootlog.ocr_rows(np.asarray(Image.open(FIX / "loot_fading_live.png").convert("RGB")))
    kinds = [ln.kind for r in fading if (ln := lootlog.parse(r[0]))]
    assert kinds == ["exp", "mesos", "item"]


@needs_kb
def test_a_log_is_saved_ended_and_kept_per_character(kb, isolated_store):
    st = lootlog.Store()
    lg = st.start("c1", kb, now=1000.0)
    lg.add([lootlog.Event(1010.0, "exp", 21), lootlog.Event(1011.0, "mesos", 27),
            lootlog.Event(1012.0, "item", 2, "Leaf", "item/358")])
    rec = st.end("c1", kb, lg, now=1300.0)
    assert rec["exp"] == 21 and rec["mesos"] == 27 and rec["picked"] == 2 and rec["seconds"] == 300
    again = lootlog.Store()          # from disk
    assert again.running("c1") is None and again.recent("c1")[0]["top"] == [["Leaf", 2]]
    assert again.log("c1").totals()[0] == 21
    again.forget("c1")
    assert lootlog.Store().recent("c1") == [] and lootlog.Store().log("c1") is None


@needs_kb
def test_starting_a_log_ends_the_one_running(kb, isolated_store):
    """The game shows one character's messages: a new log (another character's too) ends the running one."""
    st = lootlog.Store()
    lg = st.start("a", kb, now=0.0)
    lg.add([lootlog.Event(5.0, "exp", 10)])
    st.put("a", lg)
    st.start("b", kb, now=100.0)
    assert st.running("a") is None and st.running_any() == "b" and st.recent("a")[0]["exp"] == 10


def test_old_events_stay_in_the_totals(monkeypatch):
    monkeypatch.setattr(lootlog, "MAX_EVENTS", 3)
    lg = lootlog.Log(start=0)
    lg.add([lootlog.Event(i, "mesos", 10) for i in range(5)])
    assert len(lg.events) == 3 and lg.totals()[1] == 50
    assert lootlog.Log.from_json(json.loads(json.dumps(lg.to_json()))).totals()[1] == 50


def test_an_events_map_and_level_are_kept_and_an_older_event_loads_without_them():
    ev = lootlog.Event(5.0, "exp", 21, map="102000000", level=12)
    assert lootlog.Event.from_json(json.loads(json.dumps(ev.to_json()))) == ev
    old = lootlog.Event.from_json({"t": 5.0, "kind": "mesos", "amount": 27})
    assert (old.map, old.level) == ("", None)
    assert lootlog.Event.from_json({"t": 5.0, "kind": "exp", "amount": 3, "level": True}).level is None
    # an EXP gain saved with the kill it was matched to (before kills went): loads, the kill left out
    tagged = lootlog.Event.from_json({"t": 5.0, "kind": "exp", "amount": 21, "map": "102000000",
                                      "monster": "monster/dark-stump", "level": 12})
    assert tagged == ev and "monster" not in tagged.to_json() and not hasattr(tagged, "monster")


def test_a_logs_bar_reads_and_pauses_are_kept(monkeypatch):
    monkeypatch.setattr(lootlog, "MAX_SAMPLES", 3)
    lg = lootlog.Log(start=0.0)
    for i in range(5):
        lg.add_sample(lootlog.HudSample(float(i), "102000000", 10, 200 + i, 11.5, 431, 444))
    lg.add_sample(lootlog.HudSample(5.0))                   # a read with nothing but its time
    assert [s.t for s in lg.samples] == [3.0, 4.0, 5.0]     # the newest kept
    assert not lg.paused
    lg.pause(10.0)
    lg.pause(11.0)                                          # already paused: the same pause
    lg.resume(20.0)
    lg.resume(21.0)                                         # not paused: nothing to end
    lg.pause(30.0)
    assert lg.paused and lg.pauses == [[10.0, 20.0], [30.0, None]]
    back = lootlog.Log.from_json(json.loads(json.dumps(lg.to_json())))
    assert back.samples == lg.samples and back.pauses == lg.pauses and back.paused
    assert back.samples[0] == lootlog.HudSample(3.0, "102000000", 10, 203, 11.5, 431, 444)
    assert back.samples[-1] == lootlog.HudSample(5.0)


def test_an_older_loot_json_log_loads_without_bar_reads_pauses_or_maps(isolated_store):
    """loot.json as the version before kept it: the running log goes on, with none of the grind's fields."""
    old = {"start": 1000.0, "ended": None, "db_id": 4, "events": [{"t": 1010.0, "kind": "exp", "amount": 21}],
           "base": {"exp": 5, "mesos": 0, "items": {}}}
    lootlog.Store.path.write_text(json.dumps({"active": {"c1": old}, "recent": {}}), encoding="utf-8")
    lg = lootlog.Store().running("c1")
    assert lg.samples == [] and lg.pauses == [] and not lg.paused and lg.db_id == 4 and lg.totals()[0] == 26
    assert (lg.events[0].map, lg.events[0].level) == ("", None)
    # what isn't a bar read or a pause loads as none
    lg = lootlog.Log.from_json(old | {"samples": [{"map": "x"}, "y", {"t": 1.0, "hp": "5"}],
                                      "pauses": [[1.0], [2.0, "z"], [3.0, None]]})
    assert lg.samples == [lootlog.HudSample(1.0)] and lg.pauses == [[3.0, None]]


@needs_kb
def test_a_log_ended_while_paused_ends_its_pause(kb, isolated_store):
    st = lootlog.Store()
    lg = st.start("c1", kb, now=1000.0)
    lg.add([lootlog.Event(1010.0, "exp", 21, map="102000000", level=12)])
    lg.pause(1100.0)
    st.put("c1", lg)
    st.start("c2", kb, now=1300.0)                          # (another log ends it, as loot.json has it)
    ended = lootlog.Store().log("c1")
    assert ended.ended == 1300.0 and ended.pauses == [[1100.0, 1300.0]] and not ended.paused
    assert (ended.events[0].map, ended.events[0].level) == ("102000000", 12)


@needs_kb
def test_value_counts_mesos_and_what_an_npc_pays(kb):
    lg = lootlog.Log(start=0, ended=600)
    lg.add([lootlog.Event(1, "mesos", 100), lootlog.Event(2, "item", 3, "Leaf", "item/358"),
            lootlog.Event(3, "item", 1, "Mystery", "")])
    sm = lootlog.summarize(kb, lg)
    leaf = next(i for i in sm.items if i[0] == "Leaf")
    assert leaf[3] and sm.value == 100 + 3 * leaf[3] and sm.picked == 4
    assert sm.mesos_h == 600 and sm.value_h == round(sm.value * 6)


# ------------------------------------------------------------ item names

@needs_kb
def test_a_cut_off_name_is_the_monster_drop_never_a_cash_item(live_kb):
    """Live: 59 Green Mushroom Caps were logged as the Green Mushroom Hat (a Cash Hat) and 14 Blue Mushroom Caps as
    the Blue Mushroom Hat: a read cut off to "Green Mushroom" is as close to either name, and difflib took the hat."""
    kb = live_kb
    assert {k: kb.get(k)["name"] for k in LIVE_HATS} == LIVE_HATS
    names = lootlog.item_names(kb)
    tr = lootlog.Tracker(names, lootlog.drop_keys(kb))
    blue = names["blue mushroom cap"]
    assert tr.resolve("Green Mushroom") == ("Green Mushroom Cap", GREEN_CAP)
    assert tr.resolve("Blue Mushroom") == ("Blue Mushroom Cap", blue) and blue != "item/3285"
    assert tr.resolve("Green Mushroom Cap") == tr.resolve("green mushroom cap") == ("Green Mushroom Cap", GREEN_CAP)
    # no Cash item is a name a pickup message has: never one's key, by its own name or any read
    cash = lootlog.unpickable_keys(kb)
    assert set(LIVE_HATS) <= cash and len(cash) > 100 and GREEN_CAP not in cash
    assert not cash & {v for n, v in names.items() if not n.startswith("\0")}
    for key in sorted(cash)[::25] + sorted(LIVE_HATS):
        assert tr.resolve(kb.get(key)["name"])[1] not in cash, key


def test_names_tied_for_the_closest_are_no_guess_unless_one_is_a_drop():
    items = _items(item_1="Green Mushroom Cap", item_2="Green Mushroom Hat")
    assert lootlog.Tracker(items).resolve("Green Mushroom") == ("Green Mushroom", "")
    assert lootlog.Tracker(items, {"item/7"}).resolve("Green Mushroom") == ("Green Mushroom", "")
    assert lootlog.Tracker(items, {"item/2"}).resolve("Green Mushroom") == ("Green Mushroom Hat", "item/2")
    assert lootlog.Tracker(items, {"item/1", "item/2"}).resolve("Green Mushroom") == ("Green Mushroom", "")
    # the closest alone is taken, a drop or not; too far from any name, none
    assert lootlog.Tracker(items).resolve("Green Mushroom Ca") == ("Green Mushroom Cap", "item/1")
    assert lootlog.Tracker(items).resolve("Blue Snail Shell") == ("Blue Snail Shell", "")
    assert lootlog.Tracker(items).resolve("") == ("", "")
    # a pickup line read as the tie counts with the read name, no key (never another item's)
    tr = lootlog.Tracker(items)
    tr.read([("You received EXP (+30)", 128.0, 14.0)], 0.0)
    new = tr.read([("You received EXP (+30)", 100.0, 14.0), ("Green Mushroom x1 earned. (Etc)", 128.0, 14.0)], 0.5)
    assert [(e.kind, e.name, e.key) for e in new] == [("item", "Green Mushroom", "")]


def test_the_store_names_again_items_logged_as_one_no_pickup_names(isolated_store):
    """loot.json's logs and Recent logs' tops: the Cash hat a cut-off read was matched to becomes the cap."""
    tr = lootlog.Tracker(_items(item_360="Green Mushroom Cap", item_358="Leaf"), {GREEN_CAP})
    bad = {"item/3551"}
    lg = lootlog.Log(start=0.0, events=[lootlog.Event(1.0, "item", 1, "Green Mushroom Hat", "item/3551", saved=True),
                                         lootlog.Event(2.0, "item", 2, "Leaf", "item/358"),
                                         lootlog.Event(3.0, "exp", 5),
                                         lootlog.Event(4.0, "item", 1, "Mystery Hat", "item/3551")])
    lg.base["items"] = {"Green Mushroom Hat": [4, "item/3551"], "Green Mushroom Cap": [1, GREEN_CAP]}
    rec = {"start": 0.0, "seconds": 60, "exp": 0, "mesos": 0, "picked": 64, "value": 0,
           "top": [["Green Mushroom Hat", 59], ["Leaf", 3], ["Green Mushroom Cap", 2]]}
    lootlog.Store.path.write_text(json.dumps({"active": {"c1": lg.to_json()}, "recent": {"c1": [rec]}}),
                                  encoding="utf-8")
    assert lootlog.Store().repair(tr.resolve, bad) == 3     # an event, the older ones' totals, a top
    st = lootlog.Store()
    got = st.log("c1")
    assert [(e.name, e.key, e.saved) for e in got.events if e.kind == "item"] == [
        ("Green Mushroom Cap", GREEN_CAP, True), ("Leaf", "item/358", False),
        ("Mystery Hat", "item/3551", False)]                # (no item it reads as: kept as it was)
    assert got.totals()[2] == {"Green Mushroom Cap": [6, GREEN_CAP], "Leaf": [2, "item/358"],
                               "Mystery Hat": [1, "item/3551"]}
    assert st.recent("c1")[0]["top"] == [["Green Mushroom Cap", 61], ["Leaf", 3]]
    assert st.repair(tr.resolve, bad) == 0                  # nothing left to fix
