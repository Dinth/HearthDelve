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


class TestEssenceAlchemy(unittest.TestCase):
    def test_essence_draughts_exist_and_clear_margin(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        made = {out: (inp, need) for inp, out, _oq, need, _m in content.APOTHECARY_POTIONS}
        for draught in (items.VENOM_DRAUGHT, items.PHANTOM_DRAUGHT):
            self.assertIn(draught, made)
            inp, _need = made[draught]
            iv = sum(it.value * q for it, q in inp)
            self.assertGreaterEqual(draught.value, iv * 1.25 - 0.5)
        # they're built from monster spoils, not just herbs
        venom_inputs = {it for it, _q in made[items.VENOM_DRAUGHT][0]}
        self.assertIn(items.SPORE_SAC, venom_inputs)

    def test_venom_draught_makes_blows_poison(self):
        from hearthdelve.game import combat, skills
        st = fresh_state(92)
        self.assertEqual(combat.weapon_inflict(st), "")
        skills.apply_buff(st, "venomed", minutes=600)
        self.assertEqual(combat.weapon_inflict(st), "poison")

    def test_phantom_draught_raises_dodge(self):
        from hearthdelve.game import combat, skills
        st = fresh_state(93)
        base = combat.player_dv(st)
        skills.apply_buff(st, "phantom", minutes=600)
        self.assertGreater(combat.player_dv(st), base)

    def test_ember_core_is_a_fuel(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        self.assertIn(items.EMBER_CORE, content.FUELS)
        self.assertGreaterEqual(content.FUELS[items.EMBER_CORE], content.FUELS[items.COKE])


class TestBossTrophyRelics(unittest.TestCase):
    def test_every_boss_trophy_mounts_into_a_neck_relic(self):
        from hearthdelve.data import content
        for trophy, relic in content.TROPHY_RELIC.items():
            self.assertEqual(content.jewel_slot(relic), "neck")
            self.assertTrue(content.JEWEL_EFFECT.get(relic), f"{relic.name} has no effect")
        self.assertEqual(len(content.TROPHY_RELIC), 5)      # one per boss

    def test_jeweller_mounts_a_trophy_and_it_works_worn(self):
        from hearthdelve.data import content
        from hearthdelve.game import crafting, jewelry
        from hearthdelve.entities import items
        st = fresh_state(94)
        inv = st.player.inventory
        inv.add(items.ABYSSAL_PEARL, 1)
        inv.add(items.SILVER_BAR, 1)
        opt = next(o for o in crafting._jeweller_options(st) if o.get("kind") == "relic")
        crafting.jeweller_choice(st, opt)
        pendant = content.TROPHY_RELIC[items.ABYSSAL_PEARL]
        self.assertEqual(inv.count(pendant), 1)
        self.assertEqual(inv.count(items.ABYSSAL_PEARL), 0)
        st.player.equipment["neck"] = pendant
        self.assertGreater(jewelry.combat_bonus(st)["dv"], 0)

    def test_relic_round_trips_through_save(self):
        import os
        import tempfile
        from hearthdelve.data import content
        from hearthdelve.engine import save
        from hearthdelve.entities import items
        relic = content.TROPHY_RELIC[items.MOLTEN_HEART]
        st = fresh_state(95)
        st.player.equipment["neck"] = relic
        path = os.path.join(tempfile.gettempdir(), "hd_relic_rt.json")
        try:
            save.save(st, path)
            self.assertIs(save.load(path).player.equipment["neck"], relic)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
