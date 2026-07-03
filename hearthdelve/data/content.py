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

# Flowers — grown for gifts and, crucially, to feed nearby beehives. They
# re-bloom like berries so a bed of them keeps a colony fed.
TULIP = Crop(
    name="Tulip", glyph="*", color=(224, 96, 104), season="Spring",
    days_to_mature=5, regrows=True, sell_price=40, regrow_days=3,
    category="flower", seed=items.TULIP_SEEDS, produce=items.TULIP,
    desc="A spring flower that re-blooms; bees adore it.",
)
SUNFLOWER = Crop(
    name="Sunflower", glyph="*", color=(236, 214, 96), season="Summer",
    days_to_mature=6, regrows=True, sell_price=45, regrow_days=3,
    category="flower", seed=items.SUNFLOWER_SEEDS, produce=items.SUNFLOWER,
    desc="A tall summer bloom that re-flowers; bees adore it.",
)
ASTER = Crop(
    name="Aster", glyph="*", color=(190, 130, 220), season="Fall",
    days_to_mature=5, regrows=True, sell_price=45, regrow_days=3,
    category="flower", seed=items.ASTER_SEEDS, produce=items.ASTER,
    desc="An autumn flower that re-blooms; bees adore it.",
)

# Winter crops — the only things that grow outdoors in the cold (and what the
# village fields fall back to), so winter isn't a dead season on the farm.
SNOW_TURNIP = Crop(
    name="Snow Turnip", glyph="♠", color=(210, 220, 232), season="Winter",
    days_to_mature=5, regrows=False, sell_price=90,
    seed=items.SNOW_TURNIP_SEEDS, produce=items.SNOW_TURNIP,
    desc="A hardy winter root, sweetened by the frost.",
)
WINTERBERRY = Crop(
    name="Winterberry", glyph="♦", color=(120, 162, 214), season="Winter",
    days_to_mature=8, regrows=True, sell_price=110, regrow_days=4,
    category="fruit", seed=items.WINTERBERRY_SEEDS, produce=items.WINTERBERRY,
    desc="A tart berry that keeps fruiting in the snow; makes a fine wine.",
)

CROPS: list[Crop] = [PARSNIP, POTATO, CAULIFLOWER, PUMPKIN,
                     TOMATO, STRAWBERRY, BLUEBERRY, GRAPE,
                     TULIP, SUNFLOWER, ASTER,
                     SNOW_TURNIP, WINTERBERRY]
SEED_TO_CROP: dict[Item, Crop] = {c.seed: c for c in CROPS}
CROP_BY_NAME: dict[str, Crop] = {c.name: c for c in CROPS}


def crops_in_season(season: str) -> list[Crop]:
    """Food crops that grow in the given season (for stocking village fields)."""
    return [c for c in CROPS if c.season == season and c.category != "flower"]
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
    accepts: str                  # "ore" | "crop" | "dairy" | "" (sprinkler: none)
    output: Item | None
    desc: str = ""
    capacity: int = 0             # animal housing: how many beasts it holds
    houses: str = ""              # animal housing: which species ("chicken"|"cow")
    footprint: tuple = ()         # carpenter outbuilding size (w, h); () = 1-tile


