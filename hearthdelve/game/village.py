"""Village life: NPC schedules, talking, gifting, shops, and tool upgrades."""
from __future__ import annotations

from ..data import content
from ..engine import constants as C
from ..entities import items
from ..entities.npc import NPC, MAX_HEARTS
from . import karma
from .state import GameState


# --- schedule ---------------------------------------------------------------
def scheduled_spot(npc, hour: int, weather: str, season: str, day_of_season: int) -> str:
    """Which anchor a resident heads to, given the hour, weather and season.

    Keys resolve against ``npc.spots``: home | work | inn | temple | square.
    """
    role = npc.role
    bad = weather in ("Rain", "Storm", "Snow")
    storm = weather == "Storm"

    # Festival day: the whole village gathers in the square through the day
    # (unless a storm spoils it). Children roam it, adults mill about.
    if content.festival_on(season, day_of_season) and 9 <= hour < 19 and not storm:
        return "square"

    # Children: out playing around the square by day, home by dusk (and in when
    # the weather's foul). "square" triggers the roaming AI in update_npcs.
    if role == "child":
        if hour < 8 or hour >= 19 or hour == 13 or storm:
            return "home"
        return "square"

    # night & early morning: asleep / at home
    if hour < 8 or hour >= 22:
        return "home"
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
    """Move each resident toward their scheduled anchor for the hour. Adults
    teleport to their spot; children roam and play around the square by day."""
    hour = (state.time_minutes // 60) % 24
    for npc in state.world.npcs:
        key = scheduled_spot(npc, hour, state.weather, state.season, state.day_of_season)
        if key == "square":
            _child_roam(state, npc)          # mill about (kids also chase to play)
        else:
            npc.x, npc.y = npc.spots.get(key) or npc.spots.get("home") or npc.work


_CHILD_RANGE = 9      # how far kids stray from the square while playing


def _child_roam(state: GameState, npc) -> None:
    """A lively amble: kids wander near the square and chase each other to play."""
    import random
    w = state.world
    anchor = npc.spots.get("square") or npc.spots.get("home") or (npc.x, npc.y)
    px, py = state.player.x, state.player.y
    # find a playmate to run toward, if one's a little way off
    mates = [n for n in w.npcs if n.role == "child" and n is not npc]
    mate = min(mates, key=lambda k: (k.x - npc.x) ** 2 + (k.y - npc.y) ** 2, default=None)

    tx = ty = None
    if mate is not None:
        d = max(abs(mate.x - npc.x), abs(mate.y - npc.y))
        if 2 < d < 16 and random.random() < 0.6:
            tx, ty = mate.x, mate.y                     # chase a friend
    if tx is None and max(abs(npc.x - anchor[0]), abs(npc.y - anchor[1])) > _CHILD_RANGE:
        tx, ty = anchor                                 # strayed too far — head back
    if random.random() < 0.35 and tx is None:
        return                                          # pause a beat

    if tx is not None:
        sx = (tx > npc.x) - (tx < npc.x)
        sy = (ty > npc.y) - (ty < npc.y)
        options = [(sx, sy), (sx, 0), (0, sy)]
    else:
        options = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        random.shuffle(options)
    for dx, dy in options:
        nx, ny = npc.x + dx, npc.y + dy
        if (dx or dy) and w.walkable(nx, ny) and (nx, ny) != (px, py):
            npc.x, npc.y = nx, ny
            return


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
    first = not npc.talked_today
    npc.met = True
    if first:
        npc.talked_today = True
        gain = karma.scale(state.player.karma, 10)
        npc.friendship = min(MAX_HEARTS * 100, npc.friendship + gain)
        treat = _festival_treat(state, npc)  # a nibble at the fair
        if treat:
            return treat
        reward = _heart_reward(state, npc)   # gifts from a good friend
        if reward:
            return reward
    return npc.speak()


def _festival_treat(state: GameState, npc: NPC):
    """At a festival, the first villager you greet presses a themed treat on
    you — once per festival."""
    fest = content.festival_on(state.season, state.day_of_season)
    if not fest:
        return None
    key = f"festival_{state.year}_{state.season}_{fest[0]}"
    if state.stats.get(key):
        return None
    state.stats[key] = 1
    treat = fest[3]
    state.player.inventory.add(treat, 1)
    name = fest[1][0].upper() + fest[1][1:]
    return (f"\"{name}! So glad you came,\" says {npc.name}.\n"
            f"\"Here — a {treat.name.lower()} for the day. Enjoy!\"")


def _heart_reward(state: GameState, npc: NPC):
    """A good friend may give the player something from their OWN, in-character
    gift pool. The forester's rare bee queen recurs at high friendship; other
    folk give a one-time token at 5 hearts and again at 8."""
    import random
    from ..entities import items
    p = state.player
    if not npc.gifts:
        return None

    # The forester passes on a bee queen (or a sapling) now and then, once close.
    if npc.role == "forester" and npc.hearts >= 6 and random.random() < 0.30:
        gift = random.choice(npc.gifts)
        p.inventory.add(gift, 1)
        if gift is items.BEE_QUEEN:
            return ("Yew cups his hands and hums low; something within them stirs:\n"
                    "\"A queen for a friend — go raise her a hall of gold!\"")
        return (f"Yew tucks a {gift.name.lower()} into your pack with a wink:\n"
                "\"The wood shares with them as shares with the wood!\"")

    # One-time tokens of friendship at heart milestones, from their own pool.
    for th in (8, 5):
        key = f"heartgift_{npc.name}_{th}"
        if npc.hearts >= th and not state.stats.get(key):
            state.stats[key] = 1
            gift = random.choice(npc.gifts)
            p.inventory.add(gift, 1)
            return (f"{npc.name} presses a {gift.name.lower()} into your hands.\n"
                    "\"For a good friend. I mean it — take it.\"")
    return None


def gift(state: GameState, npc: NPC, item) -> None:
    if npc.gifted_today:
        state.log.add(f"{npc.name} has already had a gift today.", C.DIM)
        return
    points, line = npc.gift_reaction(item)
    state.player.inventory.remove(item, 1)
    points = karma.scale(state.player.karma, points)
    npc.friendship = max(0, min(MAX_HEARTS * 100, npc.friendship + points))
    npc.gifted_today = True
    if points > 0:
        karma.adjust(state, 1)  # a small kindness
    color = (180, 230, 160) if points >= 45 else (200, 160, 140) if points < 0 else C.WHITE
    state.log.add(line, color)


def giftable_items(state: GameState):
    """Inventory items that can be given (anything but tools/weapon)."""
    return [(it, q, ql) for it, q, ql in state.player.inventory.slots
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
    if shop == "tavern":
        return [("meal", label, price, stam, hp)
                for (label, price, stam, hp) in content.TAVERN_MENU]
    if shop == "carpenter":
        return [("commission", label, kind, gold, mats)
                for (label, kind, gold, mats) in content.CARPENTER_JOBS]
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
    elif entry[0] == "meal":
        _, label, price, stam, hp = entry
        p = state.player
        if p.gold < price:
            state.log.add("You can't afford that.", C.DIM)
            return
        p.gold -= price
        p.energy = min(p.max_energy, p.energy + stam)
        p.hp = min(p.max_hp, p.hp + hp)
        state.bump("meals_eaten")
        from . import turns
        from ..engine import constants as _C
        turns.advance_time(state, _C.USE_SECONDS)
        state.log.add(f"You tuck into {label.lower()}. (+{stam} stamina)", (180, 230, 160))
    elif entry[0] == "commission":
        _, label, kind, gold, mats = entry
        p = state.player
        if state.pending_build:
            state.log.add("You already have a building on order — set it down first.", C.DIM)
            return
        if p.gold < gold:
            state.log.add("You can't afford that.", C.DIM)
            return
        missing = [f"{q}x {it.name}" for it, q in mats if p.inventory.count(it) < q]
        if missing:
            state.log.add(f"Tomas needs materials: {', '.join(missing)}.", C.DIM)
            return
        p.gold -= gold
        for it, q in mats:
            p.inventory.remove(it, q)
        state.pending_build = kind
        state.log.add(f"Tomas shakes on it. \"Head home and show me where the "
                      f"{label.split('(')[0].strip().lower()} should go — press p to set the spot.\"",
                      (200, 220, 160))
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
