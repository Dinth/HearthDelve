"""PgUp and PgDn page through the codex."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _con():
    return tcod.console.Console(80, 50, order="F")


def _text(con) -> str:
    return "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(con.height))


class TestTheCodexPages(unittest.TestCase):
    """PgUp/PgDn did nothing in the codex, whose longest page is over three
    hundred rows at one row a keypress."""

    def test_page_keys_move_most_of_a_screen(self):
        from hearthdelve import screens
        ui = screens.UI(fresh_state(31), None)
        scr = screens.HelpScreen()
        con = _con()
        longest = max(range(12), key=lambda p: self._length(ui, p))
        scr.page = longest
        scr.handle(ui, "scroll", ("scroll", -1))
        scr.render(ui, con)
        self.assertEqual(scr.scroll, screens.HelpScreen.PAGE)
        scr.handle(ui, "scroll", ("scroll", 1))
        scr.handle(ui, "scroll", ("scroll", 1))
        scr.render(ui, con)
        self.assertEqual(scr.scroll, 0)

    def _length(self, ui, page):
        from hearthdelve.engine import codex
        return codex.render_codex(_con(), ui.state, page, 10_000)


if __name__ == "__main__":
    unittest.main()
