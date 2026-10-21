"""Tests for compare_leaderboard_sources.agreement — written before the code.
Run: python3 scripts/validation/test_compare_leaderboard_sources.py"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.validation.compare_leaderboard_sources import agreement  # noqa: E402


def frame(rows):
    return pd.DataFrame(rows, columns=["tournament_id", "player_id", "position"])


PGA = frame([
    ("R2025003", "1", "1"), ("R2025003", "2", "T5"), ("R2025003", "3", "T5"), ("R2025003", "4", "CUT"),
    ("R2025003", "5", "W/D"),
    ("R2025010", "1", "T2"), ("R2025010", "2", "T9"),
    ("R2025099", "1", "1"),                       # only PGA TOUR has this event
])
DG = frame([
    ("R2025003", "1", "1"), ("R2025003", "2", "T5"), ("R2025003", "3", "T6"), ("R2025003", "4", "CUT"),
    ("R2025003", "5", "WD"), ("R2025003", "6", "CUT"),   # player 6: only DataGolf
    ("R2025010", "1", "T2"),                              # player 2: only PGA TOUR
    ("R2025528", "1", "T3"),                              # only DataGolf has this event
])


def test_counts_only_shared_events_and_pairs():
    r = agreement(PGA, DG)
    assert r["events"] == 2
    assert r["pairs"] == 6          # 5 in R2025003, 1 in R2025010


def test_match_rate_treats_W_D_and_WD_as_the_same():
    # Agree: 1/1, T5/T5, CUT/CUT, W/D/WD, T2/T2. Disagree: T5/T6.
    assert abs(agreement(PGA, DG)["match_rate"] - 5 / 6) < 1e-9


def test_players_listed_by_only_one_source():
    r = agreement(PGA, DG)
    assert r["only_pga"] == 1       # player 2 at R2025010
    assert r["only_dg"] == 1        # player 6 at R2025003


def test_worst_events_lowest_first():
    r = agreement(PGA, DG, worst_n=1)
    assert len(r["worst"]) == 1
    tid, rate = r["worst"][0]
    assert tid == "R2025003" and abs(rate - 4 / 5) < 1e-9


def test_row_order_does_not_matter():
    a = agreement(PGA, DG)
    b = agreement(PGA.sample(frac=1, random_state=1), DG.sample(frac=1, random_state=2))
    assert a == b


def test_nothing_shared():
    r = agreement(frame([("R2025099", "1", "1")]), frame([("R2025528", "1", "1")]))
    assert r == {"events": 0, "pairs": 0, "match_rate": 0.0, "only_pga": 0, "only_dg": 0, "worst": []}


# TODO(Jack): one test for decision (a) or (b).
def test_untied_and_tied_spelling_agree():          # decision (a)
    r = agreement(frame([("R2025003", "1", "5")]), frame([("R2025003", "1", "T5")]))
    assert r["match_rate"] == 1.0
    
def test_cut_wd():
    r = agreement(frame([("R2025528", "1", "CUT")]), frame([("R2025528", "1", "WD")]))
    assert r['pairs'] == 1 and r['match_rate'] == 0.0
    

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except (AssertionError, NotImplementedError) as e:
            failed += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
