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

# Per-kind wall/floor palette. The floor is carved generically and re-skinned to
# these at the end, so every gen-time ``== DUNGEON_FLOOR`` check still holds while
# each site ends up reading distinctly. Mines keep the default brown rock; tombs
# take the pale ruins stone; the rest get their own new tiles.
_THEME = {
    "grotto":    ("cave_wall", "cave_floor"),        # damp blue-green cavern
    "sea cave":  ("cave_wall", "cave_floor"),        # briny sea-cut cave (damp look)
    "barrow":    ("barrow_wall", "barrow_floor"),    # dark earthen burrow
    "tomb":      ("ruins_wall", "ruins_floor"),      # pale worked stone
    "dwarfhold": ("dwarf_wall", "dwarf_floor"),      # grey dwarven masonry
    "crypt":     ("crypt_wall", "crypt_floor"),      # cold blue-grey crypt stone
    "cavern":    ("cavern_wall", "cavern_floor"),    # pale limestone
    # "mine" (and any unlisted kind) keeps DUNGEON_WALL/FLOOR.
}


# Per-kind décor: "walk" tiles sprinkle freely on the floor; "block" tiles are
# placed in room interiors and reverted if they'd seal the floor off. Each entry
# is (tile name, probability per candidate cell).
_DECOR = {
    "mine":      {"block": (("mine_timber", 0.010),)},                     # pit-props
    "grotto":    {"block": (("stalagmite", 0.012),)},                      # dripstone spires
    "sea cave":  {"block": (("stalagmite", 0.010),)},
    "cavern":    {"walk": (("crystal", 0.020),), "block": (("stalagmite", 0.014),)},
    "barrow":    {"walk": (("bones", 0.045),)},                            # scattered bones
    "crypt":     {"walk": (("bones", 0.050),), "block": (("pillar", 0.012), ("brazier", 0.004))},
    "tomb":      {"walk": (("bones", 0.030),), "block": (("pillar", 0.014), ("brazier", 0.004))},
    "dwarfhold": {"block": (("pillar", 0.010), ("brazier", 0.005))},       # worked hall
}


def _apply_theme(gm, kind: str) -> None:
    """Re-skin the finished floor's generic walls/floors to the kind's palette
    and record which tiles those are (so runtime code can restore matching floor
    when a vein is mined or a trap sprung)."""
    wall_name, floor_name = _THEME.get(kind, ("dungeon_wall", "dungeon_floor"))
    wall, floor = tile.tid(wall_name), tile.tid(floor_name)
    gm.wall_tile, gm.floor_tile = wall, floor
    if floor != tile.DUNGEON_FLOOR:
        gm.tiles[gm.tiles == tile.DUNGEON_FLOOR] = floor
    if wall != tile.DUNGEON_WALL:
        gm.tiles[gm.tiles == tile.DUNGEON_WALL] = wall


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


# How each kind is carved: organic blobby caverns, clean rectilinear halls, or
# a mine of small chambers strung on long tunnels.
_LAYOUT = {
    "grotto": "cave", "cavern": "cave", "sea cave": "cave",
    "crypt": "halls", "tomb": "halls", "dwarfhold": "halls",
    "mine": "mine",
}

# What each kind is rich or poor in, so where you delve changes the reward:
# ore veins, extra gems, trap frequency (x the base roll), underground pools, and
# extra chests. Mines & dwarfholds run to metal; caverns glitter with gems; sea
# caves flood; crypts & tombs are trap-riddled and full of grave-goods.
_BIAS = {
    "mine":      dict(ore=5, gem=1, trap=0.8, lakes=1, chest=0),
    "dwarfhold": dict(ore=4, gem=1, trap=1.0, lakes=0, chest=1),
    "cavern":    dict(ore=4, gem=2, trap=1.0, lakes=2, chest=0),
    "grotto":    dict(ore=2, gem=0, trap=1.0, lakes=2, chest=0),
    "sea cave":  dict(ore=1, gem=0, trap=1.0, lakes=3, chest=1),
    "barrow":    dict(ore=1, gem=0, trap=1.4, lakes=0, chest=1),
    "tomb":      dict(ore=1, gem=1, trap=1.8, lakes=0, chest=2),
    "crypt":     dict(ore=0, gem=0, trap=1.9, lakes=0, chest=2),
}
_BIAS_DEFAULT = dict(ore=2, gem=0, trap=1.0, lakes=1, chest=0)

KIND_BIAS = _BIAS       # a public, read-only view for the codex's Dungeon Sites page


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


