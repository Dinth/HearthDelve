"""Crop hybrids: two related crops side by side, both in flower, may cross at
dawn; the crossed plant's harvest saves seed of a new, finer variety."""
from __future__ import annotations

import os
import random
import tempfile
import unittest
from unittest import mock

from tests.common import fresh_state


def _pair(st, a, b, flowering=True, apart=1):
    """Plant crops `a` and `b` side by side (or `apart`) on your own field."""
    from hearthdelve.data import content
    from hearthdelve.world import tile
    from hearthdelve.world.crops import CropPlot
    p = st.player
    pa, pb = (p.x + 2, p.y + 2), (p.x + 2 + apart, p.y + 2)
    plots = []
    for pos, name in ((pa, a), (pb, b)):
        crop = content.CROP_BY_NAME[name]
        st.surface.tiles[pos] = tile.TILLED
        plot = CropPlot(crop=crop, days_grown=crop.days_to_mature // 2 + 1 if flowering else 0,
                        watered=True)
        st.surface.crops[pos] = plot
        plots.append(plot)
    return pa, pb, plots


def _dawn(st, chance=1.0):
    from hearthdelve.game import farming
    with mock.patch.object(farming, "CROSS_CHANCE", chance):
        farming._cross_pollinate(st)


class TestTheHybridsAreSound(unittest.TestCase):
    def test_each_crosses_two_real_crops_and_is_worth_more_than_either(self):
        from hearthdelve.data import content
        for h in content.HYBRIDS:
            a, b = (content.CROP_BY_NAME[n] for n in content.HYBRID_PARENTS[h.name])
            with self.subTest(hybrid=h.name):
                self.assertNotIn(h, content.CROPS)
                self.assertGreaterEqual(h.produce.value, 1.25 * max(a.produce.value, b.produce.value))
                self.assertIs(content.SEED_TO_CROP[h.seed], h)
                self.assertIn(h.season, (a.season, b.season))

    def test_they_never_reach_worldgen_village_fields_or_the_herbarium(self):
        """A new crop in those lists would shift worldgen's draws and move whole
        villages in an existing save."""
        from hearthdelve.data import content
        for season in ("Spring", "Summer", "Fall", "Winter"):
            self.assertFalse(set(content.crops_in_season(season)) & set(content.HYBRIDS))
        herb = {it.name for wing in content.COLLECTION.values() for it in wing}
        self.assertFalse(herb & {h.name for h in content.HYBRIDS})

    def test_their_goods_are_worth_their_ingredient(self):
        from hearthdelve.data import content
        berry = content.CROP_BY_NAME["Frostberry"].produce
        self.assertGreater(content.FRUIT_JAM[berry].value, berry.value)
        swede = content.CROP_BY_NAME["Rutabaga"].produce
        self.assertGreater(content.VEG_PICKLE[swede].value, swede.value)


class TestCrossing(unittest.TestCase):
    def test_related_crops_in_flower_side_by_side_may_cross(self):
        st = fresh_state(2)
        _pa, _pb, plots = _pair(st, "Cauliflower", "Kale")
        _dawn(st)
        self.assertEqual(sorted(p.cross for p in plots), ["", "Romanesco"])

    def test_not_apart_not_unrelated_not_before_they_flower(self):
        for args in (("Cauliflower", "Kale", True, 2), ("Cauliflower", "Parsnip", True, 1),
                     ("Cauliflower", "Kale", False, 1)):
            with self.subTest(args=args):
                st = fresh_state(2)
                _pa, _pb, plots = _pair(st, *args)
                _dawn(st)
                self.assertEqual([p.cross for p in plots], ["", ""])

    def test_now_and_then_not_on_a_beat(self):
        from hearthdelve.game import farming
        st = fresh_state(2)
        _pa, _pb, plots = _pair(st, "Cauliflower", "Kale")
        days = 0
        while not any(p.cross for p in plots) and days < 400:
            st.day += 1
            farming._cross_pollinate(st)
            days += 1
        self.assertGreater(days, 1)
        self.assertLess(days, 400)

    def test_the_villages_fields_aren_t_yours_to_cross(self):
        st = fresh_state(2)
        pa, pb, plots = _pair(st, "Cauliflower", "Kale")
        st.surface.village_fields = list(st.surface.village_fields) + [pa, pb]
        _dawn(st)
        self.assertEqual([p.cross for p in plots], ["", ""])


class TestSavingTheSeed(unittest.TestCase):
    def test_the_crossed_plant_gives_up_hybrid_seed_at_harvest(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming
        st = fresh_state(2)
        pa, pb, plots = _pair(st, "Cauliflower", "Kale")
        _dawn(st)
        pos, plot = next((pos, p) for pos, p in zip((pa, pb), plots) if p.cross)
        plot.days_grown = plot.crop.days_to_mature
        seed = content.CROP_BY_NAME["Romanesco"].seed
        farming.harvest(st, *pos)
        self.assertGreaterEqual(st.player.inventory.count(seed), 1)

    def test_the_seed_grows_the_hybrid_which_now_and_then_breeds_true(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming
        from hearthdelve.world import tile
        st = fresh_state(2)
        romanesco = content.CROP_BY_NAME["Romanesco"]
        self.assertEqual(st.season, romanesco.season)      # a new game opens in spring
        p = st.player
        pos = (p.x + 2, p.y + 2)
        st.surface.tiles[pos] = tile.TILLED
        st.player.inventory.add(romanesco.seed, 1)
        farming.plant(st, *pos, romanesco.seed)
        self.assertIs(st.surface.crops[pos].crop, romanesco)
        st.surface.crops[pos].days_grown = romanesco.days_to_mature
        with mock.patch("random.random", return_value=0.0):
            farming.harvest(st, *pos)
        self.assertGreaterEqual(st.player.inventory.count(romanesco.produce), 1)
        self.assertEqual(st.player.inventory.count(romanesco.seed), 1)       # it bred true

    def test_a_cross_survives_a_save_and_an_old_save_has_none(self):
        import json
        from hearthdelve.engine import save
        st = fresh_state(2)
        pa, pb, plots = _pair(st, "Cauliflower", "Kale")
        _dawn(st)
        crossed = next(pos for pos, p in zip((pa, pb), plots) if p.cross)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            self.assertEqual(save.load(path).surface.crops[crossed].cross, "Romanesco")
            with open(path) as fh:
                data = json.load(fh)
            for rec in data["crops"].values():
                del rec[7:]                                       # a save from before hybrids
            with open(path, "w") as fh:
                json.dump(data, fh)
            self.assertEqual(save.load(path).surface.crops[crossed].cross, "")

    def test_a_hybrid_plot_survives_a_save(self):
        from hearthdelve.data import content
        from hearthdelve.engine import save
        from hearthdelve.world.crops import CropPlot
        st = fresh_state(2)
        pos = (st.player.x + 2, st.player.y + 2)
        st.surface.crops[pos] = CropPlot(crop=content.CROP_BY_NAME["Frostberry"], days_grown=3)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            self.assertEqual(save.load(path).surface.crops[pos].crop.name, "Frostberry")


if __name__ == "__main__":
    unittest.main()
