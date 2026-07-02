"""Data-driven content registry — the single source of truth for stats.

The encyclopedia (help screen) and the gameplay systems both read from these
tables, so anything added here shows up in-game *and* in the compendium with
no extra wiring. As crops, monsters, machines, and recipes come online in
M2-M4 they get appended here.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..engine import constants as C
from ..entities import items
from ..entities.items import Item
from ..entities.npc import NPC


# --- Tools & weapon stats ----------------------------------------------------
@dataclass(frozen=True)
class ToolStat:
    verb: str          # what the tool does
    stamina: int       # exertion per use
    seconds: int       # in-game time per use
    target: str        # what it acts on
    yields: str = ""   # what it produces


TOOL_STATS: dict[Item, ToolStat] = {
    items.HOE:          ToolStat("Till",  *C.TILL_COST,  "grass / meadow", "tilled soil"),
    items.WATERING_CAN: ToolStat("Water", *C.WATER_COST, "tilled soil",    "growth"),
    items.AXE:          ToolStat("Chop",  *C.CHOP_COST,  "trees",          "wood"),
    items.PICKAXE:      ToolStat("Mine",  *C.MINE_COST,  "rock / ore vein","stone, ore, gems"),
    items.MACHETE:      ToolStat("Clear", *C.MACHETE_COST, "foliage / shrubs", "fiber, berries"),
    items.FISHING_ROD:  ToolStat("Fish",  *C.FISH_COST,  "water tiles",    "fish"),
}


@dataclass(frozen=True)
class WeaponStat:
    atk: int
    note: str = ""


WEAPON_STATS: dict[Item, WeaponStat] = {
    items.SWORD: WeaponStat(atk=C.SWORD_ATK, note="bump-attack in the wilds"),
}


# --- Crops -------------------------------------------------------------------
@dataclass(frozen=True)
class Crop:
    name: str
    glyph: str                      # mature glyph drawn on the soil
    color: tuple[int, int, int]     # mature colour
    season: str
    days_to_mature: int
    regrows: bool
    sell_price: int
    seed: Item
    produce: Item
    category: str = "vegetable"     # "vegetable" | "fruit" — gates artisan goods
    regrow_days: int = 0            # if regrows, days to re-ripen after harvest
    desc: str = ""


PARSNIP = Crop(
    name="Parsnip", glyph="♠", color=(224, 206, 148), season="Spring",
    days_to_mature=4, regrows=False, sell_price=35,
    seed=items.PARSNIP_SEEDS, produce=items.PARSNIP,
    desc="A hardy spring root. The classic first crop.",
)
POTATO = Crop(
    name="Potato", glyph="o", color=(176, 134, 92), season="Spring",
    days_to_mature=6, regrows=False, sell_price=80,
    seed=items.POTATO_SEEDS, produce=items.POTATO,
    desc="An earthy spring staple.",
)
CAULIFLOWER = Crop(
    name="Cauliflower", glyph="%", color=(236, 234, 218), season="Spring",
    days_to_mature=12, regrows=False, sell_price=175,
    seed=items.CAULIFLOWER_SEEDS, produce=items.CAULIFLOWER,
    desc="Slow to grow, but a prized head.",
)
PUMPKIN = Crop(
    name="Pumpkin", glyph="O", color=(232, 142, 56), season="Fall",
    days_to_mature=13, regrows=False, sell_price=320,
    seed=items.PUMPKIN_SEEDS, produce=items.PUMPKIN,
    desc="The great autumn harvest.",
)

# Fruits — the only inputs for jam (jar) and wine (keg).
TOMATO = Crop(
    name="Tomato", glyph="♥", color=(212, 74, 62), season="Summer",
    days_to_mature=11, regrows=True, sell_price=60, regrow_days=4,
    category="fruit", seed=items.TOMATO_SEEDS, produce=items.TOMATO,
    desc="A summer vine fruit that keeps fruiting.",
)
STRAWBERRY = Crop(
    name="Strawberry", glyph="♦", color=(224, 72, 96), season="Spring",
    days_to_mature=8, regrows=True, sell_price=120, regrow_days=4,
    category="fruit", seed=items.STRAWBERRY_SEEDS, produce=items.STRAWBERRY,
    desc="A spring berry that re-fruits.",
)
BLUEBERRY = Crop(
    name="Blueberry", glyph="♦", color=(96, 124, 220), season="Summer",
    days_to_mature=10, regrows=True, sell_price=80, regrow_days=4,
    category="fruit", seed=items.BLUEBERRY_SEEDS, produce=items.BLUEBERRY,
    desc="Clusters of summer berries.",
)
GRAPE = Crop(
    name="Grape", glyph="♦", color=(158, 96, 204), season="Fall",
    days_to_mature=9, regrows=True, sell_price=80, regrow_days=3,
    category="fruit", seed=items.GRAPE_SEEDS, produce=items.GRAPE,
    desc="Fall vine fruit; re-fruits.",
)

CROPS: list[Crop] = [PARSNIP, POTATO, CAULIFLOWER, PUMPKIN,
                     TOMATO, STRAWBERRY, BLUEBERRY, GRAPE]
SEED_TO_CROP: dict[Item, Crop] = {c.seed: c for c in CROPS}
CROP_BY_NAME: dict[str, Crop] = {c.name: c for c in CROPS}


def crops_in_season(season: str) -> list[Crop]:
    """Field crops that grow in the given season (for stocking village fields)."""
    return [c for c in CROPS if c.season == season]
# produce item -> "fruit" | "vegetable"
PRODUCE_CATEGORY: dict[Item, str] = {c.produce: c.category for c in CROPS}
# fruits not grown as field crops (shrubs & orchard trees) still count as fruit
_EXTRA_FRUIT = {items.RASPBERRY, items.GOOSEBERRY, items.CURRANT,
                items.CHERRY, items.PEACH, items.APPLE, items.ORANGE}


# --- Orchard trees -----------------------------------------------------------
@dataclass(frozen=True)
class TreeDef:
    name: str
    sapling: Item
    fruit: Item
    fruit_color: tuple[int, int, int]
    season: str
    days_to_mature: int
    desc: str = ""


TREES: list[TreeDef] = [
    TreeDef("Cherry", items.CHERRY_SAPLING, items.CHERRY, (224, 72, 96), "Spring", 7),
    TreeDef("Peach", items.PEACH_SAPLING, items.PEACH, (236, 150, 90), "Summer", 7),
    TreeDef("Apple", items.APPLE_SAPLING, items.APPLE, (216, 70, 62), "Fall", 8),
    TreeDef("Orange", items.ORANGE_SAPLING, items.ORANGE, (236, 150, 60), "Winter", 8),
]
SAPLING_TO_TREE: dict[Item, TreeDef] = {t.sapling: t for t in TREES}
TREE_BY_NAME: dict[str, TreeDef] = {t.name: t for t in TREES}

# berry-shrub tile name -> the fruit it drops when cleared
SHRUB_FRUIT: dict[str, Item] = {
    "shrub_raspberry": items.RASPBERRY,
    "shrub_gooseberry": items.GOOSEBERRY,
    "shrub_currant": items.CURRANT,
}


def is_fruit(produce: Item) -> bool:
    return PRODUCE_CATEGORY.get(produce) == "fruit" or produce in _EXTRA_FRUIT


# --- Machines (placed; process inputs over time) -----------------------------
@dataclass(frozen=True)
class MachineDef:
    kind: str
    name: str
    glyph: str
    color: tuple[int, int, int]
    minutes: int                  # in-game minutes to process a batch
    accepts: str                  # "ore" | "crop" | "" (sprinkler: none)
    output: Item | None
    desc: str = ""


MACHINES: dict[str, MachineDef] = {
    "furnace": MachineDef("furnace", "Furnace", "F", (224, 132, 70), 120, "ore",
                          items.COPPER_BAR, "Smelts ore + coal into bars (alloys need two ores)."),
    "jar":     MachineDef("jar", "Preserves Jar", "J", (202, 170, 110), 240, "crop",
                          None, "Fruit->jam, veg->pickles, eel->jellied eel."),
    "keg":     MachineDef("keg", "Keg", "K", (172, 110, 72), 480, "fruit",
                          items.WINE, "Ferments fruit into wine."),
    "sprinkler": MachineDef("sprinkler", "Sprinkler", "¤", (120, 188, 222), 0, "",
                            None, "Waters the 4 neighbouring tiles each morning."),
}


# --- Recipes (the crafting / build / cook menu) ------------------------------
@dataclass(frozen=True)
class Recipe:
    name: str
    kind: str                     # "build" | "cook" | "item"
    inputs: tuple                 # ((Item, qty), ...)
    machine: str = ""             # for build: which MachineDef to place
    energy: int = 0               # for cook: energy restored
    output: Item | None = None    # for item: what it makes
    out_qty: int = 1
    desc: str = ""


RECIPES: list[Recipe] = [
    Recipe("Furnace", "build", ((items.STONE, 5),), machine="furnace",
           desc="Smelts ore into bars."),
    Recipe("Preserves Jar", "build", ((items.WOOD, 10),), machine="jar",
           desc="Crops -> jam."),
    Recipe("Keg", "build", ((items.WOOD, 10), (items.COPPER_BAR, 1)), machine="keg",
           desc="Crops -> wine."),
    Recipe("Sprinkler", "build", ((items.COPPER_BAR, 1),), machine="sprinkler",
           desc="Auto-waters nearby soil."),
    Recipe("Parsnip Soup", "cook", ((items.PARSNIP, 2),), energy=45,
           desc="A warming bowl. Restores energy."),
    Recipe("Roasted Veg", "cook", ((items.PARSNIP, 1), (items.POTATO, 1)), energy=70,
           desc="Hearty fare. Restores more energy."),
    Recipe("Bomb", "item", ((items.COAL, 1), (items.FIBER, 2)), output=items.BOMB, out_qty=1,
           desc="Throw with 'a' to harm monsters and shatter rock."),
    Recipe("Fish Stew", "cook", ((items.PERCH, 1), (items.PARSNIP, 1)), energy=60,
           desc="Hearty stew. Restores plenty of energy."),
    Recipe("Grilled Trout", "cook", ((items.TROUT, 1),), energy=45,
           desc="Simple and restorative."),
    Recipe("Mushroom Stew", "cook", ((items.CAVE_MUSHROOM, 2),), energy=65,
           desc="Earthy cave-fungus stew. Restores plenty of energy."),
    Recipe("Glowcap Broth", "cook", ((items.GLOWCAP, 1),), energy=95,
           desc="A radiant broth from Glimmerwood caps. Restores a great deal of energy."),
    Recipe("Sauteed Mushrooms", "cook", ((items.BUTTON_MUSHROOM, 2),), energy=45,
           desc="Wild field mushrooms in butter. Restores energy."),
    Recipe("Chanterelle Saute", "cook", ((items.CHANTERELLE, 1),), energy=60,
           desc="Golden chanterelles, gently fried. A forager's treat."),
    Recipe("Bolete Broth", "cook", ((items.BOLETE, 1), (items.PARASOL_MUSHROOM, 1)), energy=70,
           desc="A rich woodland mushroom broth. Very restorative."),
]


# --- Fishing -----------------------------------------------------------------
@dataclass(frozen=True)
class Fish:
    item: Item
    weight: int              # higher = more common
    seasons: tuple           # () means all year


FISH: list[Fish] = [
    # year-round
    Fish(items.MINNOW, 40, ()),
    Fish(items.PERCH, 26, ()),
    Fish(items.CARP, 10, ()),
    Fish(items.CATFISH, 3, ()),
    # spring
    Fish(items.SMELT, 30, ("Spring",)),
    Fish(items.TROUT, 18, ("Spring", "Fall")),
    Fish(items.BREAM, 20, ("Spring", "Summer")),
    # summer
    Fish(items.SUNFISH, 28, ("Summer",)),
    Fish(items.PIKE, 12, ("Summer",)),
    # fall
    Fish(items.SALMON, 16, ("Fall",)),
    # winter
    Fish(items.ICEFISH, 26, ("Winter",)),
    Fish(items.STURGEON, 4, ("Winter",)),
]
FISH_CATCH_CHANCE = 0.75

# Distinct catches from underground lakes (not seasonal).
CAVE_FISH: list[tuple[Item, int]] = [
    (items.CAVE_BASS, 30), (items.EEL, 22), (items.BLINDFISH, 30), (items.GLOWFISH, 6),
]


def fish_in_season(season: str) -> list[tuple[Item, int]]:
    return [(f.item, f.weight) for f in FISH if not f.seasons or season in f.seasons]


# --- Monsters ----------------------------------------------------------------
@dataclass(frozen=True)
class Monster:
    name: str
    glyph: str
    color: tuple[int, int, int]
    hp: int
    atk: int
    defense: int
    speed: int
    behavior: str          # "chase" | "erratic" | "charge"
    min_depth: int         # only appears at/after this dungeon floor
    desc: str = ""
    boss: bool = False


MONSTERS: list[Monster] = [
    Monster("Cave Slime", "s", (120, 200, 130), 8, 2, 0, 1, "chase", 1,
            "Slow but persistent — easy to outrun."),
    Monster("Bat", "w", (172, 150, 214), 5, 2, 0, 3, "erratic", 1,
            "Flits about erratically; flees when hurt."),
    Monster("Boar", "b", (200, 150, 112), 16, 4, 1, 2, "charge", 2,
            "Tougher; charges once it's roused."),
]

# Bosses appear on deep floors and are spawned by special logic (not the pool).
BOSSES: list[Monster] = [
    Monster("Cave Troll", "T", (214, 120, 92), 44, 8, 3, 1, "charge", 4,
            "A hulking cave troll — slow, but it hits like a landslide.", boss=True),
]


# --- Surface wildlife --------------------------------------------------------
# Harmless creatures that roam the overworld to give it life. "skittish" ones
# bolt when you get near or strike them; "defensive" ones ignore you until hit,
# then turn and fight. Diet decides what they nibble: sown crops (only reachable
# where there's no fence) or ripe berry shrubs.
@dataclass(frozen=True)
class Critter:
    name: str
    glyph: str
    color: tuple[int, int, int]
    hp: int
    atk: int
    defense: int
    speed: int
    behavior: str          # "skittish" | "defensive"
    diet: str              # "" | "crops" | "berries"
    desc: str = ""
    seasons: tuple = ()    # active seasons ("" = all year round)


_NO_WINTER = ("Spring", "Summer", "Fall")

WILDLIFE: list[Critter] = [
    Critter("Rabbit",    "r", (216, 190, 158),  3, 0, 0, 3, "skittish", "crops",
            "Timid — bolts the moment you draw near. Loves a tender crop."),
    Critter("Deer",      "d", (198, 164, 116), 10, 0, 0, 2, "skittish", "crops",
            "Graceful and shy; will graze an unfenced field down to nothing. Gone by winter.",
            seasons=_NO_WINTER),
    Critter("Fox",       "f", (222, 132, 66),   6, 0, 0, 3, "skittish", "",
            "A flash of russet through the grass — gone before you blink."),
    Critter("Squirrel",  "q", (188, 120, 88),   3, 0, 0, 3, "skittish", "berries",
            "Chatters and darts off; raids berry shrubs. Holes up for the winter.",
            seasons=_NO_WINTER),
    Critter("Wild Boar", "b", (150, 122, 100), 14, 4, 1, 2, "defensive", "crops",
            "Roots up crops and minds its own business — until provoked."),
]


# --- Villages, NPCs, shops (M3b) ---------------------------------------------
def village_npcs() -> dict[str, list[NPC]]:
    """Fresh NPC instances per game, grouped by village (positions set later).

    The first NPCs of each village fill the special buildings by role
    (shopkeeper→store, blacksmith→smithy, innkeeper→inn, priest→temple,
    farmer→farmhouse); the rest take cottages.
    """
    return {
        "Mossford": [
            NPC("Marda", "M", (236, 196, 150), shop="general", role="shopkeeper",
                blurbs=("Welcome to Mossford! The store's always open by day.",
                        "Drop goods in your bin and I'll have gold for you by morning.",
                        "A little rain's good for the fields, dear."),
                loves=(items.JAM, items.PICKLES, items.WINE),
                likes=(items.PARSNIP, items.POTATO, items.CAULIFLOWER, items.STRAWBERRY),
                dislikes=(items.WOOD, items.STONE, items.COAL),
                bio="Runs the Mossford general store on the market square."),
            NPC("Hollis", "H", (224, 168, 96), shop=None, role="innkeeper",
                blurbs=("Pull up a stool — the hearth's warm and the ale's cold.",
                        "Storm brewing? Half the village'll be under my roof by dusk.",
                        "A traveller hears everything, eventually."),
                loves=(items.WINE, items.GRAPE_WINE, items.JELLIED_EEL),
                likes=(items.JAM, items.PICKLES), dislikes=(items.STONE,),
                bio="Keeps the Mossford inn; tends the taproom day and night."),
            NPC("Sister Ivy", "I", (214, 196, 224), shop=None, role="priest",
                blurbs=("Peace to you, traveller. The shrine is always open.",
                        "The seasons turn; be grateful for each in its turn.",
                        "On the first of the season we gather to give thanks."),
                loves=(items.WINE, items.JAM, items.DIAMOND),
                likes=(items.STRAWBERRY, items.BLUEBERRY), dislikes=(items.COAL,),
                bio="Tends the shrine of Mossford; found at the altar by day."),
            NPC("Gilda", "G", (210, 176, 120), shop=None, role="farmer",
                blurbs=("Weather permitting, I'm out in the rows till dusk.",
                        "Nothing beats soil under your nails and sun on your back.",
                        "Come winter there's little to do but mend and wait."),
                loves=(items.PARSNIP, items.CAULIFLOWER, items.PUMPKIN),
                likes=(items.POTATO, items.TOMATO), dislikes=(items.STONE,),
                bio="Works the farmhouse fields at the edge of Mossford."),
            NPC("Tomas", "T", (196, 158, 110), shop=None, role="carpenter",
                blurbs=("Good timber, that. I could build you something one day.",
                        "Stone and wood — that's how a homestead grows."),
                loves=(items.WOOD,), likes=(items.STONE,), dislikes=(items.JAM,),
                bio="Mossford's carpenter; found among the timber and tools."),
            NPC("Wrenna", "W", (170, 200, 150), shop=None, role="forager",
                blurbs=("The wild berries make the loveliest preserves.",
                        "Forage the edges of the woods — you'll be surprised."),
                loves=(items.RASPBERRY, items.GOOSEBERRY, items.CURRANT),
                likes=(items.FIBER, items.CAULIFLOWER), dislikes=(items.STONE,),
                bio="Mossford's herbalist; wanders the meadows and wood-edges."),
            NPC("Pip", "p", (236, 214, 150), shop=None, role="villager",
                blurbs=("Wanna see the frog I caught? ...Oh. Maybe later.",
                        "When I grow up I'm gonna have the biggest farm ever!"),
                loves=(items.STRAWBERRY, items.JAM),
                likes=(items.RASPBERRY, items.BLUEBERRY), dislikes=(items.WOOD,),
                bio="A village child, forever underfoot around the square."),
        ],
        "Cinderhope": [
            NPC("Bron", "B", (224, 150, 110), shop="blacksmith", role="blacksmith",
                blurbs=("Bring me ore and bars and I'll sharpen your tools.",
                        "Wooden tools? We'll fix that. Bronze and up, that's my trade."),
                loves=(items.COPPER_BAR, items.COAL),
                likes=(items.COPPER_ORE, items.STONE), dislikes=(items.WINE,),
                bio="The Cinderhope blacksmith; upgrades tools at his forge."),
            NPC("Mabel", "A", (232, 176, 132), shop=None, role="innkeeper",
                blurbs=("Mind the step — floor's uneven since the old days.",
                        "Miners drink deep after a long shift, bless them.",
                        "There's always a bed and a bowl at the Cinderhope inn."),
                loves=(items.GRAPE_WINE, items.WINE, items.JELLIED_EEL),
                likes=(items.JAM, items.PICKLES), dislikes=(items.STONE,),
                bio="Runs the Cinderhope taproom and lets its rooms."),
            NPC("Father Ansel", "F", (196, 200, 224), shop=None, role="priest",
                blurbs=("The old chapel has stood longer than the outpost, they say.",
                        "Rest a moment. Even miners must look up sometimes."),
                loves=(items.WINE, items.SAPPHIRE, items.JAM),
                likes=(items.APPLE, items.CHERRY), dislikes=(items.COAL,),
                bio="Keeps the old chapel of Cinderhope; found by its altar."),
            NPC("Old Pell", "P", (150, 180, 200), shop=None, role="fisher",
                blurbs=("The river's kind to a patient soul.",
                        "Cast a line sometime — once you've a rod, mind."),
                loves=(items.WINE, items.GRAPE_WINE),
                likes=(items.RASPBERRY,), dislikes=(items.STONE,),
                bio="An old fisher; usually by the water near Cinderhope."),
            NPC("Garret", "R", (200, 168, 132), shop=None, role="villager",
                blurbs=("Twenty years down the shafts and my back knows every one.",
                        "Copper's steady, but it's silver a man dreams of."),
                loves=(items.COPPER_BAR, items.IRON_BAR, items.COAL),
                likes=(items.STONE, items.COPPER_ORE), dislikes=(items.JAM,),
                bio="A weathered miner; drinks at the taproom by the forge."),
            NPC("Nessa", "N", (206, 180, 200), shop=None, role="villager",
                blurbs=("Fibre and patience — that's a good bolt of cloth.",
                        "Winter's my busy season, at the loom by the fire."),
                loves=(items.FIBER, items.WINE),
                likes=(items.WOOD, items.CURRANT), dislikes=(items.STONE,),
                bio="The Cinderhope weaver; keeps a cottage off the square."),
            NPC("Sable", "S", (200, 170, 220), shop=None, role="trader",
                blurbs=("Rare goods, fair prices — when I'm passing through.",
                        "A fine vintage fetches a fine coin out east."),
                loves=(items.GRAPE_WINE, items.WINE),
                likes=(items.JAM, items.PICKLES), dislikes=(items.FIBER,),
                bio="A travelling trader lodging in Cinderhope."),
        ],
        "Saltmere": [
            NPC("Coralie", "C", (150, 200, 210), shop=None, role="innkeeper",
                blurbs=("Salt air and a warm fire — best cure there is.",
                        "The boats come in at dusk; that's when it gets lively.",
                        "Storm's coming? The fishers can smell it before I can."),
                loves=(items.JELLIED_EEL, items.WINE, items.GRAPE_WINE),
                likes=(items.JAM, items.PICKLES), dislikes=(items.STONE,),
                bio="Keeps the dockside inn at Saltmere; warm to every soul."),
            NPC("Bryn", "b", (140, 180, 208), shop=None, role="fisher",
                blurbs=("Out before dawn, in before dark — that's the fisher's day.",
                        "Rough seas today. The little boats stay moored."),
                loves=(items.GRAPE_WINE, items.WINE),
                likes=(items.PICKLES, items.JELLIED_EEL), dislikes=(items.STONE,),
                bio="A Saltmere fisher; works the piers when the sea allows."),
            NPC("Marli", "m", (168, 196, 210), shop=None, role="fisher",
                blurbs=("Mended forty nets this week and my fingers know it.",
                        "The catch is good when the currant blossoms fall."),
                loves=(items.JAM, items.STRAWBERRY),
                likes=(items.BLUEBERRY, items.CURRANT), dislikes=(items.COAL,),
                bio="A Saltmere fisher and net-mender by the shore."),
            NPC("Doran", "D", (128, 168, 200), shop=None, role="fisher",
                blurbs=("Forty years on the water and she still surprises me.",
                        "Learn the tides, lad, and the tides will feed you."),
                loves=(items.WINE, items.GRAPE_WINE),
                likes=(items.CHERRY, items.APPLE), dislikes=(items.WOOD,),
                bio="Saltmere's oldest fisher; harbour-master of a sort."),
            NPC("Nan", "n", (196, 190, 208), shop=None, role="villager",
                blurbs=("Every rope on that shore has passed through my hands.",
                        "Salt gets into everything, cloth most of all."),
                loves=(items.FIBER, items.WINE),
                likes=(items.WOOD, items.CURRANT), dislikes=(items.STONE,),
                bio="Saltmere's rope- and net-maker; keeps a shore cottage."),
        ],
    }


# General store stock: (seed, buy price)
GENERAL_STOCK: list[tuple[Item, int]] = [
    (items.PARSNIP_SEEDS, 20), (items.POTATO_SEEDS, 50), (items.CAULIFLOWER_SEEDS, 80),
    (items.PUMPKIN_SEEDS, 100), (items.TOMATO_SEEDS, 50), (items.STRAWBERRY_SEEDS, 100),
    (items.BLUEBERRY_SEEDS, 80), (items.GRAPE_SEEDS, 60),
    (items.CHERRY_SAPLING, 600), (items.PEACH_SAPLING, 600),
    (items.APPLE_SAPLING, 700), (items.ORANGE_SAPLING, 700),
]
# Blacksmith also sells fuel/metal: (item, buy price)
BLACKSMITH_STOCK: list[tuple[Item, int]] = [
    (items.COAL, 25), (items.COPPER_BAR, 120),
]


# tool tier -> the bar needed to reach the NEXT tier (index = current tier)
#   Wooden->Bronze, Bronze->Iron, Iron->Steel, Steel->Adamantium, Adamantium->Mithril
TIER_BAR = [items.BRONZE_BAR, items.IRON_BAR, items.STEEL_BAR,
            items.ADAMANTIUM_BAR, items.MITHRIL_BAR]


def upgrade_cost(tier: int) -> tuple[int, object, int]:
    """(gold, bar item, count) to upgrade a tool from `tier` to tier+1."""
    return 250 * (tier + 1), TIER_BAR[tier], 2 + tier


# --- ores & gems -------------------------------------------------------------
def _weighted(table, rng):
    total = sum(w for _, w in table)
    r = rng.uniform(0, total)
    acc = 0.0
    for item, w in table:
        acc += w
        if r <= acc:
            return item
    return table[0][0]


def _ore_band(depth: int):
    if depth <= 1:
        return [(items.COPPER_ORE, 50), (items.TIN_ORE, 50)]
    if depth <= 3:
        return [(items.COPPER_ORE, 22), (items.TIN_ORE, 22),
                (items.IRON_ORE, 42), (items.SILVER_ORE, 14)]
    if depth <= 5:
        return [(items.IRON_ORE, 24), (items.SILVER_ORE, 30), (items.GOLD_ORE, 24),
                (items.ADAMANTITE_ORE, 16), (items.TIN_ORE, 6)]
    return [(items.SILVER_ORE, 14), (items.GOLD_ORE, 24), (items.ADAMANTITE_ORE, 30),
            (items.MITHRIL_ORE, 26), (items.IRON_ORE, 6)]


def ore_for_depth(depth: int, rng) -> object:
    return _weighted(_ore_band(depth), rng)


GEMS = [(items.AMETHYST, 30), (items.TOPAZ, 26), (items.EMERALD, 20),
        (items.RUBY, 14), (items.SAPPHIRE, 8), (items.DIAMOND, 4)]


def random_gem(rng) -> object:
    return _weighted(GEMS, rng)


# --- dungeon texture: monster reagent drops & treasure chests ----------------
# monster name -> list of (item, drop chance)
MONSTER_DROPS: dict[str, list] = {
    "Cave Slime": [(items.SLIME_GEL, 0.7)],
    "Bat":        [(items.BAT_WING, 0.6)],
    "Boar":       [(items.BOAR_HIDE, 0.5)],
    "Cave Troll": [(items.BOAR_HIDE, 1.0), (items.COAL, 1.0)],
}


def monster_drops(name: str, rng) -> list:
    """Roll a slain creature's reagent drops (list of items)."""
    out = []
    for item, chance in MONSTER_DROPS.get(name, ()):
        if rng.random() < chance:
            out.append(item)
    return out


