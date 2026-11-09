# Hearthdelve — Design Document

*A cozy farming & crafting life-sim with the soul of a surface roguelike. Grow, make, trade, and befriend a valley — wander into the wilds only when you choose to.*

**Status:** living document (v6) · **Engine:** Python 3.14 + `tcod` · **Render:** pure ASCII tile grid, keyboard-driven

> **Scope of this document.** It describes the game *as built*. The creed that
> governs new work — the north star, the save-compatibility rules, the balance
> rule of thumb — lives in `CLAUDE.md` and takes precedence. Numbers here are
> read from `engine/constants.py` and `data/content.py`; if they ever disagree,
> the code is right and this file is stale.

---

## 0. Changelog

- **v6** — brought in line with the built game. Corrected the world (1024×1024, four regions, a sea and the Westreach), the settlements (four villages + a camp, a hut and a dwarf town), the tool ladder, the tunables and the keymap (§13 had listed vi-keys, which are a deliberate *omission*). Documented the systems that had shipped undescribed: birth signs & attributes, karma, skills & weapon mastery, land ownership & tax, encumbrance, herbalism, jewellery & gems, community projects, the Hall of Wonders, world events, the request board & market cravings, Khazgrim and the Underriver. Rewrote the architecture map and the content appendix.
- **v5** — folded in locked choices: two villages from the start, minimal fishing, lean day-1 loadout. Added a content appendix.
- **v4** — cozy-first re-centering: farming + crafting as twin core, combat a minor side mechanic; villages & NPCs; multiple themed dungeons.
- **v3** — large procedural frontier; 4-season cycle. · **v2** — surface-first, danger by distance. · **v1** — initial pitch.

## 1. The pitch

You inherit a homestead on the frontier — a few tilled acres at the heart of **Hollowmere Vale**, a wide, half-wild valley. The heart of the game is **making a life**: till and plant across the seasons, raise animals, **craft** raw goods into things worth far more than their parts, cook, build out your homestead, and slowly get to know the folk of the valley's villages.

The Vale is alive and explorable — woods, fen, rocky hills, open plains, a southern sea — dotted with **dungeon mouths**, each themed to its ground. They're optional. You go in for what you can't grow: ore and gems for better tools, rare reagents, deep metal. Fighting is *one way* to get those things — never the point of the day.

**Cozy and roguelike share one map. The cozy is the main course.**

## 2. Tone & priority (read this first)

A **cozy game**: calm, productive, social, seasonal. In descending priority:

1. **Farming** — the daily heartbeat.
2. **Crafting** — the progression & economic engine; raw goods → valuable artisan goods.
3. **Village & NPCs** — the warmth; shops, gifts, friendships, festivals, favours.
4. **Exploration & gathering** — foraging, fishing, mining, discovering sites.
5. **Combat** — a *side* mechanic. It has grown real teeth since v4 (ADOM-style rolls, weapon mastery, elites, bosses, statuses), but it is still always avoidable and never a fail-the-day threat near home.

If a choice trades coziness for challenge, **coziness wins.**

## 3. Pillars

1. **Progression is efficiency, not permission.** Nothing is hard-locked behind gear, level or quest flags. A wooden pickaxe can chip at the deepest mithril vein — it's just slow, exhausting and wasteful. Better tools, skills, meals and jewellery make the same world *cheap*, not newly *allowed*. Prefer cost gradients (time, stamina, yield, risk) to walls.
2. **Make, don't just kill.** Progression = crops → crafted goods → upgraded tools & buildings, not a kill count.
3. **One world, no mode switch.** Same renderer, scheduler, player and inventory at the workbench or in a grotto.
4. **Optional danger, by distance.** Wilds and dungeons when you want them; homestead and villages always safe.
5. **Every wild thing has a home use.** Loot is reagents, seeds, ingredients — it feeds the farm and the workbench.
6. **Soft losses, persistent gains.** Faint → wake in your bed, lose loose loot and a little gold (never your remedies and potions); land, tools and relationships persist. **No permadeath, no game over, no win — you just live here.**
7. **The seasons are the clock.** Spring planting, summer growth, fall harvest, winter craft-and-cozy.
8. **Organic, not mechanical.** Spawns, regrowth, requests, market cravings and gifts drift on seeded randomness — never fixed spots or metronome cadences. The world should breathe, not tick.
9. **Data-driven content.** Crops, recipes, machines, monsters, items, NPCs are table entries in `data/content.py`.

