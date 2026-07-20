"""Fishing sinks: every catch cooks, and curing pays for rarity."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestFishFamily(unittest.TestCase):
    def test_every_fish_shares_the_family(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        tables = ([f.item for f in content.FISH]
                  + [it for it, _ in content.SEA_FISH]
                  + [it for it, _ in content.CAVE_FISH]
                  + [items.MOONFISH])          # the lighthouse special
        self.assertGreaterEqual(len(set(tables)), 21)
        for it in tables:
            self.assertEqual(it.family, "fish", f"{it.name} is not in the fish family")

    def test_any_fish_dish_cooks_from_a_single_species(self):
        """Whatever the creel holds, an 'any fish' dish takes it — so none of the
        21 species is stuck as sell-only."""
        from hearthdelve.data import content
        from hearthdelve.game import crafting
        from hearthdelve.entities import items
        any_fish_recipes = [r for r in content.RECIPES
                            if content.ANY_FISH in [i for i, _ in r.inputs]]
        self.assertGreaterEqual(len(any_fish_recipes), 4)
        # Sashimi needs only a fish + salt — prove it cooks from the humblest catch
        st = fresh_state(5)
        inv = st.player.inventory
        inv.add(items.MINNOW, 1)
        inv.add(items.SEA_SALT, 1)
        sashimi = next(r for r in any_fish_recipes if r.name == "Sashimi")
        self.assertTrue(crafting.has_inputs(st, sashimi))
        pinned = crafting.resolve_inputs(inv, sashimi.inputs)
        self.assertIn(items.MINNOW, [it for it, _ in pinned])


class TestCuredFishPayForRarity(unittest.TestCase):
    def test_cured_value_scales_with_the_catch(self):
        from hearthdelve.data import content
        # Every cured good is an artisan good clearing its source by the margin rule
        for src, cured in content.FISH_CURED.items():
            self.assertEqual(cured.family, "cured_fish")
            self.assertIs(cured.source, src)
            self.assertGreaterEqual(cured.value, src.value * 1.25,
                                    f"{cured.name} breaks the >=25% margin rule")
        # …and a rare catch is worth curing far more than a common one
        from hearthdelve.entities import items
        self.assertGreater(content.FISH_CURED[items.MOONFISH].value,
                           content.FISH_CURED[items.CARP].value * 3)
        self.assertGreater(content.CAVIAR.value, items.STURGEON.value)

    def test_smoker_offers_a_cured_good_for_every_curable_fish(self):
        from hearthdelve.data import content
        fish_smokes = {src for src, _ in content.SMOKE_RECIPES if src.family == "fish"}
        self.assertEqual(fish_smokes, set(content.FISH_CURED))

    def test_cured_fish_round_trip_through_a_save(self):
        import os
        import tempfile
        from hearthdelve.data import content
        from hearthdelve.engine import save
        from hearthdelve.entities import items
        st = fresh_state(9)
        st.player.inventory.add(content.CAVIAR, 2)
        st.player.inventory.add(content.FISH_CURED[items.MOONFISH], 1)
        path = os.path.join(tempfile.gettempdir(), "hd_curedfish_test.json")
        try:
            save.save(st, path)
            st2 = save.load(path)
            self.assertEqual(st2.player.inventory.count(content.CAVIAR), 2)
            self.assertEqual(
                st2.player.inventory.count(content.FISH_CURED[items.MOONFISH]), 1)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
