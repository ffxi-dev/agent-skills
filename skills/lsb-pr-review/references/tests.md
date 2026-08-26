# Test rules


- New behaviour in core or shared Lua should come with an `xi_test` case; PRs that only add TODOs or
  only add unreachable code don't merge.
- Don't test RNG - a test that can flake is worse than no test.
- Arrange/Act/Assert comments only where they add information; `describe`/`it`/the assertion usually
  say enough already.
- No line-number references, no ligatures, no downstream-project issue links in test comments.
- Prefer human-readable enums in assertions over the raw underlying IDs.
