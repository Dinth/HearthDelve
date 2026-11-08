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


if __name__ == "__main__":
    unittest.main()
