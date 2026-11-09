"""The dawn ledger: what the bin sold overnight, and what's ready, as you wake."""
from __future__ import annotations

import os
import tempfile
import unittest

import tcod.console
import tcod.event

from tests.common import fresh_state


def _quiet_farm(st):
    """Nothing ripe, ready or waiting: a farm with no news of its own."""
    st.surface.crops.clear()
    st.surface.trees.clear()
    st.surface.animals.clear()
    for m in st.surface.machines.values():
        m.loaded_output = None
    return st


def _text(con):
    return "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(con.height))


class TestTheBinKeepsItsAccounts(unittest.TestCase):
    """The night's sale was one total in the log, and the itemised bin was
    thrown away the moment it was paid."""

    def test_the_sale_is_recorded_line_by_line(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(2)
        st.ship_bin.add(items.PARSNIP, 3, quality=1)
        st.ship_bin.add(items.WOOD, 10)
        each = crafting.bin_value(st, items.PARSNIP, 1)
        gold = st.player.gold
        crafting.sell_shipment(st)
        lines = {it.name: (qty, ql, g) for it, qty, ql, g in st.shipped["lines"]}
        self.assertEqual(lines["Parsnip"], (3, 1, each * 3))
        self.assertEqual(st.player.gold - gold, sum(g for *_r, g in st.shipped["lines"]))

    def test_it_survives_a_save_and_an_old_save_has_none(self):
        import json
        from hearthdelve.engine import save
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(2)
        st.ship_bin.add(items.PARSNIP, 2)
        crafting.sell_shipment(st)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            back = save.load(path)
            self.assertEqual([(it.name, q, ql, g) for it, q, ql, g in back.shipped["lines"]],
                             [(it.name, q, ql, g) for it, q, ql, g in st.shipped["lines"]])
            with open(path) as fh:
                data = json.load(fh)
            del data["shipped"]                           # a save from before the ledger
            with open(path, "w") as fh:
                json.dump(data, fh)
            self.assertEqual(save.load(path).shipped, {})


class TestTheLedgerOpensAsYouWake(unittest.TestCase):
    def _woken(self, ship=True):
        from hearthdelve import screens
        from hearthdelve.entities import items
        from hearthdelve.game import farming
        st = _quiet_farm(fresh_state(2))
        if ship:
            st.ship_bin.add(items.PARSNIP, 3)
        farming.sleep(st)
        _quiet_farm(st)
        ui = screens.UI(st)
        return st, ui

    def test_after_the_dawn_card_it_opens_with_the_night_s_sale(self):
        from hearthdelve import screens
        st, ui = self._woken()
        ui.top.tick(ui)
        self.assertIs(ui.top, ui.play, "it waited for the dawn card")
        st.fx.clear()                                     # the card has played
        ui.top.tick(ui)
        self.assertIsInstance(ui.top, screens.LedgerScreen)
        con = tcod.console.Console(80, 50, order="F")
        ui.top.render(ui, con)
        text = _text(con)
        self.assertIn("3 Parsnip", text)
        self.assertIn("Total", text)

    def test_a_quiet_morning_has_no_ledger(self):
        st, ui = self._woken(ship=False)
        st.fx.clear()
        ui.top.tick(ui)
        self.assertIs(ui.top, ui.play)
        self.assertFalse(st.ledger_due)

    def test_any_fresh_key_closes_it_but_a_held_one_doesn_t(self):
        st, ui = self._woken()
        st.fx.clear()
        ui.top.tick(ui)
        # (letters built from their code, as test_keys does: the named letter
        # members differ between tcod builds)
        held = tcod.event.KeyDown(sym=tcod.event.KeySym(ord("s")), scancode=tcod.event.Scancode(0),
                                  mod=tcod.event.Modifier.NONE, repeat=True)
        ui.top.on_raw(ui, held)
        self.assertIsNot(ui.top, ui.play)
        fresh = tcod.event.KeyDown(sym=tcod.event.KeySym.SPACE, scancode=tcod.event.Scancode(0),
                                   mod=tcod.event.Modifier.NONE)
        ui.top.on_raw(ui, fresh)
        self.assertIs(ui.top, ui.play)


class TestTheFarmReport(unittest.TestCase):
    def test_a_ready_machine_and_a_ripe_crop_are_news(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import farming
        from hearthdelve.world.crops import CropPlot
        st = _quiet_farm(fresh_state(2))
        p = st.player
        st.surface.machines[(p.x + 3, p.y)] = Machine(kind="keg", loaded_output=items.WINE, ready_at=0)
        crop = content.CROPS[0]
        st.surface.crops[(p.x + 4, p.y)] = CropPlot(crop=crop, days_grown=crop.days_to_mature)
        rep = farming.farm_report(st)
        self.assertIn(("Keg", "Wine"), rep["ready"])
        self.assertEqual(rep["ripe"], 1)
        self.assertTrue(farming.ledger_has_news(st))

    def test_the_villages_own_fields_aren_t_yours(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming
        from hearthdelve.world.crops import CropPlot
        st = _quiet_farm(fresh_state(2))
        crop = content.CROPS[0]
        for pos in list(map(tuple, st.surface.village_fields))[:5]:
            st.surface.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature)
        self.assertEqual(farming.farm_report(st)["ripe"], 0)


if __name__ == "__main__":
    unittest.main()
