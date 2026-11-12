"""Any potion can be tried at the apothecary; below its skill it may spoil."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


def _stocked(st):
    from hearthdelve.data import content
    for inputs, *_ in content.APOTHECARY_POTIONS:
        for it, q in inputs:
            st.player.inventory.add(it, q * 3)


def _potions(st):
    from hearthdelve.data import content
    from hearthdelve.game import crafting
    return [o for o in crafting.machine_load_options(st, content.MACHINES["apothecary"])
            if o.get("group") == "Potions"]


class TestRiskyBrewing(unittest.TestCase):
    """Eight potions did not appear at all below Herbalism 5 to 8."""

    def test_a_novice_is_offered_every_potion(self):
        from hearthdelve.data import content
        st = fresh_state(151)
        _stocked(st)
        self.assertEqual({o["output"] for o in _potions(st)},
                         {out for _i, out, *_ in content.APOTHECARY_POTIONS})

    def test_the_menu_shows_the_odds(self):
        st = fresh_state(151)
        _stocked(st)
        for o in _potions(st):
            with self.subTest(potion=o["output"].name):
                self.assertGreater(o["spoil"], 0)
                self.assertIn(f"{round(o['spoil'] * 100)}%", o["label"])

    def test_at_the_skill_there_is_no_risk(self):
        from hearthdelve.data import content
        from hearthdelve.game import skills
        st = fresh_state(151)
        _stocked(st)
        with mock.patch.object(skills, "skill_level", return_value=10):
            for o in _potions(st):
                self.assertEqual(o["spoil"], 0)
                self.assertEqual(o["label"], o["output"].name)
        self.assertEqual(content.brew_spoil_chance(5, 5), 0)
        self.assertEqual(content.brew_spoil_chance(5, 9), 0)

    def test_the_risk_falls_as_the_gap_closes(self):
        from hearthdelve.data import content
        odds = [content.brew_spoil_chance(8, lvl) for lvl in range(0, 9)]
        self.assertEqual(odds, sorted(odds, reverse=True))
        self.assertLess(odds[0], 1.0)                 # never a certainty: it can always be tried
        self.assertEqual(odds[-1], 0)

    def _brew(self, roll):
        from hearthdelve.data import content
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import crafting
        st = fresh_state(152)
        _stocked(st)
        opt = _potions(st)[0]
        m = Machine(kind="apothecary")
        with mock.patch("random.random", return_value=roll):
            crafting.load_machine_choice(st, m, content.MACHINES["apothecary"], opt)
        return st, m, opt

    def test_a_spoiled_batch_costs_the_herbs_and_teaches_a_little(self):
        from hearthdelve.game import skills
        st, m, opt = self._brew(0.0)
        self.assertIsNone(m.loaded_output)
        it, q = opt["inputs"][0]
        fresh = fresh_state(152)
        _stocked(fresh)
        self.assertEqual(st.player.inventory.count(it), fresh.player.inventory.count(it) - q)
        self.assertGreater(st.player.skills.get("Herbalism", 0), 0)

    def test_a_lucky_batch_brews_as_usual(self):
        st, m, opt = self._brew(0.999)
        self.assertIs(m.loaded_output, opt["output"])


if __name__ == "__main__":
    unittest.main()
