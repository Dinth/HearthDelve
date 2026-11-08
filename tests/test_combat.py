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


class TestTheBowSharesTheFightersEdge(unittest.TestCase):
    """Melee and the bow summed their bonuses by hand, separately, and every
    bonus that comes from the fighter rather than the weapon went into melee
    only: jewellery's to-hit, crit and damage, the Clarity Draught, the wolf's
    birth sign and the Hall's Trophies wing never reached a loosed arrow."""

    def _fight(self):
        from hearthdelve.data import content
        from hearthdelve.entities.monster import Mob
        st = fresh_state(1)
        bow = content.ranged_stat(content.make_ranged("Short Bow", "birch"))
        px, py = st.player.x, st.player.y
        fx, fy = next((px + dx, py + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                                                         (1, 1), (-1, -1), (1, -1), (-1, 1))
                      if st.world.walkable(px + dx, py + dy))        # open ground to shoot across
        foe = Mob("Target", "T", (200, 200, 200), 99, 99, 1, "chase", fx, fy, dv=0, pv=0)
        st.world.monsters.append(foe)
        return st, bow, foe

    def _edge_on(self, st):
        from unittest import mock
        from hearthdelve.game import collection, jewelry
        st.player.buff, st.player.buff_until = "clarity", st.abs_minutes + 600
        st.player.sign = "wolf"
        real = jewelry.combat_bonus(st)
        ring = {**real, "to_hit": real["to_hit"] + 3, "crit": real["crit"] + 0.05,
                "dmg": real["dmg"] + 2}
        return [mock.patch.object(jewelry, "combat_bonus", return_value=ring),
                mock.patch.object(collection, "perk_earned", return_value=True)]

    def test_to_hit_and_crit_rise_alike_for_sword_and_bow(self):
        from hearthdelve.game import combat
        st, bow, _foe = self._fight()
        before = (combat.player_to_hit(st), combat._ranged_to_hit(st, bow),
                  combat.player_crit(st), combat.ranged_crit(st, bow))
        patches = self._edge_on(st)
        for pt in patches:
            pt.start()
        try:
            after = (combat.player_to_hit(st), combat._ranged_to_hit(st, bow),
                     combat.player_crit(st), combat.ranged_crit(st, bow))
        finally:
            for pt in patches:
                pt.stop()
        self.assertEqual(after[0] - before[0], 6)                 # ring 3, draught 2, wolf 1
        self.assertEqual(after[1] - before[1], after[0] - before[0])
        self.assertAlmostEqual(after[2] - before[2], 0.20)        # ring, Trophies, draught
        self.assertAlmostEqual(after[3] - before[3], after[2] - before[2])

    def test_a_rings_damage_rides_the_arrow_too(self):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st, bow, foe = self._fight()
        seen = []

        def record(to_hit, dmg_range, dmg_bonus, *a, **k):
            seen.append(dmg_bonus)
            return None                                            # a miss; we only want the sum
        astat = content.ammo_stat(items.ARROW)
        with mock.patch.object(combat, "_resolve", side_effect=record):
            combat.player_attack(st, foe)
            combat._resolve_shot(st, bow, items.ARROW, astat, foe.x, foe.y)
            patches = self._edge_on(st)
            for pt in patches:
                pt.start()
            try:
                combat.player_attack(st, foe)
                combat._resolve_shot(st, bow, items.ARROW, astat, foe.x, foe.y)
            finally:
                for pt in patches:
                    pt.stop()
        melee0, shot0, melee1, shot1 = seen
        self.assertEqual(melee1 - melee0, 2)
        self.assertEqual(shot1 - shot0, 2)


