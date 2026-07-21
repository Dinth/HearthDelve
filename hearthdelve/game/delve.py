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


def _floor_seed(state: GameState, depth: int) -> int:
    # hash() is salted per process (PYTHONHASHSEED), which would re-roll floors
    # on every reload — combine the inputs arithmetically instead.
    kind_id = zlib.crc32(state.dungeon_kind.encode())
    return (state.seed * 1_000_003 + depth * 7919 + state.day * 104_729 + kind_id) & 0x7FFFFFFF


def _go_to_floor(state: GameState, depth: int, descending: bool) -> None:
    # Re-use the floor if we've already been on it today (so opened chests, scooped
    # gold and slain monsters stay gone); otherwise generate it and remember it.
    # The cache is dropped on a new day, so floors still re-roll daily.
    if state.floor_cache_day != state.day:
        state.floor_cache.clear()
        state.floor_cache_day = state.day
    key = (state.dungeon_kind, depth)
    gm = state.floor_cache.get(key)
    if gm is None:
        from ..world import dwarftown
        if state.dungeon_kind == "dwarfhold" and depth == dwarftown.TOWN_DEPTH:
            # Khazgrim: the living town — seeded from the world alone, so its
            # halls never re-roll, and its folk are the same folk every visit.
            if state.dwarves is None:
                from ..data import content
                state.dwarves = content.dwarf_npcs()
            gm = dwarftown.generate(state.seed, state.dwarves)
            state.log.add("Braziers. Voices. Ale-smell. This level is LIVED IN — "
                          "you've found Khazgrim, the dwarves' town under the mountain.",
                          (232, 200, 120))
        else:
            gm = dungeon.generate(_floor_seed(state, depth), state.dungeon_kind, depth)
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
