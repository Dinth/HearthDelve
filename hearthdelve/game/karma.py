"""Karma — a slow-moving measure of how kindly the player has lived.

Karma runs from -100 (villainous) to +100 (saintly), starting neutral at 0.
Good deeds nudge it up, unkind ones down. For now few actions touch it, but its
one live consequence is relationships: with good karma the world warms to you
faster and cools slower; with bad karma affection is hard-won and quick to fade.
"""
from __future__ import annotations

MIN_KARMA = -100
MAX_KARMA = 100

# thresholds are "karma is below this" -> label, in ascending order
_LABELS = (
    (-60, "Villainous"),
    (-25, "Wicked"),
    (-8, "Unkind"),
    (8, "Neutral"),
    (25, "Kindly"),
    (60, "Good-hearted"),
    (MAX_KARMA + 1, "Saintly"),
)


def label(karma: int) -> str:
    for hi, name in _LABELS:
        if karma < hi:
            return name
    return "Saintly"


def adjust(state, delta: int) -> None:
    """Nudge the player's karma, clamped to its range."""
    p = state.player
    p.karma = max(MIN_KARMA, min(MAX_KARMA, p.karma + delta))


def buy_mult(karma: int) -> float:
    """What the player PAYS at a counter, scaled by reputation: a beloved hero
    gets a discount, a feared one pays a premium. Soft — at most ±10%, and never
    a lock (you can always buy)."""
    return 1.0 - max(-100, min(100, karma)) / 1000.0     # +100 -> 0.90, -100 -> 1.10


def sell_mult(karma: int) -> float:
    """What the player RECEIVES when a shop buys from them: the good are paid
    better, the ill worse."""
    return 1.0 + max(-100, min(100, karma)) / 1000.0     # +100 -> 1.10, -100 -> 0.90


def scale(karma: int, points: int) -> int:
    """Adjust a friendship change by the player's karma.

    Kindness (positive points) lands harder the higher the karma; slights and
    affection lost (negative points) bite harder the lower it is. At neutral
    karma nothing changes; at the extremes the effect is +/-50%.
    """
    if points >= 0:
        return round(points * (1 + karma / 200))
    return round(points * (1 - karma / 200))
