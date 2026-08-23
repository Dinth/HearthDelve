"""The cozy engine: soil, withering, animal illness, and apothecary gating."""
from __future__ import annotations

import random
import unittest

from tests.common import fresh_state


class TestSoil(unittest.TestCase):
    def test_soil_climbs_caps_and_slips(self):
        from hearthdelve.game import farming
        from hearthdelve.world.crops import CropPlot
        from hearthdelve.data import content
        st = fresh_state(4)
        crop = next(c for c in content.CROPS if not c.regrows)
        pos = (st.player.x + 1, st.player.y)
        random.seed(1)
        for _ in range(6):
            st.surface.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature)
            farming.harvest(st, *pos)
        self.assertEqual(st.surface.soil[pos], 4)          # capped
        st.surface.crops[pos] = CropPlot(crop=crop, dead=True)
        farming.harvest(st, *pos)
        self.assertEqual(st.surface.soil[pos], 3)          # neglect slips


class TestWithering(unittest.TestCase):
    def test_thirst_and_wither_days(self):
        from hearthdelve.world.crops import CropPlot, advance_growth
        from hearthdelve.data import content
        crop = next(c for c in content.CROPS if not c.paddy)
        p = CropPlot(crop=crop)
        advance_growth(p, crop.season, wither_days=1)      # clear sky: 1 dry day kills
        self.assertTrue(p.dead)
        p = CropPlot(crop=crop)
        for _ in range(2):
            advance_growth(p, crop.season, wither_days=3)  # cloudy: survives 2 dry days
        self.assertFalse(p.dead)
        p.watered = True
        advance_growth(p, crop.season, wither_days=3)
        self.assertEqual(p.thirst, 0)                      # watering resets the count


class TestAnimalIllness(unittest.TestCase):
    def _with_hen(self):
        from hearthdelve.entities.animal import Animal
        from hearthdelve.game import husbandry
        st = fresh_state(4)
        spec = husbandry.SPECIES["chicken"]
        hen = Animal(kind="chicken", name="T", glyph=spec.glyph, color=spec.color,
                     x=st.player.x + 1, y=st.player.y, home=(st.player.x + 1, st.player.y),
                     age_days=99, happiness=80)
        st.surface.animals.append(hen)
        return st, hen

    def test_sick_gives_nothing_then_recovers(self):
        from hearthdelve.game import husbandry
        st, hen = self._with_hen()
        hen.sick = 1
        random.seed(3)
        husbandry.new_day(st)
        self.assertEqual(hen.sick, 2)
        self.assertFalse(hen.produce_ready)
        hen.sick = husbandry.SICK_RECOVER_DAYS
        husbandry.new_day(st)
        self.assertEqual(hen.sick, 0)                      # runs its course

    def test_tonic_cures_on_the_spot(self):
        from hearthdelve.game import husbandry
        from hearthdelve.entities import items
        st, hen = self._with_hen()
        hen.sick = 3
        st.player.inventory.add(items.HERBAL_TONIC, 1, quality=0)
        husbandry.interact_animal(st, hen)
        self.assertEqual(hen.sick, 0)
        self.assertEqual(st.player.inventory.count(items.HERBAL_TONIC), 0)
        hen.sick = 3
        husbandry.interact_animal(st, hen)                 # no tonic: advice only
        self.assertEqual(hen.sick, 3)


class TestApothecary(unittest.TestCase):
    def test_brewing_is_station_only(self):
        from hearthdelve.game import crafting, skills, requests
        from hearthdelve.data import content
        from hearthdelve.entities import items
        st = fresh_state(4)
        st.player.skills["Herbalism"] = 8 * skills.XP_PER_LEVEL
        requests.check_level_recipes(st)
        visible = {r.name for r in crafting.visible_recipes(st)}
        remedies = {r.name for r in content.RECIPES if r.kind == "remedy"}
        self.assertFalse(remedies & visible, "remedies leaked into the hand-craft menu")
        # the bench still offers them, plus the two-step vodka chain
        st.player.inventory.add(items.SAGE, 4)
        st.player.inventory.add(items.CHARCOAL, 2)
        st.player.inventory.add(items.GRAIN_MASH, 1)
        opts = crafting.machine_load_options(st, content.MACHINES["apothecary"])
        labels = {o.get("label") for o in opts}
        self.assertIn("Antidote", labels)
        self.assertIn("Vodka", labels)