def chest_loot(depth: int, rng) -> tuple[int, list]:
    """Contents of a dungeon chest: (gold, [items]). Richer the deeper you go."""
    gold = rng.randint(30, 70) + depth * 15
    items_out = []
    # a metal bar or ore for the depth
    items_out.append(ore_for_depth(depth, rng))
    roll = rng.random()
    if roll < 0.35:                       # a gem
        items_out.append(random_gem(rng))
    elif roll < 0.6:                      # a couple of bombs
        items_out.append(items.BOMB)
    if rng.random() < 0.4:                # a cave snack
        items_out.append(items.CAVE_MUSHROOM)
    return gold, items_out


# Furnace recipes: (bar produced, {ore/fuel: qty}). Alloys need two ores.
FURNACE_RECIPES = [
    (items.BRONZE_BAR,     {items.COPPER_ORE: 1, items.TIN_ORE: 1, items.COAL: 1}),
    (items.STEEL_BAR,      {items.IRON_ORE: 1, items.COAL: 2}),
    (items.COPPER_BAR,     {items.COPPER_ORE: 1, items.COAL: 1}),
    (items.IRON_BAR,       {items.IRON_ORE: 1, items.COAL: 1}),
    (items.SILVER_BAR,     {items.SILVER_ORE: 1, items.COAL: 1}),
    (items.GOLD_BAR,       {items.GOLD_ORE: 1, items.COAL: 1}),
    (items.ADAMANTIUM_BAR, {items.ADAMANTITE_ORE: 1, items.COAL: 1}),
    (items.MITHRIL_BAR,    {items.MITHRIL_ORE: 1, items.COAL: 1}),
]


