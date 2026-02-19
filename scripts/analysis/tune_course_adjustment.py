#!/usr/bin/env python3
"""
Tune course-history probability adjustment settings against recent completed events.

This script replays adjustment parameters on saved baseline prediction files
and evaluates against actual leaderboard outcomes.

Expected baseline inputs:
  outputs/calibration/base_R*.csv

Usage:
  python3 scripts/analysis/tune_course_adjustment.py
"""

from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.predictions.predict_tournament import (
    apply_course_performance_adjustment,
    apply_probability_constraints,
)
BASELINE_GLOB = "outputs/calibration/base_R*.csv"
LEADERBOARDS_PATH = PROJECT_ROOT / "data/historical/leaderboards_2026.csv"
OUT_DIR = PROJECT_ROOT / "outputs/calibration"


def parse_position(value) -> int:
    if pd.isna(value):
        return 999
    text = str(value).strip().upper()
    if text in {"CUT", "MC", "WD", "W/D", "DQ"}:
        return 999
    text = text.replace("T", "")
    text = re.sub(r"[^0-9]", "", text)
    if not text:
        return 999
    try:
        return int(text)
    except ValueError:
        return 999


def load_actuals() -> pd.DataFrame:
    if not LEADERBOARDS_PATH.exists():
        raise FileNotFoundError(f"Missing leaderboard file: {LEADERBOARDS_PATH}")

    lb = pd.read_csv(LEADERBOARDS_PATH).copy()
    lb["tournament_id"] = lb["tournament_id"].astype(str).str.upper()
    lb["player_id"] = pd.to_numeric(lb["player_id"], errors="coerce")
    lb["actual_position"] = lb["position"].map(parse_position)
    lb["actual_won"] = lb["actual_position"] == 1
    lb["actual_top5"] = lb["actual_position"] <= 5
    lb["actual_top10"] = lb["actual_position"] <= 10
    return lb[
        [
            "tournament_id",
            "player_id",
            "player_name",
            "actual_position",
            "actual_won",
            "actual_top5",
            "actual_top10",
        ]
    ].copy()


def brier(y_true: pd.Series, y_prob: pd.Series) -> float:
    yt = pd.to_numeric(y_true, errors="coerce").fillna(0.0).astype(float)
    yp = pd.to_numeric(y_prob, errors="coerce").fillna(0.0).astype(float)
    return float(np.mean((yp - yt) ** 2))


def evaluate_one_tournament(pred_df: pd.DataFrame, actual_df: pd.DataFrame, tid: str) -> Dict[str, float]:
    work = pred_df.copy()
    work["player_id"] = pd.to_numeric(work["player_id"], errors="coerce")
    work["tournament_id"] = tid
    merged = work.merge(
        actual_df[actual_df["tournament_id"] == tid],
        on=["tournament_id", "player_id"],
        how="inner",
        suffixes=("", "_actual"),
    )
    merged = merged[merged["actual_position"].notna()].copy()
    if merged.empty:
        return {
            "matched_players": 0.0,
            "brier_win": np.nan,
            "brier_top5": np.nan,
            "brier_top10": np.nan,
            "top10_hit_rate": np.nan,
            "winner_rank": np.nan,
        }

    merged["pred_rank"] = merged["win_prob"].rank(ascending=False, method="first")

    top10_pred = set(
        merged.sort_values("win_prob", ascending=False)
        .head(10)["player_id"]
        .dropna()
        .astype(int)
        .tolist()
    )
    top10_actual = set(
        merged[merged["actual_top10"] == True]["player_id"]
        .dropna()
        .astype(int)
        .tolist()
    )
    top10_hit_rate = len(top10_pred & top10_actual) / 10.0

    winner_rank = np.nan
    winner_rows = merged[merged["actual_won"] == True]
    if not winner_rows.empty:
        winner_rank = float(winner_rows["pred_rank"].min())

    return {
        "matched_players": float(len(merged)),
        "brier_win": brier(merged["actual_won"].astype(float), merged["win_prob"]),
        "brier_top5": brier(merged["actual_top5"].astype(float), merged["top5_prob"]),
        "brier_top10": brier(merged["actual_top10"].astype(float), merged["top10_prob"]),
        "top10_hit_rate": float(top10_hit_rate),
        "winner_rank": winner_rank,
    }


def apply_setting(df: pd.DataFrame, setting: Dict) -> pd.DataFrame:
    work = df.copy()
    with redirect_stdout(io.StringIO()):
        work = apply_course_performance_adjustment(
            work,
            boost_strength=float(setting["boost_strength"]),
            min_starts=int(setting["min_starts"]),
            max_abs_adjust=float(setting["max_abs_adjust"]),
            min_players_with_history=int(setting["min_players_with_history"]),
            allow_similar_fallback=bool(setting["allow_similar_fallback"]),
        )
        work = apply_probability_constraints(
            work,
            normalize_topk=True,
            favorite_bias_strength=0.40,
            favorite_bias_half_life=8.0,
            top5_cap=0.65,
            top10_cap=0.75,
            top20_cap=0.85,
        )
    return work


