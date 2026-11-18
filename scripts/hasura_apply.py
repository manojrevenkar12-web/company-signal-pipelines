"""Apply hasura/metadata.json to a running Hasura and check the scout role can read what it should.

    HASURA_URL=http://localhost:8080 HASURA_ADMIN_SECRET=... python scripts/hasura_apply.py
Uses only the standard library so it runs in a bare CI step.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

URL = os.environ.get("HASURA_URL", "http://localhost:8080")
SECRET = os.environ.get("HASURA_ADMIN_SECRET", "")
META = Path(__file__).resolve().parents[1] / "hasura" / "metadata.json"


def post(path: str, body: dict, role: str | None = None) -> dict:
    headers = {"content-type": "application/json", "x-hasura-admin-secret": SECRET}
    if role:
        headers["x-hasura-role"] = role
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    for _ in range(60):
        try:
            urllib.request.urlopen(URL + "/healthz", timeout=5)
            break
        except OSError:
            time.sleep(2)
    meta = json.loads(META.read_text())
    out = post("/v1/metadata", {"type": "replace_metadata", "version": 2,
                                "args": {"allow_inconsistent_metadata": False, "metadata": meta}})
    print("metadata:", json.dumps(out)[:200])
    incon = post("/v1/metadata", {"type": "get_inconsistent_metadata", "args": {}})
    if not incon.get("is_consistent", False):
        print("inconsistent metadata:", json.dumps(incon)[:1000])
        return 1
    q = """{ recommendable_startups(limit: 3, order_by: {headcount: desc_nulls_last}) {
               name country company { status signals(limit: 2) { kind event_date } } }
             feed_health { feed loads backfills alerts } }"""
    res = post("/v1/graphql", {"query": q}, role="scout")
    if "errors" in res:
        print("graphql errors:", res["errors"])
        return 1
    data = res["data"]
    print("scout sees", len(data["recommendable_startups"]), "startups and", len(data["feed_health"]), "feeds")
    assert all(s["company"]["status"] == "active" for s in data["recommendable_startups"])
    assert len(data["feed_health"]) == 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
