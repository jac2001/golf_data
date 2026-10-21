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


def test_owner_picks_refuse_anonymous():
    # One person's picks: the site shows them to admins only (audit finding 9).
    assert client.get("/api/owner-picks").status_code == 403
    assert client.get("/api/owner-picks", headers={"X-Chat-Proxy-Secret": "wrong"}).status_code == 403



def _freshen_harness(tmp, kind, write):
    """Run m._freshen(kind) against a temp data dir; return how many fetches it ran."""
    import json as _json
    import os
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    saved = (m.DATA_DIR, m.CLOUD_FETCH, m._get_tournament_id, m.subprocess.run)
    m.DATA_DIR, m.CLOUD_FETCH = tmp, True
    m._get_tournament_id = lambda: "R2026999"
    m.subprocess.run = lambda *a, **k: calls.append(a) or Done()
    m._freshen_last_attempt.clear()
    try:
        write(tmp, _json, os)
        m._freshen(kind)
        return len(calls)
    finally:
        m.DATA_DIR, m.CLOUD_FETCH, m._get_tournament_id, m.subprocess.run = saved


def test_freshen_ages_files_by_inner_stamp_not_mtime():
    # Audit follow-up: a deploy checks every file out "now", so a 2-day-old
    # forecast looked fresh for 3 hours after each push.
    import tempfile
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    new = datetime.now(timezone.utc).isoformat()

    def weather(stamp):
        def write(tmp, _json, os):
            (tmp / "weather").mkdir(parents=True, exist_ok=True)
            p = tmp / "weather" / "R2026999.json"
            p.write_text(_json.dumps({"saved_at": stamp, "daily": []}))
            os.utime(p, None)                       # mtime = now, as after a checkout
        return write

    m._freshen_fetched_ok.clear()
    with tempfile.TemporaryDirectory() as d:
        assert _freshen_harness(Path(d), "weather", weather(old)) == 1
    m._freshen_fetched_ok.clear()
    with tempfile.TemporaryDirectory() as d:
        assert _freshen_harness(Path(d), "weather", weather(new)) == 0
    m._freshen_fetched_ok.clear()
    with tempfile.TemporaryDirectory() as d:
        assert _freshen_harness(Path(d), "weather", weather("")) == 1   # no stamp = stale


def test_freshen_good_fetch_holds_even_when_source_stamp_is_old():
    # DG's odds last_updated can be hours old overnight right after a fetch;
    # one good fetch must hold for the TTL instead of refetching every minute.
    import tempfile

    def odds(tmp, _json, os):
        (tmp / "datagolf").mkdir(parents=True, exist_ok=True)
        (tmp / "datagolf" / "dg_outrights_R2026999.csv").write_text(
            "player_name,last_updated\nA,2026-01-01 00:00:00 UTC\n")

    m._freshen_fetched_ok.clear()
    with tempfile.TemporaryDirectory() as d:
        assert _freshen_harness(Path(d), "odds", odds) == 1
        assert _freshen_harness(Path(d), "odds", odds) == 0
    m._freshen_fetched_ok.clear()


def test_parse_stamp_formats():
    assert m._parse_stamp("2026-10-21 00:44:27 UTC") == m._parse_stamp("2026-10-21T00:44:27+00:00")
    # naive = America/Chicago (CDT, UTC-5, in October)
    assert m._parse_stamp("2026-10-20T19:44:27") == m._parse_stamp("2026-10-21T00:44:27+00:00")
    assert m._parse_stamp("") is None and m._parse_stamp("not a date") is None

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
