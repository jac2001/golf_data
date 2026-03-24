#!/usr/bin/env python3
"""
Compute SHAP Values for All Prediction Models
===============================================
SHAP (SHapley Additive exPlanations) explains WHY the model makes each prediction.

The core idea: each player's predicted probability can be decomposed as:
    P(win) = base_rate + shap(sg_arg) + shap(world_rank) + shap(form_trend) + ...

A positive SHAP value means a feature pushed the prediction UP for that player.
A negative SHAP value means it pulled the prediction DOWN.

This script:
  1. Loads all 4 trained models (win, top5, top10, top20)
  2. Loads the current week's feature matrix from latest_predictions.csv
  3. Computes SHAP values using TreeExplainer (exact for tree-based models, fast)
  4. Averages across the 3 calibration folds for robust estimates
  5. Saves:
     - outputs/shap_values_{model}.csv  — per-player SHAP values (one col per feature)
     - outputs/shap_global_{model}.csv  — global importance: mean |SHAP| per feature

Usage:
    python3 scripts/validation/compute_shap.py
    python3 scripts/validation/compute_shap.py --model win
"""

from __future__ import annotations
import argparse
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR    = PROJECT_ROOT / "data" / "models"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"
PREDS_FILE   = OUTPUTS_DIR / "latest_predictions.csv"
FEATURES_FILE = MODEL_DIR / "feature_importance.csv"

MODELS = ["win", "top5", "top10", "top20"]


def load_feature_matrix() -> tuple[pd.DataFrame, list[str]]:
    """Load the current week's predictions and extract the 62-feature matrix."""
    preds = pd.read_csv(PREDS_FILE)
    fi    = pd.read_csv(FEATURES_FILE)
    features = fi["feature"].tolist()

    missing = [f for f in features if f not in preds.columns]
    if missing:
        print(f"  Warning: {len(missing)} features missing from predictions — filling with 0")
        for f in missing:
            preds[f] = 0.0

    X = preds[features].fillna(0)
    return preds, X, features


def compute_shap_for_model(model_name: str, preds: pd.DataFrame,
                            X: pd.DataFrame, features: list[str]) -> None:
    """
    Compute SHAP values for one model and save results.

    CalibratedClassifierCV trains N separate base models (one per fold).
    We compute SHAP for each fold's base RandomForest, then average — this
    gives a more stable estimate than using a single fold.
    """
    model_path = MODEL_DIR / f"{model_name}_model_final.pkl"
    if not model_path.exists():
        print(f"  Skipping {model_name} — model file not found")
        return

    print(f"  Loading {model_name} model...")
    cal_model = joblib.load(model_path)

    # Each calibrated_classifier_ has a base .estimator (RandomForest)
    base_models = [c.estimator for c in cal_model.calibrated_classifiers_]
    print(f"  Computing SHAP across {len(base_models)} folds ({len(X)} players, {len(features)} features)...")

    all_shap = []
    for i, rf in enumerate(base_models):
        explainer = shap.TreeExplainer(rf)
        sv = explainer.shap_values(X)

        # sv shape: (n_samples, n_features, n_classes) — we want class 1 (positive outcome)
        if sv.ndim == 3:
            sv = sv[:, :, 1]
        elif isinstance(sv, list):
            sv = sv[1]

        all_shap.append(sv)

    # Average SHAP values across folds
    mean_shap = np.mean(all_shap, axis=0)  # shape: (n_players, n_features)

    # ── Per-player SHAP values ──────────────────────────────────────────────
    shap_df = pd.DataFrame(mean_shap, columns=features)
    shap_df.insert(0, "player_name", preds["player_name"].values)
    if "tournament_id" in preds.columns:
        shap_df.insert(1, "tournament_id", preds["tournament_id"].values)

    out_player = OUTPUTS_DIR / f"shap_values_{model_name}.csv"
    shap_df.to_csv(out_player, index=False)
    print(f"    Saved player SHAP → {out_player.name}")

    # ── Global feature importance: mean |SHAP| across all players ──────────
    # This is the SHAP-based feature importance, which is more reliable than
    # the default RandomForest importance (which over-counts high-cardinality features)
    global_imp = pd.DataFrame({
        "feature":        features,
        "mean_abs_shap":  np.abs(mean_shap).mean(axis=0),
        "mean_shap":      mean_shap.mean(axis=0),   # positive = pushes UP on average
        "max_abs_shap":   np.abs(mean_shap).max(axis=0),
    }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

    out_global = OUTPUTS_DIR / f"shap_global_{model_name}.csv"
    global_imp.to_csv(out_global, index=False)
    print(f"    Saved global SHAP → {out_global.name}")

    # Print top 10 for this model
    print(f"\n  Top 10 features by SHAP importance ({model_name}):")
    for _, row in global_imp.head(10).iterrows():
        direction = "▲" if row["mean_shap"] > 0 else "▼"
        print(f"    {row['feature']:<40} {row['mean_abs_shap']:.4f}  {direction}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Compute SHAP values for prediction models")
    parser.add_argument("--model", choices=MODELS + ["all"], default="all",
                        help="Which model to compute SHAP for (default: all)")
    args = parser.parse_args()

    if not PREDS_FILE.exists():
        print(f"ERROR: {PREDS_FILE} not found — run the prediction pipeline first")
        return

    print(f"Loading feature matrix from {PREDS_FILE.name}...")
    preds, X, features = load_feature_matrix()
    print(f"  {len(preds)} players, {len(features)} features\n")

    models_to_run = MODELS if args.model == "all" else [args.model]

    for model_name in models_to_run:
        print(f"=== {model_name.upper()} MODEL ===")
        compute_shap_for_model(model_name, preds, X, features)

    print("Done. SHAP files saved to outputs/")


if __name__ == "__main__":
    main()
