"""Planted crops living on tilled soil.

A ``CropPlot`` tracks one planted tile's growth. The world holds a
``{(x, y): CropPlot}`` map; growth ticks once per day at sleep.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..data.content import Crop

# Glyphs for the pre-mature growth stages (mature uses the crop's own glyph).
GROWTH_GLYPHS = (".", ",", '"')
SEEDLING_FG = (120, 180, 110)
SPROUT_FG = (110, 200, 120)
DEAD_FG = (150, 120, 90)


@dataclass
class CropPlot:
    crop: Crop
    days_grown: int = 0
    watered: bool = False
    dead: bool = False

    @property
    def mature(self) -> bool:
        return not self.dead and self.days_grown >= self.crop.days_to_mature

    @property
    def stage(self) -> int:
        """0..2 while growing, 3 when mature, -1 when dead."""
        if self.dead:
            return -1
        if self.mature:
            return 3
        d = max(1, self.crop.days_to_mature)
        return min(2, int(self.days_grown / d * 3))

    def glyph(self) -> str:
        if self.dead:
            return "✗"
        if self.mature:
            return self.crop.glyph
        return GROWTH_GLYPHS[self.stage]

    def color(self) -> tuple[int, int, int]:
        if self.dead:
            return DEAD_FG
        if self.mature:
            return self.crop.color
        return SEEDLING_FG if self.stage == 0 else SPROUT_FG


def advance_growth(plot: CropPlot, season: str) -> None:
    """Tick one day. Out-of-season crops wither; watered crops advance."""
    if plot.dead:
        return
    if plot.crop.season != season:
        plot.dead = True
        return
    if not plot.mature and plot.watered:
        plot.days_grown += 1
    plot.watered = False


# --- Orchard trees -----------------------------------------------------------
SAPLING_GLYPH = "τ"
SAPLING_FG = (150, 200, 120)
TREE_GLYPH = "♣"
TREE_FG = (96, 150, 78)


@dataclass
class Tree:
    name: str
    fruit: object            # the produce Item
    fruit_color: tuple
    season: str
    days_to_mature: int
    age: int = 0
    has_fruit: bool = False

    @property
    def mature(self) -> bool:
        return self.age >= self.days_to_mature

    def glyph(self) -> str:
        return TREE_GLYPH if self.mature else SAPLING_GLYPH

    def color(self) -> tuple:
        if not self.mature:
            return SAPLING_FG
        return self.fruit_color if self.has_fruit else TREE_FG


def advance_tree(tree: Tree, season: str) -> None:
    """A day passes: the tree ages, and bears fruit each morning in its season."""
    tree.age += 1
    tree.has_fruit = tree.mature and tree.season == season
