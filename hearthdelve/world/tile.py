"""Tile types.

The world map is a numpy array of ``uint8`` tile ids; ``TILES`` is the lookup
table from id -> :class:`TileType`. Rendering builds numpy glyph/fg/bg arrays
indexed by id for fast blitting (see engine/rendering.py).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TileType:
    name: str
    glyph: str          # single character drawn for this tile
    fg: tuple[int, int, int]
    bg: tuple[int, int, int]
    walkable: bool = True
    # short label shown when relevant (unused in M1, handy later)
    kind: str = "terrain"


# Registry. Index in this list IS the tile id stored in the map array, so
# ORDER MATTERS — only append, and keep the NAME->id map in sync.
TILES: list[TileType] = []
_BY_NAME: dict[str, int] = {}


def _add(t: TileType) -> int:
    tid = len(TILES)
    TILES.append(t)
    _BY_NAME[t.name] = tid
    return tid


def tid(name: str) -> int:
    """Tile id for a name (use at worldgen time)."""
    return _BY_NAME[name]


# --- Terrain (homestead / edge) ---------------------------------------------
GRASS       = _add(TileType("grass",      ".", (96, 150, 84),  (28, 48, 30)))
MEADOW      = _add(TileType("meadow",     ",", (120, 168, 92), (30, 52, 32)))
TALL_GRASS  = _add(TileType("tall_grass", '"', (132, 176, 96), (30, 54, 32)))
DIRT_PATH   = _add(TileType("path",       ".", (150, 126, 92), (52, 42, 30)))
SAND        = _add(TileType("sand",       ".", (196, 180, 128),(74, 66, 44)))

# --- Water -------------------------------------------------------------------
WATER       = _add(TileType("water",      "≈", (120, 170, 220), (24, 52, 88), walkable=False, kind="water"))
RIVER       = _add(TileType("river",      "~",      (120, 170, 220), (26, 58, 96), walkable=False, kind="water"))

# --- Flora -------------------------------------------------------------------
# Trees are PASSABLE on their own; varieties differ by glyph/colour. Axe -> wood.
TREE_OAK    = _add(TileType("oak",    "♣", (84, 132, 60),   (22, 42, 26), kind="tree"))
TREE_MAPLE  = _add(TileType("maple",  "♣", (172, 116, 58),  (30, 38, 24), kind="tree"))
TREE_BIRCH  = _add(TileType("birch",  "♣", (178, 198, 156), (26, 44, 30), kind="tree"))
TREE_POPLAR = _add(TileType("poplar", "♠", (120, 164, 94),  (22, 42, 26), kind="tree"))
TREE_WILLOW = _add(TileType("willow", "♣", (134, 170, 120), (24, 44, 30), kind="tree"))
TREE_PINE   = _add(TileType("pine",   "♠", (66, 112, 78),   (20, 38, 28), kind="tree"))
TREE_SPRUCE = _add(TileType("spruce", "♠", (58, 104, 86),   (18, 36, 28), kind="tree"))

# Foliage — dense overgrowth in groves; impassable until cleared with a machete.
FOLIAGE     = _add(TileType("foliage", "▓", (54, 112, 52), (20, 40, 24), walkable=False, kind="foliage"))

# Shrubs — impassable (machete only). Most are plain; fruit-bearing ones (rare)
# drop berries when cleared.
SHRUB            = _add(TileType("shrub",            "&", (96, 142, 72),  (24, 44, 28), walkable=False, kind="shrub"))
SHRUB_RASPBERRY  = _add(TileType("shrub_raspberry", "&", (198, 86, 102), (28, 40, 28), walkable=False, kind="shrub_berry"))
SHRUB_GOOSEBERRY = _add(TileType("shrub_gooseberry","&", (170, 196, 96), (26, 42, 28), walkable=False, kind="shrub_berry"))
SHRUB_CURRANT    = _add(TileType("shrub_currant",   "&", (160, 80, 150), (28, 38, 30), walkable=False, kind="shrub_berry"))
BUSH             = _add(TileType("bush",            "*", (108, 156, 80), (26, 46, 30)))

# Flowers — purely decorative blooms scattered on meadows (walkable).
FLOWER_RED    = _add(TileType("red flowers",    "*", (224, 96, 104), (30, 52, 32), kind="flower"))
FLOWER_YELLOW = _add(TileType("yellow flowers", "*", (236, 214, 96), (30, 52, 32), kind="flower"))
FLOWER_VIOLET = _add(TileType("violet flowers", "*", (190, 130, 220), (30, 52, 32), kind="flower"))
FLOWER_WHITE  = _add(TileType("white flowers",  "*", (236, 236, 224), (30, 52, 32), kind="flower"))

# Back-compat aliases.
TREE = TREE_OAK
PINE = TREE_PINE

# --- Wilds (T3) --------------------------------------------------------------
MOOR        = _add(TileType("moor",       ":", (120, 116, 96), (40, 40, 36)))
FOG_GRASS   = _add(TileType("fog_grass",  '"', (104, 116, 110),(34, 42, 40)))
RUINS_FLOOR = _add(TileType("ruins_floor","." , (130, 124, 118),(40, 38, 36)))
RUINS_WALL  = _add(TileType("ruins_wall", "▒", (150, 144, 134),(46, 44, 40), walkable=False, kind="wall"))
ROCK        = _add(TileType("rock",       "▒", (120, 116, 112),(40, 38, 36), walkable=False, kind="wall"))
ORE_VEIN    = _add(TileType("ore_vein",   "*", (236, 196, 110),(48, 42, 32), walkable=False, kind="ore"))

# --- Homestead built features ------------------------------------------------
HOUSE_WALL  = _add(TileType("house_wall", "#", (170, 130, 96), (44, 32, 24), walkable=False, kind="wall"))
HOUSE_FLOOR = _add(TileType("house_floor",".", (150, 130, 110),(40, 32, 26)))
DOOR        = _add(TileType("door",       "+", (210, 170, 110),(54, 40, 26), kind="door"))
BED         = _add(TileType("bed",        "≡", (210, 150, 160),(58, 36, 44), kind="bed"))
SHIP_BIN    = _add(TileType("shipping_bin","☐", (200, 170, 110),(48, 40, 26), walkable=False, kind="bin"))
FENCE       = _add(TileType("fence",      "│", (160, 130, 92), (28, 48, 30), walkable=False, kind="fence"))
TILLED      = _add(TileType("tilled",     "≡", (120, 86, 60),  (52, 36, 24), kind="soil"))

# --- Village props -----------------------------------------------------------
WELL    = _add(TileType("well",     "o", (180, 190, 205), (50, 54, 60), walkable=False, kind="well"))
LAMP    = _add(TileType("lamp",     "î", (245, 210, 130), (30, 40, 30), walkable=False, kind="lamp"))
STALL   = _add(TileType("stall",    "∩", (214, 96, 84),   (44, 34, 26), walkable=False, kind="stall"))
SIGNPOST= _add(TileType("signpost", "‡", (188, 150, 104), (40, 50, 34), walkable=False, kind="signpost"))
# Paved streets & squares — walkable and count as road (halve travel time).
COBBLE  = _add(TileType("cobble",   "·", (168, 166, 170), (78, 78, 84), kind="road"))
STATUE  = _add(TileType("statue",   "Ψ", (200, 202, 210), (70, 70, 78), walkable=False, kind="statue"))

# --- Building interiors (kitchens, bedrooms, shops, inn, temple) -------------
HEARTH  = _add(TileType("hearth",   "Ω", (236, 150, 80),  (52, 34, 26), walkable=False, kind="hearth"))
TABLE   = _add(TileType("table",    "π", (176, 140, 100), (44, 36, 28), walkable=False, kind="furniture"))
COUNTER = _add(TileType("counter",  "=", (188, 152, 104), (46, 38, 28), walkable=False, kind="counter"))
BARREL  = _add(TileType("barrel",   "θ", (168, 128, 84),  (44, 36, 28), walkable=False, kind="barrel"))
ALTAR   = _add(TileType("altar",    "♦", (240, 224, 150), (48, 44, 34), walkable=False, kind="altar"))

# --- Graveyard ---------------------------------------------------------------
GRAVE   = _add(TileType("grave",    "†", (176, 178, 184), (34, 44, 34), walkable=False, kind="grave"))

# --- Coast -------------------------------------------------------------------
BOAT    = _add(TileType("boat",     "∪", (196, 150, 96),  (26, 58, 96), walkable=False, kind="boat"))

# --- Beekeeping --------------------------------------------------------------
# A wild bee hive, found rarely in the deep woods (forage with g for honey/wax).
WILD_HIVE = _add(TileType("wild_hive", "⌂", (222, 178, 84), (26, 40, 24), walkable=False, kind="hive"))

# --- Wild mushrooms (surface forage) -----------------------------------------
# One glyph for all mushrooms; the species differ only by colour.
BUTTON_MUSHROOM  = _add(TileType("button_mushroom",  "τ", (224, 216, 200), (28, 48, 30), kind="mushroom"))
PARASOL_MUSHROOM = _add(TileType("parasol_mushroom", "τ", (204, 182, 150), (28, 48, 30), kind="mushroom"))
BOLETE           = _add(TileType("bolete",           "τ", (170, 116, 74),  (26, 44, 28), kind="mushroom"))
CHANTERELLE      = _add(TileType("chanterelle",      "τ", (228, 178, 84),  (26, 44, 28), kind="mushroom"))

# --- Roads & bridges ---------------------------------------------------------
# Roads are walkable and halve travel time; bridges carry a road over water.
ROAD        = _add(TileType("road",   "·", (150, 132, 96), (72, 62, 46), kind="road"))
BRIDGE      = _add(TileType("bridge", "=", (162, 120, 76), (40, 54, 82), kind="bridge"))

# --- Sites -------------------------------------------------------------------
DUNGEON_DOWN = _add(TileType("dungeon_down", ">", (245, 235, 200), (32, 28, 24), kind="stairs"))

# --- Dungeon interior --------------------------------------------------------
DUNGEON_WALL  = _add(TileType("dungeon_wall",  "#", (122, 110, 98), (30, 26, 23), walkable=False, kind="wall"))
DUNGEON_FLOOR = _add(TileType("dungeon_floor", ".", (150, 138, 118), (32, 28, 25), kind="terrain"))
STAIRS_UP     = _add(TileType("stairs_up",     "<", (245, 235, 200), (34, 30, 26), kind="stairs_up"))
GEM_VEIN      = _add(TileType("gem_vein",      "◊", (120, 214, 224), (40, 42, 52), walkable=False, kind="gem"))
GOLD_PILE     = _add(TileType("gold_pile",     "$", (244, 216, 110), (40, 36, 24), kind="gold"))
# Dungeon texture: chests, hazards, traps, cave fungus.
CHEST         = _add(TileType("chest",         "■", (214, 172, 92),  (44, 34, 22), walkable=False, kind="chest"))
RUBBLE        = _add(TileType("rubble",        "░", (128, 118, 104), (30, 27, 24), kind="rubble"))
TRAP          = _add(TileType("trap",          "^", (214, 96, 92),   (34, 28, 26), kind="trap"))
# A hidden trap is drawn exactly like the dungeon floor until spotted/sprung.
TRAP_HIDDEN   = _add(TileType("trap_hidden",   ".", (150, 138, 118), (32, 28, 25), kind="trap"))
MUSHROOM      = _add(TileType("mushroom",      "τ", (206, 132, 176), (30, 30, 28), kind="mushroom"))
# Glimmerwood: a rare glowing underground grove of wispwood trees & giant caps.
GLOW_MOSS     = _add(TileType("glow_moss",      ",", (110, 196, 150), (26, 46, 40), kind="terrain"))
WISPWOOD      = _add(TileType("wispwood",       "♠", (120, 214, 170), (20, 34, 30), kind="wispwood"))
GLOWCAP       = _add(TileType("glowcap",        "î", (150, 236, 222), (26, 44, 42), kind="glowcap"))

TILE_COUNT = len(TILES)
