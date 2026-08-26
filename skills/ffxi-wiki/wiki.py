#!/usr/bin/env python3
"""Query the FFXI wiki corpus: BG Wiki, FFXIclopedia, and the Japanese FFO Wiki.

  python wiki.py install                 # download the latest release and index it
  python wiki.py status                  # which release is on disk
  python wiki.py title "Joyeuse"         # exact lookup, redirects resolved
  python wiki.py search "quipus"         # title substring
  python wiki.py body "Dead Aim"         # full text, with context
  python wiki.py category "Sword"        # pages in a category
  python wiki.py name "Dead Aim"         # JP <-> EN, via the FFO reading field

The JSONL stays the source of truth. The SQLite index is derived and can be rebuilt
with `index` without re-downloading anything.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

HERE = Path(__file__).parent
CORPUS = HERE / "corpus"
INDEX = CORPUS / "wiki.db"
REPO = "sruon/ffxi-wiki-dumps"

# FFO first: the JP community is closer to dev information and more rigorous about
# datamining. FFXIclopedia is a legacy Fandom wiki, much of it pre-Abyssea.
SOURCES = {
    "ffo-wiki": ("FFO Wiki (JP)", 1),
    "bg-wiki": ("BG Wiki", 2),
    "ffxiclopedia": ("FFXIclopedia", 3),
}

# a claim carrying one of these is flagged by the wiki itself, so never pass it through silently
QUALITY_MARKERS = (
    (re.compile(r"\{\{\s*verification", re.I), "flagged {{verification}}, unverified"),
    (re.compile(r"\{\{\s*verify", re.I), "flagged {{verify}}, unverified"),
    (re.compile(r"\{\{\s*question", re.I), "flagged {{Question}}, value unknown"),
)
INCOMPLETE_CATEGORIES = ("information needed", "verification")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    rank INTEGER NOT NULL,
    title TEXT NOT NULL,
    pageid INTEGER,
    url TEXT,
    reading TEXT,
    categories TEXT,
    body TEXT
);
CREATE INDEX IF NOT EXISTS pages_title ON pages(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS pages_reading ON pages(reading COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS redirects (
    source TEXT NOT NULL,
    from_title TEXT NOT NULL,
    to_title TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS redirects_from ON redirects(from_title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts
    USING fts5(title, body, content='pages', content_rowid='id', tokenize='unicode61');
"""


class WikiError(Exception):
    """Anything the caller can act on, reported without a stack trace."""


def source_of(filename: str) -> str:
    stem = Path(filename).name.split(".")[0]
    return stem.replace("-categories", "").replace("-redirects", "")


def read_jsonl(path: Path) -> Iterator[dict[str, object]]:
    """Iterate a JSONL file. Uses the handle, not splitlines(), which also breaks on
    \\x85 and \\u2028 and both occur inside scraped wiki bodies."""
    with open(path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise WikiError(f"{path.name} line {number} is not valid JSON: {error}")


def build_index(corpus: Path, db_path: Path) -> dict[str, int]:
    """Build the SQLite index from whatever JSONL is in `corpus`."""
    files = sorted(corpus.glob("*.jsonl"))
    if not files:
        raise WikiError(f"no .jsonl files in {corpus}. Run `install` first.")

    db_path.unlink(missing_ok=True)
    connection = sqlite3.connect(db_path)
    connection.executescript(SCHEMA)
    counts: dict[str, int] = {}

    for path in files:
        source = source_of(path.name)
        if source not in SOURCES:
            continue

        rank = SOURCES[source][1]
        rows = []
        redirects = []

        for record in read_jsonl(path):
            if "from" in record and "to" in record:
                redirects.append((source, record["from"], record["to"]))
                continue

            # MediaWiki entries carry `wikitext`; FFO carries `text`. Nothing carries both.
            body = record.get("wikitext") or record.get("text") or ""
            rows.append((
                source,
                rank,
                record.get("title", ""),
                record.get("pageid"),
                record.get("url"),
                record.get("reading"),
                json.dumps(record.get("categories") or [], ensure_ascii=False),
                body,
            ))

        if rows:
            connection.executemany(
                "INSERT INTO pages(source, rank, title, pageid, url, reading, categories, body)"
                " VALUES (?,?,?,?,?,?,?,?)", rows)
        if redirects:
            connection.executemany(
                "INSERT INTO redirects(source, from_title, to_title) VALUES (?,?,?)", redirects)

        counts[path.name] = len(rows) or len(redirects)

    connection.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
    manifest = corpus / "manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        connection.execute("INSERT OR REPLACE INTO meta VALUES ('generated', ?)",
                           (data.get("generated", "unknown"),))

    connection.commit()
    connection.close()
    return counts


