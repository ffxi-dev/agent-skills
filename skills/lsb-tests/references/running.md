# Running xi_test

## The binary

`xi_test` is a single executable at `src/test/xi_test.exe` under whichever build directory you
built. The canonical local build is `cmake-build-debug-visual-studio/src/test/xi_test.exe`.
CLion's `cmake-build-releasevs/` is a SEPARATE tree that goes stale; do not run tests out of it
after building elsewhere. Building is out of scope here (see the `lsb-build` skill).

It runs C++ Catch2 unit tests first, then, only if those all pass, the Lua suite. A failing C++
test skips the entire Lua suite, so `C++ unit tests failed; skipping the Lua test suite.` in the
output means fix the C++ test before anything else.

## Flags

Verified against `src/test/test_application.cpp` (the definitive list; the wiki Arguments table
is missing `--retry`, `--no-filter`, and `--watch`).

| Flag | Effect |
|---|---|
| `--keep-going` | Continue after a failure instead of aborting on the first one. Use always. |
| `--verbose` | Print logs even for passing tests (normally logs print only on failure). |
| `--watch` | Declared but NOT implemented; does nothing. |
| `--tag <t>` | Run only cases whose name contains `#t`. Repeatable. |
| `--no-tag <t>` | Skip cases tagged `#t`. Takes precedence over `--tag`. Repeatable. |
| `--file <re>` | Run only test files whose path matches the regex. Repeatable. |
| `--no-file <re>` | Skip files matching the regex. Precedence over `--file`. Repeatable. |
| `--filter <re>` | Run only cases whose full name matches the regex. Repeatable. |
| `--no-filter <re>` | Skip cases matching the regex. Precedence over `--filter`. Repeatable. |
| `--output <path>` | Write a CTRF JSON report (use a `.json` path). |
| `--retry <n>` | Re-run each failing case up to n times; one that then passes is reported FLAKY. |

All the `--tag`/`--file`/`--filter` values are regex and all are repeatable. None of these flags
reach the C++ Catch2 tests; those always run in full.

## Recipes

```bash
# Everything, readable, don't stop on failure
./cmake-build-debug-visual-studio/src/test/xi_test.exe --keep-going 2>&1 | grep -vE "Query Failed|SELECT |Caching"

# Clean pass/fail signal for a full-suite check: retry flakes, skip the slow ones
xi_test.exe --keep-going --retry 3 --no-tag long 2>&1 | tail -8

# Only one file (regex over the path)
xi_test.exe --keep-going --file 'guild_shops'

# Only cases matching a name, across all files
xi_test.exe --keep-going --filter 'Treasure Hunter'

# Everything except one noisy file
xi_test.exe --keep-going --no-file '0x028_battle2'

# Only #magic-tagged cases that live under systems/
xi_test.exe --keep-going --tag magic --file systems
```

## The noise filter

`grep -vE "Query Failed|SELECT |Caching"` is a display-only filter for the harmless
query-cache and zone-load logging the embedded server emits at startup. It is not documented in
the repo and is not part of the harness; it just keeps the terminal readable. It removes no test
result. Drop it if you are debugging a DB or query problem.

## Output

- Default reporter is a colorized gtest-style stream (`[ RUN ]` / `[ OK ]` / `[ FAILED ]`,
  ending with a `[==========] N tests ran.` tally). It cannot be disabled. Logs print only for
  failing cases unless `--verbose`.
- Flaky cases (passed on retry) are listed separately under `[  FLAKY   ]` at the end
  (`src/test/reporters/console_reporter.cpp`).
- `--output report.json` additionally writes a CTRF JSON file at the end of the run.

## Tags

A tag is a `#word` inside a test name, e.g. `it('increases drop rates #long', ...)`. Tags are
parsed from the name string, so multiple tags in one name work (`#long #ci`). `--tag`/`--no-tag`
match those words. The only tag in real use in the tree today is `#long` (slow cases you skip
with `--no-tag long`).

## Operational rules learned the hard way

- **Run only ONE xi_test at a time.** Instances share the database and collide on test account
  ids. `xi_test` binds no network port (IPC is in-process ZMQ over `inproc://`), so nothing
  stops you launching two, but they WILL corrupt each other's DB state.
- **Killed or crashed runs leak `TEST_%` accounts** (ids >= 20000000). New runs allocate
  `max(id)+1`, so leftovers eventually cause "Unable to create new account" / duplicate-PK
  errors. Clean them from the map DB (default `xidblsb`):
  ```sql
  DELETE FROM accounts WHERE id >= 20000000 OR login LIKE 'TEST\_%';
  DELETE FROM chars    WHERE charid >= 20000000;
  ```
- **Background runs block-buffer stdout** (no TTY). To watch progress, append per-iteration
  output to a file (`>> run.log`) and tail it, rather than relying on the captured stdout of a
  backgrounded command.
