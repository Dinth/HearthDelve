"""A slime trap: goo laid on a dungeon floor that mires what steps in it."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state
from tests.test_noise import _below, _open_spot, _sleeper


def _recipe(name):
    from hearthdelve.data import content
    return next(r for r in content.RECIPES if r.name == name)


def _face_floor(st):
    from hearthdelve.game import commands
    p, w = st.player, st.world
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if int(w.tiles[p.x + dx, p.y + dy]) == commands._floor_of(w):
            p.facing = (dx, dy)
            return p.x + dx, p.y + dy
    raise AssertionError("no bare floor beside the delver")


class TestSlimeTrap(unittest.TestCase):
    def test_two_gels_make_two_traps(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(181)
        inv = st.player.inventory
        inv.add(items.SLIME_GEL, 2)
        inv.add(items.FIBER, 1)
        self.assertTrue(crafting.craft(st, _recipe("Slime Trap")))
        self.assertEqual(inv.count(items.SLIME_TRAP), 2)

    def test_it_is_laid_on_the_floor_you_face(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = _below()
        st.player.inventory.add(items.SLIME_TRAP, 1)
        spot = _face_floor(st)
        self.assertTrue(crafting.craft(st, _recipe("Set Slime Trap")))
        self.assertEqual(st.world.tile_at(*spot).kind, "goo")
        self.assertEqual(st.player.inventory.count(items.SLIME_TRAP), 0)
        self.assertTrue(st.world.walkable(*spot))

    def test_not_in_the_open_air(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(181)
        st.player.inventory.add(items.SLIME_TRAP, 1)
        self.assertFalse(crafting.craft(st, _recipe("Set Slime Trap")))
        self.assertEqual(st.player.inventory.count(items.SLIME_TRAP), 1)

    def test_a_monster_that_steps_in_it_is_mired_and_the_goo_is_spent(self):
        from hearthdelve.game import combat, commands
        from hearthdelve.world import tile
        st = _below()
        p = st.player
        x, y = _open_spot(st, (p.x, p.y), 4, 6)
        m = _sleeper(st, x, y)
        m.awake = True
        # goo on every floor tile round it: whichever way it comes, it steps in
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (dx or dy) and int(st.world.tiles[x + dx, y + dy]) == commands._floor_of(st.world):
                    st.world.tiles[x + dx, y + dy] = tile.GOO
        self.assertTrue(combat._move_toward(st, m))
        self.assertEqual(m.status.get("mired"), combat.GOO_TRAP_TURNS)
        self.assertNotEqual(st.world.tile_at(m.x, m.y).kind, "goo")

    def test_a_trap_holds_longer_than_a_bombs_spatter(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        self.assertGreater(combat.GOO_TRAP_TURNS, combat.BOMB_MIRE[items.STICKY_BOMB])

    def test_the_trap_is_worth_its_gel(self):
        from hearthdelve.entities import items
        r = _recipe("Slime Trap")
        cost = sum(it.value * q for it, q in r.inputs)
        self.assertGreaterEqual(items.SLIME_TRAP.value * r.out_qty, cost * 1.25)

    def test_laid_goo_survives_a_save(self):
        from hearthdelve.engine import save
        from hearthdelve.world import tile
        st = _below()
        spot = _face_floor(st)
        st.world.tiles[spot] = tile.GOO
        path = os.path.join(tempfile.mkdtemp(), "goo.sav")
        save.save(st, path)
        self.assertEqual(save.load(path).world.tile_at(*spot).kind, "goo")

    def test_the_goo_tile_was_appended_not_inserted(self):
        from hearthdelve.world import tile
        self.assertEqual(tile.GOO, len(tile.TILES) - 1)


if __name__ == "__main__":
    unittest.main()
