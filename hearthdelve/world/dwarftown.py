"""Khazgrim — the living dwarven town on the fourth level of the old mine.

The dwarves never left the mountain; they just moved DOWN when it last coughed.
Their hold is a stable, hand-shaped floor (seeded from the world seed alone, so
it never re-rolls): a pillared great hall, the Undertankard alehall, Thrunn's
forge, braziers against the dark — and stairs at the far end that keep going
down, into the old workings the dwarves themselves avoid.

The dwarf NPCs live on ``state.dwarves`` (created once, friendship persisted in
the save) and are re-seated in the hall each time the floor is built.
"""
from __future__ import annotations

import random

import numpy as np

from . import tile
from .gamemap import GameMap

TOWN_DEPTH = 4          # deeper than the door, shallower than the dark
UNDERRIVER_DEPTH = TOWN_DEPTH + 1   # one below Khazgrim: the dwarves' ore-river cavern
W, H = 72, 46


def generate(seed: int, dwarves: list) -> GameMap:
    rng = random.Random((seed * 60_013 + 4441) & 0x7FFFFFFF)
    tiles = np.full((W, H), tile.DUNGEON_WALL, dtype=np.uint8)

    def carve(x0, y0, x1, y1):
        tiles[x0:x1 + 1, y0:y1 + 1] = tile.DUNGEON_FLOOR

    # The great hall, pillared every sixth stride.
    carve(16, 14, 52, 32)
    for px in range(20, 50, 6):
        for py in (19, 27):
            tiles[px, py] = tile.DUNGEON_WALL
    tiles[34, 23] = tile.WELL                       # the deep well at the hall's heart

    # The Undertankard (alehall), north side.
    carve(20, 6, 34, 12)
    tiles[27, 13] = tile.DOOR
    tiles[27, 12] = tile.DUNGEON_FLOOR
    for bx in (21, 22, 33):
        tiles[bx, 7] = tile.BARREL
    tiles[26, 8] = tile.TABLE
    tiles[30, 8] = tile.TABLE
    tiles[23, 10] = tile.HEARTH

    # Thrunn's forge, south side.
    carve(38, 34, 50, 40)
    tiles[44, 33] = tile.DOOR
    tiles[44, 34] = tile.DUNGEON_FLOOR
    tiles[39, 39] = tile.HEARTH
    tiles[41, 39] = tile.HEARTH
    tiles[49, 35] = tile.BARREL

    # The Elder's alcove, west of the hall.
    carve(8, 20, 15, 26)
    tiles[16, 23] = tile.DUNGEON_FLOOR
    tiles[9, 21] = tile.TABLE

    # Braziers against the long dark.
    for lx, ly in ((18, 16), (18, 30), (50, 16), (50, 30), (34, 15), (34, 31)):
        tiles[lx, ly] = tile.LAMP

    # The way in (east, from the mine above) and the way down (the old workings).
    carve(53, 22, 64, 24)
    up = (63, 23)
    tiles[up] = tile.STAIRS_UP
    carve(4, 22, 8, 24)
    down = (5, 23)
    tiles[down] = tile.DUNGEON_DOWN

    gm = GameMap(width=W, height=H, tiles=tiles, is_dungeon=True,
                 depth=TOWN_DEPTH, kind="dwarfhold")
    gm.stairs_up = up
    gm.stairs_down = down
    gm.spawn = up
    gm.visible = np.full((W, H), False)
    gm.explored = np.full((W, H), False)

    # Seat the folk of Khazgrim (the same NPC objects every visit — their
    # friendship lives on state.dwarves, not on the floor).
    spots = {"Thrunn": (43, 38), "Brokka": (27, 9),
             "Kazrik": (46, 22), "Elder Durn": (11, 23)}
    for n in dwarves:
        n.x, n.y = spots.get(n.name, (34, 24))
        # nudge off anything solid, just in case the layout shifts someday
        if not gm.walkable(n.x, n.y):
            for dx in (0, 1, -1):
                for dy in (0, 1, -1):
                    if gm.walkable(n.x + dx, n.y + dy):
                        n.x, n.y = n.x + dx, n.y + dy
                        break
    gm.npcs = list(dwarves)
    return gm
