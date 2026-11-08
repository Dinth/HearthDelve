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


if __name__ == "__main__":
    unittest.main()
