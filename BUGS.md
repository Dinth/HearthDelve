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

## Second pass (2026-07-03) — deferred items now addressed

- [x] **INP-3** SDL Quit (Cmd+Q / window close) now leaves immediately without saving, from any screen (`input.py` `sysquit`, `main.py`).
- [~] **DEF-1** Konami code still moves the player / ships on `b` (left per your call), but the `a`→bomb side effect is gone: throwing moved to the targeting key, so `a` is now unbound.
- [x] **DEF-2** Loading a machine opens a **choose-what-to-make menu** (reuses the inventory-list style) instead of a silent auto-pick — fixes the pumpkin→pickles trap and the "honey blocks grape wine" / iron-vs-steel problem (`crafting.machine_load_options`/`load_machine_choice`, `render_load_machine`).
- [x] **DEF-3** Inventory, gift, eat, mail, and the machine menu now scroll (windowed to the selection, with ▲/▼); the codex already scrolled.
- [x] **DEF-4** Look cursor roams the whole map and the camera follows it (`cam_focus`, `camera_origin`, `clamp_look`).
- [~] **DEF-5** Monster "charge" — still deferred, folding into your planned combat/equipment revamp.
- [x] **DEF-6** `advance_time` now steps actors proportionally to elapsed time (capped); chop/mine **animate over frames** so critters visibly move, and a nearing hostile **interrupts** them (peaceful critters/villagers don't). Fishing refuses to start with a threat near (`turns.py`, `main.py` busy loop, `_threat_near`).
- [x] **DEF-7** Weather no longer overdraws entity glyphs (occupied cells skipped) and villagers/wildlife/animals now dim at night like the ground (`render_world` unified entity pass).
- [x] **DEF-8** Inventory has a cursor + `d` to drop/trash; plus the collapse/low-HP/low-stamina warnings below and log scrollback.
- [x] **DEF-9** `quests.check` runs after state-changing actions (and on run/rest completion), not every frame.
- [x] **DEF-10** Message log is bounded (400) with a full scrollback view on `m`.

### Also added this pass
- **Targeting mode** (ADOM-style, reusable): aim a cursor and confirm. Bound to **`t`** (throw bombs; will extend to bows/ranged later) and reused by **`p`** to site carpenter buildings with a live footprint preview. **Talk moved to `Shift+C`.**
- **Warnings**: amber clock + log nudge from 22:00, red from midnight (collapse at 02:00); one-shot low-HP and low-stamina alerts (re-arm on recovery / each morning).
- **Organic-lite regrowth** (per your spec — not full mushroom-style drift): orchard/wild trees fruit every ~4 days (jittered), never wither/move; berry shrubs are picked with `g` (renewable), persist, and re-berry in ~3 days; a rare adjacent tree/shrub takes root over the seasons; wildlife slowly trickles back after a cull (cap 140). New state (`Tree.refruit_in`, `GameMap.berry_regrow`) is saved.

## Third pass (2026-07-03) — reported issues

- [x] **Windows crash** `AttributeError: KeySym has no attribute 'b'` — tcod version drift (newer tcod on Windows names letter keys `KeySym.B`, this Mac uses `.b`). Key handling now matches letters/digits by character value and the Konami code by SDL keycode, so it works across tcod builds (`input.py`, `main.py`).
- [x] **Invisible furniture** (shipping bin, post box, beds, market stalls — and, silently, the card-suit crops/trees, cheese, milk, boat, beehive, scaffold). Root cause: no font was bundled, so it fell back to a system font (macOS SFNSMono) that lacks those glyphs. Fixed by bundling **DejaVu Sans Mono** at `hearthdelve/assets/font.ttf` (full coverage of all 82 game glyphs, verified); `build.sh`, `hearthdelve.spec`, and all three CI build steps now embed it so every platform's binary renders them.
- [x] **Signposts on household spurs** — signposts placed at any 3-road junction, so a short spur to one house got one. Now only placed where 3+ branches are genuine through-routes (a spur that dead-ends at a dwelling no longer counts) (`worldgen._place_waypoints`/`_branch_through`).
- [x] **Look readout truncated** — the single-row banner was overwritten by the hint. Look mode now draws a word-wrapped multi-line box, and **signposts read out the notable places and their compass bearings** (`render_look`, `describe`/`_signpost_text`).

## Still deferred (your call)

- [~] **VIL-2** Village-field crops remain free to harvest — cozy free-foraging vs. theft/karma is a design decision for you.
- [~] **Balance pass** — prices/earnings tuning (grape-wine/animal/mead faucets, cooking value, combat depth curve) left for your planned balance + combat/equipment revamp. The organic-lite tree/shrub cadence already trims the biggest wild-fruit faucet.

## Fourth pass (2026-07-04) — post-review audit fixes

Fresh full-code audit of the systems added after the last review (combat/ADOM
rework, material+affix gear, ranged weapons, land ownership/tax).

**Bugs fixed**
- [x] **SAVE-5** Mail's `tax` flag was dropped on save; a reloaded bailiff notice
  became an ordinary letter, so land tax could no longer be paid (and the karma
  penalty kept accruing) and duplicate notices piled up. Flag now persisted;
  `SAVE_VERSION` 6→7 (`save.py`).
- [x] **VIL-3** Festival treats & heart-milestone gifts from shopkeepers
  (general store, blacksmith) were consumed with no on-screen feedback — the
  shop panel only showed greetings for tavern/carpenter. Rewards now also log,
  and the greeting shows for every shop (`village.py`, `rendering.py`).
- [x] **VIL-4** Gift-menu taste tags used exact-item identity while the reaction
  math matches by family, so a "loves Jam" NPC showed no tag on a specific jam
  yet still gave +80. Tags now use the same `_matches` logic (`rendering.py`).
- [x] **VIL-5** A commissioned building could not be cancelled, locking the
  player out of the carpenter. Added a "Cancel current order" entry that refunds
  gold + materials (`village.py`, `rendering.py`). Also: heart gifts now fire
  ascending (5 before 8) so tokens arrive in order.

**Combat & monster-level balance pass**
- [x] **CMB-2** Monsters now carry a `level` (≈ dungeon depth, ±1 jitter, floored
  at the kind's `min_depth`). Stats scale with the levels a mob stands *above*
  its intro depth, so same-kind mobs on a floor differ and deep floors are no
  longer trivialised by static templates (`content.make_mob`, `dungeon.py`,
  `monster.py`). Shown in the look readout.
- [x] **CMB-3** Monster drops scale with level: better drop odds, a chance of a
  second reagent, and a depth-appropriate ore/gem trophy from a tough kill
  (`content.monster_drops`, `combat._on_kill`).
- [x] **CMB-4** The Combat skill's Dodge contribution was halved (it also feeds
  to-hit & crit); a trained player was becoming near-unhittable (`combat.player_dv`).
- [x] **CMB-5** A landed player hit now always chips ≥1 through Protection
  (`min_dmg=1`), so a high-PV foe is slow to fell rather than immune to all but
  crits; a monster's blow can still be fully soaked by the player's armour
  (`combat._resolve`).

- [x] **CMB-6** Arrows are now tiered ammo. A plain **wooden arrow** (1 Wood → 5)
  is weak and flies a touch wide; **metal-tipped arrows** (1 Wood + 1 ore → 5,
  via a new "Metal-tipped Arrows" chooser that reuses the machine-choice menu)
  hit harder the finer the ore (copper→mithril). Any bow looses any arrow and
  spends your **best** one first, so crafting good ammo pays off immediately.
  Ranged stays stronger than melee by design; ammo tier + quantity is the lever
  (`content.AMMO`/`ARROW_FROM_ORE`, `combat.fire_ranged_at`, `crafting.craft_choice`).

Still open (your call): food out-healing mid-fight; the economy faucets below.

**Look-mode clarity (tester feedback: newcomers didn't realise they were in Look mode)**
- [x] **UX-6** Look mode now opens with a clear, colour-barred **mode banner**
  that names the repurposed keys — "» LOOK — arrows move the cursor, not you ·
  Esc/l to exit" — so a new player never wonders why "moving" doesn't move them.
- [x] **UX-7** A **one-shot nudge** the first time you ever enter Look explains it
  in the log (`look_intro` stat flag).
- [x] **UX-8** A faint **tether** tints the tiles between you and the look cursor,
  so the cursor is unmistakably yours and easy to find if it has roamed off
  (`render_look`, reusing the Bresenham helper). (Deferred by choice: dimming the
  whole viewport and an animated reticle — kept it minimal.)
- [x] **UX-9** Status panel: the equipped-weapon line and the Goals line both
  landed on row 27 with a full (8-slot) hotbar, so "Goals 0/10" overdrew "⚔ Rusty
  Iron Sword" into "Goals 0/10on Sword". The goals block now flows below the
  weapon line, and long affixed weapon names are truncated to the panel width
  (`render_panel`).

## Balance (from the review — not code bugs, tuning decisions for you)

Grape→wine (~110 g/day/tile) and honey→mead chains and zero-upkeep animals
(~560 g/day/barn) dwarf normal crops (~22 g/day); 55 wild fruit trees refill
every morning (~1,100 g/day from day 1). Cooking is value-negative. Combat
flatlines after depth 2 (one weapon, no armor, food out-heals every monster)
while ore/chest rewards scale to depth 6+. See the review summary for the math.
The organic pass (fruit trees / wildlife / shrubs drifting like the mushroom
system) would fix the wild-tree faucet and the "clockwork" feel together.
