"""Tools > Quests (ui/questtool.py) and the quest card it shares with Citizenship (ui/questcard.py): each tab's list
and its count, 40 cards at a time, a level's chip; the search through every quest; open_with on the tab a quest is on
(a Citizenship one: its own window); Mark done / Back to the list saved, and the offer to mark a step's earlier
steps; a card's chain strip opening its line, a step opening its quest; the Chains tab, started lines first with the
next step's card; what a card says (prerequisites a tap away, Fame and fee, gender rewards, droppers' levels in the
UI's words, the quest that hands a needed item over); daily quests back on open; Hebrew mirrored; and the lists the
window reads (quests.for_level and the parse under it). Ported from the old Play tools' quest tests (test_followup,
test_play_tools, test_tools_windows, test_ui_wording, test_farm)."""
import re
import time
import warnings
from pathlib import Path
from urllib.parse import quote

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QPushButton

from maplehelper import quests, translations
from maplehelper.i18n import I18n

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
LEVEL = 30
MAYA, DELIVERING, FIRST, SECOND = "quest/10106", "quest/10112", "quest/10115", "quest/10116"
# "Getting Arcon's Blood" asks for Arcon's Blood x 1; only "Arcon's Blood?" (Manji) hands it over
BLOOD_ASKS, BLOOD_GIVES, BLOOD, POTION = "quest/10110", "quest/10109", "item/448", "item/273"
MARKS = dict.fromkeys(map(ord, "\u2066\u2067\u2069\u200e\u200f\u202a\u202b\u202c\ufffc"), None) | {0xa0: " "}


def plain(text: str) -> str:
    """A label's words as read: its markup out, the direction marks and pictures aside, no-break spaces plain."""
    doc = QTextDocument()
    doc.setHtml(text)
    return doc.toPlainText().translate(MARKS)


def shown(w, cls, name: str | None = None) -> list:
    """The widgets of a kind (and objectName) showing in w: the loop's next turn first, as widgets added to a window
    that shows already show then (Qt queues it); the ones of the fill before are hidden, gone later."""
    QApplication.processEvents()
    return [x for x in (w.findChildren(cls, name) if name else w.findChildren(cls)) if x.isVisibleTo(w)]


def texts(w) -> str:
    return "\n".join(plain(lb.text()) for lb in shown(w, QLabel))


def buttons(w, text: str) -> list[QPushButton]:
    return [b for b in shown(w, QPushButton) if plain(b.text()).strip() == text]


@pytest.fixture(scope="module")
def real_kb():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(isolated_store):
    s = isolated_store.Settings()
    s["quest_tool"] = True
    return s


@pytest.fixture
def profiles(isolated_store):
    p = isolated_store.Profiles()
    p.add("Kiwi", "Thief", "Assassin", LEVEL)
    return p


@pytest.fixture
def make(qapp, real_kb, settings, profiles):
    """make(lang): the window over the game, shown, torn down after."""
    made = []

    def build(lang="en"):
        from maplehelper.ui.questtool import QuestTool
        w = QuestTool(real_kb, settings, profiles, I18n(lang))
        made.append(w)
        w.refresh()
        qapp.processEvents()
        return w
    yield build
    for w in made:
        w._search_timer.stop()
        w._geom.stop()
        w.hide()
        w.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def nav():
    """What the windows asked the app for: (signal, its arguments) in order."""
    from maplehelper.ui.toolwindow import NAV
    got = []
    slots = {"tool_requested": lambda key, arg: got.append(("tool", (key, arg))),
             "ask_requested": lambda q: got.append(("ask", q)),
             "npc_requested": lambda k: got.append(("npc", k)),
             "monster_requested": lambda k: got.append(("monster", k)),
             "item_requested": lambda k: got.append(("item", k))}
    for name, slot in slots.items():
        getattr(NAV, name).connect(slot)
    yield got
    for name, slot in slots.items():
        getattr(NAV, name).disconnect(slot)


def lists(kb, c) -> dict:
    return quests.for_level(kb, c.level, c.base_class, c.job, c.quests_done, crafts=c.crafts or None)