## 4. Core loop

```
        ┌──────────────────── A DAY ────────────────────┐
 wake → farm chores → craft/cook → village / forage / fish / (optional) delve → ship goods → sleep
        └──────────── time passes · stamina drains ─────┘  crops grow · machines finish · world stirs
```

- **The day has two budgets: time and stamina.** Actions cost both, independently. For long work the clock, not stamina, is usually the real limit.
- **The ledger opens the day.** On waking, a ledger lists what the bin sold overnight, line by line, and what's ready around the homestead: finished machines, animals with produce, ripe crops, fruiting trees, and crops needing water. It only opens when there's news. The journal's Homestead page keeps last night's sale too.
- **Sleep** advances the day: crops grow, machines complete, animals produce, forage drifts, favours turn over, the calendar ticks.
- Machine crafting costs *time*, not stamina — load it and it works while you get on with the day. A few benches (anvil, gem wheel) are worked in person instead, and charge stamina there and then.

## 5. Farming

- **Plot lifecycle:** hoe → till, plant, water daily → a growth stage per watered day → harvest at maturity. Some crops **regrow** on a shorter clock; some are single-harvest.
- **Season-bound:** each crop lists its season and days-to-mature. Out of season it won't sprout; caught by a season change it withers.
- **Thirst, not instant death.** An unwatered crop goes thirsty and withers only after a dry spell — one day under clear sun, three under cloud. Rain and storms water for you; **rice floods its own paddy** and never needs watering.
- **Quality is 0–5 stars**, from the Farming skill, fertiliser, and **soil enrichment** — ground improves with every harvest and dose of fertiliser and slips when a crop is left to wither, so care compounds. Stars scale sell value 1.0× → 2.0×, and carry through into everything you make.
- **Sprinklers** water their neighbours each dawn; a **greenhouse** grows any crop in any season.
- **Hybrids.** Two related crops side by side on your land, both half-grown or more, may cross at dawn (the bees' work, seeded by the day). Harvest the crossed plant and you save the hybrid's seed. There are seven, most of them real crosses: Romanesco (cauliflower × kale) and Sugar Corn (corn × sugarcane) cross outdoors; Rutabaga, Kalette, Tritordeum, Pomato and Frostberry need a greenhouse, because their parents keep different seasons. Each is worth at least a quarter more than its better parent, and now and then breeds true and gives a seed back. Hybrids stay out of the main crop list, so worldgen, village fields, favours and the Herbarium are unchanged.
- **Orchard trees** from saplings bear in their season, refruiting every few days (jittered, never clockwork). 200-odd wild fruit trees already stand out in the Vale.
- **Hay:** grass around the homestead grows tall through the growing seasons; scythe it for cut grass, which dries into **straw** on a fair day — winter feed.
- **Animals** (chicken, duck, cow, goat, sheep, pig) are bought young, settled into a coop, barn or pen, and roam the yard. Pet them daily: happiness lifts the quality of their produce. Neglect never starves them, it just lets their spirits drift. Two well-kept adults under one roof may bring a **newborn**. An ill beast wants a Herbal Tonic. The **butcher's block** renders a grown animal into typed cuts — a somber trade.
- **Fishing:** cast at water for a catch that depends on **which water it is** — see §8.

## 6. Crafting

Raw goods are cheap; **crafted goods are the money and the upgrades.**

- **Bench crafting** (instant, costs materials): tools, sprinklers, fertiliser, fences, bombs, arrows, machines, satchels.
- **Machine crafting** (takes in-game time, runs unattended) — 31 machines, including:
  - **Furnace** — ore → bars. Every fuel has a **heat** (wood 1 · charcoal 2 · coal 3 · coke 4 · ember core 5); a metal needs a minimum heat to smelt at all, and hotter fuel smelts faster.
  - **Kiln** — wood → charcoal, coal → coke. **Anvil** — bars → weapons & armour of that metal (a skilled smith forges in a bonus affix). **Gem wheel** — rough gems → cut stones, and cracks geodes. **Jeweller's bench** — cut gem + bar → rings & amulets, or embeds a gem into gear or a tool.
  - **Preserves jar** (per-fruit jams, per-veg pickles, jellied eel) · **Keg** (per-fruit wines, mead, grain mash) · **Churn** (cheese, yogurt, butter) · **Smoker** (jerky, sausages, bacon, cured ham, smoked fish, caviar) · **Tanning rack** (hides → leather) · **Spinning wheel** → **Loom** (fibre → yarn → cloth → garments & furnishings) · **Quern / Windmill** (grain → flour, cane → sugar, salt) · **Oil press** · **Sawmill** · **Beehive** (yields more the more flowers bloom nearby).
  - **Apothecary** — the only place remedies are brewed, and where potions are distilled. **Oven** — double batches of baked goods, a touch finer. **Cellar** — ages wine, mead and cheese into something better.
- **Value flows from the ingredient.** A jam is worth its fruit; a wine its grape; a sashimi its fish; a plate of armour its metal. `content._enforce_recipe_margins()` derives every craftable's value from its inputs at import, iterating to a fixed point, so no crafted good is ever worth less than its parts + 25%. (Forging at the anvil is a deliberate exception — gear is for wearing, never for flipping. Garments from the loom and jewellery from the jeweller's bench are crafts like any other: a garment is worth at least its bolt of cloth + 25%, a ring or amulet its bar and cut stone + 25%.)
- **Cooking** is *learned*, not known: 8 starter recipes, the rest gathered around the Vale — a friend shares their favourite dish at 3 hearts, innkeepers sell house recipes, some come with practice, a filled favour sometimes has one folded in, and the Scriptorium lets you study one out.
- **Tool upgrades** at a blacksmith: **Wooden → Bronze → Iron → Steel → Adamantium → Mithril**. Each tier is −12% stamina and −10% time per use. All utility; nothing combat.

