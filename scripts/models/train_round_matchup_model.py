"""
Train a per-round head-to-head matchup model.

Instead of repurposing the 72-hole win_prob to price single-round h2h bets,
this model directly predicts: P(player A scores lower than player B in round R).

Key insight: for R3/R4, the score differential *entering* the round is the
dominant predictor — someone 5 shots ahead has a very different expected
scoring distribution than someone 5 behind (pressure, playing style, etc.).
For R1 no one has played yet, so the model falls back on SG/skill features.

Usage:
    python scripts/models/train_round_matchup_model.py

Saves:
    data/models/round_matchup_model.pkl
    data/models/round_matchup_features.json
"""

import json
import logging
import pickle
import random
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

try:
    import xgboost as xgb
except ImportError:
    raise SystemExit("xgboost not installed: pip install xgboost")

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
HIST_DIR = ROOT / "data" / "historical"
MODEL_DIR = ROOT / "data" / "models"
MODEL_DIR.mkdir(exist_ok=True)

# SG stat IDs we pull from tournament_stats CSVs
SG_STAT_IDS = {
    2567: "sg_total",
    2568: "sg_ott",
    2569: "sg_app",
    2564: "sg_putt",
}

# Pairs sampled per round per tournament.
# 40 pairs × 4 rounds × 350 tournaments ≈ 56,000 training rows — plenty for XGBoost.
PAIRS_PER_ROUND = 40

# Tie resolution: when two players shoot the same score, we flip a coin.
# This adds noise but is honest — ties are genuinely unpredictable.
RANDOM_SEED = 42


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Load & clean data
# ─────────────────────────────────────────────────────────────────────────────

def load_leaderboards() -> pd.DataFrame:
    """Load all years of round-score leaderboard data."""
    frames = []
    for f in sorted(HIST_DIR.glob("leaderboards_*.csv")):
        df = pd.read_csv(f, dtype={"player_id": str, "tournament_id": str})
        frames.append(df)
    lb = pd.concat(frames, ignore_index=True)

    for col in ["r1_score", "r2_score", "r3_score", "r4_score"]:
        lb[col] = pd.to_numeric(lb[col], errors="coerce")

    lb = lb[lb["rounds_played"] == 4].copy()  # only full 4-round finishers
    lb = lb.dropna(subset=["r1_score", "r2_score", "r3_score", "r4_score"])
    log.info("Leaderboards: %d 4-round finishers across %d tournaments",
             len(lb), lb.groupby(["tournament_id", "year"]).ngroups)
    return lb


def load_sg_stats() -> pd.DataFrame:
    """Load per-tournament SG stats for all years.

    Returns a pivot: one row per (player_id, tournament_id, year),
    columns sg_total, sg_ott, sg_app, sg_putt.
    """
    frames = []
    for f in sorted(HIST_DIR.glob("tournament_stats_*.csv")):
        df = pd.read_csv(f, dtype={"player_id": str, "tournament_id": str})
        # stat_id may be int or str
        df["stat_id"] = pd.to_numeric(df["stat_id"], errors="coerce")
        sg = df[df["stat_id"].isin(SG_STAT_IDS)].copy()
        sg["stat_name_clean"] = sg["stat_id"].map(SG_STAT_IDS)
        frames.append(sg[["player_id", "tournament_id", "year", "stat_name_clean", "stat_value"]])

    if not frames:
        log.warning("No tournament_stats files found — SG features will be missing")
        return pd.DataFrame(columns=["player_id", "tournament_id", "year",
                                     "sg_total", "sg_ott", "sg_app", "sg_putt"])

    sg_all = pd.concat(frames, ignore_index=True)
    sg_all["stat_value"] = pd.to_numeric(sg_all["stat_value"], errors="coerce")

    pivot = sg_all.pivot_table(
        index=["player_id", "tournament_id", "year"],
        columns="stat_name_clean",
        values="stat_value",
        aggfunc="first",
    ).reset_index()
    pivot.columns.name = None

    for col in ["sg_total", "sg_ott", "sg_app", "sg_putt"]:
        if col not in pivot.columns:
            pivot[col] = np.nan

    log.info("SG stats: %d player-tournament rows", len(pivot))
    return pivot


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Build pairwise training examples
# ─────────────────────────────────────────────────────────────────────────────