def lit(w) -> list[str]:
    return [card.key for card in w.cards() if card.property("lit")]


# ------------------------------------------------------------------ the tabs

@needs_kb
def test_each_tab_counts_its_list_and_shows_it(make, qapp, real_kb):
    w = make()
    w.resize(600, w.height())               # room for every count
    qapp.processEvents()
    r = lists(real_kb, w.character)
    words = [plain(b.text()) for b in w._tabs.group.buttons()]
    assert words[0].startswith("Lv. 30")
    for i, mode in enumerate(("level", "missed", "soon", "later")):
        assert w._counts[mode] == len(r[mode]) and words[i].endswith(f"· {len(r[mode])}")
    chains = quests.chains_for(real_kb, LEVEL, "Thief", "Assassin", [])
    assert w._counts["chains"] == len(chains["progress"]) + len(chains["start"])
    assert [c.key for c in w.cards()] == [q.key for q in r["level"][:40]]
    # dragged narrow, the tabs keep their words and drop the counts (the heads still count)
    w.resize(w.minimumWidth(), w.height())
    qapp.processEvents()
    assert not any("·" in b.text() for b in w._tabs.group.buttons())


@needs_kb
def test_a_list_past_40_says_so_and_shows_the_rest(make, qapp, real_kb):
    """The header counted every quest but only 40 cards were made, with nothing saying the rest were hidden."""
    w = make()
    w._tab_picked("missed")
    rows = lists(real_kb, w.character)["missed"]
    assert len(rows) > 40 and len(w.cards()) == 40
    assert f"Showing 40 of {len(rows)} quests" in texts(w)
    buttons(w, "Show more quests")[0].click()
    assert len(w.cards()) == min(len(rows), 80)
    w._tab_picked("later")
    w._tab_picked("missed")                 # another list: its first 40 again
    assert len(w.cards()) == 40


@needs_kb
def test_a_levels_chip_shows_that_levels_quests(make, real_kb):
    w = make()
    w._tab_picked("missed")
    rows = lists(real_kb, w.character)["missed"]
    chips = shown(w, QPushButton, "LevelChip")
    assert plain(chips[0].text()) == "All levels" and chips[0].isChecked()
    chips[1].click()                         # the newest skipped level
    picked = rows[0].opens_at()
    assert {c.q.opens_at() for c in w.cards()} == {picked}
    assert len(w.cards()) == min(40, sum(1 for q in rows if q.opens_at() == picked))
    assert f"from level {picked}" in texts(w)
    w._tab_picked("later")
    assert w._level_pick is None             # another tab: every level


# ------------------------------------------------------------------ the search

@needs_kb
def test_the_search_looks_through_every_quest(make, real_kb, nav):
    w = make()                              # on the level's own tab
    assert w.search.accessibleName() == I18n("en")("q_search")        # a name for screen readers
    r = lists(real_kb, w.character)
    later = r["later"][0]
    w.search.setText(later.name)
    w._searched()
    assert later.key in [c.key for c in w.cards()]
    assert f"{plain(w.t('q_later')).upper()} · " in texts(w)       # under its tab's name
    # a Citizenship quest: a row that opens its window
    w.search.setText("To Henesys, the Prairie Town")
    w._searched()
    buttons(w, "Show in Citizenship")[0].click()
    assert ("tool", ("citizenship", "quest/506000")) in nav
    w.search.setText("zzzz-no-such-quest")
    w._searched()
    assert not w.cards() and "No quest like that" in texts(w)
    w.search.clear()
    w._searched()
    assert [c.key for c in w.cards()] == [q.key for q in r["level"][:40]]


# ------------------------------------------------------------------ open_with

@needs_kb
def test_open_with_shows_the_quest_on_its_tab_lit(make, real_kb, nav):
    w = make()
    r = lists(real_kb, w.character)
    for tab in ("later", "missed", "soon", "level"):
        if r[tab]:
            q = r[tab][-1]                   # the last of a long list: the cards go on until it
            w.open_with(q.key)
            assert w.tab == tab and lit(w) == [q.key]
            assert not w.search.text()
    w.open_with("quest/506000")              # a Citizenship quest: the Citizenship window on it
    assert nav[-1] == ("tool", ("citizenship", "quest/506000"))
    # marked done: the search shows it among the ones marked done
    w.character.quests_done.append(r["later"][0].key)
    w.open_with(r["later"][0].key)
    card = next(c for c in w.cards() if c.key == r["later"][0].key)
    assert card.done and card.property("lit")


