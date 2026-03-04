#!/usr/bin/env python3
"""
Generate Calibration Data for Model Validation Dashboard
=========================================================
Loads the saved .pkl models, runs them on the held-out 2025 test set,
and computes the diagnostic curves the dashboard needs to display.

WHAT THIS TEACHES YOU
---------------------
Three separate questions about a prediction model — easy to confuse:

1. RANKING QUALITY (ROC-AUC)
   Does the model put winners near the top of the list?
   AUC = 0.50 → random guess.  AUC = 0.90 → excellent ranking.
   Measured by the ROC curve: TPR vs FPR as you slide the threshold.

2. CALIBRATION (reliability diagram)
   When the model says "15% win probability", does it actually win
   ~15% of the time in practice?
   A perfectly calibrated model lies on the diagonal y = x.
   "Overconfident" → predicted probs are too high → curve bends below diagonal.
   Measured by sklearn's calibration_curve() which bins predictions and
   computes the actual positive rate per bin.

3. OVERALL PROBABILITY ACCURACY (Brier score)
   Mean squared error between predicted probability and actual outcome.
   Range: 0 (perfect) to 1 (worst).  Random binary = 0.25.
   Combines calibration and resolution in one number.

You can have high AUC (good rankings) but poor calibration (wrong numbers).
You can have good calibration but low AUC (right numbers, wrong order).
Ideally you want both.

Usage:
    python3 scripts/validation/generate_calibration_data.py
    → writes outputs/calibration_data.json
"""

import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from sklearn.calibration import calibration_curve
from sklearn.metrics import roc_curve, roc_auc_score, brier_score_loss

PROJECT_ROOT  = Path(__file__).parent.parent.parent
DATA_DIR      = PROJECT_ROOT / "data"
MODEL_DIR     = DATA_DIR / "models"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR   = PROJECT_ROOT / "outputs"

# ── Feature groups — mirrors train_final_models.py exactly ─────────────────
SEASON_SG = [
    "season_sg_total", "season_sg_ott", "season_sg_app",
    "season_sg_putt", "season_sg_t2g", "season_sg_arg",
]
HIST = [
    "hist_avg_finish", "hist_best_finish", "hist_top5s", "hist_top10s",
    "hist_wins", "hist_cut_rate", "hist_missed_cuts", "hist_times_played",
    "has_course_history", "has_won_here", "has_made_cut_here",
    "has_course_sg_history",
]
VENUE = ["venue_avg_finish", "venue_finish_std"]
FIELD = ["field_avg_rank", "field_median_rank"]
RANK  = ["world_rank"]
FORM  = [
    "form_trend", "finish_consistency",
    "recent_top5s", "recent_top10s", "recent_cuts_pct",
    "recent_scoring_avg", "recent_gir_pct", "recent_sand_save",
    "recent_birdie_avg", "recent_bogey_avg", "recent_scrambling",
    "recent_bounce_back", "recent_final_round",
]
ALL_FEATURES = SEASON_SG + HIST + VENUE + FIELD + RANK + FORM

# Model file → target column mapping  (same as train_final_models.py)
MODELS = {
    "win":   ("win_model_final.pkl",   "won"),
    "top5":  ("top5_model_final.pkl",  "top5"),
    "top10": ("top10_model_final.pkl", "top10"),
    "top20": ("top20_model_final.pkl", "top20"),
}
DISPLAY = {"win": "Win", "top5": "Top 5", "top10": "Top 10", "top20": "Top 20"}


# ── Helpers ─────────────────────────────────────────────────────────────────
def _features_from_model(model) -> list:
    """
    Read the feature list the model was actually trained on.

    sklearn saves feature_names_in_ on the base estimator inside
    CalibratedClassifierCV.  Using this guarantees our test matrix
    matches training exactly — no guessing at column order.
    """
    try:
        return list(model.calibrated_classifiers_[0].estimator.feature_names_in_)
    except AttributeError:
        # Fallback for non-calibrated or older models
        try:
            return list(model.feature_names_in_)
        except AttributeError:
            return None


def _calibration_curve_data(y_true, y_prob, n_bins: int = 10) -> dict:
    """
    Wrapper around sklearn's calibration_curve.

    Returns two parallel lists (same length, trimmed to bins that have data):
      mean_predicted : average predicted probability in each bin  [x-axis]
      fraction_pos   : actual positive rate in each bin           [y-axis]

    Perfect calibration → fraction_pos[i] ≈ mean_predicted[i] for all i.
    """
    frac_pos, mean_pred = calibration_curve(
        y_true, y_prob,
        n_bins=n_bins,
        strategy="uniform",   # equal-width bins (easier to read than quantile)
    )
    return {
        "mean_predicted":  mean_pred.tolist(),   # x-axis
        "fraction_pos":    frac_pos.tolist(),     # y-axis
    }


