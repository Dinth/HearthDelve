# Hearthdelve

A cozy farming & crafting life-sim with the soul of a surface roguelike, built in
Python 3 + [tcod](https://python-tcod.readthedocs.io). Tend a homestead in
Hollowmere Vale by day; wander the procedurally-generated wilds when you choose.

See [`DESIGN.md`](DESIGN.md) for the full design (frozen at v5).

## Download

Prebuilt standalone binaries for **Linux, macOS and Windows** are published on
every push under the [**rolling release**](https://github.com/Dinth/HearthDelve/releases/tag/rolling)
— no Python needed. Grab the one for your OS and run it in a terminal. (On
macOS, first run: right-click → Open, or clear Gatekeeper with
`xattr -dr com.apple.quarantine hearthdelve-macos`.)

## Run it

```bash
# one-time setup
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt

# play
./.venv/bin/python -m hearthdelve
```

A window titled *"Hearthdelve — Hollowmere Vale"* opens.

## Sharing it with testers

**Option A — double-click launcher (testers have Python 3).** Zip the project
folder and send it. On the tester's machine:
- macOS: double-click **`run.command`** (or `bash run.command`)
- Windows: double-click **`run.bat`**
- Linux: `./run.sh`

The script makes a local `.venv`, installs deps, and launches the game — no dev
setup needed beyond Python 3.

**Option B — standalone executable (testers need nothing installed).** Build a
single self-contained binary with [PyInstaller]:

```bash
./build.sh          # -> dist/hearthdelve  (a ~17 MB double-clickable executable)
```

Send them `dist/hearthdelve` (macOS/Linux) or `dist\hearthdelve.exe` (Windows).
tcod, SDL, numpy, and the font are all bundled.

> **Caveat:** a PyInstaller binary only runs on the OS it was built on (a macOS
> build won't run on Windows). Build on each OS you need to target, or use
> Option A for cross-platform testers. On macOS, testers may need to right-click
> → Open the first time (unsigned app).

[PyInstaller]: https://pyinstaller.org

## Controls (M1)

| Key | Action |
|-----|--------|
| Arrow keys | move (up / down / left / right) |
| Numpad `1`–`9` | move, including diagonals |
| Numpad `5` / `.` | wait a turn |
| `Space` | use the active tool / plant the selected seed on the faced tile |
| `1`–`9` (top row) | select hotbar tool or seed |
| `g` | gather / harvest a crop, or load/collect a machine |
| `c` | craft, build machines, cook |
| `b` | shipping bin — sell goods (stand beside it) |
| `t` | talk to a villager / open their shop |
| `f` | give a villager a gift |
| `s` | sleep (in or beside your bed) → next day |
| `i` | inventory |
| `e` | equipment |
| `l` | look around (move a cursor, read what's there) |
| `?` | help + encyclopedia (← → pages, ↑ ↓ scroll) |
| `Esc` | quit / close a screen |

**Using tools:** tools act on the tile you face (the last direction you moved),
which is **always highlighted** — it glows **green** when the active tool can
act there. Bumping into an obstacle (tree, rock, wall) just turns you to face it
without moving, so you can line up a chop or a dig. Then press `Space`:
the **Hoe** tills grass into soil, the **Axe** fells trees, the **Pickaxe**
breaks rock and ore veins, the **Machete** clears foliage and shrubs, the
**Watering Can** waters soil, the **Fishing Rod** casts at water. Each use costs
energy. Tools start at **Wooden** tier (later upgradeable: Bronze → Iron → Steel
→ Adamantium → Mithril).

**The wild flora:** individual trees (oak, maple, birch, poplar, willow, pine,
spruce) are passable — you walk among them. Dense groves choke with impassable
**foliage**; **shrubs** also block. Both are cleared with the machete (dropping
fibre). Rare **berry shrubs** (raspberry, gooseberry, currant) drop fruit when
cleared — and fruit is what the keg and jar turn into wine and jam.

## Status — Milestones 1–4 ✅ (vertical slice complete)

**M4 — the wilds:**
- **Dungeons**: procedural floors (rooms + corridors) with fog-of-war, reached via
  themed surface sites (a boulder-strewn mine, a ruin). Stairs `>` / `<` to
  descend/ascend; sparse ore/gem **veins** to mine.
- **Light combat**: bump-attack gentle monsters (slime, bat, boar) that wake in
  your FOV and chase. Throw a **Bomb** (`a`, craft from coal + fiber) to hit a
  group and shatter rock/ore. Faint (0 HP / 0 energy / past 2 AM) → hauled home,
  minus loose loot and 10% gold; sleep heals.
- **Fishing**: cast the rod at water for a **season-specific** catch (12 species);
  fish sell, gift, and cook.
- **Save/Load**: the game **auto-saves each morning and on quit** to
  `~/.hearthdelve_save.json`, and **auto-continues** on launch. Run with
  `--new` to start over.

## Status — Milestones 1, 2, 3a & 3b ✅

**M3b — Villages, NPCs & trading:**
- Two villages — **Mossford** (the hamlet, far east) and **Cinderhope** (the
  outpost, far west) — with six residents who keep a daily schedule. **Roads**
  link them through your farm (with **bridges** over rivers); travelling a road
  is twice as fast as crossing open country.
- **Talk** (`t`) and **gift** (`f`) raise **friendship hearts**; each villager has
  loved/liked/disliked items (your crops & crafts are the currency of friendship).
- **General Store** (Marda) sells seeds for all crops; the **Blacksmith** (Bron)
  **upgrades tools** up the ladder Wooden → Bronze → Iron → Steel → Adamantium →
  Mithril (gold + copper bars), each tier cutting the tool's energy cost.

## Status — Milestones 1, 2 & 3a ✅

**M3a — Make & trade (crafting + selling):**
- **Gather** raw materials: chop trees → Wood, mine rock → Stone, mine ore veins
  → Copper Ore + Coal.
- **Shipping bin** (`b` beside it): drop crops/goods in; they sell for gold
  overnight.
- **Crafting** (`c`): build machines & sprinklers, and cook dishes that restore
  energy.
- **Machines** (load/collect with `g`): the **Furnace** smelts ore → bars, the
  **Preserves Jar** turns crops → jam, the **Keg** ferments crops → wine — each
  processing over in-game time. The **value ladder** (raw < jam < wine) is the
  money. **Sprinklers** auto-water adjacent soil each morning.

## Status — Milestones 1 & 2 ✅

**M2 — Hearth & seasons (farming loop):**
- Till soil (Hoe) → select seeds (`6`) → `Space` to plant → water daily (Can)
  → `s` to sleep → crops advance a growth stage each watered day → `g` to
  harvest when ripe. Crops render on the soil through their growth stages.
- **Seasons** (28-day Spring/Summer/Fall/Winter): crops are season-bound and
  wither when the season turns; planting out of season is refused.
- **Weather** rolled each dawn (clear / rain / storm / fog / snow), shown in the
  HUD, with animated **rain and snow**; rain auto-waters your crops.
- **Day/night light**: the whole valley tints cool at night, warm at dawn/dusk,
  bright at midday as the (slowed) clock advances.
- **Energy & collapse**: tools cost energy; hit 0 (or stay up past 02:00) and you
  faint, waking the next morning with reduced energy.

**M1 — walking skeleton:**

- Procedurally-generated 200×200 surface world: homestead carved at center
  (house, bed, shipping bin, fenced tilled plot), with meadow / woods / river /
  rocky-ore / moor / ruins biomes radiating outward by "wildness" distance.
- Scrolling camera viewport, right-hand status panel (date/season, time,
  HP / energy / stamina / gold), and a bottom message log.
- 8-direction movement with tile collision; the in-game clock advances per step.
- Two dungeon entrances placed out in the wilds (enterable in a later milestone).
- **Ambient animation**: wind gusts ripple through the grass, waves shimmer
  across water, and ore veins glint — subtle time-based brightness/colour shifts.
- **Look** mode (`l`): move a cursor and read a description of any tile.
- **Help** overlay (`?`), **inventory** (`i`) and **equipment** (`e`) screens.
- **Hotbar** (`1`–`9`): quick-select among the starter tools (Hoe, Watering Can,
  Axe, Pickaxe, Fishing Rod); starting inventory holds 15 parsnip seeds.

### Roadmap

- **M2** ✅ — farming loop (till/plant/water/grow/harvest) + season & weather clock
- **M3** ✅ — crafting (bench + machines + cooking), two villages, NPCs, trading
- **M4** ✅ — the wilds: dungeons, light combat, fishing, save/load

## Project layout

```
hearthdelve/
  main.py            entry point + main loop
  engine/            constants, font loading, rendering, input
  world/             tile types, worldgen, the map container
  entities/          player (monsters/npcs to come)
  game/              state, turn scheduler (actions/crafting/economy to come)
  data/              content tables (to come)
```
