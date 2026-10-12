"""The Build & Skills window over the game (ui/buildtool.py): its two tabs and open_with; the Build tab's plan (the SP
table's "Changed in COT2" chips, once each, their changes on hover; the community tier card; the gear's items opening
their page, the full guide; a Beginner's way on); the Skills tab (a pick of class line and, in it, of job up to the
2nd, each skill with its picture, name, description, max level, prerequisite and its level 1 and max level effects, in
Hebrew from assets/skills/he.json, then the nightly's kind "skill_desc"), the job picked in each class line kept;
Hebrew mirrored; the white glass's colours in the rich text."""
import html
import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import unquote

import pytest
from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from maplehelper import skillbook, translations
from maplehelper.i18n import I18n

ROOT = Path(__file__).resolve().parent.parent
REAL_KB = ROOT / "data" / "kb"
FIXTURE_KB = Path(__file__).parent / "fixtures" / "kb"
MEOWDB = Path(__file__).parent / "fixtures" / "meowdb"
ASSET = ROOT / "assets" / "skills" / "he.json"
needs_kb = pytest.mark.skipif(not (REAL_KB / "index.json").exists(), reason="no real knowledge base")
SECOND = {"Warrior": ["Fighter", "Page", "Spearman"], "Magician": ["F/P Wizard", "I/L Wizard", "Cleric"],
          "Bowman": ["Hunter", "Crossbowman"], "Thief": ["Assassin", "Bandit"]}
THIRD = {"Crusader", "White Knight", "Dragon Knight", "F/P Mage", "I/L Mage", "Priest", "Ranger", "Sniper", "Hermit",
         "Chief Bandit"}


def bare(text: str) -> str:
    """A label's text without its direction marks (and the word joiner that keeps "\u05d1-" with what follows)."""
    return "".join(ch for ch in text if ch not in "\u200e\u200f\u202a\u202b\u202c\u2066\u2067\u2069\u2060")


def plain_text(label: QLabel) -> str:
    """A rich-text label's words, its tags (the "?" pictures among them) and direction marks aside."""
    from maplehelper import glossary
    text = html.unescape(re.sub(r"<[^>]+>", "", label.text().replace(glossary.MARK, "")))
    text = re.sub(r"\s+", " ", bare(text))
    return re.sub(r" ([.,;:])", r"\1", text).strip()          # (the "?" left its space before a comma)


def pump(ms=60):
    app = QApplication.instance()
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _dark_look():
    """Every test starts and ends on today's dark glass, whatever look a test picked (npcoverlay's module state)."""
    from maplehelper.ui import npcoverlay
    npcoverlay.apply_look(None)
    yield
    npcoverlay.apply_look(None)


@pytest.fixture(scope="module")
def real_kb():
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    from maplehelper.kb import KnowledgeBase
    return KnowledgeBase(REAL_KB)


@pytest.fixture
def opened(qapp, isolated_store):
    """make(kb, base, job, level, lang): the window shown for a character of that job (its setting on)."""
    from maplehelper.ui.buildtool import BuildTool
    made = []

    def make(kb, base="Thief", job="Assassin", level=35, lang="en"):
        settings = isolated_store.Settings()
        settings["build_tool"] = True
        profiles = isolated_store.Profiles()
        profiles.add("Kiwi", base, job, level)
        w = BuildTool(kb, settings, profiles, I18n(lang))
        made.append(w)
        w.refresh()
        pump()
        return w
    yield make
    for w in made:
        w.hide()
        w.deleteLater()
    QApplication.processEvents()


@pytest.fixture
def tool(opened, real_kb):
    return lambda *a, **k: opened(real_kb, *a, **k)


@pytest.fixture
def signals():
    """What the window asked of the app (toolwindow.NAV), by signal name; the connections undone after."""
    from maplehelper.ui.toolwindow import NAV
    got: dict[str, list] = {}
    made = []

    def catch(name: str):
        return lambda value: got.setdefault(name, []).append(value)
    for name in ("item_requested", "guide_requested", "ask_requested"):
        sig, slot = getattr(NAV, name), catch(name)
        sig.connect(slot)
        made.append((sig, slot))
    yield got
    for sig, slot in made:
        sig.disconnect(slot)


