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


class TestAnyEggAndDairy(unittest.TestCase):
    def test_duck_and_goat_goods_cook_everything(self):
        """A farmer who keeps only ducks and goats can still cook the coop &
        dairy dishes — the wildcards take whatever the larder holds."""
        from hearthdelve.data import content
        from hearthdelve.game import crafting
        from hearthdelve.entities import items
        st = fresh_state(3)
        inv = st.player.inventory
        for it in (items.DUCK_EGG, items.DUCK_EGG, items.GOAT_MILK, items.GOAT_CHEESE,
                   items.FLOUR, items.POTATO, items.TOMATO, items.SUGAR):
            inv.add(it, 3)
        for name in ("Omelette", "Creamy Soup", "Cheese Omelette", "Pizza", "Cake"):
            r = next(r for r in content.RECIPES if r.name == name)
            self.assertTrue(crafting.has_inputs(st, r), f"{name} won't cook from duck/goat")

    def test_signature_dishes_name_the_premium_good(self):
        """Quiche and the tart require the rich duck egg / goat cheese by name —
        a guaranteed sink beyond mere substitution."""
        from hearthdelve.data import content
        from hearthdelve.game import crafting
        from hearthdelve.entities import items
        st = fresh_state(4)
        inv = st.player.inventory
        # only hen eggs & cow cheese — the signature dishes must NOT be craftable
        for it in (items.EGG, items.EGG, items.CHEESE, items.FLOUR, items.TOMATO):
            inv.add(it, 3)
        quiche = next(r for r in content.RECIPES if r.name == "Quiche")
        tart = next(r for r in content.RECIPES if r.name == "Goat Cheese Tart")
        self.assertFalse(crafting.has_inputs(st, quiche))
        self.assertFalse(crafting.has_inputs(st, tart))
        inv.add(items.DUCK_EGG, 2)
        inv.add(items.GOAT_CHEESE, 1)
        self.assertTrue(crafting.has_inputs(st, quiche))
        self.assertTrue(crafting.has_inputs(st, tart))


class TestAnglersCabinetAndPerkLatch(unittest.TestCase):
    def test_cabinet_covers_every_water(self):
        from hearthdelve.data import content
        ang = {it.name for it in content.COLLECTION["Angler's Cabinet"]}
        for must in ("Moonfish", "Tuna", "Sardine", "Cave Bass", "Glowfish", "Eel"):
            self.assertIn(must, ang, f"{must} missing from the Angler's Cabinet")
        self.assertGreaterEqual(len(ang), 21)

    def test_cave_fish_can_be_requested(self):
        from hearthdelve.game import requests
        from hearthdelve.entities import items
        st = fresh_state(6)
        pool_names = {p.name for p in requests._fish_pool(st)}
        for cave in (items.CAVE_BASS, items.EEL, items.BLINDFISH):
            self.assertIn(cave.name, pool_names)

    def test_a_completed_wing_keeps_its_perk_when_the_catalogue_grows(self):
        """The whole point of the latch: adding specimens must never revoke a
        perk the player already earned."""
        from hearthdelve.game import collection
        st = fresh_state(7)
        wing = "Angler's Cabinet"
        # not yet completed -> no perk
        self.assertFalse(collection.perk_earned(st, wing))
        # completed once (latched), but the live cabinet is now short of specimens
        st.stats[f"wing_done_{wing}"] = 1
        self.assertFalse(collection.wing_done(st, wing))     # live: cases unfilled
        self.assertTrue(collection.perk_earned(st, wing))    # earned: perk stays

    def test_cured_fish_are_requestable_and_loved(self):
        from hearthdelve.game import requests
        from hearthdelve.data import content
        from hearthdelve.entities import items
        st = fresh_state(8)
        inn = {p.name for p in requests._request_pool(st, "innkeeper")}
        self.assertTrue(any(c.name in inn for c in content.FISH_CURED.values()))
        pell = next(n for n in st.surface.npcs if n.name == "Old Pell")
        loved, _ = pell.gift_reaction(content.FISH_CURED[items.TROUT])
        neutral, _ = pell.gift_reaction(items.PERCH)          # raw fish: a different family
        self.assertGreater(loved, neutral)


if __name__ == "__main__":
    unittest.main()
