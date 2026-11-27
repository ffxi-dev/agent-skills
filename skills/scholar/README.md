# scholar

Read Vault's archive of retail FFXI captures through Scholar. Use it whenever you are given a mogsafe.sruon.dev, scholar.sruon.dev, or lens.sruon.dev link (a capture, a mob, an item, a recipe, a TP move, an NPC, a shop, a timeline, a /c/ download): those pages draw their data with JavaScript, so fetching the HTML shows nothing. `scholar.py open <link>` returns the page's data, `scholar.py sql <link>` the SQL behind it for the mogsafe MCP server's query tool, and `scholar.py download <link>` the capture's .xicap file to read packet by packet. Also use it to ask SQL across every capture: which mobs and NPCs appear in a zone, where and how often, their HP, claims, and positions; what the recording character wore; zones visited; any decoded packet field. Every packet row links to Lens, so an answer can be checked against the bytes.

See [SKILL.md](SKILL.md) for the full instructions, and the [repo README](../../README.md) for how skills are installed.

**Requirements:** Requires Python 3.9+ and network access to scholar.sruon.dev and mogsafe.sruon.dev. SQL needs the mogsafe MCP server (Clerk sign-in) or SCHOLAR_API_KEY.

<!-- generated from SKILL.md by tools/gen_skill_readmes.py; do not edit -->
