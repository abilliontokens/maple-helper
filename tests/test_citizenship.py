"""Tools > Citizenship (ui/citizenship.py): the town tabs (the class guide's town until one is picked, the pick saved
as the character's), open_with on a quest's own town (another quest: the Quests window), the one card under level 12,
the grade chips short and the done link over the cards, 40 cards and "Show more quests", Mark done / Back to the list,
the search, the town's clerk a tap away, the guide's reasons with the citizen grades and the towns standing out;
Hebrew mirrored; and the town's quests the window reads (quests.citizenship, town_of, the parse of their pages).
Ported from the old Play tools' town tests (test_farm, test_ux_tools, test_look_ux, test_tools_windows,
test_play_tools)."""
import re
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from maplehelper import buildplan, plan, quests
from maplehelper.i18n import I18n

REAL_KB = Path(__file__).resolve().parent.parent / "data" / "kb"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
# four citizenship quests' pages frozen as NiaMeowDB had them: the parser's exact checks don't follow the live KB
QUEST_FIXTURE = Path(__file__).parent / "fixtures" / "tst4b_quests"
OPENER = "quest/506000"          # To Henesys, the Prairie Town: a Henesys quest Henesys' Arthur hands out
MARKS = dict.fromkeys(map(ord, "\u2066\u2067\u2069\u200e\u200f\u202a\u202b\u202c\ufffc"), None) | {0xa0: " "}


def plain(text: str) -> str:
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
def make(qapp, real_kb, isolated_store):
    """make(base, job, level, lang, town): a character and the window over the game, shown, torn down after."""
    made = []

    def build(base="Thief", job="Assassin", level=30, lang="en", town=""):
        from maplehelper.ui.citizenship import Citizenship
        s = isolated_store.Settings()
        s["citizenship"] = True
        p = isolated_store.Profiles()
        c = p.add("Kiwi", base, job, level)
        c.town = town
        w = Citizenship(real_kb, s, p, I18n(lang))
        made.append(w)
        w.refresh()
        qapp.processEvents()
        return w, c
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
    from maplehelper.ui.toolwindow import NAV
    got = []
    slots = {"tool_requested": lambda key, arg: got.append(("tool", (key, arg))),
             "npc_requested": lambda k: got.append(("npc", k))}
    for name, slot in slots.items():
        getattr(NAV, name).connect(slot)
    yield got
    for name, slot in slots.items():
        getattr(NAV, name).disconnect(slot)


def lit(w) -> list[str]:
    return [card.key for card in w.cards() if card.property("lit")]


def town_rows(kb, town: str, level: int, done=()) -> list[quests.Quest]:
    from maplehelper.ui.citizenship import grade
    return sorted(quests.citizenship(kb, town, level, list(done)), key=lambda q: (grade(q), -q.exp))


# ------------------------------------------------------------------ the towns

@needs_kb
def test_the_guides_town_until_one_is_picked_then_the_pick_is_saved(make, real_kb, isolated_store, nav):
    w, c = make("Warrior", "Fighter", 30)
    rec = buildplan.citizenship_advice(real_kb, "Warrior", "Fighter", "en")[0] or quests.TOWNS[0]
    assert w.tab == rec and c.town == ""
    assert [b.property("value") for b in w._tabs.group.buttons()] == list(quests.TOWNS)
    assert [x.key for x in w.cards()] == [q.key for q in town_rows(real_kb, rec, 30)][:40]
    other = next(t for t in quests.TOWNS if t != rec)
    w._tab_picked(other)
    assert w.tab == other and c.town == other and isolated_store.Profiles().active.town == other
    assert [x.key for x in w.cards()] == [q.key for q in town_rows(real_kb, other, 30)][:40]
    # where to sign up in the town picked: its clerk, a tap away (their page in the toolbar's search)
    sign = next(lb for lb in shown(w, QLabel) if "Sign up with" in plain(lb.text()))
    sign.linkActivated.emit(re.search(r"href='([^']+)'", sign.text()).group(1))
    assert nav[-1][0] == "npc" and real_kb.get(nav[-1][1])["category"] == "npc"


@needs_kb
def test_open_with_goes_to_the_quests_own_town(make, nav, isolated_store):
    """Kerning City's opener asks for "To Henesys" first: its jump went to the quests page, "not on your lists"."""
    w, c = make("Thief", "Thief", 15, town="Kerning City")
    assert w.tab == "Kerning City"
    w.open_with(OPENER)
    assert w.tab == "Henesys" and c.town == "Henesys" and isolated_store.Profiles().active.town == "Henesys"
    assert w.search.text() == "To Henesys, the Prairie Town" and lit(w) == [OPENER]
    w.open_with("quest/10115")                           # not a Citizenship quest: the Quests window on it
    assert nav[-1] == ("tool", ("quest_tool", "quest/10115"))


