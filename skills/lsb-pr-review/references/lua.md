# Lua rules


### Control flow
- **Early returns** over nesting. Each guard gets its own `if ... then return end` with a comment
  `-- Early return: <reason>.`
- **One condition -> one line.** Do not wrap a single condition across lines.
- Don't `not` two conditions at once; write it plainly.
- Don't check `== nil` / `~= nil`; use `if mob then` / `if not mob then`.
- Quest/local vars can never be nil - unset means `0`. Don't nil-check them.
- Nil-default patterns rely on short-circuit order: `local v = input and input >= 0 or 0`, not
  `input >= 0 and input or 0` (which throws on nil).
- `0` and `1` are both truthy in Lua. Settings must be checked explicitly (`== 1` / `== true`) and
  the setting's declared type and comment must agree.
- Prefer `hasStatusEffect()` over `getStatusEffect()` when you only need presence.
- You do not need to check an effect exists before deleting it - delete it directly.
- Don't re-fetch an entity/value you already have in scope. If something is fetched twice or more,
  store it in a local (`local skillId = skill:getID()`, `local zoneId = player:getZoneID()`).
- Conversely: don't create a local for a value used exactly once - use it inline.
- `GetMobByID`/`GetNPCByID` can return nil - assign, check, then use, or LLS will complain.
- `onMobFight` / `onMobRoam` run every tick. Keep them minimal; move what you can to
  `onMobSpawn`, `onMobEngage`, `onMobDisengage`, `onMobWeaponSkillUse`.
- Prefer the entity functions (`entity.onMobFight`) over `addListener('COMBAT_TICK', ...)`.
  If a listener really is needed, register it in `onMobInitialize` or remove it in `onMobDespawn`,
  and give it a specific name (not `ANY`). Inside a listener use the passed `mobArg`, never the
  captured outer `mob`.
- `onMobDeath` runs once per entity in the enmity list - guard with
  `if optParams.isKiller or optParams.noKiller then`. `noKiller` is the DoT-kill case.
- `player` in `onMobDeath` can be nil - check it before `player:addTitle(...)`.
- `GetSystemTime()`, not `os.time()`.

### Functions and abstraction
- **No one-line functions.** Abstracting a single check only costs the reader time. Inline it.
- No function used in exactly one place - put the logic where it belongs.
- No functions defined inside functions.
- Functions not used outside the file must be `local function`.
- Don't daisy-chain functions or add a wrapper "patch" around a global - fix the global.
- Avoid functions returning two values, and functions returning a converted value where a factor
  would do. If you need "did a block happen", return that, don't infer it from a changed number.
- Don't drop unused function parameters from a signature.
- Keep parameters non-optional rather than 2-or-3-arg variants; people copy the worst example.
- **No naked bool flags** in signatures or parameter lists. Use an enum with true/false values, or a
  named-field table, rather than a positional list of naked booleans.

### Data
- **Tables over if/elseif chains**, always. If a table already exists in the file, extend it rather
  than adding a parallel chain. Define tables at file scope, not inside the function.
- Table entries that act as constants should be treated as immutable enums - keep the enum table and
  the mutable current value separate.
- **Use enums, never magic numbers**: `xi.zone.*`, `xi.item.*`, `xi.effect.*`, `xi.mobSkill.*`,
  `xi.magic.spell.*`, `xi.element.*`, `xi.mod.*`, `xi.title.*`, `xi.anim.*`, `xi.inventoryLocation.*`.
  Index element tables by `xi.element.X`, not `1..8`. Loops over contiguous effects can run
  `for effect = xi.effect.STR_DOWN, xi.effect.CHR_DOWN do`.
- Enum names use the long DB names (`LUMP_OF_TAMA_HAGANE`), `xi.camelCase` namespaces
  (`xi.chocoboRacing`, `xi.moonCycle`, `xi.macroTest` - no underscores).
- Duplicate mobskill names get a numeric suffix (`DOOM_1`, `GREAT_WHIRLWIND_1`); trust versions get
  `_TRUST`; mobskill naming is `MOBSKILL_NAME_USE_CASE` (`DAEDALUS_WING_COP_PRISHE`).
- `mob_skill`/`mob_pools` enums are ordered by ID. Blank lines mark *gaps* in the ID sequence -
  never a blank line between consecutive IDs, always one where IDs skip.
- `IDs.lua` mob/npc/text entries: alphabetical order. Long runs of sequential text IDs should use
  `ID.text.BASE + n` instead of being spelled out.
- **`IDs.lua` text comments must be byte-exact copies of the client string**, wildcards included
  (`%`, not `<ki>`). The client update tooling matches on these comments; a wrong one silently bakes
  in an ID shift. Don't put the speaker's name in the comment - put it in the enum name.
- Loot/drop weights are base-10000 within a group, and must sum to the base. Table entries are
  `{ itemId = ..., weight = ... }` in that order; drop the redundant `-- Item Name` comments.
