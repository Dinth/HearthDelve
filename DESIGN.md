# Hearthdelve — Design Document

*A cozy farming & crafting life-sim with the soul of a surface roguelike. Grow, make, trade, and befriend a valley — wander into the wilds only when you choose to.*

**Status:** draft for review (v5) · **Engine:** Python 3.14 + `tcod` 21.2.1 · **Render:** pure ASCII tile grid, keyboard-driven

---

## 0. Changelog

- **v5** — folded in locked choices: **two villages from the start** (§9), **minimal fishing in the slice** (§5/§10), **lean classic day-1 loadout** (§14). Added a **Content appendix** (§18): the valley, both villages & their residents, seasonal crops, dungeon roster, monsters, starter recipes. Debug fast-season flag confirmed.
- **v4** — cozy-first re-centering: farming + crafting as twin core, combat a minor side mechanic; villages & NPCs added; single mine → multiple themed dungeons; no ultimate goal.
- **v3** — large procedural frontier; 4-season cycle; tunables. · **v2** — surface-first, danger by distance. · **v1** — initial pitch.

## 1. The pitch

You inherit a homestead on the frontier — a few tilled acres at the edge of **Hollowmere Vale**, a wide, half-wild valley. The heart of the game is **making a life**: till and plant across the seasons, raise crops, **craft** them into goods worth far more than their parts, cook, build out your homestead, and trade with the **two villages** down the road whose people you slowly get to know.

The Vale around you is alive and explorable — meadows, woods, riverlands, a fog-moor, old ruins — dotted with **small dungeons**, each themed to its biome. They're optional. You go in for what you can't grow: ore and gems for better tools, rare seeds, mushrooms, monster-drop crafting reagents. Fighting is *one way* to get those things — never the point of the day.

**Cozy and roguelike share one map. The cozy is the main course.**

## 2. Tone & priority (read this first)

A **cozy game**: calm, productive, social, seasonal. In descending priority:

1. **Farming** — the daily heartbeat.
2. **Crafting** — the progression & economic engine; raw goods → valuable artisan goods.
3. **Village & NPCs** — the warmth; shops, gifts, friendships, festivals.
4. **Exploration & gathering** — foraging, fishing, mining, discovering dungeon sites.
5. **Combat** — a *side* mechanic, low-stakes by design, gating some crafting materials. Always avoidable; never a fail-the-day threat near home.

If a choice trades coziness for challenge, **coziness wins.**

## 3. Pillars

1. **Make, don't just kill.** Progression = crops → crafted goods → upgraded tools/buildings, not a kill count.
2. **One world, no mode switch.** Same renderer, scheduler, player, inventory at the workbench or in a grotto.
3. **Optional danger, by distance.** Wilds & dungeons when you want them; homestead and villages always safe.
4. **Every wild thing has a home use.** Loot is reagents, seeds, ingredients — it feeds the farm and the workbench.
5. **Soft losses, persistent gains.** Faint in a dungeon → wake home, lose loose loot + a little gold; land/tools/relationships persist. **No permadeath, no game over, no win — you just live here.**
6. **The seasons are the clock.** Spring planting, summer growth, fall harvest, winter craft-and-cozy — rhythm for an open sandbox.
7. **Data-driven content.** Crops, recipes, biomes, monsters, items, NPCs, abilities are table entries.

## 4. Core loop

```
        ┌──────────────────── A DAY ────────────────────┐
 wake → farm chores → craft/cook → village / forage / fish / (optional) delve → ship goods → sleep
        └──────────── energy drains · time passes ───────┘  crops grow · machines finish · world stirs
```

- **Time** advances per action; the day ends when you sleep (or faint).
- **Energy** is the daily budget for physical actions (till, chop, mine, fight). Machine crafting is *time*, not energy — load it and it works while you do other things.
- **Sleep** advances the day: crops grow, machines complete, shops/forage restock, wilds re-stir, calendar ticks, NPC schedules reset.

## 5. Farming  *(main mechanic — Stardew/Coral Island model)*

