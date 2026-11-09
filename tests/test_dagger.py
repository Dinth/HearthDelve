"""The dagger was weaker AND dearer than the sword (2-5 damage against 3-7, and
more gold), with only +1 to hit for it. Now it's the cheaper blade, and it
finds the gaps: far more critical hits."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _make(base, material="iron"):
    from hearthdelve.data import content
    return content.make_gear(base, material, "", "", ())


class TestTheDaggerEarnsItsPlace(unittest.TestCase):
    def test_it_is_cheaper_than_a_sword_of_the_same_metal(self):
        for metal in ("iron", "steel", "mithril"):
            with self.subTest(metal=metal):
                self.assertLess(_make("Dagger", metal).value, _make("Sword", metal).value)

    def test_it_lands_far_more_critical_hits(self):
        from hearthdelve.game import combat
        st = fresh_state(2)
        p = st.player
        p.hotbar[p.active_slot] = _make("Sword")
        sword = combat.player_crit(st)
        p.hotbar[p.active_slot] = _make("Dagger")
        dagger = combat.player_crit(st)
        self.assertAlmostEqual(dagger - sword, 0.10)

    def test_any_dagger_has_the_knack_whatever_its_make(self):
        from hearthdelve.data import content
        self.assertEqual(content.weapon_crit(content.make_gear("Dagger", "adamantium", "fine", "", ())), 0.10)
        self.assertEqual(content.weapon_crit(None), 0.0)


if __name__ == "__main__":
    unittest.main()
