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
    not be filled at home. Tomas will sink one: a well is a tradesman's job."""

    def _row(self, st):
        from hearthdelve.game import village
        return next(r for r in village.shop_entries("carpenter", st)
                    if r.kind == "commission" and r.build == "well")

    def _order(self, st):
        from hearthdelve.game import village
        row = self._row(st)
        p = st.player
        p.gold = row.price
        for it, q in row.mats:
            p.inventory.add(it, q)
        village.purchase(st, row)
        return row

    def _site(self, st):
        from hearthdelve.game import husbandry
        px, py = st.player.x, st.player.y
        for d in range(2, 14):
            for dx in range(-d, d + 1):
                for dy in range(-d, d + 1):
                    if husbandry.place_commission_at(st, px + dx, py + dy):
                        return px + dx, py + dy
        self.fail("no ground for a well near the house")

    def test_the_farmer_cannot_dig_one_alone(self):
        from hearthdelve.data import content
        self.assertNotIn("Well", [r.name for r in content.RECIPES])

    def test_tomas_takes_gold_and_stone_for_it(self):
        from hearthdelve.entities import items
        st = fresh_state(65)
        row = self._order(st)
        self.assertEqual(st.pending_build, "well")
        self.assertEqual(st.player.gold, 0)
        self.assertEqual(st.player.inventory.count(items.STONE), 0)
        self.assertIn(items.STONE, [it for it, _q in row.mats])

    def test_it_takes_one_tile_and_two_mornings(self):
        self._dug()

    def _dug(self):
        from hearthdelve.game import husbandry
        from hearthdelve.world import tile
        st = fresh_state(65)
        self._order(st)
        spot = self._site(st)
        self.assertEqual(st.pending_build, "")
        self.assertEqual(int((st.surface.tiles == tile.SCAFFOLD).sum()), 1)
        self.assertNotEqual(st.surface.tile_at(*spot).kind, "well")     # not yet
        st.day += husbandry.BUILD_DAYS + 1
        husbandry._finish_construction(st)
        self.assertEqual(st.surface.tile_at(*spot).kind, "well")
        self.assertNotIn(spot, st.surface.machines)
        return st, spot

    def test_the_finished_well_fills_a_skin_and_keeps(self):
        from hearthdelve.entities import items
        from hearthdelve.engine import save
        from hearthdelve.game import commands
        st, (wx, wy) = self._dug()
        p = st.player
        w = st.surface
        dx, dy = next((dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                      if w.walkable(wx + dx, wy + dy))
        p.x, p.y, p.facing = wx + dx, wy + dy, (-dx, -dy)
        p.inventory.add(items.WATERSKIN, 1)
        commands.do_grab(st)
        self.assertEqual(p.inventory.count(items.FULL_WATERSKIN), 1)
        path = os.path.join(tempfile.mkdtemp(), "well.sav")
        save.save(st, path)
        self.assertEqual(save.load(path).surface.tile_at(wx, wy).kind, "well")

    def test_a_half_dug_well_survives_a_save(self):
        from hearthdelve.engine import save
        st = fresh_state(65)
        self._order(st)
        spot = self._site(st)
        path = os.path.join(tempfile.mkdtemp(), "site.sav")
        save.save(st, path)
        back = save.load(path)
        self.assertEqual(back.surface.machines[spot].build_kind, "well")


if __name__ == "__main__":
    unittest.main()
