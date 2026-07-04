"""Items, tools, and the player inventory.

A small data-driven model: every carryable thing is an :class:`Item`. Tools and
the weapon sit on a quick-access hotbar / equipment slots; seeds, crops, and
materials stack in the inventory. Expanded heavily in M2+ (crops, crafted goods).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    name: str
    glyph: str
    kind: str            # tool | weapon | seed | crop | material | artisan | food
    desc: str = ""
    stackable: bool = True
    value: int = 0       # base sell price (0 = not sellable)
    energy: int = 0      # stamina restored when eaten (food dishes)
    buff: str = ""       # a temporary boon granted on eating (see skills.BUFFS)
    family: str = ""     # groups per-source artisan goods (all jams share "jam")
                         # so NPC gift tastes & the like match any variant
    source: object = None  # the fruit/veg this good was made from (artisan goods);
                           # its price already reflects the source's value
    # Weapons & armour are made of a material (iron, steel, mithril, ...) and may
    # carry a prefix and/or suffix affix. Stats derive from base + material +
    # affixes (see content.make_gear); the name encodes all three so a save
    # round-trips by name alone.
    material: str = ""
    prefix: str = ""
    suffix: str = ""


# --- Tools (hotbar) ----------------------------------------------------------
# Tools carry a material tier per player (see TOOL_TIERS); the base name here is
# prefixed with the tier for display, e.g. "Wooden Hoe". Upgraded at the smith.
HOE          = Item("Hoe",          "(", "tool", "Tills grass into farmable soil.", stackable=False)
WATERING_CAN = Item("Watering Can", "!", "tool", "Waters tilled soil so crops grow.", stackable=False)
AXE          = Item("Axe",          "/", "tool", "Chops trees for wood.", stackable=False)
PICKAXE      = Item("Pickaxe",      "\\","tool", "Breaks rock and ore veins.", stackable=False)
MACHETE      = Item("Machete",      ")", "tool", "Clears foliage and shrubs.", stackable=False)
FISHING_ROD  = Item("Fishing Rod",  "{", "tool", "Cast at water to catch fish.", stackable=False)

# Tools whose name takes a material-tier prefix (Wooden Hoe, Bronze Axe, ...).
TIERED_TOOLS = (HOE, WATERING_CAN, AXE, PICKAXE, MACHETE)

# --- Weapons (held like a tool; see content.WEAPON_STATS for combat profiles) -
# These are the iron-tier "canonical" pieces; content.make_gear seeds itself with
# them and generates the other materials/affixes. The starter blade is a humble
# rusty one — the affix system in miniature from turn one.
SWORD        = Item("Rusty Iron Sword", "|", "weapon", "A basic blade for the wilds.", stackable=False, value=40, material="iron", prefix="rusty")
DAGGER       = Item("Iron Dagger",      "†", "weapon", "A quick, light blade — deft and accurate.", stackable=False, value=70, material="iron")
BATTLE_AXE   = Item("Iron Battle Axe",  "¶", "weapon", "A heavy axe; fells foes and trees alike.", stackable=False, value=180, material="iron")
WAR_MACE     = Item("Iron War Mace",    "‡", "weapon", "A crushing head that shrugs off armour.", stackable=False, value=150, material="iron")

# --- Armor (worn; grants Protection, sometimes at a Dodge cost) --------------
LEATHER_ARMOR = Item("Leather Armour", "]", "armor", "Boar-hide armour; light and unencumbering.", stackable=False, value=90, material="leather")
CHAIN_MAIL    = Item("Iron Armour",    "]", "armor", "Linked iron rings; solid cover, a touch bulky.", stackable=False, value=280, material="iron")
PLATE_ARMOR   = Item("Steel Armour",   "]", "armor", "Heavy steel plate; the best protection, but it slows your dodge.", stackable=False, value=650, material="steel")

# --- Seeds -------------------------------------------------------------------
PARSNIP_SEEDS     = Item("Parsnip Seeds",     "_", "seed", "Plant in spring; matures in ~4 days.")
POTATO_SEEDS      = Item("Potato Seeds",      "_", "seed", "A hearty spring tuber.")
CAULIFLOWER_SEEDS = Item("Cauliflower Seeds", "_", "seed", "Slow-growing spring prize.")
TOMATO_SEEDS      = Item("Tomato Seeds",      "_", "seed", "Summer fruit; keeps fruiting.")
PUMPKIN_SEEDS     = Item("Pumpkin Seeds",     "_", "seed", "The great fall harvest.")
STRAWBERRY_SEEDS  = Item("Strawberry Seeds",  "_", "seed", "Spring fruit; re-fruits.")
BLUEBERRY_SEEDS   = Item("Blueberry Seeds",   "_", "seed", "Summer fruit; re-fruits.")
GRAPE_SEEDS       = Item("Grape Seeds",       "_", "seed", "Fall fruit; re-fruits.")
TULIP_SEEDS       = Item("Tulip Seeds",       "_", "seed", "Spring flowers; bloom again and again. Bees love them.")
SUNFLOWER_SEEDS   = Item("Sunflower Seeds",   "_", "seed", "Tall summer blooms. Bees love them.")
ASTER_SEEDS       = Item("Aster Seeds",       "_", "seed", "Autumn flowers. Bees love them.")
SNOW_TURNIP_SEEDS = Item("Snow Turnip Seeds", "_", "seed", "Plant in winter; a hardy frost-sweet root.")
WINTERBERRY_SEEDS = Item("Winterberry Seeds", "_", "seed", "Winter berry; re-fruits in the cold.")

# --- Produce: vegetables ----------------------------------------------------
PARSNIP     = Item("Parsnip",     "♠", "crop", "A pale, hardy root.",   value=35)
POTATO      = Item("Potato",      "o", "crop", "An earthy staple.",     value=80)
CAULIFLOWER = Item("Cauliflower", "%", "crop", "A big, prized head.",   value=175)
PUMPKIN     = Item("Pumpkin",     "O", "crop", "A heavy autumn gourd.", value=320)
SNOW_TURNIP = Item("Snow Turnip", "♠", "crop", "A frost-sweetened winter root.", value=130)

# --- Flowers (grown for beauty, gifts, and to feed the bees) ----------------
TULIP       = Item("Tulip",       "*", "crop", "A cheerful spring bloom.",  value=40)
SUNFLOWER   = Item("Sunflower",   "*", "crop", "A tall, sunny summer flower.", value=45)
ASTER       = Item("Aster",       "*", "crop", "A starry autumn flower.",   value=45)

# --- Produce: fruits (the only inputs for jam & wine) -----------------------
TOMATO      = Item("Tomato",      "♥", "crop", "Plump and red.",        value=60)
STRAWBERRY  = Item("Strawberry",  "♦", "crop", "Sweet spring berry.",   value=120)
BLUEBERRY   = Item("Blueberry",   "♦", "crop", "Summer berry cluster.", value=80)
GRAPE       = Item("Grape",       "♦", "crop", "Fall vine fruit; prized for wine.", value=80)
WINTERBERRY = Item("Winterberry", "♦", "crop", "A tart berry that ripens in the snow.", value=110)
RASPBERRY   = Item("Raspberry",   "♦", "crop", "Wild berry from shrubs.",  value=50)
GOOSEBERRY  = Item("Gooseberry",  "♦", "crop", "Tart berry from shrubs.",  value=55)
CURRANT     = Item("Currant",     "♦", "crop", "Jewel-like shrub berry.",  value=65)

# --- Orchard fruit (from planted trees) -------------------------------------
CHERRY      = Item("Cherry",      "♦", "crop", "Sweet spring cherry.",     value=80)
PEACH       = Item("Peach",       "♦", "crop", "Juicy summer peach.",      value=90)
APPLE       = Item("Apple",       "♦", "crop", "Crisp autumn apple.",      value=100)
ORANGE      = Item("Orange",      "♦", "crop", "Bright winter orange.",    value=100)

# --- Saplings (plant to grow a fruit tree) ----------------------------------
CHERRY_SAPLING = Item("Cherry Sapling", "↑", "sapling", "Grows to bear cherries each spring.")
PEACH_SAPLING  = Item("Peach Sapling",  "↑", "sapling", "Grows to bear peaches each summer.")
APPLE_SAPLING  = Item("Apple Sapling",  "↑", "sapling", "Grows to bear apples each autumn.")
ORANGE_SAPLING = Item("Orange Sapling", "↑", "sapling", "Grows to bear oranges each winter.")

# --- Seed pouch (hotbar slot for planting; cycles through what you carry) ----
SEED_POUCH  = Item("Seed Pouch", "_", "pouch", "Your seeds & saplings. Press its key to cycle.", stackable=False)

# --- Raw materials (gathered with axe / pickaxe / machete) ------------------
WOOD        = Item("Wood",        "=", "material", "Logged from trees.",        value=5)
TIMBER_PLANK = Item("Timber Plank", "≡", "material", "Sawn from logs at a sawmill; a sturdier building material.", value=15)
FIBER       = Item("Fiber",       ";", "material", "Plant fibre from foliage.", value=3)
CUT_GRASS   = Item("Cut Grass",   "\"","material", "Freshly scythed grass — dries into straw on a fair day.", value=2)
STRAW       = Item("Straw",       "~", "material", "Dried grass; winter feed for your animals.", value=5)
STONE       = Item("Stone",       "o", "material", "Broken from rock.",         value=4)
FENCE       = Item("Fence",       "│", "material", "A timber fence panel; set it down (build menu) to bound and claim wild land.", value=6)
COAL        = Item("Coal",        "♦", "material", "Fuel for the furnace.",     value=12)
# Dungeon reagents: foraged fungus and creature drops (cook/sell/gift).
CAVE_MUSHROOM = Item("Cave Mushroom", "τ", "material", "An earthy cave fungus — good in a stew.", value=30)
SLIME_GEL     = Item("Slime Gel",     "*", "material", "Sticky residue from a cave slime.",       value=15)
BAT_WING      = Item("Bat Wing",      "~", "material", "A leathery wing from a cave bat.",         value=20)
BOAR_HIDE     = Item("Boar Hide",     "u", "material", "Tough hide from a wild boar.",             value=40)
GLOWCAP       = Item("Glowcap",       "î", "material", "A luminous cave fungus from the Glimmerwood — prized by cooks.", value=65)
# Wild mushrooms — field species (open ground) and forest species (woodland).
BUTTON_MUSHROOM  = Item("Button Mushroom",  "τ", "material", "A small, common field mushroom.",            value=20)
PARASOL_MUSHROOM = Item("Parasol Mushroom", "τ", "material", "A tall field mushroom with a broad cap.",     value=32)
BOLETE           = Item("Bolete",           "τ", "material", "A fat-stemmed woodland mushroom, prized in the pot.", value=42)
CHANTERELLE      = Item("Chanterelle",      "τ", "material", "A golden, funnel-shaped forest mushroom.",    value=55)
# ores (mined; smelted in the furnace) — deeper floors hold better metals
COPPER_ORE     = Item("Copper Ore",     "*", "material", "Common shallow ore.",   value=15)
TIN_ORE        = Item("Tin Ore",        "*", "material", "Alloys with copper.",   value=15)
IRON_ORE       = Item("Iron Ore",       "*", "material", "Sturdy mid-depth ore.", value=25)
SILVER_ORE     = Item("Silver Ore",     "*", "material", "A precious metal ore.", value=40)
GOLD_ORE       = Item("Gold Ore",       "*", "material", "A rich vein of gold.",  value=60)
ADAMANTITE_ORE = Item("Adamantite Ore", "*", "material", "Deep, hard ore.",       value=90)
MITHRIL_ORE    = Item("Mithril Ore",    "*", "material", "The rarest deep ore.",  value=150)
# bars (smelted; alloys need two ores)
COPPER_BAR     = Item("Copper Bar",     "‡", "material", "Smelted copper.",       value=60)
BRONZE_BAR     = Item("Bronze Bar",     "‡", "material", "Copper + tin alloy.",   value=90)
IRON_BAR       = Item("Iron Bar",       "‡", "material", "Smelted iron.",         value=120)
STEEL_BAR      = Item("Steel Bar",      "‡", "material", "Iron forged with coal.", value=180)
SILVER_BAR     = Item("Silver Bar",     "‡", "material", "Smelted silver.",       value=220)
GOLD_BAR       = Item("Gold Bar",       "‡", "material", "Smelted gold; valuable.", value=320)
ADAMANTIUM_BAR = Item("Adamantium Bar", "‡", "material", "A near-unbreakable bar.", value=400)
MITHRIL_BAR    = Item("Mithril Bar",    "‡", "material", "The finest bar of all.", value=600)
# gems (mined from gem veins)
AMETHYST    = Item("Amethyst",    "◊", "material", "A violet gemstone.", value=90)
TOPAZ       = Item("Topaz",       "◊", "material", "A golden gemstone.", value=110)
EMERALD     = Item("Emerald",     "◊", "material", "A green gemstone.",  value=140)
RUBY        = Item("Ruby",        "◊", "material", "A red gemstone.",    value=170)
SAPPHIRE    = Item("Sapphire",    "◊", "material", "A blue gemstone.",   value=210)
DIAMOND     = Item("Diamond",     "◊", "material", "The most prized gem.", value=320)

# --- Artisan goods (made in machines — the value ladder) --------------------
# Generic artisan goods double as the "family" anchors for gifts & tastes; the
# jar/keg actually make per-fruit variants (content.FRUIT_JAM etc.) whose price
# is derived from the source fruit.
JAM         = Item("Jam",         "■", "artisan",  "Preserved fruit; sells well.", value=160, family="jam")
WINE        = Item("Wine",        "ø", "artisan",  "Aged fruit wine.",            value=200, family="wine")
GRAPE_WINE  = Item("Grape Wine",  "ø", "artisan",  "Vintage grape wine; the finest.", value=260, family="wine", source=GRAPE)
PICKLES     = Item("Pickles",     "■", "artisan",  "Pickled vegetables; tangy and tidy.", value=130, family="pickles")
JELLIED_EEL = Item("Jellied Eel", "■", "artisan",  "Eel set in savoury jelly; a delicacy.", value=150, family="jellied")
MEAD        = Item("Mead",        "u", "artisan",  "Fermented honey mead (miód pitny).", value=180)

# --- Cooked dishes (kind 'food'; eat to restore stamina, scaled by quality) --
PARSNIP_SOUP     = Item("Parsnip Soup",     "≈", "food", "A warming bowl of soup.",        value=90, energy=45, buff="tiller")
ROASTED_VEG      = Item("Roasted Veg",      "≈", "food", "Hearty roasted vegetables.",     value=135, energy=70, buff="tiller")
FISH_STEW        = Item("Fish Stew",        "≈", "food", "A rich fisherman's stew.",       value=85, energy=60, buff="hearty")
GRILLED_FISH     = Item("Grilled Fish",     "≈", "food", "Simply grilled and restorative.", value=65, energy=45, buff="hearty")
MUSHROOM_STEW    = Item("Mushroom Stew",    "≈", "food", "Earthy cave-mushroom stew.",     value=90, energy=65, buff="forager")
GLOWCAP_BROTH    = Item("Glowcap Broth",    "≈", "food", "A radiant, deeply restorative broth.", value=150, energy=95, buff="forager")
SAUTEED_MUSH     = Item("Sauteed Mushrooms","≈", "food", "Wild field mushrooms in butter.", value=60, energy=45, buff="forager")
CHANTERELLE_SAUTE= Item("Chanterelle Saute","≈", "food", "Golden chanterelles, gently fried.", value=90, energy=60, buff="forager")
BOLETE_BROTH     = Item("Bolete Broth",     "≈", "food", "A rich woodland mushroom broth.", value=100, energy=70, buff="forager")
GLAZED_VEG       = Item("Glazed Vegetables","≈", "food", "Vegetables glazed in honey.",    value=150, energy=75, buff="tiller")
FRIED_FISH       = Item("Fried Fish",       "≈", "food", "Fish fried in sunflower oil.",   value=180, energy=65, buff="hearty")
CANDIED_FRUIT    = Item("Candied Fruit",    "≈", "food", "Fruit candied in honey; a sweet treat.", value=190, energy=85, buff="brisk")
# Dishes made from the farm's own eggs, milk and cheese — the husbandry->kitchen tie-in.
FRIED_EGG        = Item("Fried Egg",        "≈", "food", "A quick fried egg.",             value=45, energy=30, buff="hearty")
OMELETTE         = Item("Omelette",         "≈", "food", "A fluffy two-egg omelette.",     value=90, energy=60, buff="hearty")
CHEESE_OMELETTE  = Item("Cheese Omelette",  "≈", "food", "An omelette folded with farmhouse cheese.", value=240, energy=95, buff="hearty")
CREAMY_SOUP      = Item("Creamy Soup",      "≈", "food", "Potato simmered in fresh milk.", value=150, energy=80, buff="tiller")
CUSTARD          = Item("Custard",          "≈", "food", "Silky honey-and-egg custard.",   value=160, energy=85, buff="brisk")
AGED_MEAD   = Item("Aged Mead",   "u", "artisan",  "Mead matured in the cask; deep and mellow.", value=360)
SUNFLOWER_OIL = Item("Sunflower Oil", "ó", "artisan", "Golden oil pressed from sunflowers.", value=130)

# --- Beekeeping -------------------------------------------------------------
HONEY       = Item("Honey",       "*", "material", "Sweet golden honey from a hive.",       value=45)
BEESWAX     = Item("Beeswax",     "%", "material", "Wax from a honeycomb; used in building.", value=25)
BEE_QUEEN   = Item("Bee Queen",   "Q", "material", "A live queen — install her in a beehive to start a colony.", value=220)

# --- Animal husbandry --------------------------------------------------------
# Livestock you buy young and settle into a coop/barn; their daily produce and
# the cheese it makes carry quality tied to how well the animals are cared for.
CHICK       = Item("Chick",       "b", "livestock", "A fluffy chick — settle it in a coop.", stackable=False, value=120)
CALF        = Item("Calf",        "q", "livestock", "A young calf — settle it in a barn.", stackable=False, value=400)
EGG         = Item("Egg",         "○", "animal",   "A fresh-laid egg.",           value=35, energy=6)
MILK        = Item("Milk",        "◓", "animal",   "A pail of fresh milk.",       value=55, energy=10)
CHEESE      = Item("Cheese",      "◍", "artisan",  "A wheel of farmhouse cheese.", value=140, energy=32)

# --- Fish (caught with the rod at water; most are seasonal) -----------------
MINNOW      = Item("Minnow",      "»", "fish", "A tiny river fish.",           value=15)
PERCH       = Item("Perch",       "»", "fish", "A common river catch.",        value=30)
CARP        = Item("Carp",        "»", "fish", "A hefty, muddy carp.",         value=45)
CATFISH     = Item("Catfish",     "»", "fish", "A rare whiskered giant.",      value=120)
SMELT       = Item("Smelt",       "»", "fish", "Silvery spring shoal-fish.",   value=25)
TROUT       = Item("Trout",       "»", "fish", "A fine spring/autumn trout.",  value=55)
BREAM       = Item("Bream",       "»", "fish", "A flat, sunny-water fish.",    value=40)
SUNFISH     = Item("Sunfish",     "»", "fish", "A summer sun-lover.",          value=30)
PIKE        = Item("Pike",        "»", "fish", "A toothy summer predator.",    value=85)
SALMON      = Item("Salmon",      "»", "fish", "Runs the rivers in autumn.",   value=95)
ICEFISH     = Item("Icefish",     "»", "fish", "Caught through winter ice.",   value=45)
STURGEON    = Item("Sturgeon",    "»", "fish", "A rare winter leviathan.",     value=160)
# underground (dungeon lakes)
CAVE_BASS   = Item("Cave Bass",   "»", "fish", "Pale bass from lightless pools.", value=60)
EEL         = Item("Eel",         "»", "fish", "A slippery cave eel.",           value=70)
BLINDFISH   = Item("Blindfish",   "»", "fish", "Eyeless and ghostly.",           value=45)
GLOWFISH    = Item("Glowfish",    "»", "fish", "Faintly luminescent; prized.",   value=180)

# --- Ranged weapons & ammo ---------------------------------------------------
# Equip a launcher in the ranged slot and its ammo in the ammo slot, then aim
# with (t). Bombs need no launcher — they're thrown by hand from the ammo slot.
SHORT_BOW   = Item("Short Bow",   ")", "ranged", "A quick hunting bow; looses arrows (t).", value=90, stackable=False, material="birch")
LONG_BOW    = Item("Long Bow",    "}", "ranged", "A tall war bow — longer reach, harder hits.", value=190, stackable=False, material="yew")
SLING       = Item("Sling",       "?", "ranged", "A leather sling; hurls stones cheaply.", value=35, stackable=False, material="leather")
ARROW       = Item("Arrow",       "/", "ammo",   "Fletched arrows for a bow.", value=3)
SLING_STONE = Item("Sling Stone", ".", "ammo",   "Smooth stones for a sling.", value=1)

# --- Consumables -------------------------------------------------------------
BOMB        = Item("Bomb",        "*", "bomb",     "Aim & throw (t): harms monsters and shatters rock/ore.", value=0)


# Registry of every defined item, for save/load by name.
BY_NAME: dict[str, Item] = {v.name: v for v in list(globals().values()) if isinstance(v, Item)}


# Legacy save names (pre-material rework) -> the current canonical item, so old
# saves still resolve. Filled after the registry is built.
_ALIASES: dict[str, Item] = {
    "Sword": SWORD, "Rusty Sword": SWORD, "Dagger": DAGGER,
    "Battle Axe": BATTLE_AXE, "War Mace": WAR_MACE,
    "Leather Armor": LEATHER_ARMOR, "Chain Mail": CHAIN_MAIL, "Plate Armor": PLATE_ARMOR,
}

# Callbacks that can build an item from its name on a registry miss (e.g. a
# composed "Fine Steel Helm of Warding"). content registers the gear resolver
# here — items stays free of any dependency on content.
_RESOLVERS: list = []


def register(item: Item) -> Item:
    """Add a dynamically-built item (e.g. a per-fruit jam) to the save/load
    registry. Returns the item for convenient assignment."""
    BY_NAME[item.name] = item
    return item


def register_resolver(fn) -> None:
    """Register a name -> Item|None builder, tried by by_name on a miss."""
    _RESOLVERS.append(fn)


def by_name(name: str) -> Item | None:
    it = BY_NAME.get(name)
    if it is not None:
        return it
    for fn in _RESOLVERS:
        it = fn(name)
        if it is not None:
            BY_NAME[name] = it       # cache the reconstructed piece
            return it
    return _ALIASES.get(name)


@dataclass
class Inventory:
    """Stacking storage for non-equipment goods. Each slot is [item, qty,
    quality]; the same item at different qualities (0-5 stars) stacks apart."""
    slots: list[list] = field(default_factory=list)   # list of [Item, qty, quality]

    def add(self, item: Item, qty: int = 1, quality: int = 0) -> None:
        if item.stackable:
            for e in self.slots:
                if e[0] is item and e[2] == quality:
                    e[1] += qty
                    return
        self.slots.append([item, qty, quality])

    def count(self, item: Item, quality: int | None = None) -> int:
        return sum(e[1] for e in self.slots
                   if e[0] is item and (quality is None or e[2] == quality))

    def remove(self, item: Item, qty: int = 1, quality: int | None = None) -> bool:
        """Remove up to qty (lowest quality first unless a quality is given).
        Returns True only if the FULL qty was removed (False on a short stack),
        so callers can trust the bool rather than being told a partial take
        succeeded."""
        stacks = sorted((e for e in self.slots if e[0] is item
                         and (quality is None or e[2] == quality)),
                        key=lambda e: e[2])
        need = qty
        for e in stacks:
            take = min(e[1], need)
            e[1] -= take
            need -= take
            if need <= 0:
                break
        self.slots = [e for e in self.slots if e[1] > 0]
        return need <= 0

    def pop_quality(self, item: Item, qty: int = 1) -> float:
        """Remove qty (lowest quality first) and return the average quality of
        the units removed — used to carry quality into processed goods."""
        removed = []
        for e in sorted((e for e in self.slots if e[0] is item), key=lambda e: e[2]):
            take = min(e[1], qty - len(removed))
            removed.extend([e[2]] * take)
            e[1] -= take
            if len(removed) >= qty:
                break
        self.slots = [e for e in self.slots if e[1] > 0]
        return sum(removed) / len(removed) if removed else 0.0

    def is_empty(self) -> bool:
        return not self.slots