- **Plot lifecycle:** hoe→till, plant seed, water daily → a growth stage per watered day → harvest at maturity. Some crops **regrow**; some are single-harvest.
- **Season-bound:** each crop lists season(s) + days-to-mature; out of season it won't sprout; caught by a season change it withers at the new season's dawn (one grace night).
- **Quality tiers** (normal/silver/gold) from soil care, fertilizer, sprinklers → higher price & better crafted goods.
- **Watering** by hand early; **sprinklers** (crafted from bars) automate it later — the key QoL unlock freeing days for crafting/exploring.
- **Fertilizer & soil** crafted from forage/compost.
- **Fishing** (light, in slice): cast at water tiles for fish that feed cooking/crafting; deeper catches in the flooded dungeon.
- **Animals & orchards** (post-slice): coops/barns/trees producing craft inputs.

## 6. Crafting  *(co-main mechanic — the economic engine)*

Raw goods are cheap; **crafted goods are the money and the upgrades.**

- **Bench crafting** (instant, costs materials): tools, sprinklers, fertilizer, fences, paths, scarecrow, bombs, fishing rod, machines.
- **Machine crafting** (takes time, runs unattended):
  - **Furnace:** ore + coal → metal **bars** (tool upgrades & machines).
  - **Preserves Jar:** crop → pickle/jam (much higher value).
  - **Keg:** fruit/crop → juice/wine (highest value, slowest).
  - **Loom / Mill / Dehydrator** (later).
- **Value ladder:** `raw crop < cooked dish < artisan good`. Selling raw is the trickle; **processing is the river.**
- **Cooking** (kitchen): recipes → dishes that restore energy/HP and grant temporary buffs.
- **Recipe unlocks:** start with a few; more from **NPC friendship**, shops, foraged blueprints, seasonal events.
- **Tool upgrades:** bars + gold at the blacksmith upgrade hoe/can/axe/pickaxe (bigger area, less energy) — the main power curve, all utility, not combat.

## 7. Time, seasons & weather

- **Calendar:** Spring / Summer / Fall / Winter — **28 days** each ⇒ 112-day year. *(Debug "fast season" flag, e.g. 4-day, for testing.)*
- **A day:** 06:00 → ~02:00; actions cost minutes; sleep resets to 06:00 and advances the date.
- **Season character:** Spring gentle & rainy (free watering) · Summer long days, best forage, livelier wilds · Fall peak harvest & festivals · **Winter no outdoor crops** — the cozy indoor season: craft, cook, ice-fish, delve, deepen friendships.
- **Weather** (per dawn, season-weighted): clear / rain (auto-waters) / fog (shorter sight) / storm / snow — mostly flavor & farming convenience.
- **Festivals** mark the calendar without imposing a goal.

## 8. The world & its dungeons  *(ADOM/ToME "world of sites")*

**Large procedural frontier, generated once per save**, homestead at center, danger by distance (T1 Homestead → T2 Edge → T3 Wilds). Both **villages** sit in T1/T2. Scattered across biomes are **several small, themed dungeons** — not one big hole.

```
   T3 WILDS ── old-forest grove · fog-moor barrow · ruined keep
   T2 EDGE  ── woodland grotto · flooded hollow · the old mine · Cinderhope village
   T1 HOME  ── homestead · Mossford village
```

- Each dungeon is **2–4 floors**, procedurally generated (rooms + corridors), with **FOV**.
- **Themed loot tied to crafting** (see §18 roster).
- **Low-stakes combat:** few, slow, telegraphed monsters; sneak/retreat/mine-around viable. Faint → eject home.
- **Re-rolls per in-game day** (stable within a day, fresh after sleep); depth/danger scales with the biome's wildness tier. You can step out and return to the same floor the same day — rewards a planned delve.
- **Worldgen:** wildness field (distance + noise) → biome flood-fill → carve homestead + two village sites → rivers/ore/forage → dungeon entrances per biome → bake passability/FOV grids (numpy).

## 9. Villages & NPCs  *(two villages — in scope)*

