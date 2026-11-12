"""A quilt on the bed, a tapestry on the wall: what the loom's best is for."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _at_bed(st):
    st.player.x, st.player.y = st.surface.bed
    return st.surface.bed


def _facing_wall(st):
    """Stand inside the farmhouse facing one of its walls."""
    from hearthdelve.game import husbandry
    surf = st.surface
    (x0, y0, w, h), *_ = husbandry.house_rects(st)
    for x in range(x0 + 1, x0 + w - 1):
        for y in range(y0 + 1, y0 + h - 1):
            if not surf.walkable(x, y):
                continue
            for dx, dy in ((0, -1), (1, 0), (-1, 0), (0, 1)):
                if surf.tile_at(x + dx, y + dy).name == "house_wall" and (x, y) != tuple(surf.bed):
                    st.player.x, st.player.y, st.player.facing = x, y, (dx, dy)
                    return x + dx, y + dy
    raise AssertionError("no wall to face")


class TestQuiltOnTheBed(unittest.TestCase):
    """A 420g quilt could be sold, gifted to no one, or handed in as a favour."""

    def test_laid_on_the_bed_it_leaves_the_pack(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, home
        st = fresh_state(71)
        st.player.inventory.add(items.QUILT, 1, quality=2)
        _at_bed(st)
        commands.do_grab(st)
        self.assertEqual(st.player.inventory.count(items.QUILT), 0)
        self.assertEqual(st.stats[home.QUILT], 3)
        self.assertEqual(home.comfort(st), home.COMFORT_BASE + 2 * home.COMFORT_PER_STAR)

    def test_you_wake_with_more_than_a_full_measure(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, farming, home
        st = fresh_state(71)
        p = st.player
        st.player.inventory.add(items.QUILT, 1)
        _at_bed(st)
        commands.do_grab(st)
        p.energy = 5
        farming.sleep(st)
        self.assertEqual(p.energy, p.max_energy + home.COMFORT_BASE)

    def test_a_bare_bed_gives_the_plain_measure(self):
        from hearthdelve.game import farming
        st = fresh_state(71)
        _at_bed(st)
        farming.sleep(st)
        self.assertEqual(st.player.energy, st.player.max_energy)

    def test_a_faint_gets_no_comfort(self):
        from hearthdelve.game import farming, home
        st = fresh_state(71)
        st.stats[home.QUILT] = 4
        farming.new_day(st, rested=False)
        self.assertEqual(st.player.energy, st.player.max_energy // 2)

    def test_breakfast_does_not_eat_the_bonus(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, farming, home
        st = fresh_state(71)
        p = st.player
        st.stats[home.QUILT] = 1
        _at_bed(st)
        farming.sleep(st)
        over = p.energy
        self.assertGreater(over, p.max_energy)
        p.inventory.add(items.HERBAL_TONIC, 1)
        commands._eat(st, items.HERBAL_TONIC, 0)
        self.assertEqual(p.energy, over)

    def test_a_finer_quilt_replaces_it_and_the_old_comes_back(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, home
        st = fresh_state(71)
        inv = st.player.inventory
        _at_bed(st)
        inv.add(items.QUILT, 1, quality=1)
        commands.do_grab(st)
        inv.add(items.QUILT, 1, quality=4)
        commands.do_grab(st)
        self.assertEqual(st.stats[home.QUILT], 5)
        self.assertEqual(inv.count(items.QUILT, 1), 1)
        self.assertEqual(inv.count(items.QUILT, 4), 0)

    def test_a_lesser_quilt_stays_in_the_pack(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, home
        st = fresh_state(71)
        st.stats[home.QUILT] = 4
        st.player.inventory.add(items.QUILT, 1, quality=1)
        _at_bed(st)
        commands.do_grab(st)
        self.assertEqual(st.stats[home.QUILT], 4)
        self.assertEqual(st.player.inventory.count(items.QUILT, 1), 1)


class TestTapestryOnTheWall(unittest.TestCase):
    def test_it_hangs_on_a_farmhouse_wall(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, home
        st = fresh_state(72)
        st.player.inventory.add(items.WALL_TAPESTRY, 1, quality=3)
        _facing_wall(st)
        commands.do_grab(st)
        self.assertEqual(st.player.inventory.count(items.WALL_TAPESTRY), 0)
        self.assertEqual(st.stats[home.TAPESTRY], 4)

    def test_quilt_and_tapestry_add_up(self):
        from hearthdelve.game import home
        st = fresh_state(72)
        st.stats[home.QUILT] = 1
        one = home.comfort(st)
        st.stats[home.TAPESTRY] = 1
        self.assertEqual(home.comfort(st), 2 * one)

    def test_not_on_a_village_wall(self):
        from hearthdelve.entities import items
        from hearthdelve.game import home
        st = fresh_state(72)
        st.player.inventory.add(items.WALL_TAPESTRY, 1)
        surf = st.surface
        b = next(b for b in surf.buildings)
        self.assertFalse(home.furnish(st, b["x"], b["y"]))
        self.assertEqual(st.player.inventory.count(items.WALL_TAPESTRY), 1)

    def test_look_mode_says_what_hangs_there(self):
        from hearthdelve.engine import rendering
        from hearthdelve.game import home
        st = fresh_state(72)
        wall = _facing_wall(st)
        self.assertNotIn("tapestry", rendering.describe(st, *wall))
        st.stats[home.TAPESTRY] = 3
        st.stats[home.QUILT] = 1
        self.assertIn("tapestry", rendering.describe(st, *wall))
        st.player.x += 99                        # (not standing on the bed)
        self.assertIn("quilt", rendering.describe(st, *st.surface.bed))

    def test_the_furnishings_survive_a_save(self):
        from hearthdelve.engine import save
        from hearthdelve.game import home
        st = fresh_state(72)
        st.stats[home.QUILT], st.stats[home.TAPESTRY] = 3, 5
        path = os.path.join(tempfile.mkdtemp(), "home.sav")
        save.save(st, path)
        back = save.load(path)
        self.assertEqual(home.comfort(back), home.comfort(st))

    def test_an_old_save_has_a_bare_house(self):
        from hearthdelve.game import home
        st = fresh_state(72)
        self.assertEqual(home.comfort(st), 0)


class TestRibbonsOnTheWall(unittest.TestCase):
    """A fair ribbon was 250g at the bin and nothing else."""

    def _pin(self, st, n=1):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st.player.inventory.add(items.FAIR_RIBBON, n)
        _facing_wall(st)
        for _ in range(n):
            commands.do_grab(st)

    def test_pinned_up_it_lifts_starred_goods_only(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting, home
        st = fresh_state(73)
        plain, starred = (crafting.bin_value(st, items.WINE, q) for q in (0, 3))
        self._pin(st)
        self.assertEqual(home.ribbons(st), 1)
        self.assertEqual(st.player.inventory.count(items.FAIR_RIBBON), 0)
        self.assertEqual(crafting.bin_value(st, items.WINE, 0), plain)
        self.assertGreater(crafting.bin_value(st, items.WINE, 3), starred)

    def test_the_wall_holds_only_so_many(self):
        from hearthdelve.entities import items
        from hearthdelve.game import home
        st = fresh_state(73)
        self._pin(st, home.RIBBON_CAP + 2)
        self.assertEqual(home.ribbons(st), home.RIBBON_CAP)
        self.assertEqual(st.player.inventory.count(items.FAIR_RIBBON), 2)
        self.assertAlmostEqual(home.ribbon_mult(st, 1),
                               1 + home.RIBBON_BONUS * home.RIBBON_CAP)

    def test_a_tapestry_goes_up_before_a_ribbon(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, home
        st = fresh_state(73)
        st.player.inventory.add(items.FAIR_RIBBON, 1)
        st.player.inventory.add(items.WALL_TAPESTRY, 1)
        _facing_wall(st)
        commands.do_grab(st)
        self.assertEqual((st.stats.get(home.TAPESTRY), home.ribbons(st)), (1, 0))
        commands.do_grab(st)
        self.assertEqual(home.ribbons(st), 1)

    def test_no_shop_good_can_be_bought_and_binned_at_a_profit(self):
        from hearthdelve.game import crafting, home
        from hearthdelve.entities import items
        st = fresh_state(73)
        st.stats[home.RIBBONS] = home.RIBBON_CAP
        self.assertEqual(crafting.bin_value(st, items.WINE, 0),
                         crafting.bin_value(fresh_state(73), items.WINE, 0))


if __name__ == "__main__":
    unittest.main()
