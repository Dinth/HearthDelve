"""Karma now lands somewhere: shop prices and the shrine blessing react to it."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestKarmaShopPrices(unittest.TestCase):
    def _buy_price(self, k):
        from hearthdelve.game import village
        st = fresh_state(1)
        st.player.karma = k
        bron = next(n for n in st.surface.npcs if n.shop == "blacksmith")
        return next((r.price for r in village.shop_entries("blacksmith", st, bron)
                     if r.kind == "buy"), None)

    def test_a_hero_buys_cheaper_than_a_villain(self):
        hero, neutral, villain = self._buy_price(100), self._buy_price(0), self._buy_price(-100)
        self.assertLess(hero, neutral)
        self.assertLess(neutral, villain)
        self.assertGreater(hero, 0)                       # still buyable — a gradient, not a lock

    def test_a_hero_sells_dearer_than_a_villain(self):
        from hearthdelve.game import village
        from hearthdelve.entities import items

        def sell(k):
            st = fresh_state(2)
            st.player.karma = k
            st.player.inventory.add(items.WINE, 1)
            inn = next((n for n in st.surface.npcs if n.shop == "tavern"), None)
            return next((r.price for r in village.shop_entries("tavern", st, inn)
                         if r.kind == "sellto"), None)
        self.assertGreater(sell(100), sell(0))
        self.assertGreater(sell(0), sell(-100))

    def test_mults_are_soft_and_bounded(self):
        from hearthdelve.game import karma
        self.assertAlmostEqual(karma.buy_mult(0), 1.0)
        self.assertGreaterEqual(karma.buy_mult(100), 0.88)   # at most ~10% off
        self.assertLessEqual(karma.buy_mult(-100), 1.12)


class TestKarmaShrineBlessing(unittest.TestCase):
    def _bless_minutes(self, k):
        from hearthdelve.game import commands
        st = fresh_state(3)
        st.player.karma = k
        st.projects = [dict(p) for p in st.projects]
        for p in st.projects:
            if p["id"] == "shrine":
                p["state"] = "done"
        commands._pray(st)
        return st.player.buff_until - st.abs_minutes

    def test_the_good_are_blessed_longer(self):
        villain, neutral, saint = self._bless_minutes(-100), self._bless_minutes(0), self._bless_minutes(100)
        self.assertLess(villain, neutral)
        self.assertLess(neutral, saint)
        self.assertGreaterEqual(villain, 360)             # even the wicked get a grudging boon


class TestAPredatorIsAFightNotACruelty(unittest.TestCase):
    """Westreach beasts spawn as wildlife, so killing an Ash Wolf that hadn't
    yet turned on you cost karma like a rabbit, taught nothing and never reached
    the bestiary — and the sulphur their MONSTER_DROPS rows promised was dead
    data, never read for wildlife."""

    def _beast(self, name):
        from hearthdelve.data import content
        from hearthdelve.entities.monster import Mob
        c = next(c for c in content.WEST_WILDLIFE if c.name == name)
        return Mob(c.name, c.glyph, c.color, c.hp, c.hp, c.speed, c.behavior, 1, 1,
                   dv=c.dv, pv=c.pv, to_hit=c.to_hit, dmg=c.dmg, kind="wildlife",
                   diet=c.diet, seasons=c.seasons, inflicts=c.inflicts)

    def test_a_wolf_costs_no_karma_and_teaches_combat(self):
        from hearthdelve.game import combat
        st = fresh_state(1)
        wolf = self._beast("Ash Wolf")
        self.assertFalse(wolf.hostile)                     # not yet on the hunt
        st.world.monsters.append(wolf)
        xp = st.player.skills.get("Combat", 0)
        combat._on_kill(st, wolf)
        self.assertEqual(st.player.karma, 0)
        self.assertEqual(st.bestiary.get("Ash Wolf"), 1)
        self.assertGreater(st.player.skills.get("Combat", 0), xp)
        self.assertNotIn(wolf, st.world.monsters)

    def test_an_unroused_boar_is_still_an_unkindness(self):
        from hearthdelve.game import combat
        st = fresh_state(1)
        boar = self._beast("Cinder Boar")                   # defensive, not a hunter
        st.world.monsters.append(boar)
        combat._on_kill(st, boar)
        self.assertEqual(st.player.karma, -2)
        self.assertNotIn("Cinder Boar", st.bestiary)

    def test_the_volcanic_beasts_yield_sulphur_and_no_drop_row_is_dead(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        for name in ("Rock Viper", "Ember Drake"):
            self.assertIn(items.SULPHUR, [it for it, _c, _q in content.WILDLIFE_DROPS[name]])
        foes = {m.name for m in content.MONSTERS} | {b.name for b in content.BOSSES}
        self.assertEqual(sorted(set(content.MONSTER_DROPS) - foes), [])


if __name__ == "__main__":
    unittest.main()
