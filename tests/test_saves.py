"""Save-format safety: full round-trips, and old saves grandfathering cleanly.

The save contract: records are positional and append-only; new fields load with
defaults when absent. Breaking this bricks players' farms — these tests are the
tripwire.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from tests.common import fresh_state


class TestSaveRoundTrip(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.gettempdir(), "hd_test_save.json")

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _mutated_state(self):
        from hearthdelve.entities import items
        from hearthdelve.entities.animal import Animal
        from hearthdelve.game import husbandry
        from hearthdelve.world.crops import CropPlot
        from hearthdelve.data import content
        st = fresh_state(3)
        p = st.player
        p.gold = 777
        p.status = {"poison": 3, "sick": 5}
        st.donated = {"Ruby", "Chamomile"}
        st.seen_events = {"Hollis:4"}
        st.known_recipes.add("Antidote")
        st.surface.soil[(50, 50)] = 3
        crop = content.CROPS[0]
        st.surface.crops[(51, 50)] = CropPlot(crop=crop, days_grown=1, thirst=2,
                                              fertilized=True)
        spec = husbandry.SPECIES["chicken"]
        st.surface.animals.append(Animal(
            kind="chicken", name="RoundTrip", glyph=spec.glyph, color=spec.color,
            x=52, y=50, home=(52, 50), age_days=9, happiness=64, sick=2))
        return st

    def test_everything_round_trips(self):
        from hearthdelve.engine import save
        st = self._mutated_state()
        save.save(st, self.path)
        st2 = save.load(self.path)
        self.assertEqual(st2.player.gold, 777)
        self.assertEqual(st2.player.status, {"poison": 3, "sick": 5})
        self.assertEqual(st2.donated, {"Ruby", "Chamomile"})
        self.assertEqual(st2.seen_events, {"Hollis:4"})
        self.assertIn("Antidote", st2.known_recipes)
        self.assertEqual(st2.surface.soil.get((50, 50)), 3)
        plot = st2.surface.crops.get((51, 50))
        self.assertIsNotNone(plot)
        self.assertEqual((plot.thirst, plot.fertilized), (2, True))
        beast = next(a for a in st2.surface.animals if a.name == "RoundTrip")
        self.assertEqual((beast.sick, beast.happiness, beast.age_days), (2, 64, 9))

    def test_old_save_grandfathers(self):
        """Strip every recently-added key/field; the save must still load with
        sensible defaults — never a crash, never a wiped farm."""
        from hearthdelve.engine import save
        st = self._mutated_state()
        save.save(st, self.path)
        with open(self.path) as f:
            raw = json.load(f)
        for key in ("soil", "donated", "seen_events", "projects"):
            raw.pop(key, None)
        raw["animals"] = [rec[:9] for rec in raw.get("animals", [])]
        raw["wildlife"] = [rec[:18] for rec in raw.get("wildlife", [])]
        raw["crops"] = {k: rec[:4] for k, rec in raw.get("crops", {}).items()}
        raw.get("player", {}).pop("status", None)
        with open(self.path, "w") as f:
            json.dump(raw, f)

        st3 = save.load(self.path)
        self.assertEqual(st3.surface.soil, {})
        self.assertEqual(st3.donated, set())
        self.assertEqual(st3.seen_events, set())
        self.assertEqual(st3.player.status, {})
        self.assertTrue(all(p["state"] == "open" for p in st3.projects))
        beast = next(a for a in st3.surface.animals if a.name == "RoundTrip")
        self.assertEqual(beast.sick, 0)
        plot = st3.surface.crops.get((51, 50))
        self.assertIsNotNone(plot)
        self.assertEqual((plot.thirst, plot.fertilized), (0, False))


class TestBackupRecovery(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.gettempdir(), "hd_test_recover.json")

    def tearDown(self):
        for suffix in ("", ".bak", ".broken", ".tmp"):
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass

    def test_rolling_backup_holds_the_previous_save(self):
        from hearthdelve.engine import save
        st = fresh_state(5)
        st.player.gold = 111
        save.save(st, self.path)                 # first write: no backup yet
        self.assertFalse(os.path.isfile(self.path + ".bak"))
        st.player.gold = 222
        save.save(st, self.path)                 # second write: .bak = the 111 save
        self.assertEqual(save.load(self.path).player.gold, 222)
        self.assertEqual(save.load(self.path + ".bak").player.gold, 111)

    def test_corrupt_main_restores_the_backup(self):
        from hearthdelve.engine import save
        st = fresh_state(5)
        st.player.gold = 111
        save.save(st, self.path)
        st.player.gold = 222
        save.save(st, self.path)
        with open(self.path, "w") as f:
            f.write("{ this is not json")        # the main save corrupts
        st2, restored = save.load_or_backup(self.path)
        self.assertTrue(restored)
        self.assertEqual(st2.player.gold, 111)   # yesterday morning survives
        self.assertTrue(os.path.isfile(self.path + ".broken"))
        # and the promoted main is a normal, loadable save again
        self.assertEqual(save.load(self.path).player.gold, 111)

    def test_healthy_save_never_touches_the_backup(self):
        from hearthdelve.engine import save
        st = fresh_state(5)
        st.player.gold = 333
        save.save(st, self.path)
        st2, restored = save.load_or_backup(self.path)
        self.assertFalse(restored)
        self.assertEqual(st2.player.gold, 333)

    def test_corrupt_with_no_backup_still_raises(self):
        from hearthdelve.engine import save
        with open(self.path, "w") as f:
            f.write("not a save at all")
        with self.assertRaises(Exception):
            save.load_or_backup(self.path)


class TestTheSuiteNeverTouchesARealSave(unittest.TestCase):
    """Advancing the day autosaves. The suite used to write that autosave over
    the developer's own farm, because the path was frozen into default
    arguments at import time where no test could redirect it."""

    def test_the_default_path_is_the_suites_scratch_file(self):
        from hearthdelve.engine import save
        here = save.default_path()
        self.assertNotEqual(os.path.abspath(here), os.path.abspath(save.SAVE_PATH))
        self.assertTrue(os.path.abspath(here).startswith(
            os.path.abspath(tempfile.gettempdir())))

    def test_the_path_is_resolved_at_call_time(self):
        from unittest import mock
        from hearthdelve.engine import save
        elsewhere = os.path.join(tempfile.mkdtemp(prefix="hd-elsewhere-"), "s.json")
        st = fresh_state(5)
        with mock.patch.dict(os.environ, {"HEARTHDELVE_SAVE": elsewhere}):
            save.save(st)
            self.assertTrue(save.exists())
            self.assertEqual(save.load().seed, 5)
            save.delete()
            self.assertFalse(os.path.isfile(elsewhere))

    def test_the_dawn_autosave_lands_in_the_scratch_file(self):
        from hearthdelve.engine import save
        from hearthdelve.game import farming

        def stamp(p):
            return os.stat(p).st_mtime_ns if os.path.isfile(p) else None
        real = (stamp(save.SAVE_PATH), stamp(save.SAVE_PATH + ".bak"))
        save.delete()
        st = fresh_state(5)
        farming.new_day(st)
        self.assertTrue(os.path.isfile(save.default_path()))
        self.assertEqual(save.load().day, st.day)
        self.assertEqual((stamp(save.SAVE_PATH), stamp(save.SAVE_PATH + ".bak")), real)


class TestTodaysFloorsSurviveASave(unittest.TestCase):
    """Dungeon floors lived only in memory: a save made below put the player at
    the mouth and the next load rolled every floor afresh — opened chests full
    again, slain monsters back — and quitting was a free escape from a losing
    fight. Today's floors are now saved, and a save made below resumes there."""

    def setUp(self):
        from hearthdelve.engine import save
        save.delete()

    def _below(self):
        import numpy as np
        from hearthdelve.game import delve
        from hearthdelve.world import tile
        st = fresh_state(1)
        mouth = sorted(p for p, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        f1 = st.world
        chest = next(zip(*np.nonzero(f1.tiles == tile.CHEST)))
        f1.tiles[chest] = f1.floor_tile                    # loot a chest
        f1.monsters.pop(0)                                 # slay one
        f1.monsters[0].hp, f1.monsters[0].awake = 1, True  # and wound another
        delve.descend(st)
        return st, mouth, f1, chest

    def test_a_save_made_below_resumes_on_the_same_floor(self):
        import numpy as np
        from hearthdelve.engine import save
        st, mouth, _f1, _chest = self._below()
        st.player.x, st.player.y = st.world.stairs_up[0], st.world.stairs_up[1]
        here = st.world
        save.save(st)
        again = save.load()
        self.assertEqual((again.depth, again.dungeon_kind), (2, "mine"))
        self.assertTrue(again.world.is_dungeon)
        self.assertEqual((again.player.x, again.player.y), (st.player.x, st.player.y))
        self.assertTrue(np.array_equal(again.world.tiles, here.tiles))
        self.assertEqual(again.return_pos, mouth)          # and the way out is the way in
        self.assertTrue(again.world.visible[again.player.x, again.player.y])

    def test_a_looted_floor_stays_looted_after_a_reload(self):
        import numpy as np
        from hearthdelve.engine import save
        from hearthdelve.game import delve
        from hearthdelve.world import tile
        st, mouth, f1, chest = self._below()
        save.save(st)
        again = save.load()
        g1 = again.floor_cache[("mine", ("vale", *mouth), 1)]
        self.assertTrue(np.array_equal(g1.explored, f1.explored))   # the map you'd drawn
        delve.ascend(again)                                # back up to floor 1
        self.assertIs(again.world, g1)
        self.assertNotEqual(g1.tiles[chest], tile.CHEST)   # the chest is still empty
        self.assertTrue(np.array_equal(g1.tiles, f1.tiles))
        self.assertEqual(g1.hidden_traps, f1.hidden_traps)
        self.assertEqual([(m.name, m.hp, m.x, m.y, m.awake, m.elite, m.base, m.boss)
                          for m in g1.monsters],
                         [(m.name, m.hp, m.x, m.y, m.awake, m.elite, m.base, m.boss)
                          for m in f1.monsters])

    def test_yesterdays_floors_are_not_kept(self):
        from hearthdelve.engine import save
        from hearthdelve.game import delve
        st, _mouth, _f1, _chest = self._below()
        delve.leave_to_surface(st)
        st.day += 1                                        # a new dawn re-rolls them
        save.save(st)
        again = save.load()
        self.assertEqual(again.floor_cache, {})
        self.assertEqual(again.depth, 0)

    def test_an_older_save_wakes_at_the_mouth(self):
        import json
        from hearthdelve.engine import save
        st, mouth, _f1, _chest = self._below()
        save.save(st)
        with open(save.default_path()) as f:
            raw = json.load(f)
        raw.pop("delve")
        for rec in raw["wildlife"]:
            del rec[23:]                                   # and the shorter monster record
        with open(save.default_path(), "w") as f:
            json.dump(raw, f)
        again = save.load()
        self.assertEqual(again.depth, 0)
        self.assertFalse(again.world.is_dungeon)
        self.assertEqual((again.player.x, again.player.y), mouth)
        self.assertEqual(again.floor_cache, {})



def _lived_in():
    """A state that has been played a little: a crop, a beast, claimed and
    tilled ground, starred goods and gear, the chest, a letter with a gift,
    friendships, a finished project and a night's sleep behind it."""
    import random
    from hearthdelve.data import content
    from hearthdelve.entities import items
    from hearthdelve.entities.animal import Animal
    from hearthdelve.game import farming, husbandry, land, projects
    from hearthdelve.world import tile
    from hearthdelve.world.crops import CropPlot
    random.seed(1)
    st = fresh_state(3)
    p = st.player
    p.gold, p.status = 777, {"poison": 3}
    st.donated, st.seen_events = {"Ruby", "Chamomile"}, {"Hollis:4"}
    st.surface.soil[(50, 50)] = 3
    st.surface.crops[(51, 50)] = CropPlot(crop=content.CROPS[0], days_grown=1, thirst=2,
                                          fertilized=True)
    spec = husbandry.SPECIES["chicken"]
    st.surface.animals.append(Animal(kind="chicken", name="RoundTrip", glyph=spec.glyph,
                                     color=spec.color, x=52, y=50, home=(52, 50),
                                     age_days=9, happiness=64))
    for xy in ((400, 400), (401, 400)):
        st.surface.tiles[xy] = tile.TILLED
    land.claim(st, [(400, 400), (401, 400)])
    p.inventory.add(items.PANACEA, 2)
    p.inventory.add(items.HONEY, 3, quality=4)
    p.inventory.add(content.make_gear("Armour", "steel", gems=("topaz",)), 1)
    st.storage.add(items.WOOD, 30)
    st.mail.append({"sender": "Ivo", "body": "For you.", "items": [(items.HONEY, 1, 2)],
                    "until": 9})
    for n in st.surface.npcs[:5]:
        n.friendship += 250
        n.met = True
    projects.get(st, "shrine")["state"] = "done"
    farming.new_day(st)
    return st


class TestEveryFieldSurvivesASave(unittest.TestCase):
    """The save is hand-written field by field, so a field added to the game
    and forgotten in save.py is lost on reload with nothing to say so. Every
    field of GameState must be classed here as saved or deliberately not,
    and every saved one must come back exactly as it was — down through the
    villagers, beasts, crops and maps it holds."""

    NOT_SAVED = {
        "log",          # the message history starts afresh with each session
        "cheats",       # the hidden cheat menu's toggles are a session's play
        "cam_focus",    # where Look or aim mode points the camera
        "warned",       # "press again to take it" warnings, for this sitting
        "aim_target",   # the aim cursor
    }
    # Rebuilt from the world on demand, so never saved.
    CACHES = {"_owner_cache", "route"}

    def _differences(self, a, b, path="", depth=0):
        import dataclasses
        import numpy as np
        from hearthdelve.entities import items
        if a is b or depth > 8:
            return []
        if isinstance(a, items.Item) and isinstance(b, str):      # a letter's gift, by name
            return [] if a.name == b else [path]
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            ok = (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)
                  and a.shape == b.shape and np.array_equal(a, b))
            return [] if ok else [path]
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            if len(a) != len(b):
                return [f"{path} (length {len(a)} -> {len(b)})"]
            return [d for i, (u, v) in enumerate(zip(a, b))
                    for d in self._differences(u, v, f"{path}[{i}]", depth + 1)]
        if type(a) is not type(b):
            return [f"{path} ({type(a).__name__} -> {type(b).__name__})"]
        if isinstance(a, dict):
            if set(map(repr, a)) != set(map(repr, b)):
                return [f"{path} (keys)"]
            bk = {repr(k): v for k, v in b.items()}
            return [d for k, v in a.items()
                    for d in self._differences(v, bk[repr(k)], f"{path}[{k!r}]", depth + 1)]
        if dataclasses.is_dataclass(a) and type(a).__dataclass_params__.frozen:
            return [] if a == b else [path]
        if hasattr(a, "__dict__") and type(a).__module__.startswith("hearthdelve."):
            return [d for k in sorted(set(vars(a)) | set(vars(b))) if k not in self.CACHES
                    for d in self._differences(getattr(a, k, None), getattr(b, k, None),
                                               f"{path}.{k}", depth + 1)]
        return [] if a == b else [path]

    def test_every_field_is_classed(self):
        import dataclasses
        from hearthdelve.engine import save
        from hearthdelve.game.state import GameState
        src = open(save.__file__).read()
        for f in dataclasses.fields(GameState):
            with self.subTest(field=f.name):
                if f.name not in self.NOT_SAVED:
                    self.assertIn(f"state.{f.name}", src,
                                  f"GameState.{f.name} is never saved — save it, or class "
                                  "it as NOT_SAVED here if it's meant to be lost")

    def test_a_lived_in_game_comes_back_exactly(self):
        import dataclasses
        from hearthdelve.engine import save
        from hearthdelve.game.state import GameState
        st = _lived_in()
        save.save(st)
        again = save.load()
        for f in dataclasses.fields(GameState):
            if f.name in self.NOT_SAVED:
                continue
            with self.subTest(field=f.name):
                self.assertEqual(self._differences(getattr(st, f.name), getattr(again, f.name),
                                                   f.name), [])

    def test_save_load_save_writes_the_same_file(self):
        from hearthdelve.engine import save
        save.save(_lived_in())
        with open(save.default_path()) as f:
            first = f.read()
        save.save(save.load())
        with open(save.default_path()) as f:
            self.assertEqual(f.read(), first, "something was lost or changed on the way through")


if __name__ == "__main__":
    unittest.main()
