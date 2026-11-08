"""The window kit and the text it lays out: frames, banners, footers, wrapping.

Pure Console draws, so these run headless anywhere.
"""
from __future__ import annotations

import unittest
import warnings

import numpy as np
import tcod.console


def _con(w=80, h=50):
    return tcod.console.Console(w, h, order="F")


class TestWindowFrames(unittest.TestCase):
    """Every window drew its frame with tcod's ``draw_frame(title=…)``, which
    tcod has deprecated: the day it's removed, every window raises TypeError."""

    def test_a_window_uses_no_deprecated_tcod_call(self):
        from hearthdelve.engine import ui
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            ui.Modal(_con(), 40, 10, "Pack")

    def test_the_frame_looks_as_tcod_drew_it(self):
        from hearthdelve.engine import ui
        for w in (10, 21, 40, 79):
            for title in ("", "Pack", "Shipping Bin — sell", "x" * (w - 4)):
                if len(title) > w - 4:
                    continue                # too long to fit: see the next test
                ours = _con()
                ui.frame(ours, 3, 2, w, 6, title)
                ref = _con()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        ref.draw_frame(3, 2, w, 6, title=title, fg=ui.HDR, bg=ui.BASE_BG)
                    except TypeError:
                        self.skipTest("this tcod no longer draws titled frames")
                with self.subTest(w=w, title=title):
                    self.assertTrue(np.array_equal(ours.ch, ref.ch))
                    self.assertTrue(np.array_equal(ours.fg, ref.fg))
                    self.assertTrue(np.array_equal(ours.bg, ref.bg))

    def test_a_title_too_long_keeps_the_corners(self):
        from hearthdelve.engine import ui
        con = _con()
        ui.frame(con, 0, 0, 12, 4, "A title far too long for it")
        self.assertEqual(chr(con.ch[0, 0]), "┌")
        self.assertEqual(chr(con.ch[11, 0]), "┐")


def _rows(con, x0, x1, y0, y1) -> str:
    """The text in a console rectangle, rows joined by spaces."""
    return " ".join("".join(chr(con.ch[x, y]) for x in range(x0, x1)).strip()
                    for y in range(y0, y1))


class TestLongLogLinesWrap(unittest.TestCase):
    """The log pane cut every message at 56 columns and the full history at
    68: three of the five opening tips lost their ends, and a hit on a
    long-named monster lost the damage number."""

    LONG = ("The deep troll of the sunless vaults swings its club — your armour "
            "holds, but it still bites for 4217.")

    def test_wrap_keeps_every_word_within_the_width(self):
        from hearthdelve.engine import ui
        for width in (12, 30, 56):
            lines = ui.wrap(self.LONG, width, indent=2)
            with self.subTest(width=width):
                self.assertTrue(all(len(line) <= width for line in lines))
                self.assertEqual(" ".join(line.strip() for line in lines), self.LONG)
                self.assertTrue(all(line.startswith("  ") for line in lines[1:]))

    def test_a_word_longer_than_the_line_is_split_not_spilled(self):
        from hearthdelve.engine import ui
        lines = ui.wrap("x" * 25, 10)
        self.assertEqual("".join(lines), "x" * 25)
        self.assertTrue(all(len(line) <= 10 for line in lines))

    def test_the_log_pane_shows_the_whole_message(self):
        from hearthdelve.engine import constants as C
        from hearthdelve.engine import rendering
        from tests.common import fresh_state
        st = fresh_state(1)
        st.log.add(self.LONG)
        con = _con()
        rendering.render_log(con, st)
        shown = _rows(con, 0, C.VIEW_W, C.VIEW_H + 1, C.SCREEN_H)
        self.assertIn("bites for 4217.", shown)
        self.assertIn("sunless vaults", shown)

    def test_the_history_shows_the_whole_message(self):
        from hearthdelve.engine import rendering
        from tests.common import fresh_state
        st = fresh_state(1)
        st.log.add(self.LONG + " " + self.LONG)       # longer than the history's width
        con = _con()
        rendering.render_message_log(con, st, 0)
        shown = _rows(con, 5, 75, 0, 50)              # inside the 72-wide frame
        self.assertEqual(shown.count("bites for 4217."), 2)


