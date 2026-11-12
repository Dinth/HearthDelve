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


class TestAWellOfYourOwn(unittest.TestCase):
    """Wells stood only in the villages and the dwarf hall, so a skin could
    not be filled at home."""

    def _dig(self, st):
        from hearthdelve.data import content
        from hearthdelve.game import crafting, land
        p = st.player
        r = next(r for r in content.RECIPES if r.name == "Well")
        for it, q in r.inputs:
            p.inventory.add(it, q)
        w = st.world
        def open_ground(x, y):
            return (w.in_bounds(x, y) and w.tile_at(x, y).name in land.FENCEABLE
                    and (x, y) not in w.machines and (x, y) not in w.crops
                    and (x, y) not in w.trees and not land.owned_by_other(st, x, y))
        hx, hy = p.x, p.y
        for d in range(1, 12):                       # the yard by the door
            for x in range(hx - d, hx + d + 1):
                for y in range(hy - d, hy + d + 1):
                    if open_ground(x, y) and open_ground(x + 1, y):
                        p.x, p.y, p.facing = x, y, (1, 0)
                        return crafting.craft(st, r), (x + 1, y), r
        self.fail("no open ground beside the farmer")

    def test_it_is_dug_where_you_face_and_fills_a_skin(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = fresh_state(65)
        ok, spot, r = self._dig(st)
        self.assertTrue(ok)
        self.assertEqual(st.world.tile_at(*spot).kind, "well")
        for it, _q in r.inputs:
            self.assertEqual(st.player.inventory.count(it), 0)
        st.player.inventory.add(items.WATERSKIN, 1)
        commands.do_grab(st)
        self.assertEqual(st.player.inventory.count(items.FULL_WATERSKIN), 1)

    def test_it_is_still_there_after_a_save(self):
        from hearthdelve.engine import save
        st = fresh_state(65)
        _ok, spot, _r = self._dig(st)
        path = os.path.join(tempfile.mkdtemp(), "well.sav")
        save.save(st, path)
        back = save.load(path)
        self.assertEqual(back.world.tile_at(*spot).kind, "well")

    def test_not_underground(self):
        from hearthdelve.data import content
        from hearthdelve.game import crafting
        from tests.test_noise import _below
        st = _below()
        r = next(r for r in content.RECIPES if r.name == "Well")
        for it, q in r.inputs:
            st.player.inventory.add(it, q)
        self.assertFalse(crafting.craft(st, r))
        self.assertEqual(st.player.inventory.count(r.inputs[0][0]), r.inputs[0][1])


if __name__ == "__main__":
    unittest.main()
