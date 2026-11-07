"""Villagers whose day is spent on the square actually get there.

The square's roaming walk stepped straight at the square, so a villager waking
behind a cottage wall never found the door: by mid-morning 61 of 70 square-goers
across five worlds were still wedged beside their homes, and a festival — when
the whole village gathers — gathered almost nobody.
"""
from __future__ import annotations

import random
import unittest

from tests.common import fresh_state


def _walk_the_morning(st, until_hour: int):
    """From 07:59 to ``until_hour``, stepping the villagers as play would (one
    update per 30 s of game time)."""
    from hearthdelve.game import village
    while st.time_minutes < 7 * 60 + 59:
        st.clock += 30
    village.update_npcs(st)                              # everyone is at home
    homes = {n.name: (n.x, n.y) for n in st.world.npcs}
    while st.time_minutes < until_hour * 60:
        st.clock += 30
        village.update_npcs(st)
    return homes


def _square_goers(st):
    from hearthdelve.game import village
    hour = (st.time_minutes // 60) % 24
    return [n for n in st.world.npcs
            if village.scheduled_spot(n, hour, st.weather, st.season, st.day_of_season) == "square"]


def _off_square(n):
    """Out of the square's range — or, for folk with no square (a camp), out of
    their home's, which is the anchor their roaming falls back to."""
    from hearthdelve.game import village
    sx, sy = n.spots.get("square") or n.spots["home"]
    return max(abs(n.x - sx), abs(n.y - sy)) > village._CHILD_RANGE + 1


class TestTheSquareFillsUp(unittest.TestCase):
    def test_an_ordinary_morning_gets_the_idle_folk_to_the_square(self):
        for seed in (6, 555):
            random.seed(seed)
            st = fresh_state(seed)
            st.day, st.weather = 2, "Clear"
            homes = _walk_the_morning(st, 10)
            goers = _square_goers(st)
            with self.subTest(seed=seed):
                self.assertGreater(len(goers), 8)
                self.assertEqual([n.name for n in goers if (n.x, n.y) == homes[n.name]], [])
                self.assertEqual([n.name for n in goers if _off_square(n)], [])

    def test_a_festival_gathers_the_village(self):
        from tests.test_festivals import FESTIVAL_DAY
        random.seed(11)
        st = fresh_state(11)
        st.day, st.weather = FESTIVAL_DAY, "Clear"
        _walk_the_morning(st, 11)
        goers = _square_goers(st)
        self.assertEqual(len(goers), len(st.world.npcs))  # the whole village is due there
        away = [n.name for n in goers if _off_square(n)]
        self.assertLessEqual(len(away), len(goers) // 10, away)

    def test_a_route_finds_the_door_a_straight_step_cannot(self):
        from hearthdelve.game import village
        st = fresh_state(555)
        neri = next(n for n in st.surface.npcs if n.name == "Neri")
        home, square = neri.spots["home"], neri.spots["square"]
        path = village._route(st.surface, home, square)
        self.assertTrue(path)
        steps = [home] + path
        for (ax, ay), (bx, by) in zip(steps, steps[1:]):
            self.assertEqual(max(abs(ax - bx), abs(ay - by)), 1)
            self.assertTrue(st.surface.walkable(bx, by))
        ex, ey = path[-1]
        self.assertLessEqual(max(abs(ex - square[0]), abs(ey - square[1])), 2)


if __name__ == "__main__":
    unittest.main()
