#!/usr/bin/env python3
"""
Train score regression model: predicts 4-round to-par total (relative to field avg).

WHY WE SWITCHED FROM RANDOM FOREST TO XGBOOST
==============================================
Both are "ensemble" methods — they combine many decision trees into one prediction.
The key difference is HOW they build the trees:

  Random Forest (what we had):
    - Builds all trees INDEPENDENTLY, in parallel
    - Each tree sees a random subset of data + features
    - Final prediction = average of all trees
    - Problem: averaging naturally pulls predictions toward the mean.
      A player projected to shoot -15 might get averaged down to -7 because
      most trees "hedge" toward more common outcomes.

  XGBoost (Gradient Boosting, what we're switching to):
    - Builds trees SEQUENTIALLY, each one fixing the errors of the previous
    - Each new tree focuses on the players the model currently gets most wrong
    - Uses calculus (gradient descent) to find the direction that reduces error fastest
    - Result: better at learning extreme values, like tournament winners shooting -18

ANALOGY:
  RF = 200 forecasters who each guess independently, then you average them
  XGBoost = 200 forecasters where each one studies the previous forecaster's
            mistakes and tries to correct them
"""

import glob
import joblib
import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODEL_DIR     = PROJECT_ROOT / "data" / "models"

# Same feature set as before — no changes needed here
SCORE_FEATURES = [
    "season_sg_total", "season_sg_ott", "season_sg_app", "season_sg_arg",
    "season_sg_t2g", "season_sg_putt", "season_sg_arg_vs_field",
    "season_sg_total_vs_field", "season_sg_ott_vs_field",
    "season_sg_app_vs_field", "season_sg_putt_vs_field",
    "season_sg_ott_field_pct", "season_sg_app_field_pct", "season_sg_putt_field_pct",
    "recent_sg_weighted", "recent_sg_trend",
    "recent_sg_ott_weighted", "recent_sg_app_weighted", "recent_sg_putt_weighted",
    "hist_times_played", "hist_avg_finish", "hist_best_finish",
    "hist_wins", "hist_top5s", "hist_top10s", "hist_cut_rate", "hist_missed_cuts",
    "has_won_here", "has_course_history", "has_made_cut_here",
    "venue_avg_finish", "venue_finish_std",
    "form_trend", "finish_consistency", "recent_top10s", "recent_top5s",
    "recent_cuts_pct", "recent_birdie_avg", "recent_scoring_avg",
    "dg_fit_ott", "dg_fit_app", "dg_fit_arg", "dg_fit_putt",
    "dg_fit_total", "predictive_sg_weighted",
    "world_rank",
]


def to_par_numeric(series):
    """Convert to_par to float: 'E'->0, '+3'->3, '-12'->-12, numeric pass-through."""
    def _parse(v):
        if pd.isna(v): return np.nan
        s = str(v).strip()
        if s in ("E", "e", "0", "0.0"): return 0.0
        try: return float(s)
        except: return np.nan
    return series.map(_parse)