def tab_buttons(w):
    return w._tabs.group.buttons()


def skills_tab(w):
    tab_buttons(w)[1].click()
    pump()


def cards(w):
    return [c for c in w.findChildren(QFrame, "Card") if c.property("skill") and c.isVisibleTo(w)]


def job_buttons(w):
    return [b for b in w._picker.findChildren(QPushButton, "Segment") if b.isVisibleTo(w)]


# ------------------------------------------------------------------ the tabs and the skills (data)

def test_five_class_tabs_each_with_its_1st_and_2nd_jobs_and_no_3rd():
    tabs = skillbook.class_jobs()
    assert [c for c, _ in tabs] == ["Beginner", "Warrior", "Magician", "Bowman", "Thief"]
    jobs = dict(tabs)
    assert jobs["Beginner"] == ["Beginner"]
    assert jobs["Thief"] == ["Thief", "Assassin", "Bandit"]
    for cls, second in SECOND.items():
        assert jobs[cls] == [cls] + second
    assert not THIRD & {j for js in jobs.values() for j in js}


def test_the_tab_to_open_on_is_the_characters_own():
    assert skillbook.default_tab("Thief", "Assassin") == ("Thief", "Assassin")
    assert skillbook.default_tab("Magician", "Magician") == ("Magician", "Magician")
    assert skillbook.default_tab("Thief", "Hermit") == ("Thief", "Assassin")     # a later job: the 2nd it came from
    assert skillbook.default_tab("Bowman", "Beginner") == ("Beginner", "Beginner")
    assert skillbook.default_tab(None, None) == ("Beginner", "Beginner")


@needs_kb
def test_every_shown_job_has_its_skills_each_with_all_its_parts(real_kb):
    book = skillbook.book(real_kb)
    counts = {j: len(book[j]) for _, js in skillbook.class_jobs(real_kb) for j in js}
    assert counts["Beginner"] == 3 and counts["Thief"] == 6 and counts["Assassin"] == 6 and counts["Bandit"] == 6
    assert counts["Fighter"] == counts["Page"] == counts["Spearman"] == 8
    assert sum(counts.values()) == 93
    for job, skills in book.items():
        assert not THIRD & {job}
        for s in skills:
            assert s.job == job and s.name and s.desc and s.lv1 and s.max and s.max_lv
            assert s.picture and s.picture.exists() and "fallback" not in s.picture.parts, s.key
            props = real_kb.get(s.key)["props"]
            assert (s.prereq is not None) == bool(props.get("Prerequisite")), s.key
            assert s.desc in real_kb.page(s.key) and s.max in real_kb.page(s.key)
    haste = next(s for s in book["Assassin"] if s.name == "Claw Booster")
    assert haste.prereq == ("Claw Mastery", 5) and haste.max_lv == 20
    assert haste.lv1.startswith("HP -30, MP -30") and haste.max.startswith("HP -10, MP -10")


@needs_kb
def test_the_hebrew_asset_covers_every_shown_text_made_from_its_english(real_kb):
    from maplehelper.brain import _LEVEL_WORD
    from maplehelper.translations import made_from
    rows = json.loads(ASSET.read_text(encoding="utf-8"))
    shown = {k: en for skills in skillbook.book(real_kb).values() for s in skills
             for k, en in skillbook.texts(s).items()}
    assert len(shown) == 279 and set(shown) <= set(rows)       # (the rows of a skill NiaMeowDB re-keyed stay too)
    names = {s.name for skills in skillbook.book(real_kb).values() for s in skills}
    for key, en in shown.items():
        he = made_from(rows[key], en)      # the row's Hebrew, or the version made from this KB's English ("alt")
        assert he, key
        assert re.search(r"[א-ת]", he) and not _LEVEL_WORD.search(he), key
        assert sorted(re.findall(r"\d+", en)) == sorted(re.findall(r"\d+", he)), key     # numbers kept
        for name in names:          # a skill named in the English stays in English letters (one-word names
            if " " in name and re.search(rf"(?<![\w:]){re.escape(name)}(?![\w:])", en):    # are words too: "Focus to")
                assert name in he, (key, name)
        assert not re.search(r"(?:^|\s)[בהוכלמש]{1,2}[A-Za-z]", he), key        # a prefix takes a hyphen: "ב-Heal"
    # the app shows it, and only while the English holds
    s = next(s for s in skillbook.book(real_kb)["Assassin"] if s.name == "Haste")
    assert skillbook.text(real_kb, s, "desc", "he") == made_from(rows[s.key], s.desc)
    assert skillbook.text(real_kb, s, "max", "en") == s.max
    from dataclasses import replace
    rewritten = replace(s, desc=s.desc + " Now stronger.")
    assert skillbook.text(real_kb, rewritten, "desc", "he") == rewritten.desc


