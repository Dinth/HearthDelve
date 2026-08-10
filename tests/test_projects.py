"""Community restoration projects: funding, siting, raising, and the perks.

The landmark a village raises becomes *its* land the moment it stands. Ownership
is derived and cached per-map (see game/land.py), so `projects.finish` has to
drop that cache — otherwise a hall you just paid 4000g for reads as wilderness
until the next load. The cache is warmed deliberately below, because that's what
real play does (any till/build/harvest check warms it) and the bug is invisible
without it.
"""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _fund(st, pid: str):
    """Pay a project off in one instalment and return its record."""
    from hearthdelve.data import content
    from hearthdelve.game import projects
    d = content.PROJECTS[pid]
    proj = projects.get(st, pid)
    st.player.gold = d.gold
    for it, q in d.mats:
        st.player.inventory.add(it, q)
    projects.contribute(st, proj, all_in=True)
    return proj, d


def _raise(st, d):
    """Sleep the build out and let the morning tick finish the landmark."""
    from hearthdelve.game import husbandry
    st.day += d.build_days
    st.clock = 0
    husbandry.new_day(st)


class TestRaisingALandmark(unittest.TestCase):
    def test_funding_stakes_a_site_and_it_raises_into_a_building(self):
        from hearthdelve.world import tile
        from hearthdelve.game import projects
        st = fresh_state(1337)
        proj, d = _fund(st, "grange_hall")
        self.assertEqual(proj["state"], "building", "full funding should break ground")
        self.assertIsNotNone(proj["site"])
        x0, y0, w, h = proj["site"]
        self.assertEqual((w, h), d.size)
        self.assertEqual(int(st.surface.tiles[x0, y0]), tile.SCAFFOLD)
        self.assertTrue(any(m.kind == "site" and m.build_kind == "grange_hall"
                            for m in st.surface.machines.values()))

        _raise(st, d)
        self.assertTrue(projects.done(st, "grange_hall"))
        self.assertEqual(int(st.surface.tiles[x0, y0]), tile.HOUSE_WALL,
                         "the scaffold should have become a walled hall")
        self.assertTrue(any(b.get("kind") == "grange_hall" for b in st.surface.buildings),
                        "look-mode needs a building record")

    def test_a_finished_landmark_is_village_land_at_once(self):
        """The regression: ownership is cached, so finishing must invalidate it."""
        from hearthdelve.game import land, projects
        st = fresh_state(1337)
        proj, d = _fund(st, "grange_hall")
        x0, y0, w, h = proj["site"]
        inside = (x0 + w // 2, y0 + h // 2)

        # Warm the cache exactly as ordinary play would, BEFORE the hall stands.
        land.owner_at(st, *st.surface.spawn)
        self.assertIsNotNone(getattr(st.surface, "_owner_cache", None))

        _raise(st, d)
        self.assertEqual(land.owner_at(st, *inside), "Mossford")
        self.assertTrue(land.owned_by_other(st, *inside),
                        "you shouldn't be able to treat the hall as your own ground")

    def test_you_cannot_set_a_machine_down_inside_it(self):
        """What the stale cache actually let you do."""
        from hearthdelve.game import crafting, land
        from hearthdelve.world import tile
        st = fresh_state(1337)
        proj, d = _fund(st, "grange_hall")
        x0, y0, w, h = proj["site"]
        land.owner_at(st, *st.surface.spawn)          # warm the cache first
        _raise(st, d)

        # Stand on clear hall floor facing more clear hall floor, so ownership is
        # the ONLY thing that can refuse — a chair or a wall in the way would
        # make this pass for the wrong reason.
        surf, stand = st.surface, None
        for xx in range(x0 + 1, x0 + w - 1):
            for yy in range(y0 + 1, y0 + h - 1):
                if int(surf.tiles[xx, yy]) != tile.HOUSE_FLOOR:
                    continue
                for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    if int(surf.tiles[xx - dx, yy - dy]) == tile.HOUSE_FLOOR:
                        stand = ((xx - dx, yy - dy), (dx, dy))
                        break
                if stand:
                    break
            if stand:
                break
        self.assertIsNotNone(stand, "the hall should have two clear floor tiles")
        (px, py), facing = stand
        st.player.x, st.player.y = px, py
        st.player.facing = facing
        st.world = surf
        self.assertTrue(surf.walkable(px + facing[0], py + facing[1]),
                        "the target tile must otherwise be placeable")
        before = len(surf.machines)
        crafting._place_machine(st, "furnace")
        self.assertEqual(len(surf.machines), before,
                         "the village's hall is not yours to build in")


class TestPerks(unittest.TestCase):
    def test_the_deep_forge_takes_a_fifth_off_a_tool_upgrade(self):
        from hearthdelve.data import content
        from hearthdelve.game import projects, village
        st = fresh_state(1337)
        base_gold, bar, count = content.upgrade_cost(0)
        self.assertEqual(village.upgrade_price(st, 0), (base_gold, bar, count))
        projects.get(st, "deep_forge")["state"] = "done"
        gold, bar2, count2 = village.upgrade_price(st, 0)
        self.assertEqual(gold, round(base_gold * 0.8))
        self.assertEqual((bar2, count2), (bar, count), "only the labour gets cheaper")

    def test_the_deep_forge_puts_deep_metal_on_brons_counter(self):
        from hearthdelve.data import content
        from hearthdelve.game import projects, village
        st = fresh_state(1337)
        before = {r.label for r in village.shop_entries("blacksmith", st)}
        for b in content.DEEP_FORGE_BARS:
            self.assertNotIn(b.name, before)
        projects.get(st, "deep_forge")["state"] = "done"
        after = {r.label for r in village.shop_entries("blacksmith", st)}
        for b in content.DEEP_FORGE_BARS:
            self.assertIn(b.name, after, f"{b.name} should reach the counter")


class TestGrandfathering(unittest.TestCase):
    def test_a_save_from_before_projects_loads_with_everything_open(self):
        from hearthdelve.data import content
        from hearthdelve.game import projects
        for raw in (None, [], [{"id": "no_such_project", "state": "done"}]):
            merged = projects.merge_loaded(raw)
            self.assertEqual(len(merged), len(content.PROJECTS))
            self.assertTrue(all(p["state"] == "open" for p in merged), f"raw={raw!r}")

    def test_a_dropped_material_does_not_break_a_saved_record(self):
        from hearthdelve.game import projects
        saved = projects.fresh()
        saved[0]["mats"]["Nonexistent Widget"] = 99      # a mat the defs no longer list
        saved[0]["gold_paid"] = 250
        merged = projects.merge_loaded(saved)
        self.assertNotIn("Nonexistent Widget", merged[0]["mats"])
        self.assertEqual(merged[0]["gold_paid"], 250, "progress must survive")


if __name__ == "__main__":
    unittest.main()
