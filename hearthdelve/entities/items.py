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

# --- Weapon ------------------------------------------------------------------
SWORD        = Item("Rusty Sword",  "|", "weapon", "A basic blade for the wilds.", stackable=False)

# --- Seeds -------------------------------------------------------------------
PARSNIP_SEEDS     = Item("Parsnip Seeds",     "_", "seed", "Plant in spring; matures in ~4 days.")
POTATO_SEEDS      = Item("Potato Seeds",      "_", "seed", "A hearty spring tuber.")
CAULIFLOWER_SEEDS = Item("Cauliflower Seeds", "_", "seed", "Slow-growing spring prize.")
TOMATO_SEEDS      = Item("Tomato Seeds",      "_", "seed", "Summer fruit; keeps fruiting.")
PUMPKIN_SEEDS     = Item("Pumpkin Seeds",     "_", "seed", "The great fall harvest.")
STRAWBERRY_SEEDS  = Item("Strawberry Seeds",  "_", "seed", "Spring fruit; re-fruits.")
BLUEBERRY_SEEDS   = Item("Blueberry Seeds",   "_", "seed", "Summer fruit; re-fruits.")
GRAPE_SEEDS       = Item("Grape Seeds",       "_", "seed", "Fall fruit; re-fruits.")

# --- Produce: vegetables ----------------------------------------------------
PARSNIP     = Item("Parsnip",     "♠", "crop", "A pale, hardy root.",   value=35)
POTATO      = Item("Potato",      "o", "crop", "An earthy staple.",     value=80)
CAULIFLOWER = Item("Cauliflower", "%", "crop", "A big, prized head.",   value=175)
PUMPKIN     = Item("Pumpkin",     "O", "crop", "A heavy autumn gourd.", value=320)

# --- Produce: fruits (the only inputs for jam & wine) -----------------------
TOMATO      = Item("Tomato",      "♥", "crop", "Plump and red.",        value=60)
STRAWBERRY  = Item("Strawberry",  "♦", "crop", "Sweet spring berry.",   value=120)
BLUEBERRY   = Item("Blueberry",   "♦", "crop", "Summer berry cluster.", value=80)
GRAPE       = Item("Grape",       "♦", "crop", "Fall vine fruit; prized for wine.", value=80)
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
FIBER       = Item("Fiber",       ";", "material", "Plant fibre from foliage.", value=3)
STONE       = Item("Stone",       "o", "material", "Broken from rock.",         value=4)
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
JAM         = Item("Jam",         "■", "artisan",  "Preserved fruit; sells well.", value=110)
WINE        = Item("Wine",        "ø", "artisan",  "Aged fruit wine.",            value=200)
GRAPE_WINE  = Item("Grape Wine",  "ø", "artisan",  "Vintage grape wine; the finest.", value=450)
PICKLES     = Item("Pickles",     "■", "artisan",  "Pickled vegetables; tangy and tidy.", value=95)
JELLIED_EEL = Item("Jellied Eel", "■", "artisan",  "Eel set in savoury jelly; a delicacy.", value=150)

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

# --- Consumables -------------------------------------------------------------
BOMB        = Item("Bomb",        "*", "bomb",     "Thrown (a): harms monsters and shatters rock/ore.", value=0)


# Registry of every defined item, for save/load by name.
BY_NAME: dict[str, Item] = {v.name: v for v in list(globals().values()) if isinstance(v, Item)}


def by_name(name: str) -> Item | None:
    return BY_NAME.get(name)


@dataclass
class Inventory:
    """Stacking storage for non-equipment goods."""
    slots: list[list] = field(default_factory=list)   # list of [Item, qty]

    def add(self, item: Item, qty: int = 1) -> None:
        if item.stackable:
            for entry in self.slots:
                if entry[0] is item:
                    entry[1] += qty
                    return
        self.slots.append([item, qty])

    def count(self, item: Item) -> int:
        return sum(e[1] for e in self.slots if e[0] is item)

    def remove(self, item: Item, qty: int = 1) -> bool:
        """Remove up to qty of item; drop the stack if it empties. False if absent."""
        for entry in self.slots:
            if entry[0] is item:
                entry[1] -= qty
                if entry[1] <= 0:
                    self.slots.remove(entry)
                return True
        return False

    def is_empty(self) -> bool:
        return not self.slots
