"""Nobody asks a favour of a hybrid's goods before the hybrid has been bred."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from tests.common import fresh_state

_ROLES = ("priest", "trader", "woodcarver", "bard", "innkeeper", "villager", "shopkeeper")


def _hybrid_goods(st, role):
    from hearthdelve.data import content
    from hearthdelve.game import requests
    produce = {c.produce: c.name for c in content.HYBRIDS}
    return {produce[it.source] for it in requests._request_pool(st, role)
            if getattr(it, "source", None) in produce}


class TestHybridGoodsWaitForTheHybrid(unittest.TestCase):
    """Jams, wines and pickles are generated for every fruit and vegetable,
    hybrids included, and the favour pools took them all: on day one a priest
    could ask for Frostberry Jam, which no one in the Vales could make."""

    def test_a_fresh_game_asks_for_none(self):
        st = fresh_state(23)
        for role in _ROLES:
            with self.subTest(role=role):
                self.assertEqual(_hybrid_goods(st, role), set())

    def test_breeding_one_opens_only_its_own(self):
        st = fresh_state(23)
        st.hybrids_bred.add("Frostberry")
        self.assertEqual(_hybrid_goods(st, "trader"), {"Frostberry"})

    def test_saving_a_crossed_seed_records_the_hybrid(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming

        class _Plot:
            cross = "Frostberry"
            crop = content.CROPS[0]
        st = fresh_state(23)
        farming._save_seed(st, _Plot())
        self.assertEqual(st.hybrids_bred, {"Frostberry"})


class TestTheRecordIsSaved(unittest.TestCase):
    def _round_trip(self, st, strip=False):
        from hearthdelve.engine import save
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            if strip:                                    # a save from before the field
                with open(path) as fh:
                    data = json.load(fh)
                del data["hybrids_bred"]
                with open(path, "w") as fh:
                    json.dump(data, fh)
            return save.load(path)

    def test_it_round_trips(self):
        st = fresh_state(23)
        st.hybrids_bred.add("Pomato")
        self.assertEqual(self._round_trip(st).hybrids_bred, {"Pomato"})

    def test_an_old_save_that_bred_hybrids_keeps_them_all(self):
        from hearthdelve.data import content
        st = fresh_state(23)
        st.bump("hybrids_found")
        self.assertEqual(self._round_trip(st, strip=True).hybrids_bred,
                         {c.name for c in content.HYBRIDS})

    def test_an_old_save_that_bred_none_starts_empty(self):
        self.assertEqual(self._round_trip(fresh_state(23), strip=True).hybrids_bred, set())


if __name__ == "__main__":
    unittest.main()
