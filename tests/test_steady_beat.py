"""A run goes at one pace, however busy the mouse."""
from __future__ import annotations

import unittest


def _steps(loop_hz: float, seconds: float = 10.0) -> int:
    from hearthdelve import main
    beat, n = main.Beat(), 0
    for i in range(int(seconds * loop_hz)):
        n += beat.due(i / loop_hz)
    return n


class TestRealTimeWorkKeepsItsPace(unittest.TestCase):
    """The loop turns once per frame and once per input event, and a run took
    a step on every turn: moving the mouse over the window made runs, rests
    and long jobs play out twice as fast at 60Hz and four times at 120Hz."""

    def test_a_fast_loop_steps_no_faster(self):
        for hz in (60, 120, 144, 1000):
            with self.subTest(hz=hz):
                self.assertAlmostEqual(_steps(hz), 300, delta=3)

    def test_an_idle_loop_steps_every_pass(self):
        self.assertEqual(_steps(29.0), 290)

    def test_a_stall_is_not_made_up_for_in_a_burst(self):
        from hearthdelve import main
        beat = main.Beat()
        self.assertTrue(beat.due(0.0))
        self.assertTrue(beat.due(5.0))                    # the window was dragged a while
        self.assertFalse(beat.due(5.001))
        self.assertFalse(beat.due(5.02))
        self.assertTrue(beat.due(5.04))

    def test_the_loop_ticks_on_the_beat(self):
        import inspect
        from hearthdelve import main
        src = inspect.getsource(main._loop)
        self.assertIn("if beat.due(", src)
        self.assertEqual(src.count("ui.top.tick(ui)"), 1)


if __name__ == "__main__":
    unittest.main()
