#!/usr/bin/env python3
"""Render points on an FFXI zone map, via the xi-visualizer headless renderer.

  python render.py --points spawns.json --out shots/
  python render.py --points spawns.json --out shots/ --repo /path/to/xi-visualizer

Input is a JSON list of {zone, group?, kind?, x, y, z}. `zone` may be a numeric zone id
or a zone name ("West Ronfaure"); names are resolved against the visualizer's own
zones.json so the two can never disagree.

Everything is checked before the browser starts. A bad zone id is otherwise a 120 second
wait for a mesh that will never load, which reads as a hang rather than a mistake.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REQUIRED_COORDS = ("x", "y", "z")

REPO_URL = "https://github.com/sruon/xi-visualizer.git"

SEARCH_PATHS = (
    "xi-visualizer",
    "../xi-visualizer",
    "~/Documents/GitHub/xi-visualizer",
    "~/src/xi-visualizer",
)


class RenderError(Exception):
    """Anything the caller can fix, reported without a stack trace."""


def find_repo(explicit: str | None) -> Path:
    """Locate a checkout, cloning one only when the caller did not name a path.

    An explicit --repo that is wrong is a mistake to report, never a reason to go and
    clone somewhere else behind the caller's back.
    """
    if explicit:
        root = Path(explicit).expanduser()
        if not (root / "scripts" / "shot.mjs").is_file():
            raise RenderError(f"{root} is not an xi-visualizer checkout (no scripts/shot.mjs)")

        return root.resolve()

    candidates = list(SEARCH_PATHS)
    if os.environ.get("XI_VISUALIZER"):
        candidates.insert(0, os.environ["XI_VISUALIZER"])

    for candidate in candidates:
        root = Path(candidate).expanduser()
        if (root / "scripts" / "shot.mjs").is_file():
            return root.resolve()

    return clone(Path(SEARCH_PATHS[2]).expanduser())


# project-local setup is ours to do; language runtimes are not. Installing node or git on
# someone's machine unasked is not a thing a skill should decide to do.
RUNTIMES = {
    "git": "https://git-scm.com/downloads",
    "node": "https://nodejs.org (v24 or newer)",
}


def preflight() -> None:
    """Report every missing runtime at once, not one per failed run."""
    missing = [f"  {name}: {where}" for name, where in RUNTIMES.items() if not shutil.which(name)]
    if missing:
        listed = "\n".join(missing)
        raise RenderError(f"missing required tools, install these first:\n{listed}")


def pnpm_command() -> list[str]:
    """pnpm if installed, else let node provide it rather than making that the user's problem."""
    if shutil.which("pnpm"):
        return ["pnpm"]

    if shutil.which("corepack"):
        return ["corepack", "pnpm"]

    return ["npx", "--yes", "pnpm"]


def run(command: list[str], cwd: Path | None = None, what: str = "") -> None:
    print(f"  {' '.join(command)}", file=sys.stderr)
    try:
        result = subprocess.run(command, cwd=cwd)
    except FileNotFoundError:
        raise RenderError(f"{command[0]} is not installed, and {what or 'setup'} needs it")

    if result.returncode != 0:
        raise RenderError(f"{what or ' '.join(command[:2])} failed (exit {result.returncode})")


def clone(dest: Path) -> Path:
    """No checkout anywhere, so make one. Better than handing back instructions."""
    print(f"no xi-visualizer checkout found, cloning into {dest}", file=sys.stderr)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", REPO_URL, str(dest)], what="clone")
    return dest.resolve()


def missing_prerequisites(root: Path) -> list[str]:
    """What is not ready, without touching anything. Kept separate so it is testable."""
    missing = []
    if not any((root / "public" / "ximeshes").glob("*.ximesh")):
        missing.append("meshes")

    if not (root / "node_modules" / "puppeteer-core").is_dir():
        missing.append("deps")

    return missing