# --- Goals / journal ---------------------------------------------------------
@dataclass(frozen=True)
class Quest:
    id: str
    title: str
    desc: str
    gold: int
    check: object          # callable(state) -> bool


def _hearts(state, n: int) -> bool:
    return any(npc.friendship >= n * 100 for npc in state.surface.npcs) if state.surface else False


QUESTS: list[Quest] = [
    Quest("harvest", "A Fresh Start", "Harvest your first crop.", 100,
          lambda s: s.stats.get("crops_harvested", 0) >= 1),
    Quest("wood", "Woodcutter", "Chop 5 trees for wood.", 100,
          lambda s: s.stats.get("trees_chopped", 0) >= 5),
    Quest("upgrade", "Tools of the Trade", "Upgrade a tool at Bron's forge.", 150,
          lambda s: any(t > 0 for t in s.player.tool_tier.values())),
    Quest("friend", "Good Neighbours", "Reach 2 hearts with a villager.", 150,
          lambda s: _hearts(s, 2)),
    Quest("artisan", "The Good Stuff", "Make an artisan good in a machine.", 150,
          lambda s: s.stats.get("artisan_made", 0) >= 1),
    Quest("angler", "The Angler", "Catch 10 fish.", 150,
          lambda s: s.stats.get("fish_caught", 0) >= 10),
    Quest("orchard", "Orchardist", "Plant a fruit tree.", 200,
          lambda s: s.stats.get("trees_planted", 0) >= 1),
    Quest("delve", "Into the Dark", "Descend to dungeon floor 2.", 200,
          lambda s: s.stats.get("deepest_depth", 0) >= 2),
    Quest("hunter", "Monster Hunter", "Defeat 5 monsters.", 200,
          lambda s: s.stats.get("monsters_slain", 0) >= 5),
    Quest("prosper", "Prosperity", "Earn 2000g from the shipping bin.", 500,
          lambda s: s.stats.get("gold_earned", 0) >= 2000),
]


# --- Convenience views for the encyclopedia ----------------------------------
ALL_TOOLS = [items.HOE, items.WATERING_CAN, items.AXE, items.PICKAXE, items.MACHETE, items.FISHING_ROD]
ALL_WEAPONS = [items.SWORD]
ALL_SEEDS = [items.PARSNIP_SEEDS]
