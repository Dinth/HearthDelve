"""Bellows beside a furnace, and a scarecrow over the crops."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _recipe(name):
    from hearthdelve.data import content
    return next(r for r in content.RECIPES if r.name == name)


def _furnace(st, with_bellows):
    from hearthdelve.entities.machine import Machine
    p = st.player
    pos = (p.x + 3, p.y + 3)
    m = Machine(kind="furnace")
    st.surface.machines[pos] = m
    if with_bellows:
        st.surface.machines[(pos[0] + 1, pos[1] + 1)] = Machine(kind="bellows")
    return m


def _smelt_minutes(st, m):
    from hearthdelve.data import content
    from hearthdelve.entities import items
    from hearthdelve.game import crafting
    inv = st.player.inventory
    inv.add(items.COPPER_ORE, 1)
    inv.add(items.COAL, 1)
    mdef = content.MACHINES["furnace"]
    opt = next(o for o in crafting.machine_load_options(st, mdef)
               if o["output"] is items.COPPER_BAR)
    crafting.load_machine_choice(st, m, mdef, opt)
    return m.ready_at - st.abs_minutes


class TestBellows(unittest.TestCase):
    def test_bat_wings_and_planks_build_them(self):
        from hearthdelve.entities import items
        self.assertEqual(dict(_recipe("Forge Bellows").inputs),
                         {items.BAT_WING: 4, items.TIMBER_PLANK: 3})

    def test_a_furnace_beside_them_burns_a_third_faster(self):
        from hearthdelve.data import content
        st0 = fresh_state(171)
        plain = _smelt_minutes(st0, _furnace(st0, False))
        st1 = fresh_state(171)
        fed = _smelt_minutes(st1, _furnace(st1, True))
        self.assertEqual(fed, round(plain * content.BELLOWS_TIME))
        self.assertLess(fed, plain)

    def test_they_must_stand_beside_it(self):
        from hearthdelve.entities.machine import Machine
        st0 = fresh_state(171)
        plain = _smelt_minutes(st0, _furnace(st0, False))
        st = fresh_state(171)
        m = _furnace(st, False)
        p = st.player
        st.surface.machines[(p.x + 6, p.y + 3)] = Machine(kind="bellows")   # three tiles off
        self.assertEqual(_smelt_minutes(st, m), plain)

    def test_they_do_nothing_for_a_keg(self):
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import crafting
        st = fresh_state(171)
        p = st.player
        keg = Machine(kind="keg")
        st.surface.machines[(p.x + 3, p.y + 3)] = keg
        st.surface.machines[(p.x + 4, p.y + 3)] = Machine(kind="bellows")
        self.assertTrue(crafting.bellows_beside(st, keg))        # they stand there...
        from hearthdelve.data import content
        self.assertNotIn("keg", content.BELLOWS_FIRES)           # ...but feed only a fire

    def test_they_survive_a_save(self):
        from hearthdelve.engine import save
        from hearthdelve.entities.machine import Machine
        st = fresh_state(171)
        pos = (st.player.x + 4, st.player.y + 4)
        st.surface.machines[pos] = Machine(kind="bellows")
        path = os.path.join(tempfile.mkdtemp(), "b.sav")
        save.save(st, path)
        self.assertEqual(save.load(path).surface.machines[pos].kind, "bellows")


class TestScarecrow(unittest.TestCase):
    """Only a firecracker kept deer off the crops, for three days at a time."""

    def _field(self, guarded):
        from hearthdelve.data import content
        from hearthdelve.entities.machine import Machine
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game.farming import CropPlot
        st = fresh_state(172)
        st.world.monsters.clear()
        p = st.player
        plot = (p.x + 6, p.y + 6)
        st.world.crops[plot] = CropPlot(crop=content.PARSNIP, days_grown=1, watered=True)
        if guarded:
            st.world.machines[(plot[0] + 2, plot[1])] = Machine(kind="scarecrow")
        deer = Mob("Deer", "d", (200, 170, 150), 20, 20, 2, "skittish", plot[0] + 1, plot[1],
                   kind="wildlife", diet="crops")
        st.world.monsters.append(deer)
        return st, plot, deer

    def test_an_unguarded_crop_is_eaten(self):
        from hearthdelve.game import wildlife
        st, plot, deer = self._field(False)
        self.assertEqual(wildlife._nearest_food(st, deer), plot)
        self.assertTrue(wildlife._eat_crops(st, deer))
        self.assertNotIn(plot, st.world.crops)

    def test_a_guarded_one_is_left_alone(self):
        from hearthdelve.game import wildlife
        st, plot, deer = self._field(True)
        self.assertIsNone(wildlife._nearest_food(st, deer))
        self.assertFalse(wildlife._eat_crops(st, deer))
        self.assertIn(plot, st.world.crops)

    def test_its_watch_has_an_edge(self):
        from hearthdelve.data import content
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import crafting
        st = fresh_state(172)
        x, y = st.player.x + 10, st.player.y + 10
        st.world.machines[(x, y)] = Machine(kind="scarecrow")
        r = content.SCARECROW_REACH
        self.assertTrue(crafting.scarecrow_guards(st.world, x + r, y - r))
        self.assertFalse(crafting.scarecrow_guards(st.world, x + r + 1, y))

    def test_bears_still_come_for_the_honey(self):
        from hearthdelve.entities.machine import Machine
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game import wildlife
        st = fresh_state(172)
        st.world.monsters.clear()
        p = st.player
        hive = (p.x + 6, p.y + 6)
        st.world.machines[hive] = Machine(kind="beehive", has_queen=True)
        st.world.machines[(hive[0] + 1, hive[1])] = Machine(kind="scarecrow")
        bear = Mob("Bear", "B", (150, 110, 80), 40, 40, 2, "defensive", hive[0] - 2, hive[1],
                   kind="wildlife", diet="honey")
        self.assertEqual(wildlife._nearest_food(st, bear), hive)

    def test_wood_straw_and_fibre_build_one(self):
        from hearthdelve.entities import items
        self.assertIn(items.STRAW, dict(_recipe("Scarecrow").inputs))


if __name__ == "__main__":
    unittest.main()
