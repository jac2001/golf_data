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
    df = pd.DataFrame(rows, columns=["tournament_id", "player_id", "finish", "date"])
    df["had_cut"] = ~df["tournament_id"].isin(NO_CUT)
    return df


NO_CUT = {"R2025028", "R2024028"}   # BMW Championship editions: no cut


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


def test_no_cut_editions_never_count_as_made_cuts():
    h = pd.concat([H, hist([("R2025028", "1", 30, D("2025-08-17")), ("R2024028", "1", 12, D("2024-08-18"))])])
    f = golfer_facts(h, ["1"], "R2026028", BEFORE)["1"]
    assert f["event_starts"] == 0 and f["event_cuts"] == 0, f


def test_unknown_player_gets_empty_facts():
    f = golfer_facts(H, ["999"], "R2026557", BEFORE)["999"]
    assert f == {"recent": [], "event_starts": 0, "event_cuts": 0}


def test_datagolf_history_only_adds_missing_events():
    """leaderboards_dg_* fills events the PGA TOUR files lack; where both
    have an event, the PGA TOUR rows stand (no double counting)."""
    import tempfile
    cols = "tournament_id,year,player_id,player_name,position,tournament_name\n"
    with tempfile.TemporaryDirectory() as d:
        Path(d, "leaderboards_2025.csv").write_text(
            cols + "R2025003,2025,1,A,T5,WM Phoenix Open\nR2025003,2025,2,B,CUT,WM Phoenix Open\n")
        Path(d, "leaderboards_dg_2025.csv").write_text(
            cols + "R2025003,2025,1,A,T9,WM Phoenix Open\n"           # PGA TOUR's row wins
                   "R2025528,2025,1,A,T3,Butterfield Bermuda Championship\n")
        h = load_history(Path(d))
        a = h[h["player_id"] == "1"].set_index("tournament_id")["finish"].to_dict()
        assert a == {"R2025003": 5, "R2025528": 3}, a
        assert len(h[h["tournament_id"] == "R2025003"]) == 2


def test_real_history_loads_with_dates():
    h = load_history()
    assert len(h) > 10_000, len(h)
    assert h["date"].notna().all() and h["player_id"].str.fullmatch(r"(DG)?\d+").all()   # DG-only golfers carry a DG prefix
    # the 2025 BMW (no cut) and a regular event (has one)
    assert not h.loc[h["tournament_id"] == "R2025028", "had_cut"].any()
    assert h.loc[h["tournament_id"] == "R2025010", "had_cut"].all()


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
