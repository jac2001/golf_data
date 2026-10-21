"""Route-table and response-contract tests for api/main.py. Run: python3 api/test_routes.py

Audit finding 8: /api/model-comparison was registered twice; HTTP served the
first handler while a direct Python lookup found the second, so editing or
testing the second changed nothing live.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402

client = TestClient(m.app)


def test_every_route_registered_once():
    seen = Counter(
        (method, r.path)
        for r in m.app.routes if isinstance(r, APIRoute)
        for method in r.methods
    )
    dupes = sorted(k for k, n in seen.items() if n > 1)
    assert not dupes, f"registered more than once: {dupes}"


def test_model_comparison_contract():
    # Keys web/lib/api.ts ModelComparison / ModelCompPlayer read.
    r = client.get("/api/model-comparison")
    if r.status_code == 404:
        print(f"  (skipped contract body: {r.json().get('detail')})")
        return
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ["tournament_id", "tournament_name", "players_compared",
                "overall_spearman_rho", "markets", "our_top10", "dg_top10",
                "disagreements", "players"]:
        assert key in body, key
    assert body["tournament_id"] == m._get_tournament_id()
    assert body["players"], "players list empty"
    for key in ["player", "our_rank", "dg_rank", "delta",
                "our_win", "dg_win", "our_top10", "dg_top10"]:
        assert key in body["players"][0], key


def test_dg_latest_refused_for_another_event():
    # A tid that has no per-event file and is not the event in _latest.
    assert m._dg_pre_tournament_path("R1999999") is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
