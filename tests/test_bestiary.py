"""The delve information layer: kill record, bestiary & dungeon-site codex."""
from __future__ import annotations

import os
import random
import tempfile
import unittest

import tcod

from tests.common import fresh_state


def _kill(st, mdef, level=2, elite=""):
    from hearthdelve.data import content
    from hearthdelve.game import combat
    mob = content.make_mob(mdef, st.player.x + 1, st.player.y, level, random.Random(1))
    if elite:
        mob.elite = elite
        mob.name = f"{elite} {mob.name}"
    st.world.monsters = [mob]
    combat._on_kill(st, mob)


class TestKillRecord(unittest.TestCase):
    def test_slaying_records_the_base_name(self):
        from hearthdelve.data import content
        from hearthdelve.game import delve
        st = fresh_state(2)
        delve.enter(st, "mine")
        boar = next(m for m in content.MONSTERS if m.name == "Boar")
        _kill(st, boar)
        _kill(st, boar)
        self.assertEqual(st.bestiary.get("Boar"), 2)

    def test_elite_kills_count_under_the_base(self):
        from hearthdelve.data import content
        from hearthdelve.game import delve
        st = fresh_state(2)
        delve.enter(st, "mine")
        boar = next(m for m in content.MONSTERS if m.name == "Boar")
        _kill(st, boar, elite="Dire")            # "Dire Boar" -> base "Boar"
        self.assertEqual(st.bestiary.get("Boar"), 1)
        self.assertNotIn("Dire Boar", st.bestiary)

    def test_peaceful_wildlife_is_not_a_trophy(self):
        from hearthdelve.game import combat
        st = fresh_state(2)
        # a peaceful surface critter: killing it must not add a bestiary tally
        crit = type("W", (), {"name": "Rabbit", "kind": "wildlife", "hostile": False})()
        st.world.monsters = [crit]
        combat._on_kill(st, crit)
        self.assertEqual(st.bestiary, {})

    def test_bestiary_round_trips_and_grandfathers(self):
        from hearthdelve.engine import save
        st = fresh_state(2)
        st.bestiary = {"Cave Slime": 5, "Wraith": 1}
        path = os.path.join(tempfile.gettempdir(), "hd_bestiary_test.json")
        try:
            save.save(st, path)
            self.assertEqual(save.load(path).bestiary, {"Cave Slime": 5, "Wraith": 1})
            import json
            with open(path) as f:
                raw = json.load(f)
            raw.pop("bestiary", None)                 # an old save predating the record
            with open(path, "w") as f:
                json.dump(raw, f)
            self.assertEqual(save.load(path).bestiary, {})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


class TestCodexPages(unittest.TestCase):
    def _pages(self, st):
        from hearthdelve.engine import rendering as R
        return {t: rows for t, rows in R.build_codex_pages(st)}

    def test_bestiary_and_dungeon_pages_exist_and_render(self):
        from hearthdelve.engine import rendering as R
        st = fresh_state(3)
        pages = self._pages(st)
        self.assertIn("Bestiary", pages)
        self.assertIn("Dungeon Sites", pages)
        con = tcod.console.Console(R.C.SCREEN_W, R.C.SCREEN_H, order="F")
        for i in range(len(R.build_codex_pages(st))):
            R.render_codex(con, st, i, 0)            # must not raise

    def test_dungeon_page_covers_every_kind(self):
        from hearthdelve.world import dungeon
        st = fresh_state(3)
        rows = self._pages(st)["Dungeon Sites"]
        text = "\n".join(r[0] for r in rows)
        for name in ("Mines", "Caverns", "Sea Caves", "Crypts", "Dwarfholds"):
            self.assertIn(name, text)

    def test_bestiary_shows_a_kill_tally_once_slain(self):
        from hearthdelve.game import delve
        from hearthdelve.data import content
        st = fresh_state(3)
        delve.enter(st, "mine")
        _kill(st, next(m for m in content.MONSTERS if m.name == "Boar"))
        rows = self._pages(st)["Bestiary"]
        text = "\n".join(r[0] for r in rows)
        self.assertIn("slain 1×", text)

    def test_character_sheet_renders_combat_numbers(self):
        from hearthdelve.engine import rendering as R
        st = fresh_state(3)
        con = tcod.console.Console(R.C.SCREEN_W, R.C.SCREEN_H, order="F")
        R.render_character(con, st)                  # combat block must not raise


if __name__ == "__main__":
    unittest.main()
