"""The animation engine: one engine for everything that moves on screen."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _con():
    return tcod.console.Console(80, 50, order="F")


class TestOneEngine(unittest.TestCase):
    """The view's animations were written straight into the renderer's
    drawing functions. They now all run through the engine, layer by layer;
    the renderer only calls the layers at their places."""

    def test_a_frame_runs_every_layer_in_order(self):
        from unittest import mock
        from hearthdelve.engine import anim, rendering
        seen = []
        real = anim.run
        with mock.patch.object(anim, "run", side_effect=lambda layer, f: (seen.append(layer),
                                                                          real(layer, f))):
            rendering.render_all(_con(), fresh_state(2), 1.5)
        self.assertEqual(seen, list(anim.LAYERS))

    def test_every_ambient_animation_is_an_engine_effect(self):
        from hearthdelve.engine import anim
        from hearthdelve.engine import rendering  # noqa: F401  (registers the effects)
        names = {layer: [fn.__name__ for _o, fn in anim._ONGOING[layer]] for layer in anim.LAYERS}
        self.assertEqual(names[anim.SHADE], ["cloud_shadows"])
        self.assertEqual(names[anim.TINT], ["wind", "water_shimmer", "ore_twinkle",
                                            "campfire_flicker"])
        self.assertEqual(names[anim.GROUND], ["coastal_foam", "rain_on_the_ground"])
        self.assertEqual(names[anim.GROUND_LATE], ["gem_glitter", "lava_breathes"])
        self.assertEqual(names[anim.VEIL], ["westreach_weather"])
        self.assertEqual(names[anim.OVERLAY], ["weather", "shooting_stars", "fish_rising",
                                               "seasonal_motes",
                                               "living_fire", "festival_bunting", "crossings",
                                               "fireworks",
                                               "songs_at_the_inn", "chatter", "underground_life",
                                               "afflictions"])

    def test_effects_in_a_layer_draw_lowest_order_first(self):
        from hearthdelve.engine import anim
        drawn = []
        try:
            anim.ongoing(anim.OVERLAY, 1001)(lambda f: drawn.append("second"))
            anim.ongoing(anim.OVERLAY, 1000)(lambda f: drawn.append("first"))
            from hearthdelve.engine import rendering
            rendering.render_all(_con(), fresh_state(2), 0.0)
        finally:
            anim._ONGOING[anim.OVERLAY][:] = [e for e in anim._ONGOING[anim.OVERLAY]
                                              if e[0] < 1000]
        self.assertEqual(drawn, ["first", "second"])

    def test_no_effect_redefines_another_s_name(self):
        """effects.py is one module of many effects: a second top-level
        `_WATER_IDS = ...` (fish rising's own table) silently replaced the
        shimmer's, foam's and puddles' list of water tiles, and grass and
        meadow rolled like the sea."""
        import ast
        import collections
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent
               / "hearthdelve" / "engine" / "effects.py").read_text(encoding="utf-8")
        names = collections.Counter()
        for node in ast.parse(src).body:
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(node, ast.AnnAssign) else [])
            names.update(t.id for t in targets if isinstance(t, ast.Name))
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names[node.name] += 1
        self.assertEqual([n for n, c in names.items() if c > 1], [])

    def test_the_water_list_stays_the_water_tiles_after_frames_play(self):
        import numpy as np
        from hearthdelve.engine import effects
        from hearthdelve.world import tile
        for k in range(3):
            _render(fresh_state(2), k * 0.4)
        self.assertEqual(sorted(np.asarray(effects._WATER_IDS).tolist()), sorted([tile.WATER, tile.RIVER]))

    def test_the_game_never_imports_drawing_code(self):
        """Game logic records what happens; it never reaches for the screen."""
        import pathlib
        import re
        root = pathlib.Path(__file__).resolve().parent.parent / "hearthdelve" / "game"
        drawing = re.compile(r"(engine\s+import\s+.*\b(rendering|anim|effects|screens_render|ui)\b"
                             r"|engine\.(rendering|anim|effects|screens_render|ui)\b"
                             r"|import\s+tcod\.(console|context))")   # (tcod.map is field of view)
        offenders = [f"{p.name}:{n}" for p in sorted(root.glob("*.py"))
                     for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                     if drawing.search(line)]
        self.assertEqual(offenders, [])



class TestOneOffEffects(unittest.TestCase):
    """Things that happen are recorded by the game (state.happen, never
    saved) and played by the engine for their short life, then dropped."""

    def setUp(self):
        from hearthdelve.engine import anim
        self.drawn = []
        anim.one_off("probe", life=1.0)(lambda f, h, age: self.drawn.append(round(age, 2)))
        self.st = fresh_state(2)

    def tearDown(self):
        from hearthdelve.engine import anim
        anim._ONE_OFFS.pop("probe", None)

    def _frame(self, t):
        from hearthdelve.engine import rendering
        rendering.render_all(_con(), self.st, t)

    def test_it_plays_from_the_frame_it_first_shows_on_then_goes(self):
        p = self.st.player
        self.st.happen("probe", p.x, p.y)
        for t in (10.0, 10.5, 10.99, 11.2, 12.0):
            self._frame(t)
        self.assertEqual(self.drawn, [0.0, 0.5, 0.99])
        self.assertEqual(self.st.fx, [])

    def test_a_happening_long_past_when_the_screen_gets_to_it_never_shows(self):
        p = self.st.player
        self.st.happen("probe", p.x, p.y)
        self.st.clock += 60 * 60                     # an hour's rest went by unseen
        self._frame(5.0)
        self.assertEqual(self.drawn, [])
        self.assertEqual(self.st.fx, [])

    def test_it_shows_only_on_the_map_it_happened_on(self):
        from hearthdelve.game import delve
        p = self.st.player
        mouth = sorted(q for q, k in self.st.surface.dungeon_kind.items() if k == "mine")[0]
        p.x, p.y = mouth
        self.st.happen("probe", p.x, p.y)            # on the surface…
        delve.enter(self.st, "mine")                 # …then straight down the stairs
        self._frame(1.0)
        self.assertEqual(self.drawn, [])

    def test_the_record_stays_short_with_no_screen_to_play_it(self):
        from hearthdelve.game import state as gs
        for i in range(gs.MAX_HAPPENINGS + 30):
            self.st.happen("probe", i, 0)
        self.assertEqual(len(self.st.fx), gs.MAX_HAPPENINGS)
        self.assertEqual(self.st.fx[-1].x, gs.MAX_HAPPENINGS + 29)



def _clear_line(st, reach):
    """A direction from the player with `reach` open, walkable cells in a row."""
    p, w = st.player, st.world
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if all(w.walkable(p.x + dx * k, p.y + dy * k) for k in range(1, reach + 1)):
            return dx, dy
    raise AssertionError("boxed in")


def _foe_beside(st, hp=99, reach=3):
    """A target `reach` cells off in a clear straight line from the player."""
    from hearthdelve.entities.monster import Mob
    p = st.player
    dx, dy = _clear_line(st, reach + 3)
    foe = Mob("Target", "T", (200, 200, 200), hp, hp, 1, "chase",
              p.x + dx * reach, p.y + dy * reach, dv=0, pv=0)
    st.world.monsters.append(foe)
    return foe


class TestAHitShows(unittest.TestCase):
    """A blow landing was only a log line. Now the struck cell flashes and the
    damage floats up from it."""

    def _strike(self, crit=False):
        from unittest import mock
        from hearthdelve.game import combat
        st = fresh_state(2)
        foe = _foe_beside(st)
        with mock.patch.object(combat, "_resolve", return_value=(17, crit)):
            combat.player_attack(st, foe)
        return st, foe

    def _cells(self, st, t):
        from hearthdelve.engine import rendering
        con = _con()
        rendering.render_all(con, st, t)
        return con

    def test_the_blow_is_recorded_with_its_damage(self):
        st, foe = self._strike(crit=True)
        (h,) = [h for h in st.fx if h.kind == "hit"]
        self.assertEqual((h.x, h.y, h.data["amount"], h.data["crit"], h.data["on"]),
                         (foe.x, foe.y, 17, True, "foe"))

    def test_the_number_floats_up_from_the_struck_cell(self):
        from hearthdelve.engine import rendering
        st, foe = self._strike()
        ox, oy = rendering.camera_origin(st)
        sx, sy = foe.x - ox, foe.y - oy
        plain = self._cells(fresh_state(2), 50.0)
        first = self._cells(st, 50.0)
        text = "".join(chr(first.ch[x, sy - 1]) for x in (sx - 1, sx))
        self.assertEqual(text, "17")
        self.assertNotEqual(tuple(first.bg[sx, sy]), tuple(plain.bg[sx, sy]))   # the flash
        later = self._cells(st, 50.7)                  # two rows higher by now
        self.assertEqual("".join(chr(later.ch[x, sy - 3]) for x in (sx - 1, sx)), "17")

    def test_your_own_wounds_show_red(self):
        from unittest import mock
        from hearthdelve.engine import rendering
        from hearthdelve.game import combat
        st = fresh_state(2)
        foe = _foe_beside(st)
        with mock.patch.object(combat, "_resolve", return_value=(6, False)):
            combat._attack_player(st, foe)
        ox, oy = rendering.camera_origin(st)
        con = self._cells(st, 3.0)
        px, py = st.player.x - ox, st.player.y - oy
        self.assertEqual(chr(con.ch[px, py - 1]), "6")
        r, g, b = con.fg[px, py - 1]
        self.assertGreater(int(r), int(g) + 80)

    def test_a_blow_out_of_sight_underground_shows_nothing(self):
        from hearthdelve.engine import anim
        from hearthdelve.game import delve
        st = fresh_state(2)
        mouth = sorted(q for q, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        w = st.world
        dark = next((x, y) for x in range(w.width) for y in range(w.height)
                    if not w.visible[x, y] and abs(x - st.player.x) < 20
                    and abs(y - st.player.y) < 15)
        f = anim.Frame(con=_con(), state=st, t=0.0, ox=st.player.x - 29, oy=st.player.y - 22,
                       vw=58, vh=44, daylight=(1.0, 1.0, 1.0))
        self.assertIsNone(f.cell(*dark))



class TestAKillCrumbles(unittest.TestCase):
    """A slain monster vanished the instant it died, the hit's flash playing
    over an empty cell. Now it slumps into a heap and crumbles to dust."""

    def _kill(self):
        from unittest import mock
        from hearthdelve.game import combat
        st = fresh_state(2)
        foe = _foe_beside(st, hp=5, reach=1)
        with mock.patch.object(combat, "_resolve", return_value=(9, False)):
            combat.player_attack(st, foe)
        self.assertNotIn(foe, st.world.monsters)
        return st, foe

    def test_the_fall_is_recorded_with_what_fell(self):
        st, foe = self._kill()
        (h,) = [h for h in st.fx if h.kind == "slain"]
        self.assertEqual((h.x, h.y, h.data["glyph"]), (foe.x, foe.y, "T"))

    def test_it_stands_a_beat_then_slumps_and_crumbles(self):
        st, foe = self._kill()
        at = _screen(st, foe.x, foe.y)
        seen = [chr(_render(st, 30.0 + t).ch[at]) for t in (0.0, 0.3, 0.6, 0.9)]
        self.assertEqual(seen, ["T", "%", ",", "·"])
        self.assertNotIn(chr(_render(st, 31.2).ch[at]), "T%,")       # gone


class TestAMissSwishesPast(unittest.TestCase):
    """A swing that went wide showed nothing, and a shot that streaked past
    stopped dead at its target. Now a swish sweeps round the far side of
    whoever dodged, and a missed arrow flies on."""

    def test_your_miss_swishes_past_the_foe(self):
        from unittest import mock
        from hearthdelve.game import combat
        st = fresh_state(2)
        foe = _foe_beside(st, reach=1)
        with mock.patch.object(combat, "_resolve", return_value=None):
            combat.player_attack(st, foe)
        (h,) = [h for h in st.fx if h.kind == "miss"]
        p = st.player
        way = (foe.x - p.x, foe.y - p.y)
        self.assertEqual((h.x, h.y, tuple(h.data["way"])), (foe.x, foe.y, way))
        swept = set()
        for t in (0.0, 0.1, 0.2, 0.3):
            con = _render(st, 40.0 + t)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    at = _screen(st, foe.x + way[0] + dx * (way[1] != 0),
                                 foe.y + way[1] + dy * (way[0] != 0))
                    if chr(con.ch[at]) == "~":
                        swept.add(at)
        self.assertEqual(len(swept), 3)                    # it swept the far side

    def test_a_dodged_lunge_swishes_past_you(self):
        from unittest import mock
        from hearthdelve.game import combat
        st = fresh_state(2)
        foe = _foe_beside(st, reach=1)
        with mock.patch.object(combat, "_resolve", return_value=None):
            combat._attack_player(st, foe)
        (h,) = [h for h in st.fx if h.kind == "miss"]
        self.assertEqual((h.x, h.y), (st.player.x, st.player.y))

    def test_a_missed_arrow_flies_on(self):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = fresh_state(2)
        st.player.equipment["ranged"] = content.make_ranged("Short Bow", "birch")
        st.player.inventory.add(items.ARROW, 5)
        foe = _foe_beside(st, reach=4)
        with mock.patch.object(combat, "_resolve", return_value=None):
            combat.fire_ranged_at(st, foe.x, foe.y)
        on = [h for h in st.fx if h.kind == "shot" and (h.x, h.y) == (foe.x, foe.y)]
        self.assertEqual(len(on), 1)
        self.assertGreater(len(on[0].data["path"]), 0)
        first = next(h for h in st.fx if h.kind == "shot" and h is not on[0])
        self.assertAlmostEqual(on[0].data["delay"], len(first.data["path"]) * first.data["per"])


class TestWoundsShow(unittest.TestCase):
    """Poison, bleeding and burns showed only as a tag in the panel. Now they
    show on whoever has them."""

    def _player_cell(self, kinds, t):
        st = fresh_state(2)
        for k in kinds:
            st.player.status[k] = 3
        con = _render(st, t)
        at = _screen(st, st.player.x, st.player.y)
        return st, con, at

    def test_the_poisoned_pulse_green(self):
        _s, sick, at = self._player_cell(["poison"], 2.0)
        _s, well, _a = self._player_cell([], 2.0)
        g = lambda c: int(c.fg[at][1]) - (int(c.fg[at][0]) + int(c.fg[at][2])) // 2
        self.assertGreater(g(sick), g(well) + 25)

    def test_the_bleeding_drip(self):
        st, _c, (sx, sy) = self._player_cell(["bleed"], 0.0)
        drips = 0
        for k in range(40):
            con = _render(st, k * 0.1)
            drips += chr(con.ch[sx, sy + 1]) == "," and con.fg[sx, sy + 1][0] > 120
        self.assertGreater(drips, 5)

    def test_the_burning_smoulder(self):
        _s, hot, at = self._player_cell(["burn"], 2.0)
        _s, cool, _a = self._player_cell([], 2.0)
        warm = lambda c: int(c.bg[at][0]) - int(c.bg[at][2])
        self.assertGreater(warm(hot), warm(cool) + 20)

    def test_a_creature_you_envenomed_shows_it_too(self):
        st = fresh_state(2)
        foe = _foe_beside(st, reach=2)
        at = _screen(st, foe.x, foe.y)
        plain = _render(st, 2.0).fg[at].astype(int)
        foe.status["poison"] = 3
        tinted = _render(st, 2.0).fg[at].astype(int)
        self.assertGreater(tinted[1] - tinted[0], plain[1] - plain[0] + 25)


class TestALevelGainedShows(unittest.TestCase):
    """A skill or character level gained was a log line. Now a ring of light
    spreads from you and the new level lifts off you."""

    def _row_text(self, con, y):
        return "".join(chr(c) for c in con.ch[:58, y])

    def test_a_skill_level_lifts_off_you(self):
        from hearthdelve.game import skills
        st = fresh_state(2)
        st.player.skills["Farming"] = 0
        skills.gain(st, "Farming", skills.XP_PER_LEVEL * 2)
        h = next(h for h in st.fx if h.kind == "level_up")
        level = skills.skill_level(st, "Farming")
        self.assertEqual(h.data["text"], f"Farming {level}")
        sx, sy = _screen(st, st.player.x, st.player.y)
        con = _render(st, 50.0)
        self.assertIn(f"Farming {level}", self._row_text(con, sy - 2))

    def test_a_ring_spreads_from_you(self):
        from hearthdelve.game import skills
        st = fresh_state(2)
        skills.gain(st, "Mining", skills.XP_PER_LEVEL * 2)
        sx, sy = _screen(st, st.player.x, st.player.y)
        _render(st, 50.0)
        con = _render(st, 50.25)
        plain = _render(fresh_state(2), 50.25)
        ring = sum(chr(con.ch[x, y]) == "*" and chr(plain.ch[x, y]) != "*"
                   for x in range(sx - 8, sx + 9) for y in range(sy - 6, sy + 7))
        self.assertGreater(ring, 8)

    def test_your_own_level_waits_its_turn_behind_a_skill(self):
        from hearthdelve.game import skills
        st = fresh_state(2)
        st.player.xp = skills.xp_to_next(st.player.level) - 1
        skills.gain(st, "Combat", skills.XP_PER_LEVEL * 2)
        ups = [h for h in st.fx if h.kind == "level_up"]
        self.assertEqual(len(ups), 2)
        self.assertTrue(ups[1].data["text"].startswith("Level "))
        self.assertGreater(ups[1].data["delay"], ups[0].data["delay"])


class TestAHeartWonShows(unittest.TestCase):
    """A heart won with a villager went by unremarked. Now hearts burst out
    around them, whatever won it — and every source of friendship goes
    through the one place that notices."""

    def _villager(self, st):
        p = st.player
        npc = st.surface.npcs[0]
        dx, dy = _clear_line(st, 4)
        npc.x, npc.y = p.x + dx * 3, p.y + dy * 3
        return npc

    def test_a_gift_that_wins_a_heart_bursts_into_hearts(self):
        from hearthdelve.game import village
        st = fresh_state(2)
        npc = self._villager(st)
        npc.friendship = 299
        village.befriend(st, npc, 5)
        (h,) = [h for h in st.fx if h.kind == "hearts"]
        self.assertEqual((h.x, h.y, h.data["hearts"]), (npc.x, npc.y, 3))
        _render(st, 60.0)
        con = _render(st, 60.4)
        sx, sy = _screen(st, npc.x, npc.y)
        around = sum(chr(con.ch[x, y]) == "♥" for x in range(sx - 6, sx + 7)
                     for y in range(sy - 4, sy + 4))
        self.assertGreaterEqual(around, 5)

    def test_a_dwarf_s_heart_shows_in_khazgrim(self):
        """The burst only ever showed on the surface, so a heart won with one of
        Khazgrim's dwarves never showed at all."""
        from hearthdelve.data import content
        from hearthdelve.game import village
        from hearthdelve.world import dwarftown
        st = fresh_state(2)
        st.dwarves = content.dwarf_npcs()
        st.world = dwarftown.generate(st.seed, st.dwarves)
        dwarf = st.dwarves[0]
        dwarf.friendship = 299
        village.befriend(st, dwarf, 5)
        self.assertEqual([(h.x, h.y) for h in st.fx if h.kind == "hearts"], [(dwarf.x, dwarf.y)])

    def test_a_villager_s_heart_won_while_you_re_below_doesnt_show_there(self):
        from hearthdelve.game import delve, village
        st = fresh_state(2)
        mouth = sorted(q for q, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        npc = st.surface.npcs[0]
        npc.friendship = 299
        village.befriend(st, npc, 5)
        self.assertEqual([h for h in st.fx if h.kind == "hearts"], [])

    def test_points_within_a_heart_dont_burst(self):
        from hearthdelve.game import village
        st = fresh_state(2)
        npc = self._villager(st)
        npc.friendship = 210
        village.befriend(st, npc, 30)
        village.befriend(st, npc, -100)
        self.assertEqual([h for h in st.fx if h.kind == "hearts"], [])

    def test_every_friendship_gain_goes_through_befriend(self):
        """So none of them can win a heart without it showing."""
        import pathlib
        import re
        root = pathlib.Path(__file__).resolve().parent.parent / "hearthdelve" / "game"
        raw = re.compile(r"\.friendship\s*=\s*min\(")
        offenders = [f"{p.name}:{n}" for p in sorted(root.glob("*.py"))
                     for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                     if raw.search(line)]
        self.assertEqual(offenders, [])


class TestGainsHopIntoYourPack(unittest.TestCase):
    """What you gathered went into your pack unseen, with at most a log line.
    Now it hops from where it came into you, and a "+2 Wood" lifts off you."""

    def _ripe_crop(self, st):
        from hearthdelve.data import content
        from hearthdelve.world import tile
        from hearthdelve.world.crops import CropPlot
        p = st.player
        dx, dy = _clear_line(st, 2)
        pos = (p.x + dx, p.y + dy)
        st.world.tiles[pos] = tile.TILLED
        crop = next(c for c in content.CROPS if c.season == st.season)
        st.world.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature, watered=True)
        p.facing = (dx, dy)
        return pos, crop

    def _label_row(self, con, st):
        sx, sy = _screen(st, st.player.x, st.player.y)
        return " ".join("".join(chr(c) for c in con.ch[max(0, sx - 12):sx + 13, y])
                        for y in range(sy - 3, sy))

    def test_a_harvest_hops_into_your_pack(self):
        from hearthdelve.game import commands
        st = fresh_state(2)
        pos, crop = self._ripe_crop(st)
        commands.do_grab(st)
        (h,) = [h for h in st.fx if h.kind == "pickup"]
        self.assertEqual((h.x, h.y, h.data["name"]), (*pos, crop.produce.name))
        n = h.data["qty"]
        _render(st, 70.0)
        self.assertIn(f"+{n} {crop.produce.name}", self._label_row(_render(st, 70.5), st))

    def test_a_kill_s_drops_hop_from_where_it_fell(self):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = fresh_state(2)
        foe = _foe_beside(st, hp=3, reach=1)
        with mock.patch.object(combat, "_resolve", return_value=(9, False)), \
                mock.patch.object(content, "monster_drops", return_value=[items.COAL, items.COAL]):
            combat.player_attack(st, foe)
        (h,) = [h for h in st.fx if h.kind == "pickup"]
        self.assertEqual((h.x, h.y, h.data["name"], h.data["qty"]), (foe.x, foe.y, "Coal", 2))

    def test_several_gains_follow_one_another_up(self):
        from hearthdelve.entities import items
        st = fresh_state(2)
        p = st.player
        with st.noting_gains([(p.x + 1, p.y)]):
            p.inventory.add(items.WOOD, 2)
            p.inventory.add(items.STONE, 1)
        delays = [h.data["delay"] for h in st.fx if h.kind == "pickup"]
        self.assertEqual(len(delays), 2)
        self.assertLess(delays[0], delays[1])

    def test_what_you_give_up_isnt_shown_as_a_gain(self):
        from hearthdelve.entities import items
        st = fresh_state(2)
        p = st.player
        p.inventory.add(items.WOOD, 5)
        with st.noting_gains([(p.x, p.y)]):
            p.inventory.remove(items.WOOD, 3)
        self.assertEqual([h for h in st.fx if h.kind == "pickup"], [])


class TestFishRise(unittest.TestCase):
    """Open water lay still between casts, telling you nothing. Now fish rise
    on it now and then — as often as a cast there would find one."""

    def _pond(self):
        from hearthdelve.world import tile
        st = fresh_state(2)
        st.weather = "Clear"
        p = st.player
        for x in range(p.x - 20, p.x + 21):
            for y in range(p.y - 15, p.y + 16):
                if max(abs(x - p.x), abs(y - p.y)) > 3:
                    st.world.tiles[x, y] = tile.WATER
        return st

    def _rises(self, st, seconds=30.0):
        from hearthdelve.world import tile
        n = 0
        for k in range(int(seconds / 0.25)):
            con = _render(st, k * 0.25)
            ox, oy = _screen(st, 0, 0)
            for x in range(58):
                for y in range(44):
                    wx, wy = x - ox, y - oy
                    if (st.world.tiles[wx, wy] == tile.WATER             # (water's own
                            and chr(con.ch[x, y]) in "o°"):               #  glyph is ≈)
                        n += 1
        return n

    def test_fish_rise_on_open_water(self):
        self.assertGreater(self._rises(self._pond()), 10)

    def test_none_rise_where_none_bite(self):
        from unittest import mock
        from hearthdelve.game import fishing
        st = self._pond()
        with mock.patch.object(fishing, "bite_odds", return_value=(0.9, [])):
            self.assertEqual(self._rises(st), 0)

    def test_a_cast_reads_the_same_odds(self):
        from unittest import mock
        from hearthdelve.game import fishing
        st = self._pond()
        p = st.player
        with mock.patch.object(fishing, "bite_odds", return_value=(0.0, [])):
            ctx = fishing.begin(st, p.x + 5, p.y)
        self.assertFalse(ctx["bite"])


class TestVillagersChat(unittest.TestCase):
    """Villagers stood side by side in silence. Now, now and then, one says
    something and the other answers."""

    def _pair(self, apart=1, hour=11):
        from hearthdelve.engine import constants as C
        st = fresh_state(2)
        st.clock = (hour * 60 - C.DAY_START_MIN) * 60
        p = st.player
        dx, dy = _clear_line(st, 4)
        a, b = st.surface.npcs[0], st.surface.npcs[1]
        a.x, a.y = p.x + dx * 2 + dy, p.y + dy * 2 + dx
        b.x, b.y = a.x + dx * apart, a.y + dy * apart
        return st, a, b

    def _said_over(self, st, npc, seconds=40.0):
        sx, sy = _screen(st, npc.x, npc.y)
        return {chr(_render(st, k * 0.2).ch[sx, sy - 1]) for k in range(int(seconds / 0.2))} & set("…?!♪")

    def test_two_together_take_turns(self):
        st, a, b = self._pair()
        self.assertTrue(self._said_over(st, a))
        self.assertTrue(self._said_over(st, b))

    def test_two_far_apart_say_nothing(self):
        st, a, b = self._pair(apart=5)
        self.assertEqual(self._said_over(st, a), set())

    def test_nothing_in_the_small_hours(self):
        st, a, b = self._pair(hour=2)
        self.assertEqual(self._said_over(st, a), set())


class TestFestivalSquaresAreDressed(unittest.TestCase):
    """A festival or a fete changed nothing you could see on the square. Now
    bunting runs between its lamp posts, and lanterns hang lit after dark."""

    def _at_square(self, day, hour=11, village=None):
        from hearthdelve.engine import constants as C
        st = fresh_state(2)
        st.day = day
        st.clock = (hour * 60 - C.DAY_START_MIN) * 60
        st.weather = "Clear"
        name, (vx, vy) = village or sorted(st.surface.village_centers.items())[0]
        st.player.x, st.player.y = vx, vy + 5
        return st, (vx, vy)

    def _flags(self, st, centre, t=1.0):
        vx, vy = centre
        con = _render(st, t)
        cells = [_screen(st, x, y) for x in range(vx - 3, vx + 4) for y in (vy - 2, vy + 2)]
        return sum(chr(con.ch[c]) in "▼▾" for c in cells), con, cells

    def _festival_day(self):
        from hearthdelve.data import content
        from hearthdelve.engine import constants as C
        season, fests = next((s, f) for s, f in content.FESTIVALS.items() if f)
        return C.SEASONS.index(season) * C.SEASON_LEN + fests[0][0] - 1

    def test_a_festival_hangs_bunting_on_the_square(self):
        st, centre = self._at_square(self._festival_day())
        self.assertGreater(self._flags(st, centre)[0], 4)

    def test_an_ordinary_day_doesnt(self):
        st, centre = self._at_square(self._festival_day() + 2)
        self.assertEqual(self._flags(st, centre)[0], 0)

    def test_the_lanterns_are_lit_after_dark(self):
        st, centre = self._at_square(self._festival_day(), hour=21)
        _n, con, cells = self._flags(st, centre)
        self.assertTrue(any(chr(con.ch[c]) in "o☻" for c in cells))

    def test_a_fete_dresses_its_own_square_from_noon_on_the_eve(self):
        from unittest import mock
        from hearthdelve.game import events
        st, _c = self._at_square(self._festival_day() + 2, hour=15)
        name = events.fete_village(st, st.day + 1)
        centre = st.surface.village_centers[name]
        st.player.x, st.player.y = centre[0], centre[1] + 5
        with mock.patch.object(events, "peek_tomorrow", return_value="fete"):
            self.assertGreater(self._flags(st, centre)[0], 4)
            other = next(c for n, c in st.surface.village_centers.items() if n != name)
            st.player.x, st.player.y = other[0], other[1] + 5
            self.assertEqual(self._flags(st, other)[0], 0)

    def test_the_eve_s_village_is_the_one_that_keeps_the_fete(self):
        import random
        from hearthdelve.game import events
        st = fresh_state(2)
        foretold = events.fete_village(st, st.day)
        st.event = {"id": "fete"}
        events._apply_fete(st, random.Random(0))
        self.assertEqual(st.event["village"], foretold)


class TestShootingStars(unittest.TestCase):
    """The night sky was still — even on a starfall's eve, when the old folk
    tell you to watch it after dark. Now a star falls now and then on a clear
    night, and they shower down on that eve."""

    def _streaks(self, weather="Clear", eve=False, hour=23, seconds=120.0):
        from unittest import mock
        from hearthdelve.engine import constants as C
        from hearthdelve.game import events
        st = fresh_state(2)
        st.weather = weather
        st.clock = (hour * 60 - C.DAY_START_MIN) * 60
        heads = 0
        with mock.patch.object(events, "peek_tomorrow", return_value="starfall" if eve else ""):
            for k in range(int(seconds / 0.1)):
                con = _render(st, k * 0.1)
                for x in range(58):
                    for y in range(44):
                        if chr(con.ch[x, y]) == "*" and min(con.fg[x, y]) > 200:
                            heads += 1
        return heads

    def test_a_clear_night_has_its_falling_stars(self):
        self.assertGreater(self._streaks(), 0)

    def test_a_starfall_eve_showers_them(self):
        self.assertGreater(self._streaks(eve=True), 4 * max(1, self._streaks()))

    def test_none_by_day_or_under_cloud(self):
        self.assertEqual(self._streaks(hour=13, eve=True, seconds=30.0), 0)
        self.assertEqual(self._streaks(weather="Cloudy", eve=True, seconds=30.0), 0)


class TestTheDeepIsntStill(unittest.TestCase):
    """Underground nothing moved but you and what hunts you. Now water drips
    in damp caves and mines, a bat flits by now and then, and a bomb shakes
    dust down from the roof."""

    def _below(self, kind="mine"):
        from hearthdelve.game import delve
        st = fresh_state(2)
        mouth = sorted(q for q, k in st.surface.dungeon_kind.items() if k == kind)[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, kind)
        st.fx.clear()
        st.world.monsters.clear()
        return st

    def _count(self, st, glyphs, colour_test, seconds):
        n = 0
        for k in range(int(seconds / 0.1)):
            con = _render(st, k * 0.1)
            for x in range(58):
                for y in range(44):
                    if chr(con.ch[x, y]) in glyphs and colour_test(con.fg[x, y]):
                        n += 1
        return n

    def test_water_drips_in_a_mine(self):
        st = self._below("mine")
        bluish = lambda c: int(c[2]) > int(c[0]) + 25 and int(c[2]) > 120
        self.assertGreater(self._count(st, "'°", bluish, 20.0), 5)

    def test_not_in_a_dry_crypt(self):
        st = self._below("crypt")
        bluish = lambda c: int(c[2]) > int(c[0]) + 25 and int(c[2]) > 120
        self.assertEqual(self._count(st, "'°", bluish, 20.0), 0)

    def test_a_bat_flits_by_now_and_then(self):
        st = self._below("mine")
        dark = lambda c: tuple(int(v) for v in c) == (92, 84, 104)
        self.assertGreater(self._count(st, "v^", dark, 150.0), 0)

    def test_a_bomb_below_shakes_dust_down(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = self._below("mine")
        st.player.inventory.add(items.BOMB, 1)
        p = st.player
        tx, ty = next((x, y) for x in range(p.x - 3, p.x + 4) for y in range(p.y - 3, p.y + 4)
                      if st.world.walkable(x, y) and max(abs(x - p.x), abs(y - p.y)) >= 2)
        combat.throw_bomb_at(st, tx, ty)
        self.assertIn("dust", [h.kind for h in st.fx])

    def test_a_bomb_in_the_open_doesnt(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = fresh_state(2)
        st.player.inventory.add(items.BOMB, 1)
        foe = _foe_beside(st, reach=3)
        combat.throw_bomb_at(st, foe.x, foe.y)
        self.assertNotIn("dust", [h.kind for h in st.fx])


class TestAMonsterNoticesYou(unittest.TestCase):
    """A monster waking showed only as it starting to move. Now a "!" shows
    over it the moment it sees you."""

    def _below(self):
        from hearthdelve.game import delve
        st = fresh_state(2)
        mouth = sorted(q for q, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        st.fx.clear()                                  # (the way down has its own effect)
        return st

    def test_it_shows_over_a_monster_that_sees_you(self):
        from hearthdelve.engine import rendering
        from hearthdelve.game import combat
        st = self._below()
        w, p = st.world, st.player
        spot = next((x, y) for x in range(p.x - 4, p.x + 5) for y in range(p.y - 4, p.y + 5)
                    if (x, y) != (p.x, p.y) and w.walkable(x, y) and w.visible[x, y]
                    and abs(x - p.x) > 1)
        foe = _foe_beside(st)
        foe.x, foe.y, foe.awake = spot[0], spot[1], False
        w.monsters[:] = [foe]
        combat.monsters_act(st)
        self.assertTrue(foe.awake)
        self.assertEqual([h.kind for h in st.fx], ["wake"])
        con = _con()
        rendering.render_all(con, st, 2.0)
        ox, oy = rendering.camera_origin(st)
        self.assertEqual(chr(con.ch[spot[0] - ox, spot[1] - oy - 1]), "!")

    def test_one_already_awake_doesnt_announce_itself_again(self):
        from hearthdelve.game import combat
        st = self._below()
        foe = _foe_beside(st)
        foe.awake = True
        st.world.monsters[:] = [foe]
        combat.monsters_act(st)
        self.assertEqual([h for h in st.fx if h.kind == "wake"], [])



class TestAHarvestSparkles(unittest.TestCase):
    """A harvest showed only as a log line. Now it bursts into sparks coloured
    by the crop's stars."""

    def _sparks(self, quality):
        from hearthdelve.engine import effects, rendering
        st = fresh_state(2)
        p = st.player
        st.happen("harvest", p.x + 2, p.y, quality=quality)
        con = _con()
        rendering.render_all(con, st, 7.0)            # it starts…
        rendering.render_all(con, st, 7.3)            # …and 0.3 s in, the burst is open
        before = _con()
        plain = fresh_state(2)
        rendering.render_all(before, plain, 7.3)
        ox, oy = rendering.camera_origin(st)
        sx, sy = p.x + 2 - ox, p.y - oy
        changed = [(x, y) for x in range(sx - 4, sx + 5) for y in range(sy - 3, sy + 4)
                   if 0 <= x < 58 and 0 <= y < 44
                   and (con.ch[x, y] != before.ch[x, y]
                        or tuple(con.fg[x, y]) != tuple(before.fg[x, y]))]
        colours = {tuple(int(c) for c in con.fg[x, y]) for x, y in changed}
        return changed, colours, effects._QUALITY_SPARK

    def test_a_harvest_is_recorded_with_its_quality(self):
        from hearthdelve.game import farming
        from hearthdelve.world.crops import CropPlot
        from hearthdelve.data import content
        st = fresh_state(2)
        crop = content.CROPS[0]
        x, y = st.player.x + 1, st.player.y
        st.surface.crops[(x, y)] = CropPlot(crop=crop, days_grown=crop.days_to_mature)
        farming.harvest(st, x, y)
        (h,) = [h for h in st.fx if h.kind == "harvest"]
        self.assertEqual((h.x, h.y), (x, y))
        self.assertIn(h.data["quality"], range(6))

    def test_the_sparks_take_the_crops_colour(self):
        for q in (0, 3):
            changed, colours, palette = self._sparks(q)
            with self.subTest(stars=q):
                self.assertGreaterEqual(len(changed), 3)
                self.assertIn(palette[q], colours)

    def test_finer_crops_throw_more_sparks(self):
        self.assertGreater(len(self._sparks(4)[0]), len(self._sparks(0)[0]))



def _render(st, t):
    from hearthdelve.engine import rendering
    con = _con()
    rendering.render_all(con, st, t)
    return con


def _screen(st, x, y):
    from hearthdelve.engine import rendering
    ox, oy = rendering.camera_origin(st)
    return x - ox, y - oy


class TestShotsFly(unittest.TestCase):
    """A shot struck at once and showed nothing between bow and target. Now
    the arrow flies its line, and its hit lands when it arrives."""

    def _loose(self):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = fresh_state(2)
        st.player.equipment["ranged"] = content.make_ranged("Short Bow", "birch")
        st.player.inventory.add(items.ARROW, 5)
        foe = _foe_beside(st, reach=6)                  # six cells off, in a straight line
        with mock.patch.object(combat, "_resolve", return_value=(5, False)):
            self.assertTrue(combat.fire_ranged_at(st, foe.x, foe.y))
        return st, foe

    def test_the_arrow_flies_and_its_hit_waits_for_it(self):
        st, foe = self._loose()
        shot = next(h for h in st.fx if h.kind == "shot")
        hit = next(h for h in st.fx if h.kind == "hit")
        self.assertEqual(shot.data["path"][-1], (foe.x, foe.y))
        self.assertAlmostEqual(hit.data["delay"], len(shot.data["path"]) * shot.data["per"])

    def test_on_screen_the_arrow_is_on_its_way_before_the_number(self):
        st, foe = self._loose()
        p = st.player
        early = _render(st, 20.0)                         # 0 s: the first cell out
        dx, dy = (foe.x - p.x) // 6, (foe.y - p.y) // 6
        x1, y1 = _screen(st, p.x + dx, p.y + dy)
        self.assertEqual(chr(early.ch[x1, y1]), "-" if dx else "|")
        fx, fy = _screen(st, foe.x, foe.y)
        self.assertNotEqual(chr(early.ch[fx, fy - 1]), "5")   # no hit yet
        later = _render(st, 20.25)                        # landed by now
        self.assertEqual(chr(later.ch[fx, fy - 1]), "5")


class TestMonstersShotsFly(unittest.TestCase):
    """A spore spitter's shot struck you at once, with nothing in the air, and
    one that went wide was only a log line. Now its glob flies across to you
    and the hit waits for it; a miss flies on past."""

    def _spat(self, lands):
        from unittest import mock
        from hearthdelve.game import combat
        from hearthdelve.world import tile
        st = fresh_state(2)
        foe = _foe_beside(st, reach=4)
        foe.reach, foe.color = 4, (150, 200, 130)
        p = st.player
        dx, dy = (foe.x - p.x) // 4, (foe.y - p.y) // 4
        for k in (1, 2, 3):                              # open ground behind you
            st.world.tiles[p.x - dx * k, p.y - dy * k] = tile.GRASS
        with mock.patch.object(combat, "_resolve", return_value=(6, False) if lands else None):
            combat._ranged_attack(st, foe)
        shot = next(h for h in st.fx if h.kind == "shot")
        return st, foe, shot

    def test_its_glob_flies_from_it_to_you_and_the_hit_waits(self):
        st, foe, shot = self._spat(lands=True)
        p = st.player
        self.assertEqual((shot.x, shot.y), (foe.x, foe.y))
        self.assertEqual(shot.data["path"][-1], (p.x, p.y))
        hit = next(h for h in st.fx if h.kind == "hit")
        self.assertAlmostEqual(hit.data["delay"], len(shot.data["path"]) * shot.data["per"])
        first = shot.data["path"][0]
        con = _render(st, 20.0)
        self.assertEqual(chr(con.ch[_screen(st, *first)]), "°")

    def test_a_miss_flies_on_past_you(self):
        st, foe, shot = self._spat(lands=False)
        p = st.player
        self.assertIn((p.x, p.y), shot.data["path"])
        self.assertNotEqual(shot.data["path"][-1], (p.x, p.y))       # carried on beyond
        self.assertEqual([h for h in st.fx if h.kind == "hit"], [])


class TestBombsBlow(unittest.TestCase):
    """A bomb went off as a log line. Now it arcs out, then a flash and a
    ring of fire, the view jolts, and the damage it did floats up."""

    def _throw(self):
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        st = fresh_state(2)
        st.player.inventory.add(items.BOMB, 1)
        foe = _foe_beside(st)
        self.assertTrue(combat.throw_bomb_at(st, foe.x, foe.y))
        return st, foe

    def test_the_blast_shake_and_hits_wait_for_the_bomb_to_land(self):
        st, foe = self._throw()
        kinds = [h.kind for h in st.fx]
        self.assertEqual(kinds[:4], ["lob", "blast", "shake", "hit"])
        flight = next(h for h in st.fx if h.kind == "lob").data["life"] - 0.04
        for h in st.fx[1:]:
            with self.subTest(kind=h.kind):
                self.assertAlmostEqual(h.data["delay"], flight)

    def test_the_blast_lights_the_ground_and_the_view_jolts(self):
        st, foe = self._throw()
        flight = next(h for h in st.fx if h.kind == "lob").data["life"] - 0.04
        _render(st, 50.0)
        con = _render(st, 50.0 + flight + 0.01)          # the moment it goes off
        calm = _render(fresh_state(2), 50.0 + flight + 0.01)
        moved = int((con.ch[:58, :44] != calm.ch[:58, :44]).sum())
        self.assertGreater(moved, 200)                    # the whole view jolted aside



class TestWorkShows(unittest.TestCase):
    """Felling a tree or breaking rock played out over a few frames with
    nothing moving but the clock. Now chips fly, a pip fills, and a felled
    tree crashes over."""

    def _chop(self):
        from hearthdelve import screens
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        from hearthdelve.world import tile
        st = fresh_state(2)
        p = st.player
        dx, dy = _clear_line(st, 4)
        st.world.tiles[p.x + dx, p.y + dy] = tile.TREE_OAK
        p.facing = (dx, dy)
        p.hotbar[p.active_slot] = items.AXE
        ui = screens.UI(st)
        busy = commands.use_tool(st)
        self.assertIsInstance(busy, dict)
        ui.play.busy_ctx = busy
        while ui.play.busy_ctx is not None:
            ui.play.tick(ui)
        return st, (p.x + dx, p.y + dy), (dx, dy)

    def test_each_beat_of_work_is_recorded_with_its_progress(self):
        st, spot, _away = self._chop()
        done = [h.data["done"] for h in st.fx if h.kind == "strike"]
        self.assertGreater(len(done), 2)
        self.assertEqual(done, sorted(done))
        self.assertEqual(done[-1], 1.0)

    def test_the_tree_goes_over_away_from_you(self):
        st, spot, away = self._chop()
        (fell,) = [h for h in st.fx if h.kind == "fell"]
        self.assertEqual(((fell.x, fell.y), fell.data["away"]), (spot, away))
        for h in st.fx:                                  # show only the fall
            h.start = None
        st.fx[:] = [fell]
        _render(st, 30.0)
        late = _render(st, 30.5)                          # lying where it fell
        sx, sy = _screen(st, *spot)
        lying = "".join(chr(late.ch[sx + away[0] * k, sy + away[1] * k]) for k in (1, 2))
        self.assertEqual(lying, ("═" if away[0] else "║") * 2)

    def test_watering_a_crop_is_recorded(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        from hearthdelve.world.crops import CropPlot
        st = fresh_state(2)
        p = st.player
        dx, dy = _clear_line(st, 2)
        x, y = p.x + dx, p.y + dy
        st.world.crops[(x, y)] = CropPlot(crop=content.CROPS[0])
        p.facing = (dx, dy)
        p.hotbar[p.active_slot] = items.WATERING_CAN
        commands.use_tool(st)
        self.assertEqual([(h.kind, h.x, h.y, h.data.get("crop")) for h in st.fx],
                         [("water", x, y, True)])



class TestCreaturesShowHowTheyFeel(unittest.TestCase):
    """Petting an animal, or a gift going down well or badly, were log lines.
    Now a ♥ (or an "…") rises off them; ready produce glints; and the inn has
    song in it of an evening."""

    def test_a_petted_animal_shows_a_heart(self):
        from hearthdelve.entities.animal import Animal
        from hearthdelve.game import husbandry
        st = fresh_state(2)
        spec = husbandry.SPECIES["chicken"]
        p = st.player
        hen = Animal(kind="chicken", name="Hen", glyph=spec.glyph, color=spec.color,
                     x=p.x + 2, y=p.y, home=(p.x, p.y), age_days=30, happiness=50)
        st.surface.animals.append(hen)
        husbandry.interact_animal(st, hen)
        con = _render(st, 4.0)
        sx, sy = _screen(st, hen.x, hen.y)
        self.assertEqual(chr(con.ch[sx, sy - 1]), "♥")

    def test_a_gift_shows_whether_it_landed(self):
        from hearthdelve.game import village
        st = fresh_state(2)
        npc = next(n for n in st.surface.npcs if n.loves and n.dislikes)
        st.player.inventory.add(npc.loves[0], 1)
        village.gift(st, npc, npc.loves[0])
        st.player.inventory.add(npc.dislikes[0], 1)
        npc.gifted_today = False
        village.gift(st, npc, npc.dislikes[0])
        self.assertEqual([h.data["glyph"] for h in st.fx if h.kind == "emote"], ["♥", "…"])

    def test_ready_produce_glints_on_its_own_beat(self):
        from hearthdelve.engine import anim
        beats = {tuple(anim.ready_glint(k * 0.05, x, 7) for k in range(40)) for x in range(6)}
        self.assertGreater(len(beats), 1)

    def test_the_inn_sings_of_an_evening(self):
        from hearthdelve.engine import anim
        from hearthdelve.engine import constants as C
        st = fresh_state(2)
        st.clock = (20 * 60 - C.DAY_START_MIN) * 60          # 20:00
        regulars = [n for n in st.surface.npcs if n.spots.get("inn")][:3]
        for n in regulars:
            n.x, n.y = n.spots["inn"]
        st.player.x, st.player.y = regulars[0].x, regulars[0].y + 3
        notes = 0
        for k in range(0, 600):
            con = _render(st, k * 0.1)
            notes += int((con.ch[:58, :44] == ord("♪")).sum() > 0)
        self.assertGreater(notes, 20)                     # now and then…
        self.assertLess(notes, 560)                       # …not all the time



class TestFishingShows(unittest.TestCase):
    """The reel opened the instant you cast and the rest was log lines. Now
    the float sits bobbing on the water a moment first; a bite jerks it under
    with a "!", then the reel opens; a cast nothing takes is reeled in empty;
    a fish that slips the hook splashes, and a landed one leaps to you."""

    def _water_beside(self, st):
        from hearthdelve.world import tile
        p = st.player
        dx, dy = _clear_line(st, 3)
        st.world.tiles[p.x + dx * 2, p.y + dy * 2] = tile.WATER
        return p.x + dx * 2, p.y + dy * 2

    def _cast(self, bites):
        from unittest import mock
        from hearthdelve import screens
        from hearthdelve.game import fishing
        st = fresh_state(2)
        x, y = self._water_beside(st)
        with mock.patch.object(fishing.random, "random", return_value=0.0 if bites else 0.999):
            ctx = fishing.begin(st, x, y)
        ui = screens.UI(st)
        ui.push(screens.CastScreen(ctx))
        return st, ui, ctx, (x, y)

    def test_the_float_bobs_on_the_water_while_you_wait(self):
        st, _ui, ctx, (x, y) = self._cast(bites=True)
        (h,) = [h for h in st.fx if h.kind == "float"]
        self.assertEqual(((h.x, h.y), h.data["life"]), ((x, y), ctx["wait"]))
        self.assertGreaterEqual(ctx["wait"], 0.9)
        sx, sy = _screen(st, x, y)
        glyphs = {chr(_render(st, 5.0 + k * 0.2).ch[sx, sy]) for k in range(5)}
        self.assertEqual(glyphs, {"o", "°"})           # riding up, dipping

    def test_a_bite_shows_then_the_reel_opens(self):
        from hearthdelve import screens
        st, ui, ctx, (x, y) = self._cast(bites=True)
        cast = ui.top
        cast.tick(ui)                                   # still waiting
        self.assertIs(ui.top, cast)
        self.assertNotIn("bite", [h.kind for h in st.fx])
        cast.t0 -= ctx["wait"] + 0.05                   # the wait runs out (with room to
        cast.tick(ui)                                   #  spare: Windows' clock is coarse)
        self.assertIn("bite", [h.kind for h in st.fx])
        self.assertIs(ui.top, cast)                     # the "!" has its moment…
        cast.bit_at -= cast.BITE_BEAT + 0.05
        cast.tick(ui)
        self.assertIsInstance(ui.top, screens.FishingScreen)   # …then the reel

    def test_a_cast_nothing_takes_is_reeled_in_empty(self):
        st, ui, ctx, _at = self._cast(bites=False)
        self.assertFalse(ctx["bite"])
        energy = st.player.energy
        ui.top.t0 -= ctx["wait"] + 0.05
        ui.top.tick(ui)
        self.assertIs(ui.top, ui.play)
        self.assertLess(st.player.energy, energy)
        self.assertIn("nothing's biting", st.log.messages[-1][0])

    def test_you_can_draw_the_line_in_early(self):
        st, ui, ctx, _at = self._cast(bites=True)
        ui.top.handle(ui, "cancel", ("cancel",))
        self.assertIs(ui.top, ui.play)
        self.assertEqual([h for h in st.fx if h.kind in ("float", "bite")], [])

    def test_the_reel_ends_in_a_splash_or_a_catch(self):
        from hearthdelve.game import fishing
        st, _ui, ctx, (x, y) = self._cast(bites=True)
        self.assertEqual(ctx["at"], (x, y))
        st.fx.clear()
        fishing.resolve(st, ctx, caught=False)
        fishing.resolve(st, ctx, caught=True)
        self.assertEqual([h.kind for h in st.fx], ["splash", "catch", "pickup"])
        self.assertEqual(st.fx[1].data["glyph"], ctx["fish"].glyph)
        self.assertEqual(st.fx[2].data["name"], ctx["fish"].name)       # "+1 Trout" follows it
        self.assertFalse(st.fx[2].data["hop"])                          # the leap already carried it


class TestTransitions(unittest.TestCase):
    """Taking the stairs, waking from sleep and coming round from a faint all
    cut straight to the new scene. Now each comes in."""

    def _dark(self, con, rows):
        return float(con.bg[:58, rows].astype(int).sum() + con.fg[:58, rows].astype(int).sum())

    def test_the_stairs_come_out_of_the_dark_around_you(self):
        """The new floor shows first where you stand and spreads outward. (It
        once wiped in from the top of the view — underground, where the top is
        unexplored black, that read as nothing but a blink of darkness.)"""
        import numpy as np
        from hearthdelve.engine import constants as C
        from hearthdelve.game import delve
        st = fresh_state(2)
        mouth = sorted(q for q, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        st.fx[:] = [h for h in st.fx if h.kind == "stairs"]
        self.assertEqual(len(st.fx), 1)
        sx, sy = _screen(st, st.player.x, st.player.y)
        X = np.arange(C.VIEW_W)[:, None]
        Y = np.arange(C.VIEW_H)[None, :]
        far = np.sqrt(((X - sx) * 0.6) ** 2 + (Y - sy) ** 2) > 3.5      # beyond a few steps

        def lit(con, where):
            return int(con.bg[:C.VIEW_W, :C.VIEW_H][where].astype(int).sum()
                       + con.fg[:C.VIEW_W, :C.VIEW_H][where].astype(int).sum())
        first = _render(st, 3.0)                       # the moment you arrive
        early = _render(st, 3.1)
        settled = _render(st, 3.6)
        self.assertEqual(lit(first, np.ones_like(far)), 0)
        self.assertGreater(int(early.fg[sx, sy].astype(int).sum()), 0)       # you, first
        self.assertEqual(lit(early, far), 0)                                  # the rest still dark
        self.assertGreater(lit(settled, far), 0)

    def test_a_night_s_sleep_ends_in_a_card_naming_the_day(self):
        from hearthdelve.game import farming
        st = fresh_state(2)
        farming.sleep(st)
        self.assertIn("dawn", [h.kind for h in st.fx])
        st.fx[:] = [h for h in st.fx if h.kind == "dawn"]
        _render(st, 1.0)
        con = _render(st, 2.0)
        text = " ".join("".join(chr(c) for c in con.ch[:58, y]) for y in range(44))
        self.assertIn(f"{st.date_str()}, Year {st.year}", text)

    def test_coming_round_from_a_faint_swims_red_at_the_edges(self):
        from hearthdelve.game import farming
        st = fresh_state(2)
        farming.collapse(st, "You collapse.")
        st.fx[:] = [h for h in st.fx if h.kind == "faint"]
        self.assertEqual(len(st.fx), 1)
        con = _render(st, 1.0)
        calm = fresh_state(2)
        calm.day, calm.clock = st.day, st.clock
        plain = _render(calm, 1.0)
        corner = con.bg[:4, :4].astype(int)
        plain_corner = plain.bg[:4, :4].astype(int)
        self.assertGreater((corner[..., 0] - corner[..., 2]).mean(),
                           (plain_corner[..., 0] - plain_corner[..., 2]).mean())

    def test_the_whole_view_swims_as_you_come_round(self):
        """Only the corners reddened, too faintly to notice: at first the
        middle of the view swims too."""
        from hearthdelve.game import farming
        st = fresh_state(2)
        farming.collapse(st, "You collapse.")
        st.fx[:] = [h for h in st.fx if h.kind == "faint"]
        sx, sy = _screen(st, st.player.x, st.player.y)
        near = (sx + 1, sy) if sx + 1 < 58 else (sx - 1, sy)
        swim = _render(st, 1.0).bg[near].astype(int)
        st.fx.clear()
        calm = _render(st, 1.0).bg[near].astype(int)
        self.assertGreater(swim[0] - swim[2], calm[0] - calm[2] + 8)



class TestTheGoldRuns(unittest.TestCase):
    """The panel's gold jumped to a new amount. Now it runs there, green as it
    rises and red as it falls, and settles in a moment."""

    def _gold(self, con):
        row = "".join(chr(c) for c in con.ch[58:, 11]).strip()
        return int(row.split()[-1].rstrip("g")), tuple(int(c) for c in con.fg[60, 11])

    def test_it_runs_up_to_a_sale_and_settles(self):
        from hearthdelve.engine import constants as C
        st = fresh_state(2)
        st.player.gold = 100
        self.assertEqual(self._gold(_render(st, 10.0))[0], 100)
        st.player.gold = 1100                              # the bin paid out
        seen = [self._gold(_render(st, 10.0 + k * 0.1)) for k in range(8)]
        amounts = [a for a, _c in seen]
        self.assertEqual(amounts[0], 100)
        self.assertTrue(100 < amounts[2] < 1100)
        self.assertEqual(amounts, sorted(amounts))
        self.assertEqual(amounts[-1], 1100)
        self.assertNotEqual(seen[2][1], tuple(C.GOLD_COLOR))   # tinted while it runs
        self.assertEqual(seen[-1][1], tuple(C.GOLD_COLOR))

    def test_spending_runs_it_down_in_red(self):
        st = fresh_state(2)
        st.player.gold = 500
        _render(st, 1.0)
        st.player.gold = 200
        _render(st, 1.1)                                    # the frame that sees it spent
        amount, (r, g, _b) = self._gold(_render(st, 1.25))
        self.assertTrue(200 < amount < 500)
        self.assertGreater(r, g)



class TestFireworksNight(unittest.TestCase):
    """Filling the year's fireworks order paid out as a log line. Now the sky
    over the closing night actually lights up."""

    def _night(self, filled):
        from hearthdelve.engine import constants as C
        from hearthdelve.game.requests import _year_finale
        st = fresh_state(2)
        season, day, _name = _year_finale()
        st.day = C.SEASONS.index(season) * C.SEASON_LEN + day - 1
        st.clock = (20 * 60 - C.DAY_START_MIN) * 60       # (before the shooting stars come out)
        st.weather = "Clear"
        if filled:
            st.stats[f"fireworks_{st.year}"] = 2
        colours = set()
        for k in range(120):
            con = _render(st, k * 0.1)
            for x in range(58):
                for y in range(22):
                    if chr(con.ch[x, y]) == "*":
                        colours.add(tuple(int(c) for c in con.fg[x, y]))
        return colours

    def test_the_sky_bursts_in_colour_when_the_order_was_filled(self):
        self.assertGreaterEqual(len(self._night(filled=True)), 3)

    def test_no_show_without_the_order(self):
        self.assertEqual(self._night(filled=False), set())

    def test_the_show_keeps_going(self):
        """It was one small burst every few seconds, the sky dark between:
        now launchers overlap, so the night is rarely without a burst."""
        from hearthdelve.engine import constants as C
        from hearthdelve.game.requests import _year_finale
        st = fresh_state(2)
        season, day, _name = _year_finale()
        st.day = C.SEASONS.index(season) * C.SEASON_LEN + day - 1
        st.clock = (21 * 60 - C.DAY_START_MIN) * 60
        st.weather = "Clear"
        st.stats[f"fireworks_{st.year}"] = 2
        lit = 0
        for k in range(120):
            con = _render(st, k * 0.1)
            lit += sum(chr(c) in "*'" for c in con.ch[:58, :44].flat) >= 8
        self.assertGreater(lit, 80)



class TestFootprints(unittest.TestCase):
    """Walking left no trace. Now sand, and snow-covered ground in winter,
    take a footprint that fills in over a few seconds."""

    def _walk(self, ground, day):
        from hearthdelve.game import commands
        from hearthdelve.world import tile
        st = fresh_state(2)
        st.day = day
        p = st.player
        dx, dy = _clear_line(st, 4)
        for k in range(1, 4):
            st.world.tiles[p.x + dx * k, p.y + dy * k] = ground
        start = (p.x, p.y)
        for _ in range(3):
            commands.try_move(st, dx, dy)
        return st, start, (dx, dy)

    def test_sand_takes_prints_behind_you(self):
        from hearthdelve.world import tile
        st, start, (dx, dy) = self._walk(tile.SAND, day=5)
        steps = [(h.x, h.y) for h in st.fx if h.kind == "step"]
        self.assertEqual(steps, [(start[0] + dx * k, start[1] + dy * k) for k in (1, 2, 3)])
        con = _render(st, 1.0)
        sx, sy = _screen(st, start[0] + dx, start[1] + dy)      # behind you now
        self.assertEqual(chr(con.ch[sx, sy]), "∙")

    def test_a_print_is_a_dent_you_can_see(self):
        """It only darkened the dot's colour, which vanished in the sand's
        texture: the cell itself now darkens, and fills back in."""
        from hearthdelve.world import tile
        st, start, (dx, dy) = self._walk(tile.SAND, day=5)
        sx, sy = _screen(st, start[0] + dx, start[1] + dy)
        printed = _render(st, 1.0).bg[sx, sy].astype(int).sum()
        st.fx.clear()
        plain = _render(st, 1.0).bg[sx, sy].astype(int).sum()
        self.assertLess(printed, plain * 0.85)

    def test_snow_takes_them_in_winter_and_grass_doesnt_in_summer(self):
        from hearthdelve.engine import constants as C
        from hearthdelve.world import tile
        winter = 3 * C.SEASON_LEN + 4
        st, _s, _d = self._walk(tile.GRASS, day=winter)
        self.assertEqual(len([h for h in st.fx if h.kind == "step"]), 3)
        st, _s, _d = self._walk(tile.GRASS, day=C.SEASON_LEN + 4)
        self.assertEqual([h for h in st.fx if h.kind == "step"], [])


if __name__ == "__main__":
    unittest.main()