- **Mossford** *(T1, down the road)* — the friendly farming hamlet. Warm, welcoming, everyday hub: **General Store**, **Carpenter**, the river path. Where early days are spent.
- **Cinderhope** *(T2, by the old mine)* — a rugged crafter/miner outpost. **Blacksmith** (tool upgrades, bars), tinker. A reason to travel out, and the gateway to ore.
- **Shops** rotate stock by season; the General Store also **buys your goods** (a faster sell than the shipping bin, slightly lower price).
- **NPCs:** residents with simple **daily schedules** (home ↔ work ↔ gather by time), short **dialogue**, and **friendship hearts** raised by talking and **gift-giving** (each has liked/loved/disliked items — your crops & crafts are the currency of friendship). Friendship unlocks recipes, discounts, warmth.
- **Festivals:** a couple of seasonal gatherings (spring fair, fall harvest feast).
- **Slice scope:** stationary-or-scheduled NPCs, menu dialogue, gifting, friendship meter, shops. No romance/marriage/quest-trees yet (clean later additions).

## 10. Systems summary (MVP → later)

**MVP (v0.1 slice):** scrolling ASCII renderer + camera + HUD/log · 8-dir movement & collision across the procedural multi-biome world · **farming** (till/plant/water/grow/harvest, quality) + **light fishing** · **crafting** (bench + furnace/jar/keg + cooking) · **season & weather clock** · inventory + tools + hotbar · **two villages** (general store, blacksmith, carpenter, ~6 NPCs, gifting, friendship) · economy (shipping bin + shops) · **wilds + 2 small dungeons** (FOV, ~3 gentle monsters, bump + 1 ability, forage/ore/fish nodes) · save/load JSON.

**Later:** festivals, romance/quests, more NPCs · animals & orchards · more machines (loom/mill) & buildings · sprinkler/automation tiers · the remaining dungeons, deeper floors, more biomes · fishing depth · optional audio.

## 11. Combat (deliberately light)

- Bump-attack on simple stats (HP/ATK/DEF/SPD). **One** stamina ability in the slice: the **Bomb** — a thrown explosive that hurts monsters *and* breaks rock/ore in a small area, so it's useful even to a pacifist miner. Craftable from dungeon materials. More abilities later — all optional.
- Monsters **sparse, slow, avoidable**; AI = wander → chase-in-FOV → bump; many flee. **None in T1** (home/villages). Combat exists to gate *some* dungeon reagents, nothing more.
- Faint → eject home next dawn, drop loose loot + ~10% gold. No death screen.

## 12. Technical architecture

```
hearthdelve/
  main.py            # tcod context, main loop, top-level state switch
  engine/  constants.py · rendering.py · input.py · save.py
  world/   tile.py · worldgen.py · biome.py · chunk.py · dungeon.py · crops.py
  entities/ player.py · monster.py · npc.py · items.py
  game/    state.py · actions.py · economy.py · crafting.py · turns.py · abilities.py
  data/    content.py   # tables: crops, recipes, machines, biomes, monsters, items, npcs, abilities
```

- **No hard mode switch;** overlays (`PLAY`, `INVENTORY`, `CRAFT`, `SHOP`, `DIALOGUE`, `SLEEP`, `MENU`) over one world.
- **Turn model:** single scheduler; loose near home, strict turn-based only when a monster is in FOV. One `advance_time(minutes)`; machines resolved by completion-time on tick/sleep.
- **tcod:** `context`, `console`, `event`, `map`/`path` (FOV + pathfinding), numpy grids, scrolling camera (world > screen). Pure ASCII/CP437, colored by biome/tile; swappable for tiles later.

## 13. Controls (draft)

`arrows`/`hjkl`(+`yubn` diagonals) move · `.` wait · `1-5` tool/hotbar · `Space` use tool on facing tile · `g` grab/forage · `t` talk · `f` gift · `c` craft/cook · `a` ability · `>`/`<` dungeon in/out · `i` inventory · `b` buy/sell · `s` sleep · `Esc` menu.

## 14. Tunables (first pass)

| Knob | Value |
|---|---|
| Start energy / HP / stamina | 100 / 50 / 20 |
| **Day-1 loadout** | hoe, watering can, axe, pickaxe, basic sword + 15 parsnip seeds + 0 gold (**lean & classic**) |
| Till/plant/water | 6/4/4 energy · ~10 min |
| Chop / mine / bump | 8 / 10 / 3 energy |
| Furnace / Jar / Keg time | ~5h / ~part-day / ~1–3 days |
| Season length / year | 28 days / 112 days (debug flag → 4) |
| Pass-out gold loss | 10% |
| World size | 200×200 tiles |
| Value ladder | raw 1× · cooked ~2× · artisan ~3–4× |