# ------------------------------------------------------------------ Mark done, Back to the list

@needs_kb
def test_mark_done_and_back_are_saved(make, real_kb, isolated_store):
    w = make()
    c = w.character
    q = next(q for q in lists(real_kb, c)["level"] + lists(real_kb, c)["missed"]
             if not quests.earlier_steps(real_kb, q.key))
    c.active_quests = [q.name.lower(), "Another Quest"]
    w.open_with(q.key)
    card = next(x for x in w.cards() if x.key == q.key)
    assert plain(card.act.text()) == "Mark done"
    card.act.click()
    assert c.quests_done == [q.key] and isolated_store.Profiles().active.quests_done == [q.key]
    assert c.active_quests == ["Another Quest"]          # done here is done for the chat too
    assert q.key not in [x.key for x in w.cards() if not x.done]
    link = buttons(w, "Show quests marked done (1)")
    assert link
    link[0].click()
    done = [x for x in w.cards() if x.done]
    assert [x.key for x in done] == [q.key] and plain(done[0].act.text()) == "Back to the list"
    done[0].act.click()
    assert c.quests_done == [] and isolated_store.Profiles().active.quests_done == []
    assert not buttons(w, "Hide quests marked done") and not w.show_done
    w.mark_done([q.key])                     # the next one marked doesn't open the list on its own
    assert not [x for x in w.cards() if x.done]


@needs_kb
def test_marking_a_step_offers_its_earlier_steps(make, real_kb, isolated_store):
    w = make()
    c = w.character
    w.open_with(FIRST)
    card = next(x for x in w.cards() if x.key == FIRST)
    card.act.click()
    assert card.offer is not None and c.quests_done == []          # asked first, nothing marked yet
    assert "Also mark the 7 quests before it?" in texts(card.offer)
    buttons(card.offer, "Mark all 8 done")[0].click()
    line = quests.chain_of(real_kb, FIRST).line(FIRST)[:8]
    assert set(c.quests_done) == set(line) and c.quests_done[-1] == FIRST          # the newest last
    assert set(isolated_store.Profiles().active.quests_done) == set(line)
    for k in list(c.quests_done):
        w.unmark(k)
    w.open_with(FIRST)
    card = next(x for x in w.cards() if x.key == FIRST)
    card.act.click()
    buttons(card.offer, "Only this one")[0].click()
    assert c.quests_done == [FIRST]


# ------------------------------------------------------------------ chains

@needs_kb
def test_a_cards_strip_opens_its_line_and_a_step_opens_its_quest(make, qapp, real_kb):
    w = make()
    w.open_with(FIRST)
    card = next(x for x in w.cards() if x.key == FIRST)
    strip = plain(card.strip.findChild(QLabel, "ChainNext").text())
    assert "Step 8 of 11" in strip and "Next: Maya's Second Collection" in strip
    assert card.chain_box is None
    card.strip.clicked.emit()
    dots = card.chain_box.findChildren(QLabel, "StepDot")
    assert card.chain_box.isVisibleTo(card) and len(dots) == len(card.chain)
    assert dots[0].property("state") == "open"           # Maya of Henesys, Lv. 21: to do now, nothing done yet
    assert {d.property("state") for d in dots[1:]} == {"locked"}
    w._refill()                                          # the line stays open when the window fills again
    card = next(x for x in w.cards() if x.key == FIRST)
    assert card.chain_box is not None and card.chain_box.isVisibleTo(card)
    first = next(lb for lb in card.chain_box.findChildren(QLabel, "StepName") if "Maya of Henesys" in plain(lb.text()))
    first.linkActivated.emit(re.search(r"href='([^']+)'", first.text()).group(1))
    assert w.tab == "missed" and lit(w) == [MAYA]        # Lv. 21: a skipped quest at 30


