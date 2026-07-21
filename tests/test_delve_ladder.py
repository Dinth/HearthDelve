"""The deep-delve ladder: new archetypes, AI behaviors, and their sinks."""
from __future__ import annotations

import random
import unittest

from tests.common import fresh_state


def _walkable_spot(world, px, py, minr=2):
    for r in range(minr, 12):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) >= minr and world.walkable(px + dx, py + dy):
                    return px + dx, py + dy
    return px, py


class TestNewArchetypes(unittest.TestCase):
    def test_roster_extends_past_floor_six(self):
        from hearthdelve.data import content
        # deep monsters exist and only appear at their intro depth or below
        deep = {m.name: m.min_depth for m in content.MONSTERS
                if m.name in ("Spore Spitter", "Bonecaller", "Magma Fiend",
                              "Barrow Wight", "Rockjaw Wyrm")}
        self.assertEqual(len(deep), 5)
        self.assertGreaterEqual(max(deep.values()), 10)      # the ladder now reaches ~10
        mine10 = {m.name for m in content.monsters_for("mine", 10)}
        self.assertIn("Rockjaw Wyrm", mine10)
        self.assertNotIn("Rockjaw Wyrm", {m.name for m in content.monsters_for("mine", 4)})

    def test_ranged_mob_strikes_from_a_distance(self):
        from hearthdelve.game import combat, delve
        from hearthdelve.data import content
        st = fresh_state(41)
        delve.enter(st, "grotto")
        p = st.player
        sx, sy = _walkable_spot(st.world, p.x, p.y, minr=3)
        spit = content.make_mob(next(m for m in content.MONSTERS if m.name == "Spore Spitter"),
                                sx, sy, 6, random.Random(1))
        spit.awake = True
        self.assertEqual(spit.reach, 4)
        hits = 0
        for s in range(60):
            st.world.monsters = [spit]
            spit.x, spit.y = sx, sy
            p.hp = 100
            random.seed(s)
            combat._step(st, spit)
            if p.hp < 100 and abs(spit.x - p.x) > 1 or abs(spit.y - p.y) > 1:
                hits += 1
        self.assertGreater(hits, 20, "a ranged mob should land blows without closing to melee")

    def test_summoner_raises_minions_on_a_cooldown(self):
        from hearthdelve.game import combat, delve
        from hearthdelve.data import content
        st = fresh_state(42)
        delve.enter(st, "barrow")
        p = st.player
        sx, sy = _walkable_spot(st.world, p.x, p.y, minr=2)
        bc = content.make_mob(next(m for m in content.MONSTERS if m.name == "Bonecaller"),
                              sx, sy, 8, random.Random(3))
        bc.awake = True
        self.assertEqual(bc.summons, "Skeleton")
        st.world.monsters = [bc]
        random.seed(1)
        combat._try_summon(st, bc)
        self.assertIn("Skeleton", [o.name for o in st.world.monsters])
        self.assertGreater(bc.summon_cd, 0)
        before = len(st.world.monsters)
        combat._try_summon(st, bc)                           # cooldown blocks it
        self.assertEqual(len(st.world.monsters), before)


class TestDeepDropsHaveSinks(unittest.TestCase):
    def test_new_reagents_drop_and_sink(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import requests
        for name in ("Spore Spitter", "Bonecaller", "Magma Fiend", "Barrow Wight", "Rockjaw Wyrm"):
            self.assertIn(name, content.MONSTER_DROPS)
        relic = {it.name for it in content.COLLECTION["Reliquary"]}
        st = fresh_state(7)
        pools = {p.name for role in ("trapper", "forager")
                 for p in requests._request_pool(st, role)}
        for r in (items.SPORE_SAC, items.GRAVE_DUST, items.EMBER_CORE, items.WYRM_SCALE):
            self.assertIn(r.name, relic, f"{r.name} has no collection sink")
            self.assertIn(r.name, pools, f"{r.name} has no request-board sink")
            self.assertGreater(r.value, 0)


class TestBosses(unittest.TestCase):
    def test_bosses_have_varied_mechanics(self):
        from hearthdelve.data import content
        by = {b.name: b for b in content.BOSSES}
        self.assertGreaterEqual(len(by), 5)
        self.assertTrue(by["Molten Colossus"].enrage)
        self.assertEqual(by["The Bonelord"].behavior, "summon")
        self.assertEqual(by["Abyssal Horror"].behavior, "ranged")
        self.assertGreater(by["Abyssal Horror"].reach, 0)

    def test_every_boss_drops_a_signature_trophy(self):
        from hearthdelve.data import content
        trophies = {it.name for it in content.COLLECTION["Trophies"]}
        self.assertEqual(len(trophies), 5)
        for b in content.BOSSES:
            drops = {i.name for i, _ in content.MONSTER_DROPS.get(b.name, ())}
            self.assertTrue(drops & trophies, f"{b.name} drops no trophy")

    def test_enrage_erupts_below_half_health(self):
        from hearthdelve.game import combat, delve
        from hearthdelve.data import content
        st = fresh_state(50)
        delve.enter(st, "mine")
        mc = content.make_mob(next(b for b in content.BOSSES if b.name == "Molten Colossus"),
                              st.player.x + 2, st.player.y, 8, random.Random(1), boss=True)
        mc.awake = True
        st.world.monsters = [mc]
        st.world.visible = None
        before = mc.dmg
        mc.hp = mc.max_hp // 2 - 1
        combat.monsters_act(st)
        self.assertTrue(mc.enraged)
        self.assertGreater(mc.dmg[1], before[1])

    def test_trophies_wing_sharpens_crit(self):
        from hearthdelve.game import combat
        st = fresh_state(51)
        base = combat.player_crit(st)
        st.stats["wing_done_Trophies"] = 1
        self.assertGreater(combat.player_crit(st), base)


if __name__ == "__main__":
    unittest.main()
