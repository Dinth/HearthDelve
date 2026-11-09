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
        self.assertEqual(names[anim.OVERLAY], ["weather", "seasonal_motes", "living_fire",
                                               "crossings", "songs_at_the_inn"])

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
    """A cast and its end were log lines. Now a cast that finds nothing drops
    in with a ripple, a fish that slips the hook splashes, and a landed fish
    leaps out of the water to you."""

    def _water_beside(self, st):
        from hearthdelve.world import tile
        p = st.player
        dx, dy = _clear_line(st, 3)
        st.world.tiles[p.x + dx * 2, p.y + dy * 2] = tile.WATER
        return p.x + dx * 2, p.y + dy * 2

    def test_a_cast_that_finds_nothing_ripples(self):
        from unittest import mock
        from hearthdelve.game import fishing
        st = fresh_state(2)
        x, y = self._water_beside(st)
        with mock.patch.object(fishing.random, "random", return_value=0.999):
            self.assertIsNone(fishing.begin(st, x, y))
        self.assertEqual([(h.kind, h.x, h.y) for h in st.fx], [("plop", x, y)])
        con = _render(st, 9.0)
        sx, sy = _screen(st, x, y)
        self.assertEqual(chr(con.ch[sx, sy]), "o")

    def test_the_reel_ends_in_a_splash_or_a_catch(self):
        from unittest import mock
        from hearthdelve.game import fishing
        st = fresh_state(2)
        x, y = self._water_beside(st)
        with mock.patch.object(fishing.random, "random", return_value=0.0):
            ctx = fishing.begin(st, x, y)
        self.assertEqual(ctx["at"], (x, y))
        fishing.resolve(st, ctx, caught=False)
        fishing.resolve(st, ctx, caught=True)
        self.assertEqual([h.kind for h in st.fx], ["splash", "catch"])
        self.assertEqual(st.fx[1].data["glyph"], ctx["fish"].glyph)



class TestTransitions(unittest.TestCase):
    """Taking the stairs, waking from sleep and coming round from a faint all
    cut straight to the new scene. Now each comes in."""

    def _dark(self, con, rows):
        return float(con.bg[:58, rows].astype(int).sum() + con.fg[:58, rows].astype(int).sum())

    def test_the_stairs_come_out_of_the_dark_from_the_top(self):
        from hearthdelve.game import delve
        st = fresh_state(2)
        mouth = sorted(q for q, k in st.surface.dungeon_kind.items() if k == "mine")[0]
        st.player.x, st.player.y = mouth
        delve.enter(st, "mine")
        st.fx[:] = [h for h in st.fx if h.kind == "stairs"]
        self.assertEqual(len(st.fx), 1)
        _sx, sy = _screen(st, st.player.x, st.player.y)
        first = _render(st, 3.0)                       # the moment you arrive
        mid = _render(st, 3.0 + (sy + 2) * 0.45 / 48)  # the dark's edge at your row
        settled = _render(st, 3.6)
        above, below = slice(sy - 3, sy - 1), slice(sy + 2, sy + 4)   # where your torch reaches
        self.assertEqual(self._dark(first, slice(0, 44)), 0.0)
        self.assertGreater(self._dark(mid, above), 0.0)
        self.assertEqual(self._dark(mid, below), 0.0)              # the bottom still dark
        self.assertGreater(self._dark(settled, below), 0.0)

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


if __name__ == "__main__":
    unittest.main()
