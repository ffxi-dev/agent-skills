# C++ / core rules


### Types and lifetimes
- No raw pointer members; no raw `new`. `std::unique_ptr` (and then don't manually `destroy`).
  If a member is cheap to construct, just make it a value member with an accessor.
- `dynamic_cast` for entity pointers, and check the result immediately. `objtype` + `static_cast`
  only in the simplest cases, and never confirm one type then cast to another.
- If a container is constructed with a back-pointer to its owner, that owner is always valid -
  don't paper over a lifetime bug with a null check.
- `std::optional` / `Maybe<T>` for "might not exist", and name it `maybeThing`.
  Check with `has_value()`. Don't default-construct a sentinel.
- Prefer `enum class` with our `uint8`/`uint16` aliases over naked bools and raw ints; entries don't
  repeat the enum's name. For boolean-ish parameters use a strongly-typed flag (`xi::Flag<Tag>`)
  with no default, so every call site is explicit.
- Unsigned types can't be `< 0`. Watch signedness/width mixing end to end (getter, setter, member)
  rather than widening one link in the chain.
- `std::size_t` for indices, not `lua_Integer`/`int`.

### Style

General C++ style is the `lsb-cpp-style` skill: const/auto usage, ternaries, control flow,
ownership, `explicit`/`override`/`noexcept`, and the modern stdlib preferences. Read it rather
than re-deriving them here, and do not raise a style finding this file does not list.

Formatting is `.clang-format`'s job and `tools/run_clang_format.py` enforces it. Bracing,
alignment and trailing commas are not review findings.

What is left for a reviewer, because no tool catches it:

- `auto*`/`auto` when the type is already stated in a `static_cast`/`get<>`; naming it twice
  is the finding, not the `auto`.
- `#pragma once`, never include guards.
- Floats written `100.0f`, not `100.f`.
- No page-break or banner block comments.

### Idioms
- `!container.empty()` over `size() > 0`. Structured bindings over `.first`/`.second`.
  `std::ranges::any_of` and friends over hand-rolled loops. `starts_with` over manual compares.
- Invert and early-return instead of wrapping a whole function in an `if`.
- Don't erase while iterating with raw iterators; use `std::erase_if`.
- Constants go in an anonymous namespace at the top of the `.cpp`, not rebuilt per call. Same for
  lookup maps.
- All DB access via `db::preparedStmt`, with the query defined inline and arguments vertically
  spaced; pull columns by name, not index.
- Logging: don't prefix with the function name (the logger appends it). Player-action logging is
  opt-in, not default. High-frequency audit writes go through the async path.
- IPC: target the process that needs the message; broadcasting to all processes is a last resort.
- If a function is expensive (zone-wide iteration), say so in the name.
- Header declarations must match the definition you changed.
- Add `Mod::` entries to `data/enums/mod.yaml` and update the `SPARE IDs:` comment at the bottom
  when adding or freeing one. (Mods moved out of `modifier.h` to the YAML enum.)
- Core enums should mirror the Lua enum names and casing so the two are greppable together.
- Message enums are named for what the message says (`LevelSyncActivated`), never with the numeric
  ID baked into the name.
- Changing a function's parameter order or count means updating every call site, optional or not.
- Don't leave workarounds in place of a model fix - if "add but skip the DB" is needed, the
  container model is wrong.
