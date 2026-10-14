"""
Tests for serving_form.recent_par_scoring_field_pct — written first.
Run:  python3 scripts/features/test_serving_form.py

Two kinds of test: small hand-built cases where the answer is obvious,
and PARITY tests that run your function on real past events and require
the exact numbers in the training table. Parity is the whole point.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.features.serving_form import load_form_stats, recent_par_scoring_field_pct  # noqa: E402


def rows(player: str, stat: str, values: list, start: int = 1) -> list[dict]:
    """One form_stats row per value, events R2026001, R2026002, ..."""
    return [{"player_id": player, "stat_id": stat, "tournament_id": f"R2026{start + i:03d}",
             "stat_value": v} for i, v in enumerate(values)]


def frame(*row_lists) -> pd.DataFrame:
    return pd.DataFrame([r for rl in row_lists for r in rl])


def pct(out: pd.DataFrame, player: str, col: str):
    return out.set_index("player_id").loc[player, col]


# ── hand-built ───────────────────────────────────────────────────────────────

def test_lowest_scorer_gets_one():
    """Lower par-5 scoring is better: the lowest average ranks 1.0."""
    fs = frame(rows("A", "143", [4.0, 4.0]), rows("B", "143", [4.5, 4.5]), rows("C", "143", [5.0, 5.0]))
    out = recent_par_scoring_field_pct(fs, ["A", "B", "C"], "R2026010")
    assert pct(out, "A", "recent_par5_scoring_field_pct") == 1.0
    assert pct(out, "C", "recent_par5_scoring_field_pct") == 1 / 3


def test_only_prior_events_count():
    """Event R2026003's own stats (and later) must not leak in."""
    fs = frame(rows("A", "143", [4.0, 4.0, 9.0, 9.0]))   # R2026001..004
    out = recent_par_scoring_field_pct(fs, ["A"], "R2026003")
    assert pct(out, "A", "recent_par5_scoring") == 4.0


def test_last_five_only():
    fs = frame(rows("A", "142", [9, 9, 3, 3, 3, 3, 3]))  # 7 events; last 5 are all 3
    out = recent_par_scoring_field_pct(fs, ["A"], "R2026099")
    assert pct(out, "A", "recent_par4_scoring") == 3.0


def test_nan_in_last_five_is_not_replaced():
    """Training takes tail(5) THEN drops NaN: a bad value in the last 5
    leaves 4 to average; it doesn't reach back for a 6th."""
    fs = frame(rows("A", "142", [9, 2, 2, 2, "n/a", 2]))  # last 5: 2,2,2,n/a,2
    out = recent_par_scoring_field_pct(fs, ["A"], "R2026099")
    assert pct(out, "A", "recent_par4_scoring") == 2.0


def test_player_with_no_history_is_nan():
    fs = frame(rows("A", "299", [70, 68]))
    out = recent_par_scoring_field_pct(fs, ["A", "ROOKIE"], "R2026099")
    assert np.isnan(pct(out, "ROOKIE", "recent_par3_scoring"))
    assert np.isnan(pct(out, "ROOKIE", "recent_par3_scoring_field_pct"))
    assert pct(out, "A", "recent_par3_scoring_field_pct") == 1.0   # alone in the ranking


def test_one_row_per_field_player_and_all_columns():
    fs = frame(rows("A", "299", [70]))
    out = recent_par_scoring_field_pct(fs, ["A", "B"], "R2026099")
    assert sorted(out["player_id"]) == ["A", "B"]
    for c in ("recent_par3_scoring", "recent_par4_scoring", "recent_par5_scoring"):
        assert c in out.columns and f"{c}_field_pct" in out.columns, c


# ── parity with the training table ──────────────────────────────────────────

_FORM = None
_TRAIN = None


def _parity(tid: str):
    global _FORM, _TRAIN
    if _FORM is None:
        _FORM = load_form_stats()
        cols = ["tournament_id", "player_id"] + [f"recent_par{k}_scoring_field_pct" for k in (3, 4, 5)]
        _TRAIN = pd.read_csv(Path(__file__).resolve().parents[2] / "data" / "processed"
                             / "master_training_data_2016_2026.csv", usecols=cols, low_memory=False)
        _TRAIN["player_id"] = _TRAIN["player_id"].astype(str)
    t = _TRAIN[_TRAIN["tournament_id"] == tid].set_index("player_id")
    out = recent_par_scoring_field_pct(_FORM, t.index.tolist(), tid).set_index("player_id")
    for k in (3, 4, 5):
        c = f"recent_par{k}_scoring_field_pct"
        a, b = t[c], out[c].reindex(t.index)
        assert (a.isna() == b.isna()).all(), f"{tid} {c}: missing values differ from training"
        both = a.notna()
        assert np.allclose(a[both], b[both], atol=1e-12), \
            f"{tid} {c}: max diff {np.abs(a[both] - b[both]).max():.3g} vs training"


def test_parity_2025_masters():
    _parity("R2025014")


def test_parity_2024_masters():
    _parity("R2024014")


def test_parity_2025_event_475():
    _parity("R2025475")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except (AssertionError, NotImplementedError, KeyError) as e:
            failed += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
