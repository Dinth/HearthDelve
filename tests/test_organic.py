"""Organic, not mechanical: what drifts day to day must not run on a fixed
rotation you could set a calendar by — but it must still be fixed for a given
world and day, so reloading never re-rolls it."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _blessings(seed, days):
    from hearthdelve.game import commands, projects
    st = fresh_state(seed)
    projects.get(st, "shrine")["state"] = "done"
    out = []
    for day in days:
        st.day = day
        st.stats.pop("blessed_day", None)
        commands._pray(st)
        out.append(st.player.buff)
    return out


class TestTheShrinesBlessingDrifts(unittest.TestCase):
    """The blessing was `_BLESSINGS[day % 5]`: the same five-day cycle in every
    world, forever."""

    def test_it_is_not_a_five_day_cycle(self):
        from hearthdelve.game import commands
        got = _blessings(3, range(10, 70))
        cycle = [commands._BLESSINGS[d % len(commands._BLESSINGS)] for d in range(10, 70)]
        self.assertNotEqual(got, cycle)
        self.assertEqual(set(got), set(commands._BLESSINGS))      # every boon still comes

    def test_it_is_fixed_for_the_day_and_differs_between_worlds(self):
        self.assertEqual(_blessings(3, range(10, 30)), _blessings(3, range(10, 30)))
        self.assertNotEqual(_blessings(3, range(10, 30)), _blessings(4, range(10, 30)))


class TestTheScriptoriumsLessonDrifts(unittest.TestCase):
    """The recipe studied was `pool[day % len(pool)]`, predictable a season
    ahead."""

    def test_it_is_not_the_days_index_into_the_pool(self):
        from hearthdelve.data import content
        from hearthdelve.game import commands, projects
        st = fresh_state(3)
        projects.get(st, "scriptorium")["state"] = "done"
        hits = 0
        for day in range(10, 40):
            st.day = day
            st.stats.pop("studied_day", None)
            pool = [r.name for r in content.RECIPES
                    if r.kind in ("cook", "remedy") and r.name not in st.known_recipes]
            before = set(st.known_recipes)
            commands._study(st)
            (learnt,) = st.known_recipes - before
            hits += learnt == pool[day % len(pool)]
        self.assertLess(hits, 10)


class TestVillagersDontRecite(unittest.TestCase):
    """A villager walked their lines in one fixed order, round after round,
    in every world."""

    def _lines(self, seed, rounds=4):
        from hearthdelve.game import village
        st = fresh_state(seed)
        npc = next(n for n in st.surface.npcs
                   if len(n.blurbs) >= 3 and n.role not in ("fisher", "forager", "forester", "elder"))
        out = []
        for _ in range(len(npc.blurbs) * rounds):
            npc.talked_today = True                  # just the chat, no first-talk extras
            out.append(village.talk(st, npc))
        return npc, out

    def test_every_line_gets_its_turn_each_round_in_a_drifting_order(self):
        npc, lines = self._lines(3)
        n = len(npc.blurbs)
        rounds = [lines[k * n:(k + 1) * n] for k in range(4)]
        for r in rounds:
            self.assertEqual(sorted(r), sorted(npc.blurbs))
        self.assertTrue(any(r != list(npc.blurbs) for r in rounds))
        self.assertGreater(len({tuple(r) for r in rounds}), 1)
        self.assertTrue(all(a != b for a, b in zip(lines, lines[1:])), "a line twice running")

    def test_the_same_world_says_the_same_and_another_differs(self):
        self.assertEqual(self._lines(3)[1], self._lines(3)[1])
        self.assertNotEqual(self._lines(3)[1], self._lines(5)[1])


if __name__ == "__main__":
    unittest.main()
