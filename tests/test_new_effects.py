"""Eight more things that show: goo, turned earth, a drink, working machines,
a lunge, a spoiled brew, and the farmhouse's furnishings."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _render(st, t=50.0):
    from hearthdelve.engine import rendering
    con = tcod.console.Console(80, 50, order="F")
    rendering.render_all(con, st, t)
    return con


def _cell(st, x, y):
    from hearthdelve.engine import rendering
    ox, oy = rendering.camera_origin(st)
    return x - ox, y - oy


def _differs(a, b, cells) -> bool:
    return any(tuple(a.bg[c]) != tuple(b.bg[c]) or tuple(a.fg[c]) != tuple(b.fg[c])
               or a.ch[c] != b.ch[c] for c in cells)


def _around(c, r=2):
    return [(c[0] + dx, c[1] + dy) for dx in range(-r, r + 1) for dy in range(-r - 2, r + 1)]


def _yard(seed=2):
    """A quiet, clear, bare patch of the Vale at noon, the farmer in the middle."""
    from hearthdelve.world import tile
    st = fresh_state(seed)
    st.weather = "Clear"
    st.clock += 6 * 3600
    st.world.monsters.clear()
    st.fx.clear()
    p = st.player
    p.x, p.y = p.x + 10, p.y + 8
    for dx in range(-6, 7):
        for dy in range(-5, 6):
            pos = (p.x + dx, p.y + dy)
            st.world.tiles[pos] = tile.GRASS
            for d in (st.world.crops, st.world.machines, st.world.trees):
                d.pop(pos, None)
    return st


class TestEveryNewHappeningHasAnEffect(unittest.TestCase):
    def test_they_are_registered(self):
        from hearthdelve.engine import anim, rendering  # noqa: F401
        for kind in ("goo", "till", "sow", "refresh", "lunge", "spoil"):
            with self.subTest(kind=kind):
                self.assertIn(kind, anim._ONE_OFFS)


class TestGoo(unittest.TestCase):
    def _mired(self):
        from tests.test_noise import _below, _open_spot, _sleeper
        from hearthdelve.game import delve
        st = _below()
        p = st.player
        m = _sleeper(st, *_open_spot(st, (p.x, p.y), 2, 3))
        m.awake = True
        delve.update_fov(st)
        return st, m

    def test_a_mired_monster_wears_its_goo(self):
        st, m = self._mired()
        c = _cell(st, m.x, m.y)
        clean = _render(st)
        m.status["mired"] = 9
        slick = _render(st)
        self.assertNotEqual(tuple(slick.bg[c]), tuple(clean.bg[c]))
        self.assertGreater(int(slick.bg[c][1]), int(slick.bg[c][0]))      # green

    def test_a_sticky_bomb_leaves_goo_about_and_a_plain_one_does_not(self):
        from tests.test_noise import _below, _open_spot
        from hearthdelve.entities import items
        from hearthdelve.game import combat
        for bomb, want in ((items.STICKY_BOMB, 1), (items.BOMB, 0)):
            st = _below()
            p = st.player
            st.player.inventory.add(bomb, 1)
            combat.throw_bomb_at(st, *_open_spot(st, (p.x, p.y), 2, 4))
            with self.subTest(bomb=bomb.name):
                self.assertEqual(len([h for h in st.fx if h.kind == "goo"]), want)

    def test_the_spatter_shows_then_soaks_away(self):
        from tests.test_noise import _below, _open_spot
        from hearthdelve.game import delve
        st = _below()
        p = st.player
        x, y = _open_spot(st, (p.x, p.y), 2, 3)
        delve.update_fov(st)
        clean = _render(st)
        st.happen("goo", x, y, radius=1)
        c = _cell(st, x, y)
        wet = _render(st, 50.0)
        wet = _render(st, 50.5)
        self.assertNotEqual(tuple(wet.bg[c]), tuple(clean.bg[c]))
        gone = tuple(_render(st, 53.0).bg[c])            # (torchlight flickers: compare
        st.fx.clear()                                     #  the same instant, goo or none)
        self.assertEqual(gone, tuple(_render(st, 53.0).bg[c]))


class TestTheFieldShowsItsWork(unittest.TestCase):
    def test_a_hoed_tile_throws_up_earth(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = _yard()
        p = st.player
        p.facing = (1, 0)
        p.hotbar[p.active_slot] = items.HOE
        commands.use_tool(st)
        (h,) = [h for h in st.fx if h.kind == "till"]
        self.assertEqual((h.x, h.y), (p.x + 1, p.y))

    def test_a_planted_seed_is_seen_going_in(self):
        from hearthdelve.entities import items
        from hearthdelve.game import farming
        from hearthdelve.world import tile
        st = _yard()
        p = st.player
        spot = (p.x + 2, p.y)
        st.world.tiles[spot] = tile.TILLED
        bare = _render(st)
        p.inventory.add(items.PARSNIP_SEEDS, 1)
        farming.plant(st, *spot, items.PARSNIP_SEEDS)
        self.assertEqual(len([h for h in st.fx if h.kind == "sow"]), 1)
        st.world.crops.pop(spot)                      # judge the effect, not the sprout
        c = _cell(st, *spot)
        self.assertTrue(_differs(_render(st, 50.0), bare, _around(c, 1)))


class TestADrinkShows(unittest.TestCase):
    def test_a_meal_lifts_its_stamina_off_you(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = _yard()
        p = st.player
        p.energy = 10
        p.inventory.add(items.HERBAL_TONIC, 1)
        commands._eat(st, items.HERBAL_TONIC, 0)
        (h,) = [h for h in st.fx if h.kind == "refresh"]
        self.assertEqual(h.data["amount"], items.HERBAL_TONIC.energy)
        self.assertFalse(h.data.get("drink"))
        con = _render(st)
        sx, sy = _cell(st, p.x, p.y)
        text = "".join(chr(con.ch[x, sy - 1]) for x in range(sx - 1, sx + 2))
        self.assertIn("+60", text)

    def test_water_is_marked_as_a_drink(self):
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = _yard()
        st.player.energy = 10
        st.player.inventory.add(items.FULL_WATERSKIN, 1)
        commands._eat(st, items.FULL_WATERSKIN, 0)
        (h,) = [h for h in st.fx if h.kind == "refresh"]
        self.assertTrue(h.data["drink"])

    def test_a_drink_past_thirst_shows_nothing(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import commands
        st = _yard()
        st.stats["drinks_day"], st.stats["drinks"] = st.day, content.DRINKS_PER_DAY
        st.player.inventory.add(items.FULL_WATERSKIN, 1)
        commands._eat(st, items.FULL_WATERSKIN, 0)
        self.assertEqual([h for h in st.fx if h.kind == "refresh"], [])


class TestMachinesShowTheirWork(unittest.TestCase):
    def _machine(self, kind, loaded):
        from hearthdelve.entities import items
        from hearthdelve.entities.machine import Machine
        st = _yard()
        pos = (st.player.x + 3, st.player.y)
        st.world.machines[pos] = Machine(kind=kind)
        idle = _render(st)
        if loaded:
            m = st.world.machines[pos]
            m.loaded_output, m.ready_at = items.COPPER_BAR, st.abs_minutes + 500
        return st, pos, idle

    def test_a_working_furnace_glows(self):
        st, pos, _idle = self._machine("furnace", True)
        c = _cell(st, *pos)
        busy = _render(st)
        m = st.world.machines[pos]
        m.loaded_output = None
        self.assertNotEqual(tuple(busy.bg[c]), tuple(_render(st).bg[c]))
        self.assertGreater(int(busy.bg[c][0]), int(busy.bg[c][2]))        # a fire's colour

    def test_a_finished_one_stops_glowing_and_glints_instead(self):
        st, pos, _idle = self._machine("furnace", True)
        c = _cell(st, *pos)
        busy = tuple(_render(st).bg[c])
        st.world.machines[pos].ready_at = st.abs_minutes - 1
        self.assertNotEqual(tuple(_render(st).bg[c]), busy)

    def test_a_keg_bubbles_now_and_then(self):
        st, pos, _idle = self._machine("keg", True)
        sx, sy = _cell(st, *pos)
        seen = {chr(_render(st, 50.0 + i * 0.1).ch[sx, sy - 1]) for i in range(120)}
        self.assertTrue(seen & {"°", "·"}, seen)


class TestAStrikeShowsWhoStruck(unittest.TestCase):
    def test_the_attacker_flares(self):
        from unittest import mock
        from tests.test_noise import _below, _sleeper
        from hearthdelve.game import combat, delve
        st = _below()
        p = st.player
        p.hp = p.max_hp = 999
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if st.world.walkable(p.x + dx, p.y + dy):
                m = _sleeper(st, p.x + dx, p.y + dy)
                break
        m.awake = True
        delve.update_fov(st)
        calm = _render(st)
        with mock.patch.object(combat, "_resolve", return_value=None):       # a miss still shows
            combat._attack_player(st, m)
        (h,) = [h for h in st.fx if h.kind == "lunge"]
        self.assertEqual((h.x, h.y, h.data["to"]), (m.x, m.y, (p.x, p.y)))
        c = _cell(st, m.x, m.y)
        self.assertNotEqual(tuple(_render(st).bg[c]), tuple(calm.bg[c]))


class TestASpoiledBrewShows(unittest.TestCase):
    def test_the_still_belches(self):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import crafting
        st = _yard()
        pos = (st.player.x + 3, st.player.y)
        m = st.world.machines[pos] = Machine(kind="apothecary")
        for inputs, *_ in content.APOTHECARY_POTIONS:
            for it, q in inputs:
                st.player.inventory.add(it, q)
        opt = next(o for o in crafting.machine_load_options(st, content.MACHINES["apothecary"])
                   if o.get("spoil"))
        with mock.patch("random.random", return_value=0.0):
            crafting.load_machine_choice(st, m, content.MACHINES["apothecary"], opt)
        (h,) = [h for h in st.fx if h.kind == "spoil"]
        self.assertEqual((h.x, h.y), pos)


class TestTheHouseShowsItsFurnishings(unittest.TestCase):
    def _house(self):
        from hearthdelve.game import husbandry
        st = fresh_state(2)
        st.weather = "Clear"
        st.clock += 6 * 3600
        st.world.monsters.clear()
        st.fx.clear()
        bx, by = st.surface.bed
        st.player.x, st.player.y = bx + 2, by + 2
        return st, husbandry.house_rects(st)[0]

    def test_a_bare_house_is_drawn_as_it_always_was(self):
        st, _rect = self._house()
        c = _cell(st, *st.surface.bed)
        self.assertNotEqual(chr(_render(st).ch[c]), "▤")

    def test_the_quilt_lies_on_the_bed(self):
        from hearthdelve.game import home
        st, _rect = self._house()
        st.stats[home.QUILT] = 3
        c = _cell(st, *st.surface.bed)
        self.assertEqual(chr(_render(st).ch[c]), "▤")

    def test_the_tapestry_and_ribbons_hang_on_the_wall(self):
        from hearthdelve.game import home
        st, (x0, y0, w, h) = self._house()
        st.stats[home.TAPESTRY], st.stats[home.RIBBONS] = 2, 2
        con = _render(st)
        walls = [_cell(st, x, y0) for x in range(x0, x0 + w)] + \
                [_cell(st, x0, y) for y in range(y0, y0 + h)]
        drawn = [chr(con.ch[c]) for c in walls]
        self.assertEqual(drawn.count("▦"), 1)
        self.assertEqual(drawn.count("⚑"), 2)

    def test_trophies_hang_in_the_second_room(self):
        from tests.test_extension import _built, _rich
        from hearthdelve.entities import items
        from hearthdelve.game import home, husbandry
        st = _built(_rich(fresh_state(221)))
        st.weather = "Clear"
        st.fx.clear()
        bx, by = st.surface.bed
        st.player.x, st.player.y = bx + 2, by + 2
        st.stats[home.TROPHIES] = items.TROLL_TUSK.name + "|" + items.BONE_CROWN.name
        con = _render(st)
        x0, y0, w, h = husbandry.house_rects(st)[1]
        cells = [_cell(st, x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)]
        self.assertEqual(sum(1 for c in cells if chr(con.ch[c]) == "♆"), 2)


if __name__ == "__main__":
    unittest.main()
