# Flakes and determinism

## Why Lua tests flake at all

The Lua suite runs against REAL mobs with full AI in an embedded live server, and the harness
reseeds the PRNG with fresh entropy before every case (`test_engine.cpp` `runTestCaseOnce` calls
`simulation_->seed()`). So two things conspire:

1. Any case that leaves a live mob near a vulnerable player flakes on an unlucky seed: the mob
   aggros, roams, casts, or melees during the test.
2. `skipTime()` (and `tick()`) run a full ZoneTick that advances ALL entity AIs, so mobs act
   during the seconds a test skips, not just the entity under test.

State does NOT reset between cases (only seed, weather, and logs do). Whatever the previous case
mutated on a shared mob or the world clock is still there. A "per-test mob-state isolation"
effort exists in project notes but is NOT on the base branch: `runTestCaseOnce` today resets seed
+ weather + logs and nothing else. Do not assume mobs come back clean.

## Determinism levers

- **`xi.test.world:setSeed(n)`** forces a specific seed, overriding the per-case reseed. Same
  seed gives the same `math.random` stream every run. Seed at the top of a case, or in
  `before_each` if a whole suite needs it. `xi.test.world:seed()` restores a fresh random seed.
- **The RNG is bit-exact and cross-platform** (Squirrel5 + canonical53). `scripts/tests/framework/prng.lua`
  locks golden streams; if you seed, the sequence is reproducible on every machine.
- **Reproducing a flake without rebooting the server:** since `setSeed` overrides the reseed, you
  can sweep seeds in-process (loop `setSeed(n)` over a range in one run) instead of restarting
  per seed. Force the adversarial state directly (`setMobLevel`, `setWeather`, `updateEnmity`,
  co-locating the mob) rather than waiting for the full suite to drift into it. Confirm both that
  the FAIL reproduces and that your fix flips it to pass.
- **Time is a flake source too.** `skipTime(s)` moves only the steady/timer clock (recasts,
  cooldowns); it does NOT touch `earth_time` or the Vana'Diel clock. Vana ticks
  (`tick(JST_HOUR)`, `tick(VANA_HOUR)`) snap to the next boundary with `ceil`, so a repeated tick
  can STALL on the hour and advance nothing. The reliable forward lever for real-world duration
  is `xi.test.world:skipToNextVanaDay()` (about 58 earth-minutes per call). Clock offsets are
  process-global and NOT reset between cases, so prefer offset-invariant assertions: capture a
  baseline, advance by whole intervals, assert the delta.

## Fixing a flake: prefer non-leaking fixes

Mutate the FRESH per-test player, not the SHARED mob. Shared mobs leak state across cases.

- `player:setUnkillable(true)` to stop a co-located aggressive mob killing the player mid-test.
- Give the player the state it needs in `before_each`; do not rely on a mob's default.

If you MUST mutate a shared mob, restore it in `after_each`. The concrete trap:
`setAutoAttackEnabled(false)` lives on the AI controller and `respawn()`/`Spawn()` does NOT reset
it, so on a shared mob it LEAKS into the next case. `interrupt.lua` disables it in `before_each`
and re-enables it in `after_each` for exactly this reason; a sibling test needs that same rabbit
to swing.

Other traps worth knowing:

- Melee hit rate has a hard 0.2 floor (`scripts/combat/physical_hit_rate.lua`). Piling evasion on
  a sleeping caster does NOT reliably stop a mob waking it; disable the swing instead.
- Weather-gated mobs (elementals) despawn as ambient weather cycles, invalidating a target
  mid-test. Pin it: `setWeather(xi.weather.THUNDER)` then `spawn()` the elemental.
- Guild shops can close on Vana holidays (`GUILD_SHOP_HOLIDAYS`). A test that pins only the time
  and not the day flakes when suite drift lands it on the shop's day off. Pin the day too
  (`setVanaDay(xi.day.WINDSDAY)`).

## Known-jank tests: do not chase

Some cases are order/state dependent and the user has confirmed them as known jank. The standing
example is `packets::s2c::0x028_battle2::BATTLE2::Beastmaster::Jug Pet Ready`: it can fail
standalone yet pass in the same build under `--keep-going`. Do not stash, bisect, or "fix" these;
confirm the run with `--keep-going` (and `--retry`) and move on. A genuinely flaky case should be
made deterministic (pin the seed / the state) or, if it truly cannot be, it does not belong in the
suite. RNG is not something to assert on directly.

## The golden rule

Always run `--keep-going`. Without it the runner aborts on the first Lua failure, so one flake
masquerades as a full-suite collapse and you cannot tell real breakage from jank. With it you get
the true tally, and `--retry 3` tells you which failures were flakes (reported FLAKY) versus real.
