"""A polearm's reach: a spear or halberd strikes two tiles out, chosen in the
aim mode like a shot — so a bump into a monster stays the plain melee blow."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


def _holding(st, base="Spear"):
    from hearthdelve.data import content
    p = st.player
    p.hotbar[p.active_slot] = content.make_gear(base, "iron", "", "", ())
    return st


def _foe(st, dx, dy, name="Knight"):
    from hearthdelve.entities.monster import Mob
    from hearthdelve.world import tile
    p = st.player
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    for k in range(1, max(abs(dx), abs(dy)) + 1):           # open ground out to it
        st.world.tiles[p.x + k * sx, p.y + k * sy] = tile.GRASS
    st.world.tiles[p.x + dx, p.y + dy] = tile.GRASS
    m = Mob(name, "K", (200, 200, 200), 50, 50, 1, "chase", p.x + dx, p.y + dy, dv=0, pv=0)
    st.world.monsters.append(m)
    return m


class TestTheAimModeOffersReach(unittest.TestCase):
    def test_a_held_spear_can_reach_even_with_no_bow_or_bomb(self):
        from hearthdelve.game import combat
        st = _holding(fresh_state(2))
        self.assertTrue(combat.can_fire(st))
        self.assertEqual(combat.aim_purpose(st), "reach")
        self.assertEqual(combat.aim_range(st), 2)

    def test_a_hoe_is_a_tool_not_a_spear(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = fresh_state(2)
        st.player.hotbar[st.player.active_slot] = items.HOE
        self.assertFalse(combat.can_reach(st))

    def test_tab_steps_from_reach_to_the_bow_and_back(self):
        from hearthdelve import screens
        from hearthdelve.data import content
        from hearthdelve.entities import items
        st = _holding(fresh_state(2))
        st.player.equipment["ranged"] = content.make_ranged("Short Bow", "birch")
        st.player.inventory.add(items.ARROW, 5)
        ui = screens.UI(st)
        ui.play.handle(ui, "target", ("target",))
        self.assertEqual(ui.top.ctx["purpose"], "reach")
        ui.top.handle(ui, "swap", ("swap",))
        self.assertEqual(ui.top.ctx["purpose"], "shoot")
        ui.top.handle(ui, "swap", ("swap",))
        self.assertEqual(ui.top.ctx["purpose"], "reach")


class TestTheThrust(unittest.TestCase):
    def test_it_strikes_a_foe_two_tiles_out(self):
        from hearthdelve.game import combat
        st = _holding(fresh_state(2))
        foe = _foe(st, 2, 0)
        clock = st.clock
        with mock.patch.object(combat, "_resolve", return_value=(7, False)):
            self.assertTrue(combat.reach_attack(st, foe.x, foe.y))
        self.assertEqual(foe.hp, 43)
        self.assertGreater(st.clock, clock)                    # a combat turn passed

    def test_and_on_the_diagonal(self):
        from hearthdelve.game import combat
        st = _holding(fresh_state(2))
        foe = _foe(st, -2, 2)
        self.assertIs(combat.reach_target(st, foe.x, foe.y), foe)

    def test_not_off_the_line_nor_beyond_reach_nor_through_a_wall(self):
        from hearthdelve.game import combat
        from hearthdelve.world import tile
        st = _holding(fresh_state(2))
        p = st.player
        knight_move = _foe(st, 2, 1)
        far = _foe(st, 0, 3, name="Far")
        self.assertIsNone(combat.reach_target(st, knight_move.x, knight_move.y))
        self.assertIsNone(combat.reach_target(st, far.x, far.y))
        walled = _foe(st, -2, 0, name="Walled")
        st.world.tiles[p.x - 1, p.y] = tile.HOUSE_WALL
        self.assertIsNone(combat.reach_target(st, walled.x, walled.y))

    def test_a_foe_in_between_takes_the_blow(self):
        from hearthdelve.game import combat
        st = _holding(fresh_state(2))
        behind = _foe(st, 0, -2, name="Behind")
        front = _foe(st, 0, -1, name="Front")
        self.assertIs(combat.reach_target(st, behind.x, behind.y), front)

    def test_through_the_aim_screen(self):
        from hearthdelve import screens
        from hearthdelve.game import combat
        st = _holding(fresh_state(2))
        foe = _foe(st, 2, 0)
        ui = screens.UI(st)
        ui.play.handle(ui, "target", ("target",))
        self.assertEqual(tuple(ui.top.ctx["cursor"]), (foe.x, foe.y))   # opens on the foe in reach
        with mock.patch.object(combat, "_resolve", return_value=(5, False)):
            ui.top.handle(ui, "confirm", ("confirm",))
        self.assertIs(ui.top, ui.play)
        self.assertEqual(foe.hp, 45)

    def test_a_bump_is_still_a_plain_blow(self):
        from hearthdelve.game import combat, commands
        st = _holding(fresh_state(2))
        foe = _foe(st, 1, 0)
        with mock.patch.object(combat, "_resolve", return_value=(4, False)):
            commands.try_move(st, 1, 0)
        self.assertEqual(foe.hp, 46)


if __name__ == "__main__":
    unittest.main()
