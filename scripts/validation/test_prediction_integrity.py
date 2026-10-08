"""
Tests for the prediction integrity gate.  Run:  python3 scripts/validation/test_prediction_integrity.py

The two real archives are the point: Biltmore (2026-09) was published with
DG decompositions for 1% of the field and must be blocked; Bank of Utah was
clean and must pass. If someone loosens a threshold until Biltmore passes,
this fails.
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from prediction_integrity import check  # noqa: E402

ARCHIVE = HERE.parents[1] / "data" / "prediction_tracking"


def field(n=60, cov=1.0, sim_agrees=True):
    df = pd.DataFrame({"player_name": [f"P{i}" for i in range(n)],
                       "win_prob": [1 / (i + 2) for i in range(n)]})
    k = int(n * cov)
    df["final_pred"] = [1.0 - i * 0.01 if i < k else None for i in range(n)][::-1] if cov < 1 else [1.0 - i * 0.01 for i in range(n)]
    df["dg_win"] = df["win_prob"]
    df["win_prob_sim"] = df["win_prob"] if sim_agrees else df["win_prob"][::-1].values
    return df


def test_real_biltmore_blocked():
    fails, _ = check(pd.read_csv(ARCHIVE / "pred_R2026557.csv"))
    assert any("covers only" in f for f in fails), fails


def test_real_bank_of_utah_passes():
    fails, _ = check(pd.read_csv(ARCHIVE / "pred_R2026554.csv"))
    assert fails == [], fails


def test_partial_coverage_blocked():
    fails, _ = check(field(cov=0.5))
    assert any("covers only 50%" in f for f in fails), fails


def test_top_ten_gap_blocked_even_when_coverage_is_high():
    df = field()
    df.loc[df["win_prob"].idxmax(), "final_pred"] = None   # 98% coverage, but the favourite has none
    fails, _ = check(df)
    assert any("top 10" in f for f in fails), fails


def test_simulation_disagreement_blocked():
    fails, _ = check(field(sim_agrees=False))
    assert any("simulation disagrees" in f for f in fails), fails


def test_missing_merge_blocked():
    fails, _ = check(field().drop(columns=["final_pred"]))
    assert any("missing entirely" in f for f in fails), fails


def test_clean_field_passes():
    assert check(field())[0] == []


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    bad = 0
    for t in tests:
        try:
            t(); print(f"✔ {t.__name__}")
        except AssertionError as e:
            bad += 1; print(f"✖ {t.__name__}: {e}")
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
