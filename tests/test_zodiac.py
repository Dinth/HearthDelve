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
        from hearthdelve.game import attrs as A
        st = fresh_state(12)
        hp0, en0 = st.player.max_hp, st.player.max_energy

        class FakeUI:
            state = st
            def pop(self):
                pass
        scr = screens.CharGenScreen()
        scr.ctx = {"sign": "oak", "attrs": {k: 10 for k in A.ATTRS}}
        scr.handle(FakeUI(), "confirm", ("confirm",))
        self.assertEqual(st.player.sign, "oak")
        self.assertEqual(st.player.max_hp, hp0 + 6)      # oak only; To 10 adds nothing
        self.assertEqual(st.player.max_energy, en0)
        self.assertEqual(st.player.attrs["St"], 10)


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


class TestCharGenScreen(unittest.TestCase):
    def test_chargen_renders_and_rerolls(self):
        import tcod.console
        from hearthdelve import screens
        from hearthdelve.engine import rendering
        from hearthdelve.game import attrs as A
        st = fresh_state(12)
        scr = screens.CharGenScreen()
        self.assertIn(scr.ctx["sign"], {z[0] for z in
                                        __import__("hearthdelve.data.content",
                                                   fromlist=["ZODIAC"]).ZODIAC})
        for k in A.ATTRS:
            self.assertTrue(3 <= scr.ctx["attrs"][k] <= 18)
        rendering.render_chargen(tcod.console.Console(80, 50, order="F"), st, scr.ctx)
        st.player.sign = "wolf"
        st.player.attrs = {k: 12 for k in A.ATTRS}
        rendering.render_character(tcod.console.Console(80, 50, order="F"), st)


class TestCreationSurvivesQuitting(unittest.TestCase):
    """The 'life not yet begun' flag was cleared the moment the intro opened and
    never saved: closing the window at the intro or at the midwives' roll saved
    an unsigned, all-10s farmer, and creation never came back."""

    def setUp(self):
        import contextlib
        import io
        import os
        import tempfile
        from unittest import mock
        self.dir = tempfile.mkdtemp(prefix="hd-chargen-")
        self.env = mock.patch.dict(os.environ, {"HEARTHDELVE_SAVE": os.path.join(self.dir, "s.json")})
        self.env.start()
        self.quiet = contextlib.redirect_stderr(io.StringIO())
        self.quiet.__enter__()

    def tearDown(self):
        import shutil
        self.quiet.__exit__(None, None, None)
        self.env.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _opened(self, st):
        from hearthdelve import main, screens
        ui = screens.UI(st)
        main.open_screens(ui)
        return ui, [type(s).__name__ for s in ui.stack]

    def test_closing_the_window_at_the_intro_resumes_creation(self):
        from hearthdelve import main
        from hearthdelve.engine import save
        st = fresh_state(12)
        ui, stack = self._opened(st)
        self.assertEqual(stack, ["PlayScreen", "CharGenScreen", "IntroScreen"])
        main.run_guarded(ui, lambda: None)            # the window closes on the intro
        again = save.load()
        self.assertTrue(again.chargen_pending)
        self.assertEqual(self._opened(again)[1], ["PlayScreen", "CharGenScreen", "IntroScreen"])

    def test_a_crash_at_the_midwives_roll_resumes_creation(self):
        from hearthdelve import main
        from hearthdelve.engine import save
        ui, _ = self._opened(fresh_state(12))
        ui.pop()                                       # past the intro, onto the roll

        def crash():
            raise RuntimeError("fell over mid-roll")
        with self.assertRaises(RuntimeError):
            main.run_guarded(ui, crash)
        self.assertTrue(save.load().chargen_pending)

    def test_accepting_a_life_ends_it_for_good(self):
        from hearthdelve.engine import save
        ui, _ = self._opened(fresh_state(12))
        ui.pop()                                       # dismiss the intro
        ui.top.handle(ui, "confirm", ("confirm",))     # accept the roll
        self.assertFalse(ui.state.chargen_pending)
        self.assertTrue(ui.state.player.sign)
        save.save(ui.state)
        again = save.load()
        self.assertFalse(again.chargen_pending)
        self.assertEqual(again.player.sign, ui.state.player.sign)
        self.assertEqual(self._opened(again)[1], ["PlayScreen"])

    def test_an_older_save_is_a_life_already_begun(self):
        import json
        from hearthdelve.engine import save
        save.save(fresh_state(12))
        with open(save.default_path()) as f:
            raw = json.load(f)
        raw.pop("chargen_pending")
        with open(save.default_path(), "w") as f:
            json.dump(raw, f)
        self.assertFalse(save.load().chargen_pending)


if __name__ == "__main__":
    unittest.main()
