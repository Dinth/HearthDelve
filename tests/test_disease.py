"""Illness keeps its own calendar.

Wounds (poison, bleed, burn) tick per action and a night's rest sweats them out.
A disease does neither: it costs days, survives sleeping, takes its toll each
dawn, and has to run its course — or be physicked away. That's what makes the
charcoal tincture, the panacea and the Fenwick bathhouse worth their price.
"""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _sicken(st, days: int = 6):
    """Put the player abed with a disease of a known length."""
    from hearthdelve.game import combat
    combat.apply_status(st, "sick", turns=days)
    return st


class TestTheTwoClocks(unittest.TestCase):
    def test_the_table_says_which_clock_each_affliction_keeps(self):
        from hearthdelve.game import combat
        self.assertTrue(combat.is_disease("sick"))
        for wound in ("poison", "bleed", "burn"):
            self.assertFalse(combat.is_disease(wound), f"{wound} should tick per action")

    def test_a_wound_bites_every_action_but_an_illness_does_not(self):
        from hearthdelve.game import combat, turns
        st = fresh_state(21)
        st.player.status.clear()
        combat.apply_status(st, "bleed")
        hp = st.player.hp
        turns.advance_time(st, 30)
        self.assertLess(st.player.hp, hp, "a wound should bleed as time passes")

        st2 = _sicken(fresh_state(22))
        st2.player.status = {"sick": 6}
        hp2, stam2 = st2.player.hp, st2.player.energy
        for _ in range(20):
            turns.advance_time(st2, 30)
        self.assertEqual(st2.player.hp, hp2, "illness must not nibble action by action")
        self.assertEqual(st2.player.status["sick"], 6, "…nor count down in actions")

    def test_a_wound_is_slept_off_but_an_illness_is_not(self):
        from hearthdelve.game import combat, farming
        st = fresh_state(23)
        combat.apply_status(st, "poison")
        combat.apply_status(st, "burn")
        st.player.status["sick"] = 5
        farming.new_day(st)
        self.assertNotIn("poison", st.player.status, "a night's rest clears wounds")
        self.assertNotIn("burn", st.player.status)
        self.assertIn("sick", st.player.status, "an illness survives the night")
        self.assertEqual(st.player.status["sick"], 4, "and loses exactly one day")


class TestItRunsItsCourse(unittest.TestCase):
    def test_it_goes_away_on_its_own_after_some_long_time(self):
        from hearthdelve.game import farming
        st = _sicken(fresh_state(24), days=6)
        nights = 0
        while "sick" in st.player.status and nights < 40:
            farming.new_day(st)
            nights += 1
        self.assertLess(nights, 40, "it must not last forever")
        self.assertEqual(nights, 6, "six days abed, six mornings to shake it")
        self.assertNotIn("sick", st.player.status)

    def test_no_two_illnesses_run_to_the_same_length(self):
        """Pillar 8: drifting, not a fixed week."""
        from hearthdelve.game import combat
        lo, hi = combat.STATUS["sick"]["days"]
        seen = set()
        for i in range(60):
            st = fresh_state(200 + i)
            st.player.sign = ""                     # the serpent would skew the range
            st.player.status.clear()
            combat.apply_status(st, "sick")
            seen.add(st.player.status["sick"])
        self.assertGreater(len(seen), 1, "a fixed duration is a metronome")
        self.assertTrue(min(seen) >= lo and max(seen) <= hi, f"{sorted(seen)} outside {lo}-{hi}")

    def test_the_serpent_born_shake_it_a_day_sooner(self):
        from hearthdelve.game import combat
        st = fresh_state(25)
        st.player.sign = "serpent"
        st.player.status.clear()
        combat.apply_status(st, "sick", turns=6)
        self.assertEqual(st.player.status["sick"], 5)

    def test_it_costs_health_and_the_day_s_rest_each_morning(self):
        from hearthdelve.game import farming
        st = _sicken(fresh_state(26), days=6)
        p = st.player
        farming.new_day(st)
        self.assertLess(p.hp, p.max_hp, "you wake short of health")
        self.assertLess(p.energy, p.max_energy, "and short of a day")
        self.assertGreater(p.energy, p.max_energy * 0.5, "but not crippled")

    def test_a_long_illness_never_kills_you(self):
        """Cozy game: it wears you down, it does not finish you off."""
        from hearthdelve.game import farming
        st = fresh_state(27)
        st.player.status["sick"] = 30            # far beyond any real illness
        for _ in range(30):
            farming.new_day(st)
            self.assertGreater(st.player.hp, 0, "an illness must never be lethal")


