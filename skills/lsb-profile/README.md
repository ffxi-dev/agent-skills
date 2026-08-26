# lsb-profile

Profile a LandSandBoat server with Tracy to find performance hotspots. Use when the task is to profile LSB, find why the server or a zone is slow, measure a suspected hot path, capture a Tracy trace, read zone or frame timings, check a performance change against a before/after, or answer "where is the time going". Covers building with Tracy on, running, capturing a trace and CSV with the repo's capture tool, and reading the result.

See [SKILL.md](SKILL.md) for the full instructions, and the [repo README](../../README.md) for how skills are installed.

**Requirements:** Needs a Tracy-enabled build of the server, the standalone tracy-capture and tracy-csvexport tools placed at the LSB repo root, and the Tracy profiler GUI to open a trace. The CSV path works headless without the GUI.

<!-- generated from SKILL.md by tools/gen_skill_readmes.py; do not edit -->
