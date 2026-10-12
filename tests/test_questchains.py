"""Quest chains (quests.chain_of, progress, chains_for): the "Quest Complete X" prerequisites of the quest pages read
backwards as the game's questlines — each quest on the line of its deepest prerequisite, at the step its page says, a
line splitting where several quests follow one, two first steps sharing a line, a name two quests share resolved to
the asker's own town — and where a character stands on one: the steps done (marked, or before one marked), the ones
to do now, why the others wait, the EXP left; the earlier steps a step implies; Mark done's bookkeeping
(quests.mark_done / unmark). A tiny KB pins each shape; the real KB's Maya line and its pages' own "Questline · Step
N of M" check them on the game's data."""
import re
from pathlib import Path

import pytest

from maplehelper import availability, quests
from maplehelper.store import Character

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
MAYA_LINE = ["Maya of Henesys", "Finding Sophia", "Making a Sparkling Rock", "Arcon's Blood?", "Getting Arcon's Blood",
             "Making Sparkling Rock", "Delivering the Weird Medicine", "Maya's First Collection",
             "Maya's Second Collection", "Maya's Third Collection", "Maya's Last Collection"]
FIRST, DELIVERING, MAYA, SECOND, THIRD, LAST = ("quest/10115", "quest/10112", "quest/10106", "quest/10116",
                                               "quest/10117", "quest/10118")


class FakeKB:
    """Just enough of a KnowledgeBase for quests (hashable, like the real one: quests caches per KB); no release
    guide, so every quest counts as in the game."""

    def __init__(self, entities: dict, pages: dict):
        self.entities, self._pages, self._npc_by_name = entities, pages, {}

    def get(self, key):
        return self.entities.get(key)

    def page(self, key):
        return self._pages.get(key, "")


def make_kb(*rows) -> FakeKB:
    """(id, name, level, prerequisite names, extra pre-requisite lines, head lines): a quest each, 100 EXP a level."""
    entities, pages = {}, {}
    for n, name, level, after, extra, head in rows:
        key = f"quest/{n}"
        entities[key] = {"category": "quest", "name": name,
                         "props": {"Minimum Level": level, "Area": "Henesys", "EXP Reward": 100 * level}}
        pre = "".join(f"{x}\n" for x in extra) + "".join(f"Quest Complete {a}\n" for a in after)
        pages[key] = f"---\n{{}}\n---\n\n# {name}\n\n{head}Pre-requisites\nLevel Lv. {level}+\n{pre}Rewards\n1 EXP\n"
    return FakeKB(entities, pages)


def q(n, name, level, after=(), extra=(), head=""):
    return n, name, level, after, extra, head


@pytest.fixture(autouse=True)
def fresh_parse():
    """quests caches every page's parse by (KB, key): a tiny KB made later can reuse a gone one's id."""
    quests._quest.cache_clear()
    yield
    quests._quest.cache_clear()


def tree() -> FakeKB:
    """A -> B -> C -> E; B -> D (a split: C at level 12 before D at 15); E also asks X, a quest of no line."""
    return make_kb(q(1, "A", 10), q(2, "B", 10, ["A"]), q(3, "C", 12, ["B"]), q(4, "D", 15, ["B"]),
                   q(5, "E", 20, ["C", "X"]), q(6, "X", 10))


# ------------------------------------------------------------------ the lines, on a tiny KB

def test_a_quest_follows_its_deepest_prerequisite_and_a_line_splits():
    kb = tree()
    chain = quests.chain_of(kb, "quest/5")
    assert chain.root == "quest/1" and len(chain) == 5
    assert chain.line("quest/5") == ["quest/1", "quest/2", "quest/3", "quest/5"]
    assert chain.at("quest/5") == (4, 4) and chain.also["quest/5"] == ["quest/6"]
    # the line splits after B, the lower level first; B's own line ends there, each branch goes on alone
    assert chain.nexts["quest/2"] == ["quest/3", "quest/4"]
    assert chain.at("quest/2") == (2, 2) and chain.at("quest/4") == (3, 3) and chain.at("quest/3") == (3, 4)
    assert chain.branch("quest/2") == 0 and chain.branch("quest/3") == chain.branch("quest/4") == 1
    assert chain.before("quest/5") == ["quest/1", "quest/2", "quest/3"]
    assert chain.order == ["quest/1", "quest/2", "quest/3", "quest/5", "quest/4"]     # a line, then the next one
    # X opens E but starts no line: no chain of its own, what it opens is said instead
    assert quests.chain_of(kb, "quest/6") is None and quests.opens(kb, "quest/6") == ["quest/5"]
    assert quests.chain_of(kb, "quest/1").order == chain.order                       # one chain, from any step


def test_two_first_steps_open_one_line():
    """I Need to Find My Daughter 1 asks two first steps (pages/quest/10124.md): the second one is a first step of the
    same line ("Questline · Step 1 of 3" on both pages), not a quest of no line."""
    kb = make_kb(q(1, "P", 10), q(2, "Q", 10), q(3, "R", 11, ["P", "Q"]), q(4, "S", 11, ["R"]))
    chain = quests.chain_of(kb, "quest/2")
    assert chain.root == "quest/1" and chain.order == ["quest/1", "quest/2", "quest/3", "quest/4"]
    assert chain.at("quest/2") == chain.at("quest/1") == (1, 3)
    assert chain.prev["quest/3"] == "quest/1" and chain.also["quest/3"] == ["quest/2"]