@needs_kb
def test_under_level_12_one_card_says_when_it_opens(make):
    """TL2-12 / TOOL-18: "0 Henesys quests you can do now" stood above "Citizenship opens at Lv. 12", and a town to
    pick asked for a choice that can't be made yet."""
    w, c = make("Beginner", "Beginner", 1, lang="he")
    assert w._tabs.isHidden() and w.search.isHidden()
    body = [w.body.itemAt(i).widget() for i in range(w.body.count())]
    assert len(body) == 1 and "12" in texts(body[0]) and "11" in texts(body[0])
    c.level = 20
    w.character_changed()
    assert not w._tabs.isHidden() and not w.search.isHidden() and w.cards()


# ------------------------------------------------------------------ the list

@needs_kb
def test_grade_chips_are_short_and_the_done_link_is_over_the_cards(make):
    """TOOL-16 (three rows of "Citizenship grade N" chips) and TOOL-10 (the done toggle out of reach under 38
    cards)."""
    w, _ = make("Bowman", "Hunter", 50, town="Henesys")
    w.mark_done([next(x.key for x in w.cards() if not x.earlier())])
    chips = [plain(b.text()) for b in shown(w, QPushButton, "LevelChip")]
    assert chips and not any("Citizenship" in x for x in chips) and any(x.endswith("Grade 1") for x in chips)
    body = [w.body.itemAt(i).widget() for i in range(w.body.count())]
    link = next(i for i, x in enumerate(body) if isinstance(x, QPushButton) and x.property("done_link"))
    assert link < next(i for i, x in enumerate(body) if x in w.cards())
    grade = next(b for b in shown(w, QPushButton, "LevelChip") if plain(b.text()) == "Grade 1")
    grade.click()
    assert {x.q.grade[1] for x in w.cards()} == {1}


@needs_kb
def test_a_list_past_40_has_more(make, real_kb):
    w, _ = make("Bowman", "Hunter", 50, town="Henesys")
    rows = town_rows(real_kb, "Henesys", 50)
    assert len(rows) > 40 and len(w.cards()) == 40
    buttons(w, "Show more quests")[0].click()
    assert len(w.cards()) == len(rows) and not buttons(w, "Show more quests")


@needs_kb
def test_mark_done_there_and_back_to_the_list(make, isolated_store):
    w, c = make("Bowman", "Hunter", 50, town="Henesys")
    card = next(x for x in w.cards() if not x.earlier())
    key = card.key
    card.act.click()
    assert c.quests_done == [key] and isolated_store.Profiles().active.quests_done == [key]
    assert key not in [x.key for x in w.cards()]
    buttons(w, "Show quests marked done (1)")[0].click()
    done = [x for x in w.cards() if x.done]
    assert [x.key for x in done] == [key]
    done[0].act.click()
    assert c.quests_done == [] and isolated_store.Profiles().active.quests_done == []
    assert key in [x.key for x in w.cards()]


@needs_kb
def test_the_search_finds_the_towns_quests(make, real_kb):
    w, _ = make("Bowman", "Hunter", 50, town="Henesys")
    rows = town_rows(real_kb, "Henesys", 50)
    target = rows[1]
    w.search.setText(target.name)
    w._searched()
    keys = [x.key for x in w.cards()]
    assert target.key in keys and len(keys) == min(40, sum(1 for q in rows if q.matches(target.name)))
    w.search.setText("zzzz-no-such-quest")
    w._searched()
    assert not w.cards() and "No quest like that" in texts(w)


# ------------------------------------------------------------------ the guide's advice

def test_the_grades_and_towns_stand_out_in_the_advice():
    from maplehelper.ui.citizenship import bold_names
    assert bold_names("Helpful Stranger unlocks it in Kerning City.") == \
        "**Helpful Stranger** unlocks it in **Kerning City**."
    assert bold_names("**Henesys** stays") == "**Henesys** stays"          # once


@needs_kb
def test_why_the_guides_town_lists_its_reasons(make, real_kb):
    w, _ = make("Thief", "Assassin", 30)
    rec = buildplan.citizenship_advice(real_kb, "Thief", "Assassin", "en")[0]
    if rec is None:
        pytest.skip("the class guide names no citizenship town tonight")
    why = buttons(w, f"Why {rec}? ▾")
    assert why
    why[0].click()
    reasons = [lb for lb in shown(w, QLabel, "Detail") if "•" in plain(lb.text())]
    assert reasons and "<b>" in reasons[0].text()
    assert buttons(w, f"Why {rec}? ▴")