def _carve_room(tiles, room, style, rng) -> None:
    """Carve a room's floor. Halls/mines fill the rectangle; caves fill a
    jittered ellipse so the chamber reads as an organic cavern."""
    W, H = tiles.shape
    if style != "cave":
        ix, iy = room.inner()
        tiles[ix, iy] = tile.DUNGEON_FLOOR
        return
    cx, cy = room.x + room.w / 2.0, room.y + room.h / 2.0
    rx, ry = max(1.0, room.w / 2.0 - 0.5), max(1.0, room.h / 2.0 - 0.5)
    for x in range(room.x, room.x + room.w):
        for y in range(room.y, room.y + room.h):
            nx, ny = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
            if nx * nx + ny * ny <= 1.0 + rng.uniform(-0.18, 0.12) and 1 <= x < W - 1 and 1 <= y < H - 1:
                tiles[x, y] = tile.DUNGEON_FLOOR


def _carve_tunnel(tiles, a, b, style, rng) -> None:
    """Join two rooms. Halls/mines get a clean 1-wide L; caves get the same L
    thickened and roughened into a winding passage (the base L always connects,
    so widening only ever adds floor — connectivity is never at risk)."""
    if style != "cave":
        _tunnel(tiles, a, b, rng)
        return
    W, H = tiles.shape
    (x1, y1), (x2, y2) = a, b
    corner = (x2, y1) if rng.random() < 0.5 else (x1, y2)

    def paint(x, y):
        if 1 <= x < W - 1 and 1 <= y < H - 1:
            tiles[x, y] = tile.DUNGEON_FLOOR

    for (sx, sy), (ex, ey) in (((x1, y1), corner), (corner, (x2, y2))):
        for x in range(min(sx, ex), max(sx, ex) + 1):
            paint(x, sy)
            paint(x, sy + 1)
            if rng.random() < 0.4:
                paint(x, sy - 1)
        for y in range(min(sy, ey), max(sy, ey) + 1):
            paint(ex, y)
            paint(ex + 1, y)
            if rng.random() < 0.4:
                paint(ex - 1, y)


