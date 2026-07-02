"""Skills: Farming, Foraging, Mining, Fishing, Combat.

Each gains XP from the matching activity and levels up (0-10). Levels grant
small, cozy bonuses. The character sheet shows level and progress.
"""
from __future__ import annotations

from .state import GameState

SKILLS = ("Farming", "Foraging", "Mining", "Fishing", "Combat")
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
    before = level_of(p.skills.get(skill, 0))
    p.skills[skill] = p.skills.get(skill, 0) + xp
    if level_of(p.skills[skill]) > before:
        state.log.add(f"{skill} skill is now level {level_of(p.skills[skill])}!", (170, 210, 240))
    gain_char_xp(state, xp)          # all activity feeds general experience


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


# --- gentle bonuses ----------------------------------------------------------
def combat_atk_bonus(state: GameState) -> int:
    return skill_level(state, "Combat") // 3            # +0..+3 attack

def fishing_catch_bonus(state: GameState) -> float:
    return skill_level(state, "Fishing") * 0.02         # up to +20% catch

def extra_yield_chance(state: GameState, skill: str) -> float:
    return skill_level(state, skill) * 0.05             # up to +50% double drops