@needs_kb
def test_hebrew_is_mirrored_with_the_towns_in_english(make):
    w, _ = make("Thief", "Assassin", 30, lang="he")
    assert w.layoutDirection() == Qt.RightToLeft
    assert {plain(b.text()) for b in w._tabs.group.buttons()} == set(quests.TOWNS)
    assert all(card.layoutDirection() == Qt.RightToLeft for card in w.cards())


# ------------------------------------------------------------------ the town's quests (quests.py)

@needs_kb
def test_citizenship_town_and_quests(real_kb):
    # the town each class guide advises (Henesys for a Warrior, Kerning City for a Thief tonight): a citizenship
    # town, named in that guide
    for base, job in (("Warrior", "Fighter"), ("Thief", "Assassin")):
        town = buildplan.citizenship_advice(real_kb, base, job, "en")[0]
        assert town in quests.TOWNS and town in real_kb.page(plan.class_guide(real_kb, base, base))
    rows = quests.citizenship(real_kb, "Henesys", 30)
    assert rows and all(quests.town_of(real_kb, q) == "Henesys" and q.level <= 30 for q in rows)
    assert all(q.level <= 11 for q in quests.citizenship(real_kb, "Henesys", 11))


@needs_kb
def test_a_quest_says_how_you_get_it_and_what_to_do(real_kb):
    # a citizenship quest with no NPC and nothing to bring said nothing about how to do it (the owner)
    q = quests.quest(real_kb, OPENER)
    assert q.self_start and q.task and quests.town_of(real_kb, q) == "Henesys"
    rina = quests.quest(real_kb, "quest/506001")
    # the journal line as tonight's page has it (the exact sentence: test_quest_lines_parse_from_a_frozen_page)
    assert not rina.self_start and rina.task and rina.task in real_kb.page("quest/506001")


def test_quest_lines_parse_from_a_frozen_page(tmp_path):
    """The exact parse of four citizenship quests, on pages frozen as NiaMeowDB had them (the real-KB tests check
    the same things as invariants, so a rewritten page or a new quest doesn't hold a night's KB back)."""
    from maplehelper.kb import KnowledgeBase
    shutil.copytree(QUEST_FIXTURE, tmp_path / "kb")
    kb = KnowledgeBase(tmp_path / "kb")
    opener, rina, daily, kerning = (quests.quest(kb, f"quest/{n}") for n in (506000, 506001, 506002, 506100))
    assert opener.self_start and "Henesys" in opener.task and quests.town_of(kb, opener) == "Henesys"
    assert opener.turn_in == ""
    assert not rina.self_start and "greet Rina" in rina.task and not rina.task.startswith(("⌄", "02"))
    assert quests.task_text(rina, "en") == rina.task
    he = quests.task_text(rina, "he", kb)
    assert "Rina" in he and "ביקש" in he
    assert kerning.npc == "Arthur" and kerning.turn_in == "Roxy"
    # "Asking After Rina" is daily; "First Greeting with Rina", tagged Daily too, is what it asks for first: once
    assert daily.cycle == "daily" and rina.cycle == ""


@needs_kb
def test_a_quest_says_who_it_is_finished_with(real_kb):
    # the opener starts on its own and ends with Arthur; Kerning City's starts with Arthur and ends with Roxy (exact:
    # test_quest_lines_parse_from_a_frozen_page). On tonight's pages: every "Turn in:" the head names is read
    ends = 0
    for k, e in real_kb.entities.items():
        if e.get("category") != "quest" or not (q := quests.quest(real_kb, k)):
            continue
        head = real_kb.page(k).split("Pre-requisites")[0]
        if "Turn in: " in head:
            assert q.turn_in and f"Turn in: {q.turn_in}" in head, k
            ends += 1
    assert ends >= 10
    kerning = quests.quest(real_kb, "quest/506100")
    assert kerning.npc and kerning.turn_in and kerning.turn_in != kerning.npc


@needs_kb
def test_a_daily_quest_comes_back_after_the_reset(real_kb):
    # 71 of the 88 citizenship quests are daily or weekly: marked done they left the list for good
    daily = next(k for k, e in real_kb.entities.items() if e.get("category") == "quest"
                 and (q := quests.quest(real_kb, k)) and q.cycle == "daily")
    other = next(k for k, e in real_kb.entities.items() if e.get("category") == "quest" and k != daily
                 and (q := quests.quest(real_kb, k)) and not q.cycle)
    now = time.time()
    c = SimpleNamespace(quests_done=[daily, other], cycle_done={daily: now - 2 * 86400})
    assert quests.expire_cycles(real_kb, c) and c.quests_done == [other] and not c.cycle_done
    c = SimpleNamespace(quests_done=[daily], cycle_done={daily: now})
    assert not quests.expire_cycles(real_kb, c) and c.quests_done == [daily]
