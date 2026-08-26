---
name: lsb-tests
license: MIT
description: Write and run tests for LandSandBoat. Use when writing a new xi_test case, adding a failing test before a bug fix, running xi_test or the Lua test suite, filtering tests, diagnosing a flaking test, or answering "how do I test this" for LSB. Covers the Lua harness (describe/it, lifecycle, spawnPlayer, ticks, doubles, assertions), the C++ Catch2 tests, the real flags, and the flake catalog. Not for compiling (see lsb-build) or reviewing a test diff (see lsb-pr-review references/tests.md).
---

# LSB tests

`xi_test` is one binary that embeds a full `xi_map` + `xi_world` server in-process and runs
two test bodies back to back:

1. **C++ unit tests** (Catch2), for pure core logic. They run FIRST, at startup.
2. **Lua tests**, for gameplay behaviour, driven through client-emulation helpers. They run
   only if the C++ tests all pass.

Both need a working database with tables imported, same as a live `xi_map`.

The in-repo wiki page `docs/wiki/Testing.md` is the authoritative, always-current reference for
the Lua harness API (every helper namespace, every lifecycle hook, every assertion). This skill
does NOT restate it. This skill carries what a code read does not give you: which flags are real,
how to actually invoke the thing, and WHY tests flake and what to do about it.

## When to use which reference

Sections below cover the everyday path. For depth, read the reference file on demand:

| You are | Read |
|---|---|
| running the suite, filtering, reading output, using tags/`--retry` | `references/running.md` |
| a test is flaking, or you need deterministic RNG / time | `references/flakes.md` |
| writing a case and want the full helper API | `docs/wiki/Testing.md` in the repo |
| reviewing someone's test diff | the `lsb-pr-review` skill, `references/tests.md` |

## Where tests live

- Lua: `scripts/tests/`, nested by kind (`jobs/`, `missions/`, `systems/`, `packets/`,
  `quests/`, `modules/`). Keep files short; add subfolders.
- C++: `src/test/tests/`, one `*.cpp` per subject (`entity_list_tests.cpp`,
  `rng_runtime_tests.cpp`, `data/zones/mobs_tests.cpp`, ...).
- Harness itself: `src/test/` (`test_application.cpp` defines the flags, `test_engine.cpp` runs
  each case, `main.cpp` wires C++ tests before Lua).
- LLS type specs for the Lua helpers: `scripts/specs/test/` (`CSimulation.lua`,
  `CClientEntityPairActions.lua`, etc.). These are the source of truth for method signatures.

## Writing a Lua test

The whole framework is `describe` (grouping, nestable) and `it` (a case), plus four lifecycle
hooks. The test name is the file path plus every enclosing `describe`, so it must read as a
sentence: `missions::Chains of Promathia::4-3::should complete the mission successfully`.

```lua
describe('Treasure Hunter', function()
    local player

    before_each(function()
        player = xi.test.world:spawnPlayer({ zone = xi.zone.KUFTAL_TUNNEL, job = xi.job.THF, level = 75 })
    end)

    it('equals TH2 for a naked THF75', function()
        player.assert:hasModifier(xi.mod.TREASURE_HUNTER, 2)
    end)

    it('equals TH3 with a Thiefs Knife', function()
        player:addItem(xi.item.THIEFS_KNIFE)
        player:equipItem(xi.item.THIEFS_KNIFE, nil, xi.slot.MAIN)
        player.assert:hasModifier(xi.mod.TREASURE_HUNTER, 3)
    end)
end)
```

The load-bearing facts, verified against `src/test/test_engine.cpp` and the wiki page:

- **Cases run top to bottom, one at a time.**
- **State is NOT reset between cases.** A player, mob, or world value you mutate in one `it`
  stays mutated in the next. Rebuild what you need in `before_each` for isolation. The three
  things the harness DOES reset per case are the PRNG seed, the weather, and the captured logs
  (`test_engine.cpp` `runTestCaseOnce`). Nothing else. Test doubles (`spy`/`stub`/`mock`) also
  auto-revert at case end.