## 15. Milestones  *(cozy-first ordering)*

- **M1 — Walking skeleton:** window; player walks a scrolling procedural multi-biome world; HUD (date/time/energy).
- **M2 — Hearth & seasons:** full farming loop + light fishing + season/weather clock + inventory/tools.
- **M3 — Make & trade:** crafting (bench + machines + cooking), shipping bin, **two villages** with shops, NPCs, gifting & friendship.
- **M4 — The wilds:** FOV, **2 small themed dungeons**, gentle combat + 1 ability, forage/ore nodes, eject-on-faint, save/load. *(playable cozy vertical slice)*

## 16. Decisions locked

- Visuals: pure ASCII (swappable). · Tone: **cozy-first, combat a minor side mechanic.** · Goal: **none — open-ended life-sim.**
- World: one contiguous procedural frontier (~200×200), danger by distance. · Dungeons: **multiple small themed sites** (2–4 floors), 2 in slice.
- Villages: **two** (Mossford, Cinderhope) with NPCs, shops, gifting, friendship, festivals.
- Seasons: full 4-season, **28-day** cadence (+debug fast flag). · Fishing: **light, in slice.** · Combat: light bump + the **Bomb** ability.
- Loadout: **lean & classic** (tools + starter seeds, no gold). · Death: eject home, drop loose loot + ~10% gold.
- Dungeons re-roll **per in-game day** (stable within a day).
- **Tool targeting: directional** — tools act on the adjacent tile you face (Stardew-style), so trees/rock/walls stay impassable for cozy texture and dungeon/combat tactics. The faced tile is always **highlighted** (green when the active tool can act there) — this is the facing indicator. Bumping an obstacle turns you to face it without moving. "Where you stand" actions (grab, stairs, sleep) remain non-directional.

## 17. Open questions

*All design decisions are locked.* The Content appendix (§18) is illustrative starter data — names/numbers are placeholders to tune during build, not decisions. Remaining choices are implementation details to settle as we build (e.g. exact growth-day counts, monster stats, gift-taste tables).

## 18. Content appendix (starter data — tune during build)

**The valley:** Hollowmere Vale. Homestead at center; river running NE→SW; Mossford near home; Cinderhope out by the mine.

**Villages & residents**
- *Mossford:* **Marda** (General Store — warm, gossipy; loves jams/flowers), **Tomas** (Carpenter — building upgrades; likes wood/stone), **Old Pell** (river fisher/forager — likes fish/bait), **Wrenna** (herbalist & cook — teaches recipes; loves foraged herbs/mushrooms).
- *Cinderhope:* **Bron** (Blacksmith — tool upgrades, sells bars/coal; likes ore/gems), **Sable** (tinker/wandering trader — rotating rare stock; likes relics).

**Seasonal crops (sample)**
- *Spring:* parsnip, potato, cauliflower, strawberry *(regrows)*.
- *Summer:* tomato *(regrows)*, corn, hot pepper *(regrows)*, melon, blueberry.
- *Fall:* pumpkin, eggplant *(regrows)*, cranberry, wheat, grape.
- *Winter:* none outdoors; forage winter-root & crystal-fruit; greenhouse later.

**Dungeon roster** *(★ = built in slice)*
- ★ **The Old Mine** (Cinderhope, T2) — ore, coal, gems → bars, tools, machines.
- ★ **Woodland Grotto** (woods, T2) — rare seeds, sap, mushrooms.
- **Flooded Hollow** (river, T2/T3) — fish, pearls, clay (richer fishing).
- **Moor Barrow / Ruined Keep** (T3) — relic reagents, gold, rarer drops.

**Monster roster** *(★ = slice; gentle)*
- ★ **Cave Slime** (slow, weak), ★ **Bat** (erratic, flees), ★ **Boar** (charges, then calms), · Bandit-Scavenger (T2), Moor-Wight (T3).

**Starter recipes (known day 1 or early):** Furnace, Preserves Jar, Scarecrow, basic Fertilizer · Cooked: **Veggie Stew** (restore energy), **Berry Jam** (sell), **Fish Chowder** (energy+small HP). Later via friendship/shops: Keg, Sprinkler (needs bars), Loom, more dishes.