def build_training_pairs(lb: pd.DataFrame, sg: pd.DataFrame) -> pd.DataFrame:
    """For each tournament × round, sample random player pairs and create
    labelled matchup rows.

    Features per row (from player A's perspective):
        round_num           — 1 to 4
        score_diff_before   — (A_cumulative - B_cumulative) entering this round
                              (0 for R1, meaningful for R2/R3/R4)
        position_a          — A's position entering this round (0 for R1)
        position_b          — B's position entering this round
        sg_total_diff       — A_sg_total - B_sg_total (season average)
        sg_ott_diff         — A_sg_ott - B_sg_ott
        sg_app_diff         — A_sg_app - B_sg_app
        sg_putt_diff        — A_sg_putt - B_sg_putt

    Label:
        target = 1 if player A shot LOWER (better) than player B this round
                 0 if player B shot lower
                 ties broken randomly (50/50 noise is unavoidable for ties)
    """
    rng = random.Random(RANDOM_SEED)

    # Merge SG stats onto leaderboard
    merged = lb.merge(sg, on=["player_id", "tournament_id", "year"], how="left")

    rows = []
    groups = merged.groupby(["tournament_id", "year"])

    for (tid, year), field in groups:
        # Build cumulative scores entering each round
        field = field.copy()
        field["cum_after_r1"] = field["r1_score"]
        field["cum_after_r2"] = field["r1_score"] + field["r2_score"]
        field["cum_after_r3"] = field["cum_after_r2"] + field["r3_score"]

        players = field.to_dict("records")
        if len(players) < 6:
            continue

        for round_num in [1, 2, 3, 4]:
            round_col = f"r{round_num}_score"

            # Compute scores entering this round and ranking
            if round_num == 1:
                cum_col = None
            elif round_num == 2:
                cum_col = "cum_after_r1"
            elif round_num == 3:
                cum_col = "cum_after_r2"
            else:
                cum_col = "cum_after_r3"

            # Sort by entering-round cumulative score to assign position
            if cum_col:
                sorted_players = sorted(players, key=lambda p: p[cum_col])
                pos_map = {p["player_id"]: i + 1 for i, p in enumerate(sorted_players)}
            else:
                sorted_players = players[:]  # R1: no ordering yet
                pos_map = {p["player_id"]: 0 for p in players}

            # Sample realistic pairs: players within a meaningful position/score range.
            # Random pairs from a 130-player field are mostly adjacent-rank comparisons
            # with tiny score differentials — the position signal is overwhelmed by noise.
            # Books price matchups between players with meaningful differences (e.g. R4:
            # leader vs 5th, not leader vs last place). We sample with position-gap bias.
            #
            # Strategy: pick one player from top-40% of field, one from anywhere.
            # This ensures we have ~half the training data with real positional contrasts.
            n = len(sorted_players)
            top_half = sorted_players[:max(2, n // 2)]  # best half ordered by position
            round_rows: list[dict] = []
            seen: set = set()
            max_attempts = PAIRS_PER_ROUND * 20

            for attempt in range(max_attempts):
                if len(round_rows) >= PAIRS_PER_ROUND:
                    break
                # Half the time, sample from top half vs anywhere (creates meaningful diffs)
                if attempt % 2 == 0 and len(top_half) >= 2:
                    pa = rng.choice(top_half)
                    pb = rng.choice(sorted_players)
                else:
                    pa, pb = rng.sample(sorted_players, 2)
                if pa["player_id"] == pb["player_id"]:
                    continue
                pid_a, pid_b = pa["player_id"], pb["player_id"]
                pair_key = (min(pid_a, pid_b), max(pid_a, pid_b))
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                score_a = pa.get(round_col)
                score_b = pb.get(round_col)
                if pd.isna(score_a) or pd.isna(score_b):
                    continue

                # Label: did A shoot lower (better)?
                if score_a < score_b:
                    target = 1
                elif score_b < score_a:
                    target = 0
                else:
                    target = rng.randint(0, 1)  # tie → random

                cum_a = pa.get(cum_col, 0) if cum_col else 0.0
                cum_b = pb.get(cum_col, 0) if cum_col else 0.0
                pos_a = pos_map.get(pid_a, 0)
                pos_b = pos_map.get(pid_b, 0)

                sg_total_a = pa.get("sg_total")
                sg_total_b = pb.get("sg_total")
                sg_ott_a   = pa.get("sg_ott")
                sg_ott_b   = pb.get("sg_ott")
                sg_app_a   = pa.get("sg_app")
                sg_app_b   = pb.get("sg_app")
                sg_putt_a  = pa.get("sg_putt")
                sg_putt_b  = pb.get("sg_putt")

                round_rows.append({
                    "tournament_id": tid,
                    "year": year,
                    "round_num": round_num,
                    "score_diff_before": float(cum_a - cum_b),
                    "position_a": float(pos_a),
                    "position_b": float(pos_b),
                    "position_diff": float(pos_a - pos_b),
                    "sg_total_diff": float(sg_total_a - sg_total_b)
                        if pd.notna(sg_total_a) and pd.notna(sg_total_b) else np.nan,
                    "sg_ott_diff": float(sg_ott_a - sg_ott_b)
                        if pd.notna(sg_ott_a) and pd.notna(sg_ott_b) else np.nan,
                    "sg_app_diff": float(sg_app_a - sg_app_b)
                        if pd.notna(sg_app_a) and pd.notna(sg_app_b) else np.nan,
                    "sg_putt_diff": float(sg_putt_a - sg_putt_b)
                        if pd.notna(sg_putt_a) and pd.notna(sg_putt_b) else np.nan,
                    "target": target,
                })

            rows.extend(round_rows)

    df = pd.DataFrame(rows)
    log.info("Training pairs built: %d rows across %d round numbers", len(df), df["round_num"].nunique())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Train model
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_COLS = [
    "round_num",
    "score_diff_before",   # primary position signal — actual stroke gap entering round
    "sg_total_diff",       # season skill differential
    "sg_ott_diff",
    "sg_app_diff",
    "sg_putt_diff",
    # NOTE: position_a/b/diff intentionally excluded — they're collinear with
    # score_diff_before and cause XGBoost to split the signal incorrectly.
    # score_diff_before is more precise (strokes) than ordinal rank anyway.
]


def train(pairs: pd.DataFrame) -> tuple:
    """Train XGBoost classifier and return (model, feature_importances)."""
    X = pairs[FEATURE_COLS].copy()
    y = pairs["target"].astype(int)

    # Fill missing SG values with 0 (neutral — both players equal in that stat)
    X = X.fillna(0.0)

    # Group k-fold by year to avoid temporal leakage:
    # train on 2016-2023, validate on 2024-2026
    groups = pairs["year"].values
    gkf = GroupKFold(n_splits=5)

    log.info("Training XGBoost on %d rows, %d features", len(X), len(FEATURE_COLS))

    base_model = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,   # prevents overfitting on small groups
        eval_metric="logloss",
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )

    # Cross-validated evaluation
    fold_aucs, fold_briers = [], []
    for fold, (train_idx, val_idx) in enumerate(gkf.split(X, y, groups)):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
        base_model.fit(X_tr, y_tr, verbose=False)
        probs = base_model.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, probs)
        brier = brier_score_loss(y_val, probs)
        fold_aucs.append(auc)
        fold_briers.append(brier)
        log.info("  Fold %d: AUC=%.4f  Brier=%.4f", fold + 1, auc, brier)

    log.info("CV AUC:   %.4f ± %.4f", np.mean(fold_aucs), np.std(fold_aucs))
    log.info("CV Brier: %.4f ± %.4f", np.mean(fold_briers), np.std(fold_briers))

    # Refit on all data with isotonic calibration.
    # Isotonic is more numerically stable than Platt/sigmoid when XGBoost
    # outputs very confident probabilities (avoids log-odds overflow).
    calibrated = CalibratedClassifierCV(
        xgb.XGBClassifier(
            n_estimators=400,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=10,
            eval_metric="logloss",
            random_state=RANDOM_SEED,
            n_jobs=-1,
        ),
        method="isotonic",
        cv=3,
    )
    calibrated.fit(X, y)

    # Feature importance from the uncalibrated model (for reporting)
    base_model.fit(X, y, verbose=False)
    importances = dict(zip(FEATURE_COLS, base_model.feature_importances_))

    return calibrated, importances, {
        "cv_auc_mean": float(np.mean(fold_aucs)),
        "cv_auc_std": float(np.std(fold_aucs)),
        "cv_brier_mean": float(np.mean(fold_briers)),
        "cv_brier_std": float(np.std(fold_briers)),
        "n_training_rows": len(pairs),
        "features": FEATURE_COLS,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Round Matchup Model — Training ===")

    lb = load_leaderboards()
    sg = load_sg_stats()
    pairs = build_training_pairs(lb, sg)

    if len(pairs) < 1000:
        raise SystemExit(f"Too few training rows ({len(pairs)}) — check data files")

    model, importances, meta = train(pairs)

    # Save model
    model_path = MODEL_DIR / "round_matchup_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    log.info("Model saved → %s", model_path)

    # Save metadata
    meta["feature_importances"] = {k: round(float(v), 6) for k, v in
                                   sorted(importances.items(), key=lambda x: -x[1])}
    meta_path = MODEL_DIR / "round_matchup_model_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    log.info("Metadata saved → %s", meta_path)

    log.info("\nFeature importances:")
    for feat, imp in meta["feature_importances"].items():
        bar = "█" * int(imp * 100)
        log.info("  %-22s  %.4f  %s", feat, imp, bar)

    log.info("\nDone. Model ready for use in recommend_bets.py")


if __name__ == "__main__":
    main()
