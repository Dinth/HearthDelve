"""Village life: NPC schedules, talking, gifting, shops, and tool upgrades."""
from __future__ import annotations

from ..data import content
from ..engine import constants as C
from ..entities import items
from ..entities.npc import NPC, MAX_HEARTS
from .state import GameState


# --- schedule ---------------------------------------------------------------
def scheduled_spot(npc, hour: int, weather: str, season: str, day_of_season: int) -> str:
    """Which anchor a resident heads to, given the hour, weather and season.

    Keys resolve against ``npc.spots``: home | work | inn | temple | square.
    """
    role = npc.role
    bad = weather in ("Rain", "Storm", "Snow")
    storm = weather == "Storm"

    # night & early morning: asleep / at home
    if hour < 8 or hour >= 22:
        return "home"
    # first of the season is a holy morning — folk gather at the shrine
    if day_of_season == 1 and 9 <= hour < 11 and role != "innkeeper":
        return "temple"
    # midday meal at home
    if hour == 13:
        return "home"
    # evening: the tavern fills up, unless a storm keeps everyone indoors
    if hour >= 19:
        return "home" if storm else "inn"

    # working hours (08–19, minus the 13:00 meal)
    if role == "innkeeper":
        return "inn"
    if role == "priest":
        return "temple"
    if role in ("farmer", "fisher", "forager", "forester"):
        # outdoor trades can't work through a storm, a downpour, or (for the
        # fields) a frozen winter — they wait it out at the inn or at home.
        if storm or (role == "farmer" and season == "Winter"):
            return "inn"
        if bad:
            return "home"
        return "work"
    # indoor tradesfolk keep their counter/forge/loom in any weather;
    # idle villagers loiter about the market square by day
    if role in ("shopkeeper", "blacksmith", "carpenter", "trader"):
        return "work"
    return "square"


def update_npcs(state: GameState) -> None:
    """Teleport each resident to their scheduled anchor for the hour."""
    hour = (state.time_minutes // 60) % 24
    for npc in state.world.npcs:
        key = scheduled_spot(npc, hour, state.weather, state.season, state.day_of_season)
        spot = npc.spots.get(key) or npc.spots.get("home") or npc.work
        npc.x, npc.y = spot


def npc_near(state: GameState):
    """The NPC on the faced tile, or an adjacent one (for talk/gift)."""
    p = state.player
    fx, fy = p.facing
    faced = (p.x + fx, p.y + fy)
    by_pos = {(n.x, n.y): n for n in state.world.npcs}
    if faced in by_pos:
        return by_pos[faced]
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if (p.x + dx, p.y + dy) in by_pos:
            return by_pos[(p.x + dx, p.y + dy)]
    return None


# --- talk & gift ------------------------------------------------------------
def talk(state: GameState, npc: NPC) -> str:
    npc.met = True
    if not npc.talked_today:
        npc.talked_today = True
        npc.friendship = min(MAX_HEARTS * 100, npc.friendship + 10)
    return npc.next_blurb()


def gift(state: GameState, npc: NPC, item) -> None:
    if npc.gifted_today:
        state.log.add(f"{npc.name} has already had a gift today.", C.DIM)
        return
    points, line = npc.gift_reaction(item)
    state.player.inventory.remove(item, 1)
    npc.friendship = max(0, min(MAX_HEARTS * 100, npc.friendship + points))
    npc.gifted_today = True
    color = (180, 230, 160) if points >= 45 else (200, 160, 140) if points < 0 else C.WHITE
    state.log.add(line, color)


def giftable_items(state: GameState):
    """Inventory items that can be given (anything but tools/weapon)."""
    return [(it, q) for it, q in state.player.inventory.slots
            if it.kind in ("crop", "artisan", "material", "food", "fish")]


# --- shops ------------------------------------------------------------------
def shop_entries(shop: str):
    """List of entries for a shop: ('buy', item, price) | ('upgrade', tool)."""
    if shop == "general":
        return [("buy", it, price) for it, price in content.GENERAL_STOCK]
    if shop == "blacksmith":
        ups = [("upgrade", t) for t in items.TIERED_TOOLS]
        buys = [("buy", it, price) for it, price in content.BLACKSMITH_STOCK]
        return ups + buys
    return []


def purchase(state: GameState, entry) -> None:
    if entry[0] == "buy":
        _, item, price = entry
        if state.player.gold < price:
            state.log.add("You can't afford that.", C.DIM)
            return
        state.player.gold -= price
        state.player.inventory.add(item, 1)
        state.log.add(f"Bought {item.name} for {price}g.")
    elif entry[0] == "upgrade":
        upgrade_tool(state, entry[1])


def upgrade_tool(state: GameState, tool) -> None:
    p = state.player
    tier = p.tool_tier.get(tool, 0)
    if tier >= len(C.TOOL_TIERS) - 1:
        state.log.add(f"Your {C.TOOL_TIERS[tier]} {tool.name} can't be improved further.", C.DIM)
        return
    gold, bar, count = content.upgrade_cost(tier)
    if p.gold < gold or p.inventory.count(bar) < count:
        state.log.add(f"Bron needs {gold}g + {count} {bar.name} for that upgrade.", C.DIM)
        return
    p.gold -= gold
    p.inventory.remove(bar, count)
    p.tool_tier[tool] = tier + 1
    state.log.add(f"Bron forges your {tool.name} into {C.TOOL_TIERS[tier + 1]}!", (200, 220, 160))
