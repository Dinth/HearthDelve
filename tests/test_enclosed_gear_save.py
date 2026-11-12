"""Gear in a letter or on a machine persists by what it is, not what it's called."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from tests.common import fresh_state


def _piece():
    from hearthdelve.data import content
    return content.make_gear("Dagger", "steel", "fine", "", ("ruby",))


def _stocked():
    from hearthdelve.entities import items
    from hearthdelve.entities.machine import Machine
    st = fresh_state(23)
    gear = _piece()
    m = Machine(kind="anvil")
    m.loaded_output, m.ready_at = gear, 10 ** 9
    st.surface.machines[(5, 5)] = m
    st.mail.append({"sender": "Bron", "body": "As promised.",
                    "items": [(gear, 1, 0), (items.BREAD, 2, 1)], "until": 99})
    return st, gear


def _save_edit_load(st, edit=None):
    from hearthdelve.engine import save
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.json")
        save.save(st, path)
        with open(path) as fh:
            raw = json.load(fh)
        if edit:
            edit(raw)
            with open(path, "w") as fh:
                json.dump(raw, fh)
        return save.load(path), raw


class TestEnclosedGearIsStructured(unittest.TestCase):
    """Everything else that holds gear saved its structure; a letter's
    enclosure and a machine's finished piece saved only the display name, so
    they alone would be lost to any change in how gear names are composed."""

    def test_both_are_stored_as_structure(self):
        _back, raw = _save_edit_load(*_stocked()[:1])
        self.assertEqual(raw["machines"]["5,5"][1]["g"], "Dagger")
        self.assertEqual(raw["mail"][-1]["items"][0][0]["x"], ["ruby"])
        self.assertEqual(raw["mail"][-1]["items"][1][0], "Bread")     # plain goods by name

    def test_they_come_back_even_if_the_name_no_longer_resolves(self):
        from hearthdelve.entities import items
        st, gear = _stocked()

        def rename(raw):                                  # as if names were composed differently
            raw["machines"]["5,5"][1]["n"] = "Some Other Wording"
            raw["mail"][-1]["items"][0][0]["n"] = "Some Other Wording"
        back, _raw = _save_edit_load(st, rename)
        self.assertIs(back.surface.machines[(5, 5)].loaded_output, gear)
        letter = back.mail[-1]
        self.assertEqual([(it, q, ql) for it, q, ql in letter["items"]],
                         [(gear, 1, 0), (items.BREAD, 2, 1)])
        self.assertEqual((letter["sender"], letter["until"]), ("Bron", 99))

    def test_the_letter_can_be_collected_after_a_load(self):
        from hearthdelve.game import commands
        st, gear = _stocked()
        back, _raw = _save_edit_load(st)
        before = back.player.inventory.count(gear)
        commands.collect_letter(back, back.mail[-1])
        self.assertEqual(back.player.inventory.count(gear), before + 1)

    def test_and_survives_a_second_save(self):
        st, gear = _stocked()
        back, _raw = _save_edit_load(st)
        again, _raw = _save_edit_load(back)
        self.assertIs(again.mail[-1]["items"][0][0], gear)
        self.assertIs(again.surface.machines[(5, 5)].loaded_output, gear)


class TestOlderSavesStillLoad(unittest.TestCase):
    def test_names_from_before_are_read(self):
        from hearthdelve.entities import items
        st, gear = _stocked()

        def as_before(raw):
            raw["machines"]["5,5"][1] = gear.name
            raw["mail"][-1]["items"] = [[gear.name, 1, 0], ["Bread", 2, 1], ["No Such Thing", 1, 0]]
        back, _raw = _save_edit_load(st, as_before)
        self.assertIs(back.surface.machines[(5, 5)].loaded_output, gear)
        self.assertEqual([it for it, _q, _ql in back.mail[-1]["items"]], [gear, items.BREAD])


if __name__ == "__main__":
    unittest.main()
