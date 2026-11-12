"""A blow that lands during a meal eaten from the pack screen strikes you down."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


class _UI:
    def __init__(self, state):
        self.state, self.popped = state, 0

    def pop(self):
        self.popped += 1


class TestEatingFromThePackCanFellYou(unittest.TestCase):
    """The eat menu checked for a faint after each bite; the pack screen's
    Enter did not, so a meal there could leave you below zero and still
    reading your pack — and a remedy next would bring you back."""

    def test_a_blow_mid_meal_blacks_you_out(self):
        from hearthdelve import screens
        from hearthdelve.entities import items
        from hearthdelve.game import turns
        st = fresh_state(23)
        p = st.player
        p.inventory.slots[:] = []
        p.inventory.add(items.BREAD, 2)
        day = st.day

        def blow(state, *_a, **_k):                      # something bites as you chew
            state.player.hp -= 10_000

        scr, ui = screens.InventoryScreen(), _UI(st)
        with mock.patch.object(turns, "advance_time", blow):
            scr.handle(ui, "confirm", ("confirm",))
        self.assertGreater(p.hp, 0)
        self.assertEqual(st.day, day + 1)                # carried to bed
        self.assertEqual(ui.popped, 1)                   # and out of the pack

    def test_a_quiet_meal_keeps_the_pack_open(self):
        from hearthdelve import screens
        from hearthdelve.entities import items
        st = fresh_state(23)
        st.world.monsters[:] = []
        p = st.player
        p.inventory.slots[:] = []
        p.inventory.add(items.BREAD, 2)
        scr, ui = screens.InventoryScreen(), _UI(st)
        scr.handle(ui, "confirm", ("confirm",))
        self.assertEqual((p.inventory.count(items.BREAD), ui.popped), (1, 0))


if __name__ == "__main__":
    unittest.main()
