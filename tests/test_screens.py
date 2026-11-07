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


class TestRenderingFacade(unittest.TestCase):
    """rendering re-exports the overlays that moved to screens_render. When the
    split missed PAPERDOLL_SLOTS and equippables, nothing that only *draws*
    noticed — the equipment screen's key handler crashed the game instead."""

    def test_every_rendering_name_a_caller_uses_exists(self):
        import ast
        import pathlib
        from hearthdelve.engine import rendering
        root = pathlib.Path(rendering.__file__).resolve().parent.parent
        missing = []
        for path in sorted(root.rglob("*.py")):
            if path.name == "rendering.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            aliases = {a.asname or a.name for n in ast.walk(tree)
                       if isinstance(n, (ast.Import, ast.ImportFrom))
                       for a in n.names if a.name.split(".")[-1] == "rendering"}
            for n in ast.walk(tree):
                if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                        and n.value.id in aliases and not hasattr(rendering, n.attr)):
                    missing.append(f"{path.relative_to(root)}:{n.lineno} rendering.{n.attr}")
        self.assertEqual(missing, [])


def _key(ch: str, shift: bool = False):
    import tcod.event
    return tcod.event.KeyDown(
        scancode=tcod.event.Scancode(0), sym=tcod.event.KeySym(ord(ch)),
        mod=tcod.event.Modifier.SHIFT if shift else tcod.event.Modifier.NONE)


class TestEquipmentScreenKeys(unittest.TestCase):
    """Every bare letter on the equipment screen addresses a row: the worn
    slots first (take off), then the carried gear (put on)."""

    def _ui_with_gear(self):
        from hearthdelve import screens
        from hearthdelve.data import content
        from hearthdelve.game import commands as cmds
        st = fresh_state(6)
        helm = content.make_gear("Helm", "iron")
        st.player.inventory.add(helm, 1)
        cmds._equip(st, helm)
        st.player.inventory.add(content.make_gear("Boots", "iron"), 1)
        ui = screens.UI(st)
        ui.push(screens.EquipmentScreen())
        return ui, helm

    def test_every_letter_is_handled_without_crashing(self):
        import string
        ui, _ = self._ui_with_gear()
        for ch in string.ascii_lowercase:
            ui.top.on_raw(ui, _key(ch))
            ui.top.render(ui, _con())

    def test_the_first_letter_takes_off_the_helm(self):
        from hearthdelve.engine import rendering
        ui, helm = self._ui_with_gear()
        p = ui.state.player
        self.assertEqual(rendering.PAPERDOLL_SLOTS[0], "head")
        self.assertIs(p.equipment.get("head"), helm)
        self.assertTrue(ui.top.on_raw(ui, _key("a")))
        self.assertIsNone(p.equipment.get("head"))
        self.assertEqual(p.inventory.count(helm), 1)

    def test_a_gear_letter_puts_the_piece_on(self):
        from hearthdelve.engine import rendering
        ui, _ = self._ui_with_gear()
        p = ui.state.player
        gear = rendering.equippables(ui.state)
        boots = next(i for i, (it, _q, _ql) in enumerate(gear) if it.name == "Iron Boots")
        letter = chr(ord("a") + len(rendering.PAPERDOLL_SLOTS) + boots)
        self.assertNotIn(letter, ("e", "i"))
        ui.top.on_raw(ui, _key(letter))
        self.assertEqual(p.equipment.get("feet").name, "Iron Boots")


if __name__ == "__main__":
    unittest.main()