@needs_kb
def test_chains_tab_puts_started_lines_first_with_the_next_steps_card(make, real_kb):
    w = make()
    w.character.quests_done = [DELIVERING]
    w._tab_picked("chains")
    captions = [plain(lb.text()) for lb in shown(w, QLabel, "Caption")]
    assert captions[0].startswith("IN PROGRESS · ") and any(x.startswith("READY TO START · ") for x in captions)
    cards = [w.body.itemAt(i).widget() for i in range(w.body.count())]
    first = next(x for x in cards if x.property("chain"))
    assert first.property("chain") == MAYA
    bar = first.findChild(QProgressBar)
    assert (bar.value(), bar.maximum()) == (7, len(quests.chain_of(real_kb, MAYA, "Thief", "Assassin")))
    assert w.cards()[0].key == FIRST                      # the next step's whole card, inside its line's
    assert "7 of" in texts(first) and "EXP to go" in texts(first)
    # a line to start: its steps a tap away
    start = next(x for x in cards if x.property("chain") and not x.findChildren(QProgressBar))
    show = [b for b in start.findChildren(QPushButton) if plain(b.text()).startswith("Show all")]
    show[0].click()
    assert start.findChildren(QLabel, "StepDot")


# ------------------------------------------------------------------ what a card says

def test_a_card_says_fame_fee_other_lines_and_gender_rewards(qapp, kb, settings, profiles):
    from maplehelper.ui.questcard import QuestCard
    from maplehelper.ui.questtool import QuestTool
    w = QuestTool(kb, settings, profiles, I18n("en"))
    q = quests.Quest("quest/1", "Sauna Day", 20, min_fame=10, accept_cost=1000, notes=["Must not already have: X"],
                     gender_rewards={"Male": ["Blue Sauna Robe x 1"], "Female": ["Red Sauna Robe x 1"]})
    shown = texts(QuestCard(w, q))
    assert "Needs at least 10 Fame" in shown and "Costs 1,000 mesos to accept" in shown
    assert "Must not already have: X" in shown and "DEPENDS ON YOUR CHARACTER'S GENDER" in shown
    assert "Blue Sauna Robe x1 (male character)" in shown and "Red Sauna Robe x1 (female character)" in shown
    w.deleteLater()


@needs_kb
def test_a_prerequisite_is_a_tap_away_until_done(make, real_kb):
    """"Opens once you finish X": a tap shows X, on its own tab, lit (the owner); done, nothing left to say."""
    from maplehelper.ui.questcard import QuestCard
    w = make()

    def hint(card):
        return next((lb for lb in card.findChildren(QLabel) if "Opens once you finish" in plain(lb.text())), None)
    asks = hint(QuestCard(w, quests.quest(real_kb, SECOND)))
    assert asks is not None and "Maya's First Collection" in plain(asks.text())
    asks.linkActivated.emit(f"quest:{quote(FIRST)}")
    assert w.tab == "level" and lit(w) == [FIRST]
    w.character.quests_done.append(FIRST)
    assert hint(QuestCard(w, quests.quest(real_kb, SECOND))) is None


@needs_kb
@pytest.mark.parametrize("lang, word", [("he", "רמה "), ("en", "Lv. ")])
def test_droppers_say_the_level_in_the_uis_words(qapp, real_kb, settings, profiles, lang, word):
    """A quest's "where to get them" said "Snail (Lv. 1)" and "Arcforge Lv. 4" in the Hebrew UI (HEB-14)."""
    from maplehelper.ui.questcard import QuestCard
    from maplehelper.ui.questtool import QuestTool
    w = QuestTool(real_kb, settings, profiles, I18n(lang))
    card = QuestCard(w, quests.Quest("quest/x", "Test", 10, needs=["Snail Shell x 2",
                                                                   "Bottomwear HP Scroll: Lesser x 1"]))
    text = card._droppers.text()
    assert word in text and "Snail" in text and "Arcforge" in text
    if lang == "he":
        assert "Lv" not in text
    w.deleteLater()