def check_prerequisites(root: Path) -> None:
    """Bring the checkout up to a state that can render, rather than reporting on it."""
    missing = missing_prerequisites(root)

    if "meshes" in missing:
        print("zone meshes missing, fetching the submodule (150MB, one time)", file=sys.stderr)
        run(["git", "submodule", "update", "--init", "public/ximeshes"], cwd=root,
            what="submodule fetch")

    if "deps" in missing:
        print("dependencies missing, installing", file=sys.stderr)
        run([*pnpm_command(), "install"], cwd=root, what="pnpm install")

    still = missing_prerequisites(root)
    if still:
        raise RenderError(f"setup ran but {root} still lacks: {', '.join(still)}")


def load_zones(root: Path) -> dict[str, int]:
    """Zone name (lowercased) -> id, from the visualizer's own table."""
    table = root / "src" / "data" / "zones.json"
    if not table.is_file():
        raise RenderError(f"zone table missing at {table}")

    with open(table, "r", encoding="utf-8") as handle:
        return {z["name"].lower(): z["id"] for z in json.load(handle)}


def resolve(points: list[dict[str, object]], zones: dict[str, int]) -> list[dict[str, object]]:
    """Validate every record and turn any zone name into an id."""
    if not isinstance(points, list) or not points:
        raise RenderError("points must be a non-empty JSON list")

    ids = set(zones.values())
    resolved: list[dict[str, object]] = []

    for index, point in enumerate(points):
        if not isinstance(point, dict):
            raise RenderError(f"point {index} is not an object")

        missing = [k for k in REQUIRED_COORDS if not isinstance(point.get(k), (int, float))]
        if missing:
            raise RenderError(f"point {index} has no numeric {', '.join(missing)}")

        zone = point.get("zone")
        if isinstance(zone, str):
            if zone.lower() not in zones:
                raise RenderError(f"point {index}: unknown zone name {zone!r}")

            zone = zones[zone.lower()]
        elif isinstance(zone, int):
            if zone not in ids:
                raise RenderError(f"point {index}: zone id {zone} is not in the zone table")
        else:
            raise RenderError(f"point {index}: zone must be a name or a numeric id")

        resolved.append({**point, "zone": zone})

    groups = {str(p.get("group") or p["zone"]) for p in resolved}
    for group in groups:
        in_group = {str(p["zone"]) for p in resolved if str(p.get("group") or p["zone"]) == group}
        if len(in_group) > 1:
            raise RenderError(
                f"group {group!r} spans zones {', '.join(sorted(in_group))}. Only the first\n"
                "point's zone is loaded, so the rest would be drawn on the wrong map. Split it."
            )

    return resolved


def render(root: Path, points: list[dict[str, object]], out: Path, scale: int) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(points, handle)
        handle.close()

        command = ["node", "scripts/shot.mjs", "points", handle.name, str(out.resolve()), str(scale)]
        print(f"  {' '.join(command)}  (cwd {root})", file=sys.stderr)
        result = subprocess.run(command, cwd=root)
        if result.returncode != 0:
            raise RenderError(
                f"shot.mjs exited {result.returncode}. If it hung first, the zone page may no\n"
                "longer publish window.__zoneView; see scripts/README.md in the visualizer."
            )
    finally:
        os.unlink(handle.name)

    return sorted(out.glob("*.png"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", required=True, help="JSON file of point records, or - for stdin")
    parser.add_argument("--out", required=True, type=Path, help="directory to write PNGs into")
    parser.add_argument("--repo", help="xi-visualizer checkout (else $XI_VISUALIZER, else searched)")
    parser.add_argument("--scale", type=int, default=2, help="device pixel ratio, default 2")
    parser.add_argument("--dry-run", action="store_true", help="validate and resolve, render nothing")
    args = parser.parse_args()

    try:
        if not args.dry_run:
            preflight()

        root = find_repo(args.repo)
        if not args.dry_run:
            check_prerequisites(root)

        zones = load_zones(root)

        raw = sys.stdin.read() if args.points == "-" else Path(args.points).read_text(encoding="utf-8")
        points = resolve(json.loads(raw), zones)

        if args.dry_run:
            print(json.dumps(points, indent=2))
            return 0

        written = render(root, points, args.out, args.scale)
    except RenderError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"error: points file is not valid JSON: {error}", file=sys.stderr)
        return 1

    if not written:
        print("error: shot.mjs wrote no PNGs", file=sys.stderr)
        return 1

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