## 7. Time, seasons & weather

- **Calendar:** Spring / Summer / Fall / Winter, **28 days** each ⇒ 112-day year.
- **A day:** 06:00 → 02:00. Actions cost seconds; past midnight you're warned, and at 02:00 you drop where you stand.
- **Season character:** spring gentle & rainy · summer long and lively · fall the peak harvest · **winter** the cozy indoor season (three hardy crops outdoors, and ice-fishing).
- **Weather** (per dawn, season-weighted, deterministic from the seed): Clear · Cloudy · Rain · Storm · Fog · Snow. Rain waters crops; fog closes your sight right in; storms keep villagers indoors and rattle the animals.
- **Tomorrow is knowable.** The weather-wise (fishers, foragers, foresters, the dwarf elder) foretell it in folk lore, a weathervane points to it, and gnats rise before rain. Deterministic from `seed + day`, so the omens are true. The journal's **almanac** notes the forecast down once you've heard it that day, beside the season's calendar of festivals and birthdays and what's coming in the next two weeks.
- **Festivals** (6 a year, on fitting days, each scripting its own weather): the Spring Equinox · the Summer Solstice · the Harvest Fair · Hallows' Eve · the Winter Solstice · Yuletide. The village gathers in the square; stalls go up (a treat stand, one treat a guest, and a tombola, three spins a guest); the last festival of the year is fireworks night if you filled the order.

## 8. The world

**Generated once per seed, 1024×1024**, homestead at the centre, danger by distance. Four regions grow from seed points and meet at the farm, their borders ruffled by noise so they interlock organically:

```
      NW  deep wildwood ──────────── fen & bog  NE
             (grotto, camp, hut)   (barrow, crypt, Fenwick)
                      ╲  homestead  ╱
      SW  rocky hills ──────────── open plains  SE
        (mine, cavern, Cinderhope)   (Mossford)
                  southern sea (Saltmere, sea cave)
```

- A **river** meanders the whole map as a real barrier that roads must bridge. A **sea** floods the southern reach behind an irregular coast.
- **Roads** are a single network: a minimum spanning tree from the farm to each settlement, with spurs to each dungeon mouth, pathfound over terrain-aware costs so they hug gentle ground and wind through the hills. Signposts stand only where three genuine routes meet.
- **The Westreach** — a second, wilder overworld (320×320) beyond the map's western edge: ash slopes climbing to a live volcano, sulphur and nitre, ore-rich crags, and beasts that hunt on sight. No bed, no farming, no villages. Born the first time you cross, persistent thereafter.

