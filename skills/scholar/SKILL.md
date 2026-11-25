---
name: scholar
description: >
  Read Vault's archive of retail FFXI captures through Scholar. Use it whenever you are given a
  mogsafe.sruon.dev, scholar.sruon.dev, or lens.sruon.dev link (a capture, a mob, an item, a
  recipe, a TP move, an NPC, a shop, a timeline, a /c/ download): those pages draw their data
  with JavaScript, so fetching the HTML shows nothing. `scholar.py open <link>` returns the
  page's data, and `scholar.py sql <link>` the SQL behind it for the mogsafe MCP server's query
  tool. Also use it to ask SQL across every capture: which mobs and NPCs appear in a zone, where
  and how often, their HP, claims, and positions; what the recording character wore; zones
  visited; any decoded packet field. Every packet row links to Lens, so an answer can be checked
  against the bytes.
license: MIT
compatibility: Requires Python 3.9+ and network access to scholar.sruon.dev and mogsafe.sruon.dev. SQL needs the mogsafe MCP server (Clerk sign-in) or SCHOLAR_API_KEY.
---

# Scholar

Mogsafe (`https://mogsafe.sruon.dev`) archives retail captures. Scholar
(`https://scholar.sruon.dev`) decodes every one into ClickHouse and answers the pages' named
queries and read-only SQL across them. Lens (`https://lens.sruon.dev`) shows a capture's
packets in a browser.

## First: the MCP server

SQL goes through Scholar's MCP server, which the person signs in to themselves. Check that you
have its tools: `tables`, `query`, and `versions` from the `mogsafe` server (in Claude Code,
`mcp__mogsafe__query`; `claude mcp get mogsafe` shows whether it is set up). If not, tell the
person to run the command from https://mogsafe.sruon.dev/mcp-help:

```bash
claude mcp add --transport http mogsafe https://scholar.sruon.dev/mcp
```

Then they start a new session, because a running one does not see the new server. The first
call opens Clerk's sign-in in their browser (GitHub or Discord), and they approve it there. The
tools are `tables` (every table and column, with what each means: read it first), `query` (one
read-only ClickHouse query: 10,000 rows, 60 s), and `versions`. Page data needs none of this.

## A link

Mogsafe's pages are a JavaScript shell: a plain fetch of `/mobs/103/Goblin%20Leecher` returns
73 KB of HTML and none of the mob. Do not scrape it.

```bash
python scholar.py open "https://mogsafe.sruon.dev/mobs/103/Goblin%20Leecher" > mob.json   # the page's data, no sign-in
python scholar.py sql "https://mogsafe.sruon.dev/mobs/103/Goblin%20Leecher"               # the same, as SQL for query
```

`open` runs the named queries the page runs, with the page's own parameters, and prints one JSON
object. Explore pages give `{"page", "data": [{"query", "params", "rows", "truncated"}]}`, each row
an object. List pages answer hundreds of rows: send them to a file and filter there. A `?q=` on a
list page filters in the browser; `open` returns every row. A mob page's rows hold ids: its
`bestiary_names` rows (`kind` of `skill`, `spell`, or `item`, `id`, `name`) name them, in the
release the page names (`kind` `release`), as the page does.

`sql` prints each of those named queries' SQL, the page's values filled in, under a `-- name`
line. Send one to the MCP `query` tool as it is, or change it: pick columns, add a `WHERE`, join
another table. It reads Scholar's own queries from `https://scholar.sruon.dev/static/queries.json`
and the Explore pages' from `ffxi-dev/extractors` (`ffxi_extractors/sql/pages/<name>.sql` on
`main`). If one fails on a column Scholar lacks, `main` is ahead of the deployed Scholar: use `open`.
The capture list, `/c/` and timelines are Mogsafe's own JSON, which only `open` reads.

