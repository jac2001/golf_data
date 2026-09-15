#!/usr/bin/env python3
"""
Walk-Forward Cross-Validation
=============================
Replaces the single 2025 holdout with a rolling evaluation: train on all years
before Y, test on year Y, for every Y we have enough history for. This answers
the question a single split can't: "is the model consistently good, or did it
get lucky on one particular year?"

    fold 1: train 2016-2019 → test 2020
    fold 2: train 2016-2020 → test 2021
    ...
    fold 7: train 2016-2025 → test 2026

Each fold respects time: the model NEVER sees a year later than its test year.

Usage:
    python3 scripts/validation/walk_forward_cv.py
    python3 scripts/validation/walk_forward_cv.py --market top10
    python3 scripts/validation/walk_forward_cv.py --first-test-year 2022

Output:
    outputs/walk_forward_cv.csv — one row per (fold, market) with AUC/Brier/log-loss

────────────────────────────────────────────────────────────────────────────
YOUR PART: three functions marked TODO(you). Everything else is plumbing and
is already written. Suggested order: make_folds → run_fold → summarize.
Run the script after each one — it will tell you what's still missing.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_FILE    = PROJECT_ROOT / "data" / "processed" / "master_training_data_2016_2026.csv"
OUT_CSV      = PROJECT_ROOT / "outputs" / "walk_forward_cv.csv"

# Market name → label column in the training CSV
MARKETS = {"win": "won", "top5": "top5", "top10": "top10", "top20": "top20"}


# ── Provided plumbing (no need to touch) ──────────────────────────────────────

def load_data() -> tuple[pd.DataFrame, list[str]]:
    """Load the master training table and the production feature list.

    The feature list is read straight from the deployed win model pickle, so
    this evaluation uses exactly the features production uses — no drift.
    """
    df = pd.read_csv(DATA_FILE, low_memory=False)
    model = joblib.load(PROJECT_ROOT / "data" / "models" / "win_model_final.pkl")
    features = list(model.feature_names_in_)
    missing = [f for f in features if f not in df.columns]
    if missing:
        raise SystemExit(f"Features missing from training CSV: {missing}")
    return df, features


def build_model() -> CalibratedClassifierCV:
    """Fresh untrained model with the same architecture as production
    (train_final_models.py): constrained Random Forest + isotonic calibration."""
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=5,
        min_samples_split=50,
        min_samples_leaf=25,
        max_features="sqrt",
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    return CalibratedClassifierCV(rf, method="isotonic", cv=3)


def prep_xy(rows: pd.DataFrame, features: list[str], label: str,
            medians: pd.Series) -> tuple[pd.DataFrame, np.ndarray]:
    """Feature matrix + 0/1 label vector for a set of rows.

    `medians` must come from the TRAINING rows — passing test-set medians into
    training-side imputation would be a (small) leak. The caller decides.
    """
    X = rows[features].fillna(medians)
    y = pd.to_numeric(rows[label], errors="coerce").fillna(0).astype(int).values
    return X, y


# ── TODO(you) #1 ──────────────────────────────────────────────────────────────

def make_folds(years: list[int], first_test_year: int, window: int = None) -> list[tuple[list[int], int]]:
    """Return the walk-forward folds as (train_years, test_year) pairs.

    Example with years=[2016..2022], first_test_year=2020:
        [([2016, 2017, 2018, 2019],        2020),
         ([2016, 2017, 2018, 2019, 2020],  2021),
         ([2016, ...,             2021],   2022)]

    Rules:
      - test years run from first_test_year through the latest year available
      - each fold trains on EVERY year strictly before its test year
      - `years` may be unsorted — handle that

    Hint: one loop and a list comprehension (or slice) is enough.
    """
    return [(list(range(max(min(years), test_year - window) if window is not None else min(years), test_year)), test_year) for test_year in sorted(set(years) & set(range(first_test_year, max(years) + 1)))]


# ── TODO(you) #2 ──────────────────────────────────────────────────────────────

def run_fold(df: pd.DataFrame, features: list[str], label: str,
             train_years: list[int], test_year: int,
             half_life: float | None = None) -> dict:
    """Train on train_years, evaluate on test_year. Return a metrics dict:

        {"test_year": ..., "n_train": ..., "n_test": ..., "positives": ...,
         "auc": ..., "brier": ..., "log_loss": ...}

    Steps (each is 1-3 lines):
      1. Split df into train rows and test rows by the `year` column.
      2. Compute feature medians FROM THE TRAINING ROWS ONLY, then use
         prep_xy() for both splits with those same medians.
         (Why train-only? Ask yourself what test-set medians would leak.)
      3. build_model(), fit on train, predict_proba on test — take [:, 1].
      4. Score with roc_auc_score / brier_score_loss / log_loss.

    Careful: log_loss needs `labels=[0, 1]` in case a test year has no
    positives for a rare market.
    """
    df_train = df[df["year"].isin(train_years)]
    df_test = df[df["year"] == test_year]
    
    medians = df_train[features].median()
    X_train, y_train = prep_xy(df_train, features, label, medians)
    X_test, y_test = prep_xy(df_test, features, label, medians)
    
    model = build_model()
    if half_life is not None:
        # Recency weighting: a row half_life years old counts half as much as
        # a current one. Keeps ALL rows (calibration stability) while letting
        # recent seasons dominate the learned relationships.
        age = (test_year - df_train["year"]).clip(lower=1)
        weights = (0.5 ** (age / half_life)).values
        model.fit(X_train, y_train, sample_weight=weights)
    else:
        model.fit(X_train, y_train)
    y_pred = model.predict_proba(X_test)[:, 1]

    auc = roc_auc_score(y_test, y_pred)
    brier = brier_score_loss(y_test, y_pred)
    ll = log_loss(y_test, y_pred, labels=[0, 1])
    return {
        "test_year": test_year,
        "n_train": len(df_train),
        "n_test": len(df_test),
        "positives": int(y_test.sum()),
        "auc": auc,
        "brier": brier,
        "log_loss": ll,
    }



# ── TODO(you) #3 ──────────────────────────────────────────────────────────────

def summarize(results: pd.DataFrame) -> None:
    """Print the season-by-season table plus, per market: mean AUC, the std
    of AUC across folds, and worst fold.

    The std is the headline number — it's what the single 2025 split could
    never show. A model with mean AUC .75 ± .01 and one with .75 ± .06 are
    very different products.

    Format however you like — you're the one reading it.
    """

    for market in results['market'].unique():
        market_results = results[results['market'] == market]
        mean_auc = market_results['auc'].mean()
        std_auc = market_results['auc'].std()
        worst_fold = market_results.loc[market_results['auc'].idxmin()]
        print(f"Market: {market}, Mean AUC: {mean_auc:.3f}, Std AUC: {std_auc:.3f}, Worst Fold: Test Year {worst_fold['test_year']}, AUC {worst_fold['auc']:.3f}")
        

# ── Driver (provided) ─────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Walk-forward CV over the training years")
    ap.add_argument("--market", choices=list(MARKETS), default=None,
                    help="Single market (default: all four)")
    ap.add_argument("--first-test-year", type=int, default=2020,
                    help="Earliest test year (needs >= a few train years before it)")
    ap.add_argument('--window', type=int, default=None, help='Train on only the last N years (default: expanding window)')
    ap.add_argument('--half-life', type=float, default=None,
                    help='Recency-weight training rows: a row this many years old counts half')
    args = ap.parse_args()

    df, features = load_data()
    years = sorted(df["year"].dropna().astype(int).unique())
    print(f"Loaded {len(df):,} rows, {len(features)} features, years {years[0]}–{years[-1]}")

    folds = make_folds(years, args.first_test_year, window=args.window)
    print(f"{len(folds)} folds: test years {[t for _, t in folds]}")

    markets = {args.market: MARKETS[args.market]} if args.market else MARKETS
    rows = []
    for market, label in markets.items():
        for train_years, test_year in folds:
            r = run_fold(df, features, label, train_years, test_year,
                         half_life=args.half_life)
            r["market"] = market
            r['window'] = args.window or 0
            r['half_life'] = args.half_life or 0
            rows.append(r)
            print(f"  {market:<6} {test_year}: AUC={r['auc']:.3f}  Brier={r['brier']:.4f}  "
                  f"log_loss={r['log_loss']:.4f}  (n={r['n_test']}, +{r['positives']})")

    results = pd.DataFrame(rows)
    results.to_csv(OUT_CSV, index=False)
    print(f"\nSaved → {OUT_CSV.relative_to(PROJECT_ROOT)}")
    summarize(results)


if __name__ == "__main__":
    main()
