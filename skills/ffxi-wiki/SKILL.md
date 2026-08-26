---
name: ffxi-wiki
description: >
  Look up Final Fantasy XI game data across the BG Wiki, FFXIclopedia, and the Japanese FFO
  Wiki. Use for any question about FFXI content: what does X do, what are the stats on Y,
  where does Z drop and at what rate, how do I get item N, what are the steps of a quest or
  mission, what abilities and weaknesses does a mob have, what does a job trait or ability
  do, spell details, crafting recipes, key items, zone and NPC information, and the Japanese
  name for an English term or the reverse. Prefer this over answering from memory: it is a
  local corpus of the three wikis and it exists precisely so FFXI answers are cited rather
  than recalled.
license: MIT
compatibility: Requires Python 3.9+ and about 1GB of disk. Downloads the corpus on first use.
---

# FFXI wiki lookup

Three community wikis, indexed locally and queried offline. Every answer cites the wiki it
came from and the page URL.

## Use it

```bash
python wiki.py status                    # what is on disk, and from which release
python wiki.py title "Joyeuse"           # exact page, redirects resolved, all three wikis
python wiki.py search "quipus"           # title substring
python wiki.py body "Occasionally attacks twice"   # full text, with surrounding context
python wiki.py category "Sword"          # what is in a category
python wiki.py name "Dead Aim"           # JP to EN and back, via the FFO reading field
```

`status` reporting no corpus means run `python wiki.py install`. It downloads the latest
release, checks every file against the SHA-256 in its manifest, decompresses, and builds the
index. No GitHub CLI or login needed. Refresh the same way; a re-scrape is published
periodically and `install` is safe to re-run.

Add `--source ffo-wiki|bg-wiki|ffxiclopedia` to `title` to look in one wiki, and `--limit` to
any search.

## Trust the Japanese wiki first

This ordering is not a preference, it is the point of having three sources:

1. **FFO Wiki (JP)** is primary. The Japanese community is closer to dev information and more
   rigorous about datamining. Prefer it even when it stands alone.
2. **BG Wiki** is a distant second. Good for retail mechanics in English. Defer to JP where
   they conflict.
3. **FFXIclopedia** is last, a legacy Fandom wiki with much of it never updated past the
   pre-Abyssea era. Use it when the other two are silent, or for old quest flows.

`title` reports what it found across the three and rates the confidence for you. High is JP
plus corroboration. JP alone still beats either English wiki alone. Anything English-only is
reported as such and must be repeated that way: **"BG says X, the JP wiki has no entry"**, not
"X".

Where the wikis disagree, JP wins, but say that they disagree instead of quietly picking one.

## Say when a page is flagged

The wikis mark their own doubt and the tooling surfaces it with a `!` line:
`{{verification}}`, `{{verify}}`, `{{Question}}`, and the `Information Needed` or
`Verification` categories. Never launder a flagged claim into a plain statement of fact.

## Era

All three wikis describe **retail** FFXI as it stands now. For private server or era work
(75 cap, ToAU era, LandSandBoat), post-era job, ability and item data is actively misleading.
When a question looks era-related, say so, and reach for the `ffxi-version-updates` skill to
date the change rather than assuming the wiki describes the era in question.

## Answer, do not paste

- Extract the answer and cite the page. Never dump raw wikitext at someone.
- Stats live in templates. Pull the parameters out of `{{Infobox Weapon|...}}`, `{{Item|...}}`,
  `{{Bestiary Abilities Row|...}}` rather than quoting the braces.
- FFO bodies are Japanese. Translate the relevant part; do not paste Japanese Markdown at an
  English speaker. FFO links are site-relative (`/html/255.html`), so resolve them against
  `https://wiki.ffo.jp` before showing one.
- If the corpus has nothing, **say so**. Do not fall back on training data about FFXI. Being
  replaced by a citable source is the entire reason this exists.

## Where things hide

- Bestiary data for a mob family is often on the **Category:** page, not the article. If
  `title` comes up short for a mob, try `category`.
- Aliases resolve through the redirect tables, so an item's alternate name finds the real page.
  The reverse map (all known aliases of X) is not built.
- `title` also finds the FFO page for an English name by matching its `reading`, so a lookup
  crosses languages without you knowing the Japanese title.
- `name` works off FFO's `reading` field, `kana/English name`. It is the only systematic JP to
  EN mapping in the corpus, and not every page carries the English half.

## Corpus

Seven JSONL files from [sruon/ffxi-wiki-dumps](https://github.com/sruon/ffxi-wiki-dumps),
about 400MB uncompressed: articles, Category: pages and redirects for each wiki. The JSONL is
the source of truth and stays on disk; `wiki.py index` rebuilds a damaged index without
re-downloading.

Two shapes, and the difference bites: MediaWiki entries carry the body in `wikitext`, FFO
carries it in `text`. Article `categories` lists drop the `Category:` prefix that Category page
titles keep.

```bash
python test_wiki.py   # no download or network needed
```
