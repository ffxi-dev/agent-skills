# Module rules


- A module is a **bag of overrides**. Logic in the file body that overwrites a global is not a
  module - it only works by load-order accident. Use `m:addOverride('path.to.fn', function(...) ...`
  with `super()` where needed.
- Do not gate the module body behind content tags and return a fake empty module - an empty module
  is malformed. The operator chooses which modules to load.
- Era modules live under `modules/era/<expansion>/` and their header says **which** era and the
  patch date the behaviour changed, with a source link. "ERA"/"OLD" mean nothing on their own.
- Same for settings names: `USE_PRE_WOTG_EXP_LOSS_TIERS`, not `ERA_EXP_LOSS`.
- One header per file, not two. Don't duplicate the description in a second comment block.
- Modules are for downstream, not for us - but their SQL changes still get reviewed.