- `math.random()` always takes an explicit min and max: `math.random(1, 100) <= chance`.
  Bare `math.random()` is being retired.
- `utils.clamp(value, min, max)` instead of hand-rolled min/max chains - it also documents the
  intended range and stops negatives. `utils.randomEntry` / `utils.randomEntryIdx` for random picks.
- Local-var key names should live in a `local vars = { X = 'x' }` table so they can't be typo'd.
- `string.format` / `fmt`, not `..` chains.
- Prefer `set` over `add`/`del` for mods on spawn (add accumulates across spawns).
- Attach modifiers to the **effect** (`effect:addMod(...)`), which removes the need for
  `onEffectLose` cleanup entirely.
- Immunities and resistance ranks never change -> `onMobInitialize`. Damage multipliers, double/
  triple attack, animationSub resets -> `onMobSpawn`.
- Resistance ranks are per-mob and belong in the **mob script**, not in shared SQL rows.
- `xi.mod.*_MEVA` is for status-effect resistance; `xi.mod.*_RES` is only for the job-trait style
  "Resist!" message. Don't mix them up.
- Mob section order in a script: `onMobInitialize`, `onMobSpawn`, `onMobRoam`, `onMobEngage`,
  `onMobFight`, `onMobDisengage`, then death/despawn.
- In NPC/quest files, `onTrade` is defined before `onTrigger`. `onEventFinish` handlers go in
  numerical event-ID order.
- Remove empty `onMobDeath`/`onMobSpawn` functions and files with no logic (except doors, which
  need a default action set first) - they only bloat the Lua memory footprint.
- Remove all `print`/`printf` debug output.

### Quests / interaction framework
- `quest:event(id)` for filler/optional events with no `onEventFinish`; `quest:progressEvent(id)`
  only when the event actually progresses the quest. Priority cycling is automatic for equal
  priority.
- `:replaceDefault()` only where the event genuinely replaces the zone default; otherwise move it to
  the zone `DefaultActions.lua`.
- Every quest section must check quest available/accepted/completed status, even for quests that
  never show in the log.
- Char/quest var names are case-sensitive all the way into the DB - the convention is `'Prog'`.
- Any currency spend must first check the player has it. Any item grant must check free slots -
  before playing the cutscene. Message order must match the capture.
- Trades that consume items use `npcUtil.tradeHasExactly()`; trades that only need an item present
  use `trade:getItemQty(...) > 0`. Trade completion (`player:confirmTrade()` /
  `tradeComplete()`) happens in `onEventFinish`.
- Prefer positions (`!pos`) or `GetFirstID()`/`GetTableOfIDs()` over raw entity IDs - IDs shift on
  every retail update, and raw-ID modules break silently.

### Comments and naming
- **Verbose names.** `now` -> `currentTime`, `hasUsed` -> `hasUsedPerfectDodge`, `q` -> `questObject`,
  `lowSkill` -> `isBelow50HPP`, `t` -> `paramTable`. Code is read far more than it is written.
- `item` -> `itemId`, `zone` -> `zoneId` when it holds an ID; `zoneId` implies *current* zone, so a
  destination is `destinationZoneId`.
- Comments go **above** the `if`/`else` they describe, never inside the block, never below.
- `-- ` with a space for normal comments; `---` is reserved for LLS annotations.
- A comment that restates the line under it (`-- Set TP to a specific value` above `setTP(1500)`)
  is noise - delete it. Comment the non-obvious: why a timer exists, why a value was guessed, what
  an edge case is, what the capture showed.
- No references to line numbers, to "current LSB", to prior implementations (git history covers
  that), or to downstream projects and their issue trackers.
- Mob/NM script headers should carry the `!pos` and a `!additem`/`!addquest`/`!exec` line so the
  next person can test it in one paste.
- `TODO:` for anything unresolved - but a PR that is only a pile of new TODOs isn't worth merging.

## Style / formatting


- **Align `=` in tables and consecutive assignments**, values lined up so numbers read down the
  column. Match the snippet the reviewer pastes exactly; don't let a local formatter re-flow it.
  Don't take it to absurd widths.
- Long tables get **one entry per line**, indented.
- **No unneeded parentheses.** `skill / 10 + skill * maneuvers / 20`, not
  `(skill / 10) + ((skill * maneuvers) / 20)`.
- No `.0` float literals - this isn't C++.
- `* 0.2` or `/ 5`, never `* .2`.
- `math.floor()` any value that must be an integer, and floor sub-terms separately when retail does.
- Table style:
  ```lua
  local tableName =
  {
      -- entries
  }
  ```
- Trailing comma on the last table entry. Newline at end of file. No stray blank lines, no
  whitespace padding, no double indentation.
- New globals must be registered in `.vscode/settings.json` and `tools/ci/sanity_checks/lua.sh`.
