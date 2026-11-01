---
name: scholar
description: >
  Ask Scholar, Vault's index of every archived retail FFXI capture, questions in SQL: which mobs
  and NPCs appear in a zone, where and how often, their HP, claims, and positions; what the
  recording character wore; zones visited; any packet's decoded fields across every capture.
  Use it whenever a question about what retail does could be answered from captured packets,
  before grepping logs one capture at a time. Every row links to its packet in Lens, so an
  answer can be checked against the bytes. Needs SCHOLAR_API_KEY, a key made at
  https://scholar.sruon.dev/keys.
license: MIT
compatibility: Requires Python 3.9+, network access to scholar.sruon.dev, and SCHOLAR_API_KEY.
---

# Scholar

Scholar decodes every capture Mogsafe archives and answers read-only SQL across them, through
`https://scholar.sruon.dev`.

## Use it

```bash
python scholar.py tables              # every table: what it holds, its columns, and what each means
python scholar.py tables entities     # one table
python scholar.py versions            # client versions held, and the names that fit them
python scholar.py query "SELECT entity_name, count(*) AS n FROM entities WHERE monster AND zone_name = 'Garlaige Citadel' GROUP BY 1 ORDER BY n DESC"
```

Read `tables` before writing a query: column names follow `ffxi-dev/packets`
(`UniqueNo`, `SendFlg.Position`, `Data.name`), and dotted names need double quotes in SQL
(`"SendFlg.Position"`).

## Rules for queries

- Opcodes are integers. DuckDB has no hex literals: `0x017` is `opcode = 23`.
- Ids stay ids. Use the name columns the tables carry (`zone_name`, `entity_name`,
  `item_name`) or join `zone_names`, `entity_names`, `item_names`, ... on `release` and `id`:
  names come from the release that fits each capture's client version.
- `packets` and the layout tables (`s2c_0x00e`, ...) are large. Filter on `capture_id`,
  `opcode`, or a table's own columns, and aggregate rather than pull rows: an answer stops at
  10,000 rows and a query at 60 seconds.
- Every row from a packet has `lens_url`. Give it with any claim about a specific packet, so a
  person can open the bytes.
- Only `SELECT` and `EXPLAIN` run. Nothing here changes the archive.

## The key

`SCHOLAR_API_KEY` holds a Clerk API key (`ak_...`) the person made at
https://scholar.sruon.dev/keys. Never print it, put it in a command line, or write it to a file;
`scholar.py` reads it from the environment. A `401` means the key is missing, wrong, or revoked:
ask the person for a new one.
