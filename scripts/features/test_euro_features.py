"""
Tests for rolling_form_features — the euro model's feature function.
Run:  python3 scripts/features/test_euro_features.py

The one property that matters: the function must give the SAME answer
whether it's handed a player's whole career (training) or only the
recent rounds serving fetches (predict_euro.py). The stats review found
prior_rounds_count breaks this — 600 career rounds in training, ~120 at
serving — so the deployed model was fed numbers it never trained on.

These tests build fake players on synthetic data, so they run in under
a second with no database.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.features.build_euro_training_table import (  # noqa: E402
    FEATURE_WINDOW_DAYS, rolling_form_features,
)

EVENT = pd.Timestamp("2026-10-15")


def fake_player(events_per_year: int, years: int, seed: int, end: pd.Timestamp = EVENT) -> pd.DataFrame:
    """A player's rounds before `end`: events spread over `years`, 2 or 4
    rounds each (missed cut or not), every round dated the event's Sunday
    like the real DG archive."""
    rng = np.random.default_rng(seed)
    n = events_per_year * years
    sundays = sorted(rng.choice(np.arange(7, 365 * years), size=n, replace=False))
    rows = []
    for i, days_back in enumerate(sundays):
        date = end - pd.Timedelta(days=int(days_back))
        for rnd in range(1, (2 if rng.random() < 0.35 else 4) + 1):
            rows.append({
                "date": date, "event_id": i, "round_num": rnd,
                "sg_total": rng.normal(0.5, 2.5), "score": int(rng.integers(64, 78)),
                "course_par": 72, "birdies": int(rng.integers(0, 8)),
                "bogies": int(rng.integers(0, 5)), "doubles_or_worse": int(rng.integers(0, 2)),
                "pars": 11, "eagles_or_better": 0, "fin_text": "T20",
            })
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def serving_view(history: pd.DataFrame, event_date: pd.Timestamp = EVENT) -> pd.DataFrame:
    """What predict_euro.py can see: only rounds inside the window, and
    no event_id column (serving rows are dg_id, date, round_num + stats)."""
    recent = history[history["date"] >= event_date - pd.Timedelta(days=FEATURE_WINDOW_DAYS)]
    return recent.drop(columns=["event_id"])


def same(a: dict, b: dict) -> None:
    """Same keys, same values (NaN == NaN, floats to 1e-9)."""
    assert a.keys() == b.keys(), f"different features: {sorted(a.keys() ^ b.keys())}"
    for k in a:
        x, y = a[k], b[k]
        both_missing = (x is None or (isinstance(x, float) and math.isnan(x))) and \
                       (y is None or (isinstance(y, float) and math.isnan(y)))
        assert both_missing or math.isclose(float(x), float(y), abs_tol=1e-9), f"{k}: {x} vs {y}"


# ── the tests ────────────────────────────────────────────────────────────────

def test_unbounded_count_is_gone():
    out = rolling_form_features(fake_player(25, 8, seed=1), EVENT)
    assert "prior_rounds_count" not in out, "prior_rounds_count counts the whole career — replace it"


def test_veteran_same_in_training_and_serving():
    """8-year regular: lots of history outside the window."""
    full = fake_player(25, 8, seed=2)
    same(rolling_form_features(full, EVENT), rolling_form_features(serving_view(full), EVENT))


def test_part_timer_same_in_training_and_serving():
    """4 events a year: his 'last 20 rounds' reach back years — further
    than serving can see. This is the case sg_last20 currently fails."""
    full = fake_player(4, 8, seed=3)
    same(rolling_form_features(full, EVENT), rolling_form_features(serving_view(full), EVENT))


def test_long_layoff_looks_like_no_history():
    """Last played 500 days ago: nothing he did is inside the window, so
    his features must match a player with no history at all — not
    two-year-old form presented as current."""
    stale = fake_player(25, 3, seed=4, end=EVENT - pd.Timedelta(days=500))
    same(rolling_form_features(stale, EVENT), rolling_form_features(stale.iloc[0:0], EVENT))


def test_row_order_doesnt_matter():
    full = fake_player(25, 3, seed=5)
    shuffled = full.sample(frac=1, random_state=0)
    same(rolling_form_features(full, EVENT), rolling_form_features(shuffled, EVENT))


def test_empty_history_has_every_column():
    """A debutant still needs every feature column (as missing or 0),
    or the model gets a different column set for him."""
    out_new = rolling_form_features(fake_player(25, 1, seed=6).iloc[0:0], EVENT)
    out_vet = rolling_form_features(fake_player(25, 3, seed=6), EVENT)
    assert out_new.keys() == out_vet.keys()
    
    
def rounds_at(days_back: int, n: int) -> pd.DataFrame:
    """n rounds on the same date, days_back before EVENT."""
    date = EVENT - pd.Timedelta(days=days_back)
    return pd.DataFrame([{
        "date": date, "event_id": 0, "round_num": rnd,
        "sg_total": 0.5, "score": 70, "course_par": 72,
        "birdies": 3, "bogies": 1, "doubles_or_worse": 0,
        "pars": 11, "eagles_or_better": 0, "fin_text": "T20",
    } for rnd in range(1, n + 1)])
    
    
def test_rounds_played_365d_counts_the_last_year():
    """
    Recent activity: rounds inside 365 days count, older ones don't, 
    and rounds outside the 400-day window don't exists at all.
    """
    history = pd.concat([
        rounds_at(30, 4),    # last month: made the cut
        rounds_at(100, 2),   # spring: missed the cut
        rounds_at(380, 4),   # 13 months ago: inside the window, outside 365
        rounds_at(500, 4),   # outside the window entirely
    ])
    out = rolling_form_features(history, EVENT)
    assert out["rounds_played_365d"] == 6, f"got {out['rounds_played_365d']}"
    assert out["events_in_window"] == 3, f"got {out['events_in_window']}"
    


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
