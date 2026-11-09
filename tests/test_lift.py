"""The dwarven lift: Khazgrim's old ore-shaft cage rides, for a fare, to any
fifth floor of the mine you've reached on foot, and back. Deep delves used to
mean walking down from the first floor every time."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _in_khazgrim():
    from hearthdelve.game import commands
    st = fresh_state(2)
    commands._cheat_go(st, "west:khazgrim")
    st.player.gold = 5000
    return st


def _walk_down_to(st, depth):
    from hearthdelve.game import delve
    while st.depth < depth:
        delve.descend(st)


class TestTheLiftStands(unittest.TestCase):
    def test_khazgrim_has_its_lift(self):
        from hearthdelve.game import lift
        st = _in_khazgrim()
        self.assertIsNotNone(lift.station(st.world))

    def test_every_fifth_floor_of_the_mine_has_a_station_by_the_stairs(self):
        from hearthdelve.game import delve, lift
        st = _in_khazgrim()
        site = delve._site(st)
        for depth in (5, 10, 15):
            gm = delve.build_floor(st, "dwarfhold", site, depth)
            at = lift.station(gm)
            self.assertIsNotNone(at, depth)
            self.assertLessEqual(max(abs(at[0] - gm.stairs_up[0]), abs(at[1] - gm.stairs_up[1])), 1)
        self.assertIsNone(lift.station(delve.build_floor(st, "dwarfhold", site, 7)))
        self.assertIsNone(lift.station(delve.build_floor(st, "mine", site, 10)))   # dwarves' mine only


class TestWhereItGoes(unittest.TestCase):
    def test_only_the_fifth_floors_you_have_reached(self):
        from hearthdelve.game import lift
        st = _in_khazgrim()
        self.assertEqual(lift.stops(st), [])                  # nothing below reached yet
        _walk_down_to(st, 11)
        self.assertEqual(st.stats["dwarfhold_deepest"], 11)
        self.assertEqual(lift.stops(st), [4, 5, 10])

    def test_an_older_save_that_found_the_underriver_is_credited_generously(self):
        from hearthdelve.game import lift
        st = _in_khazgrim()
        st.stats.pop("dwarfhold_deepest", None)
        st.stats.update(found_underriver=1, deepest_depth=15)
        self.assertEqual(lift.stops(st), [5, 10, 15])


class TestRiding(unittest.TestCase):
    def _deep_then_home(self):
        from hearthdelve.game import delve, lift
        st = _in_khazgrim()
        _walk_down_to(st, 10)
        while st.depth > 4:                                   # back up on foot
            delve.ascend(st)
        return st

    def test_ride_down_for_a_fare_and_step_out_by_the_cage(self):
        from hearthdelve.game import lift
        st = self._deep_then_home()
        gold, minutes = st.player.gold, st.abs_minutes
        self.assertTrue(lift.ride(st, 10))
        self.assertEqual((st.depth, st.world.depth), (10, 10))
        self.assertEqual(gold - st.player.gold, lift.FARE_PER_FLOOR * 6)
        self.assertGreater(st.abs_minutes, minutes)
        at = lift.station(st.world)
        self.assertLessEqual(max(abs(st.player.x - at[0]), abs(st.player.y - at[1])), 1)

    def test_and_ride_back_up_to_khazgrim(self):
        from hearthdelve.game import lift
        from hearthdelve.world import dwarftown
        st = self._deep_then_home()
        lift.ride(st, 10)
        self.assertTrue(lift.ride(st, dwarftown.TOWN_DEPTH))
        self.assertEqual(st.depth, dwarftown.TOWN_DEPTH)
        self.assertIn(st.world.npcs[0], st.dwarves)

    def test_no_fare_no_ride(self):
        from hearthdelve.game import lift
        st = self._deep_then_home()
        st.player.gold = 10
        self.assertFalse(lift.ride(st, 10))
        self.assertEqual((st.depth, st.player.gold), (4, 10))

    def test_nothing_gets_a_turn_on_you_while_the_cage_comes(self):
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game import lift
        st = self._deep_then_home()
        lift.ride(st, 10)
        p = st.player
        brute = Mob("Brute", "B", (200, 80, 80), 99, 99, 4, "chase", p.x + 1, p.y,
                    dv=0, pv=0, to_hit=50, dmg=(20, 20))
        brute.awake = True
        st.world.monsters.append(brute)
        hp = p.hp
        lift.ride(st, 4)
        self.assertEqual(st.player.hp, hp)

    def test_a_ride_survives_a_save(self):
        from hearthdelve.engine import save
        from hearthdelve.game import lift
        st = self._deep_then_home()
        lift.ride(st, 10)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            back = save.load(path)
        self.assertEqual((back.depth, back.player.x, back.player.y), (10, st.player.x, st.player.y))
        self.assertIsNotNone(lift.station(back.world))
        self.assertEqual(lift.stops(back), [4, 5])


class TestTheLiftScreen(unittest.TestCase):
    def test_grabbing_the_cage_opens_its_stops(self):
        import tcod.console
        from hearthdelve import screens
        from hearthdelve.engine import rendering
        from hearthdelve.game import delve, lift
        st = _in_khazgrim()
        _walk_down_to(st, 10)
        while st.depth > 4:
            delve.ascend(st)
        lx, ly = lift.station(st.world)
        st.player.x, st.player.y = lx, ly + 1
        st.player.facing = (0, -1)
        ui = screens.UI(st)
        ui.top.handle(ui, "grab", ("grab",))
        self.assertIsInstance(ui.top, screens.LiftScreen)
        con = tcod.console.Console(80, 50, order="F")
        ui.top.render(ui, con)
        text = "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(50))
        self.assertIn("Floor 10", text)
        ui.top.handle(ui, "move", ("move", 0, 1))
        ui.top.handle(ui, "confirm", ("confirm",))
        self.assertIs(ui.top, ui.play)
        self.assertEqual(st.depth, 10)


if __name__ == "__main__":
    unittest.main()
