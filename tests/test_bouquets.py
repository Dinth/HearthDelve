"""A bouquet: what a tulip bed is for, and a gift anyone is glad of."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _bouquet(flower):
    from hearthdelve.data import content
    return content.FLOWER_BOUQUET[flower]


class TestTyingOne(unittest.TestCase):
    """The tulip was the one crop with nowhere to go but the bin and a
    priest's favour: no recipe, no press, no project."""

    def test_every_flower_crop_has_one(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        self.assertEqual({f.name for f in content.FLOWER_BOUQUET},
                         {"Tulip", "Sunflower", "Aster"})
        self.assertEqual(_bouquet(items.TULIP).name, "Tulip Bouquet")

    def test_it_is_worth_more_than_its_stems(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        for f, b in content.FLOWER_BOUQUET.items():
            cost = f.value * content.BOUQUET_STEMS + items.FIBER.value
            with self.subTest(flower=f.name):
                self.assertGreaterEqual(b.value, cost * 1.25)

    def test_three_stems_and_fibre_make_it(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(23)
        inv = st.player.inventory
        inv.add(items.TULIP, 3)
        inv.add(items.FIBER, 1)
        r = next(r for r in content.RECIPES if r.name == "Tulip Bouquet")
        self.assertIn(r, crafting.visible_recipes(st))
        self.assertTrue(crafting.craft(st, r))
        self.assertEqual((inv.count(_bouquet(items.TULIP)), inv.count(items.TULIP)), (1, 0))

    def test_it_survives_a_save(self):
        from hearthdelve.engine import save
        from hearthdelve.entities import items
        st = fresh_state(23)
        st.player.inventory.add(_bouquet(items.TULIP), 2)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            back = save.load(path)
        self.assertEqual(back.player.inventory.count(_bouquet(items.TULIP)), 2)


class TestGivingOne(unittest.TestCase):
    def _folk(self):
        return fresh_state(23).surface.npcs

    def test_anyone_is_glad_of_it(self):
        from hearthdelve.entities import items
        b = _bouquet(items.TULIP)
        for n in self._folk():
            if items.TULIP in n.dislikes:
                continue
            with self.subTest(npc=n.name):
                self.assertIn(n.taste(b), ("likes", "loves"))
                self.assertGreater(n.gift_reaction(b)[0], n.gift_reaction(items.STONE)[0]
                                   if n.taste(items.STONE) == "" else 20)

    def test_whoever_is_fond_of_the_flower_loves_it(self):
        from hearthdelve.entities import items
        b = _bouquet(items.TULIP)
        fond = [n for n in self._folk() if items.TULIP in n.likes + n.loves]
        self.assertGreaterEqual(len(fond), 3)
        for n in fond:
            self.assertEqual((n.taste(b), n.gift_reaction(b)[0]), ("loves", 80))
        plain = next(n for n in self._folk() if items.TULIP not in n.likes + n.loves + n.dislikes)
        self.assertEqual((plain.taste(b), plain.gift_reaction(b)[0]), ("likes", 45))

    def test_one_who_cannot_abide_the_flower_turns_it_down(self):
        from hearthdelve.entities import items
        st = fresh_state(23)
        folk = list(st.surface.npcs) + list(getattr(st, "dwarves", None) or [])
        n = next((n for n in folk if items.TULIP in n.dislikes), None)
        if n is None:
            n = folk[0]
            n.dislikes = n.dislikes + (items.TULIP,)
        self.assertEqual(n.taste(_bouquet(items.TULIP)), "dislikes")
        self.assertNotEqual(n.taste(_bouquet(items.SUNFLOWER)), "dislikes")

    def test_taste_is_unchanged_for_everything_else(self):
        from hearthdelve.entities import items
        for n in self._folk():
            for it in n.loves:
                self.assertEqual(n.taste(it), "loves")
            for it in n.dislikes:
                if not n._matches(it, n.loves) and not n._matches(it, n.likes):
                    self.assertEqual(n.taste(it), "dislikes")
        self.assertEqual(self._folk()[0].gift_reaction(items.SLING_STONE)[0], 20)

    def test_the_gift_screen_puts_it_with_the_liked_things(self):
        from hearthdelve.entities import items
        from hearthdelve.game import village
        st = fresh_state(23)
        st.player.inventory.slots[:] = []
        st.player.inventory.add(items.STONE, 1)
        st.player.inventory.add(_bouquet(items.TULIP), 1)
        n = next(n for n in st.surface.npcs
                 if n.taste(items.STONE) == "" and items.TULIP not in n.dislikes)
        self.assertEqual(village.giftable_items(st, n)[0][0], _bouquet(items.TULIP))


if __name__ == "__main__":
    unittest.main()
