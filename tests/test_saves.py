"""Save-format safety: full round-trips, and old saves grandfathering cleanly.

The save contract: records are positional and append-only; new fields load with
defaults when absent. Breaking this bricks players' farms — these tests are the
tripwire.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from tests.common import fresh_state


class TestSaveRoundTrip(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.gettempdir(), "hd_test_save.json")

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _mutated_state(self):
        from hearthdelve.entities import items
        from hearthdelve.entities.animal import Animal
        from hearthdelve.game import husbandry
        from hearthdelve.world.crops import CropPlot
        from hearthdelve.data import content
        st = fresh_state(3)
        p = st.player
        p.gold = 777
        p.status = {"poison": 3, "sick": 5}
        st.donated = {"Ruby", "Chamomile"}
        st.seen_events = {"Hollis:4"}
        st.known_recipes.add("Antidote")
        st.surface.soil[(50, 50)] = 3
        crop = content.CROPS[0]
        st.surface.crops[(51, 50)] = CropPlot(crop=crop, days_grown=1, thirst=2,
                                              fertilized=True)
        spec = husbandry.SPECIES["chicken"]
        st.surface.animals.append(Animal(
            kind="chicken", name="RoundTrip", glyph=spec.glyph, color=spec.color,
            x=52, y=50, home=(52, 50), age_days=9, happiness=64, sick=2))
        return st

    def test_everything_round_trips(self):
        from hearthdelve.engine import save
        st = self._mutated_state()
        save.save(st, self.path)
        st2 = save.load(self.path)
        self.assertEqual(st2.player.gold, 777)
        self.assertEqual(st2.player.status, {"poison": 3, "sick": 5})
        self.assertEqual(st2.donated, {"Ruby", "Chamomile"})
        self.assertEqual(st2.seen_events, {"Hollis:4"})
        self.assertIn("Antidote", st2.known_recipes)
        self.assertEqual(st2.surface.soil.get((50, 50)), 3)
        plot = st2.surface.crops.get((51, 50))
        self.assertIsNotNone(plot)
        self.assertEqual((plot.thirst, plot.fertilized), (2, True))
        beast = next(a for a in st2.surface.animals if a.name == "RoundTrip")
        self.assertEqual((beast.sick, beast.happiness, beast.age_days), (2, 64, 9))

    def test_old_save_grandfathers(self):
        """Strip every recently-added key/field; the save must still load with
        sensible defaults — never a crash, never a wiped farm."""
        from hearthdelve.engine import save
        st = self._mutated_state()
        save.save(st, self.path)
        with open(self.path) as f:
            raw = json.load(f)
        for key in ("soil", "donated", "seen_events", "projects"):
            raw.pop(key, None)
        raw["animals"] = [rec[:9] for rec in raw.get("animals", [])]
        raw["wildlife"] = [rec[:18] for rec in raw.get("wildlife", [])]
        raw["crops"] = {k: rec[:4] for k, rec in raw.get("crops", {}).items()}
        raw.get("player", {}).pop("status", None)
        with open(self.path, "w") as f:
            json.dump(raw, f)

        st3 = save.load(self.path)
        self.assertEqual(st3.surface.soil, {})
        self.assertEqual(st3.donated, set())
        self.assertEqual(st3.seen_events, set())
        self.assertEqual(st3.player.status, {})
        self.assertTrue(all(p["state"] == "open" for p in st3.projects))
        beast = next(a for a in st3.surface.animals if a.name == "RoundTrip")
        self.assertEqual(beast.sick, 0)
        plot = st3.surface.crops.get((51, 50))
        self.assertIsNotNone(plot)
        self.assertEqual((plot.thirst, plot.fertilized), (0, False))


class TestBackupRecovery(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.gettempdir(), "hd_test_recover.json")

    def tearDown(self):
        for suffix in ("", ".bak", ".broken", ".tmp"):
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass

    def test_rolling_backup_holds_the_previous_save(self):
        from hearthdelve.engine import save
        st = fresh_state(5)
        st.player.gold = 111
        save.save(st, self.path)                 # first write: no backup yet
        self.assertFalse(os.path.isfile(self.path + ".bak"))
        st.player.gold = 222
        save.save(st, self.path)                 # second write: .bak = the 111 save
        self.assertEqual(save.load(self.path).player.gold, 222)
        self.assertEqual(save.load(self.path + ".bak").player.gold, 111)

    def test_corrupt_main_restores_the_backup(self):
        from hearthdelve.engine import save
        st = fresh_state(5)
        st.player.gold = 111
        save.save(st, self.path)
        st.player.gold = 222
        save.save(st, self.path)
        with open(self.path, "w") as f:
            f.write("{ this is not json")        # the main save corrupts
        st2, restored = save.load_or_backup(self.path)
        self.assertTrue(restored)
        self.assertEqual(st2.player.gold, 111)   # yesterday morning survives
        self.assertTrue(os.path.isfile(self.path + ".broken"))
        # and the promoted main is a normal, loadable save again
        self.assertEqual(save.load(self.path).player.gold, 111)

    def test_healthy_save_never_touches_the_backup(self):
        from hearthdelve.engine import save
        st = fresh_state(5)
        st.player.gold = 333
        save.save(st, self.path)
        st2, restored = save.load_or_backup(self.path)
        self.assertFalse(restored)
        self.assertEqual(st2.player.gold, 333)

    def test_corrupt_with_no_backup_still_raises(self):
        from hearthdelve.engine import save
        with open(self.path, "w") as f:
            f.write("not a save at all")
        with self.assertRaises(Exception):
            save.load_or_backup(self.path)


if __name__ == "__main__":
    unittest.main()
