#!/usr/bin/env python3
"""Look up trusted FFXI reference values decoded straight from the retail client DATs.

  python resources.py install                  # download the latest release and index it
  python resources.py status                   # what is on disk, and from which release
  python resources.py get items 18             # exact record by dataset + lookup key
  python resources.py search items "Excalibur" # substring/word search within a dataset
  python resources.py item 18                  # convenience: item by id or name
  python resources.py spell "Cure"             # spell by index or name
  python resources.py ability 1                # ability by id or name
  python resources.py status Sleep             # status effect by id or name
  python resources.py keyitem 1                # key item by id or name
  python resources.py entity 1-16781313        # entity by zone-entity id or name
  python resources.py zone 100                 # zone by id or name
  python resources.py string 1 0               # message string by zone_id + string_id
  python resources.py event 1 100              # event by zone_id + event_id (byte_code + lua)

The data is a direct decode of the retail client resource DATs, not a wiki claim. That is the
whole point of this skill: values reported here are authoritative. The decompressed NDJSON is
the source of truth on disk; the SQLite index is derived and `index` rebuilds it without a
re-download.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator, Optional, Sequence

HERE = Path(__file__).parent
CORPUS = HERE / "corpus"
INDEX = CORPUS / "resources.db"
RELEASE_FILE = CORPUS / "release.json"
REPO = "ffxi-dev/retail-resources"
SITE = "https://res.sruon.dev"

# Per-dataset lookup key and searchable name field. `key` fields are joined with "-" to form
# the primary key; `name` is the field shown and indexed for search (None where a dataset has
# no meaningful display name). Datasets present in a release but absent here are indexed
# generically off `id`/`name`. Documented datasets not in the current release (modifiers,
# events_actors) are kept so they index correctly if a later release ships them.
DATASETS: dict[str, dict[str, object]] = {
    "items": {"key": ("id",), "name": "name"},
    "strings": {"key": ("zone_id", "string_id"), "name": "content"},
    "entities": {"key": ("zone_id", "entity_id"), "name": "name"},
    "events": {"key": ("zone_id", "event_id"), "name": None},
    "events_actors": {"key": ("zone_id", "actor_id"), "name": "actor_name"},
    "abilities": {"key": ("id",), "name": "name"},
    "spells": {"key": ("index",), "name": "name"},
    "statuses": {"key": ("id",), "name": "name"},
    "keyitems": {"key": ("id",), "name": "name"},
    "merits": {"key": ("id",), "name": "name"},
    "modifiers": {"key": ("id",), "name": "name"},
    "augments": {"key": ("id",), "name": "text"},
    "monster_families": {"key": ("id",), "name": "name"},
    "pankration": {"key": ("id",), "name": "name"},
    "zones": {"key": ("id",), "name": "name"},
    "autotranslate": {"key": ("key",), "name": "text"},
    "zone_layout": {"key": ("zone_id", "idx"), "name": "id_str"},
}

# datasets that have a human-facing page on res.sruon.dev; the pk is the path segment.
LINK_ROUTES = {
    "items": "items",
    "keyitems": "keyitems",
    "spells": "spells",
    "abilities": "abilities",
    "statuses": "statuses",
    "zones": "zones",
    "entities": "entities",
    "strings": "strings",
    "events": "events",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    dataset TEXT NOT NULL,
    pk TEXT NOT NULL,
    name TEXT,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_pk ON records(dataset, pk);
CREATE INDEX IF NOT EXISTS records_name ON records(dataset, name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE VIRTUAL TABLE IF NOT EXISTS records_fts
    USING fts5(name, content='records', content_rowid='id', tokenize='unicode61');
"""


class ResourceError(Exception):
    """Anything the caller can act on, reported without a stack trace."""


def dataset_of(filename: str) -> str:
    return Path(filename).name.split(".")[0]


