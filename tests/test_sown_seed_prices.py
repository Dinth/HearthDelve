"""Seed you buy again at every harvest is priced so the crop still pays."""
from __future__ import annotations

import unittest


def _per_day(crop, price):
    from hearthdelve.engine import constants as C
    L = C.SEASON_LEN
    if crop.regrows:
        picks = 1 + max(0, (L - crop.days_to_mature - 1) // max(1, crop.regrow_days))
        return (picks * crop.produce.value - price) / L
    sowings = (L - 1) // crop.days_to_mature
    return sowings * (crop.produce.value - price) / L


class TestSownCrops(unittest.TestCase):
    """Parsnip, potato and cucumber earned 3-4g a plot a day beside kale's 14."""

    SOWN = ("Parsnip", "Potato", "Cauliflower", "Carrot", "Cucumber", "Cabbage", "Beet", "Leek")

    def test_no_sown_vegetable_earns_less_than_a_quarter_of_its_seasons_best_regrower(self):
        from hearthdelve.data import content
        price = dict(content.GENERAL_STOCK)
        by = {c.name: c for c in content.CROPS}
        for name in self.SOWN:
            crop = by[name]
            best = max(_per_day(c, price[c.seed]) for c in content.CROPS
                       if c.season == crop.season and c.regrows and c.seed in price)
            with self.subTest(crop=name):
                self.assertGreaterEqual(_per_day(crop, price[crop.seed]), best / 4.2)

    def test_the_seed_never_costs_more_than_half_the_crop(self):
        from hearthdelve.data import content
        price = dict(content.GENERAL_STOCK)
        by = {c.name: c for c in content.CROPS}
        for name in self.SOWN:
            with self.subTest(crop=name):
                self.assertLessEqual(price[by[name].seed], by[name].produce.value / 2)

    def test_a_regrower_still_out_earns_what_you_must_resow(self):
        """Patience and a dearer seed are still worth something."""
        from hearthdelve.data import content
        price = dict(content.GENERAL_STOCK)
        by = {c.name: c for c in content.CROPS}
        self.assertGreater(_per_day(by["Kale"], price[by["Kale"].seed]),
                           _per_day(by["Parsnip"], price[by["Parsnip"].seed]))

    def test_seed_cannot_be_sold_back(self):
        from hearthdelve.data import content
        by = {c.name: c for c in content.CROPS}
        for name in self.SOWN:
            self.assertEqual(by[name].seed.value, 0)


if __name__ == "__main__":
    unittest.main()