def test_a_name_two_quests_share_is_the_askers_towns():
    """"Becoming a Citizen of Honor" is Henesys' and Kerning City's: each town's next quest asks its own."""
    kb = make_kb(q(1, "Becoming a Citizen of Honor", 57, extra=["Henesys: Citizenship grade 9"]),
                 q(2, "Becoming a Citizen of Honor", 57, extra=["Kerning City: Citizenship grade 9"]),
                 q(3, "A Box Hidden Long Ago", 57, ["Becoming a Citizen of Honor"], ["Henesys: Citizenship grade 9"]),
                 q(4, "A Missing Comrade", 57, ["Becoming a Citizen of Honor"],
                   ["Kerning City: Citizenship grade 9"]))
    assert quests.prerequisites(kb, "quest/3") == ["quest/1"]
    assert quests.prerequisites(kb, "quest/4") == ["quest/2"]


def test_names_match_as_the_required_list_does():
    """Spaces collapsed, the case and a closing period aside ("Asking After Mrs. Ming Ming, the Town Resident.")."""
    kb = make_kb(q(1, "Asking After Rina, the Town Resident.", 12),
                 q(2, "Rina's Errand", 12, ["asking after  Rina, the Town Resident"]))
    assert quests.prerequisites(kb, "quest/2") == ["quest/1"]
    assert quests.chain_of(kb, "quest/2").at("quest/2") == (2, 2)


def test_a_step_for_another_job_ends_its_line():
    kb = make_kb(q(1, "A", 10), q(2, "B", 10, ["A"]), q(3, "C", 12, ["B"], ["Job Warrior"]), q(4, "D", 15, ["C"]),
                 q(5, "E", 15, ["B"]))
    thief = quests.chain_of(kb, "quest/2", "Thief", "Assassin")
    assert thief.order == ["quest/1", "quest/2", "quest/5"] and thief.at("quest/2") == (2, 3)
    assert quests.chain_of(kb, "quest/4", "Thief", "Assassin") is None        # behind a Warrior's step
    assert len(quests.chain_of(kb, "quest/2", "Warrior", "Fighter")) == 5
    assert len(quests.chain_of(kb, "quest/2")) == 5                           # no class given: every class's


def test_a_loop_in_the_pages_ends():
    kb = make_kb(q(1, "A", 10, ["B"]), q(2, "B", 10, ["A"]), q(3, "C", 10, ["B"]))
    chain = quests.chain_of(kb, "quest/3")
    assert chain is None or "quest/3" in chain
    assert set(quests.earlier_steps(kb, "quest/3")) == {"quest/1", "quest/2"}


# ------------------------------------------------------------------ where a character stands

def test_progress_counts_the_steps_before_a_done_one_and_says_why():
    kb = tree()
    chain = quests.chain_of(kb, "quest/5")
    s = quests.progress(kb, chain, 12, ["quest/3"])
    assert s.done == {"quest/1", "quest/2", "quest/3"} and s.status == "progress"      # A, B: before C, so done
    assert s.open == [] and s.state("quest/4") == "locked" and s.why["quest/4"] == [("level", 15)]
    assert s.why["quest/5"] == [("level", 20), ("after", "quest/6")]
    assert s.next == "quest/5" and s.exp_left == 2000 + 1500
    s = quests.progress(kb, chain, 30, ["quest/3", "quest/6"])
    assert s.open == ["quest/5", "quest/4"] and s.next == "quest/5"
    s = quests.progress(kb, chain, 30, ["quest/5", "quest/4"])
    assert s.status == "done" and s.exp_left == 0 and s.next == ""
    s = quests.progress(kb, chain, 30, [])
    assert s.status == "start" and s.open == ["quest/1"]
    assert quests.progress(kb, chain, 5, []).status == "later"
    assert quests.done_with_earlier(kb, ["quest/5"]) == {"quest/1", "quest/2", "quest/3", "quest/5", "quest/6"}
    assert quests.earlier_steps(kb, "quest/5") == ["quest/1", "quest/6", "quest/2", "quest/3"]   # the first first


def test_a_profession_step_waits_for_its_level_when_the_player_set_it():
    kb = make_kb(q(1, "A", 10), q(2, "B", 10, ["A"], ["Profession Smithing Lv. 5+"]))
    chain = quests.chain_of(kb, "quest/2")
    assert quests.progress(kb, chain, 30, ["quest/1"], {"smithing": 3}).why["quest/2"] == [("profession",
                                                                                             ("Smithing", 5))]
    assert quests.progress(kb, chain, 30, ["quest/1"], {"smithing": 5}).open == ["quest/2"]
    assert quests.progress(kb, chain, 30, ["quest/1"], None).open == ["quest/2"]     # not set: shown, labelled


