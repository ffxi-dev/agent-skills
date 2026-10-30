# Staging: CLAUDE.md for LandSandBoat/server

Destined for the root of `LandSandBoat/server` as `CLAUDE.md`. Not named `CLAUDE.md` here
so it does not load as instructions while working in this repo.

The server repo already ships `AGENTS.txt` and `.github/copilot-instructions.md`, both short
pointers to `docs/ai_agents/README.md`. This file folds the actual rules in; decide on push
whether it replaces or complements them.

**Constraint:** this file is always-on context for every session in the server repo,
including Lua, SQL and YAML work that will never touch C++. Every line is paid for on every
task. Keep it terse. Rationale, worked examples and anything long belongs in the
`lsb-cpp-style` skill, which loads only when it is relevant.

**On push:** rename to `CLAUDE.md`. The repo's `AGENTS.txt` already serves Codex, so either
point it at this file or fold this content into it, rather than adding a competing `AGENTS.md`.

---

# LandSandBoat

The [Development Guide](https://github.com/LandSandBoat/server/wiki/Development-Guide) is the
authority for naming, formatting, casting, and the Lua/SQL/Python conventions. Read it. What
follows is what that guide does not cover.

## Working on existing code

The codebase predates most of the rules below. Apply them to code you write or are already
editing. Do not reformat or rewrite surrounding code to match, and do not open PRs that only
do this: it buries real changes and makes review harder.

## C++

- Trailing return types: `auto foo() -> uint8`, not `uint8 foo()`. Not on `void`.
- Blank line after the closing `}` of an `if`/`else`/`for`/`while`/`switch`.
- Private and protected members take a trailing underscore: `member_`, getter `member()`,
  setter `setMember()`. Preferred going forward; older `m_Name` members exist, match the file.
- Default to no comments. When one is warranted, keep it to a single line covering only what
  is not obvious. Never restate the code.
- Be as `const`, `const auto` and `constexpr` as possible.
- Types go on the right: `const auto x = Type{ ... };`, not `const Type x = ...;`.
- Declare variables at the smallest scope that works. One per line.
- `!`, `&&`, `||`. Never `not`, `and`, `or`.
- No ternaries. Use an immediately invoked lambda.
- Push ifs up and fors down: hoist conditionals to the caller, push loops down into batch
  operations over a collection.
- Simple explicit control flow. Avoid recursion. Bound loops and queues.
- Rule of Zero. If you write one of the five, write all five, using `= default` and
  `= delete` over trivial bodies.
- `std::unique_ptr` for ownership. Raw pointers and references are non-owning only. Avoid
  `std::shared_ptr`.
- `explicit` on single argument constructors unless conversion is intended.
- `override` on every overriding virtual, `final` where it applies.
- `noexcept` where a function cannot throw.
- Prefer `std::span`, `std::string_view`, `std::optional`, `std::variant`, structured
  bindings and ranges over hand rolled equivalents.

## Commits

- Do not add an AI or agent co-author trailer. Use the repo's configured git identity.
- Subject only. Add a body only when the title genuinely cannot carry the why.
- The title, read against the diff, should make the change obvious.
- Match surrounding history: either a plain imperative title, or bracket tags for the areas
  touched (`[lua]`, `[sql]`, `[cpp]`, `[yaml]`, `[module]`, stacked when a change spans
  several).
- Structure a branch for review by commit: each commit self-contained, logically complete,
  and reviewable in sequence. Squash a commit that only makes sense with the next one, split
  one that does two unrelated things.

## Commands

```sh
python tools/run_clang_format.py            # format C++, required before committing
cmake -DENABLE_CLANG_TIDY=ON ..             # the checks CI runs on every PR
./xi_test --keep-going --retry 3 --no-tag long
```

`--keep-going` avoids stopping at the first failure, `--retry 3` absorbs RNG flakes, and
`--no-tag long` skips the slow suites. Without them an ordinary run reads as breakage.

## Communication

- No emdash or other ligatures, in code, comments, commit messages, or replies.
- Be direct. No large blocks of prose.
- State things directly rather than using "it's not X, it's Y".
- Write `thing/thing/thing`, not `thing / thing / thing` and not `thing + thing`.
- Push back on weak ideas rather than agreeing, and say plainly when a path is unproductive.

## Optional

[lsb-agents-skills](https://github.com/ffxi-dev/agent-skills) packages the above as Agent
Skills, with an edit time hook that catches the C++ rules no linter checks. Not required to
contribute.