def test_the_nightlys_skill_text_is_read_and_the_asset_wins_from_the_same_english(tmp_path):
    (tmp_path / "he.json").write_text(json.dumps({"skill_desc": {
        "skill/x": {"en": "Hits hard.", "he": "מכה חזק."},
        "skill/assassin__haste": {"en": json.loads(ASSET.read_text(encoding="utf-8"))["skill/assassin__haste"]["en"],
                                  "he": "תרגום של הלילה"}}}, ensure_ascii=False), encoding="utf-8")
    assert translations.he(tmp_path, "skill_desc", "skill/x", "Hits hard.") == "מכה חזק."
    assert translations.he(tmp_path, "skill_desc", "skill/x", "Hits harder.") is None
    asset = json.loads(ASSET.read_text(encoding="utf-8"))["skill/assassin__haste"]
    assert translations.he(tmp_path, "skill_desc", "skill/assassin__haste", asset["en"]) == asset["he"]


@needs_kb
def test_a_night_translates_a_rewritten_skill_text_into_the_kb(tmp_path, monkeypatch):
    import translate_kb

    from maplehelper.kb import KnowledgeBase
    kb = tmp_path / "kb"
    shutil.copytree(REAL_KB, kb, ignore=shutil.ignore_patterns("img", "pages"))
    shutil.copytree(REAL_KB / "pages" / "skill", kb / "pages" / "skill")
    page = kb / "pages" / "skill" / "bandit__savage-blow.md"
    old = "Use MP to attack an enemy up to 6 times in a row with a dagger."
    page.write_text(page.read_text(encoding="utf-8").replace(old, old.replace("a dagger", "a sharp dagger")),
                    encoding="utf-8")
    jobs = [j for j in translate_kb.missing(kb) if j["kind"] == "skill_desc"]
    assert [(j["key"], j["en"]) for j in jobs] == [("skill/bandit__savage-blow", old.replace("a dagger", "a sharp dagger"))]
    calls = []

    def fake(key, texts):                       # no API: a stand-in translation
        calls.append(list(texts))
        return ["תוקפים עד 6 פעמים ברצף בפגיון חד." for _ in texts]
    monkeypatch.setattr(translate_kb, "translate", fake)
    assert translate_kb.run(kb, "key", jobs) == 1 and calls == [[jobs[0]["en"]]]
    made = json.loads((kb / "he.json").read_text(encoding="utf-8"))["skill_desc"]
    assert made["skill/bandit__savage-blow"] == {"en": jobs[0]["en"], "he": "תוקפים עד 6 פעמים ברצף בפגיון חד."}
    fresh = KnowledgeBase(kb)
    s = next(s for s in skillbook.book(fresh)["Bandit"] if s.name == "Savage Blow")
    assert skillbook.text(fresh, s, "desc", "he") == "תוקפים עד 6 פעמים ברצף בפגיון חד."
    assert not [j for j in translate_kb.missing(kb) if j["kind"] == "skill_desc"]


# ------------------------------------------------------------------ the window (the fixture KB: no guides, no skills)

@pytest.mark.parametrize("lang,tabs", [("he", ["בילד", "סקילים"]), ("en", ["Build", "Skills"])])
def test_two_tabs_build_first_and_open_with_picks_one(opened, lang, tabs):
    from maplehelper.kb import KnowledgeBase
    w = opened(KnowledgeBase(FIXTURE_KB), lang=lang)
    assert [bare(b.text()) for b in tab_buttons(w)] == tabs
    assert w.tab == "build" and w._tabs.value() == "build" and w._picker.isHidden()
    w.open_with("skills")
    pump()
    assert w.tab == "skills" and w._tabs.value() == "skills" and not w._picker.isHidden()
    w.open_with("a quest")                          # not a tab: left as it is
    assert w.tab == "skills"
    w.open_with("build")
    pump()
    assert w.tab == "build" and w._picker.isHidden()


