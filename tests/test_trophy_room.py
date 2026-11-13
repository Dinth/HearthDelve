"""The farmhouse's second room is a trophy room."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state
from tests.test_extension import _built, _rich


def _face_second_room_wall(st):
    """Stand on the second room's floor facing one of its outer walls."""
    from hearthdelve.game import husbandry
    surf = st.surface
    rects = husbandry.house_rects(st)
    x0, y0, w, h = rects[1]
    main = rects[0]
    in_main = lambda x, y: main[0] <= x < main[0] + main[2] and main[1] <= y < main[1] + main[3]
    for x in range(x0 + 1, x0 + w - 1):
        for y in range(y0 + 1, y0 + h - 1):
            if not surf.walkable(x, y):
                continue
            for dx, dy in ((0, -1), (1, 0), (-1, 0), (0, 1)):
                wx, wy = x + dx, y + dy
                if surf.tile_at(wx, wy).name == "house_wall" and not in_main(wx, wy):
                    st.player.x, st.player.y, st.player.facing = x, y, (dx, dy)
                    return wx, wy
    raise AssertionError("no outer wall in the second room")


class TestTrophyRoom(unittest.TestCase):
    """The 6,000g extension added floor and nothing else."""

    def _room(self):
        st = _built(_rich(fresh_state(221)))
        return st, _face_second_room_wall(st)

    def test_a_boss_trophy_mounts_on_its_wall(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, home
        st, _wall = self._room()
        st.player.inventory.add(items.TROLL_TUSK, 1)
        commands.do_grab(st)
        self.assertEqual(home.trophies(st), [items.TROLL_TUSK.name])
        self.assertEqual(st.player.inventory.count(items.TROLL_TUSK), 0)
        self.assertEqual(home.comfort(st), home.TROPHY_COMFORT)

    def test_one_of_each_and_no_more(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, home
        st, _wall = self._room()
        st.player.inventory.add(items.TROLL_TUSK, 2)
        commands.do_grab(st)
        commands.do_grab(st)
        self.assertEqual(len(home.trophies(st)), 1)
        self.assertEqual(st.player.inventory.count(items.TROLL_TUSK), 1)

    def test_all_five_can_hang_and_each_adds(self):
        from hearthdelve.data import content
        from hearthdelve.game import commands, home
        st, _wall = self._room()
        for t in content.COLLECTION["Trophies"]:
            st.player.inventory.add(t, 1)
        for _ in range(5):
            commands.do_grab(st)
        self.assertEqual(len(home.trophies(st)), 5)
        self.assertEqual(home.comfort(st), 5 * home.TROPHY_COMFORT)

    def test_you_wake_the_better_for_them(self):
        from hearthdelve.entities import items
        from hearthdelve.game import farming, home
        st, _wall = self._room()
        st.stats[home.TROPHIES] = items.TROLL_TUSK.name + "|" + items.BONE_CROWN.name
        st.player.x, st.player.y = st.surface.bed
        farming.sleep(st)
        self.assertEqual(st.player.energy, st.player.max_energy + 2 * home.TROPHY_COMFORT)

    def test_not_in_the_first_room(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, home
        from tests.test_home_comforts import _facing_wall
        st = fresh_state(221)                       # no second room at all
        st.player.inventory.add(items.TROLL_TUSK, 1)
        _facing_wall(st)
        commands.do_grab(st)
        self.assertEqual(home.trophies(st), [])
        self.assertEqual(st.player.inventory.count(items.TROLL_TUSK), 1)

    def test_look_mode_names_what_hangs_there(self):
        from hearthdelve.engine import rendering
        from hearthdelve.entities import items
        from hearthdelve.game import home
        st, wall = self._room()
        self.assertIn("trophy", rendering.describe(st, *wall))
        st.stats[home.TROPHIES] = items.TROLL_TUSK.name
        self.assertIn(items.TROLL_TUSK.name.lower(), rendering.describe(st, *wall))

    def test_the_wall_survives_a_save(self):
        from hearthdelve.engine import save
        from hearthdelve.entities import items
        from hearthdelve.game import home
        st, _wall = self._room()
        st.stats[home.TROPHIES] = items.TROLL_TUSK.name + "|" + items.BONE_CROWN.name
        path = os.path.join(tempfile.mkdtemp(), "t.sav")
        save.save(st, path)
        self.assertEqual(home.trophies(save.load(path)),
                         [items.TROLL_TUSK.name, items.BONE_CROWN.name])

    def test_the_carpenter_says_what_the_room_is_for(self):
        from hearthdelve.data import content
        label = next(l for l, k, _g, _m in content.HOUSE_JOBS if k == "extension")
        self.assertIn("trophy", label.lower())


if __name__ == "__main__":
    unittest.main()
