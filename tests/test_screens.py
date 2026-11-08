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
    """Every letter on the equipment screen addresses a row: the worn slots
    first (take off), then the carried gear (put on)."""

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
        letter = rendering.inv_letter(len(rendering.PAPERDOLL_SLOTS) + boots)
        ui.top.on_raw(ui, _key(letter.lower(), shift=letter.isupper()))
        self.assertEqual(p.equipment.get("feet").name, "Iron Boots")

    def test_every_worn_slot_comes_off_by_the_letter_beside_it(self):
        """The Girdle sat on 'e' and the Amulet on 'i' — both screen switches —
        so neither could be taken off by letter."""
        from hearthdelve.engine import rendering
        for i, slot in enumerate(rendering.PAPERDOLL_SLOTS):
            letter = rendering.inv_letter(i)
            with self.subTest(slot=slot, letter=letter):
                self.assertNotIn(letter, "ei ")
                self.assertEqual(rendering.letter_index(letter), i)
        from hearthdelve.data import content
        from hearthdelve.game import commands as cmds
        ui, _ = self._ui_with_gear()
        girdle = content.make_gear("Girdle", "iron")
        ui.state.player.inventory.add(girdle, 1)
        cmds._equip(ui.state, girdle)
        self.assertIs(ui.state.player.equipment.get("waist"), girdle)
        letter = rendering.inv_letter(rendering.PAPERDOLL_SLOTS.index("waist"))
        self.assertTrue(ui.top.on_raw(ui, _key(letter)))
        self.assertIsNone(ui.state.player.equipment.get("waist"))


class TestPackLetters(unittest.TestCase):
    """The pack drew a-z then A-Z beside its rows, but only bare a-z (minus e
    and i) picked anything: the e and i rows and every capital row were dead
    labels, and Shift+D — which reads as 'pick D' — dropped the highlighted
    stack instead."""

    def _ui_with_a_full_pack(self, n=60):
        from hearthdelve import screens
        from hearthdelve.entities import items
        from hearthdelve.game import inventory
        st = fresh_state(6)
        cheap = [it for it in items.BY_NAME.values()
                 if it.stackable and it.value < 100 and it.kind not in
                 ("weapon", "armor", "jewelry", "ranged", "ammo", "bomb")]
        for it in cheap[:n]:
            st.player.inventory.add(it, 1)
        st.player.inventory.slots.sort(key=lambda e: inventory.sort_key(e[0], e[2]))
        ui = screens.UI(st)
        ui.push(screens.InventoryScreen())
        return ui

    def test_every_drawn_letter_picks_its_own_row(self):
        from hearthdelve.engine import rendering
        ui = self._ui_with_a_full_pack()
        shown = len(ui.top._visible(ui.state))
        self.assertGreater(shown, len(rendering.INV_LETTERS))
        for v in range(shown):
            letter = rendering.inv_letter(v)
            if letter == " ":
                continue                                  # past the alphabet: arrows only
            with self.subTest(row=v, letter=letter):
                self.assertTrue(ui.top.on_raw(ui, _key(letter.lower(), shift=letter.isupper())))
                self.assertEqual(ui.top.sel, v)

    def test_the_screens_own_keys_are_never_labels(self):
        from hearthdelve.engine import input as game_input, rendering
        ui = self._ui_with_a_full_pack()
        for ch, shift, cmd in (("e", False, "equipment"), ("i", False, "inventory"),
                               ("d", True, "drop"), ("u", True, "mutemusic")):
            label = ch.upper() if shift else ch
            with self.subTest(key=label):
                self.assertNotIn(label, rendering.INV_LETTERS)
                self.assertFalse(ui.top.on_raw(ui, _key(ch, shift=shift)))
                self.assertEqual(game_input.event_to_action(_key(ch, shift=shift))[0], cmd)

    def test_shift_d_drops_the_highlighted_stack_not_another_row(self):
        from hearthdelve.engine import input as game_input
        ui = self._ui_with_a_full_pack()
        slots = ui.state.player.inventory.slots
        vis = ui.top._visible(ui.state)
        first, other = slots[vis[0]][0], slots[vis[3]][0]
        self.assertTrue(ui.top.on_raw(ui, _key("a")))
        ev = _key("d", shift=True)
        self.assertFalse(ui.top.on_raw(ui, ev))
        action = game_input.event_to_action(ev)          # what main routes it to
        ui.top.handle(ui, action[0], action)
        self.assertEqual(ui.state.player.inventory.count(first), 0)
        self.assertEqual(ui.state.player.inventory.count(other), 1)
        ui.top.render(ui, _con())