def test_with_no_build_tables_the_card_offers_the_skills_and_the_guides(opened, signals):
    from maplehelper.kb import KnowledgeBase
    w = opened(KnowledgeBase(FIXTURE_KB), "Beginner", "Beginner", 8)
    assert w.build_view is None and not w.tier_cards
    links = {bare(b.text()): b for b in w._page.findChildren(QPushButton, "Link") if b.isVisibleTo(w)}
    assert "See the skills" in links and "All guides" in links
    links["All guides"].click()
    assert signals["guide_requested"] == [""]        # the guides library
    links["See the skills"].click()
    pump()
    assert w.tab == "skills" and w._tabs.value() == "skills"


# ------------------------------------------------------------------ the window (the real KB)

@needs_kb
@pytest.mark.parametrize("lang", ["he", "en"])
def test_the_build_tab_shows_the_plan_with_the_players_row_and_the_full_guide(tool, signals, lang):
    w = tool("Warrior", "Fighter", 35, lang=lang)
    assert w.build_view is not None and w.build_view.isVisibleTo(w) and w.build_view.toPlainText()
    # the whole text shows: no box of its own to scroll in
    assert w.build_view.height() >= int(w.build_view.document().size().height())
    guide = next(b for b in w._page.findChildren(QPushButton, "Link")
                 if bare(b.text()) == ("פתיחת המדריך המלא" if lang == "he" else "Open the full guide"))
    guide.click()
    assert signals["guide_requested"] == [w._build_key] and w._build_key


@needs_kb
def test_a_gear_tables_items_open_their_page(tool, signals):
    w = tool("Warrior", "Fighter", 35)
    names = [unquote(n) for n in re.findall(r"href=[\"']item:([^\"']+)", w.build_view.toHtml())]
    assert names and all(w._kb._item_by_name.get(n.lower()) for n in names)
    for name in names[:3]:
        w.build_view.anchorClicked.emit(QUrl("item:" + name))
    assert signals["item_requested"] == [w._kb._item_by_name[n.lower()] for n in names[:3]]


@needs_kb
@pytest.mark.parametrize("lang", ["he", "en"])
def test_skills_tab_shows_the_characters_job_with_every_part_of_each_skill(tool, signals, lang):
    w = tool(lang=lang)
    skills_tab(w)
    assert w.tab == "skills"
    classes = w.skills_class.buttons()
    assert [bare(b.text()) for b in classes] == ["Beginner", "Warrior", "Magician", "Bowman", "Thief"]
    assert [b.property("value") for b in classes if b.isChecked()] == ["Thief"]
    assert [bare(b.text()) for b in job_buttons(w)] == ["Thief", "Assassin", "Bandit"]
    assert [b.property("value") for b in job_buttons(w) if b.isChecked()] == ["Assassin"]
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    book = skillbook.book(w._kb)
    for cls, jobs in skillbook.class_jobs(w._kb):
        for job in jobs:
            w._pick_skills(cls, job)
            pump(20)
            shown = cards(w)
            assert [c.property("skill") for c in shown] == [s.key for s in book[job]], job
            for card, s in zip(shown, book[job]):
                pic = card.findChild(QLabel, "SkillPicture")
                assert pic.pixmap() is not None and not pic.pixmap().isNull(), s.key
                assert bare(card.findChild(QLabel, "CardTitle").text()) == s.name
                parts = {lb.property("part"): plain_text(lb) for lb in card.findChildren(QLabel) if lb.property("part")}
                assert set(parts) == {"desc", "lv1", "max"} | ({"needs"} if s.prereq else set()), s.key
                chips = [bare(c.text()) for c in card.findChildren(QLabel, "Chip")]
                assert ("רמה מקסימלית " if lang == "he" else "Max Lv. ") + str(s.max_lv) in chips
                if lang == "he":
                    from maplehelper.translations import made_from
                    assert made_from(asset[s.key], s.desc).split(" ")[0] in parts["desc"]
                    assert made_from(asset[s.key + "#max"], s.max).split(";")[0] in parts["max"]
                    assert parts["max"].startswith(f"ברמה {s.max_lv} (מקסימום):")
                    if s.prereq:
                        assert parts["needs"] == f"דורש {s.prereq[0]} ברמה {s.prereq[1]}"
                else:
                    assert re.sub(r"\s+", " ", s.desc) in parts["desc"] and s.lv1 in parts["lv1"]
                    assert parts["lv1"].startswith("Level 1:") and parts["max"].startswith(f"Level {s.max_lv} (max):")
                    if s.prereq:
                        assert parts["needs"] == f"Requires {s.prereq[0]} at level {s.prereq[1]}"
    # "Ask in chat" on a skill asks about it
    w._pick_skills("Thief", "Assassin")
    pump(20)
    card = cards(w)[0]
    card.findChild(QPushButton, "Link").click()
    asked = signals["ask_requested"]
    assert len(asked) == 1 and book["Assassin"][0].name in asked[0] and "Assassin" in asked[0]


