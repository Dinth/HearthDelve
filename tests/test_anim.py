"""The animation engine: one engine for everything that moves on screen."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _con():
    return tcod.console.Console(80, 50, order="F")


class TestOneEngine(unittest.TestCase):
    """The view's animations were written straight into the renderer's
    drawing functions. They now all run through the engine, layer by layer;
    the renderer only calls the layers at their places."""

    def test_a_frame_runs_every_layer_in_order(self):
        from unittest import mock
        from hearthdelve.engine import anim, rendering
        seen = []
        real = anim.run
        with mock.patch.object(anim, "run", side_effect=lambda layer, f: (seen.append(layer),
                                                                          real(layer, f))):
            rendering.render_all(_con(), fresh_state(2), 1.5)
        self.assertEqual(seen, list(anim.LAYERS))

    def test_every_ambient_animation_is_an_engine_effect(self):
        from hearthdelve.engine import anim
        from hearthdelve.engine import rendering  # noqa: F401  (registers the effects)
        names = {layer: [fn.__name__ for _o, fn in anim._ONGOING[layer]] for layer in anim.LAYERS}
        self.assertEqual(names[anim.SHADE], ["cloud_shadows"])
        self.assertEqual(names[anim.TINT], ["wind", "water_shimmer", "ore_twinkle",
                                            "campfire_flicker"])
        self.assertEqual(names[anim.GROUND], ["coastal_foam", "rain_on_the_ground"])
        self.assertEqual(names[anim.GROUND_LATE], ["gem_glitter", "lava_breathes"])
        self.assertEqual(names[anim.VEIL], ["westreach_weather"])
        self.assertEqual(names[anim.OVERLAY], ["weather", "seasonal_motes", "living_fire",
                                               "crossings"])

    def test_effects_in_a_layer_draw_lowest_order_first(self):
        from hearthdelve.engine import anim
        drawn = []
        try:
            anim.ongoing(anim.OVERLAY, 1001)(lambda f: drawn.append("second"))
            anim.ongoing(anim.OVERLAY, 1000)(lambda f: drawn.append("first"))
            from hearthdelve.engine import rendering
            rendering.render_all(_con(), fresh_state(2), 0.0)
        finally:
            anim._ONGOING[anim.OVERLAY][:] = [e for e in anim._ONGOING[anim.OVERLAY]
                                              if e[0] < 1000]
        self.assertEqual(drawn, ["first", "second"])

    def test_the_game_never_imports_drawing_code(self):
        """Game logic records what happens; it never reaches for the screen."""
        import pathlib
        import re
        root = pathlib.Path(__file__).resolve().parent.parent / "hearthdelve" / "game"
        drawing = re.compile(r"(engine\s+import\s+.*\b(rendering|anim|effects|screens_render|ui)\b"
                             r"|engine\.(rendering|anim|effects|screens_render|ui)\b"
                             r"|import\s+tcod\.(console|context))")   # (tcod.map is field of view)
        offenders = [f"{p.name}:{n}" for p in sorted(root.glob("*.py"))
                     for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                     if drawing.search(line)]
        self.assertEqual(offenders, [])



class TestOneOffEffects(unittest.TestCase):
    """Things that happen are recorded by the game (state.happen, never
    saved) and played by the engine for their short life, then dropped."""

    def setUp(self):
        from hearthdelve.engine import anim
        self.drawn = []
        anim.one_off("probe", life=1.0)(lambda f, h, age: self.drawn.append(round(age, 2)))
        self.st = fresh_state(2)

    def tearDown(self):
        from hearthdelve.engine import anim
        anim._ONE_OFFS.pop("probe", None)

    def _frame(self, t):
        from hearthdelve.engine import rendering
        rendering.render_all(_con(), self.st, t)

    def test_it_plays_from_the_frame_it_first_shows_on_then_goes(self):
        p = self.st.player
        self.st.happen("probe", p.x, p.y)
        for t in (10.0, 10.5, 10.99, 11.2, 12.0):
            self._frame(t)
        self.assertEqual(self.drawn, [0.0, 0.5, 0.99])
        self.assertEqual(self.st.fx, [])

    def test_a_happening_long_past_when_the_screen_gets_to_it_never_shows(self):
        p = self.st.player
        self.st.happen("probe", p.x, p.y)
        self.st.clock += 60 * 60                     # an hour's rest went by unseen
        self._frame(5.0)
        self.assertEqual(self.drawn, [])
        self.assertEqual(self.st.fx, [])

    def test_it_shows_only_on_the_map_it_happened_on(self):
        from hearthdelve.game import delve
        p = self.st.player
        mouth = sorted(q for q, k in self.st.surface.dungeon_kind.items() if k == "mine")[0]
        p.x, p.y = mouth
        self.st.happen("probe", p.x, p.y)            # on the surface…
        delve.enter(self.st, "mine")                 # …then straight down the stairs
        self._frame(1.0)
        self.assertEqual(self.drawn, [])

    def test_the_record_stays_short_with_no_screen_to_play_it(self):
        from hearthdelve.game import state as gs
        for i in range(gs.MAX_HAPPENINGS + 30):
            self.st.happen("probe", i, 0)
        self.assertEqual(len(self.st.fx), gs.MAX_HAPPENINGS)
        self.assertEqual(self.st.fx[-1].x, gs.MAX_HAPPENINGS + 29)


if __name__ == "__main__":
    unittest.main()