MACHINES: dict[str, MachineDef] = {
    "furnace": MachineDef("furnace", "Furnace", "F", (224, 132, 70), 120, "ore",
                          items.COPPER_BAR, "Smelts ore + coal into bars (alloys need two ores)."),
    "jar":     MachineDef("jar", "Preserves Jar", "J", (202, 170, 110), 240, "crop",
                          None, "Fruit->jam, veg->pickles, eel->jellied eel."),
    "keg":     MachineDef("keg", "Keg", "K", (172, 110, 72), 480, "fruit",
                          items.WINE, "Ferments fruit into wine."),
    "sawmill": MachineDef("sawmill", "Sawmill", "≠", (176, 134, 90), 90, "wood",
                          items.TIMBER_PLANK, "Saws logs into timber planks (2 wood each)."),
    "beehive": MachineDef("beehive", "Beehive", "⌂", (222, 178, 84), 480, "bees",
                          items.HONEY, "Add a bee queen; makes honey & wax, more with flowers near."),
    "press":   MachineDef("press", "Oil Press", "P", (172, 172, 184), 120, "oil",
                          items.SUNFLOWER_OIL, "Presses sunflowers into oil (2 sunflowers each)."),
    "sprinkler": MachineDef("sprinkler", "Sprinkler", "¤", (120, 188, 222), 0, "",
                            None, "Waters the 4 neighbouring tiles each morning."),
    "churn":   MachineDef("churn", "Churn", "Ö", (206, 196, 176), 360, "dairy",
                          items.CHEESE, "Churns milk into a wheel of cheese."),
    # Animal housing. The little coop is a 1-tile placeable you build yourself;
    # the roomy coop and barn are outbuildings the carpenter raises on your farm.
    "coop_small": MachineDef("coop_small", "Little Coop", "n", (170, 130, 96), 0, "",
                             None, "A hutch for a couple of hens.", capacity=2, houses="chicken"),
    "coop_big":   MachineDef("coop_big", "Coop", "n", (196, 158, 110), 0, "",
                             None, "A roomy henhouse.", capacity=6, houses="chicken",
                             footprint=(4, 3)),
    "barn":       MachineDef("barn", "Barn", "A", (176, 106, 82), 0, "",
                             None, "A barn for the cattle.", capacity=4, houses="cow",
                             footprint=(6, 4)),
    "site":       MachineDef("site", "Building Site", "▦", (176, 148, 104), 0, "",
                             None, "The carpenter's work, still going up."),
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
    Recipe("Sawmill", "build", ((items.WOOD, 12), (items.STONE, 4)), machine="sawmill",
           desc="Saws logs into timber planks over time."),
    Recipe("Preserves Jar", "build", ((items.TIMBER_PLANK, 5),), machine="jar",
           desc="Crops -> jam. (needs timber planks)"),
    Recipe("Keg", "build", ((items.TIMBER_PLANK, 5), (items.COPPER_BAR, 1)), machine="keg",
           desc="Crops -> wine. (needs timber planks)"),
    Recipe("Beehive", "build", ((items.TIMBER_PLANK, 8), (items.BEESWAX, 3)), machine="beehive",
           desc="Add a bee queen; honey & wax, boosted by nearby flowers."),
    Recipe("Oil Press", "build", ((items.TIMBER_PLANK, 6), (items.STONE, 4), (items.COPPER_BAR, 1)),
           machine="press", desc="Presses sunflowers into oil."),
    Recipe("Sprinkler", "build", ((items.COPPER_BAR, 1),), machine="sprinkler",
           desc="Auto-waters nearby soil."),
    Recipe("Little Coop", "build", ((items.TIMBER_PLANK, 6), (items.FIBER, 4)), machine="coop_small",
           desc="A one-tile hutch; settle up to 2 chicks with 'g'."),
    Recipe("Churn", "build", ((items.TIMBER_PLANK, 5), (items.COPPER_BAR, 1)), machine="churn",
           desc="Churns milk into cheese."),
    Recipe("Bomb", "item", ((items.COAL, 1), (items.FIBER, 2)), output=items.BOMB, out_qty=1,
           desc="Aim & throw with 't' to harm monsters and shatter rock."),
    # --- Cooking: makes a carryable dish; eat it (x) for stamina -------------
    Recipe("Parsnip Soup", "cook", ((items.PARSNIP, 2),), output=items.PARSNIP_SOUP,
           desc="A warming bowl."),
    Recipe("Roasted Veg", "cook", ((items.PARSNIP, 1), (items.POTATO, 1)), output=items.ROASTED_VEG,
           desc="Hearty roasted vegetables."),
    Recipe("Fish Stew", "cook", ((items.PERCH, 1), (items.PARSNIP, 1)), output=items.FISH_STEW,
           desc="A rich fisherman's stew."),
    Recipe("Grilled Fish", "cook", ((items.TROUT, 1),), output=items.GRILLED_FISH,
           desc="Simply grilled fish."),
    Recipe("Mushroom Stew", "cook", ((items.CAVE_MUSHROOM, 2),), output=items.MUSHROOM_STEW,
           desc="Earthy cave-mushroom stew."),
    Recipe("Glowcap Broth", "cook", ((items.GLOWCAP, 1),), output=items.GLOWCAP_BROTH,
           desc="A radiant Glimmerwood broth."),
    Recipe("Sauteed Mushrooms", "cook", ((items.BUTTON_MUSHROOM, 2),), output=items.SAUTEED_MUSH,
           desc="Wild field mushrooms in butter."),
    Recipe("Chanterelle Saute", "cook", ((items.CHANTERELLE, 1),), output=items.CHANTERELLE_SAUTE,
           desc="Golden chanterelles, gently fried."),
    Recipe("Bolete Broth", "cook", ((items.BOLETE, 1), (items.PARASOL_MUSHROOM, 1)), output=items.BOLETE_BROTH,
           desc="A rich woodland mushroom broth."),
    Recipe("Glazed Vegetables", "cook", ((items.POTATO, 1), (items.HONEY, 1)), output=items.GLAZED_VEG,
           desc="Vegetables glazed in honey."),
    Recipe("Fried Fish", "cook", ((items.PERCH, 1), (items.SUNFLOWER_OIL, 1)), output=items.FRIED_FISH,
           desc="Fish fried in sunflower oil."),
    Recipe("Candied Fruit", "cook", ((items.HONEY, 1), (items.STRAWBERRY, 1)), output=items.CANDIED_FRUIT,
           desc="Fruit candied in honey."),
    # --- Cooking with the farm's own eggs, milk & cheese (husbandry tie-in) ---
    Recipe("Fried Egg", "cook", ((items.EGG, 1),), output=items.FRIED_EGG,
           desc="A quick fried egg."),
    Recipe("Omelette", "cook", ((items.EGG, 2),), output=items.OMELETTE,
           desc="A fluffy two-egg omelette."),
    Recipe("Cheese Omelette", "cook", ((items.EGG, 2), (items.CHEESE, 1)), output=items.CHEESE_OMELETTE,
           desc="An omelette folded with farmhouse cheese."),
    Recipe("Creamy Soup", "cook", ((items.MILK, 1), (items.POTATO, 1)), output=items.CREAMY_SOUP,
           desc="Potato simmered in fresh milk."),
    Recipe("Custard", "cook", ((items.MILK, 1), (items.EGG, 1), (items.HONEY, 1)), output=items.CUSTARD,
           desc="Silky honey-and-egg custard."),
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

# Bears are rare, strong, and raid beehives for honey. Spawned separately (not
# in the common pool) so you meet them only now and then, deep in the wilds.
BEAR = Critter("Bear", "B", (120, 88, 62), 42, 9, 2, 2, "defensive", "honey",
               "A great shaggy bear — slow to anger, fearsome when roused, and mad for honey.",
               seasons=_NO_WINTER)


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
                blurbs=("Welcome to Mossford! The store's always open by day —\n"
                        "and the kettle's always on for a friendly face.",
                        "Drop your goods in the bin; I'll have gold for you by\n"
                        "morning. Better than lugging it to market, eh?"),
                heart_blurbs=((3, "This shop was my mother's, and hers before that.\n"
                                  "Three generations of Mossford's news, all under one roof."),
                              (6, "My Edwin went down the Cinderhope shafts and never\n"
                                  "came up. I keep a lamp in the window still. ...Tea?")),
                loves=(items.JAM, items.PICKLES, items.WINE),
                likes=(items.PARSNIP, items.POTATO, items.CAULIFLOWER, items.STRAWBERRY),
                dislikes=(items.WOOD, items.STONE, items.COAL),
                gifts=(items.CAULIFLOWER_SEEDS, items.PUMPKIN_SEEDS, items.TULIP_SEEDS, items.JAM),
                bio="Runs the Mossford general store; warm and full of kindly gossip."),
            NPC("Hollis", "H", (224, 168, 96), shop="tavern", role="innkeeper",
                blurbs=("Pull up a stool — the hearth's warm and the ale's honest.\n"
                        "Rest your feet a while.",
                        "Storm brewing? Half the village'll be under my roof by dusk.\n"
                        "The more the merrier, I always say."),
                heart_blurbs=((3, "Twenty years I guarded caravans on the east road.\n"
                                  "One night I just stopped. Best thing I ever did."),
                              (6, "A traveller hears everything, eventually — and forgets\n"
                                  "most of it on purpose. Your secrets are safe here.")),
                loves=(items.WINE, items.GRAPE_WINE, items.JELLIED_EEL),
                likes=(items.JAM, items.PICKLES), dislikes=(items.STONE,),
                gifts=(items.WINE, items.MEAD, items.JAM, items.PICKLES),
                bio="Keeps the Mossford inn; a settled wanderer, full of stories."),
            NPC("Sister Ivy", "I", (214, 196, 224), shop=None, role="priest",
                blurbs=("Peace to you. The shrine is always open, and the seasons\n"
                        "always turning. Be gentle with yourself.",
                        "On the first of each season we gather to give thanks.\n"
                        "Come, if you like — all are welcome at the altar."),
                heart_blurbs=((3, "I came to Mossford with a grief I couldn't name.\n"
                                  "The quiet of this place gave it somewhere to rest."),
                              (6, "I tend the graves as well as the shrine, you know.\n"
                                  "Someone should remember the names. I'm glad of you.")),
                loves=(items.WINE, items.JAM, items.DIAMOND),
                likes=(items.STRAWBERRY, items.BLUEBERRY), dislikes=(items.COAL,),
                gifts=(items.AMETHYST, items.TOPAZ, items.JAM),
                bio="Tends the shrine and churchyard of Mossford; serene and watchful."),
            NPC("Gilda", "G", (210, 176, 120), shop=None, role="farmer",
                blurbs=("Weather permitting, I'm out in the rows till dusk.\n"
                        "Soil under the nails, sun on the back — that's living.",
                        "Come winter there's little to do but mend and wait.\n"
                        "A field needs its rest, same as folk."),
                heart_blurbs=((3, "These were my father's fields. I was six, trailing\n"
                                  "his plough. I'll not let them go to weeds."),
                              (6, "Some days I talk to him out there, between the furrows.\n"
                                  "Daft, maybe. But the crops don't seem to mind.")),
                loves=(items.PARSNIP, items.CAULIFLOWER, items.PUMPKIN),
                likes=(items.POTATO, items.TOMATO), dislikes=(items.STONE,),
                gifts=(items.POTATO_SEEDS, items.CAULIFLOWER_SEEDS, items.PUMPKIN_SEEDS),
                bio="Works the farmhouse fields at the edge of Mossford; salt of the earth."),
            NPC("Tomas", "T", (196, 158, 110), shop="carpenter", role="carpenter",
                blurbs=("Good timber, that — straight grain. I could build you\n"
                        "a proper coop or a barn, if you've the materials.",
                        "Stone and wood, wood and stone. That's how a homestead\n"
                        "grows. Slow and honest."),
                heart_blurbs=((3, "I've a drawing, folded in my apron, of a great\n"
                                  "mead-hall. One day — when the right beams find me."),
                              (6, "Don't laugh — I write a little verse for each tree\n"
                                  "I fell. Seems only fair to say them a few words.")),
                loves=(items.WOOD, items.TIMBER_PLANK), likes=(items.STONE,), dislikes=(items.JAM,),
                gifts=(items.TIMBER_PLANK, items.WOOD),
                bio="Mossford's carpenter; gruff, proud of his craft, secretly tender."),
            NPC("Wrenna", "W", (170, 200, 150), shop=None, role="forager",
                blurbs=("The wild berries make the loveliest preserves.\n"
                        "Forage the wood-edges — you'll be surprised what grows.",
                        "Every plant has a use, if you know how to ask it.\n"
                        "Most folk never think to ask."),
                heart_blurbs=((3, "I apprenticed to a hermit on the moor as a girl.\n"
                                  "She taught me the names of things. All of them."),
                              (6, "She's gone now, the old woman. But gathering in the\n"
                                  "fog-grass, I still feel her at my shoulder. Kindly.")),
                loves=(items.RASPBERRY, items.GOOSEBERRY, items.CURRANT),
                likes=(items.FIBER, items.CAULIFLOWER), dislikes=(items.STONE,),
                gifts=(items.STRAWBERRY_SEEDS, items.BLUEBERRY_SEEDS, items.ASTER_SEEDS, items.RASPBERRY),
                bio="Mossford's herbalist; dreamy, wise in green things."),
            NPC("Pip", "p", (236, 214, 150), shop=None, role="child",
                blurbs=("Wanna see the frog I caught? ...Oh. Maybe later then.\n"
                        "He's a REALLY good frog.",
                        "When I grow up I'm gonna have the BIGGEST farm ever!\n"
                        "Bigger than yours. No offence."),
                heart_blurbs=((3, "My big sister went off to the city last spring.\n"
                                  "She said she'd write. ...She hasn't yet."),
                              (6, "You're my best grown-up friend, you know.\n"
                                  "Don't tell Tam. Actually, do — he'll be SO jealous.")),
                loves=(items.STRAWBERRY, items.JAM),
                likes=(items.RASPBERRY, items.BLUEBERRY, items.TULIP), dislikes=(items.WOOD,),
                gifts=(items.TULIP, items.STRAWBERRY, items.RASPBERRY),
                bio="A Mossford child, forever underfoot around the square."),
            NPC("Tam", "t", (232, 200, 130), shop=None, role="child",
                blurbs=("Pip says HE'S faster but I can climb the well-house,\n"
                        "so really I win.",
                        "If you find a smooth flat stone, keep it for me?\n"
                        "I'm collecting the good ones."),
                heart_blurbs=((3, "Mum says I ask too many questions. But how ELSE\n"
                                  "are you s'posed to find things out?"),
                              (6, "When you're away I tell everyone I'm YOUR helper.\n"
                                  "...That's alright, isn't it?")),
                loves=(items.BLUEBERRY, items.JAM),
                likes=(items.TULIP, items.STRAWBERRY), dislikes=(items.COAL,),
                gifts=(items.TULIP, items.BLUEBERRY, items.ASTER_SEEDS),
                bio="A Mossford child; Pip's rival and inseparable friend."),
        ],
        "Cinderhope": [
            NPC("Bron", "B", (224, 150, 110), shop="blacksmith", role="blacksmith",
                blurbs=("Bring me ore and bars and I'll sharpen your tools!\n"
                        "Wooden tools? We'll fix that. Bronze and up, that's my trade.",
                        "Nothing like the ring of a hammer at dawn. Wakes the whole\n"
                        "street — and I don't apologise for it."),
                heart_blurbs=((3, "Burned my hand near to ruin, first forge I ever lit.\n"
                                  "Almost gave it up. The anvil wouldn't let me."),
                              (6, "A bit of me goes into every tool I make.\n"
                                  "So mind you use mine well, friend. That's an order.")),
                loves=(items.COPPER_BAR, items.COAL),
                likes=(items.COPPER_ORE, items.STONE), dislikes=(items.WINE,),
                gifts=(items.IRON_BAR, items.COPPER_BAR, items.COAL),
                bio="The Cinderhope blacksmith; loud, big-hearted, married to his forge."),
            NPC("Mabel", "A", (232, 176, 132), shop="tavern", role="innkeeper",
                blurbs=("Mind the step — floor's uneven since the old days.\n"
                        "Sit, sit. You look half-starved.",
                        "Miners drink deep after a long shift, bless them.\n"
                        "There's always a bed and a bowl at my taproom."),
                heart_blurbs=((3, "Raised half the young ones in this outpost, I did.\n"
                                  "Nursery, schoolroom, confessional — all my taproom."),
                              (6, "My own two went off to the cities years back.\n"
                                  "So I keep the lamp lit for everyone else's. Suits me.")),
                loves=(items.GRAPE_WINE, items.WINE, items.JELLIED_EEL),
                likes=(items.JAM, items.PICKLES), dislikes=(items.STONE,),
                gifts=(items.MEAD, items.GRAPE_WINE, items.PICKLES),
                bio="Runs the Cinderhope taproom; matron to the whole outpost."),
            NPC("Father Ansel", "F", (196, 200, 224), shop=None, role="priest",
                blurbs=("The old chapel has stood longer than the outpost.\n"
                        "Rest a moment. Even miners must look up sometimes.",
                        "The stone remembers what folk forget.\n"
                        "I just keep the dust off it."),
                heart_blurbs=((3, "There are names on these graves older than any record.\n"
                                  "Forty years I've spent learning who they were."),
                              (6, "Between us — there's a vault beneath the chapel floor.\n"
                                  "Some doors are best left shut. I trust you agree.")),
                loves=(items.WINE, items.SAPPHIRE, items.JAM),
                likes=(items.APPLE, items.CHERRY), dislikes=(items.COAL,),
                gifts=(items.SAPPHIRE, items.EMERALD, items.WINE),
                bio="Keeps the old chapel of Cinderhope; wry, and guards its secrets."),
            NPC("Old Pell", "P", (150, 180, 200), shop=None, role="fisher",
                blurbs=("The river's kind to a patient soul.\n"
                        "Cast a line sometime — once you've a rod, mind.",
                        "Fish bite best when you've stopped needing them to.\n"
                        "There's a lesson in that, somewhere."),
                heart_blurbs=((3, "Fished this water fifty years. Know every eddy and\n"
                                  "snag like the back of my own wrinkled hand."),
                              (6, "Lost a friend to the spring flood, long ago.\n"
                                  "I fish the quiet pools he loved. Feels like company.")),
                loves=(items.WINE, items.GRAPE_WINE),
                likes=(items.RASPBERRY,), dislikes=(items.STONE,),
                gifts=(items.TROUT, items.SALMON, items.GRAPE_WINE),
                bio="An old fisher; quiet and patient, usually by the water."),
            NPC("Garret", "R", (200, 168, 132), shop=None, role="villager",
                blurbs=("Twenty years down the shafts and my back knows every one.\n"
                        "Worth it for the glint, though.",
                        "Copper's steady, but it's silver a man dreams of.\n"
                        "Silver, and maybe a little peace."),
                heart_blurbs=((3, "My father spoke of a silver seam under the grotto.\n"
                                  "Never found it. I reckon it's still down there."),
                              (6, "Strike that seam and I'll not hoard it — half to Mabel,\n"
                                  "half to whoever's kind to an old digger. You, maybe.")),
                loves=(items.COPPER_BAR, items.IRON_BAR, items.COAL),
                likes=(items.STONE, items.COPPER_ORE), dislikes=(items.JAM,),
                gifts=(items.COPPER_ORE, items.IRON_ORE, items.RUBY),
                bio="A weathered miner; chases his father's silver dream."),
            NPC("Nessa", "N", (206, 180, 200), shop=None, role="villager",
                blurbs=("Fibre and patience — that's a good bolt of cloth.\n"
                        "Rush it and you'll see the flaw for years.",
                        "Winter's my busy season, at the loom by the fire.\n"
                        "The cold's good for concentration."),
                heart_blurbs=((3, "I grew up at Saltmere, on the coast. Miss the sound.\n"
                                  "So I weave the waves into my patterns instead."),
                              (6, "This one's for you, if you'll have it — don't argue.\n"
                                  "A friend should have something made with them in mind.")),
                loves=(items.FIBER, items.WINE),
                likes=(items.WOOD, items.CURRANT), dislikes=(items.STONE,),
                gifts=(items.FIBER, items.TULIP, items.ASTER_SEEDS),
                bio="The Cinderhope weaver; meticulous, and homesick for the sea."),
            NPC("Sable", "S", (200, 170, 220), shop=None, role="trader",
                blurbs=("Rare goods, fair prices — when I'm passing through.\n"
                        "A fine vintage fetches a fine coin out east.",
                        "I keep moving. Bad habit, or good sense —\n"
                        "depends who's asking."),
                heart_blurbs=((3, "Cinderhope's a fine place to not be found, you follow.\n"
                                  "Quiet. Out of the way. No questions."),
                              (6, "There was a deal, out east, that went poorly.\n"
                                  "Let's leave it there. Good of you to trust me anyway.")),
                loves=(items.GRAPE_WINE, items.WINE),
                likes=(items.JAM, items.PICKLES), dislikes=(items.FIBER,),
                gifts=(items.DIAMOND, items.GOLD_BAR, items.GRAPE_WINE),
                bio="A travelling trader lodging in Cinderhope; charming, evasive."),
            NPC("Bea", "e", (224, 170, 190), shop=None, role="child",
                blurbs=("I found a SPARKLY rock in the spoil-heap! ...I hid it.\n"
                        "I'm not telling where.",
                        "Da says the mines go down forever. Is that TRUE?\n"
                        "I'm gonna go all the way down one day."),
                heart_blurbs=((3, "It's dusty here and everyone's tired all the time.\n"
                                  "But Mabel makes the good soup, so it's alright."),
                              (6, "Here — you can have my second-best sparkly rock.\n"
                                  "Not the best one. But nearly!")),
                loves=(items.CURRANT, items.JAM),
                likes=(items.TULIP, items.AMETHYST), dislikes=(items.STONE,),
                gifts=(items.TULIP, items.CURRANT, items.AMETHYST),
                bio="A Cinderhope child; a magpie for shiny stones."),
        ],
        "Saltmere": [
            NPC("Coralie", "C", (150, 200, 210), shop="tavern", role="innkeeper",
                blurbs=("Salt air and a warm fire — best cure there is.\n"
                        "The boats come in at dusk; that's when it gets lively.",
                        "Storm's coming? The fishers smell it before I can.\n"
                        "Watch them all head for my door."),
                heart_blurbs=((3, "My father kept the lighthouse down the point.\n"
                                  "I grew up counting ships home. Still do, some nights."),
                              (6, "Every soul who walks through that door, I want them\n"
                                  "leaving a little warmer than they came. You do.")),
                loves=(items.JELLIED_EEL, items.WINE, items.GRAPE_WINE),
                likes=(items.JAM, items.PICKLES), dislikes=(items.STONE,),
                gifts=(items.MEAD, items.JELLIED_EEL, items.WINE),
                bio="Keeps the dockside inn at Saltmere; a lighthouse-keeper's daughter."),
            NPC("Bryn", "b", (140, 180, 208), shop=None, role="fisher",
                blurbs=("Out before dawn, in before dark — the fisher's day.\n"
                        "Rough seas today. The little boats stay moored.",
                        "Read the tide, read the sky, and don't argue with either.\n"
                        "That's the whole of it."),
                heart_blurbs=((3, "My grandmother taught me the old sea-signs.\n"
                                  "Folk laugh — till the day the signs save their nets."),
                              (6, "I'll teach you to read the water, if you like.\n"
                                  "Not many I'd bother with. You listen — that's why.")),
                loves=(items.GRAPE_WINE, items.WINE),
                likes=(items.PICKLES, items.JELLIED_EEL), dislikes=(items.STONE,),
                gifts=(items.SALMON, items.TROUT, items.GRAPE_WINE),
                bio="A Saltmere fisher; stoic and tide-wise."),
            NPC("Marli", "m", (168, 196, 210), shop=None, role="fisher",
                blurbs=("Mended forty nets this week and my fingers know it.\n"
                        "Still — a good net's a good net.",
                        "The catch is best when the currant-blossom falls.\n"
                        "Old shore wisdom. Never fails me."),
                heart_blurbs=((3, "I mend more than nets, truth be told.\n"
                                  "A quarrel here, a sulk there — somebody's got to."),
                              (6, "You've a knack for turning up when a body needs a hand.\n"
                                  "Takes one to know one, I'd say.")),
                loves=(items.JAM, items.STRAWBERRY),
                likes=(items.BLUEBERRY, items.CURRANT), dislikes=(items.COAL,),
                gifts=(items.TROUT, items.JAM, items.STRAWBERRY),
                bio="A Saltmere fisher and net-mender; cheerful peacemaker of the shore."),
            NPC("Doran", "D", (128, 168, 200), shop=None, role="fisher",
                blurbs=("Forty years on the water and she still surprises me.\n"
                        "Learn the tides, and the tides will feed you.",
                        "Harbour-master, they call me. Mostly I shout at gulls\n"
                        "and tie other folks' knots properly."),
                heart_blurbs=((3, "Wrecked once, off the point, in a squall none foresaw.\n"
                                  "Clung to a spar all night. The sea gave me back."),
                              (6, "Respect the sea — never love her, never trust her.\n"
                                  "Do the same and you'll grow as old and ugly as me.")),
                loves=(items.WINE, items.GRAPE_WINE),
                likes=(items.CHERRY, items.APPLE), dislikes=(items.WOOD,),
                gifts=(items.SALMON, items.WINE),
                bio="Saltmere's oldest fisher and harbour-master; a grizzled sage."),
            NPC("Nan", "n", (196, 190, 208), shop=None, role="villager",
                blurbs=("Every rope on that shore has passed through my hands.\n"
                        "Good rope's the difference between home and drowned.",
                        "Salt gets into everything, cloth most of all.\n"
                        "My knuckles have been white as gull-down for years."),
                heart_blurbs=((3, "My mother made rope, and hers. We tie the same knots\n"
                                  "the first Saltmere folk tied. That's worth something."),
                              (6, "Come by when your gear frays — no charge, for you.\n"
                                  "Can't have a friend put to sea on bad rope.")),
                loves=(items.FIBER, items.WINE),
                likes=(items.WOOD, items.CURRANT), dislikes=(items.STONE,),
                gifts=(items.FIBER, items.WOOD),
                bio="Saltmere's rope- and net-maker; sharp-tongued and kind."),
            NPC("Finn", "f", (150, 210, 214), shop=None, role="child",
                blurbs=("I can hold my breath for AGES. Wanna count?\n"
                        "...You have to actually count, though.",
                        "Doran says I'll be a proper sailor someday.\n"
                        "I already know four knots! Well. Three and a bit."),
                heart_blurbs=((3, "I'm not scared of the big waves. Much.\n"
                                  "Da was, at the end. So I decided not to be."),
                              (6, "I saved you the best shell off the whole beach.\n"
                                  "Listen — you can hear the sea in it!")),
                loves=(items.STRAWBERRY, items.JAM),
                likes=(items.TULIP, items.BLUEBERRY), dislikes=(items.STONE,),
                gifts=(items.MINNOW, items.TULIP, items.STRAWBERRY),
                bio="A Saltmere child; a would-be sailor, brave as he can manage."),
        ],
    }