def _roc_curve_data(y_true, y_prob) -> dict:
    """
    Compute the ROC curve.

    Returns fpr, tpr, and AUC.  Downsampled to ≤100 points so the JSON
    stays small while preserving the curve shape.
    """
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    auc_val = float(roc_auc_score(y_true, y_prob))

    idx = np.linspace(0, len(fpr) - 1, min(100, len(fpr))).astype(int)
    return {
        "fpr": fpr[idx].tolist(),
        "tpr": tpr[idx].tolist(),
        "auc": auc_val,
    }


# ── Main ────────────────────────────────────────────────────────────────────
def run() -> dict:
    print("\n" + "=" * 62)
    print("  CALIBRATION DATA GENERATOR")
    print("  Train: 2016-2024   |   Test (held-out): 2025")
    print("=" * 62)

    # 1. Load master data — auto-detect newest file
    import glob as _glob
    _td_files = sorted(_glob.glob(str(PROCESSED_DIR / "master_training_data_*.csv")))
    master_path = Path(_td_files[-1]) if _td_files else PROCESSED_DIR / "master_training_data_2016_2025.csv"
    if not master_path.exists():
        raise FileNotFoundError(f"Master data not found: {master_path}")

    print("\n  Loading master training data...")
    df = pd.read_csv(master_path)
    print(f"  Total records: {len(df):,}")

    # 2. Year-based split — identical to train_final_models.py
    train_df = df[df["year"] < 2025].copy()
    test_df  = df[df["year"] == 2025].copy()
    print(f"  Train (2016–2024): {len(train_df):,}")
    print(f"  Test  (2025):      {len(test_df):,}")

    # 3. Drop rows with missing targets (same as training)
    target_cols = [c for _, (_, c) in MODELS.items() if c in test_df.columns]
    test_df  = test_df.dropna(subset=target_cols)
    train_df = train_df.dropna(subset=target_cols)
    print(f"  Test after target cleanup: {len(test_df):,}")

    # 6. Build output structure
    output = {
        "generated_at": datetime.now().isoformat(),
        "n_train":      len(train_df),
        "n_test":       len(test_df),
        "models":       {},
    }

    # 7. Process each model
    for key, (model_file, target_col) in MODELS.items():
        model_path = MODEL_DIR / model_file
        if not model_path.exists():
            print(f"\n  ⚠  Skipping {key}: model not found ({model_file})")
            continue
        if target_col not in test_df.columns:
            print(f"\n  ⚠  Skipping {key}: target column '{target_col}' missing")
            continue

        print(f"\n  [{DISPLAY[key]}] model...")

        model    = joblib.load(model_path)
        features = _features_from_model(model)
        if features is None:
            print(f"    ⚠  Could not determine feature list — skipping")
            continue

        # Build X_test using the exact feature order the model expects,
        # imputing missing values with training-set medians.
        # Guard against new features added after this training data was built.
        present = [f for f in features if f in train_df.columns]
        missing = [f for f in features if f not in train_df.columns]
        if missing:
            print(f"    ⚠  {len(missing)} feature(s) not in training data, filling with 0: {missing[:5]}")
        feature_medians = train_df[present].median(numeric_only=True)
        X_test = test_df.reindex(columns=features, fill_value=0).fillna(feature_medians)

        y_true = test_df[target_col].fillna(0).astype(int)
        y_prob = model.predict_proba(X_test)[:, 1]

        auc_val    = float(roc_auc_score(y_true, y_prob))
        brier_val  = float(brier_score_loss(y_true, y_prob))
        pred_avg   = float(y_prob.mean())
        actual_avg = float(y_true.mean())
        cal_ratio  = pred_avg / actual_avg if actual_avg > 0 else 0.0

        print(f"    AUC:          {auc_val:.4f}")
        print(f"    Brier score:  {brier_val:.4f}  (random = {actual_avg*(1-actual_avg):.4f})")
        print(f"    Pred avg:     {pred_avg*100:.2f}%  "
              f"Actual: {actual_avg*100:.2f}%  "
              f"Ratio: {cal_ratio:.2f}x")

        output["models"][key] = {
            "display_name":      DISPLAY[key],
            "auc":               auc_val,
            "brier":             brier_val,
            "random_brier":      float(actual_avg * (1 - actual_avg)),
            "pred_avg":          pred_avg,
            "actual_avg":        actual_avg,
            "cal_ratio":         cal_ratio,
            "n_positive":        int(y_true.sum()),
            "positive_rate_pct": round(actual_avg * 100, 2),
            "calibration_curve": _calibration_curve_data(y_true, y_prob),
            "roc_curve":         _roc_curve_data(y_true, y_prob),
        }

    # 8. Feature importance from saved CSV
    fi_path = MODEL_DIR / "feature_importance.csv"
    if fi_path.exists():
        fi_df = pd.read_csv(fi_path).sort_values("avg_importance", ascending=False)
        output["feature_importance"] = fi_df.head(15).to_dict("records")
        print(f"\n  Feature importance: top {min(15, len(fi_df))} features loaded")

    # 9. Save
    out_path = OUTPUTS_DIR / "calibration_data.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  ✅ Saved → {out_path}")
    print("=" * 62)
    return output


if __name__ == "__main__":
    run()
