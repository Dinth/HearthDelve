"""Entering, leaving, and seeing inside dungeons."""
from __future__ import annotations

import zlib

import tcod.map

from ..world import dungeon, tile
from .state import GameState


def _feeling(gm) -> str:
    """A NetHack-style level feeling from the floor's riches and dangers."""
    if getattr(gm, "depth", 0) and gm.depth % 10 == 0:
        return ("A DEEP SANCTUM. The dark here is thick with dread and promise — "
                "a great guardian, and a hoard worth the descent.")
    ore = int((gm.tiles == tile.ORE_VEIN).sum())
    gem = int((gm.tiles == tile.GEM_VEIN).sum())
    score = ore + gem * 3
    if score == 0:
        base = "This place feels barren."
    elif score <= 3:
        base = "There's little of worth here."
    elif score <= 8:
        base = "You sense a few veins worth mining."
    elif score <= 15:
        base = "This floor feels rich with ore."
    else:
        base = "Your heart quickens — treasure fills these walls."
    extra = []
    if gem:
        extra.append("A gemstone glints somewhere in the dark.")
    if (gm.tiles == tile.WATER).any():
        extra.append("You hear water splashing nearby.")
    if (gm.tiles == tile.GOLD_PILE).any():
        extra.append("You feel strangely excited.")
    if (gm.tiles == tile.CHEST).any():
        extra.append("Something valuable lies hidden here.")
    if (gm.tiles == tile.MUSHROOM).any():
        extra.append("A loamy, mushroomy smell hangs in the air.")
    if (gm.tiles == tile.WISPWOOD).any():
        extra.append("A strange living glow drifts on the air — something grows down here.")
    if gm.hidden_traps:
        extra.append("Something about the floor makes you uneasy.")
    if any(getattr(m, "boss", False) for m in gm.monsters):
        extra.append("You sense an imminent danger.")
    return base + (" " + " ".join(extra) if extra else "")


def update_fov(state: GameState) -> None:
    w = state.world
    if not w.is_dungeon:
        return
    from . import attrs
    radius = max(4, dungeon.FOV_RADIUS + attrs.mod(state, "Pe") // 3)   # keen eyes see farther
    w.visible = tcod.map.compute_fov(
        w.transparency(), (state.player.x, state.player.y), radius=radius
    )
    w.explored |= w.visible


def _site(state: GameState) -> tuple:
    """The mouth this delve began at: the map it opens from and its tile. Two
    mines are two holes in the ground, and each leads to floors of its own."""
    x, y = state.return_pos
    return ("west" if state.return_west else "vale", x, y)


def _floor_seed(state: GameState, depth: int) -> int:
    return _seed_for(state, state.dungeon_kind, _site(state), depth)


def _seed_for(state: GameState, kind: str, site: tuple, depth: int) -> int:
    # hash() is salted per process (PYTHONHASHSEED), which would re-roll floors
    # on every reload — combine the inputs arithmetically instead. The mouth is
    # part of it, so two sites of the same kind never roll the same floor.
    where, x, y = site
    site_id = zlib.crc32(f"{kind}@{where}:{x},{y}".encode())
    return (state.seed * 1_000_003 + depth * 7919 + state.day * 104_729 + site_id) & 0x7FFFFFFF


def build_floor(state: GameState, kind: str, site: tuple, depth: int):
    """Generate today's floor ``depth`` below the ``kind`` mouth at ``site`` —
    exactly as it first rolled, so a save can rebuild it and lay what changed
    on top. Khazgrim and the Underriver are world-seeded: the same every day."""
    from ..world import dwarftown
    if kind == "dwarfhold" and depth == dwarftown.TOWN_DEPTH:
        # Khazgrim: the living town — seeded from the world alone, so its halls
        # never re-roll, and its folk are the same folk every visit.
        if state.dwarves is None:
            from ..data import content
            state.dwarves = content.dwarf_npcs()
        return dwarftown.generate(state.seed, state.dwarves)
    if kind == "dwarfhold" and depth == dwarftown.UNDERRIVER_DEPTH:
        # The Underriver: world-seeded like the town, so the same river every
        # time — a persistent stake you return to and pan for ore & gems.
        return dungeon.generate_underriver(state.seed)
    return dungeon.generate(_seed_for(state, kind, site, depth), kind, depth)


def _go_to_floor(state: GameState, depth: int, descending: bool) -> None:
    # Re-use the floor if we've already been on it today (so opened chests, scooped
    # gold and slain monsters stay gone); otherwise generate it and remember it.
    # The cache is dropped on a new day, so floors still re-roll daily. It is
    # keyed by the mouth too: looting one mine's floor 1 leaves the other's be.
    if state.floor_cache_day != state.day:
        state.floor_cache.clear()
        state.floor_cache_day = state.day
    key = (state.dungeon_kind, _site(state), depth)
    gm = state.floor_cache.get(key)
    if gm is None:
        from ..world import dwarftown
        gm = build_floor(state, state.dungeon_kind, _site(state), depth)
        if state.dungeon_kind == "dwarfhold" and depth == dwarftown.TOWN_DEPTH:
            state.log.add("Braziers. Voices. Ale-smell. This level is LIVED IN — "
                          "you've found Khazgrim, the dwarves' town under the mountain.",
                          (232, 200, 120))
        elif state.dungeon_kind == "dwarfhold" and depth == dwarftown.UNDERRIVER_DEPTH:
            first = not state.stats.get("found_underriver")
            state.stats["found_underriver"] = 1
            state.log.add(
                ("A black river roars through the deep dark below Khazgrim — its gravel "
                 "glints with ore and gemstone. THE UNDERRIVER. Cast a line to pan it."
                 if first else
                 "The Underriver runs on, black and cold. Cast a line to pan its gravel."),
                (150, 200, 224))
        state.floor_cache[key] = gm
    state.world = gm
    state.stats["deepest_depth"] = max(state.stats.get("deepest_depth", 0), depth)
    # arrive at the up-stairs when descending into a floor, down-stairs when rising
    state.player.x, state.player.y = gm.stairs_up if descending else gm.stairs_down
    update_fov(state)
    state.log.add(_feeling(gm), (176, 180, 216))


def enter(state: GameState, kind: str) -> None:
    """Step from a surface entrance into floor 1 of a dungeon site."""
    state.return_pos = (state.player.x, state.player.y)
    state.return_west = state.west is not None and state.world is state.west
    state.dungeon_kind = kind
    state.depth = 1
    _go_to_floor(state, 1, descending=True)
    state.log.add(f"You descend into the {kind}. (floor 1)", (200, 200, 220))


def descend(state: GameState) -> None:
    state.depth += 1
    _go_to_floor(state, state.depth, descending=True)
    state.log.add(f"You climb deeper. (floor {state.depth})", (200, 200, 220))


def ascend(state: GameState) -> None:
    state.depth -= 1
    if state.depth <= 0:
        leave_to_surface(state)
        state.log.add("You climb back out into the daylight.", (220, 215, 180))
    else:
        _go_to_floor(state, state.depth, descending=False)
        state.log.add(f"You climb up. (floor {state.depth})", (200, 200, 220))


def leave_to_surface(state: GameState) -> None:
    """Return to the open air — whichever map the delve began on (used by
    ascend and by fainting in the dark)."""
    state.depth = 0
    state.world = (state.west if (state.return_west and state.west is not None)
                   else state.surface)
    state.player.x, state.player.y = state.return_pos
    state.return_west = False
