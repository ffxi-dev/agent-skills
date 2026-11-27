# lsb-agents-skills

[Agent Skills](https://agentskills.io) for [LandSandBoat](https://github.com/LandSandBoat/server)
development and Final Fantasy XI research.

Working on an FFXI private server involves a lot of knowledge that isn't in the code: what
retail actually does, which capture or wiki page can be trusted, how the data formats fit
together, and what a reviewer will send back. That knowledge normally gets re-explained to
an agent every session, or pasted into a CLAUDE.md that grows until nobody reads it. These
skills package it once, and load it only when a task calls for it.

Two things live here:

**LSB development**: server conventions and workflows: C++/Lua/SQL style, the data-layer
formats, build and test harness usage, and pre-flight review so a PR lands the first time.

**FFXI research**: establishing what retail actually did: reading packet captures, dating a
mechanic against the version-update history, and weighing wiki sources against each other
before any of it becomes a code change.

The two feed each other. Research settles what the behaviour should be; the development
skills turn that into a change that survives review. A few skills are plain tooling that
serves both, like rendering a set of coordinates onto a zone map.

Skills are plain folders of Markdown under [`skills/`](skills/). The format is an open
standard, so the same files load in Claude Code, Codex, and ~30 other agents without
per-agent copies.

## Skills

| Skill | Use when |
| --- | --- |
| [`lsb-cpp-style`](skills/lsb-cpp-style/) | Writing, modifying, or reviewing C++ in the server. |
| [`lsb-commits`](skills/lsb-commits/) | Writing a commit message or structuring a branch for review. |
| [`lsb-docs`](skills/lsb-docs/) | Writing docs, PR descriptions, or a capture writeup. |
| [`lsb-pr-review`](skills/lsb-pr-review/) | Reviewing an LSB diff, or self-checking before opening a PR. |
| [`lsb-exploit`](skills/lsb-exploit/) | Checking a packet handler, binding, or event script for client-trust holes. |
| [`lsb-tests`](skills/lsb-tests/) | Writing and running LSB tests, and diagnosing flakes. |
| [`lsb-build`](skills/lsb-build/) | Building the server on Windows, Linux, or macOS. |
| [`lsb-profile`](skills/lsb-profile/) | Profiling the server with Tracy to find hotspots. |
| [`ffxi-version-updates`](skills/ffxi-version-updates/) | Dating when a retail mechanic changed, EN and JA patch notes. |
| [`ffxi-wiki`](skills/ffxi-wiki/) | Looking up FFXI game data across the three community wikis. |
| [`ffxi-zone-render`](skills/ffxi-zone-render/) | Plotting coordinates on a zone map as a PNG. |
| [`ffxi-resources`](skills/ffxi-resources/) | Trusted client-extracted values: message/item IDs, event bytecode, abilities. |
| [`ffxi-packets`](skills/ffxi-packets/) | Reading raw packet bytes from captures, with first-class action decode. |
| [`scholar`](skills/scholar/) | Reading the data behind a Mogsafe, Scholar, or Lens link, and asking SQL across every capture Vault archives. |
| [`ffxi-re`](skills/ffxi-re/) | Reverse-engineering the FFXI client: decomp, FFXiMain.dll, PS2 ELF. |

Pairs well with [orwell-writing](https://github.com/tamdogood/builder-essential-skills/blob/main/skills/orwell-writing/SKILL.md)
(MIT, installed separately), which `lsb-docs` defers to for sentence mechanics.

`ffxi-version-updates` builds its corpus locally on first use from
[Frankie-hz/ffxiupdates](https://github.com/Frankie-hz/ffxiupdates) (MIT); see its
[SKILL.md](skills/ffxi-version-updates/SKILL.md). The notes are Square Enix's text and are not
redistributed here.

[`rules/global-style.md`](rules/global-style.md) holds always-on communication rules. Those
are not skills: paste them into your global `CLAUDE.md` or `AGENTS.md`.

## How to use this repository

Two ways in.

**You want to use the skills.** Install the plugin, below. Your agent loads them on its own
when a task matches. Nothing else here concerns you.

**You want to work on them.** Clone it and install the two tools CI uses:

```sh
git clone https://github.com/ffxi-dev/agent-skills.git
cd lsb-agents-skills
pip install skills-ref mypy
```

The loop for any change:

1. Read [Ground rules](#ground-rules). They are short and they are the review criteria.
2. Add or edit a skill following [Adding a skill](#adding-a-skill).
3. Run what CI runs, before opening a PR:

```sh
agentskills validate skills/<skill-name>   # frontmatter
mypy --strict skills/<skill-name>           # types (per skill: two skills share a build.py basename)
python hooks/test_lsb_cpp_check.py         # or: pytest
```

One gotcha when editing a skill you also have installed: your agent loads the **installed**
copy, not your working tree. Symlink the skill into your agent's skills directory, or
reinstall the plugin, or you will be testing the old version and wondering why nothing changed.

## Install

**Claude Code**

```
/plugin marketplace add ffxi-dev/agent-skills
/plugin install lsb-agents-skills@lsb-agents-skills
```

**Codex**: clone anywhere and symlink into a repo Codex reads:

```sh
git clone https://github.com/ffxi-dev/agent-skills.git
ln -s "$PWD/lsb-agents-skills/skills" ~/.agents/skills/lsb
```

**Any other agent**: point it at `skills/`, or copy the folder you want into whatever
directory that agent scans (`.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, ...).

## Adding a skill

```
skills/<skill-name>/
├── SKILL.md      # required
├── references/   # optional, loaded on demand
├── scripts/      # optional
└── assets/       # optional
```

`SKILL.md` needs frontmatter with `name` (must equal the folder name) and `description`
(say what it does *and* when to use it, since that line is all an agent sees until it
decides to load the skill):

```markdown
---
name: lsb-pr-review
description: Review LandSandBoat changes the way the maintainers review them. Use before opening a PR against LandSandBoat/server or when reviewing an LSB diff.
---

Instructions go here.
```

Keep the body under ~500 lines; push detail into `references/`. CI validates every skill
against the spec on push:

```sh
pip install skills-ref mypy
agentskills validate skills/<skill-name>   # frontmatter
mypy --strict skills/<skill-name>           # types (per skill: two skills share a build.py basename)
python hooks/test_lsb_cpp_check.py         # or: pytest
python tools/gen_skill_readmes.py          # regenerate the per-folder README.md
```

Each skill folder has a `README.md` generated from its `SKILL.md` frontmatter, so GitHub shows
a summary when you open the folder. Do not edit it by hand; change `SKILL.md` and rerun the
generator (CI fails if it is stale).

Tests live next to what they test as `test_*.py`, run under pytest or standalone, and CI
picks them up by glob.

## Enforcement

A skill is a context delivery mechanism, not a policy one. Nothing makes an agent load a
skill, and nothing makes it comply once loaded. So the mechanical rules are enforced
outside the model, in three places:

**Edit time (this repo).** `hooks/lsb_cpp_check.py` runs on every Edit/Write of a C++ file
and reports violations back to the agent immediately. It ships in the plugin, so installing
the skills installs the enforcement. It only runs inside a LandSandBoat checkout (detected via `src/map` plus
`scripts/globals`), so installing the plugin globally will not make it fire on unrelated
C++. It checks only the rules no linter covers (ternaries, `and`/`or`/`not`) and only on
lines you changed: `src/` has 831 pre-existing ternary lines,
so whole-file checking would bury real findings.

**Build time.** `clang-format` for formatting, `clang-tidy` locally for the checks in the
server's `.clang-tidy`.

**CI.** LandSandBoat already runs clang-tidy on every PR. It is the backstop for anyone
without the plugin, not the primary gate. Finding out at CI is finding out too late.

Rules with no mechanical check anywhere (push-ifs-up-fors-down, the comment policy, smallest
scope, `const auto` with types on the right) rely on the skill being loaded. To make that
reliable, point at it from an always-loaded file rather than duplicating it:

```markdown
C++ changes follow the `lsb-cpp-style` skill. Load it before editing any .cpp/.h.
```

Put that in the server repo's agent-instruction files: it ships `AGENTS.txt` and
`.github/copilot-instructions.md` (both currently just point at `docs/ai_agents/README.md`).
Two lines, near-zero context cost, works for both agents, and keeps one source of truth.

## Ground rules

### Contributions

- AI agents building skills here is fine and welcome.
- AI agents suggesting changes to existing skills is fine.
- A human opens and owns the PR. Agent authorship needs no attribution, but nobody merges
  work they have not read.
- **Commits here use Conventional Commits** (`feat:`, `fix:`, `ci:`, `docs:`), because
  release-please reads them to bump the plugin version. A commit without a recognised prefix
  ships no release, and Claude Code caches an installed plugin by version, so the change
  reaches nobody. This is not the LandSandBoat convention: `lsb-commits` describes the server
  repo's bracket tags, which apply there and not here.
- Check the skill index before adding. A second skill covering the same trigger splits the
  description space and makes both load less reliably.

### Skills

- Skills MUST have tests, and regression tests once something has actually gone wrong.
  Frontmatter validity is checked in CI and does not count. What "test" means depends on what
  the skill ships:
  - **Skills shipping executable code** are tested end to end through the real entry point
    against synthetic fixtures. A packet parsing script ships fake packets and asserts on what
    it extracts. Unit tests on the pieces are not enough: every bug this repo's own hook has
    had passed the unit tests and only showed up against the real tree.
  - **Test what fails silently.** Anything that transforms data earns tests, because a parser
    that quietly mangles its output produces a corpus nobody knows is wrong. Code that either
    works or visibly does not, and that is safe to re-run, is worth less: the download path in
    `ffxi-version-updates/build.py` leans on this, since a failed download is loud, idempotent,
    and fixed by running it again.
  - **Prose only skills** have nothing to execute, so the obligation is verification instead.
    Every factual claim is checked against the source before it ships: run the command, open
    the path, resolve the link, count the rows. Re-check them when you touch the skill, since
    claims rot silently. A skill that confidently names a flag that has since been renamed is
    worse than no skill, because it will be believed.
- One source of truth. If the wiki or the server repo's agent-instruction files already state a rule,
  link it, do not restate it. Copies drift silently and a reader cannot tell which is
  current.
- The description is the loading contract. It is all an agent sees before deciding, so name
  concrete triggers: file types, commands, the way someone would actually phrase the task. A
  skill that never loads does nothing.
- Keep `SKILL.md` under roughly 500 lines. Detail belongs in `references/`, loaded on demand.
- Cite the source for claims about retail behaviour. Capture beats wiki, wiki beats memory.
  Say which one you used.

### Tooling

- Python and YAML by default, matching LSB's own tooling. Another language is fine if agents
  are fluent in it and can iterate quickly. Type checking is the bar: a compiled language
  gets it for free, Python needs annotations and CI runs `mypy --strict` per skill.
- Dependencies are fine as long as they are not massive, defined loosely and by judgement.
  One that does a job well beats fifty lines of clever.
- Do not let supporting scripts sprawl. Shared code lives at the repo root and gets reused.
  Copying a helper into a second skill is a refactor signal, not a shortcut.
- Validate any checker against the real server tree before shipping it, and state its false
  positive rate. Passing unit tests proves nothing: the C++ hook here passed twelve cases and
  still flagged 2794 lines of GPL header the first time it met `src/`.
- Every real world miss becomes a test case.
- Scope checks to what changed. The codebase predates most of these rules, and a tool that
  flags pre-existing code is noise that gets switched off within a week.
- Tools ship gated. Anything that runs automatically must no-op outside its scope.
- Do not reimplement a linter. If clang-format or clang-tidy already enforces a rule, wire
  those up instead.

## Layout

| Path | Purpose |
| --- | --- |
| `skills/` | The skills. Single source of truth, agent-agnostic. |
| `.claude-plugin/` | Claude Code plugin + marketplace manifests. |
| `.codex-plugin/` | Codex plugin manifest. |
| `hooks/` | Edit-time checks, shipped with the plugin. |
| `staging/` | Files headed for the server repo, not yet pushed. |
| `rules/` | Always-on rules that cannot be skills. Paste into a global instructions file. |

Supporting a new agent means adding one manifest that points at `skills/`, never a second
copy of the skills.

## License

MIT
