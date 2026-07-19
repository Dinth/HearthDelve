"""Combat & status-effect logic: DoTs, cures, elites, rosters."""
from __future__ import annotations

import random
import unittest

from tests.common import fresh_state


class TestStatusEffects(unittest.TestCase):
    def test_apply_tick_expire(self):
        from hearthdelve.game import combat
        st = fresh_state(2)
        p = st.player
        p.max_hp = 50
        p.hp = 50
        combat.apply_status(st, "poison")
        self.assertEqual(p.status["poison"], combat.STATUS["poison"]["turns"])
        for _ in range(3):
            combat.tick_player_status(st)
        self.assertEqual(p.hp, 44)                      # flat floor: 2/turn at 50 max HP
        for _ in range(10):
            combat.tick_player_status(st)
        self.assertNotIn("poison", p.status)            # runs out

    def test_dot_scales_with_max_hp(self):
        from hearthdelve.game import combat
        st = fresh_state(2)
        p = st.player
        p.max_hp = 162
        p.hp = 162
        p.status = {"poison": 5}
        combat.tick_player_status(st)
        self.assertEqual(162 - p.hp, 3)                 # pct wins over the flat floor

    def test_cure_tiers(self):
        from hearthdelve.game import commands
        st = fresh_state(2)
        p = st.player
        # salve ("all") clears wounds but never sickness
        p.status = {"poison": 3, "bleed": 2, "sick": 5}
        cured = commands._cure_status(st, "all")
        self.assertEqual(sorted(cured), ["bleed", "poison"])
        self.assertEqual(p.status, {"sick": 5})
        # targeted cure
        p.status = {"poison": 3, "bleed": 2}
        self.assertEqual(commands._cure_status(st, "poison"), ["poison"])
        self.assertEqual(p.status, {"bleed": 2})
        # panacea/elixir ("everything") clears the lot
        p.status = {"burn": 2, "sick": 4}
        self.assertEqual(sorted(commands._cure_status(st, "everything")), ["burn", "sick"])
        self.assertEqual(p.status, {})

    def test_remedy_items_declare_cures(self):
        from hearthdelve.entities import items
        self.assertEqual(items.ANTIDOTE.cures, "poison")
        self.assertEqual(items.POULTICE.cures, "bleed")
        self.assertEqual(items.BURN_BALM.cures, "burn")
        self.assertEqual(items.CHARCOAL_TINCTURE.cures, "sick")
        self.assertEqual(items.SALVE.cures, "all")
        self.assertEqual(items.PANACEA.cures, "everything")


class TestElites(unittest.TestCase):
    def test_deterministic_and_gated_by_depth(self):
        from hearthdelve.data import content
        boar = next(m for m in content.MONSTERS if m.name == "Boar")
        a = content.make_mob(boar, 0, 0, 8, random.Random(123))
        b = content.make_mob(boar, 0, 0, 8, random.Random(123))
        self.assertEqual((a.name, a.hp, a.elite), (b.name, b.hp, b.elite))
        # never on floor 1; a healthy share deep down
        self.assertFalse(any(content.make_mob(boar, 0, 0, 1, random.Random(s)).elite
                             for s in range(150)))
        deep = sum(1 for s in range(400)
                   if content.make_mob(boar, 0, 0, 8, random.Random(s)).elite)
        self.assertTrue(0.08 < deep / 400 < 0.35, f"elite rate off: {deep / 400}")

    def test_elite_drops_resolve_by_base_name(self):
        from hearthdelve.data import content
        elite = next(content.make_mob(next(m for m in content.MONSTERS if m.name == "Boar"),
                                      0, 0, 8, random.Random(s))
                     for s in range(400)
                     if content.make_mob(next(m for m in content.MONSTERS if m.name == "Boar"),
                                         0, 0, 8, random.Random(s)).elite)
        base = elite.name.split(" ", 1)[1]
        self.assertIn(base, content.MONSTER_DROPS)


class TestInflictions(unittest.TestCase):
    def test_bestiary_inflicts(self):
        from hearthdelve.data import content
        by_name = {m.name: m for m in content.MONSTERS + content.BOSSES}
        self.assertEqual(by_name["Cave Spider"].inflicts, "poison")
        self.assertEqual(by_name["Ghoul"].inflicts, "sick")
        self.assertEqual(by_name["Cave Troll"].inflicts, "bleed")
        west = {c.name: c for c in content.WEST_WILDLIFE}
        self.assertEqual(west["Ember Drake"].inflicts, "burn")
        self.assertEqual(west["Rock Viper"].inflicts, "poison")

    def test_ruby_blade_and_status_ammo(self):
        from hearthdelve.data import content
        from hearthdelve.game import combat
        from hearthdelve.entities import items
        st = fresh_state(2)
        st.player.hotbar[st.player.active_slot] = content.make_gear(
            "Sword", "iron", gems=("ruby",))
        self.assertEqual(combat.weapon_inflict(st), "burn")
        self.assertEqual(content.ammo_stat(items.FIRE_ARROW).inflicts, "burn")
        self.assertEqual(content.ammo_stat(items.VENOM_ARROW).inflicts, "poison")


if __name__ == "__main__":
    unittest.main()