def solo_npcs() -> list[NPC]:
    """Standalone folk who live out in the wilds, not in any village."""
    return [
        NPC("Yew", "Y", (150, 186, 120), shop=None, role="forester",
            blurbs=("Hey dol! merry dol! Yew am I, the warden —\n"
                    "boughs for my rafters, and the whole wood my garden!",
                    "Tread soft, little digger, where the leaf-litter's deep;\n"
                    "fell one and plant twain — that's the pledge the woods keep!",
                    "Rain in the night-time, and mushrooms by morning!\n"
                    "Gather a capful, but heed the wood's warning.",
                    "Old are the oak-folk, and older still their song;\n"
                    "I've walked these green shadows my whole life long!",
                    "Hop-o'-my-thumb through the fern and the bramble —\n"
                    "the fox knows old Yew, and the deer when they ramble!"),
            heart_blurbs=((3, "The wood was old when the first roads were new;\n"
                              "it knows your step now — and it lets you through!"),
                          (6, "Deep in my heart there's a hum and a humming —\n"
                              "the bees know a friend, and they know when he's coming!")),
            loves=(items.WOOD, items.TIMBER_PLANK, items.CHANTERELLE),
            likes=(items.BOLETE, items.FIBER, items.RASPBERRY),
            dislikes=(items.STONE, items.COAL),
            gifts=(items.BEE_QUEEN, items.CHERRY_SAPLING, items.APPLE_SAPLING,
                   items.PEACH_SAPLING, items.WOOD),
            bio="The forester of the Wildwood, who talks in rhyme; keeps a hut deep among the trees."),
    ]


