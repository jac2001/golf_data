"""
Tests for euro_integrity.check — written before the code.
Run:  python3 scripts/validation/test_euro_integrity.py

Each case is a small hand-built board, so the expected verdict is
obvious from reading the case. Tests 5 and 6 (completeness, freshness)
are yours to add once you've made those two calls.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.validation.euro_integrity import check  # noqa: E402

SUNDAY = pd.Timestamp("2026-10-11")


def board(n: int = 144, history_share: float = 1.0, market_agrees: bool = True) -> pd.DataFrame:
    """A field of n players, best first. The weakest (1 - history_share)
    of the field have no rounds in the window."""
    win = np.linspace(0.08, 0.0005, n)
    sg = np.linspace(2.0, -2.0, n)
    no_hist = int(round(n * (1 - history_share)))
    if no_hist:
        sg[-no_hist:] = np.nan
    vegas = win if market_agrees else win[::-1]
    return pd.DataFrame({
        "player_name": [f"Player {i:03d}" for i in range(n)],
        "win_prob": win / win.sum(), "season_sg_total": sg,
        "vegas_prob": vegas / vegas.sum(),
    })


def history(**overrides) -> dict:
    h = {"events_expected": 55, "events_fetched": 55, "events_failed": [],
         "newest_round": SUNDAY, "last_finished_event_end": SUNDAY}
    h.update(overrides)
    return h


# ── the tests ────────────────────────────────────────────────────────────────

def test_clean_board_passes():
    failures, notes = check(board(), history(), pre_event=True)
    assert failures == [], failures


def test_no_history_at_all_blocks():
    failures, _ = check(board(history_share=0.0),
                        history(events_fetched=0, newest_round=None), pre_event=True)
    assert failures, "an empty history fetch must block"


def test_top10_player_without_history_blocks_and_is_named():
    b = board()
    b.loc[3, "season_sg_total"] = np.nan          # the 4th favourite has no rounds
    failures, _ = check(b, history(), pre_event=True)
    assert failures, "a top-10 player without history must block"
    assert any("Player 003" in f for f in failures), f"name him: {failures}"


def test_thin_field_is_a_note_not_a_block():
    """An Australian co-sanctioned week: 40% of the field never plays
    euro events. Legitimate — the backtest's min was 29%."""
    failures, notes = check(board(history_share=0.6), history(), pre_event=True)
    assert failures == [], failures
    assert notes, "low coverage should still be mentioned"


def test_market_disagreement_pre_event_is_a_note():
    failures, notes = check(board(market_agrees=False), history(), pre_event=True)
    assert failures == [], failures
    assert any("market" in n.lower() for n in notes), notes


def test_market_disagreement_mid_event_is_ignored():
    """In-play odds disagree with pre-event form by design."""
    _, notes = check(board(market_agrees=False), history(), pre_event=False)
    assert not any("market" in n.lower() for n in notes), notes


def test_odds_missing_is_fine():
    b = board().drop(columns=["vegas_prob"])
    failures, _ = check(b, history(), pre_event=True)
    assert failures == [], failures

def test_one_failed_history_fetch():
    """One of ~55 archived events failed to download: the players who
    played it are missing that week. Decision 5 says what happens."""
    h = history(events_fetched=54, events_failed=["Open de France"])
    failures, notes = check(board(), h, pre_event=True)
    # Pick ONE of these, to match the rule you wrote in check():
    #   blocks:   assert failures, "a failed fetch must block"
    #   a note:   assert failures == [], failures
    #             assert any("Open de France" in n for n in notes), notes
    
    assert failures, "a failed fetch must block"

def test_last_week_not_posted_blocks():
    """DataGolf hasn't posted last week's event: the newest round we have
    is from two Sundays ago, but an event finished last Sunday."""
    h = history(newest_round=SUNDAY - pd.Timedelta(days=7))
    failures, _ = check(board(), h, pre_event=True)
    assert failures, "stale history must block"

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
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