- **Hooks:** `setup`/`teardown` run once per `describe`; `before_each`/`after_each` run per
  case and STACK from outer to inner describe. Only one of each kind per describe level.
- **Prefer `spawnPlayer({ job, level, zone })` over spawning then mutating.** One line, correct
  starting state.
- **Two ways to drive behaviour:** call Lua bindings directly (best for calculation-heavy
  systems like magic where you want each function pinned), or emulate a client via
  `player.actions:*` / `player.packets:send` (best for end-to-end behaviour). The wiki page
  spells out both; pick per system.
- **Assert with the wired helpers** (`player.assert:hasKI(...)`, `mob.assert:isAlive()`,
  negate with `.no:`) over bare `assert()` when one exists; they format the failure message
  for you.

Helper namespaces on the spawned player: `player.actions` (things a client does),
`player.entities` (mobs/NPCs around it), `player.events` (cutscene engine), `player.bcnm`,
`player.packets`, `player.assert`. Their methods change often; read the matching
`scripts/specs/test/*.lua` for the current signatures rather than guessing.

## Writing a C++ test

Catch2, in `src/test/tests/`. `TEST_CASE("...", "[tag]")`, `SECTION`, `REQUIRE` (fatal),
`CHECK` (non-fatal). Pure-logic only: these run before any server state exists and cannot use
the Lua world. Some are `consteval` and run entirely at compile time (see
`rng_spread_tests.cpp`). C++ tests are NOT filtered by `xi_test`'s flags; `main.cpp` passes
Catch2 only `argv[0]`. They all run, and if any fails the Lua suite is skipped entirely, so a
broken C++ test blocks everything.

## Test-before-fix discipline

For a bug fix, write the FAILING test first, watch it fail for the right reason, then fix, then
watch it pass. The failing run is the proof the test actually exercises the bug; a test written
after the fix can pass for reasons unrelated to the change and locks in nothing. `interrupt.lua`
is a good model: its header states the original crash (a use-after-free when a sleep landed
mid-cast) and the test asserts the observable signal (the cast completed / the caster is not
stuck inactive), not the internals.

New behaviour in core or shared Lua should ship WITH a case. A PR that only adds TODOs or
unreachable code does not merge.

## Style: do not let the test read as machine-written

The upstream review (see `lsb-pr-review` `references/tests.md`) is strict here:

- **Do not test RNG for its own sake.** A test that can flake is worse than no test. If a value
  is random, pin the seed (`references/flakes.md`) or assert an invariant, not a specific roll.
- **No line-number references in comments** (`foo.lua:73`); they rot on the next edit.
- **No ligatures, no downstream-project issue links** in test comments.
- **Human-readable enums in assertions**, never the raw underlying id: `xi.mod.TREASURE_HUNTER`,
  not `217`.
- **Arrange/Act/Assert comments only where they add information.** `describe`/`it` and the
  assertion usually say enough. Comment the non-obvious WHY, not the mechanics.

## Running it

The canonical local run, verified against the current tree:

```bash
./cmake-build-debug-visual-studio/src/test/xi_test.exe --keep-going 2>&1 | grep -vE "Query Failed|SELECT |Caching"
```

- `--keep-going` runs the whole suite instead of aborting on the first failure. Without it a
  single flake reads as a catastrophic regression ("157 passed" instead of 512) and you cannot
  tell breakage from jank. Always use it.
- The `grep -vE "Query Failed|SELECT |Caching"` filter drops harmless startup query-cache noise
  the harness logs while loading zones; it is not documented anywhere but keeps the output
  readable. It is a display filter only, it changes nothing about the run.

Add `--retry 3 --no-tag long` when you want a clean signal: `--retry` re-runs each failing case
up to N times and reports one that then passes as FLAKY (not failed), and `--no-tag long`
skips the handful of slow cases tagged `#long`. Full flag table, filtering recipes, output
formats, and the single-instance / DB-cleanup rules are in `references/running.md`.

If a test flakes, do not paper over it and do not chase known-jank cases blindly.
`references/flakes.md` has the catalog, the root causes (live mobs with full AI, per-case
reseed, unpinned Vana day), and the determinism levers.
