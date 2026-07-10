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
    # Embedded gems (socketed into weapons/armour, or the stone set in a ring).
    # A tuple of gem *material names* (e.g. ("ruby",)); part of the item's
    # identity so a gem-set piece is a distinct memoized type with its own stats.
    gems: tuple = ()


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
# Values below match the gear factory (base × material [+ affix]); content.make_gear
# re-derives them at import so the formula stays the single source of truth.
SWORD        = Item("Rusty Iron Sword", "|", "weapon", "A basic blade for the wilds.", stackable=False, value=30, material="iron", prefix="rusty")
DAGGER       = Item("Iron Dagger",      "†", "weapon", "A quick, light blade — deft and accurate.", stackable=False, value=70, material="iron")
BATTLE_AXE   = Item("Iron Battle Axe",  "¶", "weapon", "A heavy axe; fells foes and trees alike.", stackable=False, value=110, material="iron")
WAR_MACE     = Item("Iron War Mace",    "‡", "weapon", "A crushing head that shrugs off armour.", stackable=False, value=90, material="iron")

# --- Armor (worn; grants Protection, sometimes at a Dodge cost) --------------
# Values follow the gear factory (base × material multiplier), matching every other
# piece — so armour is always worth far less than the bars it takes to forge, and
# forging is for wearing, never for flipping into profit.
LEATHER_ARMOR = Item("Leather Armour", "]", "armor", "Boar-hide armour; light and unencumbering.", stackable=False, value=60, material="leather")
CHAIN_MAIL    = Item("Iron Armour",    "]", "armor", "Linked iron rings; solid cover, a touch bulky.", stackable=False, value=100, material="iron")
PLATE_ARMOR   = Item("Steel Armour",   "]", "armor", "Heavy steel plate; the best protection, but it slows your dodge.", stackable=False, value=190, material="steel")

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
CARROT_SEEDS   = Item("Carrot Seeds",   "_", "seed", "A quick, sweet spring root.")
KALE_SEEDS     = Item("Kale Seeds",     "_", "seed", "Spring greens; keeps re-leafing.")
CORN_SEEDS     = Item("Corn Seeds",     "_", "seed", "Summer stalks; keeps cropping ears.")
CUCUMBER_SEEDS = Item("Cucumber Seeds", "_", "seed", "A summer vine; superb pickled.")
CABBAGE_SEEDS  = Item("Cabbage Seeds",  "_", "seed", "A big, prized autumn head.")
BEET_SEEDS     = Item("Beet Seeds",     "_", "seed", "A deep-red autumn root.")
LEEK_SEEDS     = Item("Leek Seeds",     "_", "seed", "A hardy winter allium.")
COTTON_SEEDS   = Item("Cotton Seeds",   "_", "seed", "A summer fibre crop; spin the bolls into thread.")
FLAX_SEEDS     = Item("Flax Seeds",     "_", "seed", "A spring fibre crop; spun into linen thread.")
BARLEY_SEEDS   = Item("Barley Seeds",   "_", "seed", "A spring grain; mill it into flour.")
WHEAT_SEEDS    = Item("Wheat Seeds",    "_", "seed", "An autumn grain; mill it into flour.")
RICE_SEEDS     = Item("Rice Seeds",     "_", "seed", "A summer paddy grain; mill it into rice flour.")
SUGARCANE_SEEDS= Item("Sugarcane Seeds","_", "seed", "A summer cane; mill it into sugar.")

# --- Produce: vegetables ----------------------------------------------------
PARSNIP     = Item("Parsnip",     "♠", "crop", "A pale, hardy root.",   value=35)
POTATO      = Item("Potato",      "o", "crop", "An earthy staple.",     value=80)
CAULIFLOWER = Item("Cauliflower", "%", "crop", "A big, prized head.",   value=175)
PUMPKIN     = Item("Pumpkin",     "O", "crop", "A heavy autumn gourd.", value=320)
SNOW_TURNIP = Item("Snow Turnip", "♠", "crop", "A frost-sweetened winter root.", value=130)
CARROT      = Item("Carrot",      "v", "crop", "A crisp, sweet root.",  value=50)
KALE        = Item("Kale",        "%", "crop", "Hardy leafy greens.",   value=75)
CORN        = Item("Corn",        "Y", "crop", "Golden summer ears.",   value=110)
CUCUMBER    = Item("Cucumber",    "c", "crop", "A cool summer vine fruit.", value=65)
CABBAGE     = Item("Cabbage",     "%", "crop", "A dense autumn head.",   value=180)
BEET        = Item("Beet",        "o", "crop", "An earthy crimson root.", value=95)
LEEK        = Item("Leek",        "i", "crop", "A mild winter allium.",  value=100)

