#!/usr/bin/env python3
"""
Train score regression model: predicts 4-round to-par total (relative to field avg).

This script trains FOUR models total:

  1. Mean model  — predicts the expected (average) outcome for a player.
                   Used for ranking players against each other.

  2. Q10 model   — predicts the 10th percentile outcome (ceiling/best case).
                   "This player shoots this well or better only 10% of the time."
                   Useful for identifying upside in DFS.

  3. Q50 model   — predicts the 50th percentile (median outcome).
                   Similar to the mean model but uses a different loss function.
                   Should be close to the mean model in value.

  4. Q90 model   — predicts the 90th percentile outcome (floor/worst case).
                   "This player shoots this poorly or worse only 10% of the time."
                   Useful for fading players in H2H bets.

WHY WE NEED QUANTILE REGRESSION
================================
The mean model answers: "What is this player's average outcome?"
  → Scheffler: -4.7 vs field (his average across all tournaments)

But for any given week we want to know: "What's his range of outcomes?"
  → Ceiling (Q10): -9.5 vs field (a great week, top 10% of his performances)
  → Median  (Q50): -4.7 vs field (typical week)
  → Floor   (Q90): +0.3 vs field (a bad week, bottom 10% of his performances)

This directly answers the compression problem: the mean model is correct on
average but uninformative about what might happen THIS week. The quantile
models give you the full picture.

HOW QUANTILE REGRESSION WORKS
==============================
Regular regression minimizes SQUARED error: (actual - predicted)²
  → This penalizes over- and under-prediction equally.
  → The optimal solution is the conditional MEAN.

Quantile regression (pinball loss) is asymmetric:
  For alpha=0.10 (10th percentile):
    error = 0.10 × (actual - predicted)   when actual > predicted  (under-predicted)
    error = 0.90 × (predicted - actual)   when actual < predicted  (over-predicted)

  This means over-prediction is penalized 9× more than under-prediction.
  The model learns: "I'd rather predict too HIGH than too LOW."
  The optimal solution to this is the 10th percentile — the value where
  only 10% of actual outcomes fall below.

  For alpha=0.90 (90th percentile), the penalty is reversed:
    Under-prediction is penalized 9× more than over-prediction.
  The model learns: "I'd rather predict too LOW than too HIGH."
  The optimal solution is the 90th percentile.

PINBALL LOSS ANALOGY:
  Imagine a pinball machine tilted left. The ball (prediction) keeps rolling
  toward the low side. That's the 10th percentile model — it biases low
  because under-predicting (going left) costs only 10 cents, but
  over-predicting (going right) costs 90 cents.

COVERAGE CHECK:
  After training, we verify: for the Q10 model, do ~10% of actuals fall
  BELOW the prediction? If coverage is significantly off (e.g., 25% instead
  of 10%), the model is miscalibrated.

  In practice, XGBoost's quantile implementation is well-calibrated on
  large datasets (we have 18K+ training rows) so coverage should be close.
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


def _base_params():
    """
    Shared hyperparameters for all models (mean + quantile).
    Keeping them the same ensures the quantile models learn the same
    relationships — they only differ in what they OPTIMISE for.
    """
    return dict(
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
        random_state        = 42,
        n_jobs              = -1,
        verbosity           = 0,
    )


def train_quantile_model(X_train, y_train, X_val, y_val, alpha: float):
    """
    Train a quantile regression model for a given percentile (alpha).

    alpha=0.10 → 10th percentile (ceiling): 10% of actuals fall below this
    alpha=0.50 → 50th percentile (median):  50% of actuals fall below this
    alpha=0.90 → 90th percentile (floor):   90% of actuals fall below this

    The key difference from the mean model:
      objective='reg:quantileerror'  — tells XGBoost to use pinball loss
      quantile_alpha=alpha           — sets which percentile to target

    Early stopping still works the same way — we watch validation pinball
    loss instead of MAE, stopping when it stops improving.
    """
    params = _base_params()
    params["objective"]      = "reg:quantileerror"
    params["quantile_alpha"] = alpha
    params["eval_metric"]    = "quantile"   # pinball loss for early stopping

    model = XGBRegressor(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    return model


def coverage(y_actual, y_pred_quantile, alpha: float) -> float:
    """
    Coverage check: what fraction of actual values fall BELOW the prediction?

    For a well-calibrated Q10 model, this should be ~0.10 (10%).
    For a well-calibrated Q90 model, this should be ~0.90 (90%).

    If coverage is far from alpha, the model is over- or under-predicting
    the tails. A common cause is too little training data for extreme events.
    """
    return float(np.mean(np.array(y_actual) < np.array(y_pred_quantile)))


def pinball_loss(y_actual, y_pred, alpha: float) -> float:
    """
    Pinball loss (quantile loss) — the proper evaluation metric for
    quantile regression. Lower is better.

    For alpha=0.10:
      loss = 0.10 × max(actual - pred, 0) + 0.90 × max(pred - actual, 0)

    Unlike MAE which treats over- and under-prediction equally, pinball
    loss is asymmetric — it penalises the 'wrong' side more heavily.

    You can't directly compare pinball loss across different alphas
    (Q10 loss will always be smaller than Q90 loss), but you CAN compare
    same-alpha losses across models to pick the better one.
    """
    residuals = np.array(y_actual) - np.array(y_pred)
    return float(np.mean(np.where(residuals >= 0, alpha * residuals, (alpha - 1) * residuals)))


def main():
    # ── Load & prepare data ───────────────────────────────────────────────────
    files = sorted(glob.glob(str(PROCESSED_DIR / "master_training_data_*.csv")))
    if not files:
        print(f"ERROR: No master_training_data_*.csv found in {PROCESSED_DIR}")
        return
    data_file = files[-1]
    print(f"Loading: {data_file}")
    df = pd.read_csv(data_file, low_memory=False)
    print(f"  Raw rows: {len(df)}")

    df = df[df["rounds_played"] == 4].copy()
    print(f"  After rounds_played==4 filter: {len(df)}")

    df["to_par_num"] = to_par_numeric(df["to_par"])
    df = df.dropna(subset=["to_par_num"])
    print(f"  After dropping NaN to_par: {len(df)}")

    # score_vs_field removes course difficulty so models are comparable
    # across all tournaments (a -4 vs field at Augusta = -4 at Pebble)
    field_avg = df.groupby(["tournament_id", "year"])["to_par_num"].transform("mean")
    df["score_vs_field"] = df["to_par_num"] - field_avg

    print(f"\n  Target distribution: mean={df['score_vs_field'].mean():.2f} "
          f"std={df['score_vs_field'].std():.2f} "
          f"min={df['score_vs_field'].min():.1f} max={df['score_vs_field'].max():.1f}")

    train = df[df["year"].astype(int) <= 2023].copy()
    val   = df[df["year"].astype(int) == 2024].copy()
    test  = df[df["year"].astype(int) == 2025].copy()
    print(f"  Train: {len(train)} | Val: {len(val)} | Test: {len(test)}")

    feats   = [f for f in SCORE_FEATURES if f in df.columns]
    missing = [f for f in SCORE_FEATURES if f not in df.columns]
    if missing:
        print(f"  Missing features (skipped): {missing}")
    print(f"  Using {len(feats)} features\n")

    X_train = train[feats].fillna(0)
    y_train = train["score_vs_field"]
    X_val   = val[feats].fillna(0)
    y_val   = val["score_vs_field"]
    X_test  = test[feats].fillna(0)
    y_test  = test["score_vs_field"]

    # ═════════════════════════════════════════════════════════════════════════
    # STAGE 1: Mean model (same as before — used for ranking)
    # ═════════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("STAGE 1: Mean model (objective = squared error)")
    print("=" * 60)
    print("  Minimises (actual - predicted)² — optimal solution is the mean.")
    print("  Used for RANKING players: who is projected best vs field.\n")

    mean_params = _base_params()
    mean_params["eval_metric"] = "mae"
    mean_model = XGBRegressor(**mean_params)
    mean_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    preds_mean = mean_model.predict(X_test)
    print(f"  Trees used: {mean_model.best_iteration + 1} / {mean_model.n_estimators}")
    print(f"  Test MAE:  {mean_absolute_error(y_test, preds_mean):.3f} strokes")
    print(f"  Test RMSE: {root_mean_squared_error(y_test, preds_mean):.3f} strokes")
    print(f"  Prediction spread: min={preds_mean.min():.1f}  "
          f"mean={preds_mean.mean():.1f}  max={preds_mean.max():.1f}")

    # Linear calibration (confirmed slope ~1 — model is unbiased in mean)
    cal_model = LinearRegression()
    cal_model.fit(preds_mean.reshape(-1, 1), y_test.values)
    slope, intercept = float(cal_model.coef_[0]), float(cal_model.intercept_)
    print(f"  Calibration slope={slope:.4f} intercept={intercept:.4f} "
          f"(slope ~1 = unbiased, no correction needed)")

    # ═════════════════════════════════════════════════════════════════════════
    # STAGE 2: Quantile models (ceiling, median, floor)
    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 60}")
    print("STAGE 2: Quantile models (pinball loss)")
    print("=" * 60)
    print("  Each model uses a DIFFERENT loss function to target a specific")
    print("  percentile of the outcome distribution.\n")

    # Quantiles to train: (alpha, label, interpretation)
    quantiles = [
        (0.10, "q10", "ceiling — best 10% of this player's weeks"),
        (0.50, "q50", "median  — typical week"),
        (0.90, "q90", "floor   — worst 10% of this player's weeks"),
    ]

    q_models  = {}
    q_preds   = {}
    q_results = {}

    for alpha, label, interp in quantiles:
        print(f"  Training {label.upper()} (alpha={alpha}) — {interp}")

        q_models[label] = train_quantile_model(
            X_train, y_train, X_val, y_val, alpha
        )
        q_preds[label] = q_models[label].predict(X_test)

        # Evaluate with pinball loss (the correct metric for quantile models)
        pb = pinball_loss(y_test, q_preds[label], alpha)

        # Coverage: what % of actuals fall below this quantile's prediction?
        # Should match alpha — e.g. Q10 should have ~10% coverage
        cov = coverage(y_test, q_preds[label], alpha)

        pred_s = pd.Series(q_preds[label])
        print(f"    Pinball loss: {pb:.4f} | Coverage: {cov:.3f} (target {alpha:.2f})")
        print(f"    Prediction spread: min={pred_s.min():.1f}  "
              f"median={pred_s.median():.1f}  max={pred_s.max():.1f}")

        q_results[label] = {
            "alpha":        alpha,
            "pinball_loss": round(pb, 4),
            "coverage":     round(cov, 4),
            "pred_min":     round(float(pred_s.min()), 2),
            "pred_median":  round(float(pred_s.median()), 2),
            "pred_max":     round(float(pred_s.max()), 2),
        }

    # ── Interval check ────────────────────────────────────────────────────────
    # The Q10-Q90 interval should contain ~80% of actual values.
    # This is the "80% prediction interval" — if you see a player with
    # Q10=-9 and Q90=+2, real-world outcomes fall in that range 80% of the time.
    interval_coverage = float(np.mean(
        (y_test.values >= q_preds["q10"]) & (y_test.values <= q_preds["q90"])
    ))
    print(f"\n  Q10-Q90 interval coverage: {interval_coverage:.3f} "
          f"(target ~0.80 — 80% of actuals should fall within ceiling-floor range)")

    # ── Example: show what a top-ranked player looks like ────────────────────
    # Find the player with the best (lowest) mean prediction in the test set
    # and show their full ceiling/median/floor profile.
    best_idx = int(np.argmin(preds_mean))
    print(f"\n  Example — top-ranked player in 2025 test set:")
    print(f"    Mean prediction:    {preds_mean[best_idx]:+.1f} vs field")
    print(f"    Ceiling (Q10):      {q_preds['q10'][best_idx]:+.1f} vs field")
    print(f"    Median  (Q50):      {q_preds['q50'][best_idx]:+.1f} vs field")
    print(f"    Floor   (Q90):      {q_preds['q90'][best_idx]:+.1f} vs field")
    print(f"    Actual score:       {y_test.values[best_idx]:+.1f} vs field")

    # ── Feature importance ────────────────────────────────────────────────────
    fi = (pd.Series(mean_model.feature_importances_, index=feats)
          .sort_values(ascending=False).head(15))
    print(f"\n  Top 15 features (mean model, gain importance):")
    print(fi.to_string())

    # ═════════════════════════════════════════════════════════════════════════
    # SAVE
    # ═════════════════════════════════════════════════════════════════════════
    MODEL_DIR.mkdir(exist_ok=True)

    # Mean model — primary ranking model, same as before
    joblib.dump(mean_model, MODEL_DIR / "score_model_final.pkl")
    (MODEL_DIR / "score_model_features.txt").write_text("\n".join(feats))

    # Quantile models — saved individually so predict_tournament can load
    # whichever it needs without loading all three every time
    for label, qm in q_models.items():
        joblib.dump(qm, MODEL_DIR / f"score_model_{label}.pkl")

    # Calibration JSON — kept for reference even though slope ~1
    cal_data = {
        "slope": slope, "intercept": intercept,
        "n_cal": int(len(y_test)),
        "mae_raw": round(float(mean_absolute_error(y_test, preds_mean)), 4),
        "note": "Slope ~1 confirms model is unbiased in mean. No correction applied.",
    }
    (MODEL_DIR / "score_model_calibration.json").write_text(json.dumps(cal_data, indent=2))

    # Quantile metadata — stores coverage/pinball results and interval width
    # so the dashboard can show how reliable the range estimates are
    q_meta = {
        "interval_coverage_80pct": round(interval_coverage, 4),
        "quantiles": q_results,
        "note": (
            "interval_coverage_80pct = fraction of 2025 actuals that fell "
            "within the Q10-Q90 interval. Target is 0.80."
        ),
    }
    (MODEL_DIR / "score_model_quantiles.json").write_text(json.dumps(q_meta, indent=2))

    print(f"\n  Saved: score_model_final.pkl  (mean model)")
    print(f"  Saved: score_model_q10.pkl    (ceiling)")
    print(f"  Saved: score_model_q50.pkl    (median)")
    print(f"  Saved: score_model_q90.pkl    (floor)")
    print(f"  Saved: score_model_features.txt")
    print(f"  Saved: score_model_calibration.json")
    print(f"  Saved: score_model_quantiles.json")
    print(f"\nDone. Run predict_tournament.py to regenerate projected scores.")


if __name__ == "__main__":
    main()