**Tools:** Hoe · Watering Can · Axe · Pickaxe · Sword (basic) · Fishing Rod. Upgrade tiers **Copper → Iron → Gold** (bars + gold at Bron's).

## 19. Screen layout & glyph legend

Target window ~**80×50** cells: a large play viewport, a right-side status panel, and a bottom message log.

```
┌──────────────────────────────────────────────┬───────────────────────┐
│ ♣ ♣ ♣ , , , , . . . ~ ~ ~ . . . . . ♠ ♠       │  Spring 3  ☀ Clear    │
│ ♣ ♣ , , " " " . . . ~ ~ . . . ☖ . . ♠         │  08:40                │
│ , , " " " " " . . . . . . . . . . . .          │                       │
│ , , " " " ‗ ‗ ‗ ‗ . . . F . . . . . .          │  ♥ HP    42/50        │
│ , , " " ‗ ≈ ‗ ‗ ‗ . . . . . @ . . . .          │  ⚡ Energy 71/100      │
│ , , " " ‗ ‗ ♬ ‗ ‗ . . . s . . . . . .          │  ✦ Stamina 12/20      │
│ , , " " ‗ ‗ ‗ ‗ ‗ . . . . . . . o . .          │  ⛁ Gold  340g         │
│ ♣ , , , . . . . . . . . . . . . . . ♣          │                       │
│ ♣ ♣ , , . . . . . n . . . . . . ♣ ♣ ♣          │  Tool ▸ [2] Can       │
│ . . . . . . . . . . . . . . . . . . .          │  1 Hoe  2 Can  3 Axe  │
│ . . . . . . . . . . . . . . . . . . .          │  4 Pick 5 Sword       │
│ . . . . . . . . . . . . . . . . . . .          │  Bombs ×2             │
├──────────────────────────────────────────────┴───────────────────────┤
│ You water the parsnip sprout.                                          │
│ Marda: "Lovely morning for it!"                                        │
│ A boar snuffles in the brush to the east.                              │
└────────────────────────────────────────────────────────────────────────┘
```

**Glyph legend** (colored by biome/state; CP437/Unicode):

| Glyph | Meaning | | Glyph | Meaning |
|---|---|---|---|---|
| `@` | player | | `‗` | tilled soil (dark when watered) |
| `.` | grass / floor | | `♬`/`♠` | crop by growth stage → ripe |
| `,` `"` | meadow / tall grass | | `F` | forage node (herb/berry) |
| `♣` `♠` | tree / bush | | `≈` `~` | water (fishable) / river |
| `☖` | building / house | | `*` | ore vein · `◊` gem |
| `+` | door · `▒` wall | | `>` `<` | dungeon down / up |
| `s` `b` `o` | slime · bat · boar | | `n` | NPC · `☼` machine working |

- **Color carries meaning:** biome tints the base terrain; watered soil darkens; ripe crops brighten; monsters are warm-hued; the player is always bright white. Out-of-FOV dungeon tiles render dim (explored-but-unseen), like classic roguelikes.
- **Modal overlays** (inventory, craft, shop, dialogue) draw a centered panel over the play view; the world pauses.

## 20. Opening & onboarding (first 10 minutes)

- **Arrival:** a short title card — *"A letter from your grandfather: the old farm in Hollowmere Vale is yours now…"* — then you wake in the farmhouse on **Spring 1**, morning.
- **Soft, diegetic tutorial** (no walls of text — NPCs and the message log nudge):
  1. Step outside; a few starter tiles are already tilled. The log hints: *"Press 2 for the watering can, Space to use it."* Plant your 15 parsnip seeds.
  2. Marda walks up from Mossford, introduces the **General Store** and the **shipping bin** ("leave goods in the bin by night, gold by morning").
  3. The day's energy naturally runs down; the bed prompts **sleep** → first season tick, parsnips advance.
  4. Over the first few days, hints surface crafting (a furnace blueprint known from day 1), Cinderhope & Bron (tool upgrades), and the **dungeon entrances** as optional discoveries — never required.
- **No fail state in the opening.** Worst case you faint and wake home; the game frames it gently.
- **Goalless by design:** the closing onboarding line sets the tone — *"There's no rush. The Vale keeps its own time."*
