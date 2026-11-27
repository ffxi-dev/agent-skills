#!/usr/bin/env python3
"""Ask Scholar, and read any Mogsafe page's data.

  python scholar.py open URL               the data a mogsafe.sruon.dev, scholar.sruon.dev, or lens.sruon.dev page shows
  python scholar.py sql URL                the SQL behind that data, values filled in, for the MCP query tool
  python scholar.py download URL|ID [FILE] save a capture's .xicap
  python scholar.py named NAME [k=v ...]   one of the named queries the pages run
  python scholar.py tables [name] | versions | query "SQL"    (these need a key)

The key comes from SCHOLAR_API_KEY and is never printed.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Sequence, Tuple

URL = os.environ.get("SCHOLAR_URL", "https://scholar.sruon.dev")
MOGSAFE = os.environ.get("MOGSAFE_URL", "https://mogsafe.sruon.dev")
LENS = "https://lens.sruon.dev"
AGENT = "scholar-skill"
# The named queries' SQL: Scholar's own as it serves them, and the library's Explore pages from ffxi-dev/extractors.
LIBRARY = os.environ.get(
    "SCHOLAR_LIBRARY", "https://raw.githubusercontent.com/ffxi-dev/extractors/main/ffxi_extractors/sql/pages"
)
BLANK = re.compile(r"\{(\w+):(\w+)\}")
NO_KEY = "SCHOLAR_API_KEY is not set: make a key at https://scholar.sruon.dev/keys"

# One named query the page runs: its name, its parameters, and the columns a row must match to be the page's.
Step = Tuple[str, Dict[str, str], Dict[str, str]]


def key() -> str:
    return os.environ.get("SCHOLAR_API_KEY", "")


def fetch(url: str, body: str | None = None, auth: bool = False) -> Any:
    """GET (or POST body to) url and return its JSON. auth sends the key when there is one."""
    headers = {"User-Agent": AGENT}
    if auth and key():
        headers["Authorization"] = f"Bearer {key()}"
    req = urllib.request.Request(url, data=body.encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").strip()
        try:
            detail = json.loads(detail).get("error", detail)
        except (ValueError, AttributeError):
            pass
        hint = f" ({NO_KEY})" if e.code == 401 and not key() else ""
        raise SystemExit(f"{urllib.parse.urlsplit(url).netloc} answered {e.code}: {detail}{hint}") from None


def ask(path: str, body: str | None = None) -> Any:
    if not key():
        raise SystemExit(NO_KEY)
    return fetch(URL + path, body, auth=True)


def named(name: str, params: Dict[str, Any], keep: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """A named query's answer, its rows as objects; keep drops the rows the page would not show."""
    r = fetch(f"{URL}/v1/queries/{name}?{urllib.parse.urlencode(params)}", auth=True)
    rows = [dict(zip(r["columns"], row)) for row in r["rows"]]
    rows = [x for x in rows if all(str(x.get(k)) == str(v) for k, v in (keep or {}).items())]
    return {"query": name, "params": params, "rows": rows, "truncated": r.get("truncated", False)}


