"""Goals for the years after the first: a fresh, harder set joins the journal
as each new year begins. (The 21 goals stopped at "earn 2,000g".)"""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


def _in_year(st, year):
    from hearthdelve.engine import constants as C
    st.day = (year - 1) * C.YEAR_LEN + 3
    return st


class TestGoalsComeAYearAtATime(unittest.TestCase):
    def test_there_are_goals_for_years_two_and_three(self):
        from hearthdelve.data import content
        years = {q.year for q in content.QUESTS}
        self.assertEqual(years, {1, 2, 3})
        self.assertGreaterEqual(sum(q.year == 2 for q in content.QUESTS), 6)
        self.assertGreaterEqual(sum(q.year == 3 for q in content.QUESTS), 6)
        self.assertEqual(len({q.id for q in content.QUESTS}), len(content.QUESTS))

    def test_a_later_year_s_goal_waits_for_its_year(self):
        from hearthdelve.game import quests
        st = fresh_state(2)
        st.stats["crops_harvested"] = 600                     # Master Farmer's mark, in year 1
        quests.check(st)
        self.assertNotIn("master_farmer", st.quests_done)
        _in_year(st, 2)
        gold = st.player.gold
        quests.check(st)
        self.assertIn("master_farmer", st.quests_done)
        self.assertGreater(st.player.gold, gold)

    def test_the_tally_counts_the_years_so_far(self):
        from hearthdelve.data import content
        from hearthdelve.game import quests
        st = fresh_state(2)
        self.assertEqual(quests.progress(st)[1], sum(q.year == 1 for q in content.QUESTS))
        _in_year(st, 3)
        self.assertEqual(quests.progress(st)[1], len(content.QUESTS))

    def test_every_goal_s_check_runs_on_a_fresh_game(self):
        """A check that raised would be swallowed and its goal never come."""
        from hearthdelve.data import content
        st = _in_year(fresh_state(2), 3)
        for q in content.QUESTS:
            with self.subTest(goal=q.id):
                self.assertIn(q.check(st), (True, False))

    def test_the_year_three_goals_can_be_met(self):
        from hearthdelve.data import content
        from hearthdelve.game import quests, skills
        st = _in_year(fresh_state(2), 3)
        for npc in st.surface.npcs[:10]:
            npc.friendship = 1000
        st.stats.update(deepest_depth=30, collection_complete=1, animals_born=20,
                        monsters_slain=500, gold_earned=250_000)
        for name in list(skills.SKILLS)[:3]:
            st.player.skills[name] = skills.MAX_LEVEL * skills.XP_PER_LEVEL
        for p in st.projects:
            p["state"] = "done"
        quests.check(st)
        for q in content.QUESTS:
            if q.year == 3:
                self.assertIn(q.id, st.quests_done, q.id)

    def test_the_journal_shows_this_year_s_set_and_promises_the_next(self):
        import tcod.console
        from hearthdelve.engine import rendering
        st = _in_year(fresh_state(2), 2)
        con = tcod.console.Console(80, 50, order="F")
        rendering.render_journal(con, st, 0)
        text = "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(50))
        self.assertIn("Year 2", text)
        self.assertIn("Master Farmer", text)
        self.assertNotIn("Pillar of the Vale", text)
        self.assertIn("More goals come with Year 3", text)

    def test_a_new_year_says_so_at_dawn(self):
        from hearthdelve.engine import constants as C
        from hearthdelve.game import farming
        st = fresh_state(2)
        st.day = C.YEAR_LEN - 1
        farming.sleep(st)
        self.assertEqual(st.year, 2)
        self.assertTrue(any("new goals" in m for m, _c in st.log.messages))


class TestProsperitySaysWhatCounts(unittest.TestCase):
    """It read "earn 2000g from the shipping bin", but favour payouts and
    sales to the innkeepers count towards it too."""

    def test_a_favour_s_pay_counts_and_the_goal_says_so(self):
        from hearthdelve.data import content
        from hearthdelve.game import quests
        st = fresh_state(2)
        st.stats["gold_earned"] = 2000                 # as a favour's payout bumps it
        quests.check(st)
        self.assertIn("prosper", st.quests_done)
        prosper = next(q for q in content.QUESTS if q.id == "prosper")
        self.assertNotIn("shipping bin", prosper.desc)
        self.assertIn("favours", prosper.desc)


class TestFiveStarHarvestsAreCounted(unittest.TestCase):
    def test_a_five_star_harvest_counts(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming, skills
        from hearthdelve.world.crops import CropPlot
        st = fresh_state(2)
        crop = next(c for c in content.CROPS if c.season == st.season)
        pos = (st.player.x + 1, st.player.y)
        for q, want in ((3, 0), (5, 1)):
            st.surface.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature)
            with mock.patch.object(skills, "roll_quality", return_value=q):
                farming.harvest(st, *pos)
            self.assertEqual(st.stats.get("five_star_harvests", 0), want)


if __name__ == "__main__":
    unittest.main()
