#!/usr/bin/env python3
"""Tests for the Scholar skill's script, against a fake Scholar.

Runs under pytest or standalone: `python skills/scholar/test_scholar.py`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

import scholar

HERE = os.getcwd()

SEEN: list[tuple[str, str, str]] = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a: Any) -> None:
        pass

    def reply(self, code: int, body: Any) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        SEEN.append(("GET", self.path, self.headers.get("Authorization", "")))
        path, _, query = self.path.partition("?")
        if path in PAGES:  # Mogsafe's JSON and Scholar's named queries, which answer anyone
            return self.reply(200, PAGES[path](query))
        if path.startswith("/c/"):
            data = b"XICAP" * 10
            self.send_response(200)
            self.send_header("Content-Disposition", 'attachment; filename="Metur_rec1.xicap"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.headers.get("Authorization") != "Bearer ak_test":
            return self.reply(401, {"error": "sign in"})
        cols = [{"name": "zone_name", "type": "VARCHAR", "doc": "The zone's name."}]
        self.reply(200, [{"name": "zones", "doc": "Zone-ins.", "unit": "zones", "version": "1", "columns": cols}])

    def do_POST(self) -> None:
        sql = self.rfile.read(int(self.headers["Content-Length"])).decode()
        SEEN.append(("POST", self.path, sql))
        if sql.startswith("DELETE"):
            return self.reply(400, {"error": "only SELECT and EXPLAIN run here, not DELETE"})
        self.reply(200, {"columns": ["zone_name", "n"], "rows": [["Garlaige Citadel", 3], [None, 1]], "truncated": True})


def rows(columns: list[str], *values: list[Any]) -> dict[str, Any]:
    return {"columns": columns, "rows": list(values), "truncated": False}


SESSION = {"id": "ses1", "capture_id": "rec1", "name": "[cert]_2026-11-22", "start_packet": 10, "end_packet": 20}
STORED = {"fights": rows(["mob", "name"], [1, "Goblin Leecher"])}
PAGES: dict[str, Callable[[str], Any]] = {
    "/v1/web/captures/rec1": lambda q: {"capture": {"id": "rec1"}, "session": None, "analysis": {"id": "rec1"}},
    "/v1/web/captures/ses1": lambda q: {"capture": {"id": "rec1"}, "session": SESSION, "analysis": {"id": "rec1"}},
    "/v1/queries/page": lambda q: rows(["page"], [json.dumps(STORED)]),
    "/v1/queries/shop_npcs": lambda q: rows(["zone", "npc_name"], [230, "Ostalie"], [230, "Other"], [231, "Ostalie"]),
    "/v1/queries/npc_zone_shops": lambda q: rows(["npc_name", "item"], ["Ostalie", 4096], ["Other", 1]),
    "/v1/web/timeline/abc": lambda q: {"latest": 1795590741460, "captures": [] if "from" not in q else [{"id": q}]},
}
for name in scholar.MOB + ("zone_name",):
    PAGES[f"/v1/queries/{name}"] = lambda q: rows(["q"], [q])


def run(*argv: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        scholar.main(list(argv))
    return out.getvalue()


def main() -> None:
    server = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    scholar.URL = f"http://127.0.0.1:{server.server_address[1]}"
    os.environ["SCHOLAR_API_KEY"] = "ak_test"

    # A link opens the data its page shows: each named query the page runs, with the page's own parameters.
    scholar.MOGSAFE = scholar.URL
    mob = json.loads(run("open", "https://mogsafe.sruon.dev/mobs/103/Goblin%20Leecher"))
    assert [d["query"] for d in mob["data"]] == [*scholar.MOB, "zone_name"]
    assert mob["data"][0]["rows"] == [{"q": "zone=103&name=Goblin+Leecher"}], mob["data"][0]
    assert mob["data"][-1]["rows"] == [{"q": "zone=103"}]
    shop = json.loads(run("open", "mogsafe.sruon.dev/shops/230/Ostalie"))["data"]
    assert shop[0]["rows"] == [{"zone": 230, "npc_name": "Ostalie"}] and shop[1]["rows"] == [{"npc_name": "Ostalie", "item": 4096}]

    # A session's page is its recording's analysis, and Lens opens the recording at the session.
    page = json.loads(run("open", "https://mogsafe.sruon.dev/captures/ses1"))
    assert page["scholar"]["fights"] == [{"mob": 1, "name": "Goblin Leecher"}]
    assert page["lens"] == "https://lens.sruon.dev/c/rec1?session=%5Bcert%5D_2026-11-22" and page["session_range"] == [10, 20]
    assert json.loads(run("open", "https://lens.sruon.dev/c/rec1"))["lens"] == "https://lens.sruon.dev/c/rec1"

    # A timeline opens on its latest day, in UTC, or the day the link names.
    latest = json.loads(run("open", "https://mogsafe.sruon.dev/t/abc"))
    assert latest["day"] == "2026-11-25" and latest["captures"] == [{"id": "from=1795564800000&to=1795651200000"}]
    assert json.loads(run("open", "https://mogsafe.sruon.dev/t/abc?day=2026-11-24"))["day"] == "2026-11-24"

    for signed_in in ("https://mogsafe.sruon.dev/me", "https://example.com/mobs"):
        try:
            run("open", signed_in)
            raise AssertionError(f"{signed_in} must exit")
        except SystemExit:
            pass

    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        assert "Metur_rec1.xicap (50 bytes)" in run("download", "https://mogsafe.sruon.dev/captures/ses1")
        assert open("Metur_rec1.xicap", "rb").read() == b"XICAP" * 10
        os.chdir(HERE)
    assert all(a == "Bearer ak_test" for m, p, a in SEEN if p.startswith("/v1/queries/")), "a key, when set, goes along"

    out = run("query", "SELECT zone_name, count(*) AS n FROM zones GROUP BY 1")
    assert "Garlaige Citadel" in out and "cut at 10,000" in out, out
    assert SEEN[-1] == ("POST", "/v1/query", "SELECT zone_name, count(*) AS n FROM zones GROUP BY 1")
    assert "zone_name VARCHAR: The zone's name." in run("tables", "zones")

    try:
        run("query", "DELETE FROM packets")
        raise AssertionError("a refused query must exit")
    except SystemExit as e:
        assert "only SELECT" in str(e)

    os.environ["SCHOLAR_API_KEY"] = "ak_wrong"
    try:
        run("tables")
        raise AssertionError("a wrong key must exit")
    except SystemExit as e:
        assert "401" in str(e) and "ak_wrong" not in str(e), "the key never shows"

    del os.environ["SCHOLAR_API_KEY"]
    try:
        run("tables")
        raise AssertionError("no key must exit")
    except SystemExit as e:
        assert "SCHOLAR_API_KEY" in str(e)
    server.shutdown()
    print("ok")


def test_scholar() -> None:
    main()


if __name__ == "__main__":
    main()
