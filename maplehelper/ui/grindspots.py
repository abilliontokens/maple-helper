"""The Grind spots window over the game (the toolbar's Tools card, ui/toolwindow.py), top to bottom:

- the character: name · job · level, and "Your stats" — the ACC and the damage range of the game's Stat window the
  spots are ranked by (saved to the character, Character.stats), folded to one line once typed; Edit opens the
  boxes (they take the keyboard only while typed in), Read from screen asks the chat to read them off a screenshot;
- the monsters worth grinding at the character's level (combat.spots: the EXP each swing earns with those stats,
  or EXP per HP without them), the best first and lit: each its picture, its level, its map and street, why it is
  picked (in the guide, the most mesos of the list, the hit chance) and its numbers (basic hits to kill, EXP, how
  many spawn, the mesos players reported, where the numbers come from), the ACC that never misses and the kills to
  the next level, then Show the way (NAV.map_requested) and Hit & damage (its page, NAV.monster_requested)."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIntValidator, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .. import bidi, combat, sources
from .controls import FlowLayout, clear
from .gamesearch import rim
from .npcoverlay import accent_of, ink, palette
from .terms import hint_badge_html
from .toolwindow import NAV, KeyBox, ToolWindow, _rgba
from .widgets import fit_picture, mesos_text, mesos_tip, source_tag, tip_html, updated_tag, zoom_on_hover

SPOTS_N = 6                         # the monsters listed, as the old Grind spots page did
PIC = 52                            # a monster's picture
STAT_DEBOUNCE_MS = 350              # a pause in a stat box before the character is saved and the spots re-read
# the stat window's numbers: the character's key, the highest the box takes, the box's name
STATS = (("acc", 999, "stat_acc"), ("dmg_min", 99_999, "stat_dmg_min"), ("dmg_max", 99_999, "stat_dmg_max"))
GOOD, WARN = "#4CD07D", "#FFB066"   # never missing / missing some: readable on every dark tint (ink: on the white)
NEVER_MISS = 0.999                  # a hit chance this high counts as never missing


class GrindSpots(ToolWindow):
    """The monsters worth grinding at the active character's level, ranked by the stats typed at the top."""

    SHOW_KEY, GEOM_KEY, TITLE_KEY = "grind_spots", "grind_spots_geom", "tb_spots"
    MIN_W, MIN_H = 380, 440
    DEFAULT_W, DEFAULT_H = 440, 680

    # ------------------------------------------------------------ built once

    def _build_body(self) -> None:
        self._cid: str | None = None              # whose stats the boxes show
        self._stats_open: bool | None = None      # the boxes shown (None: shown while nothing is typed)
        self._saving = QTimer(self, singleShot=True, interval=STAT_DEBOUNCE_MS, timeout=self._stats_saved)
        self._char = QLabel(objectName="Char")
        self._char.setWordWrap(True)
        self.top.addWidget(self._char)
        self.top.addWidget(self._build_stats())

    def _build_stats(self) -> QFrame:
        """"Your stats" in a card: its head (the title, the typed stats on one line while folded, Edit / Done), the
        three boxes, what to do while they are not typed, and Read from screen."""
        card, v = self.card()
        v.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._stats_head = QLabel(objectName="Caption")
        self._stats_line = QLabel(objectName="StatsLine")
        self._stats_line.setWordWrap(True)        # a long range never widens the window
        self._stats_btn = self.button("", self._stats_toggled, "Small")
        row.addWidget(self._stats_head, 0, Qt.AlignVCenter)
        row.addWidget(self._stats_line, 1, Qt.AlignVCenter)
        row.addWidget(self._stats_btn, 0, Qt.AlignVCenter)
        v.addLayout(row)
        self._stats_edit = QWidget()
        boxes = QHBoxLayout(self._stats_edit)
        boxes.setContentsMargins(0, 0, 0, 0)
        boxes.setSpacing(8)
        self._names: dict[str, QLabel] = {}
        self._boxes: dict[str, KeyBox] = {}
        for key, hi, _ in STATS:
            col = QVBoxLayout()
            col.setSpacing(3)
            name = QLabel(objectName="StatName")
            box = self.key_box("", search=False)
            box.setObjectName("Stat")
            box.setValidator(QIntValidator(0, hi, box))
            box.setMaxLength(len(str(hi)))
            box.setAlignment(Qt.AlignCenter)
            box.textEdited.connect(lambda _t: self._stat_typed())
            box.entered.connect(lambda k=key: self._stat_entered(k))
            col.addWidget(name)
            col.addWidget(box)
            boxes.addLayout(col, 1)
            self._names[key], self._boxes[key] = name, box
        v.addWidget(self._stats_edit)
        self._need = QLabel(objectName="Hint")
        self._need.setWordWrap(True)
        v.addWidget(self._need)
        self._read = self.button("", NAV.read_screen_requested.emit, "Small")
        v.addWidget(self._read, 0, Qt.AlignLeft)         # the leading edge (mirrored in Hebrew)
        return card

    def extra_qss(self) -> str:
        p = palette()
        fill, _ = accent_of(self._settings)
        lit, good, warn = ink(fill), ink(GOOD), ink(WARN)
        chip = "border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700;"
        return f"""
#Char {{ color: {p.text}; font-size: 14px; font-weight: 700; padding: 0 2px; }}
#StatsLine {{ color: {p.text}; font-size: 12px; font-weight: 600; }}
#StatName {{ color: {p.muted}; font-size: 11px; font-weight: 600; }}
QLineEdit#Stat {{ border: 1px solid transparent; padding: 5px 4px; }}
QLineEdit#Stat:focus {{ border: 1px solid {fill}; }}
#LitCaption {{ color: {lit}; font-size: 10px; font-weight: 700; }}
#Pic {{ background: {rim(0.06, p)}; border-radius: 8px; }}
QLabel#ChipGood {{ color: {good}; background: {_rgba(good, 0.15)}; {chip} }}
QLabel#ChipWarn {{ color: {warn}; background: {_rgba(warn, 0.15)}; {chip} }}
QLabel#SourceTag {{ color: {lit}; background: transparent; border: 1px solid {_rgba(fill, 0.6)}; border-radius: 5px;
                    padding: 0 4px; font-size: 10px; font-weight: 700; min-height: 0; }}
QLabel#UpdatedTag {{ color: {lit}; background: {_rgba(fill, 0.14)}; border: 1px solid {_rgba(fill, 0.45)}; {chip} }}
"""

    def open_with(self, arg: str) -> None:
        """Asked for by another window (the monster page's "Type your stats"): whatever it names, the stat boxes
        open, ready to be typed in."""
        if self.character is None:
            return
        self._stats_open = True
        self._retext_stats()

    # ------------------------------------------------------------ filled

    def _rebuild(self) -> None:
        """The character's line and stats, then the spots for its level and stats."""
        t, rtl = self.t, self.t.rtl
        c = self.character
        switched = c.id != self._cid
        if switched:
            if self._saving.isActive():            # typed for the character before: saved to it
                self._saving.stop()
                self._save()
            self._cid, self._stats_open = c.id, None
        self._char.setText(bidi.plain(f"{bidi.ltr_name(f'{c.name} · {c.job}', rtl)} · {t('lv_short', n=c.level)}",
                                      rtl))
        stats = c.stats or {}
        for key, _, name in STATS:
            self._names[key].setText(bidi.plain(t(name), rtl))
            box = self._boxes[key]
            box.setPlaceholderText("\u2014")            # its name over it says what it is; "—" not typed yet
            box.setAccessibleName(t(name))
            if switched or not box.hasFocus():          # the box being typed in keeps what is typed
                box.setText(str(stats[key]) if stats.get(key) else "")
        self._stats_head.setText(bidi.plain(t("my_stats") if rtl else t("my_stats").upper(), rtl))
        self._stats_btn.setToolTip(t("gs_stats_tip"))
        self._read.setText(bidi.plain(t("gs_read"), rtl))
        self._read.setToolTip(t("gs_read_tip"))
        self._retext_stats()
        self._fill_spots()

    def _stats(self) -> tuple[int | None, tuple[int, int] | None]:
        """The character's ACC and damage range as typed (combat.damage_range: min above max swapped)."""
        s = (self.character.stats if self.character else {}) or {}
        return int(s.get("acc") or 0) or None, combat.damage_range(s.get("dmg_min"), s.get("dmg_max"))

    def _fill_spots(self) -> None:
        t = self.t
        c = self.character
        clear(self.body)
        acc, dmg = self._stats()
        magic = c.base_class == combat.MAGE
        rows = combat.spots(self._kb, c.level, acc, dmg, magic, n=SPOTS_N)
        if not rows:
            self.body.addWidget(self.empty("swords", t("train_none")))
            return
        if not any(s.fits for s in rows):
            # nothing passes the miss / hits limits: still the best options, with why they're shown (a Magician's
            # hits are spells: "too many basic hits" and "skills make it faster" don't apply)
            self.body.addWidget(self.label(t("train_stretch_magician" if magic else "train_stretch"), "Hint",
                                           wrap=True))
        self.body.addWidget(self.caption(t("list_monsters")))
        self.body.addWidget(self._why(rows, acc, dmg, magic))
        most = self._most_mesos(rows)
        for i, s in enumerate(rows):
            self.body.addWidget(self._spot_card(s, best=i == 0, most_mesos=s is most))

    def _why(self, rows: list[combat.Spot], acc, dmg, magic: bool) -> QLabel:
        """One short line, the levels the list shows; the whole why behind its "?" (the rule, the stat window's
        note)."""
        t, rtl = self.t, self.t.rtl
        c = self.character
        levels = [s.monster.level for s in rows]
        lo, hi = min(levels), max(levels)
        span = str(lo) if lo == hi else bidi.ltr_block(f"{lo}\u2013{hi}", rtl)     # (read "27–23" in Hebrew)
        rule = t("train_why_stats" if acc and dmg and not magic else "train_why",
                 lo=max(1, c.level - combat.SPOT_BELOW), hi=c.level + combat.SPOT_ABOVE)
        if acc and dmg:
            rule += "\n" + t("train_mage_note" if magic else "train_basic_note")
        # the "?" before the line says there is more on hover, in the glass's own grey (the accent's clashed)
        text = hint_badge_html(13) + html.escape(bidi.plain(t("train_shown", n=len(rows), span=span), rtl))
        why = QLabel(text, objectName="Hint")
        why.setTextFormat(Qt.RichText)
        why.setWordWrap(True)
        why.setToolTip(tip_html(rule, rtl))
        return why

    def _most_mesos(self, rows: list[combat.Spot]) -> combat.Spot | None:
        """The spot that brings the most mesos per swing by the players' reports (a kill's mesos x hit chance /
        hits), labelled on its card: a second ranking beside the EXP one, not a reorder. None unless at least two
        of the spots have reports to compare."""
        rated = [(s, m * s.hit / (s.avg_hits or 1)) for s in rows if (m := self._kb.mesos_per_kill(s.monster.key))]
        return max(rated, key=lambda r: r[1])[0] if len(rated) >= 2 else None

    def _spot_card(self, s: combat.Spot, best: bool, most_mesos: bool = False) -> QFrame:
        """One monster: its picture, "Best pick" over the best one's name, its level, map and street; why it is
        picked, then its numbers, as chips; the ACC that never misses and the kills to the next level; its links."""
        t, rtl = self.t, self.t.rtl
        c, m, kb = self.character, s.monster, self._kb
        acc = self._stats()[0]
        card, v = self.card(lit=best)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._picture(m.key), 0, Qt.AlignTop)
        who = QVBoxLayout()
        who.setSpacing(1)
        if best:
            who.addWidget(self.label(t("spot_best") if rtl else t("spot_best").upper(), "LitCaption"))
        name = QLabel(bidi.plain(f"{bidi.name_block(m.name, rtl)} · {t('lv_short', n=m.level)}", rtl),
                      objectName="CardTitle")
        name.setWordWrap(True)
        who.addWidget(name)
        # "Ant Tunnel I · Victoria Road", one English block (run by run, a Hebrew line put the street first)
        where = QLabel(bidi.ltr_name(kb.map_label(s.map), rtl), objectName="CardSub")
        where.setWordWrap(True)
        who.addWidget(where)
        top.addLayout(who, 1)
        v.addLayout(top)
        # why it's picked, then the numbers: one wrapping row of chips (never wider than the window)
        box = QWidget()
        flow = FlowLayout(box, spacing=4, line_spacing=4)
        if s.recommended:
            flow.addWidget(self._chip(t("spot_guide"), "ChipOn"))
        if most_mesos:
            flow.addWidget(self._chip(t("spot_most_mesos"), "ChipOn", t("spot_most_mesos_tip")))
        if acc:
            flow.addWidget(self._chip(t("spot_hit", pct=round(s.hit * 100)),
                                      "ChipGood" if s.hit >= NEVER_MISS else "ChipWarn"))
        updated = updated_tag(t, kb, m.key, stats_only=True)
        if updated is not None:
            flow.addWidget(updated)
        if s.hits:
            flow.addWidget(self._chip(t("spot_hits", n=s.hits), "Chip"))
        flow.addWidget(self._chip(t("spot_exp", n=f"{m.exp:,}"), "Chip"))
        flow.addWidget(self._chip(t("spot_crowd", n=m.maps[0][1]), "Chip"))
        mesos = kb.community_mesos(m.key)
        if mesos:
            flow.addWidget(self._chip(mesos_text(t, mesos), "Chip", mesos_tip(t, mesos)))
        # the monster's numbers come from its page: its build ("COT2") or MeowDB's own
        stamp = sources.stat_source(kb, m.key)
        flow.addWidget(source_tag(t, stamp.source if stamp else sources.MEOWDB, stamp))
        v.addWidget(box)
        info = []
        if acc and s.hit < NEVER_MISS:
            info.append(t("spot_acc_need", n=s.acc_needed))
        kills = combat.kills_to_level(kb, c.level, c.exp_pct, m)
        if kills:
            info.append(t("spot_kills", n=f"{kills:,}"))
        if info:
            line = QHBoxLayout()
            line.setSpacing(6)
            # the kills come from the EXP table: past its confirmed levels it is a historical reference
            if kills and sources.exp_source(kb, c.level) == sources.REFERENCE:
                line.addWidget(source_tag(t, sources.REFERENCE), 0, Qt.AlignTop)
            line.addWidget(self.label(" · ".join(info), "Hint", wrap=True), 1)
            v.addLayout(line)
        links = QHBoxLayout()
        links.setSpacing(16)
        way = combat.map_key(kb, s.map)
        go = self.button(t("gw_show_way"), lambda k=way: NAV.map_requested.emit(k), "Link", t("gw_show_way_tip"))
        go.setEnabled(way is not None)
        links.addWidget(go)
        links.addWidget(self.button(t("tool_calc"), lambda k=m.key: NAV.monster_requested.emit(k), "Link",
                                    t("gs_calc_tip")))
        links.addStretch(1)
        v.addLayout(links)
        return card

    def _chip(self, text: str, name: str, tip: str = "") -> QLabel:
        chip = QLabel(bidi.plain(text, self.t.rtl), objectName=name)
        chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        if tip:
            chip.setToolTip(tip_html(tip, self.t.rtl))
        return chip

    def _picture(self, key: str) -> QLabel:
        """The monster's picture in its square, larger on hover."""
        pic = QLabel(objectName="Pic", alignment=Qt.AlignCenter)
        pic.setFixedSize(PIC, PIC)
        path = self._kb.picture(key)
        if path:
            pm = QPixmap(str(path))
            if not pm.isNull():
                pic.setPixmap(fit_picture(pm, PIC - 6, PIC - 6, pic))
                zoom_on_hover(pic, path)
        return pic

    # ------------------------------------------------------------ the player's own numbers

    def _typed(self) -> bool:
        stats = (self.character.stats if self.character else {}) or {}
        return any(stats.get(key) for key, _, _ in STATS)

    def _retext_stats(self) -> None:
        """Your stats: open (the boxes, Read from screen) or folded to "ACC 120 · Damage 150–300"; what to do while
        the ACC or the damage the spots need is missing (a Magician's damage is never used: a staff swing)."""
        t, rtl = self.t, self.t.rtl
        c = self.character
        if c is None:
            return
        acc, dmg = self._stats()
        open_ = self._stats_open if self._stats_open is not None else not self._typed()
        self._stats_edit.setVisible(open_)
        self._read.setVisible(open_)
        parts = []
        if acc:
            parts.append(bidi.ltr_block(t("gs_acc", n=acc), rtl))
        if dmg:
            span = f"{dmg[0]:,}" if dmg[0] == dmg[1] else f"{dmg[0]:,}\u2013{dmg[1]:,}"
            parts.append(t("gs_dmg", range=bidi.ltr_block(span, rtl)))
        line = " · ".join(parts) or t("ga_stats_none")
        self._stats_line.setText("" if open_ else bidi.plain(line, rtl))
        self._stats_btn.setText(bidi.plain(t("ga_stats_done" if open_ else "ga_stats_edit"), rtl))
        missing = not acc or (not dmg and c.base_class != combat.MAGE)
        self._need.setText(bidi.plain(t("gs_need_stats"), rtl))
        self._need.setVisible(missing)

    def _stats_toggled(self) -> None:
        """Edit / Done: the boxes open (the first empty one takes the keyboard) or fold to their line, the keyboard
        back to the game — a number typed just before Done saved first, so the line has it."""
        if self.character is None:
            return
        open_ = self._stats_open if self._stats_open is not None else not self._typed()
        self._stats_open = not open_
        if self._saving.isActive():
            self._saving.stop()
            self._stats_saved()
        else:
            self._retext_stats()
        if self._stats_open:
            stats = self.character.stats or {}
            key = next((k for k, _, _ in STATS if not stats.get(k)), STATS[0][0])
            self._take_keys(self._boxes[key])
        else:
            self._give_keys()

    def _stat_typed(self) -> None:
        """A keystroke in a stat box: the row stays open while typed in; the saving waits for the pause."""
        self._stats_open = True
        self._saving.start()

    def _stat_entered(self, key: str) -> None:
        """Enter in a box: on to the next one; in the last, Done."""
        keys = [k for k, _, _ in STATS]
        i = keys.index(key)
        if i + 1 < len(keys):
            self._boxes[keys[i + 1]].setFocus(Qt.OtherFocusReason)
        else:
            self._stats_open = True
            self._stats_toggled()

    def _save(self) -> bool:
        """Every stat box to the character whose boxes they are (empty or 0: not said); True when one changed."""
        c = next((c for c in self._profiles.characters if c.id == self._cid), None)
        if c is None:
            return False
        stats = dict(c.stats or {})
        for key, _, _ in STATS:
            text = self._boxes[key].text().strip()
            if text.isdigit() and int(text) > 0:
                stats[key] = int(text)
            else:
                stats.pop(key, None)
        if stats == (c.stats or {}):
            return False
        c.stats = stats
        self._profiles.save()
        NAV.stats_changed.emit()                 # the search's monster page: its Hit & damage again
        return True

    def _stats_saved(self) -> None:
        """The pause held: the stats saved and the spots ranked again by them."""
        if self._save():
            self._refill()
        else:
            self._retext_stats()

    def hideEvent(self, e) -> None:
        if self._saving.isActive():             # typed just before the window closed: kept
            self._saving.stop()
            self._save()
        super().hideEvent(e)
