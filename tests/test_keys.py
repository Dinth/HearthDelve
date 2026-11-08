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


class TestAShiftedDigitIsNotASlot(unittest.TestCase):
    """The digit's keysym is the same with Shift held, so '@' (Shift+2 on a
    US board) picked hotbar slot 2 and '!' slot 1."""

    def test_digits_pick_slots(self):
        K = tcod.event.KeySym
        self.assertEqual(_press(K.N2), ("slot", 1))
        self.assertEqual(_press(K.N0), ("slot", 9))

    def test_shifted_digits_do_not(self):
        K = tcod.event.KeySym
        for sym in (K.N1, K.N2, K.N9, K.N0):
            with self.subTest(sym=sym):
                self.assertIsNone(_press(sym, shift=True))


class TestTheCodexListsEveryKey(unittest.TestCase):
    """The codex's Controls page had drifted from the key map: no hotbar
    slot 0, no q, no Shift+U, no Tab in aim mode, and the farming page sent
    you to seeds on '6'."""

    def _keys(self):
        import re
        from hearthdelve.engine import codex
        from tests.common import fresh_state
        pages = dict(codex.build_codex_pages(fresh_state(1)))
        keys = set()
        for text, _c in pages["Controls"]:
            keys.update(t for t in re.split(r"[\s/,]+", text[:19]) if t)
        return pages, keys

    def test_every_command_key_is_listed(self):
        from hearthdelve.engine import input as keymap
        _pages, keys = self._keys()
        letters = set(keymap._LETTER_CMD) - {"d"}     # 'd' on the map only points to the pack
        wanted = letters | {"0", "Shift+C", "Shift+M", "Shift+U", ">", "<", "?", "Space", "Esc"}
        self.assertEqual(sorted(wanted - keys), [])

    def test_tab_in_aim_mode_is_explained(self):
        pages, _keys = self._keys()
        self.assertTrue(any("Tab swaps" in t for t, _c in pages["Controls"]))

    def test_no_page_sends_you_to_seeds_on_6(self):
        pages, _keys = self._keys()
        for title, rows in pages.items():
            for text, _c in rows:
                self.assertNotIn("seeds (6)", text, title)


if __name__ == "__main__":
    unittest.main()
