"""World events: seeded determinism, per-event effects, cleanup, persistence."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestEventRoll(unittest.TestCase):
    def _fired_days(self, st, days=60):
        from hearthdelve.game import events
        fired = []
        for d in range(1, days + 1):
            st.day = d
            events.new_day(st)
            if st.event:
                fired.append((d, st.event["id"]))
        return fired

    def test_deterministic_and_organically_paced(self):
        a = self._fired_days(fresh_state(9))
        b = self._fired_days(fresh_state(9))
        self.assertEqual(a, b, "event schedule must be seeded, not wall-clock random")
        self.assertGreaterEqual(len(a), 1, "no events in 60 days")
        self.assertLessEqual(len(a), 20, "events too frequent")
        days = [d for d, _ in a]
        gaps = [j - i for i, j in zip(days, days[1:])]
        self.assertTrue(all(g >= 3 for g in gaps), f"cooldown violated: {gaps}")

    def test_cooldown_blocks_the_roll(self):
        from hearthdelve.game import events
        st = fresh_state(9)
        st.day = 10
        st.stats["last_event_day"] = 9
        events.new_day(st)
        self.assertEqual(st.event, {})


class TestEventEffects(unittest.TestCase):
    def test_shoal_and_caravan_and_fete_multipliers(self):
        import random
        from hearthdelve.game import events, crafting, village
        from hearthdelve.entities import items
        st = fresh_state(9)
        base = crafting.bin_value(st, items.WINE, 0)
        self.assertEqual(events.fishing_bonus(st), 0.0)
        st.event = {"id": "shoal"}
        self.assertEqual(events.fishing_bonus(st), 0.25)
        st.event = {"id": "caravan"}
        self.assertEqual(crafting.bin_value(st, items.WINE, 0), round(base * 1.25))
        # fete: first talk of the day gains double friendship
        npc = next(n for n in st.surface.npcs if n.role == "villager" or True)
        st.event = {}
        f0 = npc.friendship
        village.talk(st, npc)
        plain_gain = npc.friendship - f0
        npc2 = next(n for n in st.surface.npcs if n is not npc)
        st.event = {"id": "fete"}
        f0 = npc2.friendship
        village.talk(st, npc2)
        self.assertEqual(npc2.friendship - f0, plain_gain * 2)

    def test_starfall_stamps_minable_crags(self):
        import random
        from hearthdelve.game import events
        from hearthdelve.world import tile
        st = fresh_state(9)
        st.event = {"id": "starfall"}
        before = int((st.surface.tiles == tile.ORE_VEIN).sum()
                     + (st.surface.tiles == tile.GEM_VEIN).sum())
        events._apply_starfall(st, random.Random(5))
        after = int((st.surface.tiles == tile.ORE_VEIN).sum()
                    + (st.surface.tiles == tile.GEM_VEIN).sum())
        self.assertGreaterEqual(st.event["fell"], 5)
        self.assertEqual(after - before, st.event["fell"])

    def test_wolves_arrive_and_leave(self):
        import random
        from hearthdelve.game import events
        st = fresh_state(9)
        st.event = {"id": "wolves"}
        events._apply_wolves(st, random.Random(5))
        packs = [m for m in st.surface.monsters if m.name == "Ash Wolf"]
        self.assertGreaterEqual(len(packs), 4)
        self.assertTrue(all(m.inflicts == "bleed" for m in packs))
        # next dawn (cooldown active, so no new event): the pack melts away
        st.day += 1
        st.stats["last_event_day"] = st.day
        events.new_day(st)
        self.assertFalse(any(m.name == "Ash Wolf" for m in st.surface.monsters))

    def test_bloom_sprouts_the_meadows(self):
        import random
        import numpy as np
        from hearthdelve.game import events
        from hearthdelve.world import tile
        st = fresh_state(9)
        herb_ids = [tid for tid, t in enumerate(tile.TILES) if t.kind == "herb"]
        before = int(np.isin(st.surface.tiles, herb_ids).sum())
        events._apply_bloom(st, random.Random(5))
        after = int(np.isin(st.surface.tiles, herb_ids).sum())
        self.assertGreater(after, before)


class TestEventPersistence(unittest.TestCase):
    def test_round_trip_and_old_save(self):
        import json
        import os
        import tempfile
        from hearthdelve.engine import save
        st = fresh_state(9)
        st.event = {"id": "caravan", "village": "Mossford"}
        path = os.path.join(tempfile.gettempdir(), "hd_event_test.json")
        try:
            save.save(st, path)
            st2 = save.load(path)
            self.assertEqual(st2.event, {"id": "caravan", "village": "Mossford"})
            with open(path) as f:
                raw = json.load(f)
            raw.pop("event", None)
            with open(path, "w") as f:
                json.dump(raw, f)
            st3 = save.load(path)
            self.assertEqual(st3.event, {})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