def summarize(metrics_by_tournament: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    rows = pd.DataFrame(metrics_by_tournament).T
    out = {}
    for col in rows.columns:
        out[col] = float(pd.to_numeric(rows[col], errors="coerce").mean())

    weighted_brier = (
        0.50 * out.get("brier_win", np.nan) +
        0.20 * out.get("brier_top5", np.nan) +
        0.30 * out.get("brier_top10", np.nan)
    )
    # Lower is better
    out["weighted_brier"] = float(weighted_brier)
    # Composite ranking objective
    out["objective"] = float(
        weighted_brier
        - 0.05 * out.get("top10_hit_rate", 0.0)
        + 0.002 * out.get("winner_rank", 50.0)
    )
    return out


def make_grid() -> List[Dict]:
    grid = []
    for boost_strength in [0.00, 0.04, 0.06, 0.08, 0.10, 0.12]:
        for max_abs_adjust in [0.04, 0.06, 0.08]:
            for min_starts in [1, 2, 3]:
                for min_players_with_history in [5, 8, 12]:
                    for allow_similar_fallback in [False, True]:
                        grid.append(
                            {
                                "boost_strength": boost_strength,
                                "max_abs_adjust": max_abs_adjust,
                                "min_starts": min_starts,
                                "min_players_with_history": min_players_with_history,
                                "allow_similar_fallback": allow_similar_fallback,
                            }
                        )
    return grid


def tournament_id_from_path(path: Path) -> str:
    m = re.search(r"(R\d{7})", path.stem.upper())
    if not m:
        raise ValueError(f"Could not extract tournament ID from filename: {path.name}")
    return m.group(1)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    actuals = load_actuals()

    baseline_paths = sorted(PROJECT_ROOT.glob(BASELINE_GLOB))
    if not baseline_paths:
        raise SystemExit(f"No baseline files found for pattern: {BASELINE_GLOB}")

    baseline_data: Dict[str, pd.DataFrame] = {}
    for path in baseline_paths:
        tid = tournament_id_from_path(path)
        df = pd.read_csv(path)
        required = {"player_id", "win_prob", "top5_prob", "top10_prob", "course_perf_score", "course_starts"}
        missing = required - set(df.columns)
        if missing:
            print(f"Skipping {path.name} (missing columns: {sorted(missing)})")
            continue
        baseline_data[tid] = df

    if not baseline_data:
        raise SystemExit("No usable baseline files for tuning.")

    print(f"Tuning on tournaments: {sorted(baseline_data.keys())}")
    grid = make_grid()
    print(f"Grid size: {len(grid)}")

    results: List[Dict] = []
    for idx, setting in enumerate(grid, 1):
        metrics_by_tid = {}
        for tid, base_df in baseline_data.items():
            adjusted_df = apply_setting(base_df, setting)
            metrics_by_tid[tid] = evaluate_one_tournament(adjusted_df, actuals, tid)

        summary = summarize(metrics_by_tid)
        row = {**setting, **summary}
        row["tournaments_used"] = len(metrics_by_tid)
        results.append(row)

        if idx % 50 == 0:
            print(f"Processed {idx}/{len(grid)} settings...")

    res_df = pd.DataFrame(results).sort_values(
        ["objective", "weighted_brier", "brier_win"],
        ascending=[True, True, True],
    ).reset_index(drop=True)

    baseline_row = res_df[
        (res_df["boost_strength"] == 0.0)
        & (res_df["max_abs_adjust"] == 0.04)
        & (res_df["min_starts"] == 1)
        & (res_df["min_players_with_history"] == 5)
        & (res_df["allow_similar_fallback"] == False)
    ]
    if baseline_row.empty:
        baseline_row = res_df[res_df["boost_strength"] == 0.0].head(1)

    best = res_df.iloc[0].to_dict()
    baseline = baseline_row.iloc[0].to_dict()

    out_csv = OUT_DIR / "course_adjust_tuning_results.csv"
    out_json = OUT_DIR / "course_adjust_tuning_best.json"
    res_df.to_csv(out_csv, index=False)

    payload = {
        "best": best,
        "baseline": baseline,
        "delta_vs_baseline": {
            "objective": float(best["objective"] - baseline["objective"]),
            "weighted_brier": float(best["weighted_brier"] - baseline["weighted_brier"]),
            "brier_win": float(best["brier_win"] - baseline["brier_win"]),
            "brier_top5": float(best["brier_top5"] - baseline["brier_top5"]),
            "brier_top10": float(best["brier_top10"] - baseline["brier_top10"]),
            "top10_hit_rate": float(best["top10_hit_rate"] - baseline["top10_hit_rate"]),
            "winner_rank": float(best["winner_rank"] - baseline["winner_rank"]),
        },
    }
    out_json.write_text(json.dumps(payload, indent=2))

    print("\nTop 10 settings:")
    show_cols = [
        "boost_strength",
        "max_abs_adjust",
        "min_starts",
        "min_players_with_history",
        "allow_similar_fallback",
        "objective",
        "weighted_brier",
        "brier_win",
        "brier_top5",
        "brier_top10",
        "top10_hit_rate",
        "winner_rank",
    ]
    print(res_df[show_cols].head(10).to_string(index=False))
    print(f"\nSaved: {out_csv}")
    print(f"Saved: {out_json}")


if __name__ == "__main__":
    main()
