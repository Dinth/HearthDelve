"""Small goods that used to clear their ingredients by nothing at all."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestNoWorkForNothing(unittest.TestCase):
    def test_a_wolf_pelt_tans_into_two_leathers(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(111)
        inv = st.player.inventory
        for hide in (items.RAW_HIDE, items.BOAR_HIDE, items.WOLF_PELT):
            inv.add(hide, 1)
        opts = {o["inputs"][0][0]: o for o in
                crafting.machine_load_options(st, content.MACHINES["tanner"])}
        self.assertEqual(opts[items.WOLF_PELT].get("out_qty", 1), 2)
        self.assertEqual(opts[items.BOAR_HIDE].get("out_qty", 1), 1)
        for hide, o in opts.items():
            with self.subTest(hide=hide.name):
                made = items.LEATHER.value * o.get("out_qty", 1)
                self.assertGreaterEqual(made, hide.value * 1.25)

    def test_two_leathers_come_off_the_rack(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import crafting
        st = fresh_state(111)
        inv = st.player.inventory
        inv.add(items.WOLF_PELT, 1)
        mdef = content.MACHINES["tanner"]
        m = Machine(kind="tanner")
        opt = next(o for o in crafting.machine_load_options(st, mdef)
                   if o["inputs"][0][0] is items.WOLF_PELT)
        crafting.load_machine_choice(st, m, mdef, opt)
        self.assertEqual(m.out_qty, 2)
        self.assertEqual(inv.count(items.WOLF_PELT), 0)

    def test_charring_wood_is_worth_the_kiln(self):
        from hearthdelve.entities import items
        self.assertGreaterEqual(items.CHARCOAL.value, 2 * items.WOOD.value * 1.25)

    def test_charcoal_stays_the_cheap_fuel(self):
        from hearthdelve.entities import items
        self.assertLess(items.CHARCOAL.value, items.COKE.value)


if __name__ == "__main__":
    unittest.main()
