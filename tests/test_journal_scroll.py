"""The journal wraps a long row and scrolls a long page."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _con():
    return tcod.console.Console(80, 50, order="F")


def _text(con) -> str:
    return "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(con.height))


def _flat(s: str) -> str:
    return " ".join(s.replace("│", " ").split())


class TestTheJournalScrolls(unittest.TestCase):
    """The journal drew the first rows that fitted and cut the rest: from
    the third year the Goals page was longer than its window, and a goal's
    reward — at the end of its row — fell off the right edge."""

    def _year3(self):
        st = fresh_state(31)
        st.day = 2 * 112 + 3
        return st

    def _seen_by_scrolling(self, st, tab):
        from hearthdelve.engine import rendering
        seen, scroll = [], 0
        for _ in range(40):
            con = _con()
            got = rendering.render_journal(con, st, tab, scroll)
            seen.append(_text(con))
            if got < scroll:                              # clamped: that was the end
                break
            scroll = got + 6
        return "\n".join(seen)

    def test_every_goal_and_its_reward_can_be_read(self):
        from hearthdelve.data import content
        st = self._year3()
        seen = _flat(self._seen_by_scrolling(st, 0))
        goals = [q for q in content.QUESTS if q.year == st.year]
        self.assertGreater(len(goals), 5)
        for q in goals:
            with self.subTest(goal=q.title):
                self.assertIn(_flat(q.title[:20]), seen)
                self.assertIn(f"{_flat(q.desc)} (+{q.gold}g)", seen)   # the row's end, reward and all

    def test_the_scroll_is_clamped_and_reported(self):
        from hearthdelve.engine import rendering
        st = self._year3()
        end = rendering.render_journal(_con(), st, 0, 10_000)
        self.assertGreater(end, 0)                        # the page really is longer
        self.assertEqual(rendering.render_journal(_con(), st, 0, end), end)
        self.assertEqual(rendering.render_journal(_con(), st, 0, -5), 0)

    def test_the_keys_scroll_it_and_a_new_page_starts_at_the_top(self):
        from hearthdelve import screens
        st = self._year3()
        ui = screens.UI(st, None)
        scr = screens.JournalScreen()
        con = _con()
        from hearthdelve.engine import rendering
        end = rendering.render_journal(_con(), st, 0, 10_000)
        scr.handle(ui, "move", ("move", 0, 1))            # ↓ one row
        scr.render(ui, con)
        self.assertEqual(scr.scroll, 1)
        scr.handle(ui, "scroll", ("scroll", -1))          # PgDn
        scr.render(ui, con)
        self.assertEqual(scr.scroll, min(end, 1 + screens.JournalScreen.PAGE))
        scr.handle(ui, "scroll", ("scroll", 1))           # PgUp
        scr.render(ui, con)
        self.assertEqual(scr.scroll, max(0, min(end, 1 + screens.JournalScreen.PAGE)
                                         - screens.JournalScreen.PAGE))
        scr.handle(ui, "move", ("move", 1, 0))
        self.assertEqual((scr.tab, scr.scroll), (1, 0))

    def test_a_page_that_fits_does_not_scroll(self):
        from hearthdelve.engine import rendering
        st = fresh_state(31)
        con = _con()
        self.assertEqual(rendering.render_journal(con, st, 0, 7), 0)
        self.assertNotIn("scroll", _text(con))


if __name__ == "__main__":
    unittest.main()