@needs_kb
def test_an_item_only_a_quest_gives_names_that_quest_and_opens_it(make, real_kb):
    """The owner hunted Arcon's Blood as a drop: nothing drops it, "Arcon's Blood?" hands it over (QUEST-01)."""
    from maplehelper.ui.questcard import QuestCard
    w = make()
    card = QuestCard(w, quests.quest(real_kb, BLOOD_ASKS))
    text = plain(card._droppers.text())
    assert "Arcon's Blood?" in text and "Manji" in text and "You get it from the quest" in text
    card._droppers.linkActivated.emit(f"quest:{quote(BLOOD_GIVES)}")
    assert lit(w) == [BLOOD_GIVES]


@needs_kb
def test_a_plain_drop_says_nothing_about_quests(make, real_kb):
    """Squishy Liquid is a drop: the item keeps its droppers and gets no quest line, and no empty row either."""
    from maplehelper.ui.questcard import QuestCard
    w = make()
    card = QuestCard(w, quests.Quest("quest/x", "Test", 10, needs=["Squishy Liquid x 30"]))
    text = plain(card._droppers.text())
    assert "Squishy Liquid" in text and "quest" not in text.lower()
    assert not quests.item_givers(real_kb, "item/353", BLOOD_ASKS)


@needs_kb
def test_the_giver_on_the_same_line_comes_first(real_kb):
    """Dozens of quests hand out Blue Potion; the one named is the step of this quest's own line."""
    givers = quests.item_givers(real_kb, POTION, BLOOD_ASKS)
    assert len(givers) > 1 and givers[0] == BLOOD_GIVES and BLOOD_ASKS not in givers
    assert quests.item_givers(real_kb, BLOOD, BLOOD_ASKS) == [BLOOD_GIVES]


@needs_kb
def test_daily_quests_come_back_when_the_window_opens(make, real_kb, profiles, isolated_store):
    daily = next(k for k, e in real_kb.entities.items() if e.get("category") == "quest"
                 and (q := quests.quest(real_kb, k)) and q.cycle == "daily")
    c = profiles.active
    c.quests_done, c.cycle_done = [daily], {daily: time.time() - 3 * 86400}
    profiles.save()
    make()
    assert c.quests_done == [] and isolated_store.Profiles().active.quests_done == []


@needs_kb
def test_hebrew_is_mirrored(make):
    w = make("he")
    assert w.layoutDirection() == Qt.RightToLeft
    assert "רמה 30" in plain(w._tabs.group.buttons()[0].text())
    assert w.search.placeholderText().strip("\u200f").startswith("חיפוש קווסט")
    assert all(card.layoutDirection() == Qt.RightToLeft for card in w.cards())


# ------------------------------------------------------------------ the lists it reads (quests.py)

@needs_kb
def test_quests_for_a_level(real_kb):
    r = quests.for_level(real_kb, 22, "Warrior", "Warrior", [])
    assert r["now"] and all(q.level <= 22 for q in r["now"]) and all(q.area != "Citizenship" for q in r["now"])
    assert r["now"] == sorted(r["now"], key=lambda q: (-q.exp, q.level))
    first = r["now"][0].key
    assert first not in [q.key for q in quests.for_level(real_kb, 22, "Warrior", "Warrior", [first])["now"]]
    mai = next(quests.quest(real_kb, k) for k, e in real_kb.entities.items() if e["name"] == "Mai's Training")
    # its level is the page's own, a Beginner's quest, asking "<monster or item> x N"
    assert mai.level == real_kb.get(mai.key)["props"].get("Minimum Level", 1) and "Beginner" in mai.job
    assert mai.needs and all(re.search(r" x \d+$", n) for n in mai.needs)


def test_quest_matches_name_npc_and_what_it_asks():
    q = quests.Quest(key="quest/1", name="Pio's Collecting Recycled Goods", level=10, npc="Pio", area="Lith Harbor",
                     needs=["Green Mushroom Cap x 20"], rewards=["Red Potion x 20"])
    assert q.matches("pio") and q.matches("mushroom cap") and q.matches("red potion") and q.matches("LITH")
    assert not q.matches("mushroom snail")