def generate(seed: int, kind: str, depth: int) -> GameMap:
    rng = random.Random(seed)
    w, h = DUN_W, DUN_H
    tiles = np.full((w, h), tile.DUNGEON_WALL, dtype=np.uint8)

    style = _LAYOUT.get(kind, "halls")
    # Per-style shape: caves are fewer, rounder chambers; mines are many small
    # chambers on long tunnels; halls are the middling rectangular rooms.
    if style == "cave":
        n_rooms, rw_rng, rh_rng = rng.randint(6, 9), (6, 12), (5, 9)
    elif style == "mine":
        n_rooms, rw_rng, rh_rng = rng.randint(9, 14), (4, 7), (3, 6)
    else:
        n_rooms, rw_rng, rh_rng = rng.randint(8, 13), (5, 11), (4, 8)

    rooms: list[_Room] = []
    for _ in range(n_rooms):
        rw, rh = rng.randint(*rw_rng), rng.randint(*rh_rng)
        rx, ry = rng.randint(1, w - rw - 2), rng.randint(1, h - rh - 2)
        room = _Room(rx, ry, rw, rh)
        if any(room.intersects(o) for o in rooms):
            continue
        _carve_room(tiles, room, style, rng)
        if rooms:
            _carve_tunnel(tiles, rooms[-1].center, room.center, style, rng)
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

    # Deeper floors run richer, but loosely — a little random drift, not a fixed
    # count per depth.
    bias = _BIAS.get(kind, _BIAS_DEFAULT)
    ore_veins = bias["ore"] + rng.randint(0, 1 + depth // 2)
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

    gem_count = bias["gem"] + (1 if rng.random() < 0.18 * depth else 0)
    for _ in range(gem_count):
        cands = [p for p in walls if tiles[p] == tile.DUNGEON_WALL]
        if not cands:
            break
        tiles[rng.choice(cands)] = tile.GEM_VEIN

    # Alchemical deposits, scattered as drifting singles: nitre crusts anywhere,
    # sulphur seams mostly where the rock runs hot (deeper floors).
    nitre = rng.randint(0, 2)
    sulphur = rng.randint(0, 1) + (1 if depth >= 2 and rng.random() < 0.6 else 0)
    for tid, n in ((tile.NITRE_DEPOSIT, nitre), (tile.SULPHUR_DEPOSIT, sulphur)):
        for _ in range(n):
            cands = [p for p in walls if tiles[p] == tile.DUNGEON_WALL]
            if not cands:
                break
            tiles[rng.choice(cands)] = tid

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

    # Only rooms roomy enough to hold a pool with a wall margin (small mine
    # chambers are skipped, which also keeps the randint ranges non-empty).
    lake_rooms = [r for r in rooms[1:-1] if r.w >= 6 and r.h >= 6] if len(rooms) > 2 else []
    for room in rng.sample(lake_rooms, min(bias["lakes"], len(lake_rooms))):
        lw, lh = rng.randint(2, room.w - 3), rng.randint(2, room.h - 3)
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

    # Per-kind décor — the biggest tell that one site isn't another. Walkable
    # atmosphere sprinkles anywhere; blocking features go in room interiors and
    # revert if they'd cut the floor (reusing the lake connectivity check).
    spec = _DECOR.get(kind, {})
    for name, dens in spec.get("walk", ()):
        deco = tile.tid(name)
        for x, y in floor_cells():
            if (tiles[x, y] == tile.DUNGEON_FLOOR and not in_entry(x, y)
                    and rng.random() < dens):
                tiles[x, y] = deco
    room_centers = {r.center for r in rooms}
    need = {down} | room_centers
    for name, dens in spec.get("block", ()):
        deco = tile.tid(name)
        interior = [(x, y) for r in rooms[1:]
                    for x in range(r.x + 1, r.x + r.w - 1)
                    for y in range(r.y + 1, r.y + r.h - 1)
                    if tiles[x, y] == tile.DUNGEON_FLOOR
                    and (x, y) not in room_centers and (x, y) not in (up, down)]
        rng.shuffle(interior)
        budget = max(1, int(len(interior) * dens)) + rng.randint(0, 2)
        for x, y in interior:
            if budget <= 0:
                break
            tiles[x, y] = deco
            if need.issubset(_connected(up)):       # still all reachable?
                budget -= 1
            else:
                tiles[x, y] = tile.DUNGEON_FLOOR     # would seal a room off — undo

    # Hidden traps — never in the entry room; more on deeper floors. Recorded as
    # coordinates (not a distinct tile) so the per-kind floor re-skin below can't
    # betray them; the tile stays ordinary floor until spotted or sprung.
    hidden_traps = []
    cells = [(x, y) for (x, y) in floor_cells() if not in_entry(x, y)]
    rng.shuffle(cells)
    for x, y in cells[:max(0, round(rng.randint(2, 3 + depth) * bias["trap"]))]:
        if tiles[x, y] == tile.DUNGEON_FLOOR:
            hidden_traps.append((x, y))

    # Treasure chests — a few, tucked in non-entry rooms.
    n_chest = rng.randint(1, 2 + (1 if depth >= 3 else 0)) + bias["chest"]
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
    pool = content.monsters_for(kind, depth)
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

    # Every tenth floor is a Deep Sanctum: a guaranteed boss and a rich vault.
    milestone = depth > 0 and depth % 10 == 0

    # A boss lurks on deep floors (near the down-stairs); always on a Sanctum,
    # and there it's the most fearsome the floor can muster.
    bosses = content.bosses_for(kind, depth)
    if bosses and (milestone or rng.random() < 0.6):
        b = max(bosses, key=lambda m: m.min_depth) if milestone else rng.choice(bosses)
        room = rooms[-1]
        # scan the room for a free floor cell so the spawn never silently fails
        spots = [(x, y) for x in range(room.x + 1, room.x + room.w - 1)
                 for y in range(room.y + 1, room.y + room.h - 1)
                 if tiles[x, y] == tile.DUNGEON_FLOOR and (x, y) not in occupied]
        if spots:
            bx, by = rng.choice(spots)
            occupied.add((bx, by))
            gm.monsters.append(content.make_mob(b, bx, by, depth, rng, boss=True))

    # Vault: a big chamber on deep floors, packed with gold and its guardians —
    # guaranteed and richer on a Sanctum floor.
    if milestone or (depth >= 3 and rng.random() < 0.5):
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
            n_gold = rng.randint(14, 20) if milestone else rng.randint(8, 14)
            for gx, gy in cells[:n_gold]:                      # heaps of gold
                tiles[gx, gy] = tile.GOLD_PILE
            if milestone:                                      # a Sanctum keeps chests too
                for cx, cy in cells[n_gold:n_gold + rng.randint(2, 3)]:
                    if tiles[cx, cy] == tile.DUNGEON_FLOOR:
                        tiles[cx, cy] = tile.CHEST
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

    # Hidden traps only survive on tiles that are still plain floor (a vein or a
    # repair corridor may have overwritten one), then re-skin to the kind palette.
    gm.hidden_traps = {(x, y) for (x, y) in hidden_traps if tiles[x, y] == tile.DUNGEON_FLOOR}
    _apply_theme(gm, kind)
    return gm
