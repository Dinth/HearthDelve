"""Birth attributes: every stat modifies its system; absent attrs read 10."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestAttributeHooks(unittest.TestCase):
    def _flat(self, st, **over):
        from hearthdelve.game import attrs as A
        st.player.attrs = {k: 10 for k in A.ATTRS}
        st.player.attrs.update(over)

    def test_absent_attrs_are_neutral(self):
        from hearthdelve.game import attrs as A
        st = fresh_state(13)
        self.assertEqual(st.player.attrs, {})
        for k in A.ATTRS:
            self.assertEqual(A.get(st, k), 10)
            self.assertEqual(A.mod(st, k), 0)

    def test_strength_carries_more(self):
        from hearthdelve.game import encumbrance as enc
        st = fresh_state(13)
        base = enc.capacity(st)
        self._flat(st, St=16)
        self.assertEqual(enc.capacity(st), base + 6)

    def test_dexterity_dodges_and_aims(self):
        from hearthdelve.game import combat
        from hearthdelve.data import content
        from hearthdelve.entities import items
        st = fresh_state(13)
        base_dv = combat.player_dv(st)
        rstat = content.ranged_stat(content.make_ranged("Short Bow", "yew"))
        base_rth = combat._ranged_to_hit(st, rstat)
        self._flat(st, Dx=16)
        self.assertEqual(combat.player_dv(st), base_dv + 2)
        self.assertEqual(combat._ranged_to_hit(st, rstat), base_rth + 2)

    def test_learning_speeds_skills(self):
        from hearthdelve.game import skills
        st = fresh_state(13)
        self._flat(st, Le=15)                    # +10% xp
        skills.gain(st, "Farming", 10)
        self.assertEqual(st.player.skills["Farming"], 11)

    def test_charisma_and_appearance_warm_the_village(self):
        from hearthdelve.game import village
        st = fresh_state(13)
        npc = st.surface.npcs[0]
        self._flat(st, Ch=15)                    # +20% talk warmth
        f0 = npc.friendship
        village.talk(st, npc)
        self.assertEqual(npc.friendship - f0, 12)          # 10 * 1.20

    def test_willpower_resists_status(self):
        import random
        from hearthdelve.game import combat, delve
        from hearthdelve.data import content
        st = fresh_state(13)
        delve.enter(st, "mine")
        spider = content.make_mob(
            next(m for m in content.MONSTERS if m.name == "Cave Spider"),
            st.player.x + 1, st.player.y, 4, random.Random(1))
        spider.to_hit = 40
        st.world.monsters = [spider]

        def rate():
            hits = 0
            for _ in range(500):
                st.player.status.clear()
                combat._attack_player(st, spider)
                if "poison" in st.player.status:
                    hits += 1
            return hits

        self._flat(st, Wi=10)
        random.seed(0)
        base = rate()
        self._flat(st, Wi=18)                    # x0.76 infliction odds
        random.seed(0)
        strong = rate()
        self.assertLess(strong, base)

    def test_perception_sees_farther(self):
        from hearthdelve.game import delve
        import numpy as np
        st = fresh_state(13)
        delve.enter(st, "grotto")
        self._flat(st, Pe=3)                     # radius shrinks toward 4
        delve.update_fov(st)
        dim = int(np.count_nonzero(st.world.visible))
        self._flat(st, Pe=18)                    # radius grows past the torch
        delve.update_fov(st)
        keen = int(np.count_nonzero(st.world.visible))
        self.assertGreater(keen, dim)

    def test_attrs_persist_and_grandfather(self):
        import json
        import os
        import tempfile
        from hearthdelve.engine import save
        st = fresh_state(13)
        self._flat(st, St=14, Pe=8)
        path = os.path.join(tempfile.gettempdir(), "hd_attrs_test.json")
        try:
            save.save(st, path)
            st2 = save.load(path)
            self.assertEqual(st2.player.attrs["St"], 14)
            self.assertEqual(st2.player.attrs["Pe"], 8)
            with open(path) as f:
                raw = json.load(f)
            raw["player"].pop("attrs", None)
            with open(path, "w") as f:
                json.dump(raw, f)
            self.assertEqual(save.load(path).player.attrs, {})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
