"""Skills: Farming, Foraging, Mining, Fishing, Combat.

Each gains XP from the matching activity and levels up (0-10). Levels grant
small, cozy bonuses. The character sheet shows level and progress.
"""
from __future__ import annotations

import random

from .state import GameState

SKILLS = ("Farming", "Foraging", "Mining", "Fishing", "Combat", "Cooking")
XP_PER_LEVEL = 120
MAX_LEVEL = 10


def level_of(xp: int) -> int:
    return min(MAX_LEVEL, xp // XP_PER_LEVEL)


def skill_level(state: GameState, skill: str) -> int:
    return level_of(state.player.skills.get(skill, 0))


def char_level(state: GameState) -> int:
    """Overall level = sum of skill levels (0-50)."""
    return sum(skill_level(state, s) for s in SKILLS)


def gain(state: GameState, skill: str, xp: int) -> None:
    p = state.player
    cap = MAX_LEVEL * XP_PER_LEVEL
    cur = p.skills.get(skill, 0)
    if cur >= cap:
        return                       # skill maxed — no more XP, and no more
                                     # character XP fed from it (keeps HP &
                                     # produce quality from inflating forever)
    before = level_of(cur)
    applied = min(xp, cap - cur)     # never bank XP past the level-10 cap
    p.skills[skill] = cur + applied
    if level_of(p.skills[skill]) > before:
        state.log.add(f"{skill} skill is now level {level_of(p.skills[skill])}!", (170, 210, 240))
    gain_char_xp(state, applied)     # all activity feeds general experience


# --- general character level (raises max HP & stamina) -----------------------
def xp_to_next(level: int) -> int:
    return level * 150


def gain_char_xp(state: GameState, amount: int) -> None:
    p = state.player
    p.xp += amount
    while p.xp >= xp_to_next(p.level):
        p.xp -= xp_to_next(p.level)
        p.level += 1
        p.max_hp += 8
        p.max_energy += 12
        p.hp = min(p.max_hp, p.hp + 8)
        p.energy = min(p.max_energy, p.energy + 12)
        state.log.add(f"You reach level {p.level}! (+8 max HP, +12 max stamina)", (240, 220, 140))


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


# --- gentle bonuses ----------------------------------------------------------
def combat_atk_bonus(state: GameState) -> int:
    bonus = skill_level(state, "Combat") // 3           # +0..+3 attack
    if active_buff(state) == "hearty":
        bonus += 2                                      # a hearty meal steels you
    return bonus

def fishing_catch_bonus(state: GameState) -> float:
    return skill_level(state, "Fishing") * 0.02         # up to +20% catch

def extra_yield_chance(state: GameState, skill: str) -> float:
    chance = skill_level(state, skill) * 0.05           # up to +50% double drops
    b = active_buff(state)
    if (b == "tiller" and skill == "Farming") or (b == "forager" and skill == "Foraging"):
        chance += 0.30
    return chance


# --- quality (0-5 stars) -----------------------------------------------------
STAR = "★"
_QUALITY_KINDS = ("crop", "fish", "artisan", "food", "animal")
_QUALITY_NAMES = ("Honey",)               # tiered items that aren't one of the kinds


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
