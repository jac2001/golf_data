"""
compare_retrain.py — does a candidate training table beat the production
recipe, scored on the features serving actually produces?

First used Oct 15, 2026 (retrain step 4); keep it for the January retrain.
  python3 scripts/validation/compare_retrain.py --candidate <master csv> [--production <master csv>]
Lessons from the first run (stats review): score only years that played
no part in choosing features (2025 picked the production 58 features, so
it's in-sample), drop known-bad events from BOTH tables, and repeat over
several fit seeds before believing a gap.

Both models are scored on DATE-ORDERED test features (what serving computes
since 2f10e89). They differ only in what they were trained on:
  A = production recipe: id-ordered table (data/processed/master_training_data_2016_2026.csv)
  B = candidate:         date-ordered table, corrected data (build_date_fixed)

1. Walk-forward, test years 2024-2026: A and B both trained on years < Y.
2. Ship decision: A as production is today (fit on years < 2025) vs B fit on
   years < 2026, both scored on 2026.

Exact trainer setup (train_final_models.py): the production models' 58
features, RandomForest(100, depth 5, min_split 50, min_leaf 25, sqrt,
balanced_subsample) in isotonic CalibratedClassifierCV(cv=3), half-life-2
recency weights, NaN -> training medians. Bootstrap by EVENT for the
B-minus-A difference.
"""
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

warnings.simplefilter("ignore")
ROOT = Path("/Users/jacklegnon/Desktop/golf_data")
S = Path(__file__).resolve().parent
import argparse as _ap
_p = _ap.ArgumentParser()
_p.add_argument("--candidate", required=True, help="date-ordered master_training_data CSV")
_p.add_argument("--production", default=str(ROOT / "data/processed/master_training_data_2016_2026.csv"))
_ARGS = _p.parse_args()
FEATS = list(joblib.load(ROOT / "data/models/win_model_final.pkl").feature_names_in_)
TARGETS = ["won", "top5", "top10"]


BAD_EVENTS = {"R2021535"}   # a copy of the 2025 U.S. Open (fix_mislabeled_events.py)


def load(path):
    d = pd.read_csv(path, low_memory=False)
    d = d[~d["tournament_id"].isin(BAD_EVENTS)]
    d["player_id"] = d["player_id"].astype(str)
    d["field_size"] = d.groupby("tournament_id")["player_id"].transform("count")
    d["no_cut"] = (d["field_size"] <= 90).astype(int)
    return d.dropna(subset=[t for t in TARGETS if t in d.columns])


A_TBL = load(_ARGS.production)
B_TBL = load(_ARGS.candidate)


def fit(train, target):
    med = train[FEATS].median(numeric_only=True)
    base = RandomForestClassifier(n_estimators=100, max_depth=5, min_samples_split=50, min_samples_leaf=25,
                                  max_features="sqrt", random_state=42, n_jobs=-1,
                                  class_weight="balanced_subsample")
    m = CalibratedClassifierCV(estimator=base, method="isotonic", cv=3)
    w = 0.5 ** (((train["year"].max() + 1) - train["year"]) / 2.0)
    m.fit(train[FEATS].fillna(med), train[target], sample_weight=w.values)
    return m, med


def score(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return log_loss(y, p, labels=[0, 1]), brier_score_loss(y, p), (roc_auc_score(y, p) if y.nunique() > 1 else np.nan)


def boot(test, pa, pb, target, n=1000, seed=7):
    """Event-level bootstrap of log-loss(B) - log-loss(A); negative = B better."""
    rng = np.random.default_rng(seed)
    ev = test["tournament_id"].values
    uniq = np.unique(ev)
    idx = {e: np.where(ev == e)[0] for e in uniq}
    y = test[target].values
    la = -(y * np.log(np.clip(pa, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - pa, 1e-6, 1)))
    lb = -(y * np.log(np.clip(pb, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - pb, 1e-6, 1)))
    diffs = []
    for _ in range(n):
        pick = np.concatenate([idx[e] for e in rng.choice(uniq, len(uniq))])
        diffs.append(lb[pick].mean() - la[pick].mean())
    return np.percentile(diffs, [2.5, 97.5])


rows = []
print("== 1. Walk-forward (both scored on date-ordered test features)")
for Y in (2024, 2025, 2026):
    test = B_TBL[B_TBL["year"] == Y]
    for t in TARGETS:
        ma, meda = fit(A_TBL[A_TBL["year"] < Y], t)
        mb, medb = fit(B_TBL[B_TBL["year"] < Y], t)
        pa = ma.predict_proba(test[FEATS].fillna(meda))[:, 1]
        pb = mb.predict_proba(test[FEATS].fillna(medb))[:, 1]
        la, ba, aa = score(test[t], pa)
        lb, bb, ab = score(test[t], pb)
        lo, hi = boot(test, pa, pb, t)
        rows.append(("walk-forward", Y, t, la, lb, (lb - la) / la, aa, ab, ba, bb, lo, hi, len(test)))
        print(f"  {Y} {t:6} logloss A {la:.4f} B {lb:.4f} ({(lb-la)/la:+.2%}) | AUC A {aa:.3f} B {ab:.3f} | "
              f"B-A 95% CI [{lo:+.4f}, {hi:+.4f}]")

print("\n== 2. Ship decision: production recipe (id, < 2025) vs candidate (date, < 2026), scored on 2026")
test = B_TBL[B_TBL["year"] == 2026]
for t in TARGETS:
    ma, meda = fit(A_TBL[A_TBL["year"] < 2025], t)
    mb, medb = fit(B_TBL[B_TBL["year"] < 2026], t)
    pa = ma.predict_proba(test[FEATS].fillna(meda))[:, 1]
    pb = mb.predict_proba(test[FEATS].fillna(medb))[:, 1]
    la, ba, aa = score(test[t], pa)
    lb, bb, ab = score(test[t], pb)
    lo, hi = boot(test, pa, pb, t)
    rows.append(("ship", 2026, t, la, lb, (lb - la) / la, aa, ab, ba, bb, lo, hi, len(test)))
    print(f"  2026 {t:6} logloss A {la:.4f} B {lb:.4f} ({(lb-la)/la:+.2%}) | AUC A {aa:.3f} B {ab:.3f} | "
          f"Brier A {ba:.5f} B {bb:.5f} | B-A 95% CI [{lo:+.4f}, {hi:+.4f}] | {test['tournament_id'].nunique()} events")

pd.DataFrame(rows, columns=["test", "year", "target", "logloss_A", "logloss_B", "rel_change", "auc_A", "auc_B",
                            "brier_A", "brier_B", "ci_lo", "ci_hi", "n"]).to_csv("compare_retrain_results.csv", index=False)
print("\nwrote step4_results.csv")