def verify(path: Path, expected: str) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise WikiError(f"{path.name} failed its checksum. Re-download it.\n"
                        f"  expected {expected}\n  got      {digest}")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "ffxi-wiki-skill"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data: bytes = response.read()
    return data


def release_assets(tag: str | None) -> tuple[str, dict[str, str]]:
    """Asset name -> download URL, over the public API. No gh CLI, no auth, no login."""
    path = f"tags/{tag}" if tag else "latest"
    try:
        payload = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases/{path}"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            which = f"release {tag}" if tag else "published release"
            raise WikiError(
                f"no {which} on {REPO}.\n  https://github.com/{REPO}/releases")

        raise WikiError(f"GitHub returned {error.code} for the release list")
    except urllib.error.URLError as error:
        raise WikiError(f"could not reach GitHub: {error.reason}")

    return payload["tag_name"], {a["name"]: a["browser_download_url"] for a in payload["assets"]}


def install(corpus: Path, tag: str | None) -> None:
    corpus.mkdir(parents=True, exist_ok=True)
    version, assets = release_assets(tag)
    print(f"corpus release {version}", file=sys.stderr)

    if "manifest.json" not in assets:
        raise WikiError("release has no manifest.json, so nothing can be checksummed")

    manifest = json.loads(fetch(assets["manifest.json"]))
    (corpus / "manifest.json").write_bytes(json.dumps(manifest, indent=2).encode())

    for entry in manifest["files"]:
        name = entry["name"]
        if name not in assets:
            raise WikiError(f"{name} is in the manifest but not in the release")

        archive = corpus / name
        print(f"  {name} ({entry['bytes'] / 1048576:.0f} MB)", file=sys.stderr)
        archive.write_bytes(fetch(assets[name]))
        verify(archive, entry["sha256"])

        with gzip.open(archive, "rb") as src, open(archive.with_suffix(""), "wb") as dst:
            shutil.copyfileobj(src, dst)

        archive.unlink()
        print(f"    {entry['lines']:,} lines, checksum ok", file=sys.stderr)

    counts = build_index(corpus, INDEX)
    print(f"indexed {sum(counts.values()):,} records from {len(counts)} files -> {INDEX}")


def connect() -> sqlite3.Connection:
    if not INDEX.is_file():
        raise WikiError(f"no index at {INDEX}. Run `python wiki.py install` first.")

    connection = sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def flags_for(body: str, categories: str) -> list[str]:
    found = [note for pattern, note in QUALITY_MARKERS if pattern.search(body or "")]
    lowered = (categories or "").lower()
    if any(marker in lowered for marker in INCOMPLETE_CATEGORIES):
        found.append("category marks the page incomplete")
    return found


def show(rows: list[sqlite3.Row], snippet_for: str | None = None) -> None:
    if not rows:
        print("no match in any of the three wikis")
        return

    for row in rows:
        label = SOURCES[row["source"]][0]
        print(f"\n=== {row['title']}  [{label}]")
        print(f"    {row['url']}")
        if row["reading"]:
            print(f"    reading: {row['reading']}")

        categories = json.loads(row["categories"] or "[]")
        if categories:
            print(f"    categories: {', '.join(categories[:8])}")

        for flag in flags_for(row["body"], row["categories"]):
            print(f"    ! {flag}")

        if snippet_for:
            for line in context(row["body"], snippet_for):
                print(f"    | {line}")


