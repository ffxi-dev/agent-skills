#!/usr/bin/env python3
"""Build the searchable patch note corpus from the ffxiupdates archive.

  python build.py              # download the archive if absent, then render notes/
  python build.py --refresh    # re-download first, for a monthly update
  python build.py --source D   # render from a local ffxiupdates clone instead

Upstream (github.com/Frankie-hz/ffxiupdates, MIT) already enumerates every official
news id and crawls both the EN and JA version update subforums, so this only filters
its records and renders them to one plain text file per update per language. Grepping
6000 single-line JSON records full of HTML is miserable; a file per update makes the
date and language of every hit free.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).parent
ARCHIVE = HERE / "raw" / "all.jsonl"
OUT = HERE / "notes"

ARCHIVE_URL = "https://raw.githubusercontent.com/Frankie-hz/ffxiupdates/master/data/all.jsonl"

# upstream categories that carry version update content, out of ~9. The rest is
# login server status and maintenance notices, which bury real hits.
WANTED = {"Version Update", "Update Details", "Updates"}

SKIP_TAGS = {"script", "style", "head", "noscript", "select", "textarea"}
BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "table", "ul", "ol", "blockquote", "hr"}
VOID_TAGS = {"br", "img", "hr", "meta", "link", "input"}


class Extractor(HTMLParser):
    """Flatten HTML to readable text, dropping script/style/head content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.out.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(data)

    def text(self) -> str:
        joined = "".join(self.out)
        # \r has to go in this pass: the legacy pages are CRLF, and a surviving \r sits
        # between the newlines and stops the blank-line collapse below from matching
        joined = re.sub(r"[ \t\r\xa0]+", " ", joined)
        joined = re.sub(r" ?\n ?", "\n", joined)
        return re.sub(r"\n{3,}", "\n\n", joined).strip()


def to_text(markup: str) -> str:
    parser = Extractor()
    parser.feed(markup)
    parser.close()
    return parser.text()


def slugify(title: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    # JA titles slugify to nothing useful, so fall back to the upstream record id
    return slug if len(re.sub(r"[-0-9]", "", slug)) >= 3 else fallback


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response:
        dest.write_bytes(response.read())
    print(f"  {dest.stat().st_size // 1024 // 1024} MB -> {dest}")


def load(path: Path) -> list[dict[str, object]]:
    """Read JSONL. Iterate the handle rather than splitlines(), which also breaks on
    \\x85 and \\u2028 and those occur inside the archived HTML."""
    records: list[dict[str, object]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def render(record: dict[str, object]) -> str:
    body = to_text(str(record.get("body") or ""))

    translation = record.get("translation")
    if isinstance(translation, dict):
        translated = to_text(str(translation.get("body") or ""))
        if translated:
            body += (
                "\n\n--- machine translation (not official, from the upstream archive) ---\n\n"
                + translated
            )

    return (
        f"# {record.get('title')}\n"
        f"# date: {record.get('date')}\n"
        f"# lang: {record.get('lang')}\n"
        f"# category: {record.get('category')}\n"
        f"# source: {record.get('url')}\n\n"
        f"{body}\n"
    )


def build(records: list[dict[str, object]], out: Path) -> list[tuple[str, str, str, str]]:
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.iterdir():
        stale.unlink()

    index: list[tuple[str, str, str, str]] = []
    for record in records:
        if record.get("category") not in WANTED:
            continue

        date = str(record.get("date") or "")[:10] or "0000-00-00"
        lang = str(record.get("lang") or "en")
        title = str(record.get("title") or "")
        slug = slugify(title, str(record.get("id") or "untitled"))

        path = out / f"{date}-{lang}-{slug}.txt"
        suffix = 2
        while path.exists():
            path = out / f"{date}-{lang}-{slug}-{suffix}.txt"
            suffix += 1

        path.write_text(render(record), encoding="utf-8")
        index.append((date, lang, title, path.name))

    index.sort()
    dated = [d for d, _, _, _ in index if d != "0000-00-00"]
    (out / "INDEX.md").write_text(
        f"{len(index)} notes, oldest {dated[0]}, newest {dated[-1]}\n\n"
        "| date | lang | title | file |\n|---|---|---|---|\n"
        + "".join(f"| {d} | {l} | {t} | {f} |\n" for d, l, t, f in index),
        encoding="utf-8",
    )
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-download the archive")
    parser.add_argument("--source", type=Path, help="local ffxiupdates clone to read instead")
    args = parser.parse_args()

    if args.source:
        archive = args.source / "data" / "all.jsonl" if args.source.is_dir() else args.source
        if not archive.is_file():
            print(f"no all.jsonl under {args.source}", file=sys.stderr)
            return 1
    else:
        archive = ARCHIVE
        if args.refresh or not archive.is_file():
            download(ARCHIVE_URL, archive)

    records = load(archive)
    index = build(records, OUT)

    langs: dict[str, int] = {}
    for _, lang, _, _ in index:
        langs[lang] = langs.get(lang, 0) + 1

    kept = ", ".join(f"{k}:{v}" for k, v in sorted(langs.items()))
    print(f"{len(index)} of {len(records)} records -> {OUT}  ({kept})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