# General store stock: (seed, buy price)
GENERAL_STOCK: list[tuple[Item, int]] = [
    (items.PARSNIP_SEEDS, 20), (items.POTATO_SEEDS, 50), (items.CAULIFLOWER_SEEDS, 80),
    (items.PUMPKIN_SEEDS, 100), (items.TOMATO_SEEDS, 50), (items.STRAWBERRY_SEEDS, 100),
    (items.BLUEBERRY_SEEDS, 80), (items.GRAPE_SEEDS, 60),
    (items.CHERRY_SAPLING, 600), (items.PEACH_SAPLING, 600),
    (items.APPLE_SAPLING, 700), (items.ORANGE_SAPLING, 700),
    (items.TULIP_SEEDS, 40), (items.SUNFLOWER_SEEDS, 50), (items.ASTER_SEEDS, 50),
    (items.SNOW_TURNIP_SEEDS, 70), (items.WINTERBERRY_SEEDS, 90),
    (items.CHICK, 120), (items.CALF, 400),
]
# Blacksmith also sells fuel/metal: (item, buy price)
BLACKSMITH_STOCK: list[tuple[Item, int]] = [
    (items.COAL, 25), (items.COPPER_BAR, 120),
]

# --- Festivals ---------------------------------------------------------------
# Real seasonal festivals on fitting days (never the arbitrary 1st). The whole
# village gathers in the square. Each: (day_of_season, name, flavour, treat).
# Each festival scripts its own weather: fine days for most, fog for Hallows'
# Eve, snow for the winter feasts. (day, name, flavour, treat, weather)
FESTIVALS: dict[str, list] = {
    "Spring": [(11, "the Spring Equinox",
                "blossom and wildflowers deck the square; fiddles play", items.TULIP_SEEDS, "Clear")],
    "Summer": [(5, "the Summer Solstice",
                "the longest day — bonfires, garlands and dancing", items.SUNFLOWER_SEEDS, "Clear"),
               (24, "the Harvest Fair",
                "the first great harvest in; long tables fill the square", items.ROASTED_VEG, "Clear")],
    "Fall":   [(26, "Hallows' Eve",
                "carved lanterns loom in the mist; a pleasant shiver in the dark", items.CANDIED_FRUIT, "Fog")],
    "Winter": [(4, "the Winter Solstice",
                "snow falls soft; every lamp is lit against the long dark", items.MEAD, "Snow"),
               (25, "Yuletide",
                "the great midwinter feast — snow, gifts, song and warmth", items.GRAPE_WINE, "Snow")],
}


