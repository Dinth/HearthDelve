"""Procedural dungeon floors: rooms joined by corridors, with stairs and loot.

Each themed site (mine, grotto, ...) generates floors on demand. Per the design,
a floor re-rolls per in-game day; the caller seeds it accordingly.
"""
from __future__ import annotations

import random

import numpy as np

from . import tile
from .gamemap import GameMap

DUN_W, DUN_H = 72, 46
FOV_RADIUS = 8


class _Room:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    @property
    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def inner(self):
        return slice(self.x + 1, self.x + self.w - 1), slice(self.y + 1, self.y + self.h - 1)

    def intersects(self, o) -> bool:
        return (self.x <= o.x + o.w and self.x + self.w >= o.x
                and self.y <= o.y + o.h and self.y + self.h >= o.y)


def _tunnel(tiles, a, b, rng):
    (x1, y1), (x2, y2) = a, b
    if rng.random() < 0.5:
        corner = (x2, y1)
    else:
        corner = (x1, y2)
    for (sx, sy), (ex, ey) in (((x1, y1), corner), (corner, (x2, y2))):
        for x in range(min(sx, ex), max(sx, ex) + 1):
            tiles[x, sy] = tile.DUNGEON_FLOOR
        for y in range(min(sy, ey), max(sy, ey) + 1):
            tiles[ex, y] = tile.DUNGEON_FLOOR