| Link | What the page runs | Sign-in |
| --- | --- | --- |
| `/captures/<id>`, a capture or a /cap session | Mogsafe `GET /v1/web/captures/<id>`, then Scholar `page?id=<recording id>`: the capture view's stored parts (`fights`, `drops`, `zones`, `party`, `events`, ...). For a session, `session_range` gives its packets in the recording. | no |
| `/captures`, `/` | Mogsafe `GET /v1/web/captures` with the page's `name`, `character`, `by`, `state`; `next` pages with `before=` | no |
| `/c/<id>` | the download link and the Lens link; save it with `download` | no |
| `/captures/<id>/timeline`, `/t/<code>` | the uploader's shared timeline, Mogsafe `GET /v1/web/timeline/<code>?from=&to=` for `?day=` or the latest day, as UTC | no |
| `/mobs` | `bestiary_list` | no |
| `/mobs/<zone>/<name>` | `bestiary_mob`, `bestiary_geometry`, `bestiary_evidence`, `bestiary_names`, `bestiary_steals`, `bestiary_effects`, `bestiary_events`, `bestiary_exp`, `bestiary_looks`, `bestiary_animations`, `bestiary_aggro`, `bestiary_mp`, `bestiary_gil` with `zone`, `name`; `zone_name` with `zone` | no |
| `/moves`, `/moves/<id>` | `tp_moves`; `tp_move` with `move` | no |
| `/wanted` | `bestiary_wanted` | no |
| `/items`, `/items/<id>` | `items`; `item_sources` with `item` | no |
| `/recipes` | `recipe_catalog` | no |
| `/fish` | `fishing_catalog` | no |
| `/weather`, `/weather/<zone>` | `weather_zones`, `weather_next`; `weather_zone` with `zone` | no |
| `/npcs`, `/npcs/<zone>` | `npc_zones`; `npc_zone`, `npc_zone_trades`, `npc_zone_shops` with `zone` | no |
| `/shops`, `/shops/<zone>/<name>` | `shop_npcs`; for one NPC, its `shop_npcs` row and its `npc_zone_shops` rows | no |
| `/search?kind=&q=&mob=&character=&from=&to=` | Scholar `GET /v1/search` (`open` with a key). Through MCP, query the kind's table: `fights` (mob), `zone_visits` (zone), `tp_uses` (tp), `spell_results` (spell), `drops` (drop), `log_changes` (quest), `keyitems` (keyitem), joined to `captures` for the character | yes |
| `/gaps` (the owner's) | `gaps`, `gaps_load`: `sql` for MCP, or `open` with a key | yes |
| `/me`, `/import`, `/timeline/me`, `/link`, `/admin` | none: Mogsafe reads them only for its signed-in browser session | n/a |
| `scholar.sruon.dev/captures/<id>`, `lens.sruon.dev/c/<id>` | the capture, as `/captures/<id>` | no |

One named query on its own: `python scholar.py named bestiary_mob zone=103 "name=Goblin Leecher"`.
Over HTTP it is `GET https://scholar.sruon.dev/v1/queries/<name>?<params>`, which answers
`{"columns", "rows", "truncated"}` to anyone. Without a sign-in it leaves out who recorded each
row (`recorder`, `recorders`). MCP SQL keeps them.

## A capture's file, and Lens

```bash
python scholar.py download https://mogsafe.sruon.dev/c/l2DRncUnT1GS [FILE]   # or any capture or session link or id
```

Without `FILE` it saves to the current directory under Mogsafe's name, `<character>_<id>.xicap`.

`/c/<id>` is public. An archived capture redirects to a signed R2 link that lasts 15 minutes; a
session's id gives its whole recording. A capture still recording downloads only for its
uploader. The file is xicap: read it with xicap's reader (`ffxi-dev/xicap`), or the
`ffxi-packets` skill for captain logs, never by hand.

Lens runs in a browser, so give the person its link: `https://lens.sruon.dev/c/<recording id>`,
with `?session=<name>` to open at a /cap session and `#packet=<n>` to select a packet (`n` counts
from 0 across the recording, as Scholar's `idx` does). `open` prints the link as `lens`.

## An API key, without MCP

For scripted SQL, search, and gaps outside MCP, `scholar.py` takes a key. The person signs in at
https://scholar.sruon.dev/keys and makes one (`ak_...`), then sets `SCHOLAR_API_KEY` where the
agent's shell sees it: in Claude Code, `"env": {"SCHOLAR_API_KEY": "ak_..."}` in
`~/.claude/settings.json`; elsewhere an `export` in the shell profile. `scholar.py` sends it as
`Authorization: Bearer <key>`; with it set, `open` also gets the recorder columns.

Never print the key, put it in a command line, or write it to a file. A `401` means the key is
missing, wrong, or revoked: ask the person for a new one. Mogsafe itself takes no key or MCP
token: `/me`, `/import`, `/timeline/me`, `/link`, and `/admin` stay its browser session's.

## SQL

Through MCP, call `tables`, then `query`. With a key instead:

```bash
python scholar.py tables              # every table: what it holds, its columns, and what each means
python scholar.py tables zone_visits  # one table
python scholar.py versions            # client versions held, and the names that fit them
python scholar.py query "SELECT name, zone_name, fights FROM bestiary_list WHERE zone = 103 ORDER BY fights DESC LIMIT 10"
```

Read `tables` before writing a query. Scholar holds decoded events and facts, not raw packets.

- Ids stay ids. Use the name columns the tables carry (`zone_name`, `entity_name`, `item_name`)
  or join `zone_names`, `entity_names`, `item_names`, `mob_skill_names`, ... on `release` and
  `id`: names come from the release that fits each capture's client version. Some ids are
  reused across releases (mob skills 3968 to 3978 change names from one release to the next), so
  name a row by its own capture's release, never another's.
- Filter on `capture_id` or a table's own columns, and aggregate rather than pull rows: an
  answer stops at 10,000 rows and a query at 60 seconds.
- Every row from a packet has `idx`, its packet in Lens (`#packet=<idx>`), and some tables carry
  `lens_url`. Give the link with any claim about a specific packet, so a person can open the bytes.
- Only `SELECT` and `EXPLAIN` run. Nothing here changes the archive.
