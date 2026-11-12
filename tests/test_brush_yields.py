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


if __name__ == "__main__":
    unittest.main()
