#!/usr/bin/env python3
"""Ask Scholar: python scholar.py tables [name] | versions | query "SQL".

The key comes from SCHOLAR_API_KEY and is never printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

URL = os.environ.get("SCHOLAR_URL", "https://scholar.sruon.dev")


def ask(path: str, body: str | None = None) -> Any:
    key = os.environ.get("SCHOLAR_API_KEY", "")
    if not key:
        raise SystemExit("SCHOLAR_API_KEY is not set: make a key at https://scholar.sruon.dev/keys")
    req = urllib.request.Request(
        URL + path,
        data=body.encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "User-Agent": "scholar-skill"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except ValueError:
            pass
        raise SystemExit(f"Scholar answered {e.code}: {detail}") from None


def table(columns: list[str], rows: list[list[Any]]) -> str:
    cells = [[("" if v is None else str(v)) for v in r] for r in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    line = " | ".join(c.ljust(w) for c, w in zip(columns, widths))
    rule = "-+-".join("-" * w for w in widths)
    body = [" | ".join(v.ljust(w) for v, w in zip(r, widths)) for r in cells]
    return "\n".join([line, rule, *body])


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("tables", "versions", "query"):
        print(__doc__)
        return 2
    if argv[0] == "query":
        if len(argv) < 2:
            raise SystemExit('give the SQL: python scholar.py query "SELECT ..."')
        r = ask("/v1/query", argv[1])
        print(table(r["columns"], r["rows"]))
        print(f"\n{len(r['rows'])} rows" + (" (cut at 10,000: narrow the query)" if r["truncated"] else ""))
    elif argv[0] == "versions":
        print(json.dumps(ask("/v1/versions"), indent=2))
    else:
        for t in ask("/v1/tables"):
            if len(argv) > 1 and t["name"] != argv[1]:
                continue
            print(f"{t['name']}: {t['doc']}")
            if len(argv) > 1 or t["unit"] not in (None, "decode") or t["name"] in ("packets", "captures"):
                for c in t["columns"]:
                    print(f"  {c['name']} {c['type']}: {c['doc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
