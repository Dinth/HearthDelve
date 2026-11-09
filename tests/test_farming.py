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


class TestTodaysRainWatersTodaysSowing(unittest.TestCase):
    """Rain and sprinklers soak the plots at dawn only, so a seed sown into
    the day's rain (or right beside a sprinkler) started dry, and the next dawn
    counted it as neglected."""

    def _sow(self, weather="Clear", sprinkler=False):
        from hearthdelve.data import content
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import farming
        from hearthdelve.world import tile
        st = fresh_state(4)
        st.weather = weather
        x, y = st.player.x + 2, st.player.y + 2
        st.surface.tiles[x, y] = tile.TILLED
        st.surface.crops.pop((x, y), None)
        st.surface.machines.pop((x, y), None)
        if sprinkler:
            st.surface.tiles[x + 1, y] = tile.TILLED
            st.surface.machines[(x + 1, y)] = Machine(kind="sprinkler")
        seed, crop = next((sd, c) for sd, c in farming.SEED_TO_CROP.items()
                          if c.season == st.season)
        st.player.inventory.add(seed, 1)
        farming.plant(st, x, y, seed)
        return st, st.surface.crops[(x, y)]

    def test_a_seed_sown_in_the_rain_is_watered(self):
        self.assertTrue(self._sow("Rain")[1].watered)
        self.assertTrue(self._sow("Storm")[1].watered)

    def test_a_seed_sown_beside_a_sprinkler_is_watered(self):
        self.assertTrue(self._sow("Clear", sprinkler=True)[1].watered)

    def test_a_dry_day_sowing_still_needs_the_can(self):
        self.assertFalse(self._sow("Clear")[1].watered)

    def test_it_grows_overnight_without_a_trip_with_the_can(self):
        from hearthdelve.game import farming
        st, plot = self._sow("Rain")
        farming.new_day(st)
        self.assertEqual(plot.days_grown, 1)
        self.assertFalse(plot.dead)


class TestTheSeasonsEndIsNotNeglect(unittest.TestCase):
    """Clearing any dead plot cost a point of soil ("neglect leaches the
    ground") — including a regrower that simply reached the end of its season,
    which every patch of berries does once a year."""

    def _patch(self):
        from hearthdelve.data import content
        from hearthdelve.world.crops import CropPlot
        st = fresh_state(4)
        x, y = st.player.x + 2, st.player.y + 2
        crop = next(c for c in content.CROPS if c.regrows and c.season == st.season)
        st.surface.crops[(x, y)] = CropPlot(crop=crop, days_grown=crop.days_to_mature)
        st.surface.soil[(x, y)] = 3
        return st, x, y

    def test_a_crop_whose_season_ended_clears_without_costing_soil(self):
        from hearthdelve.engine import constants as C
        from hearthdelve.game import farming
        st, x, y = self._patch()
        st.day = C.SEASON_LEN - 1                          # the season's last day
        farming.new_day(st)                                # and it turns
        plot = st.surface.crops[(x, y)]
        self.assertTrue(plot.dead and plot.season_ended)
        farming.harvest(st, x, y)                          # clear it away
        self.assertEqual(st.surface.soil[(x, y)], 3)

    def test_a_plant_left_to_wither_still_costs_soil(self):
        from hearthdelve.game import farming
        st, x, y = self._patch()
        plot = st.surface.crops[(x, y)]
        plot.dead = True                                   # withered in its own season
        farming.harvest(st, x, y)
        self.assertEqual(st.surface.soil[(x, y)], 2)

    def test_the_cause_survives_a_save_and_old_saves_are_read_kindly(self):
        import json
        from hearthdelve.engine import constants as C
        from hearthdelve.engine import save
        from hearthdelve.game import farming
        st, x, y = self._patch()
        st.day = C.SEASON_LEN - 1
        farming.new_day(st)                                # autosaves the season death
        self.assertTrue(save.load().surface.crops[(x, y)].season_ended)
        with open(save.default_path()) as f:
            raw = json.load(f)
        raw["crops"][f"{x},{y}"] = raw["crops"][f"{x},{y}"][:6]     # an older record
        with open(save.default_path(), "w") as f:
            json.dump(raw, f)
        self.assertTrue(save.load().surface.crops[(x, y)].season_ended)


class TestSaplingsArePlantedAtHome(unittest.TestCase):
    """plant() refused anywhere but the Vale, but plant_tree() only refused the
    dungeons: a sapling set in the Westreach took the sapling, never grew (the
    night only ages the Vale's trees) and was gone on the next load (the
    Westreach saves its tiles and beasts, not trees)."""

    def test_a_sapling_is_not_taken_in_the_westreach(self):
        from hearthdelve.entities import items
        from hearthdelve.game import farming
        from hearthdelve.world import westgen
        st = fresh_state(4)
        st.west = westgen.generate(st.seed)
        st.world = st.west
        x, y = next((x, y) for x in range(st.west.width) for y in range(st.west.height)
                    if st.west.tile_at(x, y).name in ("grass", "meadow"))
        st.player.inventory.add(items.APPLE_SAPLING, 1)
        farming.plant_tree(st, x, y, items.APPLE_SAPLING)
        self.assertEqual(st.west.trees, {})
        self.assertEqual(st.player.inventory.count(items.APPLE_SAPLING), 1)

    def test_one_still_plants_at_home(self):
        from hearthdelve.entities import items
        from hearthdelve.game import farming
        st = fresh_state(4)
        p = st.player                         # open grass near home, any direction
        x, y = next((p.x + dx, p.y + dy) for r in range(2, 30)
                    for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                    if max(abs(dx), abs(dy)) == r
                    and st.surface.tile_at(p.x + dx, p.y + dy).name == "grass"
                    and (p.x + dx, p.y + dy) not in st.surface.trees)
        st.player.inventory.add(items.APPLE_SAPLING, 1)
        farming.plant_tree(st, x, y, items.APPLE_SAPLING)
        self.assertIn((x, y), st.surface.trees)


class TestFaintingKeepsYourMedicine(unittest.TestCase):
    """Fainting below drops the loose loot you carried — and every remedy went
    with it, being kind 'material': a 440g Panacea kept for an emergency, the
    potions, and the attribute treats (kind 'food')."""

    def _faint_below(self, *carried):
        from hearthdelve.game import delve, farming
        st = fresh_state(1)
        mouth = sorted(p for p, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        for it in carried:
            st.player.inventory.add(it, 2)
        farming.collapse(st, "You collapse.")
        return st

    def test_remedies_potions_and_treats_stay_in_your_pack(self):
        from hearthdelve.entities import items
        kept = (items.PANACEA, items.by_name("Greater Healing Potion"), items.by_name("Sulphur Salve"),
                items.by_name("Firebrand Elixir"), items.TITAN_MARROW, items.by_name("Warding Tea"))
        st = self._faint_below(*kept)
        for it in kept:
            with self.subTest(item=it.name):
                self.assertEqual(st.player.inventory.count(it), 2)

    def test_the_loose_loot_is_still_lost(self):
        from hearthdelve.entities import items
        st = self._faint_below(items.COPPER_ORE, items.BREAD)
        self.assertEqual(st.player.inventory.count(items.COPPER_ORE), 0)
        self.assertEqual(st.player.inventory.count(items.BREAD), 0)


if __name__ == "__main__":
    unittest.main()
