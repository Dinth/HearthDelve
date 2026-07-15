"""The Westreach — volcanic hill country west of the Vale.

A second, wilder overworld: hills climbing westward to a live volcano, ash
fields, ore-rich crags, sulphur seams — and beasts that hunt on sight. No
villages, no bed, no farming: an expedition region, reached by walking off the
main map's west edge and left the same way. Generated deterministically from
the world seed; the player's changes (mined seams, felled pines, slain beasts)
persist through the save exactly like the surface."""
from __future__ import annotations

import math
import random

import numpy as np

from . import tile
from .gamemap import GameMap
from .worldlib import grow_veins as _grow_veins, noise_field as _noise_field

W, H = 320, 320


def generate(seed: int) -> GameMap:
    rng = random.Random((seed * 48_611 + 977) & 0x7FFFFFFF)
    tiles = np.full((W, H), tile.MOOR, dtype=np.uint8)

    # Ground rises toward the west, where the mountain stands.
    elev = _noise_field(seed + 9101, W, H, 0.02, 4)
    detail = _noise_field(seed + 9102, W, H, 0.09, 2)
    flora = _noise_field(seed + 9103, W, H, 0.05, 3)
    slope = (1.0 - np.arange(W, dtype=np.float32)[:, None] / W) * 0.45
    elev = np.clip(elev * 0.7 + slope, 0.0, 1.0)

    tiles[elev < 0.40] = tile.GRASS
    tiles[(elev >= 0.40) & (elev < 0.56)] = tile.MOOR
    tiles[(elev >= 0.56) & (elev < 0.72)] = tile.HILL
    tiles[(elev >= 0.72) & (detail > 0.45)] = tile.SCREE
    tiles[elev >= 0.82] = tile.ROCK

    # Hardy conifers on the mid slopes.
    conif = (flora > 0.62) & (elev > 0.30) & (elev < 0.66)
    for x, y in zip(*np.where(conif)):
        if tiles[x, y] in (tile.GRASS, tile.MOOR, tile.HILL):
            tiles[x, y] = tile.TREE_PINE if detail[x, y] > 0.5 else tile.TREE_SPRUCE

    # The same sea that fringes the Vale laps this southern edge too — water
    # can't just stop at a map border. A wandering coast with a sandy strand;
    # its coastline is stored so foam breaks on it and midges know it's salt.
    wob = _noise_field(seed + 9210, W, 1, scale=0.05, octaves=3).reshape(-1)
    base = int(H * 0.86)
    coast = np.empty(W, dtype=np.int32)
    for x in range(W):
        cy = max(4, min(H - 4, base + int((wob[x] - 0.5) * 42)))
        coast[x] = cy
        tiles[x, cy:H] = tile.WATER
        for y in range(cy - 2, cy):
            if 0 <= y < H and tiles[x, y] != tile.WATER:
                tiles[x, y] = tile.SAND

    # --- the volcano -----------------------------------------------------------
    vx, vy = int(W * 0.30), H // 2 + rng.randint(-24, 24)
    ph = [rng.uniform(0, 6.28) for _ in range(3)]
    for x in range(max(1, vx - 30), min(W - 1, vx + 31)):
        for y in range(max(1, vy - 30), min(H - 1, vy + 31)):
            dx, dy = x - vx, y - vy
            d = math.hypot(dx, dy)
            ang = math.atan2(dy, dx)
            wob = (1.0 + 0.14 * math.sin(ang * 3 + ph[0])
                   + 0.10 * math.sin(ang * 5 + ph[1]))
            if d < 5.5 * wob:
                tiles[x, y] = tile.LAVA                       # the caldera
            elif d < 10.5 * wob:
                tiles[x, y] = tile.ROCK                       # the cone
            elif d < 15.5 * wob:
                tiles[x, y] = tile.SCREE
            elif d < 23.0 * wob and detail[x, y] > 0.40:
                tiles[x, y] = tile.ASH                        # the fallout apron

    # Sulphur crusts the cone; nitre gathers in the cooler folds.
    ring = [(x, y) for x in range(vx - 18, vx + 19) for y in range(vy - 18, vy + 19)
            if tiles[x, y] in (tile.ROCK, tile.SCREE)
            and 7 <= math.hypot(x - vx, y - vy) <= 17]
    rng.shuffle(ring)
    for i, (x, y) in enumerate(ring[:rng.randint(12, 16)]):
        tiles[x, y] = tile.SULPHUR_DEPOSIT
    for x, y in ring[20:20 + rng.randint(5, 8)]:
        if tiles[x, y] in (tile.ROCK, tile.SCREE):
            tiles[x, y] = tile.NITRE_DEPOSIT

    # The frontier is mineral-rich: ore streaks through every crag.
    _grow_veins(tiles, W, H, tile.ROCK, ore_veins=12, max_len=4, gems=3, rng=rng)

    # A guaranteed landing strip along the east edge, whatever the noise says.
    for y in range(H):
        for x in range(W - 5, W):
            if not tile.TILES[tiles[x, y]].walkable:
                tiles[x, y] = tile.MOOR

    gm = GameMap(width=W, height=H, tiles=tiles)
    gm.spawn = (W - 3, H // 2)
    gm.coast = coast                     # per-column first sea row (salt vs fresh)

    # --- the delvings ------------------------------------------------------------
    # An old tomb in the eastern hills, and the mouth of the dwarven mine on the
    # volcano's flank — the road down to whatever the dwarves left (and kept).
    def _entrance(cx, cy, kind, r0=2, r1=26):
        for r in range(r0, r1):
            for _try in range(24):
                x = cx + rng.randint(-r, r)
                y = cy + rng.randint(-r, r)
                if (gm.in_bounds(x, y) and gm.walkable(x, y)
                        and tiles[x, y] not in (tile.LAVA, tile.ASH)):
                    tiles[x, y] = tile.DUNGEON_DOWN
                    gm.dungeons.append((x, y))
                    gm.dungeon_kind[(x, y)] = kind
                    return (x, y)
        return None

    _entrance(vx + 60 + rng.randint(-8, 8), vy + rng.randint(-40, 40), "tomb")
    _entrance(vx + 18, vy - 18, "dwarfhold", r0=1, r1=18)

    # The beasts: wolves and vipers range everywhere, cinder boars root the
    # slopes, and ember drakes sun themselves near the caldera.
    from ..data import content
    from ..entities.monster import Mob

    def _scatter(critter, n, near_volcano=False):
        for _ in range(n):
            for _try in range(40):
                if near_volcano:
                    x = vx + rng.randint(-26, 26)
                    y = vy + rng.randint(-26, 26)
                else:
                    x, y = rng.randint(4, W - 8), rng.randint(4, H - 5)
                if not gm.in_bounds(x, y) or not gm.walkable(x, y):
                    continue
                if any(m.x == x and m.y == y for m in gm.monsters):
                    continue
                gm.monsters.append(Mob(critter.name, critter.glyph, critter.color,
                                       critter.hp, critter.hp, critter.speed,
                                       critter.behavior, x, y, dv=critter.dv,
                                       pv=critter.pv, to_hit=critter.to_hit,
                                       dmg=critter.dmg, kind="wildlife",
                                       diet=critter.diet, seasons=critter.seasons,
                                       inflicts=critter.inflicts))
                break

    by_name = {c.name: c for c in content.WEST_WILDLIFE}
    _scatter(by_name["Ash Wolf"], rng.randint(7, 9))
    _scatter(by_name["Rock Viper"], rng.randint(5, 7))
    _scatter(by_name["Cinder Boar"], rng.randint(4, 6))
    _scatter(by_name["Ember Drake"], rng.randint(2, 3), near_volcano=True)
    return gm
