"""Every dungeon kind must have a themed roster and reachable bosses.

"dwarfhold" was a real site — the descent to Khazgrim and the Underriver — but no
monster or boss was ever tagged with it, so every ordinary floor at every depth
spawned only the two ``kinds=()`` mobs: a depth-1 Cave Slime and a Bat, and never
a boss, while its ore and chest rewards scaled with depth as normal.

``monsters_for``'s "no floor is ever left empty" fallback could not catch it,
because those two anywhere-mobs always qualify — the pool was never *empty*, just
never themed. So these tests assert the stronger property the fallback implies.
"""
from __future__ import annotations

import unittest

from tests.common import fresh_state     # noqa: F401  (repo-root path bootstrap)

from hearthdelve.data import content
from hearthdelve.world import dungeon

# Every kind the world can actually generate. dungeon.py's theme/decor tables are
# the authority on what exists; "mine" is the unlisted default.
SITE_KINDS = tuple(sorted(set(dungeon._THEME) | set(dungeon._DECOR) | {"mine"}))


class DungeonRosterTest(unittest.TestCase):
    def test_every_site_kind_has_themed_monsters(self):
        bare = []
        for kind in SITE_KINDS:
            themed = [m for m in content.MONSTERS if kind in m.kinds]
            if not themed:
                bare.append(kind)
        self.assertEqual(bare, [], f"dungeon kinds with no themed monster at all: {bare}")

    def test_every_site_kind_has_a_boss(self):
        bare = [k for k in SITE_KINDS if not [b for b in content.BOSSES if k in b.kinds]]
        self.assertEqual(bare, [], f"dungeon kinds that can never spawn a boss: {bare}")

    def test_a_deep_floor_is_not_populated_by_depth_one_fodder(self):
        """The symptom, stated directly: a deep floor of any kind must offer more
        than the two anywhere-mobs."""
        anywhere = {m.name for m in content.MONSTERS if not m.kinds}
        for kind in SITE_KINDS:
            with self.subTest(kind=kind):
                pool = {m.name for m in content.monsters_for(kind, 10)}
                self.assertTrue(pool - anywhere,
                                f"{kind} at depth 10 offers only {sorted(pool)}")

    def test_rosters_grow_with_depth(self):
        for kind in SITE_KINDS:
            with self.subTest(kind=kind):
                shallow = len(content.monsters_for(kind, 1))
                deep = len(content.monsters_for(kind, 10))
                self.assertGreater(deep, shallow,
                                   f"{kind}'s roster never widens between depth 1 and 10")

    def test_no_monster_lists_a_kind_twice(self):
        dupes = []
        for m in list(content.MONSTERS) + list(content.BOSSES):
            if len(m.kinds) != len(set(m.kinds)):
                dupes.append((m.name, m.kinds))
        self.assertEqual(dupes, [], f"duplicated kind tags: {dupes}")

    def test_no_monster_is_tagged_with_an_unknown_kind(self):
        """A typo in a kinds tuple would silently exclude the mob everywhere."""
        strays = []
        for m in list(content.MONSTERS) + list(content.BOSSES):
            for k in m.kinds:
                if k not in SITE_KINDS:
                    strays.append((m.name, k))
        self.assertEqual(strays, [], f"monsters tagged with a non-existent site kind: {strays}")


if __name__ == "__main__":
    unittest.main()
