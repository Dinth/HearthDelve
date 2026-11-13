"""Every forged weapon is a step up from the rusty sword you start with."""
from __future__ import annotations

import unittest


def _avg(stat):
    return (stat.dmg[0] + stat.dmg[1]) / 2


class TestTheWeaponLadder(unittest.TestCase):
    """The starter Rusty Iron Sword cut 3-7; a new copper one 1-5 and a bronze
    one 2-6. The first two rungs of the ladder were steps down."""

    def _sword(self, metal):
        from hearthdelve.data import content
        return content.WEAPON_STATS[content.make_gear("Sword", metal)]

    def _starter(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        return content.WEAPON_STATS[items.SWORD]

    def test_every_metal_sword_beats_the_starter(self):
        from hearthdelve.data import content
        start = self._starter()
        for metal in content.FORGE_METALS:
            s = self._sword(metal)
            with self.subTest(metal=metal):
                self.assertGreaterEqual(_avg(s), _avg(start))
                self.assertGreaterEqual(s.to_hit, start.to_hit)
                self.assertGreater(_avg(s) + s.to_hit, _avg(start) + start.to_hit)

    def test_each_rung_through_steel_is_better_than_the_last(self):
        rungs = [self._starter()] + [self._sword(m) for m in ("copper", "bronze", "iron", "steel")]
        for worse, better in zip(rungs, rungs[1:]):
            self.assertGreaterEqual(_avg(better), _avg(worse))
            self.assertGreaterEqual(better.to_hit, worse.to_hit)
            self.assertGreater(_avg(better) + better.to_hit, _avg(worse) + worse.to_hit)

    def test_the_numbers(self):
        got = [(s.to_hit, s.dmg) for s in
               [self._starter()] + [self._sword(m) for m in ("copper", "bronze", "iron", "steel")]]
        self.assertEqual(got, [(1, (2, 6)), (2, (2, 6)), (2, (3, 7)), (2, (4, 8)), (3, (5, 9))])

    def test_steel_and_the_deep_metals_are_as_they_were(self):
        got = {m: (self._sword(m).to_hit, self._sword(m).dmg)
               for m in ("steel", "silver", "mithril", "adamantium")}
        self.assertEqual(got, {"steel": (3, (5, 9)), "silver": (3, (5, 9)),
                               "mithril": (4, (6, 10)), "adamantium": (4, (7, 11))})

    def test_a_clean_iron_sword_is_a_real_step_over_a_rusty_one(self):
        iron, rusty = self._sword("iron"), self._starter()
        self.assertEqual(_avg(iron) - _avg(rusty), 2)
        self.assertEqual(iron.to_hit - rusty.to_hit, 1)

    def test_rust_does_not_touch_what_armour_turns(self):
        from hearthdelve.data import content
        plain = content.ARMOR_STATS[content.make_gear("Helm", "iron")]
        rusty = content.ARMOR_STATS[content.make_gear("Helm", "iron", "rusty")]
        self.assertEqual(plain[0], rusty[0])                 # Dodge the same
        self.assertEqual(plain[1] - rusty[1], 1)             # one Protection, as before

    def test_no_weapon_can_roll_below_one(self):
        from hearthdelve.data import content
        for base in content.WEAPON_BASES:
            for metal in content.FORGE_METALS:
                for pfx in ("", "rusty"):
                    lo, _hi = content.WEAPON_STATS[content.make_gear(base, metal, pfx)].dmg
                    self.assertGreaterEqual(lo, 1)


if __name__ == "__main__":
    unittest.main()