def text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return str(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{urllib.parse.urlsplit(url).netloc} answered {e.code} for {url}") from None


def literal(value: Any, kind: str = "") -> str:
    """value as a ClickHouse literal: a number when kind is not String and it is one, else a quoted string."""
    v = str(value)
    if kind != "String" and re.fullmatch(r"-?\d{1,19}", v):
        return v
    if kind not in ("", "String"):
        raise SystemExit(f"{v!r} is not a number")
    return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"


def step_sql(name: str, params: Dict[str, Any], keep: Dict[str, Any], own: Dict[str, str]) -> str:
    """A named query's SQL with the page's values in its {name:Type} blanks, cut to the rows the page shows."""
    sql = own[name] if name in own else text(f"{LIBRARY}/{name}.sql")
    missing = {k for k, _ in BLANK.findall(sql)} - params.keys()
    if missing:
        raise SystemExit(f"{name} needs {', '.join(sorted(missing))}")
    sql = BLANK.sub(lambda m: literal(params[m[1]], m[2]), sql).strip().rstrip(";")
    if keep:
        sql = f"SELECT * FROM ({sql}) WHERE " + " AND ".join(f"{k} = {literal(v)}" for k, v in keep.items())
    return f"-- {name} {json.dumps(params, ensure_ascii=False)}\n{sql}"


def sql_of(steps: Sequence[Step]) -> str:
    own = fetch(f"{URL}/static/queries.json")
    return "\n\n".join(step_sql(*s, own) for s in steps)


# Every Explore page and the named queries it runs, as Scholar's capture.js mounts it on Mogsafe.
MOB = ("bestiary_mob", "bestiary_geometry", "bestiary_evidence", "bestiary_names", "bestiary_steals",
       "bestiary_effects", "bestiary_events", "bestiary_exp", "bestiary_looks", "bestiary_animations",
       "bestiary_aggro", "bestiary_mp", "bestiary_gil")  # fmt: skip
EXPLORE: List[Tuple[str, Callable[[Dict[str, str]], Sequence[Step]]]] = [
    (r"/mobs", lambda m: [("bestiary_list", {}, {})]),
    (r"/mobs/(?P<zone>-?\d+)/(?P<name>[^/]+)", lambda m: [(q, {"zone": m["zone"], "name": m["name"]}, {}) for q in MOB]
     + [("zone_name", {"zone": m["zone"]}, {})]),
    (r"/moves", lambda m: [("tp_moves", {}, {})]),
    (r"/moves/(?P<move>\d+)", lambda m: [("tp_move", {"move": m["move"]}, {})]),
    (r"/wanted", lambda m: [("bestiary_wanted", {}, {})]),
    (r"/items", lambda m: [("items", {}, {})]),
    (r"/items/(?P<item>\d+)", lambda m: [("item_sources", {"item": m["item"]}, {})]),
    (r"/recipes", lambda m: [("recipe_catalog", {}, {})]),
    (r"/fish", lambda m: [("fishing_catalog", {}, {})]),
    (r"/weather", lambda m: [("weather_zones", {}, {}), ("weather_next", {}, {})]),
    (r"/weather/(?P<zone>-?\d+)", lambda m: [("weather_zone", {"zone": m["zone"]}, {})]),
    (r"/npcs", lambda m: [("npc_zones", {}, {})]),
    (r"/npcs/(?P<zone>-?\d+)", lambda m: [(q, {"zone": m["zone"]}, {}) for q in ("npc_zone", "npc_zone_trades", "npc_zone_shops")]),
    (r"/shops", lambda m: [("shop_npcs", {}, {})]),
    (r"/shops/(?P<zone>-?\d+)/(?P<name>[^/]+)", lambda m: [("shop_npcs", {}, {"zone": m["zone"], "npc_name": m["name"]}),
     ("npc_zone_shops", {"zone": m["zone"]}, {"npc_name": m["name"]})]),
    (r"/gaps", lambda m: [("gaps", {}, {}), ("gaps_load", {}, {})]),
]  # fmt: skip
# Pages only a person signed in to Mogsafe in a browser can read: Mogsafe takes no API key.
SIGNED_IN = ("/me", "/import", "/timeline/me", "/link", "/admin")


def explore(path: str) -> Sequence[Step] | None:
    for pattern, steps in EXPLORE:
        m = re.fullmatch(pattern, path)
        if m:
            return steps({k: urllib.parse.unquote(v) for k, v in m.groupdict().items()})
    return None


def capture(id: str, sql: bool = False) -> Any:
    """A capture's page: Mogsafe's record of it, and Scholar's analysis of its whole recording."""
    web = fetch(f"{MOGSAFE}/v1/web/captures/{urllib.parse.quote(id)}")
    if sql:  # the page column is one JSON string: each part's {"columns", "rows"}
        return sql_of([("page", {"id": web["analysis"]["id"]}, {})])
    recording, session = web["analysis"]["id"], web.get("session")
    stored = named("page", {"id": recording})["rows"]
    parts = json.loads(stored[0]["page"]) if stored else {}
    return {
        "mogsafe": web,
        "scholar": {k: [dict(zip(v["columns"], row)) for row in v["rows"]] for k, v in parts.items()},
        "scholar_note": "" if parts else "Scholar has not read this capture yet.",
        "session_range": [session["start_packet"], session["end_packet"]] if session else None,
        "download": f"{MOGSAFE}/c/{id}",
        "lens": lens(web),
    }


def lens(web: Dict[str, Any]) -> str:
    """Lens's link to a capture, at its /cap session when the id was a session's."""
    session = web.get("session")
    name = f"?session={urllib.parse.quote(session['name'])}" if session else ""
    return f"{LENS}/c/{web['analysis']['id']}{name}"


def utc_day(day: str) -> Tuple[int, int]:
    start = datetime.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    return int(start.timestamp() * 1000), int(start.timestamp() * 1000) + 86_400_000


def timeline(code: str, query: Dict[str, str]) -> Any:
    """A shared timeline's day, ?day=YYYY-MM-DD (UTC here; the page uses the viewer's zone), or its latest day."""
    base = f"{MOGSAFE}/v1/web/timeline/{urllib.parse.quote(code)}"
    who = {"character": query["character"]} if query.get("character") else {}
    day = query.get("day")
    if not day:
        latest = fetch(f"{base}?{urllib.parse.urlencode(who)}")["latest"]
        if not latest:
            return {"captures": [], "note": "No play on this timeline."}
        day = datetime.datetime.fromtimestamp(latest / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")
    start, end = utc_day(day)
    return {"day": day, **fetch(f"{base}?{urllib.parse.urlencode({**who, 'from': start, 'to': end})}")}


def search(query: Dict[str, str]) -> Any:
    """Mogsafe's /search, which asks Scholar's /v1/search; from and to are days there and Unix ms here."""
    if not key():
        raise SystemExit("Search needs a key: " + NO_KEY)
    q = {k: v for k, v in query.items() if k in ("kind", "q", "mob", "character", "offset")}
    if query.get("from"):
        q["from"] = str(utc_day(query["from"])[0])
    if query.get("to"):
        q["to"] = str(utc_day(query["to"])[1])
    return fetch(f"{URL}/v1/search?{urllib.parse.urlencode(q)}", auth=True)


def capture_id(target: str) -> str:
    """A capture or session id from a bare id or any link that names one."""
    path = urllib.parse.urlsplit(target).path if "/" in target else "/c/" + target
    m = re.fullmatch(r"/(?:c|captures)/([A-Za-z0-9_-]+)/?", path)
    if not m:
        raise SystemExit(f"no capture id in {target}")
    return m[1]


def open_url(url: str, sql: bool = False) -> Any:
    """The data the page at url shows; with sql, the SQL behind it instead."""
    parts = urllib.parse.urlsplit(url if "://" in url else "https://" + url)
    host, path = parts.netloc.lower(), parts.path.rstrip("/") or "/"
    query = dict(urllib.parse.parse_qsl(parts.query))
    if host == "lens.sruon.dev" or (host == "scholar.sruon.dev" and path.startswith("/captures/")):
        return capture(capture_id(path), sql)
    if host == "scholar.sruon.dev" and path.startswith("/v1/queries/"):
        name = path.rsplit("/", 1)[1]
        return sql_of([(name, query, {})]) if sql else named(name, query)
    if host != "mogsafe.sruon.dev":
        raise SystemExit(f"not a Mogsafe, Scholar, or Lens link: {url}")
    if path.startswith("/captures/") and not path.endswith("/timeline"):
        return capture(capture_id(path), sql)
    if sql and explore(path) is None:
        raise SystemExit(f"{path} is Mogsafe's own data or a search, not a named query: use open")
    if path in ("/", "/captures"):
        return fetch(f"{MOGSAFE}/v1/web/captures?{parts.query}")
    if re.fullmatch(r"/c/[^/]+", path):
        web = fetch(f"{MOGSAFE}/v1/web/captures/{urllib.parse.quote(capture_id(path))}")
        return {"download": f"{MOGSAFE}{path}", "lens": lens(web), "capture": web["capture"],
                "note": "Save it with: python scholar.py download " + url}  # fmt: skip
    m = re.fullmatch(r"/captures/([^/]+)/timeline", path)
    if m:  # redirects to the uploader's shared timeline, /t/<code>
        req = urllib.request.Request(f"{MOGSAFE}{path}", headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            path = urllib.parse.urlsplit(r.url).path
    m = re.fullmatch(r"/t/([^/]+)", path)
    if m:
        return timeline(m[1], query)
    if path == "/search":
        return search(query)
    if path in SIGNED_IN:
        raise SystemExit(f"{path} shows the signed-in person's own account; only their browser session reads it.")
    steps = explore(path)
    if steps is None:
        raise SystemExit(f"no data behind {url}: see the route table in SKILL.md")
    if sql:
        return sql_of(steps)
    note = "The page's ?q= filters these rows in the browser; filter them yourself." if query.get("q") else ""
    return {"page": url, "data": [named(*s) for s in steps], "note": note}


def download(target: str, dest: str | None) -> None:
    """Save a capture's file: /c/<id> redirects to a short-lived signed link, a session's id to its recording's."""
    id = capture_id(target)
    req = urllib.request.Request(f"{MOGSAFE}/c/{id}", headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            m = re.search(r'filename="([^"]+)"', r.headers.get("Content-Disposition", ""))
            path = dest or (m[1] if m else f"{id}.xicap")
            with open(path, "wb") as f:
                shutil.copyfileobj(r, f)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Mogsafe answered {e.code} for {id}: {e.read().decode('utf-8', 'replace').strip()}") from None
    link = lens(fetch(f"{MOGSAFE}/v1/web/captures/{urllib.parse.quote(id)}"))
    print(f"saved {path} ({os.path.getsize(path):,} bytes); a person opens it in Lens at {link}")


def table(columns: list[str], rows: list[list[Any]]) -> str:
    cells = [[("" if v is None else str(v)) for v in r] for r in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    line = " | ".join(c.ljust(w) for c, w in zip(columns, widths))
    rule = "-+-".join("-" * w for w in widths)
    body = [" | ".join(v.ljust(w) for v, w in zip(r, widths)) for r in cells]
    return "\n".join([line, rule, *body])


def main(argv: list[str]) -> int:
    commands = ("open", "sql", "download", "named", "tables", "versions", "query")
    if not argv or argv[0] not in commands or any(a.startswith("-") for a in argv[1:2] + argv[2:3]):
        print(__doc__)  # an option such as --help is no URL or file name
        return 2
    if argv[0] in ("open", "sql", "download", "named", "query") and len(argv) < 2:
        raise SystemExit(f"{argv[0]} needs an argument: see python scholar.py")
    if argv[0] == "open":
        print(json.dumps(open_url(argv[1]), ensure_ascii=False))
    elif argv[0] == "sql":
        print(open_url(argv[1], sql=True))
    elif argv[0] == "download":
        download(argv[1], argv[2] if len(argv) > 2 else None)
    elif argv[0] == "named":
        print(json.dumps(named(argv[1], dict(a.split("=", 1) for a in argv[2:])), ensure_ascii=False))
    elif argv[0] == "query":
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
