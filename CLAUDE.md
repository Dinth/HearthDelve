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
  gems) should pay generously even at low effort. And the ingredient carries through:
  a product's quality and value should scale with what went into it (a tuna sashimi
  worth far more than a minnow one, adamantium plate more than iron), not be a flat
  number — see the gear/jewellery/artisan factories for the model.
- **Crafting chains stay believable.** Recipes should mirror how the thing is really
  made — ore → bar → tool, milk → cheese, flour + egg → noodles, hide → leather →
  armour. Where the ingredients are fantasy, keep the transformation plausible
  in-world (a wraith's essence into a phantom draught, a drake's scale into scale
  armour); never an arbitrary "A + B → C" that wouldn't make sense.
- **Information over hand-holding.** Surface the world's state (journal tabs, panel
  hints, look-mode, codex) so the player can plan; never auto-play for them.
- **Keys follow ADOM.** The control scheme mirrors ADOM's keymap wherever possible —
  numpad/arrow movement, letter commands players of the genre already know. Don't
  invent a binding where an ADOM convention exists, and don't add vi-keys (yubn/hjkl):
  that's a deliberate choice. UI idioms follow ADOM too (paperdoll equipment,
  categorised letter-indexed inventory, weights shown).

## Practicalities

- Run: `./run.sh` (or `python play.py`). One-frame render check:
  `HEARTHDELVE_SMOKETEST=1 python -m hearthdelve`.
- Tests: `python -m unittest discover -s tests -v` (headless; CI runs them on every
  push and the binary build won't ship if they fail). New systems get tests in
  `tests/` — especially save round-trips and old-save grandfathering.
- Content is data-driven in `data/content.py` + `entities/items.py`; game logic in
  `game/`; rendering in `engine/rendering.py`; world in `world/`.
- **Save compatibility matters**: tile ids are positional — only append to the tile
  registry in `world/tile.py`. Persist by structured fields (names, records), never
  by parsing display strings. New save fields must be additive with sensible defaults
  for older saves (grandfather generously).
- Balance rule of thumb: every processed good should clear its ingredients' value by
  ≥ ~25%; deeper/rarer chains pay more.