@needs_kb
def test_a_class_line_keeps_its_job_while_the_app_runs(tool):
    w = tool()
    skills_tab(w)
    w._pick_skills("Thief", "Bandit")
    w.skills_class.button(1).click()                 # Warrior: its 1st job
    pump()
    assert w._skills_pick == ("Warrior", "Warrior")
    w.skills_class.button(4).click()                 # back to Thief: on Bandit again
    pump()
    assert w._skills_pick == ("Thief", "Bandit")
    assert [b.property("value") for b in job_buttons(w) if b.isChecked()] == ["Bandit"]
    tab_buttons(w)[0].click()                        # the other tab and back: the same picks
    pump()
    tab_buttons(w)[1].click()
    pump()
    assert w.tab == "skills" and w._skills_pick == ("Thief", "Bandit")
    w.hide()                                         # closed and opened again: still
    w.refresh()
    pump()
    assert w._skills_pick == ("Thief", "Bandit")
    # another character: its own job first
    w._profiles.add("Mage", "Magician", "Cleric", 40)
    w.character_changed()
    pump()
    assert w._skills_pick == ("Magician", "Cleric")


@needs_kb
def test_a_beginner_opens_on_beginner_and_the_tabs_read_right_to_left(tool):
    w = tool("Beginner", "Beginner", 8, lang="he")
    skills_tab(w)
    assert w._skills_pick == ("Beginner", "Beginner") and not job_buttons(w)
    assert len(cards(w)) == 3
    w._pick_skills("Magician", None)
    pump()
    classes, jobs = w.skills_class.buttons(), job_buttons(w)
    assert len(jobs) == 4
    for row in (classes[:3], jobs):                  # (the class line may wrap onto a second row)
        xs = [b.mapTo(w, b.rect().center()).x() for b in row if b.mapTo(w, QPoint(0, 0)).y() ==
              row[0].mapTo(w, QPoint(0, 0)).y()]
        assert len(xs) >= 2 and xs == sorted(xs, reverse=True)      # the first on the right, the next to its left


@needs_kb
@pytest.mark.parametrize("lang", ["he", "en"])
def test_the_skills_tab_fits_the_narrow_window(tool, lang):
    w = tool(lang=lang)
    skills_tab(w)
    for width in (w.DEFAULT_W, w.MIN_W):
        w.resize(width, 800)
        for cls, jobs in skillbook.class_jobs(w._kb):
            w._pick_skills(cls, jobs[-1])
            pump(40)
            assert w._scroll.widget().minimumSizeHint().width() <= w._scroll.viewport().width(), (cls, width)
            for b in w.skills_class.buttons() + job_buttons(w):
                assert b.width() >= b.fontMetrics().horizontalAdvance(bare(b.text())), (bare(b.text()), width)
                left = b.mapTo(w._picker, QPoint(0, 0)).x()             # none cut at the picks' edges
                assert 0 <= left and left + b.width() <= w._picker.width(), (bare(b.text()), width)


