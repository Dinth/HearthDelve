"""Gear persists by structured identity, not by re-parsing its display name."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from tests.common import fresh_state


def _roundtrip(st):
    from hearthdelve.engine import save
    path = os.path.join(tempfile.gettempdir(), "hd_gearsave_test.json")
    save.save(st, path)
    with open(path) as f:
        raw = json.load(f)
    st2 = save.load(path)
    os.remove(path)
    return st2, raw


class TestStructuredGearSave(unittest.TestCase):
    def test_gear_and_jewellery_round_trip_to_the_same_item(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        st = fresh_state(21)
        p = st.player
        gs = content.make_gear("Greatsword", "mithril", "masterwork", "slaying", ("ruby",))
        helm = content.make_gear("Helm", "steel")
        ring = content.make_jewel("Ring", "gold", "topaz")
        amu = content.make_jewel("Amulet", "silver", "sapphire")
        p.weapon = gs
        p.equipment["head"] = helm
        p.equipment["ring1"] = ring
        p.equipment["neck"] = amu
        p.inventory.add(items.SWORD, 1)                       # a canonical piece
        p.inventory.add(content.make_gear("Dagger", "adamantium", "fine"), 1)

        st2, _ = _roundtrip(st)
        p2 = st2.player
        self.assertIs(p2.weapon, gs)                          # same memoized instance
        self.assertIs(p2.equipment["head"], helm)
        self.assertIs(p2.equipment["ring1"], ring)
        self.assertIs(p2.equipment["neck"], amu)
        inv = {it for it, _, _ in p2.inventory.slots}
        self.assertIn(items.SWORD, inv)
        self.assertTrue(any("Adamantium Dagger" in it.name for it in inv))

    def test_gear_is_stored_structurally_not_by_name(self):
        from hearthdelve.data import content
        st = fresh_state(22)
        st.player.weapon = content.make_gear("Warhammer", "steel", "", "warding")
        _, raw = _roundtrip(st)
        wep = raw["player"]["weapon"]
        self.assertIsInstance(wep, dict)                      # structured, not a bare name
        self.assertEqual(wep["g"], "Warhammer")
        self.assertEqual(wep["s"], "warding")

    def test_old_bare_name_saves_still_load(self):
        """Grandfather: a save written before this change stored gear as a bare
        name. That path must still resolve (via the name-parse resolver)."""
        from hearthdelve.engine import save
        from hearthdelve.data import content
        st = fresh_state(23)
        gs = content.make_gear("Greatsword", "iron", "fine", "")
        st.player.weapon = gs
        path = os.path.join(tempfile.gettempdir(), "hd_gearsave_old.json")
        try:
            save.save(st, path)
            with open(path) as f:
                raw = json.load(f)
            raw["player"]["weapon"] = gs.name                 # downgrade to the old form
            with open(path, "w") as f:
                json.dump(raw, f)
            self.assertIs(save.load(path).player.weapon, gs)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


class TestAnUnknownPieceDoesNotBrickTheSave(unittest.TestCase):
    """make_gear raised KeyError on a material, affix or base this build didn't
    know, so one renamed affix made every save holding such a piece unloadable
    — the rolling .bak too, since it holds the same piece."""

    def test_the_save_loads_without_the_unknown_piece_and_says_so(self):
        from hearthdelve.data import content
        from hearthdelve.engine import save
        from hearthdelve.entities import items
        st = fresh_state(21)
        p = st.player
        odd = content.make_gear("Sword", "steel")
        fine = content.make_gear("Helm", "iron")
        p.inventory.add(odd, 1)
        p.inventory.add(fine, 1)
        p.inventory.add(items.BREAD, 3)
        save.save(st)
        with open(save.default_path()) as f:
            raw = json.load(f)
        for rec in raw["player"]["inventory"]:
            if isinstance(rec[0], dict) and rec[0].get("g") == "Sword":
                rec[0]["m"] = "unobtainium"                 # a metal since cut
                rec[0]["n"] = "Unobtainium Sword"
        if isinstance(raw["player"]["weapon"], dict):
            raw["player"]["weapon"]["p"] = "gone_affix"     # an affix since renamed
            raw["player"]["weapon"]["n"] = "Vanished Blade"
        with open(save.default_path(), "w") as f:
            json.dump(raw, f)
        again = save.load()
        self.assertEqual(again.player.inventory.count(fine), 1)
        self.assertEqual(again.player.inventory.count(items.BREAD), 3)
        self.assertFalse(any(it.name == "Unobtainium Sword" for it, _q, _ql in again.player.inventory.slots))
        lost = [t for t, _c in again.log.messages if "couldn't be recognised" in t]
        self.assertTrue(lost and "Unobtainium Sword" in lost[0])


if __name__ == "__main__":
    unittest.main()
