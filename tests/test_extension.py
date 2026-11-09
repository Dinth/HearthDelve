"""A bigger farmhouse: Tomas the carpenter builds a second room onto the house,
a late-game commission (gold, planks, stone and iron)."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _rich(st):
    from hearthdelve.entities import items
    st.player.gold = 20_000
    for it, q in ((items.TIMBER_PLANK, 80), (items.STONE, 100), (items.IRON_BAR, 10)):
        st.player.inventory.add(it, q)
    return st


def _row(st):
    from hearthdelve.game import village
    rows = village.shop_entries("carpenter", st)
    return next((r for r in rows if r.kind == "housejob" and r.build == "extension"), None)


def _built(st):
    """Order the room, then let two mornings pass."""
    from hearthdelve.game import farming, village
    village.purchase(st, _row(st))
    farming.sleep(st)
    farming.sleep(st)
    return st


def _house_floor(st):
    from hearthdelve.game import husbandry
    from hearthdelve.world import tile
    cells = {(x, y) for x0, y0, w, h in husbandry.house_rects(st)        # (the rooms share
             for x in range(x0, x0 + w) for y in range(y0, y0 + h)}         #  a wall)
    return sum(1 for x, y in cells if st.surface.tiles[x, y] == tile.HOUSE_FLOOR)


class TestTomasBuildsASecondRoom(unittest.TestCase):
    def test_he_offers_it_and_it_costs_what_a_room_costs(self):
        from hearthdelve.entities import items
        from hearthdelve.game import village
        st = _rich(fresh_state(2))
        row = _row(st)
        self.assertIsNotNone(row)
        gold = st.player.gold
        village.purchase(st, row)
        self.assertEqual(gold - st.player.gold, row.price)
        self.assertEqual(st.player.inventory.count(items.TIMBER_PLANK), 20)
        self.assertTrue(any(m.kind == "site" and m.build_kind == "extension"
                            for m in st.surface.machines.values()))
        self.assertIsNone(_row(st))                        # one order at a time

    def test_two_mornings_later_the_house_has_a_second_room(self):
        from hearthdelve.game import husbandry
        from hearthdelve.world import tile
        st = _rich(fresh_state(2))
        before = _house_floor(st)
        _built(st)
        side = husbandry.extension_side(st)
        self.assertIn(side, ("north", "east", "west"))
        self.assertEqual(_house_floor(st), before + 12 + 1)     # a 4x3 room and its doorway
        _rect, door = husbandry._extension_rect(*husbandry._house_origin(st.surface), side)
        self.assertEqual(st.surface.tiles[door], tile.HOUSE_FLOOR)
        self.assertFalse(any(m.kind == "site" for m in st.surface.machines.values()))
        self.assertIsNone(_row(st))                        # one second room is enough

    def test_it_goes_round_whatever_s_in_the_way(self):
        from hearthdelve.data import content
        from hearthdelve.game import husbandry
        from hearthdelve.world.crops import CropPlot
        st = _rich(fresh_state(2))
        hx, hy = husbandry._house_origin(st.surface)
        for x, y in husbandry._new_cells(hx, hy, "north"):     # a bed of parsnips up north
            st.surface.crops[(x, y)] = CropPlot(crop=content.CROPS[0])
        _built(st)
        self.assertNotEqual(husbandry.extension_side(st), "north")
        self.assertTrue(all((x, y) in st.surface.crops
                            for x, y in husbandry._new_cells(hx, hy, "north")))

    def test_it_never_builds_over_a_road(self):
        from hearthdelve.game import husbandry
        from hearthdelve.world import tile
        st = _rich(fresh_state(2))
        hx, hy = husbandry._house_origin(st.surface)
        for side in ("north", "east", "west"):
            x, y = husbandry._new_cells(hx, hy, side)[0]
            st.surface.tiles[x, y] = tile.DIRT_PATH
        self.assertIsNone(husbandry.find_house_spot(st, "extension"))

    def test_the_new_room_survives_a_save(self):
        from hearthdelve.engine import save
        from hearthdelve.game import husbandry
        st = _built(_rich(fresh_state(2)))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            back = save.load(path)
        self.assertEqual(husbandry.extension_side(back), husbandry.extension_side(st))
        self.assertEqual(_house_floor(back), _house_floor(st))

    def test_an_oven_can_go_in_the_new_room_when_the_old_one_is_full(self):
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import husbandry
        from hearthdelve.world import tile
        st = _built(_rich(fresh_state(2)))
        hx, hy = husbandry._house_origin(st.surface)
        for x in range(hx + 1, hx + husbandry.HOUSE_W - 1):        # fill the old room
            for y in range(hy + 1, hy + husbandry.HOUSE_H - 1):
                if st.surface.tiles[x, y] == tile.HOUSE_FLOOR:
                    st.surface.machines.setdefault((x, y), Machine(kind="keg"))
        spot = husbandry.find_house_spot(st, "oven")
        self.assertIsNotNone(spot)
        x0, y0, w, h = husbandry.house_rects(st)[1]
        self.assertTrue(x0 < spot[0] < x0 + w - 1 and y0 < spot[1] < y0 + h - 1)


if __name__ == "__main__":
    unittest.main()