@needs_kb
def test_another_job_or_class_line_starts_at_the_top_of_its_list(tool):
    from PySide6.QtTest import QTest
    w = tool()
    skills_tab(w)
    w.resize(w.width(), 500)
    pump()
    bar = w._scroll.verticalScrollBar()
    for i in range(len(job_buttons(w))):
        bar.setValue(bar.maximum())
        pump()
        b = job_buttons(w)[i]
        QTest.mouseClick(b, Qt.LeftButton, pos=QPoint(b.width() // 2, b.height() // 2))
        pump()
        assert bar.value() == 0, f"scrolled to {bar.value()} after {b.property('value')}"
        assert [j.property("value") for j in job_buttons(w) if j.isChecked()] == [b.property("value")]
    bar.setValue(bar.maximum())
    w.skills_class.buttons()[0].click()
    pump()
    assert bar.value() == 0


# ------------------------------------------------------------------ the Build tab with NiaMeowDB's list pages

@pytest.fixture
def real_site(monkeypatch):
    """The real KB with the recorded list pages (CI's KB may be from before the first nightly that has them)."""
    if not (REAL_KB / "index.json").exists():
        pytest.skip("no real knowledge base")
    import meowdb_sections as ms

    from maplehelper import sitedata
    from maplehelper.kb import KnowledgeBase

    def page(name: str) -> str:
        return (MEOWDB / f"{name}.html").read_text(encoding="utf-8")
    parsed = {ms.SKILL_CHANGES: ms.parse_skill_changes(page("skill-changes")),
              ms.TIERS: ms.parse_tiers(page("tier-list"))}
    monkeypatch.setattr(sitedata, "_file", lambda kb, name: parsed.get(name, {}))
    return KnowledgeBase(REAL_KB)


@pytest.mark.parametrize("lang", ["he", "en"])
def test_the_sp_table_marks_changed_skills_and_the_tier_card_ranks_the_job(opened, real_site, lang, monkeypatch):
    from maplehelper import sitedata
    from maplehelper.ui import terms
    w = opened(real_site, "Warrior", "Fighter", 35, lang=lang)
    # the SP table: a chip at the first mention of a changed skill, its changes on hover. Which skills the Warrior
    # guide's table names is the guide's: every chip is once, a changed skill of this character's line (never the
    # Page's), and the guide still names some of them
    chips = re.findall(r"change:(skill/[\w-]+)", w.build_view.toHtml())
    assert chips and set(chips) <= set(sitedata.skill_changes(real_site))
    assert all(chips.count(k) == 1 for k in chips) and not any(k.startswith("skill/page__") for k in chips)
    assert all(k.split("/")[1].split("__")[0] in ("warrior", "fighter", "beginner") for k in chips)
    shown = []
    monkeypatch.setattr(terms, "show_html", lambda body, rtl=False: shown.append(body))
    w.build_view.highlighted.emit(QUrl("change:" + chips[0]))
    ch = sitedata.skill_change(real_site, chips[0])
    assert shown and all(str(v) in shown[0] for row in ch.changes[:1] for v in row[1:3] if v not in (None, ""))
    # the community tier card: one for a Fighter (a Bowman before the 2nd job gets two), a grade per column
    assert len(w.tier_cards) == 1
    card = w.tier_cards[0]
    assert any(bare(t.text()) in ("קהילה", "Community") for t in card.findChildren(QLabel, "SourceTag"))
    grades = card.findChildren(QLabel, "Grade")
    assert len(grades) == len(sitedata.tier_data(real_site)["columns"]) == 8
    assert {g.property("grade") for g in grades} <= {"S", "A", "B", ""}


@needs_kb
def test_the_white_glass_rebuilds_the_rich_text_in_its_colours(tool, isolated_store):
    from maplehelper.ui import npcoverlay
    w = tool("Warrior", "Fighter", 35)
    fill = npcoverlay.accent_of(w._settings)[0]
    dark_view = w.build_view
    assert npcoverlay.ink(fill).lower() == fill.lower()          # the dark glass: the accent as it is
    w._settings["overlay_tint"] = "white"
    npcoverlay.apply_look(w._settings)
    w.refresh()                                                  # the ⚙ panel picked the white glass
    pump()
    assert w.build_view is not dark_view
    dark_link, light_link = fill.lower(), npcoverlay.ink(fill).lower()
    assert dark_link != light_link
    text = w.build_view.toHtml().lower()
    assert light_link in text and f"color:{dark_link}" not in text.replace(" ", "")
