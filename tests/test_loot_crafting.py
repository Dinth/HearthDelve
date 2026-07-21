"""Combat loot feeds the bench: scales forge into armour (and later phases)."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


class TestScaleArmour(unittest.TestCase):
    def test_scales_forge_armour_rivalling_metal(self):
        from hearthdelve.data import content
        # each scale material makes a body piece whose protection sits in the
        # metal ladder (iron 5 … adamantium 8)
        for mat, min_pv in (("lurkerscale", 5), ("drakescale", 6), ("wyrmscale", 7)):
            it = content.make_gear("Armour", mat)
            _dv, pv = content.ARMOR_STATS[it]
            self.assertGreaterEqual(pv, min_pv, f"{mat} armour too weak")
            self.assertGreater(it.value, 0)
        # drakescale is the light, evasive one (a DV bonus, unlike heavy metal)
        d_dv, _ = content.ARMOR_STATS[content.make_gear("Armour", "drakescale")]
        self.assertGreater(d_dv, 0)

    def test_anvil_forges_scales_into_armour_only(self):
        from hearthdelve.data import content
        from hearthdelve.game import crafting
        from hearthdelve.entities import items
        st = fresh_state(90)
        st.player.inventory.add(items.WYRM_SCALE, 5)
        opts = crafting.machine_load_options(st, content.MACHINES["anvil"])
        made = [o["output"].name for o in opts if "Wyrmscale" in o["output"].name]
        self.assertIn("Wyrmscale Armour", made)
        self.assertTrue(made)
        # no scale WEAPONS — you don't knap a sword from a scale
        for w in ("Sword", "Axe", "Mace", "Hammer", "Dagger", "Halberd", "Spear"):
            self.assertFalse(any(w in n for n in made), f"scale {w} should not be forgeable")

    def test_scale_gear_round_trips(self):
        from hearthdelve.data import content
        from hearthdelve.engine import save
        st = fresh_state(91)
        piece = content.make_gear("Armour", "drakescale")
        st.player.equipment["body"] = piece
        path = os.path.join(tempfile.gettempdir(), "hd_scalegear.json")
        try:
            save.save(st, path)
            self.assertIs(save.load(path).player.equipment["body"], piece)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