def test_quest_item_names_with_a_lowercase_x():
    found = quests._ITEM.findall("Defeat Dark Axe Stump x 100 Defeat Drake x 50 Moon Rock x 1")
    assert found == [("Defeat Dark Axe Stump", "100"), ("Defeat Drake", "50"), ("Moon Rock", "1")]
    assert quests._ITEM.findall("Dexterity Potion x 5 Blue Potion x 30") == [("Dexterity Potion", "5"),
                                                                             ("Blue Potion", "30")]
    assert quests._ITEM.findall("Elixir x 15 Bottomwear HP Scroll: Greater x 1")[1] == ("Bottomwear HP Scroll: Greater", "1")


def test_maple_island_quests_leave_once_a_job_is_taken():
    """Maple Island is behind a one-way boat: its quests show for a Beginner, not for a Lv. 31 Assassin."""
    q = quests.Quest(key="quest/x", name="Bringing a Mirror to Heena", level=1, area="Maple Island")
    assert quests.job_fits(q, "Beginner", "Beginner") and not quests.job_fits(q, "Thief", "Assassin")
    assert quests.job_fits(quests.Quest(key="quest/y", name="Y", level=1, area="Victoria Island"), "Thief", "Assassin")


@needs_kb
def test_class_specific_rewards_follow_the_class(real_kb):
    # every quest with class-specific choices (Welcome to the Hollow's scrolls): a class gets its own set and the
    # "Any Class" ones, never another class's, and the choices aren't also promised as sure rewards
    picky = [q for q in (quests.quest(real_kb, k) for k, e in real_kb.entities.items() if e["category"] == "quest")
             if q and q.class_rewards]
    assert picky
    for q in picky:
        for cls in ("Warrior", "Magician", "Bowman", "Thief", "Beginner"):
            assert q.rewards_pick(cls) == q._for_class(q.class_rewards, cls), q.key
            others = {x for c, xs in q.class_rewards.items() if c not in (cls, "Any Class") for x in xs}
            own = set(q.class_rewards.get(cls, [])) | set(q.class_rewards.get("Any Class", []))
            assert not (set(q.rewards_pick(cls)) & (others - own)), (q.key, cls)
        assert not set(q.rewards) & {x for xs in q.class_rewards.values() for x in xs}, q.key


def test_the_later_tab_says_which_areas_are_not_open_yet(kb):
    """Quests in an area the KB doesn't confirm are hidden: the "later" tab names those areas, and the note goes
    once every area is open (the owner)."""
    assert all("event" not in a.lower() for a in quests.closed_areas(kb))


def test_a_done_daily_or_weekly_quest_comes_back_without_an_invented_reset():
    # the KB names no reset time (the owner: don't make things up): a daily one is back the next calendar day,
    # a weekly one seven days after it was marked
    from datetime import datetime
    done = datetime(2026, 10, 3, 15, 30).timestamp()
    assert quests.back_at("daily", done) == datetime(2026, 10, 4).timestamp()
    assert quests.back_at("weekly", done) == done + 7 * 86400


@needs_kb
def test_what_to_do_reads_in_hebrew(real_kb):
    # the quest journal showed in English in the Hebrew app (the owner): every line has its Hebrew
    talk = [q for k, e in real_kb.entities.items() if e.get("category") == "quest"
            for q in [quests.quest(real_kb, k)] if q and q.task and not q.needs]
    assert talk and not [q.key for q in talk if q.task.startswith(("⌄", "02"))]       # the page's markers are gone
    assert all(quests.task_text(q, "en") == q.task for q in talk)
    # a line NiaMeowDB wrote tonight may wait for the nightly's Hebrew (tools/translate_kb.py, capped, only warns):
    # reported, not a failed night. What has Hebrew must show it
    made = [q for q in talk if translations.he(real_kb.root, "quest_tasks", q.key, q.task)
            or quests.task_text(q, "he") != q.task]
    if len(made) < len(talk):
        warnings.warn(f"{len(talk) - len(made)} quest lines have no Hebrew yet: "
                      + ", ".join(q.key for q in talk if q not in made)[:300], stacklevel=2)
    assert made and all(re.search("[֐-׿]", quests.task_text(q, "he", real_kb)) for q in made)