def read_ndjson(path: Path) -> Iterator[dict[str, object]]:
    """Iterate an NDJSON file. Uses the handle, not splitlines(), which also breaks on
    \\x85 and \\u2028 and both occur inside the decoded game text."""
    with open(path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ResourceError(f"{path.name} line {number} is not valid JSON: {error}")


def primary_key(record: dict[str, object], fields: Sequence[str]) -> Optional[str]:
    parts = []
    for field in fields:
        if field not in record or record[field] is None:
            return None

        parts.append(str(record[field]))

    return "-".join(parts)


def display_name(record: dict[str, object], field: Optional[str]) -> Optional[str]:
    if field is None:
        return None

    value = record.get(field)
    if isinstance(value, dict):
        # items carry name as {english, japanese, ...}; index the English form
        english = value.get("english")
        return str(english) if english is not None else None

    return str(value) if value is not None else None


def strip_bulk(record: dict[str, object]) -> dict[str, object]:
    """Drop the base64 icon PNG; it is useless bulk for a text lookup."""
    if "icon" in record:
        trimmed = dict(record)
        trimmed.pop("icon")
        return trimmed

    return record


def build_index(corpus: Path, db_path: Path) -> dict[str, int]:
    """Build the SQLite index from whatever NDJSON is in `corpus`."""
    files = sorted(corpus.glob("*.ndjson"))
    if not files:
        raise ResourceError(f"no .ndjson files in {corpus}. Run `install` first.")

    db_path.unlink(missing_ok=True)
    connection = sqlite3.connect(db_path)
    connection.executescript(SCHEMA)
    counts: dict[str, int] = {}

    for path in files:
        dataset = dataset_of(path.name)
        config = DATASETS.get(dataset, {"key": ("id",), "name": "name"})
        key_fields = config["key"]
        name_field = config["name"]
        assert isinstance(key_fields, tuple)
        assert name_field is None or isinstance(name_field, str)

        rows = []
        for record in read_ndjson(path):
            pk = primary_key(record, key_fields)
            if pk is None:
                continue

            rows.append((
                dataset,
                pk,
                display_name(record, name_field),
                json.dumps(strip_bulk(record), ensure_ascii=False),
            ))

        if rows:
            connection.executemany(
                "INSERT INTO records(dataset, pk, name, body) VALUES (?,?,?,?)", rows)
        counts[dataset] = len(rows)

    connection.execute("INSERT INTO records_fts(records_fts) VALUES('rebuild')")

    if RELEASE_FILE.is_file() or (corpus / "release.json").is_file():
        source = RELEASE_FILE if RELEASE_FILE.is_file() else corpus / "release.json"
        tag = json.loads(source.read_text(encoding="utf-8")).get("tag", "unknown")
        connection.execute("INSERT OR REPLACE INTO meta VALUES ('tag', ?)", (str(tag),))

    connection.commit()
    connection.close()
    return counts


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "ffxi-resources-skill"})
    with urllib.request.urlopen(request, timeout=300) as response:
        data: bytes = response.read()
    return data


def release_assets(tag: Optional[str]) -> tuple[str, dict[str, str]]:
    """Asset name -> download URL, over the public API. No gh CLI, no auth, no login."""
    path = f"tags/{tag}" if tag else "latest"
    try:
        payload = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases/{path}"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            which = f"release {tag}" if tag else "published release"
            raise ResourceError(f"no {which} on {REPO}.\n  https://github.com/{REPO}/releases")

        raise ResourceError(f"GitHub returned {error.code} for the release list")
    except urllib.error.URLError as error:
        raise ResourceError(f"could not reach GitHub: {error.reason}")

    return payload["tag_name"], {a["name"]: a["browser_download_url"] for a in payload["assets"]}


def install(corpus: Path, tag: Optional[str]) -> None:
    corpus.mkdir(parents=True, exist_ok=True)
    version, assets = release_assets(tag)
    print(f"resources release {version}", file=sys.stderr)

    archives = sorted(name for name in assets if name.endswith(".ndjson.gz"))
    if not archives:
        raise ResourceError("release has no .ndjson.gz assets")

    RELEASE_FILE.write_text(json.dumps({"tag": version}, indent=2), encoding="utf-8")

    for name in archives:
        target = corpus / name[: -len(".gz")]
        print(f"  {name}", file=sys.stderr)
        blob = fetch(assets[name])
        with gzip.open(io.BytesIO(blob), "rb") as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)

    counts = build_index(corpus, INDEX)
    total = sum(counts.values())
    print(f"indexed {total:,} records across {len(counts)} datasets -> {INDEX}")


