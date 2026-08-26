---
name: lsb-commits
description: Commit message and branch structure conventions for LandSandBoat. Use when writing a commit message, splitting work into commits, or structuring a branch or PR against LandSandBoat/server.
license: MIT
---

# LSB commits and branch structure

## Never

Do not add a Claude, AI, or agent co-author trailer to a commit or PR. Use the repo's
configured git identity, and never pass `-c user.name` or `-c user.email`.

## Message

LSB uses one of two subject forms. Match what the surrounding history does:

```
Implement Mount Zhayolm daily ore caps
[lua][sql] Update Windurst 6-1 and 6-2
```

Bracket tags are the touched area (`[lua]`, `[sql]`, `[cpp]`, `[yaml]`, `[module]`) and
stack when a change spans several. They are common but not mandatory; a plain imperative
title is equally idiomatic. LSB does not use `type(module):`.

Be as concise as possible. The title alone, read against the diff, should make the change
obvious.

Avoid a body unless the title genuinely cannot carry the why. Do not add one by default.

No emdash or other ligatures in the title or body.

## Branch structure

Structure a branch for **review by commit**: each commit is a self-contained, logically
complete, reviewable unit, in sequence. A reviewer should be able to read the branch commit
by commit and follow the reasoning.

This is the opposite of one large diff a reviewer has to page through file by file. If a
commit only makes sense alongside the next one, squash them. If a commit does two unrelated
things, split it.

Prefer amending a commit on an in-flight PR over stacking a follow-up "fix typo" commit.