class TestRegrowHarvestKeepsItsWater(unittest.TestCase):
    """Picking a regrowing crop used to kill it outright under a clear sky.

    Three things compounded: the dawn rain and sprinkler passes both skipped
    ``mature`` plots, so a ripe plot went into the day dry; ``harvest`` then
    cleared ``watered``, discarding the player's own watering can; and
    ``_WITHER_DAYS["Clear"] == 1`` makes a single dry dawn fatal. All twelve
    regrowing crops died about one harvest in five, whatever the player did.
    """

    def _cycle(self, hand_water=False, weather="Clear", sprinkler=False):
        from hearthdelve.game import farming
        from hearthdelve.world.crops import CropPlot, advance_growth
        from hearthdelve.data import content
        crop = next(c for c in content.CROPS if c.regrows and c.season == "Spring")
        plot = CropPlot(crop=crop, days_grown=crop.days_to_mature)   # ripe at dawn
        wither = farming._WITHER_DAYS.get(weather, 999)
        advance_growth(plot, crop.season, wither)                    # dawn N tick
        if farming.is_wet_weather(weather) and not plot.dead:
            plot.watered = True                                     # dawn rain
        if sprinkler and not plot.dead:
            plot.watered = True                                     # dawn sprinkler
        if hand_water:
            plot.watered = True                                     # the player waters
        plot.days_grown = max(0, crop.days_to_mature - crop.regrow_days)  # harvest()
        advance_growth(plot, crop.season, wither)                   # dawn N+1
        return plot

    def test_hand_watering_before_harvest_is_not_thrown_away(self):
        self.assertFalse(self._cycle(hand_water=True).dead)

    def test_a_sprinklered_patch_survives_being_picked(self):
        self.assertFalse(self._cycle(sprinkler=True).dead)

    def test_rain_reaches_a_ripe_plot(self):
        self.assertFalse(self._cycle(weather="Rain").dead)

    def test_genuine_neglect_still_kills(self):
        """The pressure has to stay: no water at all under a clear sky is fatal."""
        self.assertTrue(self._cycle().dead)

    def test_harvest_leaves_the_watered_flag_alone(self):
        from hearthdelve.game import farming
        from hearthdelve.world.crops import CropPlot
        from hearthdelve.data import content
        st = fresh_state(4)
        crop = next(c for c in content.CROPS if c.regrows and c.season == st.season)
        pos = (st.player.x + 1, st.player.y)
        st.surface.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature,
                                         watered=True)
        random.seed(2)
        self.assertTrue(farming.harvest(st, *pos))
        self.assertTrue(st.surface.crops[pos].watered,
                        "harvest discarded water the player had already given the plot")

    def test_sprinklers_water_ripe_neighbours(self):
        from hearthdelve.game import crafting
        from hearthdelve.world.crops import CropPlot
        from hearthdelve.entities.machine import Machine
        from hearthdelve.data import content
        st = fresh_state(4)
        crop = next(c for c in content.CROPS if c.regrows)
        mx, my = st.player.x + 3, st.player.y + 3
        st.surface.machines[(mx, my)] = Machine(kind="sprinkler")
        pos = (mx + 1, my)
        st.surface.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature)
        self.assertTrue(st.surface.crops[pos].mature)
        crafting.run_sprinklers(st)
        self.assertTrue(st.surface.crops[pos].watered)


if __name__ == "__main__":
    unittest.main()
