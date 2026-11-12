"""Forged gear is worth its metal; a set gem is worth the stone."""
from __future__ import annotations

import math
import unittest

from tests.common import fresh_state


class TestForgedGearIsWorthItsBars(unittest.TestCase):
    """An iron sword was 60g of work from 240g of iron, and the smith sold it
    for a quarter of what he asked for the two bars."""

    def test_every_forgeable_piece_clears_its_bars_by_a_quarter(self):
        from hearthdelve.data import content
        hard = [b for b in content.ARMOR_BASES if b not in content._SOFT_BASES]
        for metal in content.FORGE_METALS + content.SCALE_FORGE:
            bar = content.MATERIALS[metal].bar
            bases = hard + (list(content.WEAPON_BASES) if metal in content.FORGE_METALS else [])
            for base in bases:
                it = content.make_gear(base, metal)
                with self.subTest(piece=it.name):
                    self.assertGreaterEqual(it.value,
                                            bar.value * content.forge_cost(base) * 1.25)

    def test_the_anvil_offers_nothing_at_a_loss(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(121)
        for metal in content.FORGE_METALS + content.SCALE_FORGE:
            st.player.inventory.add(content.MATERIALS[metal].bar, 3)
        opts = crafting.machine_load_options(st, content.MACHINES["anvil"])
        self.assertTrue(opts)
        for o in opts:
            cost = sum(it.value * q for it, q in o["inputs"])
            with self.subTest(piece=o["output"].name):
                self.assertGreaterEqual(o["output"].value, cost * 1.25)

    def test_a_weapon_takes_metal_by_its_size(self):
        from hearthdelve.data import content
        self.assertEqual(content.forge_cost("Dagger"), 1)
        self.assertEqual(content.forge_cost("Sword"), 2)
        self.assertEqual(content.forge_cost("Greatsword"), 3)
        self.assertEqual(content.forge_cost("Armour"), 3)
        self.assertLess(content.make_gear("Dagger", "iron").value,
                        content.make_gear("Sword", "iron").value)
        self.assertLess(content.make_gear("Sword", "iron").value,
                        content.make_gear("Greatsword", "iron").value)

    def test_a_dearer_metal_makes_a_dearer_piece(self):
        from hearthdelve.data import content
        vals = [content.make_gear("Armour", m).value for m in ("copper", "bronze", "iron", "steel")]
        self.assertEqual(vals, sorted(vals))
        self.assertGreater(content.make_gear("Armour", "adamantium").value,
                           content.make_gear("Armour", "steel").value)

    def test_buying_it_costs_more_than_buying_the_bars(self):
        """The smith's own rule: a bought edge is dearer than a crafted one."""
        from hearthdelve.data import content
        price = dict(content.blacksmith_stock())
        for metal in ("copper", "iron", "steel"):
            bar = content.MATERIALS[metal].bar
            for base in content.WEAPON_BASES:
                it = content.make_gear(base, metal)
                with self.subTest(piece=it.name):
                    self.assertGreater(price[it], it.value)
                    self.assertGreaterEqual(price[it],
                                            price[bar] * content.forge_cost(base) * 0.9)

    def test_an_affix_still_scales_it(self):
        from hearthdelve.data import content
        plain = content.make_gear("Sword", "iron")
        fine = content.make_gear("Sword", "iron", "masterwork")
        rusty = content.make_gear("Sword", "iron", "rusty")
        self.assertGreater(fine.value, plain.value)
        self.assertLess(rusty.value, plain.value)

    def test_soft_and_leather_pieces_are_not_valued_as_metal(self):
        from hearthdelve.data import content
        self.assertEqual(content._forged_floor("Cloak", "silk"), 0)
        self.assertEqual(content._forged_floor("Helm", "leather"), 0)


class TestASetGemIsWorthTheStone(unittest.TestCase):
    """Setting a 240g topaz into a 165g leather armour made a 156g armour."""

    def test_setting_a_gem_never_loses_value(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(122)
        inv = st.player.inventory
        for it in (items.LEATHER_ARMOR, content.make_gear("Sword", "steel"),
                   content.make_gear("Helm", "iron"), content.make_gear("Cloak", "linen")):
            inv.add(it, 1)
        for name in ("Cut Topaz", "Cut Ruby", "Cut Sapphire", "Cut Emerald",
                     "Cut Amethyst", "Cut Diamond"):
            inv.add(items.by_name(name), 1)
        opts = [o for o in crafting.machine_load_options(st, content.MACHINES["jeweller"])
                if o.get("kind") == "embed_gear"]
        self.assertTrue(opts)
        for o in opts:
            cost = sum(it.value * q for it, q in o["inputs"])
            with self.subTest(piece=o["output"].name):
                self.assertGreater(o["output"].value, cost)

    def test_the_stone_carries_the_setters_quarter(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        plain = items.LEATHER_ARMOR
        topaz = items.by_name("Cut Topaz")
        set_ = content.embed_gem(plain, "topaz")
        self.assertIsNotNone(set_)
        self.assertEqual(set_.value, plain.value + round(topaz.value * 1.25))

    def test_a_second_stone_adds_again(self):
        from hearthdelve.data import content
        sword = content.make_gear("Sword", "steel")
        one = content.embed_gem(sword, "ruby")
        self.assertGreater(one.value, sword.value)


class TestRelicsAreWorthTheirTrophy(unittest.TestCase):
    def test_each_clears_its_trophy_and_bar(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        for trophy, relic in content.TROPHY_RELIC.items():
            with self.subTest(relic=relic.name):
                self.assertGreaterEqual(
                    relic.value, (trophy.value + items.SILVER_BAR.value) * 1.25)


if __name__ == "__main__":
    unittest.main()
