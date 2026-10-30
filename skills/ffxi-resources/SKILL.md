---
name: ffxi-resources
description: >
  Look up trusted FFXI reference values decoded straight from the retail client DATs. Use to
  find a message or string ID and its text, an item ID and its properties, event bytecode and
  the decompiled Lua for an NPC event, ability, spell, status effect, key item, merit, augment
  or monster-family data, an NPC or monster entity name by id, or a zone id and name. Use it
  whenever you need to VERIFY a "trusted" FFXI value rather than recall one: this is a direct
  decode of the game's own resource files, not a wiki claim, so the numbers are authoritative.
  Prefer it over ffxi-wiki when the question is about an exact id, string, or bytecode value.
license: MIT
compatibility: Requires Python 3.9+, network on first run, and about 3GB of disk (a 93MB
  download, ~935MB decompressed NDJSON plus a ~2GB search index, most of it the 2.9M-row
  strings table). Pure standard library, no pandas or pyarrow.
---

# FFXI client resource lookup

A set of datasets decoded directly from the retail FFXI client resource DATs, indexed locally
and queried offline. Every value is a decode of the game's own files, so it is authoritative,
not a wiki claim. That is the whole point of this skill: use it to check an id, a message
string, or event bytecode against ground truth.

## Use it

```bash
python resources.py status                    # what is on disk, and from which release
python resources.py get items 18              # exact record by dataset + lookup key
python resources.py search items "Excalibur"  # word/substring search within one dataset

python resources.py item 18                   # item by id or name
python resources.py spell "Cure"              # spell by index or name
python resources.py ability 1                 # ability by id or name
python resources.py status Sleep              # status effect by id or name
python resources.py keyitem 1                 # key item by id or name
python resources.py entity 1-16781313         # entity by zone-entity id, or by name
python resources.py zone 100                  # zone by id or name
python resources.py string 1 0                # message string by zone_id + string_id
python resources.py event 1 100               # event by zone_id + event_id (byte_code + lua)
```

`status` with no argument reports the corpus; `status <id|name>` looks up a status effect.

`status` reporting no corpus means run `python resources.py install`. It downloads the latest
release from [ffxi-dev/retail-resources](https://github.com/ffxi-dev/retail-resources), decompresses
every `<dataset>.ndjson.gz`, and builds the index. No GitHub CLI or login needed. Refresh the
same way; `install` is safe to re-run when a new decode is published.

## It is trusted, so say so, and hand over the link

Every result prints a line stating the value is client-extracted (a direct DAT decode). When
you report one of these values, say where it came from: **"item id 18 is Excalibur (client
decode)"**, not just "Excalibur". The trust is the reason to reach for this over memory or a
wiki.

Each result for a dataset with a human page also prints a version-pinned deep link to
`res.sruon.dev`, so a person can open the same record in a browser. Pass it through. The routes,
pinned to the release tag the corpus was built from:

```
res.sruon.dev/v/<tag>/items/<id>
res.sruon.dev/v/<tag>/keyitems/<id>
res.sruon.dev/v/<tag>/spells/<index>
res.sruon.dev/v/<tag>/abilities/<id>
res.sruon.dev/v/<tag>/statuses/<id>
res.sruon.dev/v/<tag>/zones/<id>
res.sruon.dev/v/<tag>/entities/<zone_id>-<entity_id>
res.sruon.dev/v/<tag>/strings/<zone_id>-<string_id>
res.sruon.dev/v/<tag>/events/<zone_id>-<event_id>
```

Agents query the local datasets; humans get the link.

## Lookup keys, because they are not all `id`

The key is not always a plain `id`, and using the wrong one gives the wrong record:

- **spells** key on `index`, not `id`. Every spell row has `id` 0, so `id` collides across 72
  rows. `spell` and `get spells N` use `index`.
- **strings** key on `(zone_id, string_id)`, **entities** on `(zone_id, entity_id)`, **events**
  on `(zone_id, event_id)`. That is why `string`, `entity`, and `event` take two ids (or one
  hyphenated `zone-id` for `entity`).
- **events** `event_id` is a signed 16-bit value, so `-1` is a real key (the raw `0xFFFF`).
  The `byte_code` is the FFXI event VM's compiled script; atom0s's
  [XiEvents](https://github.com/atom0s/XiEvents) documents that bytecode and the VM, and is
  the reference for reading it when the decompiled `lua` is absent or unclear.
- everything else (items, abilities, statuses, keyitems, merits, augments, monster_families,
  zones) keys on `id`.

## What each dataset holds

Rich records: **items** (name, description, type, stack, flags, targets, category), **spells**
and **abilities** (cost, range, element, valid targets, recast), **statuses** (name, passive
name, description, flag), **keyitems** (name, plural, description, category), **events**
(byte_code plus decompiled `lua`, entrypoint, params), **strings** (the message text for a
`(zone_id, string_id)`), **entities** (NPC/monster name for a `(zone_id, entity_id)`), **zones**
(name, short name).

Name-or-text only, so do not imply more: **merits**, **monster_families** (id to name),
**augments** (id to text), **autotranslate** (auto-translate phrases), **zone_layout** (raw
layout geometry, low value for a name/id lookup). Some releases add or drop a dataset (a
`modifiers` or `events_actors` table, a `pankration` table); `install` indexes whatever the
release ships and `status` lists what you actually have.

The base64 icon PNG on items and statuses is stripped when indexing. It is useless bulk for a
text lookup and would bloat the index; get the picture from the `res.sruon.dev` link instead.

## When to use this vs the wiki

Reach for this when the question is an exact value: an id, a message string, event bytecode,
the real cost or range of an ability. Reach for `ffxi-wiki` for prose, mechanics, drop rates,
quest flows, and anything the DATs do not encode. The client decode is retail data, same era
caveat as the wiki: for private-server or era work, an item or spell may have been rebalanced
since, so date it with `ffxi-version-updates` rather than assuming this row matches the era.

## Corpus

Fifteen or so NDJSON files, about 935MB decompressed (the index over them is a further ~2GB,
most of it the 2.9M-row strings table), from the release assets on
[ffxi-dev/retail-resources](https://github.com/ffxi-dev/retail-resources). The decompressed NDJSON is the
source of truth on disk; the SQLite index is derived, and `python resources.py index` rebuilds
it from the NDJSON without re-downloading. Force-UTF-8 stdout is set at startup because the data
is largely Japanese and a Windows cp1252 console crashes on it otherwise.

```bash
python test_resources.py   # no download or network needed
```