class TestTheAimBannerStaysReadable(unittest.TestCase):
    """The aim banner and its key hint shared the top row and the hint was
    printed over the banner: with only bombs it read ' Aim — th', so 'out of
    range' never showed; with a bow too, the 64-character hint covered it all
    and ran past the map onto the side panel."""

    def _aim(self, purpose, bow, far):
        from hearthdelve.data import content
        from hearthdelve.engine import constants as C
        from hearthdelve.engine import rendering
        from hearthdelve.entities import items
        from tests.common import fresh_state
        st = fresh_state(1)
        st.player.inventory.add(items.BOMB, 3)
        if bow:
            st.player.equipment["ranged"] = content.make_ranged("Short Bow", "birch")
            st.player.inventory.add(items.ARROW, 10)
        p = st.player
        cursor = (p.x + (30 if far else 1), p.y)
        con = _con()
        rendering.render_all(con, st, 0.0)
        panel = (con.ch[C.VIEW_W:].copy(), con.fg[C.VIEW_W:].copy())
        rendering.render_target(con, st, {"cursor": cursor, "purpose": purpose})
        return con, panel

    def test_out_of_range_is_shown_with_bombs_alone(self):
        from hearthdelve.engine import constants as C
        con, _panel = self._aim("throw", bow=False, far=True)
        self.assertIn("Aim — out of range", _rows(con, 0, C.VIEW_W, 0, 1))

    def test_with_bow_and_bomb_the_banner_and_hint_both_read_in_full(self):
        from hearthdelve.engine import constants as C
        con, panel = self._aim("shoot", bow=True, far=False)
        self.assertIn("Aim — loose the short bow", _rows(con, 0, C.VIEW_W, 0, 1))
        hint = _rows(con, 0, C.VIEW_W, 1, 4)
        for words in ("move to aim", "Enter/Space confirm", "Tab bow/bomb", "Esc cancel"):
            self.assertIn(words, hint)
        self.assertTrue(np.array_equal(con.ch[C.VIEW_W:], panel[0]), "spilled onto the panel")
        self.assertTrue(np.array_equal(con.fg[C.VIEW_W:], panel[1]))


class TestTheWorldMapLegendIsReadable(unittest.TestCase):
    """The map's legend and its footer were both printed on row 48, so the
    footer overwrote the legend's start: 'm / Esc closem ■ village …'."""

    def test_legend_and_footer_both_read_in_full(self):
        from hearthdelve.engine import rendering
        from tests.common import fresh_state
        st = fresh_state(1)
        con = _con()
        rendering.render_world_map(con, st)
        text = [_rows(con, 1, 79, y, y + 1) for y in range(50)]
        legend = "@ you   ⌂ farm   ■ village   ▼ delve (by kind)   · road"
        self.assertTrue(any(legend in row for row in text))
        self.assertTrue(any(row == "m / Esc close" for row in text))


class TestScrollingStopsAtTheEnd(unittest.TestCase):
    """The codex, the relations list and the message log clamped their scroll
    only while drawing, never the stored value: after 200 presses past the
    end it read 200, and took 200 presses back before the view moved."""

    PRESSES = 2000                                      # past the end of the longest page

    def _overscroll(self, screen, older):
        """Press far past the end (a frame drawn after each, as in play),
        then once back. Returns the scroll before and after."""
        from hearthdelve import screens
        from hearthdelve.entities import items
        from tests.common import fresh_state
        from hearthdelve.engine import codex
        st = fresh_state(6)
        for i in range(100):                            # a history longer than the window
            st.log.add(f"Note {i}: the wind turns over the {items.WHEAT.name.lower()}.")
        for npc in st.surface.npcs:                     # a relations list longer than it
            npc.met = True
        if isinstance(screen, screens.HelpScreen):      # the codex's longest page
            pages = codex.build_codex_pages(st)
            screen.page = max(range(len(pages)), key=lambda k: len(pages[k][1]))
        ui = screens.UI(st)
        ui.push(screen)
        con = _con()
        for _ in range(self.PRESSES):
            screen.handle(ui, "move", ("move", 0, older))
            screen.render(ui, con)
        end = screen.scroll
        screen.handle(ui, "move", ("move", 0, -older))
        screen.render(ui, con)
        return end, screen.scroll

    def test_one_press_back_moves_the_view(self):
        from hearthdelve import screens
        for make, older in ((screens.HelpScreen, 1), (screens.RelationsScreen, 1),
                            (screens.LogScreen, -1)):
            with self.subTest(screen=make.__name__):
                end, back = self._overscroll(make(), older)
                self.assertTrue(0 < end < self.PRESSES, end)   # it scrolls, and stops at the end
                self.assertEqual(back, end - 1)