# --- Grains & cane (milled at a quern or windmill) --------------------------
BARLEY      = Item("Barley",      "≈", "crop", "A spring grain.",         value=40)
WHEAT       = Item("Wheat",       "≈", "crop", "Golden autumn grain.",    value=45)
RICE        = Item("Rice",        "≈", "crop", "Summer paddy grain.",     value=60)
SUGARCANE   = Item("Sugarcane",   "‖", "crop", "A tall, sweet summer cane.", value=55)

# --- Fibre crops (spun & woven into cloth) ----------------------------------
COTTON      = Item("Cotton",      "*", "crop", "Fluffy cotton bolls for spinning.", value=45)
FLAX        = Item("Flax",        "|", "crop", "Flax stalks, retted for linen thread.", value=40)

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
PEAR        = Item("Pear",        "♦", "crop", "A sweet autumn pear; ferments into perry.", value=100)
ORANGE      = Item("Orange",      "♦", "crop", "Bright winter orange.",    value=100)

# --- Saplings (plant to grow a fruit tree) ----------------------------------
CHERRY_SAPLING = Item("Cherry Sapling", "↑", "sapling", "Grows to bear cherries each spring.")
PEACH_SAPLING  = Item("Peach Sapling",  "↑", "sapling", "Grows to bear peaches each summer.")
APPLE_SAPLING  = Item("Apple Sapling",  "↑", "sapling", "Grows to bear apples each autumn.")
PEAR_SAPLING   = Item("Pear Sapling",   "↑", "sapling", "Grows to bear pears each autumn.")
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
COAL        = Item("Coal",        "♦", "material", "A hot furnace fuel.",       value=12)
# Milled goods (ground at a quern or windmill; carry a 0-5 star quality).
FLOUR       = Item("Flour",       "▪", "material", "Ground from grain; the heart of baking.", value=55)
RICE_FLOUR  = Item("Rice Flour",  "▪", "material", "Fine flour ground from rice.",  value=70)
SUGAR       = Item("Sugar",       "▪", "material", "Milled from pressed cane; sweetens any bake.", value=80)
SALT_LUMP   = Item("Salt Lump",   "○", "material", "A crust of sea salt scraped from the strand — mill it fine.", value=12)
SEA_SALT    = Item("Sea Salt",    "▪", "material", "Finely milled sea salt; seasons a dish.", value=20)
CHARCOAL    = Item("Charcoal",    "♦", "material", "Wood charred in a kiln; a modest, self-sufficient fuel.", value=10)
COKE        = Item("Coke",        "♦", "material", "Coal baked in a kiln; the hottest fuel — smelts the deepest metals fast.", value=28)
# Dungeon reagents: foraged fungus and creature drops (cook/sell/gift).
CAVE_MUSHROOM = Item("Cave Mushroom", "τ", "material", "An earthy cave fungus — good in a stew.", value=30)
SLIME_GEL     = Item("Slime Gel",     "*", "material", "Sticky residue from a cave slime.",       value=15)
BAT_WING      = Item("Bat Wing",      "~", "material", "A leathery wing from a cave bat.",         value=20)
BOAR_HIDE     = Item("Boar Hide",     "u", "material", "Tough hide from a wild boar.",             value=40)
# Meat is TYPED — the cut carries its animal the way a jam carries its fruit
# (family "meat" lets recipes ask for "any meat" and old generic Meat still fit).
MEAT          = Item("Meat",          "▬", "material", "Game meat; good in a pie.", value=55, family="meat")
PORK          = Item("Pork",          "▬", "material", "A fine cut of pork.",       value=85, family="meat")
BEEF          = Item("Beef",          "▬", "material", "A marbled cut of beef.",    value=100, family="meat")
CHICKEN_MEAT  = Item("Chicken Meat",  "▬", "material", "A plump dressed chicken.",  value=45, family="meat")
DUCK_MEAT     = Item("Duck Meat",     "▬", "material", "A rich, dark duck breast.", value=60, family="meat")
MUTTON        = Item("Mutton",        "▬", "material", "A hearty cut of mutton.",   value=70, family="meat")
GOAT_MEAT     = Item("Goat Meat",     "▬", "material", "A lean cut of goat.",       value=65, family="meat")
SPIDER_SILK   = Item("Spider Silk",   "~", "material", "Strong, fine silk from a cave spider.",    value=35)
LURKER_SCALE  = Item("Lurker Scale",  "u", "material", "A thick armoured scale from a deep lurker.", value=55)
WRAITH_ESSENCE= Item("Wraith Essence","*", "material", "Cold, half-real essence bled from a wraith.", value=75)
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
PLATINUM_ORE   = Item("Platinum Ore",   "*", "material", "A lustrous precious-metal ore.", value=120)
ADAMANTITE_ORE = Item("Adamantite Ore", "*", "material", "Deep, hard ore.",       value=90)
MITHRIL_ORE    = Item("Mithril Ore",    "*", "material", "The rarest deep ore.",  value=150)
# bars (smelted; alloys need two ores)
COPPER_BAR     = Item("Copper Bar",     "‡", "material", "Smelted copper.",       value=60)
BRONZE_BAR     = Item("Bronze Bar",     "‡", "material", "Copper + tin alloy.",   value=90)
IRON_BAR       = Item("Iron Bar",       "‡", "material", "Smelted iron.",         value=120)
STEEL_BAR      = Item("Steel Bar",      "‡", "material", "Iron forged with coal.", value=180)
SILVER_BAR     = Item("Silver Bar",     "‡", "material", "Smelted silver.",       value=180)
GOLD_BAR       = Item("Gold Bar",       "‡", "material", "Smelted gold; valuable.", value=260)
PLATINUM_BAR   = Item("Platinum Bar",   "‡", "material", "Smelted platinum; a prized precious metal.", value=420)
ADAMANTIUM_BAR = Item("Adamantium Bar", "‡", "material", "A near-unbreakable bar.", value=340)
MITHRIL_BAR    = Item("Mithril Bar",    "‡", "material", "The finest bar of all.", value=480)
# gems (mined from gem veins)
AMETHYST    = Item("Amethyst",    "◊", "material", "A violet gemstone.", value=90)
TOPAZ       = Item("Topaz",       "◊", "material", "A golden gemstone.", value=110)
EMERALD     = Item("Emerald",     "◊", "material", "A green gemstone.",  value=140)
RUBY        = Item("Ruby",        "◊", "material", "A red gemstone.",    value=170)
SAPPHIRE    = Item("Sapphire",    "◊", "material", "A blue gemstone.",   value=210)
DIAMOND     = Item("Diamond",     "◊", "material", "The most prized gem.", value=320)
# Cut gems (shaped at a gemcutting station; carry 0-5 star quality). The polished
# stones set into jewellery or embedded into gear — worth far more than the rough.
CUT_AMETHYST = Item("Cut Amethyst", "♦", "gem", "A faceted violet gem, ready to set.", value=200)
CUT_TOPAZ    = Item("Cut Topaz",    "♦", "gem", "A faceted golden gem, ready to set.", value=240)
CUT_EMERALD  = Item("Cut Emerald",  "♦", "gem", "A faceted green gem, ready to set.",  value=300)
CUT_RUBY     = Item("Cut Ruby",     "♦", "gem", "A faceted red gem, ready to set.",    value=370)
CUT_SAPPHIRE = Item("Cut Sapphire", "♦", "gem", "A faceted blue gem, ready to set.",   value=450)
CUT_DIAMOND  = Item("Cut Diamond",  "♦", "gem", "A brilliant-cut diamond, ready to set.", value=700)
# A rough nodule pulled from the rock — crack it open at a gemcutting station for a
# gem within.
GEODE       = Item("Geode",       "◓", "material", "An unopened nodule; crack it at a gemcutting station for the gem inside.", value=45)

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
GLAZED_VEG       = Item("Glazed Vegetables","≈", "food", "Vegetables glazed in honey.",    value=195, energy=75, buff="tiller")
FRIED_FISH       = Item("Fried Fish",       "≈", "food", "Fish fried in sunflower oil.",   value=180, energy=65, buff="hearty")
CANDIED_FRUIT    = Item("Candied Fruit",    "≈", "food", "Fruit candied in honey; a sweet treat.", value=240, energy=85, buff="brisk")
# Dishes made from the farm's own eggs, milk and cheese — the husbandry->kitchen tie-in.
FRIED_EGG        = Item("Fried Egg",        "≈", "food", "A quick fried egg.",             value=45, energy=30, buff="hearty")
OMELETTE         = Item("Omelette",         "≈", "food", "A fluffy two-egg omelette.",     value=90, energy=60, buff="hearty")
CHEESE_OMELETTE  = Item("Cheese Omelette",  "≈", "food", "An omelette folded with farmhouse cheese.", value=240, energy=95, buff="hearty")
CREAMY_SOUP      = Item("Creamy Soup",      "≈", "food", "Potato simmered in fresh milk.", value=150, energy=80, buff="tiller")
CUSTARD          = Item("Custard",          "≈", "food", "Silky honey-and-egg custard.",   value=210, energy=85, buff="brisk")
# Baked goods — the grain-milling payoff.
BREAD            = Item("Bread",            "≈", "food", "A warm loaf of crusty bread.",   value=170, energy=60, buff="brisk")
CAKE             = Item("Cake",             "≈", "food", "A rich, sweet celebration cake.", value=320, energy=110, buff="brisk")
BERRY_PIE        = Item("Berry Pie",        "≈", "food", "A golden pie brimming with berries.", value=260, energy=95, buff="forager")
PANCAKES         = Item("Pancakes",         "≈", "food", "A honey-drizzled stack of pancakes.", value=210, energy=80, buff="tiller")
FRIED_RICE       = Item("Fried Rice",       "≈", "food", "Rice fried with egg and a pinch of salt.", value=170, energy=80, buff="hearty")
MEAT_PIE         = Item("Meat Pie",         "≈", "food", "A hearty pie of game meat and potato.", value=280, energy=110, buff="hearty")
PUMPKIN_PIE      = Item("Pumpkin Pie",      "≈", "food", "Spiced pumpkin in a golden crust.", value=570, energy=100, buff="tiller")
FISH_PIE         = Item("Fish Pie",         "≈", "food", "Flaky fish and potato under a pastry lid.", value=240, energy=95, buff="hearty")
PIZZA            = Item("Pizza",            "≈", "food", "Tomato and melted cheese on a crisp base.", value=390, energy=100, buff="brisk")
COOKIES          = Item("Cookies",          "≈", "food", "A batch of sweet, buttery cookies.", value=210, energy=65, buff="brisk")
FRUIT_PARFAIT    = Item("Fruit Parfait",    "≈", "food", "Layers of yogurt, berries and honey.", value=310, energy=80, buff="forager")
FROZEN_YOGURT    = Item("Frozen Yogurt",    "≈", "food", "Sweet, chilled frozen yogurt.", value=210, energy=70, buff="brisk")
YOGURT_PIE       = Item("Yogurt Pie",       "≈", "food", "A creamy fruit-and-yogurt custard pie.", value=570, energy=105, buff="tiller")
# Salads, sandwiches & the pasta line (savoury cooking).
COLESLAW         = Item("Coleslaw",         "≈", "food", "Shredded cabbage in creamy mayo.", value=510, energy=55, buff="forager")
POTATO_SALAD     = Item("Potato Salad",     "≈", "food", "Potato and egg bound in mayonnaise.", value=430, energy=75, buff="hearty")
EGG_SANDWICH     = Item("Egg Sandwich",     "≈", "food", "Egg mayo between slices of fresh bread.", value=540, energy=70, buff="brisk")
TUNA_SALAD       = Item("Tuna Salad",       "≈", "food", "Flaked tuna, mayo and crisp greens.", value=630, energy=85, buff="hearty")
TUNA_SANDWICH    = Item("Tuna Sandwich",    "≈", "food", "A hearty tuna-mayo sandwich.", value=750, energy=95, buff="hearty")
SHORTBREAD       = Item("Shortbread",       "≈", "food", "Crumbly, buttery shortbread.", value=330, energy=70, buff="brisk")
NOODLES          = Item("Noodles",          "≈", "food", "Fresh egg noodles.", value=110, energy=55, buff="brisk")
PASTA            = Item("Pasta",            "≈", "food", "Noodles in a rich tomato sauce with cheese.", value=650, energy=100, buff="hearty")
BACON_AND_EGGS   = Item("Bacon & Eggs",     "≈", "food", "Crispy bacon with fried eggs.", value=310, energy=95, buff="hearty")
SAUSAGE_ROLL     = Item("Sausage Roll",     "≈", "food", "A sausage baked in flaky pastry.", value=280, energy=80, buff="hearty")
# Dishes for the catch the kitchen used to ignore (sardines, pike, cave fish).
GRILLED_SARDINES = Item("Grilled Sardines", "≈", "food", "A row of small fish, charred and salted.", value=110, energy=55, buff="hearty")
BAKED_PIKE       = Item("Baked Pike",       "≈", "food", "A whole pike baked in butter.", value=260, energy=95, buff="hearty")
CAVE_CHOWDER     = Item("Cave Chowder",     "≈", "food", "A pale, earthy chowder of blindfish and cave mushroom.", value=230, energy=90, buff="forager")
TRUFFLE_PASTA    = Item("Truffle Pasta",    "≈", "food", "Buttered noodles under shaved black truffle — decadence itself.", value=680, energy=110, buff="hearty")
AGED_MEAD   = Item("Aged Mead",   "u", "artisan",  "Mead matured in the cask; deep and mellow.", value=360)
SUNFLOWER_OIL = Item("Sunflower Oil", "ó", "artisan", "Golden oil pressed from sunflowers.", value=130)
# Condiments, dairy & preserved goods.
MAYONNAISE  = Item("Mayonnaise",  "◓", "artisan", "Whisked egg and oil — a creamy staple.", value=230, energy=15)
BUTTER      = Item("Butter",      "▪", "artisan", "A golden pat of churned butter.", value=130, energy=20)
KETCHUP     = Item("Ketchup",     "■", "artisan", "A tangy-sweet tomato sauce.", value=270)
CIDER       = Item("Cider",       "ø", "artisan", "Crisp fermented apple cider.", value=220, family="cider", source=None)
PERRY       = Item("Perry",       "ø", "artisan", "Fermented pear perry; delicate and dry.", value=230, family="perry", source=None)
# Textiles: raw fibre -> yarn (spinning wheel) -> cloth (loom) -> garments.
WOOL_YARN   = Item("Wool Yarn",   ";", "material", "Wool spun into yarn.", value=70)
COTTON_YARN = Item("Cotton Thread", ";", "material", "Cotton spun into thread.", value=70)
LINEN_YARN  = Item("Linen Thread", ";", "material", "Flax spun into linen thread.", value=90)
SILK_YARN   = Item("Silk Thread", ";", "material", "Spider silk spun into fine thread.", value=140)
WOOLEN_CLOTH = Item("Woolen Cloth", "≡", "artisan", "A bolt of warm woven wool.", value=160)
COTTON_CLOTH = Item("Cotton Cloth", "≡", "artisan", "A bolt of soft cotton cloth.", value=160)
LINEN_CLOTH  = Item("Linen Cloth",  "≡", "artisan", "A bolt of crisp woven linen.", value=210)
SILK_CLOTH   = Item("Silk Cloth",   "≡", "artisan", "A bolt of lustrous woven silk.", value=320)
JERKY       = Item("Jerky",       "▬", "artisan", "Smoke-cured strips of meat; keeps for ages.", value=150, energy=45, family="jerky")
SAUSAGES    = Item("Sausages",    "▬", "artisan", "Plump smoked sausages.", value=170, energy=55, family="sausages")
BACON       = Item("Bacon",       "▬", "artisan", "Streaky smoked bacon — pork, always pork.", value=180, energy=50, family="bacon", source=PORK)
SMOKED_FISH = Item("Smoked Fish", "»", "artisan", "Fish slow-smoked to a delicacy.", value=200, energy=50)

