"""A waterskin: bat-wing membrane, filled at a well, drunk on the road."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _at_a_well(st):
    """Stand the farmer facing a well set down beside them."""
    from hearthdelve.world import tile
    p = st.player
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x, y = p.x + dx, p.y + dy
        if st.world.in_bounds(x, y) and (x, y) not in st.world.machines \
                and (x, y) not in st.world.crops:
            st.world.tiles[x, y] = tile.WELL
            p.facing = (dx, dy)
            return
    raise AssertionError("nowhere to sink a well")


class TestWaterskin(unittest.TestCase):
    def test_wings_fibre_and_wax_make_one(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(61)
        inv = st.player.inventory
        r = next(r for r in content.RECIPES if r.name == "Waterskin")
        for it, q in r.inputs:
            inv.add(it, q)
        self.assertTrue(crafting.craft(st, r))
        self.assertEqual(inv.count(items.WATERSKIN), 1)
        self.assertEqual(inv.count(items.BAT_WING), 0)
        cost = sum(it.value * q for it, q in r.inputs)
        self.assertGreaterEqual(items.WATERSKIN.value, cost * 1.25)

    def test_a_well_fills_every_empty_skin(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = fresh_state(62)
        inv = st.player.inventory
        inv.add(items.WATERSKIN, 3)
        _at_a_well(st)
        before = st.abs_minutes
        commands.do_grab(st)
        self.assertEqual(inv.count(items.FULL_WATERSKIN), 3)
        self.assertEqual(inv.count(items.WATERSKIN), 0)
        self.assertGreater(st.abs_minutes, before)       # drawing water takes a while

    def test_a_well_without_a_skin_gives_nothing(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = fresh_state(62)
        _at_a_well(st)
        commands.do_grab(st)
        self.assertEqual(st.player.inventory.count(items.FULL_WATERSKIN), 0)

    def test_a_drink_restores_stamina_and_keeps_the_skin(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, crafting
        st = fresh_state(63)
        p = st.player
        p.inventory.add(items.FULL_WATERSKIN, 1)
        p.energy = 10
        meals = st.stats.get("meals_eaten", 0)
        self.assertIn(items.FULL_WATERSKIN, [e[0] for e in crafting.edible_items(st)])
        commands._eat(st, items.FULL_WATERSKIN, 0)
        self.assertEqual(p.energy, 10 + items.FULL_WATERSKIN.energy)
        self.assertEqual(p.inventory.count(items.FULL_WATERSKIN), 0)
        self.assertEqual(p.inventory.count(items.WATERSKIN), 1)
        self.assertEqual(st.stats.get("meals_eaten", 0), meals)    # water is no meal
        self.assertNotIn(items.WATERSKIN, [e[0] for e in crafting.edible_items(st)])

    def test_a_well_mints_no_gold(self):
        from hearthdelve.entities import items
        self.assertEqual(items.FULL_WATERSKIN.value, items.WATERSKIN.value)

    def test_water_is_a_sip_beside_a_tonic(self):
        from hearthdelve.entities import items
        self.assertLess(items.FULL_WATERSKIN.energy, items.HERBAL_TONIC.energy / 2)

    def test_full_and_empty_survive_a_save(self):
        from hearthdelve.entities import items
        from hearthdelve.engine import save
        st = fresh_state(64)
        st.player.inventory.add(items.WATERSKIN, 1)
        st.player.inventory.add(items.FULL_WATERSKIN, 2)
        path = os.path.join(tempfile.mkdtemp(), "skin.sav")
        save.save(st, path)
        back = save.load(path)
        self.assertEqual(back.player.inventory.count(items.WATERSKIN), 1)
        self.assertEqual(back.player.inventory.count(items.FULL_WATERSKIN), 2)


if __name__ == "__main__":
    unittest.main()
