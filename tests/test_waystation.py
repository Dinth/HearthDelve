"""The deep couriers' waystation on every Deep Sanctum (each tenth floor): a
load left in its coffer reaches your farm chest by morning, for a fee — out
of your pack, and safe from a faint."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from tests.common import fresh_state


def _in_a_sanctum(depth=10):
    from hearthdelve.game import delve
    st = fresh_state(2)
    mouth = sorted(q for q, k in st.surface.dungeon_kind.items() if k == "mine")[0]
    st.player.x, st.player.y = mouth
    delve.enter(st, "mine")
    while st.depth < depth:
        delve.descend(st)
    st.player.gold = 100
    return st


def _station(gm):
    return next((pos for pos, m in gm.machines.items() if m.kind == "waystation"), None)


class TestEverySanctumKeepsOne(unittest.TestCase):
    def test_by_the_stairs_on_every_tenth_floor_and_no_other(self):
        from hearthdelve.game import delve
        st = _in_a_sanctum(10)
        at = _station(st.world)
        self.assertIsNotNone(at)
        up = st.world.stairs_up
        self.assertLessEqual(max(abs(at[0] - up[0]), abs(at[1] - up[1])), 1)
        site = delve._site(st)
        self.assertIsNotNone(_station(delve.build_floor(st, "mine", site, 20)))
        self.assertIsNone(_station(delve.build_floor(st, "mine", site, 9)))

    def test_the_dwarves_tenth_floor_has_both_the_lift_and_the_coffer(self):
        from hearthdelve.game import delve, lift
        st = _in_a_sanctum(10)
        gm = delve.build_floor(st, "dwarfhold", delve._site(st), 10)
        self.assertIsNotNone(_station(gm))
        self.assertIsNotNone(lift.station(gm))
        self.assertNotEqual(_station(gm), lift.station(gm))


class TestSendingItUp(unittest.TestCase):
    def test_a_load_leaves_the_pack_for_a_fee_and_reaches_the_chest_by_morning(self):
        from hearthdelve.entities import items
        from hearthdelve.game import farming, waystation
        st = _in_a_sanctum()
        st.player.inventory.add(items.IRON_ORE, 12)
        self.assertTrue(waystation.send(st, items.IRON_ORE, 12, 0))
        self.assertEqual(st.player.inventory.count(items.IRON_ORE), 0)
        self.assertEqual(st.player.gold, 100 - waystation.COURIER_FEE)
        self.assertEqual(st.storage.count(items.IRON_ORE), 0)            # not yet
        farming.sleep(st)
        self.assertEqual(st.storage.count(items.IRON_ORE), 12)
        self.assertTrue(st.couriered.is_empty())

    def test_no_fee_no_courier(self):
        from hearthdelve.entities import items
        from hearthdelve.game import waystation
        st = _in_a_sanctum()
        st.player.gold = 2
        st.player.inventory.add(items.IRON_ORE, 3)
        self.assertFalse(waystation.send(st, items.IRON_ORE, 3, 0))
        self.assertEqual(st.player.inventory.count(items.IRON_ORE), 3)

    def test_what_s_on_its_way_is_safe_from_a_faint(self):
        from hearthdelve.entities import items
        from hearthdelve.game import farming, waystation
        st = _in_a_sanctum()
        st.player.inventory.add(items.IRON_ORE, 8)
        st.player.inventory.add(items.COAL, 5)
        waystation.send(st, items.IRON_ORE, 8, 0)
        farming.collapse(st, "You black out.")
        self.assertEqual(st.player.inventory.count(items.COAL), 0)       # loose loot is lost…
        self.assertEqual(st.storage.count(items.IRON_ORE), 8)            # …the coffer's isn't

    def test_it_survives_a_save_and_an_old_save_has_nothing_on_its_way(self):
        from hearthdelve.engine import save
        from hearthdelve.entities import items
        from hearthdelve.game import waystation
        st = _in_a_sanctum()
        st.player.inventory.add(items.IRON_ORE, 4)
        waystation.send(st, items.IRON_ORE, 4, 0)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            self.assertEqual(save.load(path).couriered.count(items.IRON_ORE), 4)
            with open(path) as fh:
                data = json.load(fh)
            del data["couriered"]
            with open(path, "w") as fh:
                json.dump(data, fh)
            self.assertTrue(save.load(path).couriered.is_empty())


class TestTheCoffer(unittest.TestCase):
    def test_grabbing_it_opens_it_and_space_sends_the_lot(self):
        from hearthdelve import screens
        from hearthdelve.entities import items
        st = _in_a_sanctum()
        st.player.inventory.add(items.IRON_ORE, 3)
        st.player.inventory.add(items.COAL, 2)
        x, y = _station(st.world)
        st.player.x, st.player.y = x, y
        ui = screens.UI(st)
        ui.play.handle(ui, "grab", ("grab",))
        self.assertIsInstance(ui.top, screens.WaystationScreen)
        ui.top.handle(ui, "use", ("use",))
        self.assertTrue(st.player.inventory.is_empty())
        self.assertEqual(st.couriered.count(items.COAL), 2)


if __name__ == "__main__":
    unittest.main()
