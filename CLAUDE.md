# Hearthdelve

A terminal ASCII game (Python + tcod) that crosses a **classical roguelike** (ADOM,
ToME — deep dungeons, bump combat, monsters, loot, permadeath-adjacent stakes) with a
**cozy farming sim** (Stardew Valley, Coral Island — crops, seasons, animals, artisan
goods, villagers, friendship) in one persistent **open world**: farm on the surface by
day, delve the dark below, and trade it all back into the villages.

## Design north star

**A strong feeling of progression, without ever limiting freedom.**

- **Progression is efficiency, not permission.** Nothing is hard-locked behind gear,
  level or quest flags. A wooden pickaxe can chip at the deepest mithril vein — it's
  just slow, exhausting and wasteful. Better tools, skills, meals and jewellery make
  the same world *cheap*, not newly *allowed*. Prefer cost gradients (time, stamina,
  yield, risk) over walls; when a system needs a gate, make it soft and explain it
  in-fiction ("your bronze pick barely bites — Steel would serve").
- **The day has two budgets: time and stamina.** Tools are the multiplier that
  stretches both; depth fatigue, travel and heavy work spend them. The player chooses
  where the day goes — the game never chooses for them.
- **Organic, not mechanical.** Spawns, regrowth, requests, market cravings and NPC
  gifts drift on seeded randomness — never fixed spots or metronome cadences. The
  world should feel like it breathes, not tick.
- **Everything produced needs somewhere to go.** New items must have sinks beyond the
  shipping bin: dishes to loved-dish gifting, materials to request-board favours,
  goods to crafting chains. Rarity justifies reward — a rare input (bee queens, deep
  gems) should pay generously even at low effort.
- **Information over hand-holding.** Surface the world's state (journal tabs, panel
  hints, look-mode, codex) so the player can plan; never auto-play for them.

## Practicalities

- Run: `./run.sh` (or `python play.py`). One-frame render check:
  `HEARTHDELVE_SMOKETEST=1 python -m hearthdelve`.
- Content is data-driven in `data/content.py` + `entities/items.py`; game logic in
  `game/`; rendering in `engine/rendering.py`; world in `world/`.
- **Save compatibility matters**: tile ids are positional — only append to the tile
  registry in `world/tile.py`. Persist by structured fields (names, records), never
  by parsing display strings. New save fields must be additive with sensible defaults
  for older saves (grandfather generously).
- Balance rule of thumb: every processed good should clear its ingredients' value by
  ≥ ~25%; deeper/rarer chains pay more.