### Dungeons

Eight mouths in the Vale, of six kinds; the Westreach adds tombs, a lava cavern and the dwarven mine. Each kind differs in **layout** (blobby caves · rectilinear halls · mine chambers on long tunnels), **palette**, **décor**, **spawn roster**, and what it's rich in (ore, gems, traps, pools, chests).

- Floors are **72×46 with FOV**, generated on demand and **re-rolled per in-game day** — but cached within the day, so stepping out and back returns the same already-looted floor. Depth is unbounded.
- Texture: hidden traps, rubble, chests, cave fungus, underground lakes, gold vaults on deeper floors, and the rare **Glimmerwood Hollow** — a glowing grove of wispwood and giant caps.
- Every **10th floor is a Deep Sanctum**: a guaranteed boss and a rich vault.
- **Khazgrim** — the dwarves' living town on floor 4 of the dwarfhold. Hand-shaped and world-seeded, so it never re-rolls: a pillared hall, an alehall, Thrunn's forge, and folk who remember a friend across saves. Floor 5 below it is the **Underriver**, a persistent ore-river you pan with a rod for ore and gems. The dwarves' **lift** in the west corridor rides, for a fare (15g a floor, a few minutes), to every fifth floor of the mine you've reached on foot, and back from a station beside the stairs on each. It saves the walk down and opens nothing new.

### Water

Which body of water you cast into decides the catch, derived from the world rather than stored: the coastline says what's salt, and the ground around a pool says whether it's peat or open water.

| Water | Catch | Character |
|---|---|---|
| **River** | seasonal freshwater | the doorstep trickle |
| **Still water** | pond fish — perch, rudd, bream, carp, zander, mirror carp | safe, close, easy |
| **The fen** | roach, tench, eel, red swamp crayfish, lamprey | a trek, and the miasma can make you ill |
| **The sea** | sardine, mackerel, sea bass, tuna (+ moonfish once the lighthouse stands) | the coast |
| **Cave pools** | cave bass, eel, blindfish, glowfish | pays best of all |

## 9. Villages & folk

**42 residents** across four villages and three smaller places. Each has a home and a work anchor, an hourly schedule (home ↔ work ↔ inn ↔ temple ↔ square, bent by weather, season and festivals, and kept loosely: each resident runs up to 45 minutes early or late, differently each day), and children who roam and chase each other about the square.

- **Mossford** (SE plains, 10) — the farming town: general store, carpenter, chapel, inn.
- **Cinderhope** (SW hills, 9) — the mining outpost: blacksmith, chapel, taproom, a trader.
- **Saltmere** (south coast, 7) — the fishing village: piers, boats, an inn.
- **Fenwick** (NE fen, 7) — the stilt-house hamlet: a herbalist, an eel-catcher, a trapper, a trader.
- **Thornwake Camp** (4) — woodcutters living rough round a fire in the NW wood. No shops, no roofs but canvas.
- **The Wildwood hut** (1) — Yew the forester, who speaks in rhyme.
- **Khazgrim** (4) — the dwarves, underground.

**Friendship** (0–10 hearts) rises by talking daily and, more, by **gifting**. Tastes match by *family*, so "loves jam" is satisfied by any jam. Depth unfolds as you grow closer: **heart blurbs** reveal backstory at 3 and 6 hearts, and **heart events** are one-time scripted scenes at 4, 7 or 8. Good friends give you things from their own in-character pool, teach you their favourite dish, and remember. Every villager has a **birthday** (drawn from the seed, one to a day, never on a festival): a kind gift that day counts three times over, they'll tell you it's their day, and the dawn names the birthdays of folk you know.

**Shops:** general store (seeds, saplings, livestock, soft goods) · blacksmith (fuel, bars, gear, tool upgrades) · carpenter (outbuildings, farmhouse fittings, and a **second room** for the farmhouse: 6,000g, planks, stone and iron, raised in two mornings on clear open ground north, east or west of the house, never over a road) · taverns (meals, house recipes, and they buy your artisan goods at a premium) · **rotating trader wagons** whose stock turns over on 3–6 day windows, carrying high-tier gear at 3–4× its worth — the non-crafter's road to endgame kit.