def generate(seed: int, kind: str, depth: int) -> GameMap:
    rng = random.Random(seed)
    w, h = DUN_W, DUN_H
    tiles = np.full((w, h), tile.DUNGEON_WALL, dtype=np.uint8)

    rooms: list[_Room] = []
    for _ in range(rng.randint(8, 13)):
        rw, rh = rng.randint(5, 11), rng.randint(4, 8)
        rx, ry = rng.randint(1, w - rw - 2), rng.randint(1, h - rh - 2)
        room = _Room(rx, ry, rw, rh)
        if any(room.intersects(o) for o in rooms):
            continue
        ix, iy = room.inner()
        tiles[ix, iy] = tile.DUNGEON_FLOOR
        if rooms:
            _tunnel(tiles, rooms[-1].center, room.center, rng)
        rooms.append(room)

    # stairs: up in the first room, down in the last. If collisions left us with
    # a single room, up and down would coincide (down would clobber up), so put
    # them on two distinct interior tiles (opposite corners of the inner area).
    if len(rooms) == 1:
        r = rooms[0]
        up = (r.x + 1, r.y + 1)
        down = (r.x + r.w - 2, r.y + r.h - 2)
    else:
        up = rooms[0].center
        down = rooms[-1].center
    tiles[up] = tile.STAIRS_UP
    tiles[down] = tile.DUNGEON_DOWN

    # Sparse, mineable loot in the walls that border open floor. Ore comes in a
    # few short veins; gems are rare singles.
    def exposed():
        return [(x, y) for x in range(1, w - 1) for y in range(1, h - 1)
                if tiles[x, y] == tile.DUNGEON_WALL
                and (tiles[x - 1:x + 2, y - 1:y + 2] == tile.DUNGEON_FLOOR).any()]

    walls = exposed()
    for x, y in walls:                                  # a little loose rock
        if rng.random() < 0.10:
            tiles[x, y] = tile.ROCK

    ore_veins = (5 if kind == "mine" else 2)
    max_len = (5 if kind == "mine" else 3)
    for _ in range(ore_veins):
        cands = [p for p in walls if tiles[p] == tile.DUNGEON_WALL]
        if not cands:
            break
        x, y = rng.choice(cands)
        for _ in range(rng.randint(1, max_len)):
            if tiles[x, y] != tile.DUNGEON_WALL:
                break
            tiles[x, y] = tile.ORE_VEIN
            nbrs = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    if (dx or dy) and tiles[x + dx, y + dy] == tile.DUNGEON_WALL
                    and (tiles[x + dx - 1:x + dx + 2, y + dy - 1:y + dy + 2] == tile.DUNGEON_FLOOR).any()]
            if not nbrs:
                break
            x, y = rng.choice(nbrs)

    gem_count = (1 if kind == "mine" else 0) + (1 if rng.random() < 0.18 * depth else 0)
    for _ in range(gem_count):
        cands = [p for p in walls if tiles[p] == tile.DUNGEON_WALL]
        if not cands:
            break
        tiles[rng.choice(cands)] = tile.GEM_VEIN

    # Underground lakes: a small pool in a couple of rooms. Never the entry
    # (rooms[0]) nor the down-stairs room (rooms[-1]) — a pool there could drown
    # the stairs tile itself. A lake can still stray onto a corridor and cut off
    # later rooms, so we snapshot each lake's footprint, carve it, and revert if
    # it disconnected anything (stairs or a room centre).
    def _connected(reachable_from):
        """Flood-fill over walkable tiles (per the tile registry) from a start,
        returning the set of reached (x, y). tiles is indexed [x, y], (w, h)."""
        seen = {reachable_from}
        stack = [reachable_from]
        while stack:
            sx, sy = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = sx + dx, sy + dy
                if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in seen:
                    continue
                if tile.TILES[tiles[nx, ny]].walkable:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return seen

    lake_rooms = rooms[1:-1] if len(rooms) > 2 else []
    for room in rng.sample(lake_rooms, min(2, len(lake_rooms))):
        lw, lh = rng.randint(2, max(2, room.w - 3)), rng.randint(2, max(2, room.h - 3))
        lx = rng.randint(room.x + 1, room.x + room.w - lw - 1)
        ly = rng.randint(room.y + 1, room.y + room.h - lh - 1)
        pool = [(x, y) for x in range(lx, lx + lw) for y in range(ly, ly + lh)
                if tiles[x, y] == tile.DUNGEON_FLOOR]
        snapshot = [(x, y, tiles[x, y]) for x, y in pool]      # revert-on-cut
        for x, y in pool:
            tiles[x, y] = tile.WATER
        reachable = _connected(up)
        need = {down} | {r.center for r in rooms}
        if not need.issubset(reachable):
            for x, y, old in snapshot:                          # lake cut us off — revert
                tiles[x, y] = old

    # --- texture: rubble, cave fungus, hidden traps, treasure chests --------
    entry = rooms[0]

    def in_entry(x, y):
        return entry.x <= x < entry.x + entry.w and entry.y <= y < entry.y + entry.h

    def floor_cells():
        return [(x, y) for x in range(1, w - 1) for y in range(1, h - 1)
                if tiles[x, y] == tile.DUNGEON_FLOOR and (x, y) not in (up, down)]

    # Rubble scree — slows the crossing; commoner in mines.
    for x, y in floor_cells():
        if rng.random() < (0.06 if kind == "mine" else 0.02):
            tiles[x, y] = tile.RUBBLE

    # Cave fungus — clusters, mostly in damp grottoes.
    n_mush = (len(rooms) * 2 if kind == "grotto" else max(1, len(rooms) // 2))
    for _ in range(n_mush):
        room = rng.choice(rooms[1:]) if len(rooms) > 1 else rooms[0]
        mx = rng.randint(room.x + 1, room.x + room.w - 2)
        my = rng.randint(room.y + 1, room.y + room.h - 2)
        if tiles[mx, my] == tile.DUNGEON_FLOOR and (mx, my) not in (up, down):
            tiles[mx, my] = tile.MUSHROOM

    # Hidden traps — never in the entry room; more on deeper floors.
    cells = [(x, y) for (x, y) in floor_cells() if not in_entry(x, y)]
    rng.shuffle(cells)
    for x, y in cells[:rng.randint(2, 3 + depth)]:
        if tiles[x, y] == tile.DUNGEON_FLOOR:
            tiles[x, y] = tile.TRAP_HIDDEN

    # Treasure chests — a few, tucked in non-entry rooms.
    n_chest = rng.randint(1, 2 + (1 if depth >= 3 else 0))
    picks = rng.sample(rooms[1:], min(len(rooms) - 1, n_chest)) if len(rooms) > 1 else []
    for room in picks:
        cx2 = rng.randint(room.x + 1, room.x + room.w - 2)
        cy2 = rng.randint(room.y + 1, room.y + room.h - 2)
        if tiles[cx2, cy2] == tile.DUNGEON_FLOOR and (cx2, cy2) not in (up, down):
            tiles[cx2, cy2] = tile.CHEST

    gm = GameMap(width=w, height=h, tiles=tiles, is_dungeon=True, depth=depth, kind=kind)
    gm.stairs_up = up
    gm.stairs_down = down
    gm.spawn = up
    gm.visible = np.full((w, h), False)
    gm.explored = np.full((w, h), False)
    gm.rooms = rooms

    # A few gentle monsters, never in the entry room. More on deeper floors.
    # Track occupied tiles (seeded with the stairs) so no two mobs share a spot.
    from ..data import content
    occupied = {up, down}
    pool = [m for m in content.MONSTERS if m.min_depth <= depth]
    n_mon = rng.randint(2, 3 + depth)
    for _ in range(n_mon):
        if len(rooms) < 2 or not pool:
            break
        room = rng.choice(rooms[1:])
        mx = rng.randint(room.x + 1, room.x + room.w - 2)
        my = rng.randint(room.y + 1, room.y + room.h - 2)
        if tiles[mx, my] != tile.DUNGEON_FLOOR or (mx, my) in occupied:
            continue
        occupied.add((mx, my))
        t = rng.choice(pool)
        gm.monsters.append(content.make_mob(t, mx, my, depth, rng))

    # A boss lurks on deep floors (near the down-stairs).
    bosses = [b for b in content.BOSSES if b.min_depth <= depth]
    if bosses and rng.random() < 0.6:
        b = rng.choice(bosses)
        room = rooms[-1]
        bx = rng.randint(room.x + 1, room.x + room.w - 2)
        by = rng.randint(room.y + 1, room.y + room.h - 2)
        if tiles[bx, by] == tile.DUNGEON_FLOOR and (bx, by) not in occupied:
            occupied.add((bx, by))
            gm.monsters.append(content.make_mob(b, bx, by, depth, rng, boss=True))

    # Vault: a big chamber on deep floors, packed with gold and its guardians.
    if depth >= 3 and rng.random() < 0.5:
        vw, vh = rng.randint(10, 14), rng.randint(7, 9)
        vroom = None
        for _ in range(40):
            vx, vy = rng.randint(1, w - vw - 2), rng.randint(1, h - vh - 2)
            cand = _Room(vx, vy, vw, vh)
            if not any(cand.intersects(o) for o in rooms):
                vroom = cand
                break
        if vroom is not None:
            ix, iy = vroom.inner()
            tiles[ix, iy] = tile.DUNGEON_FLOOR
            _tunnel(tiles, rooms[-1].center, vroom.center, rng)
            rooms.append(vroom)
            cells = [(x, y) for x in range(vroom.x + 1, vroom.x + vw - 1)
                     for y in range(vroom.y + 1, vroom.y + vh - 1)
                     if tiles[x, y] == tile.DUNGEON_FLOOR]
            rng.shuffle(cells)
            for gx, gy in cells[:rng.randint(8, 14)]:          # heaps of gold
                tiles[gx, gy] = tile.GOLD_PILE
            guards = pool or content.MONSTERS
            for mx, my in cells[-rng.randint(4, 6):]:          # and its guardians
                if tiles[mx, my] == tile.DUNGEON_FLOOR and (mx, my) not in occupied:
                    occupied.add((mx, my))
                    t = rng.choice(guards)
                    gm.monsters.append(content.make_mob(t, mx, my, depth, rng))

    # Glimmerwood Hollow: a rare, peaceful glowing grove — fungal trees, giant
    # luminous caps and a still pool. Commoner in damp grottoes; a cozy find.
    grove_chance = 0.30 if kind == "grotto" else 0.10
    if depth >= 2 and rng.random() < grove_chance:
        gw, gh = rng.randint(11, 15), rng.randint(7, 10)
        groom = None
        for _ in range(40):
            gx, gy = rng.randint(1, w - gw - 2), rng.randint(1, h - gh - 2)
            cand = _Room(gx, gy, gw, gh)
            if not any(cand.intersects(o) for o in rooms):
                groom = cand
                break
        if groom is not None:
            ix, iy = groom.inner()
            tiles[ix, iy] = tile.GLOW_MOSS
            _tunnel(tiles, rooms[-1].center, groom.center, rng)
            rooms.append(groom)
            gcx, gcy = groom.center
            cells = [(x, y) for x in range(groom.x + 1, groom.x + gw - 1)
                     for y in range(groom.y + 1, groom.y + gh - 1)
                     if tiles[x, y] == tile.GLOW_MOSS]
            rng.shuffle(cells)
            # The grove floor teems with fungi — a rich foraging chamber.
            for x, y in cells:
                if (x - gcx) ** 2 + (y - gcy) ** 2 <= 2:      # keep the arrival spot clear
                    continue
                r = rng.random()
                if r < 0.15:
                    tiles[x, y] = tile.WISPWOOD               # glowing wispwood trees
                elif r < 0.42:
                    tiles[x, y] = tile.MUSHROOM               # plentiful cave mushrooms
                elif r < 0.54:
                    tiles[x, y] = tile.GLOWCAP                # giant luminous caps
            pw, ph = rng.randint(2, 4), rng.randint(2, 3)     # a still, glowing pool
            px = rng.randint(groom.x + 1, groom.x + gw - pw - 1)
            py = rng.randint(groom.y + 1, groom.y + gh - ph - 1)
            for x in range(px, px + pw):
                for y in range(py, py + ph):
                    if tiles[x, y] == tile.GLOW_MOSS:
                        tiles[x, y] = tile.WATER
            if rng.random() < 0.6:                            # something tucked among the roots
                spot = next((c for c in cells if tiles[c] == tile.GLOW_MOSS), None)
                if spot:
                    tiles[spot] = tile.CHEST

    # The vault/grove tunnels above start from the last room's centre — which is
    # the down-stairs tile — and _tunnel paints floor over its own endpoints, so
    # re-assert the stairs before anything relies on them (nearly half of deep
    # floors would otherwise have no way down).
    tiles[up] = tile.STAIRS_UP
    tiles[down] = tile.DUNGEON_DOWN

    # --- connectivity repair -------------------------------------------------
    # The room/tunnel carve can leave a room stranded when ore/gem veins grow
    # across a one-wide corridor's flanks and pinch it shut. Flood from the
    # up-stairs over walkable tiles; for any target (down-stairs or a room
    # centre) still unreachable, dig a fresh L-corridor from it to the nearest
    # reachable floor. Repeat until everything is joined.
    def _reachable():
        seen = {up}
        stack = [up]
        while stack:
            sx, sy = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = sx + dx, sy + dy
                if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in seen:
                    continue
                if tile.TILES[tiles[nx, ny]].walkable:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return seen

    targets = [down] + [r.center for r in rooms]
    for _ in range(len(targets) + 2):                 # each pass joins >=1 target
        reach = _reachable()
        stranded = [p for p in targets if p not in reach]
        if not stranded:
            break
        tx, ty = min(stranded, key=lambda p: min(
            (abs(p[0] - rx) + abs(p[1] - ry) for rx, ry in reach)))
        gx, gy = min(reach, key=lambda c: abs(c[0] - tx) + abs(c[1] - ty))
        for x in range(min(tx, gx), max(tx, gx) + 1):  # horizontal leg
            if tiles[x, ty] == tile.DUNGEON_WALL or not tile.TILES[tiles[x, ty]].walkable:
                if (x, ty) not in (up, down):
                    tiles[x, ty] = tile.DUNGEON_FLOOR
        for y in range(min(ty, gy), max(ty, gy) + 1):  # vertical leg
            if tiles[gx, y] == tile.DUNGEON_WALL or not tile.TILES[tiles[gx, y]].walkable:
                if (gx, y) not in (up, down):
                    tiles[gx, y] = tile.DUNGEON_FLOOR
    return gm
