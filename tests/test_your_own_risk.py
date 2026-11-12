"""Working beside a threat, and breaking another's ground: your call, your cost."""
from __future__ import annotations

import unittest

from tests.common import fresh_state
from tests.test_anim import _clear_line


def _wolf(st, dx, dy):
    from hearthdelve.entities.monster import Mob
    p = st.player
    m = Mob("Wolf", "w", (170, 170, 170), 40, 40, 0, "predator", p.x + dx, p.y + dy,
            kind="wildlife", hostile=True, dmg=(1, 1))
    st.world.monsters.append(m)
    return m


def _at_a_tree(st):
    from hearthdelve.entities import items
    from hearthdelve.world import tile
    p = st.player
    dx, dy = _clear_line(st, 4)
    st.world.tiles[p.x + dx, p.y + dy] = tile.TREE_OAK
    p.facing = (dx, dy)
    p.hotbar[p.active_slot] = items.AXE
    return (p.x + dx, p.y + dy), (dx, dy)


class TestWorkingBesideAThreat(unittest.TestCase):
    """With a hostile close, chopping, mining and casting were refused."""

    def test_the_task_starts_and_names_the_risk(self):
        from hearthdelve.game import commands
        st = fresh_state(2)
        st.world.monsters.clear()
        spot, (dx, dy) = _at_a_tree(st)
        wolf = _wolf(st, -dx * 2, -dy * 2)
        busy = commands.use_tool(st)
        self.assertIsInstance(busy, dict)
        self.assertIn(id(wolf), busy["ack"])

    def test_the_one_you_chose_to_work_beside_does_not_stop_you(self):
        from hearthdelve import screens
        from hearthdelve.game import commands
        st = fresh_state(2)
        st.world.monsters.clear()
        spot, (dx, dy) = _at_a_tree(st)
        _wolf(st, -dx * 2, -dy * 2)
        st.player.hp = st.player.max_hp = 9999
        ui = screens.UI(st)
        ui.play.busy_ctx = commands.use_tool(st)
        for _ in range(400):
            if ui.play.busy_ctx is None:
                break
            ui.play.tick(ui)
        self.assertNotEqual(st.world.tile_at(*spot).kind, "tree")        # the tree came down

    def test_a_newcomer_still_breaks_it_off(self):
        from hearthdelve import screens
        from hearthdelve.game import commands
        st = fresh_state(2)
        st.world.monsters.clear()
        spot, (dx, dy) = _at_a_tree(st)
        ui = screens.UI(st)
        ui.play.busy_ctx = commands.use_tool(st)
        ui.play.tick(ui)
        self.assertIsNotNone(ui.play.busy_ctx)
        _wolf(st, -dx * 2, -dy * 2)
        ui.play.tick(ui)
        self.assertIsNone(ui.play.busy_ctx)
        self.assertEqual(st.world.tile_at(*spot).kind, "tree")

    def test_new_threat_ignores_what_was_acknowledged(self):
        from hearthdelve.game import commands
        st = fresh_state(2)
        st.world.monsters.clear()
        a = _wolf(st, 2, 0)
        self.assertIs(commands.new_threat(st, frozenset()), a)
        self.assertIsNone(commands.new_threat(st, frozenset({id(a)})))
        b = _wolf(st, 0, 2)
        self.assertIs(commands.new_threat(st, frozenset({id(a)})), b)

    def test_a_line_can_be_cast_with_one_lurking(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        from hearthdelve.world import tile
        st = fresh_state(2)
        st.world.monsters.clear()
        p = st.player
        dx, dy = _clear_line(st, 4)
        st.world.tiles[p.x + dx, p.y + dy] = tile.RIVER
        p.facing = (dx, dy)
        p.hotbar[p.active_slot] = items.FISHING_ROD
        _wolf(st, -dx * 2, -dy * 2)
        got = commands.use_tool(st)
        self.assertIsInstance(got, dict)
        self.assertIn("fishing", got)


class TestBreakingAnothersGround(unittest.TestCase):
    """Tilling a villager's land was refused outright, while felling their
    tree was allowed at a cost."""

    def _on_their_land(self):
        from hearthdelve.entities import items
        from hearthdelve.game import land
        from hearthdelve.world import tile
        st = fresh_state(1337)
        p = st.player
        for (x, y), _who in land._village_owner(st.surface).items():
            if st.surface.tile_at(x, y).name != "bush":
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                sx, sy = x + dx, y + dy
                if st.surface.walkable(sx, sy):
                    st.surface.tiles[x, y] = tile.GRASS      # a patch of their garden, cleared
                    p.x, p.y, p.facing = sx, sy, (-dx, -dy)
                    p.hotbar[p.active_slot] = items.HOE
                    self.assertTrue(land.owned_by_other(st, x, y))
                    return st, (x, y)
        self.fail("no owned garden ground with a way up to it")

    def test_the_first_press_only_warns(self):
        from hearthdelve.game import commands
        st, spot = self._on_their_land()
        karma = st.player.karma
        commands.use_tool(st)
        self.assertNotEqual(st.surface.tile_at(*spot).name, "tilled")
        self.assertEqual(st.player.karma, karma)

    def test_the_second_tills_it_and_is_remembered(self):
        from hearthdelve.game import commands, land
        st, spot = self._on_their_land()
        karma, thefts = st.player.karma, st.stats.get("thefts", 0)
        commands.use_tool(st)
        commands.use_tool(st)
        self.assertEqual(st.surface.tile_at(*spot).name, "tilled")
        self.assertLess(st.player.karma, karma)
        self.assertEqual(st.stats.get("thefts", 0), thefts + 1)
        self.assertTrue(land.owned_by_other(st, *spot))           # and the ground is still theirs

    def test_your_own_ground_tills_as_ever(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, land
        st = fresh_state(1337)
        p = st.player
        dx, dy = _clear_line(st, 4)
        p.facing = (dx, dy)
        p.hotbar[p.active_slot] = items.HOE
        if land.owned_by_other(st, p.x + dx, p.y + dy):
            self.skipTest("spawn faces owned land")
        karma = p.karma
        commands.use_tool(st)
        self.assertEqual(p.karma, karma)


if __name__ == "__main__":
    unittest.main()
