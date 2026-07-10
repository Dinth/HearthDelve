"""Global constants and tunables for Hearthdelve.

Everything balance-related lives here or in ``data/`` so a tuning pass is a
one-file edit, per DESIGN.md §8/§14.
"""
from __future__ import annotations

# --- Window / layout (cells) -------------------------------------------------
SCREEN_W = 80
SCREEN_H = 50

PANEL_W = 22                       # right-hand status panel
LOG_H = 6                          # bottom message log (incl. its border row)

VIEW_W = SCREEN_W - PANEL_W        # world viewport width  -> 58
VIEW_H = SCREEN_H - LOG_H          # world viewport height -> 44

# --- World -------------------------------------------------------------------
WORLD_W = 1024
WORLD_H = 1024
WORLD_CENTER = (WORLD_W // 2, WORLD_H // 2)

# Rough carrying capacity of surface wildlife, scaled with map area so a bigger
# Vale feels equally alive (worldgen seeds this many; respawn tops back up to it).
WILDLIFE_CAP = int(140 * (WORLD_W * WORLD_H) / (512 * 512))

# Wildness tier thresholds (0..1 field): below T1 = homestead, etc.
TIER1_MAX = 0.34                   # homestead / safe
TIER2_MAX = 0.66                   # edge

# --- Clock / calendar (DESIGN §7) --------------------------------------------
DAY_START_MIN = 6 * 60             # 06:00
DAY_END_MIN = 26 * 60              # 02:00 next day (sleep cutoff)
SEASON_LEN = 28                    # days per season
SEASONS = ("Spring", "Summer", "Fall", "Winter")
YEAR_LEN = SEASON_LEN * len(SEASONS)

# --- Player start ------------------------------------------------------------
START_HP = 50
START_ENERGY = 270        # daily exertion pool (shown in the HUD as "Stamina")
START_STAMINA = 20        # legacy field, unused (kept for save compatibility)
START_GOLD = 0

# --- Action costs: exertion (stamina) and time (seconds) are independent -----
# The day runs 06:00 -> 02:00 (~1200 in-game minutes). For long tasks the clock,
# not exertion, is the real limit. Roads cost no exertion.
MOVE_SECONDS = 30
ROAD_MOVE_SECONDS = 15
WALK_STAMINA = 1          # per off-road step (0 on roads/bridges)

# (stamina, seconds) per action
TILL_COST    = (3, 45)
WATER_COST   = (2, 30)
PLANT_COST   = (2, 40)
HARVEST_COST = (1, 30)
CHOP_COST    = (6, 600)    # felling a tree takes a good while
MINE_COST    = (8, 1200)   # heavy, tiring work underground
MACHETE_COST = (3, 45)
FISH_COST    = (1, 1000)   # avg; actual time is random (see FISH_SECONDS_*)
FISH_SECONDS_MIN = 400     # ~7 min — a cast costs a slice of the day, not half of it
FISH_SECONDS_MAX = 1600    # ~27 min
ATTACK_COST  = (3, 20)
BOMB_COST    = (8, 60)
CRAFT_COST   = (3, 300)    # cooking a dish / fletching a batch: 5 min at the bench
USE_SECONDS  = 45         # fallback time for misc uses

# Combat (DESIGN §7) — light bump combat.
BASE_ATK = 1            # unarmed
SWORD_ATK = 3

# Tool material tiers (blacksmith upgrades, M3b+). Wooden is the starting tier;
# each step up is bigger area / less energy.
TOOL_TIERS = ("Wooden", "Bronze", "Iron", "Steel", "Adamantium", "Mithril")

# --- Colors (RGB) ------------------------------------------------------------
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DIM = (110, 110, 120)
HUD_BG = (18, 20, 28)
PANEL_BG = (24, 26, 36)
SEP = (60, 64, 82)

PLAYER_FG = (255, 255, 255)

HP_COLOR = (214, 92, 92)
ENERGY_COLOR = (236, 196, 92)
STAMINA_COLOR = (110, 188, 220)
GOLD_COLOR = (240, 214, 120)

# Weather glyph tints
SUN_COLOR = (245, 214, 110)

# Target-tile highlight (the tile the active tool would act on).
TARGET_HL = (92, 84, 52)        # neutral reticle: just shows facing
TARGET_OK = (54, 96, 58)        # green: the active tool can act here

# Aiming reticle (targeting mode — throwing, siting a building).
AIM_OK = (72, 120, 80)          # a valid target/placement
AIM_BAD = (120, 60, 56)         # out of range / blocked

# Warning colours (HUD clock + alerts).
WARN_COLOR = (240, 200, 90)     # amber: getting late / running low
DANGER_COLOR = (228, 92, 82)    # red: past midnight / critical

# Time-of-day warning thresholds (minute-of-day; day runs 06:00–02:00).
LATE_WARN_MIN = 22 * 60         # 22:00 — evening drawing on (amber)
MIDNIGHT_MIN = 24 * 60          # 00:00 — past midnight (red)
# Low-resource warning fractions.
LOW_HP_FRAC = 0.25
LOW_ENERGY_FRAC = 0.15
