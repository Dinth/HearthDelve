"""A long carried-gear list pages, and its letters pick what they sit beside."""
from __future__ import annotations

import unittest
from unittest import mock

import tcod.console

from tests.common import fresh_state


def _text(con) -> str:
    return "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(con.height))


def _hoard(st):
    from hearthdelve.data import content
    for base in ("Dagger", "Sword", "Rapier", "Greatsword", "War Mace", "Spear"):
        for mat in ("copper", "bronze", "iron", "steel", "silver", "mithril", "adamantium"):
            st.player.inventory.add(content.make_gear(base, mat), 1)


class _UI:
    def __init__(self, state):
        self.state = state


class TestTheGearListPages(unittest.TestCase):
    """The list stopped at the window's edge with no way down, and past the
    alphabet its rows were drawn with a blank where the letter goes."""

    def test_every_piece_can_be_reached_and_has_a_letter(self):
        from hearthdelve import screens
        from hearthdelve.engine import rendering
        st = fresh_state(23)
        _hoard(st)
        gear = rendering.equippables(st)
        self.assertGreater(len(gear), 40)
        scr, ui, seen = screens.EquipmentScreen(), _UI(st), ""
        for _ in range(6):
            con = tcod.console.Console(80, 50, order="F")
            scr.render(ui, con)
            page = _text(con)
            self.assertNotIn("   - ", page)                 # no row without its letter
            seen += page
            scr.handle(ui, "scroll", ("scroll", -1))        # PgDn
        for it, _n, _ql in gear:
            self.assertIn(it.name[:22], seen)

    def test_a_letter_picks_the_row_on_the_page_shown(self):
        from hearthdelve import screens
        from hearthdelve.engine import rendering
        st = fresh_state(23)
        _hoard(st)
        scr, ui = screens.EquipmentScreen(), _UI(st)
        scr.handle(ui, "scroll", ("scroll", -1))
        scr.render(ui, tcod.console.Console(80, 50, order="F"))
        first, _shown = rendering.gear_page(st, scr.scroll)
        self.assertGreater(first, 0)
        want = rendering.equippables(st)[first + 2][0]
        with mock.patch.object(screens, "_pick_index",
                               lambda _e: len(rendering.PAPERDOLL_SLOTS) + 2):
            scr.on_raw(ui, None)
        self.assertIs(st.player.weapon, want)

    def test_a_short_list_is_drawn_as_before(self):
        from hearthdelve.engine import rendering
        st = fresh_state(23)
        n = len(rendering.equippables(st))
        self.assertEqual(rendering.gear_page(st, 7), (0, n))


if __name__ == "__main__":
    unittest.main()