def main():
    # ── Load data ─────────────────────────────────────────────────────────────
    files = sorted(glob.glob(str(PROCESSED_DIR / "master_training_data_*.csv")))
    if not files:
        print(f"ERROR: No master_training_data_*.csv found in {PROCESSED_DIR}")
        return
    data_file = files[-1]
    print(f"Loading: {data_file}")
    df = pd.read_csv(data_file)
    print(f"  Raw rows: {len(df)}")

    # ── Filter to 4-round completers only ────────────────────────────────────
    # We exclude missed cuts because a 2-round to_par (+8) is a different
    # measurement than a 4-round to_par (-5). Mixing them confuses the model.
    df = df[df["rounds_played"] == 4].copy()
    print(f"  After rounds_played==4 filter: {len(df)}")

    # ── Parse the target variable ─────────────────────────────────────────────
    df["to_par_num"] = to_par_numeric(df["to_par"])
    df = df.dropna(subset=["to_par_num"])
    print(f"  After dropping NaN to_par: {len(df)}")

    # ── Compute target: score relative to field average ───────────────────────
    # Instead of predicting absolute to-par (e.g., -15 at a low-scoring course),
    # we predict how many strokes BETTER or WORSE than the field average.
    # This removes course difficulty from the equation — a -3 vs field is
    # equally good whether the winner shot -20 or -10.
    # Example: if field avg is -8 and player shoots -12, score_vs_field = -4
    field_avg = df.groupby(["tournament_id", "year"])["to_par_num"].transform("mean")
    df["score_vs_field"] = df["to_par_num"] - field_avg
    print(f"\n  Target (score_vs_field) distribution:")
    print(f"    mean={df['score_vs_field'].mean():.2f}  std={df['score_vs_field'].std():.2f}")
    print(f"    min={df['score_vs_field'].min():.1f}  max={df['score_vs_field'].max():.1f}")

    # ── Train / validation / test split ──────────────────────────────────────
    # Train:      2016-2023  (model learns patterns)
    # Validation: 2024       (used during training for early stopping — see below)
    # Test:       2025       (held out completely, never seen during training)
    #
    # Why do we need a VALIDATION set separate from the test set?
    # Early stopping (explained below) watches a validation set to decide when
    # to stop building trees. If we used the test set for this, we'd be
    # "peeking" at test data during training — a form of data leakage that
    # makes our evaluation metrics look better than they really are.
    train = df[df["year"].astype(int) <= 2023].copy()
    val   = df[df["year"].astype(int) == 2024].copy()
    test  = df[df["year"].astype(int) == 2025].copy()
    print(f"\n  Train: {len(train)} rows | Val: {len(val)} rows | Test: {len(test)} rows")

    feats = [f for f in SCORE_FEATURES if f in df.columns]
    missing = [f for f in SCORE_FEATURES if f not in df.columns]
    if missing:
        print(f"  Missing features (skipped): {missing}")
    print(f"  Using {len(feats)} features")

    X_train = train[feats].fillna(0)
    y_train = train["score_vs_field"]
    X_val   = val[feats].fillna(0)
    y_val   = val["score_vs_field"]
    X_test  = test[feats].fillna(0)
    y_test  = test["score_vs_field"]

    # ── XGBoost hyperparameters (with explanations) ───────────────────────────
    #
    # n_estimators=1000
    #   Maximum number of trees to build. With early stopping we rarely hit
    #   this limit — the model stops when it stops improving.
    #
    # learning_rate=0.05
    #   How much each tree contributes to the final prediction (aka "eta").
    #   Lower = each tree has less influence = more trees needed = better generalization.
    #   Think of it as step size when walking toward a solution:
    #     - Too large: you overshoot and bounce around
    #     - Too small: you get there eventually but need many more steps
    #   0.05 is a solid default for tabular data.
    #
    # max_depth=5
    #   Maximum depth of each tree. Shallower trees = simpler rules per tree,
    #   but with 1000 of them it adds up. RF used depth=8; XGBoost works
    #   better with shallower trees (4-6) because sequential training
    #   compensates with more trees, not deeper ones.
    #
    # subsample=0.8
    #   Each tree only sees 80% of training rows (randomly selected).
    #   This is "stochastic" gradient boosting — adds randomness to prevent
    #   overfitting, similar to how RF bootstraps its data.
    #
    # colsample_bytree=0.7
    #   Each tree only considers 70% of features (randomly selected).
    #   Like RF's max_features — prevents the model from always relying on
    #   the same few dominant features and forces it to find redundant signals.
    #
    # min_child_weight=5
    #   A leaf node must have at least this many samples (weighted).
    #   Prevents splits on very small groups. Higher = more conservative.
    #   RF equivalent: min_samples_leaf.
    #
    # gamma=0.1
    #   Minimum loss reduction required to make a split. Acts as a penalty
    #   for complexity — a split only happens if it reduces error by at least
    #   this much. Helps prune useless splits.
    #
    # reg_alpha=0.1, reg_lambda=1.0
    #   L1 and L2 regularization on the leaf weights (the actual predicted values).
    #   L1 (alpha) tends to drive weak feature weights to zero (feature selection).
    #   L2 (lambda) smooths all weights toward zero (reduces overfitting).
    #   These are unique to XGBoost — RF has no equivalent.
    #
    # early_stopping_rounds=50
    #   If the validation MAE hasn't improved in 50 consecutive rounds,
    #   stop building trees. This is the key advantage: instead of guessing
    #   how many trees to use, the model tells you when more trees stop helping.
    #
    # eval_metric="mae"
    #   Use Mean Absolute Error to decide when to stop. MAE = average absolute
    #   error in strokes, which is directly interpretable ("off by X strokes").
    #
    print("\nTraining XGBRegressor...")
    model = XGBRegressor(
        n_estimators        = 1000,
        learning_rate       = 0.05,
        max_depth           = 5,
        subsample           = 0.8,
        colsample_bytree    = 0.7,
        min_child_weight    = 5,
        gamma               = 0.1,
        reg_alpha           = 0.1,
        reg_lambda          = 1.0,
        early_stopping_rounds = 50,
        eval_metric         = "mae",
        random_state        = 42,
        n_jobs              = -1,
        verbosity           = 0,   # suppress XGBoost's own output
    )

    # Pass the validation set so early stopping can monitor it
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    best_n = model.best_iteration + 1
    print(f"  Early stopping: used {best_n} trees out of {model.n_estimators} max")

    # ── Evaluate ──────────────────────────────────────────────────────────────
    #
    # MAE (Mean Absolute Error): average absolute difference between
    #   predicted and actual scores. A MAE of 3.5 means predictions are
    #   off by 3.5 strokes on average. Directly interpretable.
    #
    # RMSE (Root Mean Squared Error): like MAE but squares errors first,
    #   so large errors are penalized more heavily. Always >= MAE.
    #   If RMSE >> MAE, the model makes occasional very large errors.
    #
    # The gap between train and test MAE tells you about overfitting:
    #   - Small gap (< 0.5): model generalizes well
    #   - Large gap (> 1.5): model memorized training data, won't generalize
    #
    preds_train = model.predict(X_train)
    preds_val   = model.predict(X_val)
    preds_test  = model.predict(X_test)

    print(f"\n  Train MAE: {mean_absolute_error(y_train, preds_train):.3f} | "
          f"RMSE: {root_mean_squared_error(y_train, preds_train):.3f}")
    print(f"  Val   MAE: {mean_absolute_error(y_val,   preds_val):.3f}  | "
          f"RMSE: {root_mean_squared_error(y_val,   preds_val):.3f}")
    print(f"  Test  MAE: {mean_absolute_error(y_test,  preds_test):.3f}  | "
          f"RMSE: {root_mean_squared_error(y_test,  preds_test):.3f}")

    # ── Prediction range check ────────────────────────────────────────────────
    # This is the key improvement over RF: we expect the test predictions
    # to have a wider spread (lower min, higher max) than RF produced.
    # A good score_vs_field prediction should range roughly -8 to +5.
    pred_series = pd.Series(preds_test)
    print(f"\n  Test prediction spread (score vs field avg):")
    print(f"    min={pred_series.min():.2f}  mean={pred_series.mean():.2f}  "
          f"max={pred_series.max():.2f}  std={pred_series.std():.2f}")
    print(f"    (Target: winners ~-6 to -10, bubble ~+2 to +4 vs field avg)")

    # ── Calibration: fit a linear stretch on the 2025 holdout ────────────────
    #
    # WHAT IS CALIBRATION?
    # The model predicts score_vs_field values that are systematically
    # compressed toward zero — a known trait of gradient boosting and all
    # ensemble regression models. The model predicts the CONDITIONAL MEAN
    # (expected outcome), so extreme values get averaged away.
    #
    # Example without calibration:
    #   True winner shoots  -10 vs field | model predicts  -6
    #   True median player shoots -1     | model predicts  -0.5
    #   True bad finisher   +5 vs field  | model predicts  +2
    #
    # The RANKINGS are correct (winner > median > bad) but the MAGNITUDES
    # are wrong. Calibration fixes the magnitudes by learning a linear
    # mapping from compressed predictions to realistic values.
    #
    # HOW LINEAR CALIBRATION WORKS:
    #   We fit: actual_score = slope × raw_prediction + intercept
    #
    #   If slope > 1: the model is under-predicting the spread (most common)
    #                 calibration will stretch predictions outward
    #   If intercept ≠ 0: there's a systematic bias (model always too high/low)
    #
    # We fit this on the 2025 HOLDOUT — data the model has never seen.
    # This gives us an unbiased estimate of the real-world gap.
    #
    # After calibration, a player predicted at -6 (raw) might become -9
    # (calibrated), which better matches what tournament winners actually shoot.
    #
    print("\n── Calibration (fit on 2025 holdout) ──────────────────────────────")

    # Reshape for sklearn: needs (n, 1) column matrix, not 1D array
    X_cal = preds_test.reshape(-1, 1)
    y_cal = y_test.values  # actual score_vs_field for 2025

    cal_model = LinearRegression()
    cal_model.fit(X_cal, y_cal)

    slope     = float(cal_model.coef_[0])
    intercept = float(cal_model.intercept_)
    print(f"  slope={slope:.4f}  intercept={intercept:.4f}")
    print(f"  Interpretation: a raw prediction of -5.0 becomes "
          f"{slope * -5.0 + intercept:.1f} after calibration")

    # Measure improvement: how much does calibration reduce MAE on 2025 holdout?
    preds_calibrated = slope * preds_test + intercept
    mae_raw = mean_absolute_error(y_cal, preds_test)
    mae_cal = mean_absolute_error(y_cal, preds_calibrated)
    print(f"  Test MAE before calibration: {mae_raw:.3f}")
    print(f"  Test MAE after  calibration: {mae_cal:.3f}  "
          f"({'better' if mae_cal < mae_raw else 'no improvement — slope near 1'})")

    # Show how the prediction range changes after calibration
    cal_series = pd.Series(preds_calibrated)
    print(f"  Calibrated spread: min={cal_series.min():.1f}  "
          f"mean={cal_series.mean():.1f}  max={cal_series.max():.1f}  "
          f"std={cal_series.std():.2f}")

    # ── Feature importance (gain-based) ──────────────────────────────────────
    # XGBoost gives us gain-based importance: how much each feature
    # reduced error across all splits where it was used.
    # This is more reliable than RF's impurity-based importance,
    # which can be biased toward high-cardinality features.
    fi = (pd.Series(model.feature_importances_, index=feats)
          .sort_values(ascending=False)
          .head(15))
    print("\n  Top 15 features (gain importance):")
    print(fi.to_string())

    # ── Save model, features, and calibration parameters ─────────────────────
    MODEL_DIR.mkdir(exist_ok=True)
    model_path = MODEL_DIR / "score_model_final.pkl"
    feats_path = MODEL_DIR / "score_model_features.txt"
    cal_path   = MODEL_DIR / "score_model_calibration.json"

    joblib.dump(model, model_path)
    feats_path.write_text("\n".join(feats))

    # Calibration is stored as a simple JSON dict so predict_tournament.py
    # can load it without needing to import sklearn or joblib.
    # The 'n_cal' field records how many points we fit on, so we can
    # sanity-check it hasn't been fit on too small a sample.
    cal_data = {
        "slope":     slope,
        "intercept": intercept,
        "n_cal":     int(len(y_cal)),
        "mae_raw":   round(mae_raw, 4),
        "mae_calibrated": round(mae_cal, 4),
        "note": (
            "Applied as: calibrated = slope * raw_prediction + intercept. "
            "Fit on 2025 holdout (never seen during training)."
        ),
    }
    cal_path.write_text(json.dumps(cal_data, indent=2))

    print(f"\n  Saved model       -> {model_path}")
    print(f"  Saved features    -> {feats_path}")
    print(f"  Saved calibration -> {cal_path}")
    print(f"\nDone. Run predict_tournament.py to generate new projected scores.")


if __name__ == "__main__":
    main()
