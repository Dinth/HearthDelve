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


class TestTheVillageKeepsLooseHours(unittest.TestCase):
    """Every adult downed tools and went home on the stroke of 13:00 (and to
    the inn on the stroke of 19:00), the same in every world."""

    def _lunch_minutes(self, seed, day):
        """The minute of the day each working adult heads home for lunch."""
        from hearthdelve.game import village
        st = fresh_state(seed)
        st.day, st.weather = day, "Clear"
        from hearthdelve.engine import constants as C

        def spot(n, minute):
            st.clock = (minute - C.DAY_START_MIN) * 60      # the clock counts from 06:00
            return village.scheduled_spot(n, village.npc_hour(st, n), st.weather, st.season,
                                          st.day_of_season)
        working = [n for n in st.surface.npcs
                   if n.role != "child" and spot(n, 11 * 60) != "home"]
        went = {}
        for n in working:
            went[n.name] = next(m for m in range(11 * 60, 15 * 60) if spot(n, m) == "home")
        return went

    def test_folk_head_home_at_their_own_times(self):
        went = self._lunch_minutes(3, 2)
        self.assertGreater(len(set(went.values())), 10)
        self.assertTrue(all(12 * 60 + 15 <= m <= 13 * 60 + 45 for m in went.values()))

    def test_the_hours_shift_with_the_day(self):
        self.assertEqual(self._lunch_minutes(3, 2), self._lunch_minutes(3, 2))
        self.assertNotEqual(self._lunch_minutes(3, 2), self._lunch_minutes(3, 3))


def _onsets(signal, seconds, step=0.02):
    """The moments `signal(t)` switches on, sampled over `seconds`."""
    out, was = [], False
    for k in range(int(seconds / step)):
        t = k * step
        now = signal(t)
        if now and not was:
            out.append(round(t, 2))
        was = now
    return out


class TestTheSkyKeepsNoBeat(unittest.TestCase):
    """Lightning struck every 6.5 s, the caldera erupted every 41 s, flocks
    crossed on a fixed period each, and every finished machine glinted on one
    shared 1-second beat."""

    def _gaps(self, onsets):
        return {round(b - a, 1) for a, b in zip(onsets, onsets[1:])}

    def test_lightning_strikes_at_irregular_moments(self):
        from hearthdelve.engine import anim
        strikes = _onsets(lambda t: anim.lightning(t, 7) > 0.5, 200)
        self.assertGreater(len(strikes), 15)
        self.assertGreater(len(self._gaps(strikes)), 5)
        self.assertEqual(strikes, _onsets(lambda t: anim.lightning(t, 7) > 0.5, 200))

    def test_the_caldera_erupts_at_irregular_moments(self):
        from hearthdelve.engine import anim
        fits = _onsets(lambda t: anim.eruption_age(t, 7) is not None, 1200, step=0.25)
        self.assertGreater(len(fits), 15)
        self.assertGreater(len(self._gaps(fits)), 5)

    def test_flocks_cross_at_irregular_moments(self):
        from hearthdelve.engine import anim
        flights = _onsets(lambda t: anim.flyover(0, t, 7) is not None, 2400, step=0.25)
        self.assertGreater(len(flights), 20)
        self.assertGreater(len(self._gaps(flights)), 5)

    def test_finished_machines_glint_out_of_step(self):
        from hearthdelve.engine import anim
        spots = [(10, 10), (11, 10), (12, 10), (10, 11), (40, 33)]
        patterns = {tuple(anim.machine_lit(k * 0.05, x, y) for k in range(60))
                    for x, y in spots}
        self.assertGreater(len(patterns), 1)


if __name__ == "__main__":
    unittest.main()
