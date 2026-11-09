# Hearthdelve

A cozy farming & crafting life-sim with the soul of a classical roguelike, built
in Python 3 + [tcod](https://python-tcod.readthedocs.io). Farm a homestead in
Hollowmere Vale by day, delve the dark below when you choose, and trade it all
back into the villages.

See [`DESIGN.md`](DESIGN.md) for the full design — a living document that
describes the game as built.

## Download

Prebuilt standalone binaries for **Linux, macOS (Apple Silicon & Intel) and
Windows** are published under the
[**rolling release**](https://github.com/Dinth/HearthDelve/releases/tag/rolling)
and on [**itch.io**](https://dinth.itch.io/hearthdelve) (the itch app keeps it
up to date) — no Python needed. Grab the one for your OS and run it in a terminal. (On
macOS, first run: right-click → Open, or clear Gatekeeper with
`xattr -dr com.apple.quarantine <file>`.)

**NixOS** (no FHS loader, so the prebuilt binary won't start bare):

```bash
nix run github:Dinth/HearthDelve      # build & play from source (flake)
# …or run the release binary through an FHS shim:
steam-run ./hearthdelve-linux
```

## Run it

```bash
# one-time setup
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt

# play
./.venv/bin/python -m hearthdelve
```

A window titled *"Hearthdelve — Hollowmere Vale"* opens.

## Saves

The game **auto-saves each morning and when you quit** (with `q` or the window's close
button; Cmd+Q leaves at once without saving), to
`~/.hearthdelve_save.json` (with the previous save kept beside it as
`.bak`), and **continues it** on the next launch. Pass `--new` to start a new
life instead. Set `HEARTHDELVE_SAVE` to keep the save somewhere else.

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

## Controls

The keymap follows ADOM: movement on the arrows and numeric keypad (there are
deliberately no vi-keys), letters for commands. The in-game codex (`?`) is the
always-current reference.

| Key | Action |
|-----|--------|
| Arrow keys | move (up / down / left / right) |
| Numpad `1`–`9` | move, including diagonals |
| Numpad `5` / `.` | wait a moment |
| `w` then a direction / `.` | run until something happens / rest a while |
| `Space` | use the active tool, or plant the selected seed, on the tile you face |
| `1`–`9`, `0` (top row) | pick a hotbar slot (tool or seed) |
| `g` | gather / harvest, load or collect a machine, open a chest, read a notice board or post box |
| `>` / `<` | go down / up stairs |
| `c` | craft, build machines, cook |
| `p` | site a building ordered from the carpenter |
| `x` | eat (restores stamina & health) |
| `b` | shipping bin — sell goods (stand beside it) |
| `t` | aim & loose a readied bow or sling, or throw a bomb (`Tab` swaps between them, `Enter`/`Space` fires) |
| `Shift`+`C` | talk to a villager / open their shop |
| `f` | give a villager a gift |
| `s` | sleep in your bed → next day |
| `i` | pack · `e` equipment · `v` character sheet |
| `j` | journal (goals, favours, projects, collection, almanac) · `r` relationships |
| `m` | world map · `h` or `Shift`+`M` message history (`PgUp`/`PgDn` page through it) |
| `l` | look around (move a cursor, read what's there) |
| `?` | codex: help & encyclopedia (← → pages, ↑ ↓ scroll) |
| `Shift`+`U` | mute / unmute the music |
| `q` / `Esc` | quit: the prompt saves and quits on `Enter`, quits without saving on `Backspace` · `Esc` also closes a screen |

**In the pack:** press an item's letter to pick it, `Enter` to use or equip
it, `Shift`+`D` to drop the stack, `Tab` to filter by category.

**Using tools:** tools act on the tile you face (the last direction you moved),
which is **always highlighted** — it glows **green** when the active tool can
act there. Bumping into an obstacle (tree, rock, wall) just turns you to face it
without moving, so you can line up a chop or a dig. Then press `Space`:
the **Hoe** tills grass into soil, the **Axe** fells trees, the **Pickaxe**
breaks rock and ore veins, the **Machete** clears foliage and shrubs, the
**Watering Can** waters soil, the **Fishing Rod** casts at water. Each use costs
stamina and time. Tools start at **Wooden** and a blacksmith upgrades them:
Bronze → Iron → Steel → Adamantium → Mithril, each tier cheaper to use.

## What's in the Vale

- **A 1024×1024 world** generated from a seed: four regions (deep wildwood,
  fen, rocky hills, open plains) meeting at your homestead, a river and a
  southern sea — and, past the western edge, the **Westreach**, a wilder land of
  ash and a live volcano.
- **Farming** across four 28-day seasons: 26 crops with 0–5 star quality,
  orchard trees, six kinds of livestock, sprinklers and a greenhouse.
- **Crafting** at 31 machines — furnace, anvil, keg, loom, apothecary, cellar
  and more — where a product's value grows from what went into it.
- **Villages and folk:** Mossford, Cinderhope, Saltmere and Fenwick, a
  woodcutters' camp, a forester's hut and the dwarf town of Khazgrim — 42
  residents with schedules, tastes, friendships, favours and festivals.
- **Dungeons** of six kinds, themed to their ground, re-rolled daily, with a
  boss and a vault in every tenth-floor Deep Sanctum. Combat follows ADOM
  (to-hit against DV, damage against PV), and is always optional.
- **No permadeath, no game over.** Faint and you wake in your bed, short some
  loose loot and gold; the land, tools and friendships stay.

## Development

```bash
./.venv/bin/python -m unittest discover -s tests       # the test suite (headless)
HEARTHDELVE_SMOKETEST=1 ./.venv/bin/python -m hearthdelve   # one-frame render check
```

CI runs the suite on every push, and the release binaries aren't built if it fails.

## Project layout

```
hearthdelve/
  main.py         the tcod context and the main loop
  screens.py      the screen stack: one class per mode (play, pack, shop, aim, fishing…)
  engine/         rendering, the animation engine and its effects, the window kit, the codex,
                  input, saving, audio, the font
  world/          tiles, the world and dungeon generators, the map container, crops
  entities/       the player, items, monsters, NPCs, animals, machines
  game/           the simulation: farming, crafting, combat, villages, delving, the economy…
  data/           content.py — every table: crops, recipes, machines, monsters, NPCs, projects
tests/            the unittest suite
```