class TestPhysickingItAway(unittest.TestCase):
    def test_the_charcoal_tincture_and_panacea_cure_it_but_the_salve_does_not(self):
        from hearthdelve.game import commands
        from hearthdelve.entities import items
        for remedy, should_cure in ((items.CHARCOAL_TINCTURE, True),
                                    (items.PANACEA, True),
                                    (items.MANDRAKE_ELIXIR, False),
                                    (items.SALVE, False)):
            st = _sicken(fresh_state(28), days=6)
            st.player.inventory.add(remedy, 1)
            commands._eat(st, remedy, 0)
            self.assertEqual("sick" not in st.player.status, should_cure,
                             f"{remedy.name} cured={should_cure} expected")

    def test_the_bathhouse_sweats_it_out(self):
        from hearthdelve.game import commands, projects
        st = _sicken(fresh_state(29), days=6)
        commands._bathe(st)                       # not built yet: no cure
        self.assertIn("sick", st.player.status)
        projects.get(st, "bathhouse")["state"] = "done"
        st.player.energy = st.player.max_energy // 3     # a hard day's work behind us
        stam = st.player.energy
        commands._bathe(st)
        self.assertNotIn("sick", st.player.status, "a hot soak should break a fever")
        self.assertGreater(st.player.energy, stam, "and restore some of the day")

    def test_a_warding_tea_keeps_the_miasma_off(self):
        from hearthdelve.game import commands, skills
        from hearthdelve.world import tile
        st = fresh_state(30)
        st.player.status.clear()
        skills.apply_buff(st, "warded")
        st.world.tiles[st.player.x, st.player.y] = tile.MARSH
        for _ in range(4000):                     # far more marsh than any real trip
            commands._surface_tile_fx(st)
        self.assertNotIn("sick", st.player.status, "the ward should hold")

    def test_the_fen_can_still_make_you_ill_without_one(self):
        from hearthdelve.game import commands
        from hearthdelve.world import tile
        st = fresh_state(31)
        st.player.status.clear()
        st.world.tiles[st.player.x, st.player.y] = tile.MARSH
        for _ in range(4000):
            commands._surface_tile_fx(st)
            if "sick" in st.player.status:
                break
        self.assertIn("sick", st.player.status, "the miasma must still bite sometimes")

    def test_catching_it_is_uncommon_enough_to_survive_a_fen_trip(self):
        """It costs days now, so the incidence had to come down with it."""
        from hearthdelve.game import commands
        self.assertLess(commands.MIASMA_CHANCE, 0.005)
        trip = 1 - (1 - commands.MIASMA_CHANCE) ** 150     # a 150-step wander in the wet
        self.assertLess(trip, 0.55, "a fen trip shouldn't be a near-certain illness")
        self.assertGreater(trip, 0.10, "…but it should be a real risk")


class TestItSurvivesASave(unittest.TestCase):
    def test_the_days_left_round_trip(self):
        import os
        import tempfile
        from hearthdelve.engine import save
        st = _sicken(fresh_state(32), days=4)
        path = os.path.join(tempfile.gettempdir(), "hd_disease_rt.json")
        try:
            save.save(st, path)
            self.assertEqual(save.load(path).player.status.get("sick"), 4)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
