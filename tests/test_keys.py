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



class TestRealKeysThroughTheGame(unittest.TestCase):
    """Key handling lived inside main.py's loop, out of reach of any test, so
    the cheat code, the keys that work from every screen and the quit prompt
    were only ever checked by hand. These press real key events through
    main.route_event, the very path the loop takes."""

    def setUp(self):
        from hearthdelve import screens
        from tests.common import fresh_state
        self.music = _FakeMusic()
        self.ui = screens.UI(fresh_state(2), self.music)
        self.konami = []

    def _press(self, sym, shift=False, repeat=False):
        from hearthdelve import main
        ev = tcod.event.KeyDown(scancode=tcod.event.Scancode(0), sym=sym,
                                mod=tcod.event.Modifier.SHIFT if shift else tcod.event.Modifier.NONE,
                                repeat=repeat)
        return main.route_event(self.ui, ev, self.konami)

    def _key(self, ch, shift=False, repeat=False):
        return self._press(tcod.event.KeySym(ord(ch)), shift, repeat)

    def test_the_konami_code_opens_the_cheats(self):
        from hearthdelve import screens
        K = tcod.event.KeySym
        for sym in (K.UP, K.UP, K.DOWN, K.DOWN, K.LEFT, K.RIGHT, K.LEFT, K.RIGHT):
            self._press(sym)
        self._key("b")
        self.ui.top.handle(self.ui, "cancel", ("cancel",))     # 'b' opened the bin; close it
        self._key("a")
        self.assertIsInstance(self.ui.top, screens.CheatScreen)

    def test_shift_u_mutes_the_music_from_any_screen(self):
        from hearthdelve import screens
        self._key("i")
        self.assertIsInstance(self.ui.top, screens.InventoryScreen)
        self._key("u", shift=True)
        self.assertTrue(self.music.muted)
        self.assertIsInstance(self.ui.top, screens.InventoryScreen)   # and nothing else moved

    def test_quit_without_saving_from_the_prompt(self):
        from hearthdelve import screens
        self._key("q")
        self.assertIsInstance(self.ui.top, screens.QuitScreen)
        self._press(tcod.event.KeySym.BACKSPACE)
        self.assertFalse(self.ui.running)
        self.assertFalse(self.ui.save_on_exit)

    def test_a_held_key_does_not_repeat_a_one_off_action(self):
        from hearthdelve import screens
        self._key("i")
        self._key("i", repeat=True)                        # OS key-repeat of the same press
        self.assertIsInstance(self.ui.top, screens.InventoryScreen)

    def test_pack_letters_pick_their_rows_and_shift_d_drops(self):
        from hearthdelve.engine import rendering
        from hearthdelve.entities import items
        p = self.ui.state.player
        p.inventory.add(items.WOOD, 3)
        p.inventory.add(items.STONE, 4)
        self._key("i")
        screen = self.ui.top
        rows = [e[0] for e in p.inventory.slots]
        target = rows.index(items.STONE)
        self._key(rendering.INV_LETTERS[target])
        self.assertEqual(screen.sel, target)
        self._key("d", shift=True)
        self.assertEqual(p.inventory.count(items.STONE), 0)


class _FakeMusic:
    muted = False

    def toggle_mute(self):
        self.muted = not self.muted
        return self.muted


if __name__ == "__main__":
    unittest.main()
