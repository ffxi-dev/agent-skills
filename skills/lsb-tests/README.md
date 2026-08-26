# lsb-tests

Write and run tests for LandSandBoat. Use when writing a new xi_test case, adding a failing test before a bug fix, running xi_test or the Lua test suite, filtering tests, diagnosing a flaking test, or answering "how do I test this" for LSB. Covers the Lua harness (describe/it, lifecycle, spawnPlayer, ticks, doubles, assertions), the C++ Catch2 tests, the real flags, and the flake catalog. Not for compiling (see lsb-build) or reviewing a test diff (see lsb-pr-review references/tests.md).

See [SKILL.md](SKILL.md) for the full instructions, and the [repo README](../../README.md) for how skills are installed.

<!-- generated from SKILL.md by tools/gen_skill_readmes.py; do not edit -->
