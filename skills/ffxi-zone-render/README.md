# ffxi-zone-render

Render a top-down map of an FFXI zone with arbitrary coordinates marked on it, headless, as a PNG. Use whenever the answer is easier to see than to read: where a set of mobs or NPCs spawn, where a list of positions falls in a zone, whether coordinates land on the navmesh or in a wall, what a set of extracted or computed positions looks like laid out on the map. Takes a zone and a list of x/y/z points and returns an image. It does not know or care where the points came from.

See [SKILL.md](SKILL.md) for the full instructions, and the [repo README](../../README.md) for how skills are installed.

**Requirements:** Requires git and Node 24+ on PATH, plus Python 3.9+. Clones the xi-visualizer renderer and fetches its 150MB mesh submodule on first run.

<!-- generated from SKILL.md by tools/gen_skill_readmes.py; do not edit -->
