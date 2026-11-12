"""A hunting beast makes a hurried meal cost what a fight costs."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _beast(st, dx, **kw):
    from hearthdelve.entities.monster import Mob
    p = st.player
    m = Mob("Ash Wolf", "w", (200, 200, 200), 20, 20, 2, "chase", p.x + dx, p.y, **kw)
    st.world.monsters.append(m)
    return m


class TestAHostileBeastIsAThreat(unittest.TestCase):
    """Predators turn hostile on sight but are never flagged awake (that is
    the dungeon's flag), so eating beside a wolf at your heels cost the
    leisurely seconds of a picnic."""

    def test_a_wolf_on_the_hunt_counts(self):
        from hearthdelve.game import commands
        st = fresh_state(23)
        st.world.monsters[:] = []
        _beast(st, 3, kind="wildlife", hostile=True)
        self.assertTrue(commands._under_threat(st))

    def test_a_grazing_deer_does_not(self):
        from hearthdelve.game import commands
        st = fresh_state(23)
        st.world.monsters[:] = []
        _beast(st, 3, kind="wildlife", hostile=False, awake=True)
        self.assertFalse(commands._under_threat(st))

    def test_a_sleeping_monster_still_does_not(self):
        from hearthdelve.game import commands
        st = fresh_state(23)
        st.world.monsters[:] = []
        m = _beast(st, 3)
        self.assertFalse(commands._under_threat(st))
        m.awake = True
        self.assertTrue(commands._under_threat(st))

    def test_nor_one_far_off(self):
        from hearthdelve.game import commands
        st = fresh_state(23)
        st.world.monsters[:] = []
        _beast(st, commands._EAT_THREAT_RADIUS + 1, kind="wildlife", hostile=True)
        self.assertFalse(commands._under_threat(st))


if __name__ == "__main__":
    unittest.main()
