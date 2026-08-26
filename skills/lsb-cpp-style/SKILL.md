---
name: lsb-cpp-style
description: C++ style rules for LandSandBoat server code. Use when writing, modifying, or reviewing C++ (.cpp, .h, .hpp) in LandSandBoat/server. Covers comments, const/auto/constexpr usage, variable scope, control flow, ternaries and IILEs, push-ifs-up-fors-down, rule of zero/five, ownership and smart pointers, explicit/override/noexcept, and modern standard library preferences.
license: MIT
---

# LSB C++ style

Applies to C++ you write or touch. Do not churn existing code to match: the codebase
predates most of these rules (`src/map` alone has over 750 ternaries). Fix what you
are already editing, leave the rest.

Three sources, no overlap:

- **This skill**: the rules below. It covers writing C++. For reviewing a diff, the
  `lsb-pr-review` skill adds the LSB-specific checks (entity casts, `db::preparedStmt`, the
  `Mod::` enum, logging, IPC) and defers general style back here.
- **[Development Guide](https://github.com/LandSandBoat/server/wiki/Development-Guide)**:
  naming, casting, exceptions, formatting rationale, plus the Lua/SQL/Python conventions.

Three more conventions for new code, not in the guide: trailing return types (already common,
1200+ uses), a blank line after a closing brace, and `member_` for private and protected
members, with a getter `member()` and a setter `setMember()`. That is the preferred form going
forward; much of the tree still uses the older `m_Name` prefix, so write new members the new
way and match the surrounding file rather than churning old ones.

Formatting is not your job. `.clang-format` owns it, and `tools/run_clang_format.py`
enforces it (clang-format 22 exactly; it rejects other versions). Run it before you consider an edit done.

## Comments

Default to none. Well laid out, well named code documents itself.

When a comment is warranted, keep it to a single line covering only what is unintuitive or
not obvious. Never restate what the code already says.

## Declarations

Be as `const`, `const auto`, and `constexpr` as possible.

Types go on the right for assignment:

```cpp
const auto entity = CBaseEntity{ ... };   // yes
const CBaseEntity entity = ...;           // no
```

This also answers the Development Guide's caution about `auto` hiding type information:
the type is still on the line, just on the right.

Declare variables at the smallest scope that works. One variable per line, never several in
one statement.

Use `!`, `&&`, `||`. Never the alternative spellings `not`, `and`, `or`.

## Control flow

No ternaries. Use an IILE:

```cpp
const auto damage = [&]() -> int32
{
    if (isCritical)
    {
        return baseDamage * 2;
    }

    return baseDamage;
}();
```

**Push ifs up, fors down.** Hoist conditionals and preconditions to the caller instead of
burying branches inside a function, and push loops down into batch operations over a whole
collection instead of making every caller iterate. Branching stays visible in one place and
loops stay next to the data.

Keep control flow simple and explicit. Avoid recursion. Put fixed upper bounds on loops and
queues so nothing runs unbounded.

## Resource management

**Rule of Zero.** Prefer members that manage their own resources (RAII types, smart
pointers, containers) so the compiler generated destructor, copy, and move all just work.

If you must write one of destructor, copy constructor, copy assignment, move constructor, or
move assignment, write all five. Use `= default` and `= delete` rather than hand writing
trivial bodies.

Prefer `std::unique_ptr` for ownership. Raw pointers and references are for non-owning
access only. Avoid `std::shared_ptr`; keep lifetimes tightly managed.

## Interfaces

Mark single argument constructors `explicit` unless implicit conversion is genuinely
intended.

Put `override` on every overriding virtual function, and `final` where it applies.

Mark functions `noexcept` when they cannot throw.

## Standard library

Prefer modern standard library facilities over hand rolled equivalents: `std::span`,
`std::string_view`, `std::optional`, `std::variant`, structured bindings, and ranges.

## References

- [Development Guide](https://github.com/LandSandBoat/server/wiki/Development-Guide)
- [TigerStyle](https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/TIGER_STYLE.md)
- [Push Ifs Up And Fors Down](https://matklad.github.io/2023/11/15/push-ifs-up-and-fors-down.html)
