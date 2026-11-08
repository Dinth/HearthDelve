"""Keys map to the actions they print, whatever the keyboard layout."""
from __future__ import annotations

import unittest

import tcod.event


def _press(sym, shift=False):
    from hearthdelve.engine import input as keys
    return keys.event_to_action(tcod.event.KeyDown(
        scancode=tcod.event.Scancode(0), sym=sym,
        mod=tcod.event.Modifier.SHIFT if shift else tcod.event.Modifier.NONE))


class TestTheStairKeysOnEveryLayout(unittest.TestCase):
    """German, French and most ISO boards have a key of its own for '<' that
    gives '>' when shifted. Its keysym is LESS either way, and the shift was
    ignored, so pressing '>' to go down climbed back up instead."""

    def test_shifted_less_key_goes_down(self):
        self.assertEqual(_press(tcod.event.KeySym.LESS, shift=True), ("descend",))

    def test_the_less_key_alone_goes_up(self):
        self.assertEqual(_press(tcod.event.KeySym.LESS), ("ascend",))

    def test_a_us_board_still_works(self):
        K = tcod.event.KeySym
        self.assertEqual(_press(K.PERIOD, shift=True), ("descend",))
        self.assertEqual(_press(K.COMMA, shift=True), ("ascend",))
        self.assertEqual(_press(K.PERIOD), ("wait",))


if __name__ == "__main__":
    unittest.main()