def connect() -> sqlite3.Connection:
    if not INDEX.is_file():
        raise ResourceError(f"no index at {INDEX}. Run `python resources.py install` first.")

    connection = sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def tag_of(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT value FROM meta WHERE key='tag'").fetchone()
    return str(row["value"]) if row else "unknown"


def link_for(dataset: str, pk: str, tag: str) -> Optional[str]:
    route = LINK_ROUTES.get(dataset)
    if route is None:
        return None

    return f"{SITE}/v/{tag}/{route}/{pk}"


def show(rows: Sequence[sqlite3.Row], tag: str) -> None:
    if not rows:
        print("no match")
        return

    for row in rows:
        dataset = str(row["dataset"])
        pk = str(row["pk"])
        name = row["name"]
        header = f"\n=== {dataset} {pk}"
        if name:
            header += f"  {name}"
        print(header)
        print("    client-extracted from the retail FFXI DATs (trusted, direct decode)")

        body = json.loads(row["body"])
        if dataset == "events":
            print(f"    byte_code: {body.get('byte_code')}")
            print(f"    lua: {body.get('lua')}")

        link = link_for(dataset, pk, tag)
        if link:
            print(f"    {link}")

        print(indent(json.dumps(body, ensure_ascii=False, indent=2)))


def indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def get_rows(connection: sqlite3.Connection, dataset: str, pk: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM records WHERE dataset = ? AND pk = ?", (dataset, pk)).fetchall()


def search_rows(connection: sqlite3.Connection, dataset: str, text: str,
                limit: int) -> list[sqlite3.Row]:
    """Word/prefix search via FTS, then a substring fallback so partial words still hit."""
    rows = connection.execute(
        "SELECT r.* FROM records_fts f JOIN records r ON r.id = f.rowid"
        " WHERE records_fts MATCH ? AND r.dataset = ? LIMIT ?",
        (f'"{text}"*', dataset, limit)).fetchall()
    if rows:
        return rows

    return connection.execute(
        "SELECT * FROM records WHERE dataset = ? AND name LIKE ? COLLATE NOCASE"
        " ORDER BY length(name) LIMIT ?", (dataset, f"%{text}%", limit)).fetchall()


def cmd_get(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.dataset not in DATASETS:
        print(f"unknown dataset {args.dataset!r}. Known: {', '.join(sorted(DATASETS))}")
        return 1

    rows = get_rows(connection, args.dataset, args.id)
    show(rows, tag_of(connection))
    return 0 if rows else 1


def cmd_search(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.dataset not in DATASETS:
        print(f"unknown dataset {args.dataset!r}. Known: {', '.join(sorted(DATASETS))}")
        return 1

    rows = search_rows(connection, args.dataset, args.query, args.limit)
    show(rows, tag_of(connection))
    return 0 if rows else 1


def lookup(connection: sqlite3.Connection, dataset: str, arg: str, limit: int) -> int:
    """id-or-name convenience: try the arg as a primary key first (a plain id or a composite
    like `1-16781313`), and fall back to a name search when nothing keys on it."""
    rows = get_rows(connection, dataset, arg)
    if not rows:
        rows = search_rows(connection, dataset, arg, limit)

    show(rows, tag_of(connection))
    return 0 if rows else 1


def cmd_convenience(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    dataset = {"item": "items", "spell": "spells", "ability": "abilities",
               "status": "statuses", "keyitem": "keyitems", "entity": "entities",
               "zone": "zones"}[str(args.command)]
    return lookup(connection, dataset, args.query, args.limit)


def cmd_string(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows = get_rows(connection, "strings", f"{args.zone_id}-{args.string_id}")
    show(rows, tag_of(connection))
    return 0 if rows else 1


def cmd_event(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows = get_rows(connection, "events", f"{args.zone_id}-{args.event_id}")
    show(rows, tag_of(connection))
    return 0 if rows else 1


def cmd_status_report(_: object, __: object) -> int:
    if not INDEX.is_file():
        print("no corpus. Run: python resources.py install")
        return 1

    connection = connect()
    try:
        print(f"index:    {INDEX}  ({INDEX.stat().st_size // 1048576} MB)")
        print(f"release:  {tag_of(connection)}")
        for row in connection.execute(
                "SELECT dataset, COUNT(*) n FROM records GROUP BY dataset ORDER BY dataset"):
            print(f"  {str(row['dataset']):18} {row['n']:>9,} records")
    finally:
        connection.close()

    return 0


def main() -> int:
    # The data is largely Japanese and game text; Windows consoles default to cp1252 and crash.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    # `status` with no argument reports the corpus; `status <id|name>` is a status-effect lookup.
    reporter = sub.add_parser("status")
    reporter.add_argument("query", nargs="?")
    reporter.add_argument("--limit", type=int, default=20)
    installer = sub.add_parser("install")
    installer.add_argument("--tag", help="release tag, default latest")
    indexer = sub.add_parser("index", help="rebuild the index from NDJSON already on disk")
    indexer.add_argument("--dir", type=Path, default=CORPUS)

    getter = sub.add_parser("get")
    getter.add_argument("dataset")
    getter.add_argument("id")

    searcher = sub.add_parser("search")
    searcher.add_argument("dataset")
    searcher.add_argument("query")
    searcher.add_argument("--limit", type=int, default=20)

    for name in ("item", "spell", "ability", "keyitem", "entity", "zone"):
        node = sub.add_parser(name)
        node.add_argument("query")
        node.add_argument("--limit", type=int, default=20)

    stringer = sub.add_parser("string")
    stringer.add_argument("zone_id")
    stringer.add_argument("string_id")

    eventer = sub.add_parser("event")
    eventer.add_argument("zone_id")
    eventer.add_argument("event_id")

    args = parser.parse_args()

    try:
        if args.command == "status" and args.query is None:
            return cmd_status_report(None, None)

        if args.command == "install":
            install(CORPUS, args.tag)
            return 0

        if args.command == "index":
            counts = build_index(args.dir, args.dir / "resources.db" if args.dir != CORPUS else INDEX)
            print(f"indexed {sum(counts.values()):,} records across {len(counts)} datasets")
            return 0

        connection = connect()
        try:
            if args.command == "get":
                return cmd_get(connection, args)

            if args.command == "search":
                return cmd_search(connection, args)

            if args.command == "string":
                return cmd_string(connection, args)

            if args.command == "event":
                return cmd_event(connection, args)

            return cmd_convenience(connection, args)
        finally:
            connection.close()
    except ResourceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
