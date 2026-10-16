"""
Tests for golfer_form.py (the why-line facts).
Run:  python3 scripts/features/test_golfer_form.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.features.golfer_form import golfer_facts, load_history, parse_finish  # noqa: E402

D = pd.Timestamp


def hist(rows):
    return pd.DataFrame(rows, columns=["tournament_id", "player_id", "finish", "date"])


# Player "1" — ids deliberately out of calendar order: R2026010 is the
# LATEST event here (tournament_id order is not date order).
H = hist([
    ("R2026010", "1", 3,    D("2026-09-28")),
    ("R2026500", "1", "MC", D("2026-09-21")),
    ("R2026020", "1", 12,   D("2026-09-14")),
    ("R2026030", "1", 1,    D("2026-09-07")),
    ("R2026040", "1", 40,   D("2026-08-31")),
    ("R2026050", "1", 7,    D("2026-08-24")),   # 6th most recent: dropped
    # past editions of event 557
    ("R2025557", "1", 20,   D("2025-09-21")),
    ("R2024557", "1", "MC", D("2024-09-22")),
    ("R2014557", "1", 5,    D("2014-09-21")),   # > 10 years before: not "here"
    # this week's event itself, already played (viewing history)
    ("R2026557", "1", 2,    D("2026-10-05")),
    # a U.S. Open (rotating)
    ("R2025026", "1", 9,    D("2025-06-15")),
])
BEFORE = D("2026-10-05")


def test_parse_finish():
    assert parse_finish("T7") == 7
    assert parse_finish("1") == 1
    assert parse_finish("CUT") == "MC" and parse_finish("W/D") == "MC" and parse_finish("DQ") == "MC"
    assert parse_finish("nan") is None


def test_recent_is_by_date_most_recent_first_max_5():
    f = golfer_facts(H, ["1"], "R2026557", BEFORE)["1"]
    assert f["recent"] == [3, "MC", 12, 1, 40], f["recent"]


def test_never_counts_this_event_or_later():
    f = golfer_facts(H, ["1"], "R2026557", BEFORE)["1"]
    assert 2 not in f["recent"]
    early = golfer_facts(H, ["1"], "R2026557", D("2026-09-15"))["1"]
    assert early["recent"][0] == 12, early["recent"]   # only starts before Sep 15


def test_event_record_is_past_editions_within_ten_years():
    f = golfer_facts(H, ["1"], "R2026557", BEFORE)["1"]
    assert (f["event_starts"], f["event_cuts"]) == (2, 1), f   # 2025 (made), 2024 (MC); 2014 too old


def test_rotating_majors_have_no_event_record():
    f = golfer_facts(H, ["1"], "R2026026", BEFORE)["1"]
    assert f["event_starts"] == 0 and f["event_cuts"] == 0


def test_unknown_player_gets_empty_facts():
    f = golfer_facts(H, ["999"], "R2026557", BEFORE)["999"]
    assert f == {"recent": [], "event_starts": 0, "event_cuts": 0}


def test_real_history_loads_with_dates():
    h = load_history()
    assert len(h) > 10_000, len(h)
    assert h["date"].notna().all() and h["player_id"].str.fullmatch(r"(DG)?\d+").all()   # DG-only golfers carry a DG prefix


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
