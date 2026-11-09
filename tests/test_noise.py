"""Noise underground: bombs and a ringing pick wake what sleeps nearby."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


def _below():
    from hearthdelve.game import delve
    st = fresh_state(2)
    mouth = sorted(q for q, k in st.surface.dungeon_kind.items() if k == "mine")[0]
    st.player.x, st.player.y = mouth
    delve.enter(st, "mine")
    st.world.monsters.clear()
    st.fx.clear()
    return st


def _sleeper(st, x, y):
    from hearthdelve.entities.monster import Mob
    m = Mob("Rat", "r", (200, 170, 150), 30, 30, 1, "chase", x, y, dv=0, pv=0)
    m.awake = False
    st.world.monsters.append(m)
    return m


def _open_spot(st, near, at_least, at_most):
    w = st.world
    nx, ny = near
    for d in range(at_least, at_most + 1):
        for x in range(nx - d, nx + d + 1):
            for y in range(ny - d, ny + d + 1):
                if max(abs(x - nx), abs(y - ny)) == d and w.walkable(x, y) \
                        and (x, y) != (st.player.x, st.player.y):
                    return x, y
    raise AssertionError("no open floor")


class TestABombIsHeard(unittest.TestCase):
    """A bomb went off underground and only what it hit woke up; everything
    else slept on through the boom."""

    def _throw(self, st):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st.player.inventory.add(items.BOMB, 1)
        p = st.player
        tx, ty = _open_spot(st, (p.x, p.y), 2, 4)
        combat.throw_bomb_at(st, tx, ty)
        return combat.bomb_landing(st, tx, ty)

    def test_sleepers_within_earshot_wake(self):
        st = _below()
        p = st.player
        sleeper = _sleeper(st, *_open_spot(st, (p.x, p.y), 5, 7))
        with mock.patch("random.random", return_value=0.0):
            self._throw(st)
        self.assertTrue(sleeper.awake)

    def test_far_beyond_earshot_they_sleep_on(self):
        from hearthdelve.game import combat
        st = _below()
        p = st.player
        far = _sleeper(st, p.x + combat.BLAST_NOISE + 12, p.y)
        with mock.patch("random.random", return_value=0.0):
            self._throw(st)
        self.assertFalse(far.awake)


class TestAPickRings(unittest.TestCase):
    """Mining underground made no sound at all."""

    def test_a_sleeper_close_by_may_stir(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = _below()
        p = st.player
        tx, ty = p.x + 1, p.y
        sleeper = _sleeper(st, *_open_spot(st, (p.x, p.y), 3, 4))
        with mock.patch("random.random", return_value=0.0):
            commands._pick_rings(st, items.PICKAXE, tx, ty)
        self.assertTrue(sleeper.awake)

    def test_but_not_always(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = _below()
        p = st.player
        sleeper = _sleeper(st, *_open_spot(st, (p.x, p.y), 3, 4))
        with mock.patch("random.random", return_value=0.99):
            commands._pick_rings(st, items.PICKAXE, p.x + 1, p.y)
        self.assertFalse(sleeper.awake)

    def test_finishing_a_seam_rings_out(self):
        """Wired into the work itself, not just a helper."""
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = _below()
        p = st.player
        sleeper = _sleeper(st, *_open_spot(st, (p.x, p.y), 3, 4))
        target = st.world.tile_at(p.x + 1, p.y)
        b = {"item": items.PICKAXE, "target": target, "new_tile": None, "tx": p.x + 1,
             "ty": p.y, "stamina": 0, "msg": ""}
        with mock.patch("random.random", return_value=0.0):
            commands._finish_busy(st, b)
        self.assertTrue(sleeper.awake)

    def test_the_surface_is_out_of_earshot(self):
        from hearthdelve.game import combat
        st = fresh_state(2)
        self.assertEqual(combat.make_noise(st, st.player.x, st.player.y, 10), 0)


if __name__ == "__main__":
    unittest.main()