def test_mark_done_and_unmark_keep_the_characters_lists():
    kb = make_kb(q(7, "Daily Thing", 10, head="Daily\n"), q(8, "Once", 10))
    c = Character("1", "Kiwi", "Thief", "Assassin", 30)
    c.active_quests = ["daily  thing", "Another"]
    assert quests.mark_done(kb, c, ["quest/7", "quest/8", "quest/7"], now=100.0) == ["quest/7", "quest/8"]
    assert c.quests_done == ["quest/7", "quest/8"] and c.cycle_done == {"quest/7": 100.0}
    assert c.active_quests == ["Another"]                     # done here is done for the chat too
    assert quests.unmark(c, "quest/7") and c.quests_done == ["quest/8"] and c.cycle_done == {}
    assert not quests.unmark(c, "quest/7")


# ------------------------------------------------------------------ the real KB

@pytest.fixture(scope="module")
def real():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


@needs_kb
def test_mayas_line_in_order_with_its_split(real):
    """Maya's First Collection: "Questline · Step 8 of 11", the line splitting after Delivering the Weird Medicine
    (pages/quest/10115.md)."""
    chain = quests.chain_of(real, FIRST)
    assert chain.root == MAYA
    assert [real.get(k)["name"] for k in chain.line(FIRST)] == MAYA_LINE
    assert chain.at(FIRST) == (8, 11) and chain.branch(FIRST) == 1
    assert chain.at(DELIVERING) == (7, 7) and FIRST in chain.nexts[DELIVERING] and len(chain.nexts[DELIVERING]) >= 2
    assert chain.nexts[FIRST] == [SECOND] and chain.at(LAST) == (11, 11)
    assert quests.earlier_steps(real, FIRST)[:7] == chain.before(FIRST)[:7] == chain.line(FIRST)[:7]
    # only quests the KB confirms are in the game
    open_ = availability.of(real)
    assert all(open_.quest_open(k) for k in chain.order)


@needs_kb
def test_every_questline_page_agrees_with_its_chain(real):
    """Each page's own "Questline · Step N of M" is the chain's step and its line's length (all of them on the KB of
    the day this was written; a rewritten page or a new quest of an odd shape doesn't hold a night's KB back)."""
    open_ = availability.of(real)
    agree, differ = 0, []
    for k, e in real.entities.items():
        if e.get("category") != "quest" or not open_.quest_open(k):
            continue
        m = next((m for ln in real.page(k).splitlines() if (m := re.match(r"Questline · Step (\d+) of (\d+)",
                                                                          ln.strip()))), None)
        if not m:
            continue
        chain = quests.chain_of(real, k)
        if chain is not None and chain.at(k) == (int(m.group(1)), int(m.group(2))):
            agree += 1
        else:
            differ.append((k, m.group(0), chain.at(k) if chain else None))
    assert agree > 100 and len(differ) <= agree // 20, differ[:10]


@needs_kb
def test_the_next_step_after_marking_one_done(real):
    chain = quests.chain_of(real, FIRST, "Thief", "Assassin")
    s = quests.progress(real, chain, 30, [FIRST])
    assert set(chain.line(FIRST)[:8]) <= s.done                     # the steps before it count as done
    assert s.status == "progress" and s.next == SECOND and SECOND in s.open
    assert all(chain.prev[k] in s.done for k in s.open)            # a step to do now follows a done one
    assert all(s.why[k] for k in chain.order if s.state(k) == "locked")
    third = quests.quest(real, THIRD)
    assert ("after", SECOND) in s.why[THIRD]
    if third.opens_at() > 30:
        assert ("level", third.opens_at()) in s.why[THIRD]
    assert s.exp_left == sum(quests.quest(real, k).exp for k in chain.order if k not in s.done)
    s = quests.progress(real, chain, 200, [FIRST, SECOND, THIRD])
    assert LAST in s.open


@needs_kb
def test_chains_for_a_character_by_where_they_stand(real):
    def where(level, done):
        r = quests.chains_for(real, level, "Thief", "Assassin", done)
        return next(status for status, states in r.items() for s in states if s.chain.root == MAYA)
    assert where(30, []) == "start" and where(10, []) == "later" and where(30, [DELIVERING]) == "progress"
    r = quests.chains_for(real, 30, "Thief", "Assassin", [DELIVERING])
    maya = next(s for s in r["progress"] if s.chain.root == MAYA)
    assert maya.next == FIRST and len(maya.done) == 7
    assert r["progress"][0].open                                    # one with a step to do now first
    starts = [quests.quest(real, s.chain.root).opens_at() for s in r["start"]]
    assert starts == sorted(starts, reverse=True)                   # the ones nearest the level first
    # the Citizenship board's own lines are the Citizenship window's
    roots = {s.chain.root for states in r.values() for s in states}
    assert all(quests.quest(real, k).area != "Citizenship" for k in roots)
    board = quests.chains_for(real, 30, "Thief", "Assassin", [], citizenship=True)
    assert all(quests.quest(real, s.chain.root).area == "Citizenship" for states in board.values() for s in states)
