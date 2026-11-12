"""Putting on a ring wears the copy you picked, not the plainest one you hold."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


def _jewel():
    from hearthdelve.data import content
    return next(iter(content.JEWEL_EFFECT))


class TestTheChosenCopyIsWorn(unittest.TestCase):
    """Equipping took 'one, lowest stars first' — right for cooking with the
    worst egg, wrong for jewellery, whose effect scales with its stars."""

    def _holding(self):
        st = fresh_state(23)
        j = _jewel()
        st.player.inventory.add(j, 1, quality=0)
        st.player.inventory.add(j, 1, quality=5)
        return st, j

    def _slot(self, st, j):
        return next(s for s, it in st.player.equipment.items() if it is j)

    def test_the_picked_stars_go_on(self):
        from hearthdelve.game import commands
        for pick, left in ((5, 0), (0, 5)):
            st, j = self._holding()
            commands._equip(st, j, pick)
            with self.subTest(pick=pick):
                self.assertEqual(st.player.equip_quality[self._slot(st, j)], pick)
                self.assertEqual([ql for it, _n, ql in st.player.inventory.slots if it is j], [left])

    def test_with_no_copy_named_the_finest_goes_on(self):
        from hearthdelve.game import commands
        st, j = self._holding()
        commands._equip(st, j)
        self.assertEqual(st.player.equip_quality[self._slot(st, j)], 5)

    def test_the_equipment_screen_wears_the_row_picked(self):
        from hearthdelve import screens
        from hearthdelve.engine import rendering
        st, j = self._holding()
        gear = rendering.equippables(st)
        row = next(i for i, (it, _n, ql) in enumerate(gear) if it is j and ql == 5)
        letter = rendering.INV_LETTERS[len(rendering.PAPERDOLL_SLOTS) + row]

        class _UI:
            state = st
        with mock.patch.object(screens, "_pick_index",
                                        lambda _e: rendering.INV_LETTERS.index(letter)):
            screens.EquipmentScreen().on_raw(_UI(), None)
        self.assertEqual(st.player.equip_quality[self._slot(st, j)], 5)

    def test_nothing_is_worn_from_an_empty_pack(self):
        from hearthdelve.game import commands
        st = fresh_state(23)
        j = _jewel()
        commands._equip(st, j)
        self.assertNotIn(j, st.player.equipment.values())


if __name__ == "__main__":
    unittest.main()
