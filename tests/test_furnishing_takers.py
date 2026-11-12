"""Quilts and tapestries have takers beyond the farmhouse: gifts, and two halls."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestGifts(unittest.TestCase):
    def test_several_villagers_like_each(self):
        from hearthdelve.entities import items
        st = fresh_state(91)
        for it in (items.QUILT, items.WALL_TAPESTRY):
            fans = [n.name for n in st.surface.npcs if n.taste(it) in ("likes", "loves")]
            with self.subTest(item=it.name):
                self.assertGreaterEqual(len(fans), 4, fans)

    def test_the_innkeepers_and_priests_are_among_them(self):
        from hearthdelve.entities import items
        st = fresh_state(91)
        by = {n.name: n for n in st.surface.npcs}
        self.assertEqual(by["Mabel"].taste(items.QUILT), "likes")
        self.assertEqual(by["Father Ansel"].taste(items.WALL_TAPESTRY), "likes")
        self.assertEqual(by["Nessa"].taste(items.QUILT), "likes")


class TestHalls(unittest.TestCase):
    def test_two_great_works_ask_for_tapestries(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        for pid in ("scriptorium", "hall_of_wonders"):
            with self.subTest(project=pid):
                self.assertEqual(dict(content.PROJECTS[pid].mats).get(items.WALL_TAPESTRY), 2)

    def test_the_first_great_work_does_not(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        self.assertNotIn(items.WALL_TAPESTRY, dict(content.PROJECTS["grange_hall"].mats))

    def test_handing_them_over_counts(self):
        from hearthdelve.entities import items
        from hearthdelve.game import projects
        st = fresh_state(92)
        proj = projects.get(st, "scriptorium")
        st.player.inventory.add(items.WALL_TAPESTRY, 3)
        st.player.gold = 0
        self.assertTrue(projects.contribute(st, proj))
        self.assertEqual(proj["mats"][items.WALL_TAPESTRY.name], 2)
        self.assertEqual(st.player.inventory.count(items.WALL_TAPESTRY), 1)

    def test_a_hall_already_raised_stays_raised(self):
        from hearthdelve.game import projects
        old = [{"id": "scriptorium", "state": "done", "gold_paid": 4000,
                "mats": {"Timber Plank": 100, "Stone": 50, "Woolen Cloth": 6}},
               {"id": "hall_of_wonders", "state": "building", "gold_paid": 7000,
                "mats": {"Stone": 160, "Timber Plank": 120, "Silk Cloth": 8}}]
        merged = {p["id"]: p for p in projects.merge_loaded(old)}
        self.assertEqual(merged["scriptorium"]["state"], "done")
        self.assertEqual(merged["hall_of_wonders"]["state"], "building")

    def test_one_half_funded_now_wants_them_too(self):
        from hearthdelve.entities import items
        from hearthdelve.game import projects
        st = fresh_state(92)
        st.projects = projects.merge_loaded(
            [{"id": "scriptorium", "state": "open", "gold_paid": 4000,
              "mats": {"Timber Plank": 100, "Stone": 50, "Woolen Cloth": 6}}])
        gold_left, mats_left = projects.remaining(st, projects.get(st, "scriptorium"))
        self.assertEqual(gold_left, 0)
        self.assertEqual(mats_left, [(items.WALL_TAPESTRY, 2)])


if __name__ == "__main__":
    unittest.main()