class TestLookSeesOnlyWhatYouSee(unittest.TestCase):
    """Look named any monster on a dungeon floor — HP, DV, elite and all — even
    in rooms you had never entered, and described surface critters hibernating
    out of season, which the game itself treats as not there."""

    def _floor(self):
        from hearthdelve.game import delve
        st = fresh_state(6)
        mouth = next(p for p, k in st.surface.dungeon_kind.items() if k == "grotto")
        st.player.x, st.player.y = mouth
        delve.enter(st, "grotto")
        return st

    def test_an_unexplored_monster_is_just_darkness(self):
        from hearthdelve.engine import rendering
        st = self._floor()
        gm = st.world
        m = next(m for m in gm.monsters if not gm.explored[m.x, m.y])
        text = rendering.describe(st, m.x, m.y)
        self.assertNotIn(m.name.lower(), text.lower())
        self.assertIn("haven't explored", text)

    def test_a_remembered_room_shows_no_one_in_it(self):
        from hearthdelve.engine import rendering
        st = self._floor()
        gm = st.world
        m = gm.monsters[0]
        gm.explored[m.x, m.y] = True
        gm.visible[m.x, m.y] = False                       # seen once, not in sight now
        self.assertNotIn(m.name.lower(), rendering.describe(st, m.x, m.y).lower())
        gm.visible[m.x, m.y] = True                        # and once it's in sight
        self.assertIn(m.name.lower(), rendering.describe(st, m.x, m.y).lower())

    def test_a_hibernating_critter_is_not_there(self):
        from hearthdelve.engine import rendering
        from hearthdelve.entities.monster import Mob
        st = fresh_state(6)
        x, y = st.player.x + 3, st.player.y
        other = next(s for s in ("Spring", "Summer", "Fall", "Winter") if s != st.season)
        st.world.monsters.append(Mob("Dormouse", "r", (180, 160, 140), 3, 3, 1, "skittish",
                                     x, y, kind="wildlife", seasons=(other,)))
        self.assertNotIn("dormouse", rendering.describe(st, x, y).lower())


class TestRestingBesideTheBin(unittest.TestCase):
    """Rest checked its surroundings as if arriving: beside the shipping bin, the
    stairs or any villager, it stopped after its first half-minute."""

    def _rest_by_the_bin(self):
        from hearthdelve import screens
        st = fresh_state(6)
        bx, by = st.surface.bin
        st.player.x, st.player.y = next((bx + dx, by + dy) for dx, dy in
                                        ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1))
                                        if st.surface.walkable(bx + dx, by + dy))
        ui = screens.UI(st)
        play = ui.top
        play.handle(ui, "runprefix", ("runprefix",))
        play.handle(ui, "wait", ("wait",))
        return st, ui, play

    def test_a_rest_beside_the_bin_and_a_neighbour_carries_on(self):
        st, ui, play = self._rest_by_the_bin()
        npc = st.surface.npcs[0]
        npc.x, npc.y = st.player.x, st.player.y + 1        # someone already at your side…
        play.handle(ui, "runprefix", ("runprefix",))
        play.handle(ui, "wait", ("wait",))                 # …when you settle down
        self.assertIn(id(npc), play.rest_ack)
        for _ in range(6):
            play.tick(ui)
        self.assertGreater(play.rest_left, 0)

    def test_a_beast_that_wanders_up_still_wakes_you(self):
        from hearthdelve.entities.monster import Mob
        st, ui, play = self._rest_by_the_bin()
        play.tick(ui)
        self.assertGreater(play.rest_left, 0)
        st.world.monsters.append(Mob("Wolf", "w", (150, 150, 150), 10, 10, 2, "chase",
                                     st.player.x + 1, st.player.y + 1, hostile=True))
        play.tick(ui)
        self.assertEqual(play.rest_left, 0)


if __name__ == "__main__":
    unittest.main()
