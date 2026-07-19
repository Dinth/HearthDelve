"""Economy guard-rails: the >=25% margin rule and outlier ceilings."""
from __future__ import annotations

import unittest

from tests.common import shared_state


def _input_value(inputs) -> int:
    return sum(it.value * q for it, q in inputs)


class TestAlchemyMargins(unittest.TestCase):
    def test_every_remedy_clears_25_percent(self):
        from hearthdelve.data import content
        for r in content.RECIPES:
            if r.kind != "remedy":
                continue
            iv = _input_value(r.inputs)
            ov = r.output.value * r.out_qty
            self.assertGreaterEqual(ov, iv * 1.25,
                                    f"{r.name}: {iv} -> {ov} breaks the margin rule")

    def test_potions_and_vodka_chain(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        for inputs, out, oq, _lvl, _mins in content.APOTHECARY_POTIONS:
            iv = _input_value(inputs)
            self.assertGreaterEqual(out.value * oq, iv * 1.25 - 1,
                                    f"{out.name} margin too thin")
        self.assertGreater(items.GRAIN_MASH.value, items.POTATO.value * 1.25)
        self.assertGreater(items.VODKA.value, items.GRAIN_MASH.value * 1.25)

    def test_no_apothecary_gold_printer(self):
        """Guard the Mandrake Elixir regression: no bench good may out-earn the
        game's established top chains (~480 g/day for oil)."""
        from hearthdelve.data import content
        bench = content.MACHINES["apothecary"].minutes
        worst = ("", 0.0)
        for r in content.RECIPES:
            if r.kind != "remedy":
                continue
            gain = (r.output.value * r.out_qty - _input_value(r.inputs)) * 2  # double batch
            per_day = gain * (1440 / bench)
            if per_day > worst[1]:
                worst = (r.name, per_day)
        self.assertLessEqual(worst[1], 500, f"{worst[0]} prints {worst[1]:.0f} g/day")


class TestRequestBoard(unittest.TestCase):
    ROLES = ("innkeeper", "blacksmith", "carpenter", "forester", "forager", "priest",
             "farmer", "fisher", "child", "trader",
             "woodcarver", "bard", "mason", "diver", "trapper")

    def test_every_role_has_a_pool(self):
        from hearthdelve.game import requests
        st = shared_state()
        for role in self.ROLES:
            pool = requests._request_pool(st, role)
            self.assertTrue(pool, f"empty request pool for {role}")
            self.assertTrue(all(p.value > 0 for p in pool),
                            f"{role} pool holds a worthless item")

    def test_every_role_has_a_voice(self):
        from hearthdelve.game.requests import _FLAVOR
        for role in ("woodcarver", "bard", "mason", "diver", "trapper"):
            self.assertIn(role, _FLAVOR)


class TestCollection(unittest.TestCase):
    def test_catalogue_is_donatable_and_sinkable(self):
        from hearthdelve.data import content
        total = sum(len(v) for v in content.COLLECTION.values())
        self.assertEqual(total, len(content.COLLECTED_NAMES))
        self.assertGreaterEqual(total, 60)
        for wing, its in content.COLLECTION.items():
            for it in its:
                self.assertGreater(it.value, 0, f"{it.name} in {wing} is worthless")


if __name__ == "__main__":
    unittest.main()
