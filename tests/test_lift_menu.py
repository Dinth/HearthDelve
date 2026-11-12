"""The lift's list of stops fits the screen however deep the shaft goes."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _draw(st, sel):
    from hearthdelve.engine import rendering
    con = tcod.console.Console(80, 50, order="F")
    rendering.render_lift(con, st, sel)
    return ["".join(chr(c) for c in con.ch[:, y]) for y in range(con.height)]


def _deep(floor):
    st = fresh_state(23)
    st.stats["found_underriver"] = 1
    st.stats["dwarfhold_deepest"] = floor
    return st


class TestTheStopsScroll(unittest.TestCase):
    """The window grew a row per stop with no cap, and the mine has no
    bottom: from floor 210 the title was cut off, from 225 the key hints,
    and from 255 the cursor could sit on a stop that was off the screen."""

    def test_the_frame_and_the_picked_stop_always_show(self):
        from hearthdelve.game import lift
        for floor in (40, 205, 230, 400, 1000):
            st = _deep(floor)
            stops = lift.stops(st)
            for sel in (0, len(stops) // 2, len(stops) - 1):
                rows = _draw(st, sel)
                with self.subTest(floor=floor, sel=sel):
                    self.assertTrue(any("Dwarven Lift" in r for r in rows))
                    self.assertTrue(any("Enter ride" in r for r in rows))
                    name = "Khazgrim" if sel == 0 else f"Floor {stops[sel]} "
                    picked = [r for r in rows if name in r]
                    self.assertEqual(len(picked), 1)
                    self.assertIn("▸", picked[0])

    def test_it_says_when_there_is_more_either_way(self):
        from hearthdelve.game import lift
        st = _deep(400)
        n = len(lift.stops(st))
        top, mid, end = ("\n".join(_draw(st, s)) for s in (0, n // 2, n - 1))
        self.assertEqual(("↑ more" in top, "↓ more" in top), (False, True))
        self.assertEqual(("↑ more" in mid, "↓ more" in mid), (True, True))
        self.assertEqual(("↑ more" in end, "↓ more" in end), (True, False))

    def test_a_short_list_is_drawn_whole(self):
        from hearthdelve.game import lift
        st = _deep(40)
        text = "\n".join(_draw(st, 0))
        self.assertNotIn("more", text)
        for d in lift.stops(st)[1:]:
            self.assertIn(f"Floor {d} ", text)


if __name__ == "__main__":
    unittest.main()