def context(body: str, needle: str, width: int = 160) -> list[str]:
    out = []
    for match in re.finditer(re.escape(needle), body or "", re.I):
        start = max(0, match.start() - width // 2)
        out.append(re.sub(r"\s+", " ", body[start:start + width]).strip())
        if len(out) >= 3:
            break

    return out


def resolve_redirect(connection: sqlite3.Connection, title: str) -> str:
    row = connection.execute(
        "SELECT to_title FROM redirects WHERE from_title = ? COLLATE NOCASE LIMIT 1",
        (title,)).fetchone()
    return row["to_title"] if row else title


def cmd_title(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    target = resolve_redirect(connection, args.query)
    if target.lower() != args.query.lower():
        print(f"'{args.query}' is a redirect to '{target}'")

    # Match the title, and also an FFO page whose reading carries this English name, since FFO
    # pages are titled in Japanese so an English title alone never finds them.
    sql = ("SELECT * FROM pages WHERE (title = ? COLLATE NOCASE"
           " OR (source = 'ffo-wiki' AND reading LIKE ? COLLATE NOCASE))")
    params: list[object] = [target, f"%/{target}"]
    if args.source:
        sql += " AND source = ?"
        params.append(args.source)

    rows = connection.execute(sql + " ORDER BY rank", params).fetchall()
    show(rows)
    report_coverage(rows)
    return 0 if rows else 1


def cmd_search(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows = connection.execute(
        "SELECT * FROM pages WHERE title LIKE ? COLLATE NOCASE ORDER BY rank, length(title)"
        " LIMIT ?", (f"%{args.query}%", args.limit)).fetchall()
    for row in rows:
        print(f"{SOURCES[row['source']][0]:16} {row['title']}")

    if not rows:
        print("no title matched")
    return 0 if rows else 1


def cmd_body(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows = connection.execute(
        "SELECT p.* FROM pages_fts f JOIN pages p ON p.id = f.rowid"
        " WHERE pages_fts MATCH ? ORDER BY p.rank, bm25(pages_fts) LIMIT ?",
        (args.query, args.limit)).fetchall()
    show(rows, snippet_for=args.query.split()[0] if args.query else None)
    return 0 if rows else 1


def cmd_category(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    # article `categories` omit the prefix that Category: page titles keep
    wanted = args.query.removeprefix("Category:")
    rows = connection.execute(
        "SELECT * FROM pages WHERE categories LIKE ? ORDER BY rank, title LIMIT ?",
        (f'%"{wanted}"%', args.limit)).fetchall()
    for row in rows:
        print(f"{SOURCES[row['source']][0]:16} {row['title']}")

    if not rows:
        print(f"no page lists category {wanted!r}")
    return 0 if rows else 1


def cmd_name(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    """JP <-> EN through the FFO reading field, `kana/English name`."""
    rows = connection.execute(
        "SELECT * FROM pages WHERE source = 'ffo-wiki' AND ("
        " reading LIKE ? COLLATE NOCASE OR title LIKE ? COLLATE NOCASE) LIMIT ?",
        (f"%{args.query}%", f"%{args.query}%", args.limit)).fetchall()

    if not rows:
        print(f"no FFO page whose title or reading contains {args.query!r}."
              "\nNot every page carries the English half of `reading`.")
        return 1

    for row in rows:
        print(f"{row['title']}   {row['reading'] or '(no reading)'}\n    {row['url']}")
    return 0


def report_coverage(rows: list[sqlite3.Row]) -> None:
    """The trust hierarchy is only useful if the agent is told what it is working from."""
    if not rows:
        return

    present = {row["source"] for row in rows}
    print()
    if "ffo-wiki" in present and len(present) > 1:
        print("confidence: high, JP agrees with at least one other wiki (check the text)")
    elif present == {"ffo-wiki"}:
        print("confidence: JP only. Still preferred, but no corroboration.")
    else:
        names = ", ".join(sorted(SOURCES[s][0] for s in present))
        print(f"confidence: low, {names} only. No JP entry, so report it as such.")


def cmd_status(_: object, __: object) -> int:
    if not INDEX.is_file():
        print(f"no corpus. Run: python wiki.py install")
        return 1

    connection = connect()
    generated = connection.execute("SELECT value FROM meta WHERE key='generated'").fetchone()
    print(f"index:     {INDEX}  ({INDEX.stat().st_size // 1048576} MB)")
    print(f"release:   {generated['value'] if generated else 'unknown'}")
    for row in connection.execute(
            "SELECT source, COUNT(*) n FROM pages GROUP BY source ORDER BY rank"):
        print(f"  {SOURCES[row['source']][0]:16} {row['n']:>7,} pages")

    redirects = connection.execute("SELECT COUNT(*) n FROM redirects").fetchone()["n"]
    print(f"  redirects        {redirects:>7,}")
    return 0


def main() -> int:
    # The corpus is largely Japanese; Windows consoles default to cp1252 and crash on it.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    installer = sub.add_parser("install")
    installer.add_argument("--tag", help="release tag, default latest")
    indexer = sub.add_parser("index", help="rebuild the index from JSONL already on disk")
    indexer.add_argument("--dir", type=Path, default=CORPUS)

    for name in ("title", "search", "body", "category", "name"):
        node = sub.add_parser(name)
        node.add_argument("query")
        node.add_argument("--limit", type=int, default=20)
        if name == "title":
            node.add_argument("--source", choices=sorted(SOURCES))

    args = parser.parse_args()

    try:
        if args.command == "status":
            return cmd_status(None, None)

        if args.command == "install":
            install(CORPUS, args.tag)
            return 0

        if args.command == "index":
            counts = build_index(args.dir, args.dir / "wiki.db" if args.dir != CORPUS else INDEX)
            print(f"indexed {sum(counts.values()):,} records from {len(counts)} files")
            return 0

        handlers = {"title": cmd_title, "search": cmd_search, "body": cmd_body,
                    "category": cmd_category, "name": cmd_name}
        connection = connect()
        try:
            return handlers[args.command](connection, args)
        finally:
            connection.close()
    except WikiError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
