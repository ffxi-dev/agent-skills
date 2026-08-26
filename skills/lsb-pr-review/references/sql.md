# SQL rules


- Only change a shared row after checking how many mobs/items use it. Per-mob values go in the mob
  script instead.
- `npc_list`: first column is the script name (underscored, matches the Lua filename), second is
  the client display name. Binary/blob names from captures **must not be changed** or the entity breaks.
- Text must match the update extractor's text exactly - no `Name: ` prefixes in comments, prefixes
  break the update tool.
- Fix the trailing comment when you change a value; align comments.
- Don't add PR-narrative comments to SQL files.
- Ordering: keep a consistent, stated pattern (ID order with a family comment is preferred).
- If you delete a spell/skill list, check nothing still references it (the server logs
  `Mob spell list ID N does not exist`).
- Mobs whose casting/skills are handled in Lua should have their SQL lists emptied - don't split the
  same logic between SQL and Lua.
- New **player-data** tables (chars, inventory, economy) go in the `player_data` protected list
  in `tools/dbtool.py`; static data tables must not, or they get excluded from import.
