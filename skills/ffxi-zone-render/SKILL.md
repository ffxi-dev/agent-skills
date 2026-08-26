---
name: ffxi-zone-render
description: >
  Render a top-down map of an FFXI zone with arbitrary coordinates marked on it, headless,
  as a PNG. Use whenever the answer is easier to see than to read: where a set of mobs or
  NPCs spawn, where a list of positions falls in a zone, whether coordinates land on the
  navmesh or in a wall, what a set of extracted or computed positions looks like laid out
  on the map. Takes a zone and a list of x/y/z points and returns an image. It does not
  know or care where the points came from.
license: MIT
compatibility: Requires git and Node 24+ on PATH, plus Python 3.9+. Clones the xi-visualizer renderer and fetches its 150MB mesh submodule on first run.
---

# Render points on a zone map

Give it a zone and some coordinates, get back a PNG of that zone from above with the
coordinates marked.

This is a rendering primitive and nothing more. It takes points and returns an image. Where
the points came from, a packet capture, a SQL table, a pathfinding run, or typed by hand, is
the caller's business and this skill must not grow an opinion about it.

## Use it

```bash
python render.py --points spawns.json --out shots/
```

Each point is `{zone, group?, kind?, x, y, z}`:

```json
[
  { "zone": "West Ronfaure", "group": "cursed_chest", "kind": "Cursed Chest",
    "x": -160.5, "y": -8.2, "z": 240.0 },
  { "zone": "West Ronfaure", "group": "cursed_chest", "x": -212.0, "y": -6.0, "z": 191.3 }
]
```

| field | required | meaning |
|---|---|---|
| `zone` | yes | zone name (`"West Ronfaure"`, case insensitive) or numeric id (`100`) |
| `x`, `y`, `z` | yes | raw FFXI coordinates, see below |
| `group` | no | one PNG per group, and the filename stem. Defaults to the zone id |
| `kind` | no | appended to the image title: `West Ronfaure - Cursed Chest` |

Writes `<out>/<group>.png` and prints each path. Roughly 15 seconds for one zone, most of it
loading and decompressing the mesh, so points in the same zone are cheapest batched into one
call.

Options: `--repo` for the checkout (else `$XI_VISUALIZER`, else the current dir or a sibling
`xi-visualizer`; anywhere else it clones one),
`--scale` for pixel ratio (default 2), `--dry-run` to validate and resolve zone names without
starting a browser.

## Coordinates go in raw, unconverted

Use the coordinates exactly as the game reports them. Do not flip anything. The renderer's
scene carries the y/z flip on its own scale, so a point handed in raw lands where it belongs.

Remember that FFXI `y` is height and **increases downward**, so a negative `y` is above
ground. This trips people up in both directions: it is not an error to see negative heights,
and it is an error to negate them on the way in.

If markers come out mirrored through the middle of the map, something flipped them twice.

## What it cannot do yet

Both of these are properties of the underlying renderer, not this skill. Say so plainly rather
than working around them silently:

- **One colour for every marker.** Two categories of point need two calls and two images, split
  by `group`. There is no per-point colour or label.
- **Always the whole zone, always straight down.** No zoom to fit the points. A handful of
  points in a large zone is a mostly empty map with a few dots, which is correct but not always
  useful.

## First run

Nothing to set up by hand. `render.py` finds an xi-visualizer checkout, or clones one, fetches
the 150MB `ximeshes` submodule, and runs `pnpm install`, doing only the parts that are missing.
First run therefore takes a few minutes; later runs are about 15 seconds.

Point it at an existing checkout with `--repo`, or `$XI_VISUALIZER`, to skip the search. An
explicit `--repo` that is not a checkout is an error rather than a reason to clone elsewhere.

It needs `git` and `node` on PATH and will not install either: project dependencies are its
business, language runtimes on your machine are not. Both are checked up front, so a missing
one is named immediately rather than surfacing partway through setup. `pnpm` is not required
separately; if it is absent, node supplies it through corepack or `npx`.

## When it fails

`render.py` validates before starting a browser, so most mistakes come back immediately: an
unknown zone name, a zone id absent from the table, a missing or non-numeric coordinate, or a
`group` spanning two zones. That last one matters because only the first point's zone is
loaded, so the rest would be drawn silently onto the wrong map.

If it starts a browser and then hangs, the likely cause is the zone page no longer publishing
the `window.__zoneView` handle the renderer drives. Nothing else in that app reads it, so it is
easy to drop by accident. Check `scripts/README.md` in the visualizer.

The command surface belongs to the visualizer, not to this skill. If `node scripts/shot.mjs
points` has moved on, that README is the authority and this file is what needs updating.

```bash
python test_render.py   # no checkout or browser needed
```
