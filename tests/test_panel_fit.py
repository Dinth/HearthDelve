"""The status panel keeps its afflictions and its bars inside itself."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _con():
    return tcod.console.Console(80, 50, order="F")


def _text(con) -> str:
    return "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(con.height))


class TestThePanelFitsItsAfflictions(unittest.TestCase):
    """Two wounds at once ran off the status panel ("≈ Bleedin"), and a
    third never showed at all."""

    def _tags(self, status):
        from hearthdelve.engine import constants as C, rendering
        from hearthdelve.game.combat import STATUS, is_disease
        room = C.PANEL_W - 3
        tags = rendering.affliction_tags(status, STATUS, is_disease, room)
        return tags, room

    def test_one_is_written_out(self):
        tags, _room = self._tags({"poison": 4})
        self.assertEqual([t for _c, t, _col in tags], ["☠ Poisoned"])

    def test_several_all_show_and_all_fit(self):
        for status in ({"poison": 4, "bleed": 3}, {"poison": 4, "bleed": 3, "burn": 2},
                       {"poison": 4, "bleed": 3, "burn": 2, "sick": 6}):
            tags, room = self._tags(status)
            with self.subTest(n=len(status)):
                self.assertEqual(len(tags), len(status))
                col, text, _colour = tags[-1]
                self.assertLessEqual(col + len(text), room)

    def test_an_illness_keeps_its_days(self):
        tags, _room = self._tags({"poison": 4, "bleed": 3, "burn": 2, "sick": 6})
        self.assertTrue(any("6d" in t for _c, t, _col in tags))
        tags, _room = self._tags({"sick": 6})
        self.assertIn("6d", tags[0][1])

    def test_the_panel_draws_them_inside_itself(self):
        from hearthdelve.engine import constants as C, rendering
        st = fresh_state(31)
        st.player.status = {"poison": 4, "bleed": 3, "burn": 2}
        con = _con()
        rendering.render_panel(con, st, 0.0)
        row = "".join(chr(c) for c in con.ch[C.VIEW_W:, 7])
        for sign in "☠≈♨":
            self.assertIn(sign, row)


class TestABarStaysInItsFrame(unittest.TestCase):
    """Health over the maximum pushed the bar out through its own numbers."""

    def _bar(self, hp, max_hp):
        from hearthdelve.engine import constants as C, rendering
        st = fresh_state(31)
        st.player.hp, st.player.max_hp = hp, max_hp
        con = _con()
        rendering.render_panel(con, st, 0.0)
        return "".join(chr(c) for c in con.ch[C.VIEW_W:, 6])

    def test_over_full_is_a_full_bar_and_its_numbers(self):
        row = self._bar(90, 50)
        self.assertEqual(row.count("█"), 12)
        self.assertIn("90/50", row)

    def test_below_nothing_is_an_empty_bar(self):
        row = self._bar(-4, 50)
        self.assertEqual((row.count("█"), row.count("·")), (0, 12))


if __name__ == "__main__":
    unittest.main()
