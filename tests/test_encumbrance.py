"""What things weigh on your back."""
from __future__ import annotations

import unittest


_BASES = ("Armour", "Helm", "Leggings", "Boots", "Gauntlets", "Girdle", "Shield", "Cloak")


def _suit(material):
    from hearthdelve.data import content
    from hearthdelve.game import encumbrance as enc
    return round(sum(enc.weight_of(content.make_gear(b, material)) for b in _BASES), 1)


class TestArmourHasRealWeight(unittest.TestCase):
    """Every armour piece weighed 3.0 — a straw hat as much as adamantium
    plate — so carry weight couldn't tell light armour from heavy, and
    mithril's lightness counted for nothing against adamantium's extra
    protection. A piece now weighs what it covers times its material's
    density."""

    def test_the_metals_weigh_what_they_should(self):
        self.assertGreater(_suit("adamantium"), _suit("iron"))
        self.assertGreater(_suit("iron"), _suit("mithril"))
        self.assertGreater(_suit("mithril"), _suit("leather"))
        self.assertAlmostEqual(_suit("iron"), 24.8, delta=1.0)   # about what a suit weighed before

    def test_bigger_pieces_weigh_more(self):
        from hearthdelve.data import content
        from hearthdelve.game import encumbrance as enc
        for metal in ("iron", "mithril", "adamantium"):
            body = enc.weight_of(content.make_gear("Armour", metal))
            girdle = enc.weight_of(content.make_gear("Girdle", metal))
            with self.subTest(metal=metal):
                self.assertGreater(body, girdle * 4)

    def test_cloth_is_next_to_nothing(self):
        from hearthdelve.data import content
        from hearthdelve.game import encumbrance as enc
        for cloth in ("straw", "cotton", "wool", "linen", "silk"):
            for base in ("Hat", "Cloak", "Robe"):
                with self.subTest(piece=f"{cloth} {base}"):
                    self.assertLessEqual(enc.weight_of(content.make_gear(base, cloth)), 0.5)

    def test_every_armour_material_has_a_density(self):
        """A material without one would fall back to the old flat weight."""
        from hearthdelve.data import content
        armour = list(content.FORGE_METALS) + ["hide", "leather", "straw", "cotton", "wool",
                                               "linen", "silk", "fur", "lurkerscale",
                                               "drakescale", "wyrmscale"]
        for m in armour:
            with self.subTest(material=m):
                self.assertGreater(content.MATERIALS[m].density, 0)


if __name__ == "__main__":
    unittest.main()
