# Hearthdelve Bug Tracker

From the 2026-07-02 full-code review. Status: `[x]` fixed (2026-07-03), `[~]` deferred (needs design / larger feature), `[ ]` open.

All fixes were compiled, smoke-tested (`HEARTHDELVE_SMOKETEST`), and covered by
scratch verification scripts (save round-trip, dungeon connectivity over 300
floors, combat kill-parity, jar/keg margins, skill cap, build timing).

## Critical

- [x] **SAVE-1** Incompatible/corrupt save no longer silently overwritten. `SAVE_VERSION` bumped 4→5; `save.backup()` copies the old save to `.bak` before a failed load falls through to a new game (`save.py`, `main.load_or_new`).
- [x] **SAVE-2** Surface wildlife now serialized (`"wildlife"` key) and restored exactly on load, replacing the seed-scatter — kills and roused states stick (`save.py`).
- [x] **SAVE-3** `Animal.petted_today` now saved/restored (`save.py`).
- [x] **SAVE-4** Player-raised coop/barn `buildings` records now saved (filtered to player-built) and re-registered on load (`save.py`).
- [x] **DGN-1** Dungeon floor seed derived arithmetically (crc32 of kind + seed/depth/day) instead of salted `hash()` — floors stable across reloads (`delve.py`).
- [x] **DGN-2** Underground lakes exclude the entry/stairs rooms and are reverted if a connectivity flood-fill from up-stairs can't reach the down-stairs or any room center (`dungeon.py`). *(Also surfaced & fixed a pre-existing bug: ore/gem veins could pinch a corridor shut and strand rooms — a final repair pass now digs an L-corridor to any stranded target.)*
- [x] **CMB-1** Extracted a shared `_on_kill` helper: the bomb now applies the karma penalty on peaceful wildlife, awards no Combat XP / no `monsters_slain` for wildlife, rolls monster drops on dungeon kills, and wakes blast-damaged survivors (`combat.py`).
- [x] **HUS-1** Outbuilding `ready_at` anchored to the dawn `BUILD_DAYS` mornings out, so it finishes on the promised morning (not a day late) and no longer reports "finished" while still scaffold (`husbandry.py`).
- [x] **ITM-1** Egg/Milk/Cheese wired in: eat menu now lists anything with `energy>0`; gifting and collapse loot-drop include kind `"animal"` (`main.py`/`crafting.py`, `village.py`, `farming.py`).
- [x] **ITM-2** Gift menu now removes the exact quality stack selected (and a finer gift pleases a little more) (`village.py`, `main.py`).
- [x] **CRF-1** Preserves jar and keg now pick the input with the best `output-input` margin — no more pumpkin→pickles value loss, and grapes are never blocked by held honey (`crafting.py`; dead `_best_crop` removed).
- [x] **CRF-2** Machines (and coop-housed animals) can no longer be placed on a dungeon floor (`crafting._place_machine`).
- [x] **GEN-1** Homestead shifts east to clear the river's actual incursion across its span; spawn fallback spirals out to the nearest walkable tile (`worldgen.py`).

## Medium

