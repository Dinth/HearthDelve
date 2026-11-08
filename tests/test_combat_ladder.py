"""The armour ladder must pay, and a mid-fight heal must cost something.

ARM-1. Two mechanics cancelled the whole upper half of the armour ladder.
``soak = min(pv, dmg * 2 // 3)`` capped useful Protection at two thirds of the
attacker's top-end hit, so against a depth-8 Magma Fiend cotton (PV 10) and
mithril (PV 21) were indistinguishable — 29.0 turns to die against 29.2, for 210g
against 1,890g. And steel and adamantium each carry -1 DV per piece, which summed
across eight slots to -7 and dropped a fully plated hero to DV 5, where anything
with to-hit +7 or better hit them *every* time. Full adamantium, the costliest
suit in the game, was beaten by 420g of iron.

FOOD-1. Eating cost 45 seconds, which advance_time turns into two monster turns.
Every remedy in the game netted between +24 and +95 HP, so any fight was winnable
by alternating attack and eat until the pack ran dry.
"""
from __future__ import annotations

import random
import unittest

from tests.common import fresh_state

from hearthdelve.data import content
from hearthdelve.engine import constants as C
from hearthdelve.entities import items
from hearthdelve.game import combat, skills, turns

BASES = ("Armour", "Helm", "Leggings", "Boots", "Gauntlets", "Girdle", "Shield", "Cloak")


def _suit(st, material):
    p = st.player
    p.skills = {s: 0 for s in skills.SKILLS}
    p.skills["Combat"] = 5 * skills.XP_PER_LEVEL
    p.mastery = {"blade": 5 * skills.MASTERY_PER}
    p.attrs = dict(p.attrs); p.attrs["Dx"] = 14; p.attrs["St"] = 14
    p.equipment = {k: None for k in p.equipment}
    for base in BASES:
        it = content.make_gear(base, material, "", "", ())
        if content.ARMOR_SLOT.get(it) and content.ARMOR_STATS.get(it):
            p.equipment[content.ARMOR_SLOT[it]] = it
    p.weapon = content.make_gear("Sword", "iron", "", "", ())
    p.hotbar = [p.weapon]; p.active_slot = 0
    return combat.player_dv(st), combat.player_pv(st)


def _damage_per_turn(mob, dv, pv, n=20000):
    """Mean damage a mob's blow deals through this armour, by simulation. On a
    fixed seed (restoring the global stream after), so a claim sitting close to
    its threshold can't pass on one run and fail on the next."""
    saved = random.getstate()
    random.seed(20000)
    try:
        total = 0
        for _ in range(n):
            r = combat._resolve(mob.to_hit, mob.dmg, 0, 0.0, dv, pv)
            if r:
                total += r[0]
        return total / n
    finally:
        random.setstate(saved)