class TestTheBladeSaysWhatItLeaves(unittest.TestCase):
    """A Venom Draught poisons what you strike, but the log always read 'Your
    blade sears the … — it catches fire!', the ruby's line."""

    def _strike(self, buff="", gems=()):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game import combat
        st = fresh_state(1)
        st.player.hotbar[st.player.active_slot] = content.make_gear("Sword", "iron", gems=gems)
        if buff:
            st.player.buff, st.player.buff_until = buff, st.abs_minutes + 600
        foe = Mob("Target", "T", (200, 200, 200), 99, 99, 1, "chase",
                  st.player.x + 1, st.player.y, dv=0, pv=0)
        with mock.patch.object(combat, "_resolve", return_value=(5, False)), \
                mock.patch.object(combat.random, "random", return_value=0.0):
            combat.player_attack(st, foe)
        return foe, " ".join(t for t, _c in st.log.messages)

    def test_a_venom_draught_poisons_and_says_so(self):
        foe, log = self._strike(buff="venomed")
        self.assertIn("poison", foe.status)
        self.assertNotIn("fire", log)
        self.assertIn("poison", log)

    def test_a_ruby_still_burns_in_its_own_words(self):
        foe, log = self._strike(gems=("ruby",))
        self.assertIn("burn", foe.status)
        self.assertIn("catches fire", log)


class TestABlastedGemVeinKnowsItsDepth(unittest.TestCase):
    """The pickaxe draws a vein's gem from the depth's band; a bomb drew from
    the flat table used for gifts. At depth 1 a bomb could give diamonds the
    pick never can, and at depth 10 it gave a seventh as many."""

    def _blast(self, depth, n=400):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        from hearthdelve.world import tile
        st = fresh_state(1)
        st.world.depth = depth
        x, y = st.player.x, st.player.y
        random.seed(depth)
        vein = tile.TILES[tile.GEM_VEIN]
        for _ in range(n):                              # the blast reads the vein it's given
            combat._shatter(st, x, y, vein)
        return st.player.inventory.count(items.DIAMOND) / n

    def test_no_diamonds_in_the_shallows(self):
        self.assertEqual(self._blast(1), 0.0)

    def test_deep_veins_give_deep_stones(self):
        self.assertGreater(self._blast(10), 0.2)


class TestJewellerySparesYourStrengthInAFight(unittest.TestCase):
    """The codex tells you to wear jewellery that spares your strength for the
    deep's fatigue — but an amethyst's ease only lightened tool work; every
    blow and shot cost the full 3 + depth/3."""

    def _stamina_spent(self, ring, shoot=False):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game import combat
        st = fresh_state(1)
        st.world.depth = 12                       # deep: the blow costs 3 + 4
        if ring:
            st.player.equipment["ring1"] = content.make_jewel("Ring", "gold", "amethyst")
            st.player.equip_quality["ring1"] = 5
        foe = Mob("Target", "T", (200, 200, 200), 99, 99, 1, "chase",
                  st.player.x + 1, st.player.y, dv=0, pv=0)
        st.world.monsters.append(foe)
        before = st.player.energy
        with mock.patch.object(combat, "_resolve", return_value=None):   # a miss is enough
            if shoot:
                st.player.equipment["ranged"] = content.make_ranged("Short Bow", "birch")
                st.player.inventory.add(items.ARROW, 5)
                self.assertTrue(combat.fire_ranged_at(st, foe.x, foe.y))
            else:
                combat.player_attack(st, foe)
        return before - st.player.energy

    def test_a_worn_amethyst_lightens_a_blow(self):
        self.assertEqual(self._stamina_spent(ring=False), 7)
        self.assertLess(self._stamina_spent(ring=True), 7)

    def test_and_a_shot(self):
        self.assertLess(self._stamina_spent(ring=True, shoot=True),
                        self._stamina_spent(ring=False, shoot=True))

    def test_never_free(self):
        from unittest import mock
        from hearthdelve.game import combat, jewelry
        st = fresh_state(1)
        with mock.patch.object(jewelry, "cozy_bonus", return_value=50.0):
            self.assertEqual(combat.fight_stamina(st), 1)


