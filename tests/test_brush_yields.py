"""What clearing brush pays: a blade on a berry bush, an imbued machete on grass."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


class TestABladeSavesSomeBerries(unittest.TestCase):
    """A sword could clear a berry shrub — and the bush, which regrows fruit
    for ever, was gone for nothing at all."""

    def test_a_berry_comes_away(self):
        from hearthdelve.data import content
        from hearthdelve.game import commands
        from hearthdelve.world import tile
        st = fresh_state(23)
        sword = content.make_gear("Sword", "iron")
        bush = tile.TILES[tile.SHRUB_RASPBERRY]
        fruit = content.SHRUB_FRUIT[bush.name]
        before = st.player.inventory.count(fruit)
        commands._gather_drop(st, sword, bush)
        self.assertEqual(st.player.inventory.count(fruit), before + 1)


class TestAnImbuedMacheteOnTallGrass(unittest.TestCase):
    """The bonus looked for a tile of KIND tall_grass; tall grass is plain
    terrain by kind, so an imbued or gem-set machete never paid on it."""

    def test_the_bonus_is_more_cut_grass(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        from hearthdelve.world import tile
        st = fresh_state(23)
        st.player.tool_affix[items.MACHETE] = "Bountiful"
        inv = st.player.inventory
        before = inv.count(items.CUT_GRASS)
        with mock.patch.object(commands.random, "random", lambda: 0.0), \
                mock.patch.object(commands.random, "randint", lambda a, b: a):
            commands._gather_drop(st, items.MACHETE, tile.TILES[tile.TALL_GRASS])
        self.assertEqual(inv.count(items.CUT_GRASS), before + 2)      # one cut, one bonus

    def test_brush_still_pays_fibre(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        from hearthdelve.world import tile
        st = fresh_state(23)
        st.player.tool_affix[items.MACHETE] = "Bountiful"
        inv = st.player.inventory
        before = inv.count(items.FIBER)
        with mock.patch.object(commands.random, "random", lambda: 0.0):
            commands._gather_drop(st, items.MACHETE, tile.TILES[tile.SHRUB])
        self.assertEqual(inv.count(items.FIBER), before + 2)


if __name__ == "__main__":
    unittest.main()
