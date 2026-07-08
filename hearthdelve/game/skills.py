"""Skills: Farming, Foraging, Mining, Fishing, Combat.

Each gains XP from the matching activity and levels up (0-10). Levels grant
small, cozy bonuses. The character sheet shows level and progress.
"""
from __future__ import annotations

import random

from .state import GameState

SKILLS = ("Farming", "Foraging", "Mining", "Fishing", "Combat", "Cooking",
          "Smithing", "Jewelcrafting", "Gemcutting")
XP_PER_LEVEL = 120
MAX_LEVEL = 10


def level_of(xp: int) -> int:
    return min(MAX_LEVEL, xp // XP_PER_LEVEL)


def skill_level(state: GameState, skill: str) -> int:
    return level_of(state.player.skills.get(skill, 0))


def gain(state: GameState, skill: str, xp: int) -> None:
    """Add skill XP (capped at the skill's level-10 ceiling) and, *separately*, feed
    the character's own experience. Character XP is an independent track: every deed
    feeds it and it keeps growing even after a skill has maxed, so character level is
    no longer bounded by (nor derived from) the skills."""
    p = state.player
    cap = MAX_LEVEL * XP_PER_LEVEL
    cur = p.skills.get(skill, 0)
    before = level_of(cur)
    applied = min(xp, max(0, cap - cur))     # never bank skill XP past the level-10 cap
    if applied:
        p.skills[skill] = cur + applied
        if level_of(p.skills[skill]) > before:
            state.log.add(f"{skill} skill is now level {level_of(p.skills[skill])}!", (170, 210, 240))
    gain_char_xp(state, xp)                   # the character track is never capped by skills


# --- general character level (its own track; raises max HP & stamina) --------
MAX_CHAR_LEVEL = 15


def xp_to_next(level: int) -> int:
    return level * 150


def gain_char_xp(state: GameState, amount: int) -> None:
    p = state.player
    if p.level >= MAX_CHAR_LEVEL:
        return
    p.xp += amount
    while p.level < MAX_CHAR_LEVEL and p.xp >= xp_to_next(p.level):
        p.xp -= xp_to_next(p.level)
        p.level += 1
        p.max_hp += 8
        p.max_energy += 12
        p.hp = min(p.max_hp, p.hp + 8)
        p.energy = min(p.max_energy, p.energy + 12)
        state.log.add(f"You reach level {p.level}! (+8 max HP, +12 max stamina)", (240, 220, 140))
    if p.level >= MAX_CHAR_LEVEL:
        p.xp = 0                              # maxed — stop banking overflow


# --- food buffs (a cooked dish grants a temporary boon; see main._eat) -------
BUFF_MINUTES = 300                    # a buff lasts ~5 in-game hours
BUFFS = {
    "hearty":  "Hearty",              # +2 attack in a scrap
    "tiller":  "Green Thumb",         # richer farm harvests
    "forager": "Keen Forager",        # richer foraging
    "brisk":   "Brisk",               # tireless on foot
}


def active_buff(state: GameState) -> str:
    """The player's current food buff key, or '' if none / expired."""
    p = state.player
    if p.buff and state.abs_minutes < p.buff_until:
        return p.buff
    return ""


def apply_buff(state: GameState, key: str, minutes: int = BUFF_MINUTES) -> None:
    if not key:
        return
    p = state.player
    p.buff = key
    p.buff_until = state.abs_minutes + minutes


# --- weapon mastery (learn by doing, per weapon category) --------------------
MASTERY_MAX = 10            # 0 = unskilled … 10 = grand mastery
MASTERY_PER = 60           # mastery xp per level


def mastery_level(state: GameState, category: str) -> int:
    return min(MASTERY_MAX, state.player.mastery.get(category, 0) // MASTERY_PER)


def gain_mastery(state: GameState, category: str, xp: int) -> None:
    p = state.player
    cap = MASTERY_MAX * MASTERY_PER
    cur = p.mastery.get(category, 0)
    if cur >= cap:
        return
    before = min(MASTERY_MAX, cur // MASTERY_PER)
    p.mastery[category] = min(cap, cur + xp)
    now = min(MASTERY_MAX, p.mastery[category] // MASTERY_PER)
    if now > before:
        state.log.add(f"Your {category} mastery deepens — level {now}.", (170, 210, 240))


def mastery_to_hit(level: int) -> int:
    return level // 2          # +0..+5

def mastery_dmg(level: int) -> int:
    return level // 3          # +0..+3

def mastery_crit(level: int) -> float:
    return level * 0.015       # +0..+15% crit

def mastery_parry(level: int) -> int:
    return level // 4          # +0..+2 DV


# --- gentle bonuses ----------------------------------------------------------
def combat_atk_bonus(state: GameState) -> int:
    bonus = skill_level(state, "Combat") // 3           # +0..+3 attack
    if active_buff(state) == "hearty":
        bonus += 2                                      # a hearty meal steels you
    return bonus

def fishing_catch_bonus(state: GameState) -> float:
    return skill_level(state, "Fishing") * 0.02         # up to +20% catch

def extra_yield_chance(state: GameState, skill: str) -> float:
    from . import jewelry
    chance = skill_level(state, skill) * 0.05           # up to +50% double drops
    b = active_buff(state)
    if (b == "tiller" and skill == "Farming") or (b == "forager" and skill == "Foraging"):
        chance += 0.30
    chance += jewelry.cozy_bonus(state, "yield")        # an emerald ring/amulet enriches the harvest
    return chance


# --- quality (0-5 stars) -----------------------------------------------------
STAR = "★"
_QUALITY_KINDS = ("crop", "fish", "artisan", "food", "animal", "gem", "jewelry")
_QUALITY_NAMES = ("Honey", "Flour", "Rice Flour", "Sugar", "Sea Salt")   # tiered items that aren't one of the kinds


# --- crafting-skill bonuses --------------------------------------------------
def socket_capacity(state: GameState) -> int:
    """How many gems a piece of gear can hold — one, plus a socket earned at
    Gemcutting 5 and again at 10."""
    lvl = skill_level(state, "Gemcutting")
    return 1 + (1 if lvl >= 5 else 0) + (1 if lvl >= 10 else 0)


def smith_speed_mult(state: GameState) -> float:
    """Forge/smelt time multiplier — a seasoned smith works a touch faster (down
    to ~0.7× at Smithing 10)."""
    return 1.0 - 0.03 * skill_level(state, "Smithing")


def has_quality(item) -> bool:
    """Whether an item carries a 0-5 star quality rating."""
    return item.kind in _QUALITY_KINDS or item.name in _QUALITY_NAMES


def stars(q: int) -> str:
    return STAR * q if q else ""


def roll_quality(state: GameState, skill: str) -> int:
    """Quality of freshly produced goods: mostly the relevant skill, a little
    the overall character level, plus luck. Returns 0-5 stars."""
    lvl = skill_level(state, skill)                       # 0..10
    clvl = min(state.player.level, 10)                    # character level, capped
    score = lvl * 0.42 + clvl * 0.12 + random.uniform(-1.3, 1.3)
    return max(0, min(5, round(score - 0.8)))


def process_quality(avg_in: float, state: GameState, skill: str) -> int:
    """Quality of a processed/cooked good: inherits the average ingredient
    quality, nudged up or down by the crafter's skill (plus a little luck)."""
    adjust = (skill_level(state, skill) - 5) * 0.14 + random.uniform(-0.6, 0.6)
    return max(0, min(5, round(avg_in + adjust)))


def value_mult(quality: int) -> float:
    """Sell-value multiplier for quality: 0★ = 1.0 … 5★ = 2.0."""
    return 1.0 + 0.2 * quality
