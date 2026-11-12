"""A sticky bomb: slime gel on a bomb, and the first thing that slows a foe."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state
from tests.test_noise import _below, _open_spot, _sleeper


def _mob(st, x, y, speed=2, hp=60):
    m = _sleeper(st, x, y)
    m.speed, m.hp, m.max_hp, m.awake = speed, hp, hp, True
    return m


class TestTheGoo(unittest.TestCase):
    """Nothing in the game slowed a monster: a foe was at full pace or dead."""

    def test_a_mired_mob_gains_half_its_energy(self):
        from hearthdelve.game import combat
        st = _below()
        for speed in (1, 2, 3):
            with self.subTest(speed=speed):
                m = _mob(st, st.player.x + 9, st.player.y, speed)
                free = sum(combat.energy_gain(m) for _ in range(8))
                m.status["mired"] = 8
                slow = 0
                for _ in range(8):
                    combat._tick_status(m)
                    slow += combat.energy_gain(m)
                self.assertEqual(slow * 2, free)
                self.assertNotIn("mired", m.status)      # ...and it wears off

    def test_goo_does_no_harm_of_its_own(self):
        from hearthdelve.game import combat
        st = _below()
        m = _mob(st, st.player.x + 9, st.player.y)
        m.status["mired"] = 8
        for _ in range(8):
            combat._tick_status(m)
        self.assertEqual(m.hp, m.max_hp)

    def test_the_blast_mires_what_it_does_not_kill(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = _below()
        p = st.player
        tx, ty = _open_spot(st, (p.x, p.y), 2, 4)
        tough = _mob(st, tx, ty, hp=60)
        st.player.inventory.add(items.STICKY_BOMB, 1)
        self.assertTrue(combat.throw_bomb_at(st, tx, ty))
        self.assertEqual(tough.hp, 60 - combat.BOMB_STATS[items.STICKY_BOMB][1])
        left = tough.status.get("mired", 0)          # the throw itself takes a turn or two
        self.assertTrue(0 < left <= combat.BOMB_MIRE[items.STICKY_BOMB], left)
        self.assertEqual(st.player.inventory.count(items.STICKY_BOMB), 0)

    def test_a_plain_bomb_leaves_no_goo(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = _below()
        p = st.player
        tx, ty = _open_spot(st, (p.x, p.y), 2, 4)
        tough = _mob(st, tx, ty, hp=60)
        st.player.inventory.add(items.BOMB, 1)
        combat.throw_bomb_at(st, tx, ty)
        self.assertNotIn("mired", tough.status)

    def test_it_trades_blast_for_goo(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        self.assertLess(combat.BOMB_STATS[items.STICKY_BOMB][1],
                        combat.BOMB_STATS[items.BOMB][1])

    def test_a_mired_chaser_covers_half_the_ground(self):
        from hearthdelve.game import combat
        st = _below()
        p = st.player
        p.hp = p.max_hp = 9999
        x, y = _open_spot(st, (p.x, p.y), 6, 8)
        m = _mob(st, x, y, speed=2, hp=500)
        m.status["mired"] = 6
        acted = 0
        real = combat._step
        try:
            def count(state, mob):
                nonlocal acted
                acted += 1
            combat._step = count
            for _ in range(6):
                combat.monsters_act(st)
        finally:
            combat._step = real
        self.assertEqual(acted, 3)


class TestMakingAndKeepingOne(unittest.TestCase):
    def test_a_bomb_and_a_gel_make_it(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(41)
        inv = st.player.inventory
        inv.add(items.BOMB, 1)
        inv.add(items.SLIME_GEL, 1)
        r = next(r for r in content.RECIPES if r.name == "Sticky Bomb")
        self.assertTrue(crafting.craft(st, r))
        self.assertEqual(inv.count(items.STICKY_BOMB), 1)
        self.assertEqual(inv.count(items.BOMB) + inv.count(items.SLIME_GEL), 0)

    def test_it_readies_in_the_ammo_slot_like_any_bomb(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat, commands
        st = fresh_state(41)
        inv = st.player.inventory
        inv.add(items.BOMB, 2)
        inv.add(items.STICKY_BOMB, 1)
        commands._equip(st, items.STICKY_BOMB)
        self.assertIs(combat._carried_bomb(st), items.STICKY_BOMB)

    def test_bomb_and_goo_survive_a_save(self):
        from hearthdelve.entities import items
        from hearthdelve.engine import save
        st = _below()
        m = _mob(st, st.player.x + 3, st.player.y)
        m.status["mired"] = 5
        st.player.inventory.add(items.STICKY_BOMB, 2)
        path = os.path.join(tempfile.mkdtemp(), "goo.sav")
        save.save(st, path)
        back = save.load(path)
        self.assertEqual(back.player.inventory.count(items.STICKY_BOMB), 2)
        kept = [x for x in back.world.monsters if x.status.get("mired")]
        self.assertEqual([x.status["mired"] for x in kept], [5])


class TestWildWounds(unittest.TestCase):
    """Out on the surface a critter's afflictions never ran: a burn laid on a
    wolf sat there for good and bit nothing."""

    def test_a_burn_runs_its_course_on_a_critter(self):
        from hearthdelve.game import wildlife
        from hearthdelve.entities.monster import Mob
        st = fresh_state(42)
        p = st.player
        st.world.monsters.clear()
        m = Mob("Deer", "d", (200, 170, 150), 30, 30, 0, "skittish", p.x + 3, p.y,
                kind="wildlife")
        st.world.monsters.append(m)
        m.status["burn"] = 3
        for _ in range(3):
            wildlife.act(st)
        self.assertLess(m.hp, 30)
        self.assertNotIn("burn", m.status)


if __name__ == "__main__":
    unittest.main()
