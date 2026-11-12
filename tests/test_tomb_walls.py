"""A tomb's walls are walls: no pick or bomb tunnels through them."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestATombCannotBeDugThrough(unittest.TestCase):
    """The tomb is built of the surface's crumbling ruin stone, which the
    pick and the bomb both break — so every tomb wall, the outer ring too,
    could be tunnelled for stone and Mining practice without end."""

    def _tomb(self):
        from hearthdelve.world import dungeon
        st = fresh_state(12)
        gm = dungeon.generate(4242, "tomb", 2)
        st.world, st.depth = gm, 2
        st.player.x, st.player.y = gm.spawn
        return st, gm

    def test_the_pick_is_turned_by_tomb_stone(self):
        from hearthdelve.entities import items
        from hearthdelve.game import actions
        from hearthdelve.world import tile
        st, gm = self._tomb()
        wall = tile.TILES[gm.wall_tile]
        self.assertEqual(wall.name, "ruins_wall")
        ok, _new, msg = actions.resolve_tool(items.PICKAXE, wall, gm)
        self.assertFalse(ok)
        self.assertIn("stone", msg)

    def test_using_it_on_a_wall_changes_nothing(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        from hearthdelve.world import tile
        st, gm = self._tomb()
        p = st.player
        spot = next(((x, y), (dx, dy)) for x in range(1, gm.width - 1) for y in range(1, gm.height - 1)
                    if gm.walkable(x, y)
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    if gm.tiles[x + dx, y + dy] == gm.wall_tile)
        (p.x, p.y), p.facing = spot
        p.hotbar[p.active_slot] = items.PICKAXE
        before = gm.tiles.copy()
        stone = p.inventory.count(items.STONE)
        commands.use_tool(st)
        self.assertTrue((gm.tiles == before).all())
        self.assertEqual(p.inventory.count(items.STONE), stone)
        self.assertEqual(tile.TILES[gm.tiles[p.x + p.facing[0], p.y + p.facing[1]]].name, "ruins_wall")

    def test_a_bomb_does_not_breach_it_either(self):
        from hearthdelve.game import actions
        from hearthdelve.world import tile
        _st, gm = self._tomb()
        self.assertFalse(actions.loose_rock(gm, tile.TILES[tile.RUINS_WALL]))
        self.assertTrue(actions.loose_rock(gm, tile.TILES[tile.ROCK]))      # rubble still breaks

    def test_ruin_stone_above_ground_still_breaks(self):
        from hearthdelve.entities import items
        from hearthdelve.game import actions
        from hearthdelve.world import tile
        st = fresh_state(12)
        ruin = tile.TILES[tile.RUINS_WALL]
        self.assertTrue(actions.resolve_tool(items.PICKAXE, ruin, st.surface)[0])
        self.assertTrue(actions.resolve_tool(items.PICKAXE, ruin)[0])
        self.assertTrue(actions.loose_rock(st.surface, ruin))


if __name__ == "__main__":
    unittest.main()