# --- Beekeeping -------------------------------------------------------------
HONEY       = Item("Honey",       "*", "material", "Sweet golden honey from a hive.",       value=75)
BEESWAX     = Item("Beeswax",     "%", "material", "Wax from a honeycomb; used in building.", value=25)
BEE_QUEEN   = Item("Bee Queen",   "Q", "material", "A live queen — install her in a beehive to start a colony.", value=220)

# --- Animal husbandry --------------------------------------------------------
# Livestock you buy young and settle into a coop/barn; their daily produce and
# the cheese it makes carry quality tied to how well the animals are cared for.
CHICK       = Item("Chick",       "b", "livestock", "A fluffy chick — settle it in a coop.", stackable=False, value=120)
CALF        = Item("Calf",        "q", "livestock", "A young calf — settle it in a barn.", stackable=False, value=400)
LAMB        = Item("Lamb",        "y", "livestock", "A young lamb — settle it in a pen; shear it for wool.", stackable=False, value=260)
DUCKLING    = Item("Duckling",    "b", "livestock", "A paddling duckling — settle it in a coop.", stackable=False, value=160)
GOAT_KID    = Item("Goat Kid",    "g", "livestock", "A springy young goat — settle it in a barn or pen.", stackable=False, value=320)
PIGLET      = Item("Piglet",      "P", "livestock", "A bright-eyed piglet — settle it in a barn; grown pigs root out truffles.", stackable=False, value=800)
WOOL        = Item("Wool",        "%", "material", "A fleece of raw wool, ready to spin.", value=45)
EGG         = Item("Egg",         "○", "animal",   "A fresh-laid egg.",           value=35, energy=6)
DUCK_EGG    = Item("Duck Egg",    "○", "animal",   "A big, rich duck egg.",       value=60, energy=12)
MILK        = Item("Milk",        "◓", "animal",   "A pail of fresh milk.",       value=55, energy=10)
GOAT_MILK   = Item("Goat's Milk", "◓", "animal",   "A pail of tangy goat's milk.", value=65, energy=10)
TRUFFLE     = Item("Truffle",     "•", "animal",   "An earthy black truffle, rooted up by a pig — a chef's treasure.", value=280)
CHEESE      = Item("Cheese",      "◍", "artisan",  "A wheel of farmhouse cheese.", value=140, energy=32)
AGED_CHEESE = Item("Aged Cheese", "◍", "artisan",  "A cellar-aged wheel; sharp and crumbling.", value=210, energy=36)
GOAT_CHEESE = Item("Goat Cheese", "◍", "artisan",  "A soft, tangy round of goat's cheese.", value=170, energy=30)
AGED_GOAT_CHEESE = Item("Aged Goat Cheese", "◍", "artisan", "Cellar-aged goat's cheese; creamy heart, sharp rind.", value=255, energy=34)
YOGURT      = Item("Yogurt",      "◓", "artisan",  "Creamy cultured yogurt, churned from fresh milk.", value=90, energy=30)

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
# sea (cast from the coast / beaches)
SARDINE     = Item("Sardine",     "»", "fish", "A little silver shoaling sea fish.", value=30)
MACKEREL    = Item("Mackerel",    "»", "fish", "A striped, oily sea fish.",       value=55)
SEA_BASS    = Item("Sea Bass",    "»", "fish", "A prized coastal sea bass.",      value=110)
TUNA        = Item("Tuna",        "»", "fish", "A big, prized deep-sea tuna.",    value=200)
MOONFISH    = Item("Moonfish",    "»", "fish", "A pale deep-sea fish that rises only to the lighthouse beam.", value=420)
# underground (dungeon lakes)
CAVE_BASS   = Item("Cave Bass",   "»", "fish", "Pale bass from lightless pools.", value=60)
EEL         = Item("Eel",         "»", "fish", "A slippery cave eel.",           value=70)
BLINDFISH   = Item("Blindfish",   "»", "fish", "Eyeless and ghostly.",           value=45)
GLOWFISH    = Item("Glowfish",    "»", "fish", "Faintly luminescent; prized.",   value=180)

# A fair-day prize: proof, in ribbon form, that your parsnip beat everyone's.
FAIR_RIBBON = Item("Fair Ribbon", "⚑", "material", "A prize ribbon from the produce contest — worth more in pride than gold.", value=250)

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