class TestTheDiceHaveTheLastWord(unittest.TestCase):
    """Monster accuracy grows with depth without limit, and a hit was simply
    d20 + to-hit against DV: past about depth 25 nothing missed you at all,
    and dart traps — growing with depth too — ignored armour entirely. As in
    ADOM, a natural 1 now always misses and a natural 20 always hits, and
    armour soaks a dart as it soaks a blow."""

    def test_a_natural_1_always_misses(self):
        from unittest import mock
        from hearthdelve.game import combat
        with mock.patch.object(combat.random, "randint", side_effect=[1, 5]):
            self.assertIsNone(combat._resolve(999, (5, 5), 0, 0.0, 0, 0))

    def test_a_natural_20_always_hits(self):
        from unittest import mock
        from hearthdelve.game import combat
        with mock.patch.object(combat.random, "randint", side_effect=[20, 5]), \
                mock.patch.object(combat.random, "random", return_value=0.99):
            self.assertIsNotNone(combat._resolve(-999, (5, 5), 0, 0.0, 999, 0))

    def test_a_deep_monster_misses_now_and_then(self):
        from hearthdelve.game import combat
        random.seed(4)
        misses = sum(combat._resolve(60, (5, 9), 0, 0.0, 12, 4) is None for _ in range(4000))
        self.assertGreater(misses, 4000 * 0.03)
        self.assertLess(misses, 4000 * 0.08)          # one roll in twenty, near enough

    def _dart(self, armour):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.game import commands, delve
        st = fresh_state(1)
        mouth = sorted(p for p, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        st.world.depth = 20
        if armour:
            for base, slot in (("Armour", "body"), ("Helm", "head"), ("Leggings", "legs"),
                               ("Shield", "shield")):
                st.player.equipment[slot] = content.make_gear(base, "steel")
        before = st.player.hp
        with mock.patch.object(commands.random, "random", return_value=0.0), \
                mock.patch.object(commands.random, "randint", return_value=4):
            commands._spring_trap(st)
        return before - st.player.hp

    def test_armour_soaks_a_dart(self):
        bare, plated = self._dart(False), self._dart(True)
        self.assertEqual(bare, 24)                     # 4 + depth 20, nothing in the way
        self.assertLess(plated, bare)
        self.assertGreaterEqual(plated, 1)


class TestStatusArrowsWaitToBeReadied(unittest.TestCase):
    """Fire and venom arrows are fletched to be readied deliberately, but with
    nothing readied a shot spent the 'best' arrow by damage — and their +1 put
    them above plain wood and level with copper tips, so a bow burned through
    your sulphur arrows on a rabbit."""

    def _shot_spends(self, carried, readied=None):
        from hearthdelve.data import content
        from hearthdelve.game import combat
        st = fresh_state(1)
        for it in carried:
            st.player.inventory.add(it, 10)
        if readied is not None:
            st.player.equipment["ammo"] = readied
        bow = content.ranged_stat(content.make_ranged("Short Bow", "birch"))
        return combat.chosen_ammo(st, bow)

    def test_a_plain_or_tipped_arrow_goes_first(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        copper = content.ARROW_FROM_ORE[items.COPPER_ORE]
        self.assertIs(self._shot_spends([items.ARROW, items.FIRE_ARROW]), items.ARROW)
        self.assertIs(self._shot_spends([items.VENOM_ARROW, items.ARROW]), items.ARROW)
        self.assertIs(self._shot_spends([items.FIRE_ARROW, items.ARROW, copper]), copper)

    def test_readied_status_arrows_are_loosed(self):
        from hearthdelve.entities import items
        self.assertIs(self._shot_spends([items.ARROW, items.FIRE_ARROW],
                                        readied=items.FIRE_ARROW), items.FIRE_ARROW)

    def test_with_nothing_else_left_they_still_fly(self):
        from hearthdelve.entities import items
        self.assertIs(self._shot_spends([items.VENOM_ARROW]), items.VENOM_ARROW)


if __name__ == "__main__":
    unittest.main()