def _mob(depth, name):
    """A plain, non-elite mob of this kind, at its *median* stat roll.

    make_mob can roll an elite variant with a name prefix and boosted stats,
    which is not what a ladder test wants to measure against — so only exact
    template matches count. And a plain mob's to-hit and damage still vary a
    band either way (a depth-15 Rockjaw Wyrm rolls one of three), so taking
    whatever the shared random stream produced made these tests flaky: the
    mid-fight salve claim failed about one run in four. The median of a fixed
    set of rolls is a reproducible, representative opponent."""
    t = next(x for x in content.MONSTERS if x.name == name)
    plain = [m for m in (content.make_mob(t, 5, 5, depth, random.Random(seed))
                         for seed in range(41)) if m.name == name]
    plain.sort(key=lambda m: (m.to_hit, tuple(m.dmg), m.hp))
    return plain[len(plain) // 2]


class ArmourDodgePenaltyTest(unittest.TestCase):
    def test_the_aggregate_dodge_penalty_is_capped(self):
        st = fresh_state(3)
        for material in ("steel", "adamantium"):
            with self.subTest(material=material):
                _suit(st, material)
                dv, _ = combat._worn(st)
                self.assertGreaterEqual(dv, -combat.MAX_ARMOR_DV_PENALTY,
                                        f"a full {material} suit costs {dv} DV")

    def test_plate_never_guarantees_a_hit(self):
        """DV 5 against to-hit +7 meant a literal 100% hit rate."""
        st = fresh_state(3)
        for material in ("steel", "adamantium"):
            dv, pv = _suit(st, material)
            mob = _mob(8, "Magma Fiend")
            misses = sum(1 for _ in range(4000)
                         if combat._resolve(mob.to_hit, mob.dmg, 0, 0.0, dv, pv) is None)
            with self.subTest(material=material):
                self.assertGreater(misses, 0,
                                   f"full {material} (DV {dv}) can never dodge a depth-8 blow")


class ProtectionLadderTest(unittest.TestCase):
    def test_protection_never_saturates(self):
        """More PV must always mean less damage, wherever blows are big enough for
        it to matter. (Shallow hits already bottom out on the min_dmg floor, which
        is the thing that guarantees no total immunity — so measure this where the
        old 2/3 cap actually flattened the ladder.)"""
        for depth, name in ((12, "Rockjaw Wyrm"), (15, "Rockjaw Wyrm")):
            mob = _mob(depth, name)
            last = None
            for pv in (10, 13, 16, 18, 21, 25):
                dpt = _damage_per_turn(mob, 13, pv)
                if last is not None:
                    with self.subTest(depth=depth, pv=pv):
                        self.assertLess(dpt, last,
                                        f"PV {pv} takes as much as the tier below at depth {depth}")
                last = dpt

    def test_the_upper_ladder_beats_iron(self):
        """The headline bug: iron, silver and mithril were identical at every depth."""
        st = fresh_state(3)
        for depth, name in ((8, "Magma Fiend"), (12, "Rockjaw Wyrm"), (15, "Rockjaw Wyrm")):
            mob = _mob(depth, name)
            iron = _damage_per_turn(mob, *_suit(st, "iron"))
            for better in ("silver", "mithril", "adamantium"):
                dpt = _damage_per_turn(mob, *_suit(st, better))
                with self.subTest(depth=depth, material=better):
                    self.assertLess(dpt, iron,
                                    f"{better} takes {dpt:.2f}/turn against iron's {iron:.2f}"
                                    f" at depth {depth} — the tier buys nothing")

    def test_the_metal_ladder_is_monotone_where_blows_are_big(self):
        st = fresh_state(3)
        for depth, name in ((12, "Rockjaw Wyrm"), (15, "Rockjaw Wyrm")):
            mob = _mob(depth, name)
            last = None
            for material in ("cotton", "bronze", "iron", "steel", "mithril", "adamantium"):
                dpt = _damage_per_turn(mob, *_suit(st, material))
                if last is not None:
                    with self.subTest(depth=depth, material=material):
                        self.assertLessEqual(dpt, last + 0.15,
                                             f"{material} is worse than the tier below at depth {depth}")
                last = dpt

    def test_armour_is_never_total_immunity(self):
        """min_dmg does the work the soak cap used to: a blow always lands for >= 1."""
        for _ in range(500):
            r = combat._resolve(99, (10, 20), 0, 0.0, 0, 9999)
            self.assertIsNotNone(r)
            self.assertGreaterEqual(r[0], 1)


class MidFightHealTest(unittest.TestCase):
    def _steps(self, seconds):
        return max(1, min(round(seconds / C.MOVE_SECONDS), turns._MAX_STEPS))

    def test_a_quiet_meal_still_takes_a_moment(self):
        from hearthdelve.game import commands
        st = fresh_state(3)
        st.world.monsters = []
        self.assertEqual(commands._eat_seconds(st), C.USE_SECONDS)

    def test_drinking_under_fire_costs_real_tempo(self):
        from hearthdelve.game import commands
        st = fresh_state(3)
        mob = _mob(8, "Magma Fiend")
        mob.x, mob.y = st.player.x + 1, st.player.y
        mob.awake = True
        st.world.monsters = [mob]
        self.assertEqual(commands._eat_seconds(st), commands.EAT_COMBAT_SECONDS)
        # Several enemy turns, not the two a 45-second sip used to buy.
        self.assertGreaterEqual(self._steps(commands.EAT_COMBAT_SECONDS), 4)
        self.assertGreater(self._steps(commands.EAT_COMBAT_SECONDS),
                           self._steps(C.USE_SECONDS))

    def test_a_grazing_rabbit_is_not_a_threat(self):
        from hearthdelve.game import commands
        st = fresh_state(3)
        crit = _mob(8, "Magma Fiend")
        crit.x, crit.y = st.player.x + 1, st.player.y
        crit.awake, crit.kind, crit.hostile = True, "wildlife", False
        st.world.monsters = [crit]
        self.assertEqual(commands._eat_seconds(st), C.USE_SECONDS)

    def test_a_sleeping_monster_is_not_a_threat(self):
        from hearthdelve.game import commands
        st = fresh_state(3)
        mob = _mob(8, "Magma Fiend")
        mob.x, mob.y = st.player.x + 1, st.player.y
        mob.awake = False
        st.world.monsters = [mob]
        self.assertEqual(commands._eat_seconds(st), C.USE_SECONDS)

    def test_a_cheap_remedy_no_longer_out_heals_a_deep_fight(self):
        """The behavioural claim: chugging salves can't carry you any more."""
        from hearthdelve.game import commands
        st = fresh_state(3)
        dv, pv = _suit(st, "iron")
        mob = _mob(15, "Rockjaw Wyrm")
        cost = self._steps(commands.EAT_COMBAT_SECONDS) * _damage_per_turn(mob, dv, pv)
        self.assertLess(items.BY_NAME["Sulphur Salve"].heal, cost,
                        "a 30 HP salve still nets positive in a depth-15 fight")

    def test_a_real_healing_potion_is_still_worth_drinking(self):
        """The fix must not make healing pointless — the 360g potion is the
        emergency button and has to work."""
        from hearthdelve.game import commands
        st = fresh_state(3)
        dv, pv = _suit(st, "iron")
        mob = _mob(12, "Rockjaw Wyrm")
        cost = self._steps(commands.EAT_COMBAT_SECONDS) * _damage_per_turn(mob, dv, pv)
        self.assertGreater(items.BY_NAME["Greater Healing Potion"].heal, cost,
                           "even a 360g potion is now a net loss — healing has become pointless")


if __name__ == "__main__":
    unittest.main()