**The notice board** on each square carries **favours**: a villager needs so-many of a thing, paid over the odds with friendship and sometimes a recipe folded in. They drift on and expire on their own clocks, and only ever ask for things you could plausibly lay hands on. Separately the **market takes cravings** — for a few days one kind of goods sells dear at the shipping bin.

## 10. Community restoration projects

Each village dreams of one great work. You fund it in freeform instalments — gold and materials, any amount, at that village's notice board. Once funded, a site is staked near the square and raised over days into a standing landmark with a **lasting perk**. Nine of them; a village hosts several over the game's life, the next stepping up as one is finished.

Mossford's **Grange Hall** (festival produce contests), **Shrine of the Seasons** (a daily blessing at the altar) and **Hall of Wonders**; Cinderhope's **Deep Forge** (deep-metal stock, eight of each deep bar a week, cheaper upgrades, a public furnace and anvil) and **Scriptorium** (study out a recipe); Saltmere's **Lighthouse** (better sea fishing, and moonfish) and **Market Cross** (+10% shipped); Fenwick's **Causeway** (opens Willa's wagon, paves and lights the fen road) and **Bathhouse**.

Nothing is ever locked behind a project — perks make the world cheaper or richer, never newly permitted.

**The Hall of Wonders** is the flagship: present the first of each specimen to the curator for a cabinet of the Vale's wonders — 93 across five wings (Herbarium, Angler's Cabinet, Lapidary, Reliquary, Trophies). Each completed wing grants a lasting perk, latched so a later content addition can never revoke what you earned.

## 11. Character

