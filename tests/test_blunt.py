"""Blunt weapons cave armour in: a mace or a warhammer ignores a third of the
target's Protection. Their descriptions always said so ("shrugs off armour",
"caves in armour"); the blow never did."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


def _pv_met(held):
    """The Protection a blow from `held` meets on a PV-9 foe."""
    from hearthdelve.entities.monster import Mob
    from hearthdelve.game import combat
    st = fresh_state(2)
    p = st.player
    p.hotbar[p.active_slot] = held
    foe = Mob("Knight", "K", (200, 200, 200), 50, 50, 1, "chase", p.x + 1, p.y, dv=0, pv=9)
    st.world.monsters.append(foe)
    with mock.patch.object(combat, "_resolve", return_value=None) as resolve:
        combat.player_attack(st, foe)
    return resolve.call_args.args[5]


class TestBluntWeaponsCaveArmourIn(unittest.TestCase):
    def test_a_mace_meets_two_thirds_of_the_armour(self):
        from hearthdelve.data import content
        self.assertEqual(_pv_met(content.make_gear("War Mace", "iron", "", "", ())), 6)
        self.assertEqual(_pv_met(content.make_gear("Warhammer", "steel", "", "", ())), 6)

    def test_a_blade_meets_all_of_it(self):
        from hearthdelve.data import content
        self.assertEqual(_pv_met(content.make_gear("Sword", "iron", "", "", ())), 9)

    def test_a_blunt_tool_is_no_mace(self):
        from hearthdelve.entities import items
        self.assertEqual(_pv_met(items.WATERING_CAN), 9)

    def test_even_light_armour_feels_it(self):
        from hearthdelve.data import content
        from hearthdelve.game import combat
        st = fresh_state(2)
        st.player.hotbar[st.player.active_slot] = content.make_gear("War Mace", "iron", "", "", ())
        self.assertEqual([combat.crushed_pv(st, pv) for pv in (0, 1, 2, 3, 4)], [0, 0, 1, 2, 2])

    def test_it_lands_harder_through_heavy_armour(self):
        """End to end: the same roll deals more through PV 9 with a mace."""
        from hearthdelve.game import combat
        hit_mace = combat.soak(10, 6)
        hit_blade = combat.soak(10, 9)
        self.assertGreater(hit_mace, hit_blade)


if __name__ == "__main__":
    unittest.main()
