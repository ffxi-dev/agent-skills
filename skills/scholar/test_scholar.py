#!/usr/bin/env python3
"""Tests for the Scholar skill's script, against a fake Scholar.

Runs under pytest or standalone: `python skills/scholar/test_scholar.py`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import scholar

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
