---
name: lsb-pr-review
description: Review LandSandBoat changes the way the upstream maintainers actually review them. Use before opening a PR against LandSandBoat/server, when reviewing an LSB diff/branch/PR, or when writing Lua/SQL/C++ for LSB and you want it to pass review first time. Rules derived from ~2900 maintainer review comments on LandSandBoat/server (Aug 2024 - Aug 2026).
license: MIT
---

# LSB PR review

Review the diff against the rules below. Report findings grouped as **Blocking**, **Should fix**,
**Nitpick**. Quote the exact replacement snippet whenever a rule has one - that is how these
comments are actually written. Do not soften: if a rule is broken, say so and give the line.

Two review lanes exist upstream and both will be applied to a given PR:

- **Content lane** (Lua scripts, quests, mobs, mobskills, data SQL): retail accuracy, correct file
  placement, idiomatic Lua, tables and enums, alignment.
- **Core lane** (C++, build, tooling, tests, modules, bindings): lifetimes, types, layering,
  performance, naming conventions, and whether the change belongs in Lua at all.

## How to use this skill

Sections 1-3 below always apply. Then get the changed file list
(`git diff --name-only <base>...HEAD`, or the PR's files) and read **only** the reference files
whose paths are touched:

| Changed paths | Read |
|---|---|
| `scripts/**/*.lua`, `modules/**/*.lua` | `references/lua.md` |
| `src/**/*.cpp`, `src/**/*.h` | `references/cpp.md` |
| `sql/**/*.sql`, `modules/**/*.sql` | `references/sql.md` |
| `modules/**` | `references/modules.md` |
| `scripts/tests/**`, `src/test/**` | `references/tests.md` |

Nothing else in the diff needs a reference file - review it against sections 1-3 and general
judgement. Do not read a reference file the diff does not touch.

Reviewing order:
1. Process gates (CI, rebase, commits, evidence, AI disclosure). A PR failing these does not get read.
2. Scope, layering, placement - is this logic even in the right file/language?
3. Data correctness and sourcing.
4. Language idioms - from the reference file(s) for the touched paths.
5. Style and formatting - same.

---

## 1. Process gates - checked before the code is

- **CI must be green.** PRs that fail the basic sanity checks are not read. Newline at end of file,
  no trailing whitespace, Lua style CI, LLS annotations, SQL sanity script.
- **Rebase on latest base** whenever there are conflicts. This is the single most frequent review
  comment in the corpus.
- **Amend + force-push.** Never a new "address comments" commit, never close-and-reopen a PR, never
  stacked PRs on unmerged work.
- **Commit hygiene**: the conventions are in the `lsb-commits` skill. As a reviewer, the findings
  are: titles over 72 characters; GitHub's auto-generated `Update <file>`; one commit covering
  several unrelated edits (`review changes`, `Add Immunities`, `Jeuno quest fixes`); evidence
  needing changes mixed in with cosmetic ones. Ask what the git history will look like to a future
  reader.
- **PR template is not to be deleted.** Fill it in, tick the boxes.
- **Do not resolve review conversations yourself** - reviewers resolve them (it is one of the
  checkboxes).
- **Do not re-request review after every push**; do not reply to every single comment, just address
  them.
- **AI usage must be disclosed**, including for the PR description. Undisclosed AI-shaped prose,
  AI-generated explanations of your own PR, or long generated write-ups get the PR closed without
  discussion. If you cannot explain the change in your own words, don't submit it. See
  `docs/ai_agents/README.md`. Disclosure is prose in the PR body; it is never a git co-author
  trailer, which `lsb-commits` bans outright.
- Untested PRs get moved to draft. Say what you tested and how.
- Security-sensitive findings go to a maintainer privately, never in a public PR/issue.

## 2. Evidence and sourcing

- Any behaviour change needs a source: **retail capture, event dump, video with timestamps, or JP
  wiki**. "Where did you get this data from?" is the default question for unsourced numbers. The
  burden of proof is on the submitter. The `lsb-docs` skill has the full trust order; the short
  version is that a wiki alone is never enough for a number.
- Wikis are frequently wrong, incomplete, or actively vandalised - do not trust them blindly.
  Chat log is not a reliable source for prep times (use action packets).
- Previous LSB/DSP implementations are not evidence either - they are often guessed or half-done.
- If the capture is not yours, say so and credit the capturer.
- Guessed or unverified values must carry the exact marker `-- Capture needed`, with no
  parenthetical. Over 400 rows under `sql/` use it and tooling greps for the literal string, so
  a `TODO` comment saying the same thing will never be found.
- **Don't default to assuming LSB is wrong.** If our capture shows X and yours doesn't, that is a
  reason to investigate, not to delete our data.
- Mob spawn positions: use the captured decimals verbatim, never round. Mark uncaptured positions
  with a comment.
- When in doubt, **balance content against players** (shorter buff durations for mobs, longer for
  players; the fixed value over a wide random).
- Wide randoms on mobskill effect durations defeat resist states - use the balanced value plus
  resistances, not `math.random(15, 60)`.
- Where retail is clearly janky or leaks information SE didn't intend, LSB may deliberately do
  better - put it behind a setting that explains the choice, and default to retail.

## 3. Scope, layering, placement - the highest-value findings

- **No scope creep.** A mixin for breaking beastmen weapons must not become "every case where a mob
  loses something". Large PRs should have been a draft or used the experimental tag.
- **Mob AI/behaviour does not live in mobskill scripts.** It belongs in the mob script or a mixin.
- **Quest/mission logic does not live in NPC or mob scripts.** Quests are self-contained under
  `scripts/quests/`; use the interaction framework and `defaultActions`. Same for NM spawn logic
  tied to a quest.
- **Zone scripts and `IDs.lua` hold no logic.** Battlefield mechanics live in the battlefield
  script, even if two battlefields look identical (they usually aren't).
- Shared logic goes in a global that everyone consumes - not in one entity that other entities reach
  into. That is a layering violation.
- **Entity iteration and target selection must not be in Lua.** The performance cost is too high and
  it has to be unpicked later for threading. Push it into core.
- Bindings belong in `luautils`/`lua_*`, not scattered through `charutils` and friends. Bindings
  prepare and look things up; they don't mutate state.
- Don't add core bindings, settings, or enum entries with no live use-case in the same PR.
- Don't push packet construction or damage multipliers into Lua; don't push into core what a mobmod
  or a Lua default would solve.
- `scripts/globals/magic.lua` is in quarantine: removals only, no additions.
- `scripts/globals/treasure.lua` is only for wild chests/coffers opened with keys or THF tools.
- Utils belong in `scripts/utils/` (loaded right after enums, so no `require` needed anywhere).
  If it is used by exactly one system, it is not a util - move it to that system's file.
- Prefer one file per behaviour over a giant shared file of simple interactions.
- New custom/downstream-only features are not taken upstream. Use a module.

---

## Output format

For each finding:

```
<file>:<line> - <Blocking|Should fix|Nitpick>
<one sentence saying what is wrong>
<replacement snippet, if there is one>
```

Then a one-line verdict: what still blocks the PR, or `Overall good. Just address the comments.`