def festival_on(season: str, day_of_season: int):
    """The festival on this day, or None: (day, name, flavour, treat, weather)."""
    for fest in FESTIVALS.get(season, ()):
        if fest[0] == day_of_season:
            return fest
    return None


# Tavern fare: (dish, price, stamina restored, hp restored) — eaten on the spot,
# a warm meal away from your own kitchen.
TAVERN_MENU: list[tuple[str, int, int, int]] = [
    ("Honeyed Tea",     20,  30, 3),
    ("Cup of Wine",     25,  25, 0),
    ("Bowl of Stew",    45,  60, 5),
    ("Mug of Mead",     35,  45, 0),
    ("Roast & Veg",     80,  95, 8),
    ("Hearty Platter", 120, 140, 12),
]


# Outbuildings the carpenter (Tomas) will raise on your farm: he takes gold and
# materials up front, then you choose where it stands and he builds it over a
# couple of days.   (label, machine kind, gold, ((item, qty), ...))
CARPENTER_JOBS: list = [
    ("Coop (roomy henhouse)", "coop_big", 450,
     ((items.TIMBER_PLANK, 20), (items.STONE, 8))),
    ("Barn (for cattle)", "barn", 900,
     ((items.TIMBER_PLANK, 32), (items.STONE, 18), (items.COPPER_BAR, 2))),
    ("Greenhouse (grow any crop, any season)", "greenhouse", 1200,
     ((items.TIMBER_PLANK, 28), (items.STONE, 12), (items.COPPER_BAR, 3))),
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
ALL_SEEDS = [c.seed for c in CROPS] + [t.sapling for t in TREES]