class TestTheCodexKnowsTheVillagersUnderground(unittest.TestCase):
    """The codex's Villagers page listed the current map's folk: underground
    that was 5 rows against 81 on the surface."""

    def _villagers(self, st):
        from hearthdelve.engine import codex
        pages = dict(codex.build_codex_pages(st))
        return [text for text, _c in pages["Villagers"]]

    def test_the_page_reads_the_same_below_as_above(self):
        from hearthdelve.game import delve
        from tests.common import fresh_state
        st = fresh_state(6)
        above = self._villagers(st)
        mouth = sorted(p for p, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        self.assertTrue(st.world.is_dungeon)
        self.assertGreater(len(above), 40)
        self.assertEqual(self._villagers(st), above)


class TestTheCodexWrapsInsteadOfCutting(unittest.TestCase):
    """The codex cut every row at its page's edge: 145 rows across eight
    pages lost their ends, some 159 characters long ('Shift+D drops the s')."""

    def test_every_page_fits_and_keeps_every_word(self):
        from hearthdelve.engine import codex
        from tests.common import fresh_state
        st = fresh_state(6)
        for npc in st.surface.npcs:
            npc.met = True
        width = codex._CODEX_W - 4
        for title, rows in codex.build_codex_pages(st):
            wrapped = codex.wrap_rows(rows, width)
            with self.subTest(page=title):
                self.assertTrue(all(len(text) <= width for text, _c in wrapped))
                self.assertEqual(" ".join(t for t, _c in wrapped).split(),
                                 " ".join(t for t, _c in rows).split())

    def test_a_key_row_hangs_its_overflow_under_the_description(self):
        from hearthdelve.engine import codex
        row = "  h  /  Shift+M     message history (PgUp/PgDn page, ↑↓ scroll), and more"
        lines = codex.wrap_row(row, 50)
        self.assertTrue(lines[0].startswith("  h  /  Shift+M     message"))
        self.assertTrue(all(line.startswith(" " * 20) and line[20] != " "
                            for line in lines[1:]))

    def test_the_page_shows_the_whole_row(self):
        from hearthdelve.engine import codex
        from tests.common import fresh_state
        con = _con()
        codex.render_codex(con, fresh_state(1), 0, 0)    # Controls
        self.assertIn("Shift+D drops the stack)", _rows(con, 9, 71, 0, 50))


class TestTheCameraComesHomeWhenOverlaysClose(unittest.TestCase):
    """Look and aim mode point the camera at their cursor and hand it back on
    close. The cheat menu opened over them (the Konami code is all arrows,
    which move a cursor) and dropped every overlay at once, so the view
    stayed fixed on the old cursor instead of following you."""

    def test_closing_the_cheats_over_look_mode_frees_the_camera(self):
        from hearthdelve import screens
        from hearthdelve.engine import rendering
        from tests.common import fresh_state
        st = fresh_state(1)
        ui = screens.UI(st)
        p = st.player
        ui.push(screens.LookScreen([p.x, p.y]))
        for _ in range(15):
            ui.top.handle(ui, "move", ("move", 1, 0))   # the cursor roams off east
        self.assertIsNotNone(st.cam_focus)
        ui.open_cheats()
        ui.top.handle(ui, "cancel", ("cancel",))
        self.assertIs(ui.top, ui.stack[0])
        self.assertIsNone(st.cam_focus)
        before = rendering.camera_origin(st)
        p.x += 3                                       # walk on; the view follows you
        self.assertNotEqual(rendering.camera_origin(st), before)


def _framed_words(con) -> list[str]:
    """Every word written inside a window's side borders, top to bottom."""
    words = []
    for y in range(con.ch.shape[1]):
        row = "".join(chr(c) for c in con.ch[:, y])
        if row.count("│") >= 2:
            words += row[row.index("│") + 1:row.rindex("│")].split()
    return words


def _contains(words, sub) -> bool:
    n = len(sub)
    return any(words[i:i + n] == sub for i in range(len(words) - n + 1))


class TestSpeechWrapsInsteadOfCutting(unittest.TestCase):
    """Dialogue was cut at 68 characters (the swarm-day line, and seven of the
    villagers' own lines), and a shopkeeper's greeting at 52 — 53 of their
    lines lost their ends on the counter."""

    def _speech(self):
        from hearthdelve.data import content
        from hearthdelve.game import events
        from tests.common import fresh_state
        st = fresh_state(1)
        omens = list(events._OMENS.values())            # the weather-wise's foretellings
        for npc in list(st.surface.npcs) + list(content.dwarf_npcs()):
            texts = list(npc.blurbs) + [t for _h, t in npc.heart_blurbs]
            for text in texts + omens:
                yield st, npc, text

    def test_a_conversation_shows_every_word(self):
        from hearthdelve.engine import rendering
        for st, npc, text in self._speech():
            con = _con()
            rendering.render_dialogue(con, st, npc, text)
            with self.subTest(npc=npc.name, text=text[:30]):
                self.assertTrue(_contains(_framed_words(con), text.split()))

    def test_a_shopkeepers_greeting_shows_every_word(self):
        from hearthdelve.engine import rendering
        from hearthdelve.game import village
        for st, npc, text in self._speech():
            if not village.npc_shop(st, npc):
                continue
            con = _con()
            rendering.render_shop(con, st, npc, 0, text)
            with self.subTest(npc=npc.name, text=text[:30]):
                self.assertTrue(_contains(_framed_words(con), text.split()))

    def test_verse_keeps_its_line_breaks(self):
        from hearthdelve.engine import ui
        verse = "Hey dol! merry dol! Yew am I, the warden —\nboughs for my rafters!"
        self.assertEqual(ui.wrap_speech(verse, 60), verse.split("\n"))


class TestEveryWindowStaysInsideItsFrame(unittest.TestCase):
    """Four windows printed past their frames: the intro page (the first
    thing a new player sees) by 4 cells, the pack's footer by 9 onto the side
    panel, the chest's by 1 and the Hall's wing tally by 13. The notice
    board's project line and two intro lines ran into the frame itself.
    Every window is drawn here with a crowded pack and chest, onto a screen
    of sentinels: nothing may change outside a frame, and no text may land
    on its sides or bottom."""

    SENTINEL = ord("¤")

    @classmethod
    def setUpClass(cls):
        from hearthdelve.entities import items
        from tests.common import fresh_state
        cls.st = fresh_state(6)
        goods = [it for it in items.BY_NAME.values() if it.stackable]
        for it in goods[:120]:
            cls.st.player.inventory.add(it, 3, quality=2)
        for it in goods[120:160]:
            cls.st.storage.add(it, 2)

    def _check(self, draw):
        from unittest import mock
        from hearthdelve.engine import ui
        rects, real = [], ui.Modal.__init__

        def record(modal, con, w, h, title):
            real(modal, con, w, h, title)
            rects.append((modal.x, modal.y, w, h))
        con = _con()
        con.ch[:] = self.SENTINEL
        with mock.patch.object(ui.Modal, "__init__", record):
            draw(con)
        self.assertTrue(rects)
        inside = np.zeros(con.ch.shape, bool)
        for x, y, w, h in rects:
            inside[max(0, x):x + w, max(0, y):y + h] = True
            sides = "".join(chr(con.ch[cx, cy]) for cy in range(y + 1, y + h - 1)
                            for cx in (x, x + w - 1))
            bottom = "".join(chr(con.ch[cx, y + h - 1]) for cx in range(x + 1, x + w - 1))
            self.assertEqual(set(sides), {"│"}, "text on a frame's side")
            self.assertEqual(set(bottom), {"─"}, "text on a frame's bottom")
        spilled = (con.ch != self.SENTINEL) & ~inside
        self.assertFalse(spilled.any(), f"{int(spilled.sum())} cells drawn outside the frame")

    def test_every_window(self):
        from hearthdelve.engine import codex, rendering as R
        st = self.st
        windows = {
            "intro": lambda c: R.render_intro(c, st),
            "chest, pack side": lambda c: R.render_storage(c, st, "pack", 0),
            "chest, chest side": lambda c: R.render_storage(c, st, "chest", 0),
            "pack": lambda c: R.render_inventory(c, st, 0, None),
            "equipment": lambda c: R.render_equipment(c, st),
            "character": lambda c: R.render_character(c, st),
            "relations": lambda c: R.render_relationships(c, st, 0),
            "craft": lambda c: R.render_craft(c, st, 0),
            "ship": lambda c: R.render_ship(c, st, 0),
            "eat": lambda c: R.render_eat(c, st, 0),
            "hall": lambda c: R.render_donate(c, st, 0),
            "log": lambda c: R.render_message_log(c, st, 0),
            "mail": lambda c: R.render_mail(c, st, 0),
            "quit": lambda c: R.render_quit(c, st),
            "world map": lambda c: R.render_world_map(c, st),
        }
        for t in range(len(R._JOURNAL_TABS)):
            windows[f"journal {t}"] = lambda c, t=t: R.render_journal(c, st, t)
        for v in ("Mossford", "Cinderhope", "Saltmere", "Fenwick"):
            windows[f"board {v}"] = lambda c, v=v: R.render_requests(c, st, 0, v)
        for pg in range(12):
            windows[f"codex {pg}"] = lambda c, pg=pg: codex.render_codex(c, st, pg, 0)
        for name, draw in windows.items():
            with self.subTest(window=name):
                self._check(draw)


if __name__ == "__main__":
    unittest.main()
