---
name: lsb-profile
description: >
  Profile a LandSandBoat server with Tracy to find performance hotspots. Use when the task is
  to profile LSB, find why the server or a zone is slow, measure a suspected hot path, capture
  a Tracy trace, read zone or frame timings, check a performance change against a before/after,
  or answer "where is the time going". Covers building with Tracy on, running, capturing a
  trace and CSV with the repo's capture tool, and reading the result.
license: MIT
compatibility: >
  Needs a Tracy-enabled build of the server, the standalone tracy-capture and tracy-csvexport
  tools placed at the LSB repo root, and the Tracy profiler GUI to open a trace. The CSV path
  works headless without the GUI.
---

# Profile LandSandBoat with Tracy

Tracy is a sampling and instrumentation profiler. LSB has Tracy zones compiled in behind a
build flag, and ships `tools/capture.py` to pull a trace from a running server. The loop is:
build with Tracy on, run, capture, read.

## 1. Build with Tracy on

Use the `lsb-build` skill with `--tracy`; it builds into its own `build-tracy` directory so it
never mixes with your normal build:

```bash
python build.py --tracy xi_map
```

That is `-DTRACY_ENABLE=ON` under the hood. A server built without it has no Tracy zones, so a
capture connects to nothing. Do not profile a normal build and wonder why it is empty.

## 2. Run the server

Start the Tracy build (`build-tracy/.../xi_map`). It listens for a profiler on the Tracy port,
**8086** by default. To use another port, set `TRACY_PORT` in the server's environment and pass
the same port to the capture in step 3. Reproduce the workload you care about while it runs:
the trace only contains what happened during the capture window.

## 3. Capture a trace

From the LSB repo, with the server running:

```bash
python tools/capture.py                 # 60s on port 8086 -> trace + CSV in the cwd
python tools/capture.py -s 120 -p 8087  # 120s, matching a TRACY_PORT=8087 server
python tools/capture.py --self          # CSV of self-times, not inclusive totals
python tools/capture.py --no-csv        # trace only, skip the CSV
```

It wraps `tracy-capture`, writing `trace_<timestamp>.tracy`, then extracts a zone-statistics
CSV next to it with `tracy-csvexport`. Options: `-s/--seconds` (default 60), `-p/--port`
(default 8086, must match the server), `-o/--out-dir` (default the current directory), `--self`
for self-times, `--no-csv` to skip extraction.

**The tools must be at the repo root.** `capture.py` looks for `tracy-capture(.exe)` and
`tracy-csvexport(.exe)` one level up from `tools/`. If it reports one missing, put the
standalone Tracy tool there. They must match the Tracy version LSB vendors (in `ext/`), or the
trace will not open cleanly.

## 4. Read the result

- **The `.tracy` file** opens in the Tracy profiler GUI: flame graph, per-frame timing, zone
  call counts, the statistics view. This is the real analysis surface.
- **The CSV** is the headless answer: one row per zone with call count and time. `--self` gives
  self-time (the zone's own cost, excluding children), which is what you want for "what is
  actually expensive" rather than "what contains the expensive thing".

## Discipline

- **Measure, do not guess.** Capture a trace before you change anything, and one after, and
  compare. A named-in-the-abstract hotspot is a hypothesis until a trace shows it.
- **Profile the real workload.** An idle server profiles as idle. Reproduce the busy zone, the
  crowded event, the heavy tick during the capture window.
- **Self-time over inclusive time** for finding the actual cost. A parent zone looking expensive
  is usually its children; `--self` tells them apart.
- The `(program)` and software-render caveats from headless measurement do not apply here; this
  profiles the real server process, not a browser. But a debug or sanitizer build has different
  timings than a release build, so profile the `--tracy` (RelWithDebInfo) build, not those.
