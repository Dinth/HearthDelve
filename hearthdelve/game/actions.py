"""Pure resolution of tool use on a tile.

``resolve_tool`` has no side effects: it answers "if I used this tool on this
tile, what would happen?" — returning (success, replacement_tile_id, message).
Both the actual action (main.use_tool) and the target-tile highlight
(rendering.render_facing) call it, so they can never disagree.
"""
from __future__ import annotations

from ..data import content
from ..entities import items
from ..entities.items import Item
from ..world import tile
from ..world.tile import TileType


def resolve_tool(tool: Item, t: TileType) -> tuple[bool, int | None, str]:
    if tool is items.HOE:
        if t.name in ("grass", "meadow", "tall_grass", "path"):
            return True, tile.TILLED, "You till the soil into a neat plot."
        return False, None, "You can only till open ground."

    if tool is items.WATERING_CAN:
        if t.name == "tilled":
            return True, None, "You water the bare soil."
        if t.kind == "water":
            return True, None, "You refill the watering can."
        return False, None, "There's nothing here to water."

    if tool is items.AXE:
        if t.kind == "tree":
            return True, tile.GRASS, "You chop down the tree."
        return False, None, "There's no tree to chop here."

    if tool is items.PICKAXE:
        if t.name == "gem_vein":
            return True, tile.GRASS, "You chip a gem free!"
        if t.name == "ore_vein":
            return True, tile.GRASS, "You mine the ore vein."
        if t.name == "sulphur_deposit":
            return True, tile.GRASS, "You chip away the yellow seam."
        if t.name == "nitre_deposit":
            return True, tile.GRASS, "You scrape the nitre crust free."
        if t.name in ("rock", "ruins_wall"):
            return True, tile.GRASS, "You break the rock apart."
        return False, None, "Your pickaxe needs rock or ore to swing at."

    if tool is items.MACHETE:
        if t.name == "tall_grass":
            return True, tile.GRASS, "You scythe the tall grass."
        if t.kind == "foliage":
            return True, tile.GRASS, "You hack through the foliage."
        if t.kind == "shrub":
            return True, tile.GRASS, "You clear the shrub."
        if t.kind == "shrub_berry":
            return True, tile.GRASS, "You clear the berry shrub."
        return False, None, "There's nothing here to clear with a machete."

    if tool is items.FISHING_ROD:
        if t.kind == "water":
            return True, None, "You cast your line."
        return False, None, "You can only fish in water."

    # A weapon can do the matching tool's job — clumsily (see main.use_tool for
    # the time penalty and reduced yield). An axe-type fells trees; a blade hacks
    # brush and tall grass.
    if tool.kind == "weapon":
        cat = content.profile_of(tool).category
        if cat == "axe" and t.kind == "tree":
            return True, tile.GRASS, "You hack the tree down with your weapon — hard going."
        if cat == "blade" and t.name == "tall_grass":
            return True, tile.GRASS, "You scythe the grass with your blade."
        if cat == "blade" and t.kind in ("foliage", "shrub", "shrub_berry"):
            return True, tile.GRASS, "You slash it away with your blade."

    return False, None, f"You can't use the {tool.name} on that."
