"""Every major screen renders headlessly without crashing.

These are pure Console draws (no SDL context), so they run anywhere — the CI
equivalent of flipping through every menu once per push.
"""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _con():
    return tcod.console.Console(80, 50, order="F")


class TestMessageLog(unittest.TestCase):
    def test_repeats_coalesce(self):
        from hearthdelve.game.state import MessageLog
        log = MessageLog()
        for _ in range(3):
            log.add("A wall blocks the way.")
        self.assertEqual(len(log.messages), 1)
        self.assertEqual(log.messages[-1][0], "A wall blocks the way. (x3)")
        log.add("Something else.")
        log.add("A wall blocks the way.")            # streak broken, then repeats again
        self.assertEqual([t for t, _ in log.messages][-2:],
                         ["Something else.", "A wall blocks the way."])


class TestScreensRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = fresh_state(6)
        # a little of everything in the pack, so list screens have rows
        from hearthdelve.entities import items
        from hearthdelve.data import content
        p = cls.st.player
        p.inventory.add(items.BREAD, 2, quality=1)
        p.inventory.add(items.STONE, 5)
        p.inventory.add(items.CHAMOMILE, 2)
        p.inventory.add(content.make_gear("Sword", "iron"), 1)
        p.inventory.add(items.ARROW, 8)

    def test_world_and_hud(self):
        from hearthdelve.engine import rendering
        rendering.render_all(_con(), self.st, 0.0)

    def test_world_in_dungeon(self):
        from hearthdelve.engine import rendering
        from hearthdelve.game import delve
        st = fresh_state(6)
        delve.enter(st, "grotto")
        rendering.render_all(_con(), st, 0.0)
        rendering.render_world_map(_con(), st)         # map shows the land above
        delve.leave_to_surface(st)

    def test_inventory_all_filters(self):
        from hearthdelve.engine import rendering
        from hearthdelve.game import inventory
        self.st.player.inventory.slots.sort(
            key=lambda e: inventory.sort_key(e[0], e[2]))
        rendering.render_inventory(_con(), self.st, 0, None)
        for cat in inventory.categories(self.st):
            rendering.render_inventory(_con(), self.st, 0, cat)

    def test_equipment(self):
        from hearthdelve.engine import rendering
        rendering.render_equipment(_con(), self.st)

    def test_journal_every_tab(self):
        from hearthdelve.engine import rendering
        for tab in range(len(rendering._JOURNAL_TABS)):
            rendering.render_journal(_con(), self.st, tab)

    def test_world_map(self):
        from hearthdelve.engine import rendering
        rendering.render_world_map(_con(), self.st)

    def test_modals(self):
        from hearthdelve.engine import rendering
        st = self.st
        rendering.render_character(_con(), st)
        rendering.render_relationships(_con(), st, 0)
        rendering.render_craft(_con(), st, 0)
        rendering.render_ship(_con(), st, 0)
        rendering.render_eat(_con(), st, 0)
        rendering.render_donate(_con(), st, 0)
        rendering.render_message_log(_con(), st, 0)
        rendering.render_mail(_con(), st, 0)
        rendering.render_quit(_con(), st)
        rendering.render_intro(_con(), st)

    def test_requests_board_every_village(self):
        from hearthdelve.engine import rendering
        for village in ("Mossford", "Cinderhope", "Saltmere", "Fenwick"):
            rendering.render_requests(_con(), self.st, 0, village)

    def test_codex_pages(self):
        from hearthdelve.engine import codex
        for page in range(10):                          # generous page sweep
            codex.render_codex(_con(), self.st, page, 0)

    def test_look_mode_samples(self):
        from hearthdelve.engine import rendering
        st = self.st
        # describe a spread of tiles around the farm — must never raise
        for dx in range(-20, 21, 5):
            for dy in range(-20, 21, 5):
                rendering.describe(st, st.player.x + dx, st.player.y + dy)


if __name__ == "__main__":
    unittest.main()
