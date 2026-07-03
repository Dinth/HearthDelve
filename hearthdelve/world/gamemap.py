"""The surface world container: a grid of tile ids plus world metadata."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import tile


# Precomputed lookups indexed by tile id (built once at import).
_WALKABLE = np.array([t.walkable for t in tile.TILES], dtype=bool)
# See-through for FOV: walkable tiles, plus water (you can see across a lake).
_TRANSPARENT = np.array([t.walkable or t.kind == "water" for t in tile.TILES], dtype=bool)


@dataclass
class GameMap:
    width: int
    height: int
    tiles: np.ndarray                       # shape (width, height), uint8 tile ids
    spawn: tuple[int, int] = (0, 0)
    bed: tuple[int, int] | None = None
    bin: tuple[int, int] | None = None
    post_box: tuple[int, int] | None = None
    dungeons: list[tuple[int, int]] = field(default_factory=list)
    dungeon_kind: dict = field(default_factory=dict)   # entrance (x,y) -> kind
    # dungeon-only
    is_dungeon: bool = False
    depth: int = 0
    kind: str = ""
    stairs_up: tuple[int, int] | None = None
    stairs_down: tuple[int, int] | None = None
    visible: object = None       # np.bool array (dungeon FOV), or None on surface
    explored: object = None
    # planted crops, keyed by (x, y)
    crops: dict = field(default_factory=dict)
    # orchard trees, keyed by (x, y)
    trees: dict = field(default_factory=dict)
    # placed machines, keyed by (x, y)
    machines: dict = field(default_factory=dict)
    # village residents
    npcs: list = field(default_factory=list)
    # live dungeon monsters
    monsters: list = field(default_factory=list)
    # player's farm animals (persistent), keyed only by their own home anchor
    animals: list = field(default_factory=list)
    # tilled tiles of village farmhouse fields, re-stocked seasonally
    village_fields: list = field(default_factory=list)
    # interior tiles of cottage kitchen-gardens (owned by the adjacent resident)
    village_gardens: list = field(default_factory=list)
    # village buildings for look/identification: dicts {x,y,w,h,kind,village,owner}
    buildings: list = field(default_factory=list)
    # wild-mushroom spots (x, y, variety_tile_id, base_tile_id): only sprout in
    # summer/autumn, toggled by the day cycle.
    mushroom_spots: list = field(default_factory=list)
    # wildflower spots (x, y, colour_tile_id, base_tile_id): bloom in spring/
    # summer and drift day to day.
    flower_spots: list = field(default_factory=list)
    # picked berry shrubs regrowing: (x, y) -> [berry_tile_id, day_ready]. A
    # shrub is stripped to a plain bush when foraged and re-berries a few days on.
    berry_regrow: dict = field(default_factory=dict)
    # village name -> plaza centre (x, y), for the cheat teleport menu
    village_centers: dict = field(default_factory=dict)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def walkable(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        return bool(_WALKABLE[self.tiles[x, y]])

    def tile_at(self, x: int, y: int) -> tile.TileType:
        return tile.TILES[self.tiles[x, y]]

    def transparency(self) -> np.ndarray:
        """Boolean see-through grid for FOV (walkable tiles + water)."""
        return _TRANSPARENT[self.tiles]