- **Birth.** A new life opens with the midwives rolling your **sign** (one of nine, each a small passive boon) and your **eight attributes** (ADOM's own — St Le Wi Dx To Ch Ap Pe — honest 3d6 each, reroll at will). Centred on 10, so an average roll changes nothing; each is a small modifier on a system that already exists, never a gate. A very rare treat can raise one for good, to a ceiling of 18.
- **Ten skills** (Farming, Foraging, Mining, Fishing, Combat, Cooking, Smithing, Jewelcrafting, Gemcutting, Herbalism), 0–10, gaining from the matching work. Levels grant small, cozy bonuses and lift the quality of what you make.
- **Character level** 1–15 on its own track — every deed feeds it and it keeps growing after a skill has capped. Each level: +8 max HP, +12 max stamina.
- **Weapon mastery** per category (blade, axe, blunt, polearm, archery, unarmed), learned by doing: to-hit, damage, crit and parry. **Blunt weapons** (the War Mace, the Warhammer) cave armour in: their blows meet only two thirds of the target's Protection.
- **Karma**, −100 (villainous) to +100 (saintly), moved by kindness and cruelty. It scales how fast the world warms to you, and what you pay and are paid at a counter (±10%, soft — never a lock).
- **Encumbrance.** Carry weight comes from item kind, except armour, which weighs what it covers times its material's density: a full iron suit about 25, mithril about 11 (its lightness is its edge), adamantium 34, cloth next to nothing. Over capacity you tire faster and move slower; well over, much more so. Never a wall — always a cost gradient. Crafted satchels raise the ceiling; the home chest takes weight off your back entirely.
- **Buffs** from cooked dishes and brewed draughts (hearty, green thumb, keen forager, brisk, warded, stoneskin, swift, firebrand, clarity, envenomed, phantom).

## 12. Land

Every surface tile has an owner, resolved on demand and cached per map:

- **Village land** — building footprints, farmhouse fields and cottage gardens belong to a named resident, or to the village. You may *take* from it — theft and vandalism cost karma and the owner's regard, after one warning — but you may not build on it.
- **The homestead grant** — a radius of 20 around your spawn. Yours, and never taxed.
- **Your claims** — wilderness you improved by tilling, building or fencing in. Yours to use, but the crown levies **2g per tile per week**. Unpaid balances only cost a drip of karma; gold and land are never seized. Ground you stop working — the fence pulled up, the soil gone back to grass, the building gone — is struck off the claim at the next weekly assessment.
- **Wilderness** — everything else is ownerless.

## 13. Combat (deliberately light, but real)

ADOM's model: a d20 to-hit roll against the target's **DV**, where a natural 1 always misses and a natural 20 always hits, then damage minus its **PV** (Protection soaks at most ~⅔ of any blow, so armour is never total immunity and a weak weapon is never useless). Armour soaks a dart trap the same way.

- **Gear is composed, not enumerated:** a **base** (9 weapons, 10 armour slots, 2 bows) × a **material** (7 forge metals, plus leather, cloths, bow woods and beast scales) × optional **prefix/suffix affixes** × **embedded gems**. Stats and value derive from all of it; the item saves by its structured identity, so a piece can always be rebuilt.
- **Gems** carry one themed effect each, powering both worn jewellery (scaled by metal and star quality) and sockets in gear and tools.
- **Afflictions come on two clocks.** A **wound** — poison, bleed, burn — bites once per action, counts down in actions, and a night's rest sweats it out. A **disease** keeps a calendar: it does nothing turn to turn, but each dawn you wake short of health and with only three-quarters of a day's rest in you, and it counts down one day. Sleeping does *not* shake it off; it runs its course over 5–8 days (drifting, never a fixed week), or you physick it away with a charcoal tincture, a panacea, or a soak at the Fenwick bathhouse. Damage on either clock scales with the victim's max HP so it never fades to a rounding error, and an illness can never be lethal.
- The fen's miasma is the common way to catch one — a low per-step chance out in the wet marsh, warded off by a Warding Tea. Fenwick sits in that fen, and Fenwick is where the bathhouse gets built.
- **Monsters:** 15 kinds + 5 bosses, filtered by dungeon kind and depth, each scaled by the levels it stands *above* its intro floor. Behaviours: chase, erratic, charge, ranged (kites you), summon (raises the dead while it stands), and bosses that enrage below half health. Deeper floors roll **elite** variants — prefixed, brighter, tougher, worth more.
- **Ranged:** bows and a sling, with **tiered ammo** (plain wood → metal-tipped by ore → brimstone and venom tips). A shot spends your best plain or metal-tipped arrow first; the status tips wait until you ready them in the ammo slot (or until nothing else is left).
- **The Bomb** and the gunpowder **Blast Charge** harm monsters *and* shatter rock and ore — useful to a pacifist miner. Firecrackers are all noise, and scare crop-raiders off your land for days.
- **Surface wildlife** is peaceful (skittish or defensive); killing it costs karma but fills the larder and the tanning rack. The Westreach's beasts are **predators** that hunt on sight.
- **Faint** → carried to your bed, wake next dawn, lose the loose loot you carried below (ore, crops, goods — never your remedies, potions or attribute treats) and some gold (scaled by depth). No death screen.

## 14. Tunables

| Knob | Value |
|---|---|
| Start HP / stamina / gold | 50 / 270 / 0 |
| Day-1 loadout | 6 tools, seed pouch, a rusty iron sword, 15 parsnip seeds |
| Day length | 06:00 → 02:00 |
| Season / year | 28 days / 112 days |
| World size | 1024×1024 (Westreach 320×320, dungeon floor 72×46) |
| Till / water / plant / harvest | 3 · 2 · 2 · 1 stamina |
| Chop / mine | 6 stamina, 10 min · 8 stamina, 20 min |
| Tool tiers | Wooden → Bronze → Iron → Steel → Adamantium → Mithril (−12% stamina, −10% time each) |
| Quality | 0–5 stars, sell value 1.0× → 2.0× |
| Skills / character level | 10 levels (120 xp each) / 15 levels |
| Carry capacity | 50 base + 4/level + satchels + Strength |
| Land tax | 2g per claimed tile per week |
| Crafted-good margin floor | ingredients + 25% |
| Faint penalty | loose loot (not remedies, potions or treats) + 10% gold + 15g per floor |

## 15. Controls

Movement is **arrows** (4-way) and the **numeric keypad** (8-way, keypad-5 waits). **There are deliberately no vi-keys** — the keymap follows ADOM, and letters are reserved for commands.

```
arrows / keypad  move        . or KP5  wait        w  run (then a direction)
Space  use the active tool   g  grab / gather / interact     1-9,0  hotbar slot
>  <   descend / ascend      l  look        t  aim & throw or loose
i  pack   e  equipment       c  craft & cook          x  eat
b  ship at the bin           f  gift       Shift+C  talk / shop
s  sleep  p  site a building j  journal     r  relationships   v  character
m  world map     h / Shift+M  message history    ?  help & codex
Tab  filter or swap    Enter  confirm    Esc  cancel    q  quit    Shift+U  mute
```

**Tool targeting is directional** — tools act on the adjacent tile you face, always highlighted (green when the active tool can act there), which doubles as the facing indicator. Bumping an obstacle turns you to face it. "Where you stand" actions (grab, stairs, sleep) are non-directional. Bumping an animal pets it or collects its produce; bumping a creature attacks it; bumping an altar, lectern or bath uses it.

## 16. Technical architecture

```
hearthdelve/
  main.py         # tcod context, the thin main loop
  screens.py      # the screen stack: one class per mode (play, inventory, shop, aim, fishing…)
  engine/  constants · rendering · anim · effects · screens_render · codex · input · save · audio · font · ui
  world/   tile · gamemap · worldgen · worldlib · westgen · dungeon · dwarftown · crops
  entities/ player · items · monster · npc · animal · machine
  game/    state · commands · turns · actions · farming · crafting · combat · village ·
           husbandry · projects · requests · collection · delve · fishing · wildlife ·
           events · land · karma · skills · attrs · jewelry · encumbrance · inventory · quests
  data/    content.py     # every table: crops, recipes, machines, monsters, items, NPCs, projects
```

- **Screen stack, not a mode enum.** The loop only ever talks to the top: `tick` (per-frame real-time work), `render`, `on_raw` (raw events, for held keys and letter namespaces), `handle` (translated commands).
- **Layering:** `game/` never imports the renderer. Presentation reads from simulation, never the reverse.
- **One animation engine** (`engine/anim.py`). Everything that moves on screen is an effect drawn in one of a few ordered layers (ground shading and tints, ground blends, late ground, a veil over the creatures, the overlay). *Ongoing* effects — wind, water, weather, motes, embers, flyovers, the volcano — run every frame and decide whether they apply; *one-off* effects play when something happens: the game records a happening on the state (`state.happen(...)`, never saved) and the engine plays its effect for a moment — blows, misses, kills, shots in flight, bombs, wounds, level-ups, hearts won, gains hopping into your pack, work, fishing, the stairs, dawn and fainting. Ambient life fills the rest: fish rising where they bite, villagers chatting, festival bunting, shooting stars, drips and bats below. Every effect lives in `engine/effects.py`; every time-varying formula in the engine's timing helpers.
- **Turn model:** one `advance_time(seconds)`. Time passing steps monsters underground, residents/wildlife/animals above. Machines resolve lazily by completion time.
- **Save:** JSON. The world is **regenerated from its seed** on load, then the player's changes are overlaid (the tile grid base64-encoded, plus crops, soil, trees, machines, animals, wildlife, buildings, NPC friendships). Persistence is **structural** — gear stores base + material + affixes + gems, never a parsed display name — and record formats are append-only with guarded defaults, so new fields don't break old saves. Tile ids are positional: **only ever append** to the registry in `world/tile.py`.
- **Determinism:** everything drifting is seeded from `(seed, day)` and salted arithmetically — never `hash()`, which is salted per process.

## 17. Content at a glance

- **26 crops** across all four seasons (12 vegetables, 5 fruits, 4 grains, 3 flowers, 2 fibre) · **5 orchard trees** · **6 livestock species**
- **31 machines** · **97 recipes** (52 cooked dishes, 22 buildings, 12 bench items, 8 remedies, 2 carry upgrades, 1 chooser)
- **6 wild herbs** → remedies, potions and combat draughts · **4 wild mushroom species** + cave fungus and glowcaps
- **9 weapon bases** × 7 forge metals × affixes × 6 gems · **10 armour slots** including cloth and beast-scale lines
- **15 monsters + 5 bosses + 6 elite affixes** · **10 wildlife species** (5 common + the rare bear in the Vale, 4 in the Westreach)
- **42 NPCs** · **9 community projects** · **93 collection specimens** · **38 goals** (21 + 9 for year 2 + 8 for year 3) · **9 birth signs** · **6 festivals**

## 18. Screen layout & glyph legend

Target window **80×50**: a 58×44 world viewport, a 22-wide status panel, a bottom message log.

```
┌──────────────────────────────────────────────┬───────────────────────┐
│ ♣ ♣ ♣ , , , , . . . ~ ~ ~ . . . . . ♠ ♠       │  Spring 3  ☀ Clear    │
│ ♣ ♣ , , " " " . . . ~ ~ . . . ☖ . . ♠         │  08:40                │
│ , , " " " ‗ ‗ ‗ ‗ . . . F . . . . . .          │  ♥ HP    42/50        │
│ , , " " ‗ ≈ ‗ ‗ ‗ . . . . . @ . . . .          │  ✦ Stamina 71/270     │
│ , , " " ‗ ‗ ♬ ‗ ‗ . . . s . . . . . .          │  ⛁ Gold  340g         │
│ ♣ , , , . . . . . . . . . . . . . . ♣          │  ⚖ Load 22/54         │
│ ♣ ♣ , , . . . . . n . . . . . . ♣ ♣ ♣          │  ▸ Space: till        │
├──────────────────────────────────────────────┴───────────────────────┤
│ You water the parsnip sprout.                                          │
└────────────────────────────────────────────────────────────────────────┘
```

| Glyph | Meaning | | Glyph | Meaning |
|---|---|---|---|---|
| `@` | player | | `‗` `≡` | tilled soil (cool when watered) |
| `.` `,` `"` | grass / meadow / tall grass | | `.` `,` `"` → crop glyph | growth stages → ripe |
| `♣` `♠` | broadleaf / conifer | | `&` `*` | shrub / bush, flowers |
| `▓` | foliage (machete) | | `≈` `~` | sea / river |
| `;` `:` `‖` | marsh / moor / reeds | | `^` `░` | hill / scree |
| `☖` `#` `+` | building / wall / door | | `·` `=` | road & cobble / bridge |
| `*` `◊` | ore vein / gem vein | | `‡` `⊠` `☐` | signpost / post box / bin |
| `>` `<` | stairs down / up | | `■` `^` `%` | chest / trap / bones |
| `τ` `ψ` | mushroom / herb | | `î` `♨` `Ω` | lamp / campfire / hearth |
| `▦` | scaffold (building site) | | `≈` (orange) | lava |

- **Colour carries meaning:** terrain recolours with the season (autumn golds, winter snow); watered soil goes cool, parched soil warm; a machine pulses gold when its output is ready; ore twinkles; gems glitter. Out-of-FOV dungeon tiles render dim, like classic roguelikes.
- **Atmosphere:** day/night light with a warm dawn and dusk, directional sun shadows, fake ambient occlusion, cloud shadows, rain puddles and ripples, coastal foam, wind gusts across the grass, seasonal motes (petals, pollen, fireflies, leaves), birds and butterflies crossing, chimney smoke, and steam boiling off the Westreach caldera in the rain.

## 19. Opening & onboarding

- **Birth:** a title card — *"A letter from your grandfather: the old farm in Hollowmere Vale is yours now…"* — then the midwives roll your sign and attributes.
- **Soft, diegetic tutorial.** No walls of text: the log nudges, the panel previews what Space would do on the tile you face, and NPCs explain themselves. A few tiles come pre-tilled; you have 15 parsnip seeds.
- **No fail state.** Worst case you faint and wake at home, and the game frames it gently.
- **Goalless by design.** Goals mark progress and pay a little gold, a year at a time: 21 for the first year, then a harder set as years 2 and 3 begin. There is no ending. *"There's no rush. The Vale keeps its own time."*

## 20. Open questions

Design decisions are locked; what remains is tuning and judgement:

- **Gear pricing.** Buying a finished piece is currently cheaper than buying the bars to forge it, at every tier — a bought edge should be dearer than a crafted one.
- **Faucets vs sinks.** The one-off sinks amount to roughly an in-game year of a developed farm's income; past that, gold is unbounded with little to want. Wild fruit trees, truffle pigs and dungeon gold all need a decision about what gold is *for*.