- [x] **UI-1** Removed stale "plant seeds once farming opens in M2" / "fishing in M4" placeholder text (`actions.py`).
- [x] **UI-2** Quit menu: `q`/`S`/`Enter` all save-and-quit (so a reflexive `qq` can't lose the day); quit-without-saving moved to the labeled `Backspace` (`input.py`, `main.py`, `rendering.py`).
- [x] **INP-1** OS key-repeat no longer cancels a run (interrupt check now ignores `event.repeat`) (`main.py`).
- [x] **INP-2** Runs now scoop gold underfoot and stop before an animal/NPC/creature; `try_move` no longer walks onto a villager (`main.py`).
- [ ] **INP-3** SDL Quit (Cmd+Q) still only closes modals rather than exiting. Left as-is: a clean fix (route Quit → save-and-exit) needs care so it doesn't quit unintentionally mid-modal. Low priority; window-close button works.
- [x] **VIL-1** All shopkeepers (incl. general store & blacksmith) now get the daily talk greeting → friendship, festival treats, heart gifts (`main.py`).
- [~] **VIL-2** Village-field crops are still free to harvest. Deferred — it's a design call (cozy free-harvest vs. theft/karma). Flagging for your decision rather than silently changing it.
- [x] **ITM-3** `Inventory.remove` now returns True only when the full qty was removed (was reporting success on a partial take) (`items.py`).
- [x] **SKL-1** Skill XP caps at level 10 and stops feeding character XP past the cap; `roll_quality` clamps character level — no more runaway quality/HP inflation (`skills.py`).
- [x] **WLD-1** Wildlife `_occupied` now treats out-of-season critters as non-blocking (matching `mob_at`), and a critter co-located with the player is nudged to a free tile (`wildlife.py`).
- [x] **WLD-2** Bears only target and raid beehives that actually have a queen (`wildlife.py`).
- [x] **TRN-1** `advance_time` parameter renamed `minutes`→`seconds` with a unit note (all callers already passed seconds) (`turns.py`).

## Low

- [x] **DGN-3** Single-room floor places the two stairs on opposite interior corners (no more lost up-stairs) (`dungeon.py`).
- [x] **DGN-4** Monster/boss/vault-guard spawns skip already-occupied tiles (no stacking) (`dungeon.py`).
- [x] **GEN-2** Deleted the dead `find()` helper with the inverted axis unpack (`worldgen.py`).
- [x] **CNT-1** `ALL_SEEDS` now derives from all crops + saplings (was a stale one-element list; the encyclopedia page itself was already correct) (`content.py`).
- [x] **UI-3** Eat menu and tavern menu now show the HP restored alongside stamina (`rendering.py`, `main.py`, `village.py`).
- [x] **UI-4** Bomb (kind `item`) is filed under "Craft", not "Cook", in the craft menu and codex (`rendering.py`).
- [x] **UI-5** A blocked run now says "You can't run that way." (`main.py`).
- [x] **INP-4** Cobble now counts as road for walking too (fast & effortless), matching running (`main.py`).
- [x] **QLT-1** `edible_items` moved to `crafting.py`; rendering no longer imports from `..main` (render→app cycle broken) (`crafting.py`, `main.py`, `rendering.py`).

## Deferred (needs design or is a larger feature)

- [~] **DEF-1** Konami code entry has gameplay side effects (arrows move you, `a` throws a real bomb) — needs an input-consuming design or a different activation (`main.py:712-719`).
- [~] **DEF-2** Furnace auto-smelts "best bar" so IRON_BAR (needed ×3 for the tool ladder) requires coal-dumping — real fix is a choose-input submenu for machines (also the nicer long-term fix behind CRF-1).
- [~] **DEF-3** Modal panels (mail, inventory, craft) don't scroll; long content silently hides rows + footer hints.
- [~] **DEF-4** Look-mode cursor clamped to viewport; camera doesn't follow.
- [~] **DEF-5** Monster "charge" behavior declared in data + flavor text but not implemented — fold into the dungeon-depth pass.
- [~] **DEF-6** Monsters get exactly one action per `advance_time` call regardless of duration — mining next to a monster is free time.
- [~] **DEF-7** Weather particles overdraw entity glyphs; NPCs are tinted by night but monsters/animals aren't.
- [~] **DEF-8** No collapse warning as 02:00 approaches; no message-log scrollback; inventory screen read-only — QoL batch.
- [~] **DEF-9** `quests.check` runs every frame at ~30fps.
- [~] **DEF-10** MessageLog grows unbounded; only 5 lines shown.

## Balance (from the review — not code bugs, tuning decisions for you)

Grape→wine (~110 g/day/tile) and honey→mead chains and zero-upkeep animals
(~560 g/day/barn) dwarf normal crops (~22 g/day); 55 wild fruit trees refill
every morning (~1,100 g/day from day 1). Cooking is value-negative. Combat
flatlines after depth 2 (one weapon, no armor, food out-heals every monster)
while ore/chest rewards scale to depth 6+. See the review summary for the math.
The organic pass (fruit trees / wildlife / shrubs drifting like the mushroom
system) would fix the wild-tree faucet and the "clockwork" feel together.
