"""Birth signs: every boon fires, choices persist, old saves stay unsigned."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestZodiacBoons(unittest.TestCase):
    def test_ox_wolf_mule_coin(self):
        from hearthdelve.game import skills, combat, crafting
        from hearthdelve.game import encumbrance as enc
        from hearthdelve.entities import items
        st = fresh_state(12)
        p = st.player
        base_yield = skills.extra_yield_chance(st, "Farming")
        base_hit = combat.player_to_hit(st)
        base_cap = enc.capacity(st)
        base_bin = crafting.bin_value(st, items.WINE, 0)
        p.sign = "ox"
        self.assertAlmostEqual(skills.extra_yield_chance(st, "Farming"),
                               base_yield + 0.06)
        p.sign = "wolf"
        self.assertEqual(combat.player_to_hit(st), base_hit + 1)
        p.sign = "mule"
        self.assertEqual(enc.capacity(st), base_cap + 6)
        p.sign = "coin"
        self.assertEqual(crafting.bin_value(st, items.WINE, 0), round(base_bin * 1.03))

    def test_serpent_shortens_afflictions(self):
        from hearthdelve.game import combat
        st = fresh_state(12)
        st.player.sign = "serpent"
        combat.apply_status(st, "poison")
        self.assertEqual(st.player.status["poison"],
                         combat.STATUS["poison"]["turns"] - 1)
        # monsters never benefit from the player's stars
        class Dummy:
            status: dict = {}
            hp = 10
        d = Dummy()
        combat.apply_status(st, "burn", target=d)
        self.assertEqual(d.status["burn"], combat.STATUS["burn"]["turns"])

    def test_star_and_oak_apply_once_at_birth(self):
        from hearthdelve import screens
        st = fresh_state(12)
        hp0, en0 = st.player.max_hp, st.player.max_energy

        class FakeUI:
            state = st
            def pop(self):
                pass
        scr = screens.ZodiacScreen()
        from hearthdelve.data.content import ZODIAC
        scr.sel = next(i for i, z in enumerate(ZODIAC) if z[0] == "oak")
        scr.handle(FakeUI(), "confirm", ("confirm",))
        self.assertEqual(st.player.sign, "oak")
        self.assertEqual(st.player.max_hp, hp0 + 6)
        self.assertEqual(st.player.max_energy, en0)


class TestZodiacPersistence(unittest.TestCase):
    def test_sign_round_trips_and_old_saves_are_unsigned(self):
        import json
        import os
        import tempfile
        from hearthdelve.engine import save
        st = fresh_state(12)
        st.player.sign = "heron"
        path = os.path.join(tempfile.gettempdir(), "hd_zodiac_test.json")
        try:
            save.save(st, path)
            self.assertEqual(save.load(path).player.sign, "heron")
            with open(path) as f:
                raw = json.load(f)
            raw["player"].pop("sign", None)
            with open(path, "w") as f:
                json.dump(raw, f)
            self.assertEqual(save.load(path).player.sign, "")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


class TestZodiacScreen(unittest.TestCase):
    def test_chooser_renders(self):
        import tcod.console
        from hearthdelve.engine import rendering
        st = fresh_state(12)
        rendering.render_zodiac(tcod.console.Console(80, 50, order="F"), st, 0)
        st.player.sign = "wolf"
        rendering.render_character(tcod.console.Console(80, 50, order="F"), st)


if __name__ == "__main__":
    unittest.main()
