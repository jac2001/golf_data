#!/usr/bin/env python3
"""
Prediction Performance Tracker
==============================

Tracks and analyzes prediction accuracy over time.
Compares model predictions vs actual tournament results.

Usage:
    python track_performance.py --record R2026005     # Record results for tournament
    python track_performance.py --report             # Generate performance report
    python track_performance.py --roi                # Calculate ROI
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LIVE_DIR = DATA_DIR / "live"
PERFORMANCE_DIR = DATA_DIR / "performance"


def load_predictions(tournament_id: str) -> Optional[pd.DataFrame]:
    """Load predictions for a tournament."""
    # Try different naming conventions
    patterns = [
        OUTPUTS_DIR / f"{tournament_id}_predictions.csv",
        OUTPUTS_DIR / f"{tournament_id.lower()}_predictions.csv",
    ]

    # Also search for any predictions file with tournament ID
    for f in OUTPUTS_DIR.glob("*_predictions.csv"):
        if tournament_id.lower() in f.stem.lower():
            patterns.insert(0, f)

    for path in patterns:
        if path.exists():
            df = pd.read_csv(path)
            print(f"Loaded predictions from {path.name}")
            return df

    print(f"No predictions found for {tournament_id}")
    return None


def load_results(tournament_id: str) -> Optional[pd.DataFrame]:
    """Load tournament results (final leaderboard)."""
    patterns = [
        LIVE_DIR / f"leaderboard_{tournament_id.lower()}.csv",
        LIVE_DIR / f"leaderboard_{tournament_id}.csv",
    ]

    for path in patterns:
        if path.exists():
            df = pd.read_csv(path)
            print(f"Loaded results from {path.name}")
            return df

    print(f"No results found for {tournament_id}")
    return None


def normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    if pd.isna(name):
        return ""
    name = str(name).lower().strip()
    # Remove common suffixes
    for suffix in [" jr.", " jr", " iii", " ii", " iv"]:
        name = name.replace(suffix, "")
    # Remove special characters
    name = "".join(c for c in name if c.isalnum() or c.isspace())
    return name


def match_predictions_to_results(
    predictions: pd.DataFrame,
    results: pd.DataFrame
) -> pd.DataFrame:
    """Match prediction data to actual results."""

    # Normalize names for matching
    predictions = predictions.copy()
    results = results.copy()

    predictions["name_key"] = predictions["player_name"].apply(normalize_name)
    results["name_key"] = results["player_name"].apply(normalize_name)

    # Merge on normalized name
    merged = predictions.merge(
        results[["name_key", "position", "total", "made_cut", "total_strokes"]],
        on="name_key",
        how="left",
        suffixes=("_pred", "_actual")
    )

    # Parse actual position to numeric
    def parse_position(pos):
        if pd.isna(pos):
            return 999
        pos_str = str(pos).upper()
        if pos_str in ["CUT", "MC", "WD", "DQ"]:
            return 999
        # Handle "T5" -> 5
        pos_str = pos_str.replace("T", "")
        try:
            return int(pos_str)
        except ValueError:
            return 999

    merged["actual_position"] = merged["position"].apply(parse_position)
    merged["predicted_rank"] = range(1, len(merged) + 1)

    return merged


def calculate_metrics(matched_df: pd.DataFrame) -> Dict:
    """Calculate performance metrics."""
    df = matched_df.copy()

    # Filter to players with actual results
    df = df[df["actual_position"] < 999]

    if df.empty:
        return {"error": "No matched results"}

    metrics = {}

    # Winner prediction
    predicted_winner = df.iloc[0]["player_name"]
    actual_winner_row = df[df["actual_position"] == 1]
    actual_winner = actual_winner_row["player_name"].iloc[0] if not actual_winner_row.empty else "Unknown"
    metrics["predicted_winner"] = predicted_winner
    metrics["actual_winner"] = actual_winner
    metrics["winner_correct"] = predicted_winner.lower() == actual_winner.lower()

    # Top 5 accuracy
    predicted_top5 = set(df.head(5)["name_key"].tolist())
    actual_top5 = set(df[df["actual_position"] <= 5]["name_key"].tolist())
    top5_overlap = len(predicted_top5 & actual_top5)
    metrics["top5_hits"] = top5_overlap
    metrics["top5_accuracy"] = top5_overlap / 5 if len(actual_top5) >= 5 else top5_overlap / len(actual_top5)

    # Top 10 accuracy
    predicted_top10 = set(df.head(10)["name_key"].tolist())
    actual_top10 = set(df[df["actual_position"] <= 10]["name_key"].tolist())
    top10_overlap = len(predicted_top10 & actual_top10)
    metrics["top10_hits"] = top10_overlap
    metrics["top10_accuracy"] = top10_overlap / 10 if len(actual_top10) >= 10 else top10_overlap / len(actual_top10)

    # Top 20 accuracy
    predicted_top20 = set(df.head(20)["name_key"].tolist())
    actual_top20 = set(df[df["actual_position"] <= 20]["name_key"].tolist())
    top20_overlap = len(predicted_top20 & actual_top20)
    metrics["top20_hits"] = top20_overlap
    metrics["top20_accuracy"] = top20_overlap / 20 if len(actual_top20) >= 20 else top20_overlap / len(actual_top20)

    # Rank correlation (Spearman)
    from scipy import stats
    valid_df = df[(df["actual_position"] < 999) & (df["predicted_rank"] <= 50)]
    if len(valid_df) > 5:
        corr, pval = stats.spearmanr(valid_df["predicted_rank"], valid_df["actual_position"])
        metrics["rank_correlation"] = corr
        metrics["rank_correlation_pval"] = pval
    else:
        metrics["rank_correlation"] = None

    # Cut accuracy
    if "made_cut" in df.columns:
        predicted_make_cut = set(df.head(70)["name_key"].tolist())  # Assume top 70 predicted to make cut
        actually_made_cut = set(df[df["made_cut"] == True]["name_key"].tolist())
        cut_hits = len(predicted_make_cut & actually_made_cut)
        metrics["cut_prediction_accuracy"] = cut_hits / len(actually_made_cut) if actually_made_cut else 0

    # Mean absolute error of predicted rank vs actual
    valid_df = df[(df["actual_position"] < 999) & (df["predicted_rank"] <= 100)]
    if not valid_df.empty:
        mae = np.abs(valid_df["predicted_rank"] - valid_df["actual_position"]).mean()
        metrics["rank_mae"] = mae

    return metrics


def calculate_roi(matched_df: pd.DataFrame, bet_amount: float = 100) -> Dict:
    """Calculate ROI for various betting strategies."""
    df = matched_df.copy()
    df = df[df["actual_position"] < 999]

    if df.empty or "win_prob" not in df.columns:
        return {"error": "Insufficient data for ROI calculation"}

    roi_results = {}

    # Strategy 1: Bet on model's top pick to win
    top_pick = df.iloc[0]
    win_prob = top_pick.get("win_prob", 0.05)
    implied_odds = (1 / win_prob) if win_prob > 0 else 20

    # Assume average sportsbook odds are ~90% of implied (vig)
    payout_odds = implied_odds * 0.9

    won = top_pick["actual_position"] == 1
    if won:
        profit = bet_amount * (payout_odds - 1)
    else:
        profit = -bet_amount

    roi_results["top_pick_to_win"] = {
        "player": top_pick["player_name"],
        "won": won,
        "bet": bet_amount,
        "profit": profit,
        "roi_pct": (profit / bet_amount) * 100
    }

    # Strategy 2: Top 5 finish for top 5 picks
    top5_picks = df.head(5)
    wins = 0
    total_profit = 0
    for _, row in top5_picks.iterrows():
        top5_prob = row.get("top5_prob", 0.2)
        implied = (1 / top5_prob) if top5_prob > 0 else 5
        payout = implied * 0.9
        won = row["actual_position"] <= 5
        if won:
            total_profit += bet_amount * (payout - 1)
            wins += 1
        else:
            total_profit -= bet_amount

    roi_results["top5_finish_strategy"] = {
        "bets": 5,
        "wins": wins,
        "total_bet": bet_amount * 5,
        "profit": total_profit,
        "roi_pct": (total_profit / (bet_amount * 5)) * 100
    }

    # Strategy 3: Top 10 finish for top 10 picks
    top10_picks = df.head(10)
    wins = 0
    total_profit = 0
    for _, row in top10_picks.iterrows():
        top10_prob = row.get("top10_prob", 0.3)
        implied = (1 / top10_prob) if top10_prob > 0 else 3.33
        payout = implied * 0.9
        won = row["actual_position"] <= 10
        if won:
            total_profit += bet_amount * (payout - 1)
            wins += 1
        else:
            total_profit -= bet_amount

    roi_results["top10_finish_strategy"] = {
        "bets": 10,
        "wins": wins,
        "total_bet": bet_amount * 10,
        "profit": total_profit,
        "roi_pct": (total_profit / (bet_amount * 10)) * 100
    }

    return roi_results


def record_tournament_performance(tournament_id: str, tournament_name: str = None):
    """Record performance for a completed tournament."""
    predictions = load_predictions(tournament_id)
    results = load_results(tournament_id)

    if predictions is None or results is None:
        print("Cannot record performance - missing predictions or results")
        return

    matched = match_predictions_to_results(predictions, results)
    metrics = calculate_metrics(matched)
    roi = calculate_roi(matched)

    record = {
        "tournament_id": tournament_id,
        "tournament_name": tournament_name or tournament_id,
        "recorded_at": datetime.now().isoformat(),
        "player_count": len(matched),
        "matched_count": len(matched[matched["actual_position"] < 999]),
        "metrics": metrics,
        "roi": roi,
    }

    # Save individual record
    PERFORMANCE_DIR.mkdir(parents=True, exist_ok=True)
    record_path = PERFORMANCE_DIR / f"performance_{tournament_id}.json"
    with open(record_path, "w") as f:
        json.dump(record, f, indent=2, default=str)
    print(f"Saved performance record to {record_path}")

    # Update aggregate history
    history_path = PERFORMANCE_DIR / "performance_history.json"
    if history_path.exists():
        with open(history_path) as f:
            history = json.load(f)
    else:
        history = {"tournaments": []}

    # Remove existing record for same tournament
    history["tournaments"] = [
        t for t in history["tournaments"]
        if t.get("tournament_id") != tournament_id
    ]
    history["tournaments"].append(record)

    with open(history_path, "w") as f:
        json.dump(history, f, indent=2, default=str)
    print(f"Updated performance history")

    # Print summary
    print(f"\nPerformance Summary: {tournament_name or tournament_id}")
    print("=" * 50)
    print(f"Predicted Winner: {metrics.get('predicted_winner', 'N/A')}")
    print(f"Actual Winner: {metrics.get('actual_winner', 'N/A')}")
    print(f"Winner Correct: {'Yes' if metrics.get('winner_correct') else 'No'}")
    print(f"\nTop-5 Hits: {metrics.get('top5_hits', 0)}/5 ({metrics.get('top5_accuracy', 0)*100:.1f}%)")
    print(f"Top-10 Hits: {metrics.get('top10_hits', 0)}/10 ({metrics.get('top10_accuracy', 0)*100:.1f}%)")
    print(f"Top-20 Hits: {metrics.get('top20_hits', 0)}/20 ({metrics.get('top20_accuracy', 0)*100:.1f}%)")

    if metrics.get("rank_correlation") is not None:
        print(f"\nRank Correlation: {metrics['rank_correlation']:.3f}")

    if "error" not in roi:
        print(f"\nROI (Top Pick to Win): {roi['top_pick_to_win']['roi_pct']:.1f}%")
        print(f"ROI (Top 5 Finish): {roi['top5_finish_strategy']['roi_pct']:.1f}%")


def generate_report():
    """Generate aggregate performance report."""
    history_path = PERFORMANCE_DIR / "performance_history.json"

    if not history_path.exists():
        print("No performance history found. Record some tournaments first.")
        return

    with open(history_path) as f:
        history = json.load(f)

    tournaments = history.get("tournaments", [])
    if not tournaments:
        print("No tournaments in history")
        return

    print(f"\nAggregate Performance Report")
    print("=" * 60)
    print(f"Tournaments Tracked: {len(tournaments)}")

    # Aggregate metrics
    winner_correct = sum(1 for t in tournaments if t.get("metrics", {}).get("winner_correct"))
    top5_total = sum(t.get("metrics", {}).get("top5_hits", 0) for t in tournaments)
    top10_total = sum(t.get("metrics", {}).get("top10_hits", 0) for t in tournaments)
    top20_total = sum(t.get("metrics", {}).get("top20_hits", 0) for t in tournaments)

    correlations = [
        t.get("metrics", {}).get("rank_correlation")
        for t in tournaments
        if t.get("metrics", {}).get("rank_correlation") is not None
    ]

    print(f"\nWinner Predictions: {winner_correct}/{len(tournaments)} ({winner_correct/len(tournaments)*100:.1f}%)")
    print(f"Total Top-5 Hits: {top5_total}/{len(tournaments)*5} ({top5_total/(len(tournaments)*5)*100:.1f}%)")
    print(f"Total Top-10 Hits: {top10_total}/{len(tournaments)*10} ({top10_total/(len(tournaments)*10)*100:.1f}%)")
    print(f"Total Top-20 Hits: {top20_total}/{len(tournaments)*20} ({top20_total/(len(tournaments)*20)*100:.1f}%)")

    if correlations:
        avg_corr = np.mean(correlations)
        print(f"\nAverage Rank Correlation: {avg_corr:.3f}")

    # ROI summary
    total_profit = 0
    total_bet = 0
    for t in tournaments:
        roi = t.get("roi", {})
        if "top10_finish_strategy" in roi:
            total_profit += roi["top10_finish_strategy"].get("profit", 0)
            total_bet += roi["top10_finish_strategy"].get("total_bet", 0)

    if total_bet > 0:
        overall_roi = (total_profit / total_bet) * 100
        print(f"\nOverall ROI (Top-10 Strategy): {overall_roi:.1f}%")
        print(f"Total Profit: ${total_profit:,.0f} on ${total_bet:,.0f} wagered")

    # Per-tournament breakdown
    print(f"\n{'Tournament':<30} {'Winner?':<10} {'Top5':<8} {'Top10':<8} {'Corr':<8}")
    print("-" * 70)
    for t in tournaments:
        name = t.get("tournament_name", t.get("tournament_id", "Unknown"))[:29]
        metrics = t.get("metrics", {})
        winner = "Yes" if metrics.get("winner_correct") else "No"
        top5 = f"{metrics.get('top5_hits', 0)}/5"
        top10 = f"{metrics.get('top10_hits', 0)}/10"
        corr = f"{metrics.get('rank_correlation', 0):.2f}" if metrics.get("rank_correlation") else "-"
        print(f"{name:<30} {winner:<10} {top5:<8} {top10:<8} {corr:<8}")


def main():
    parser = argparse.ArgumentParser(description="Track prediction performance")
    parser.add_argument("--record", help="Record results for tournament ID")
    parser.add_argument("--name", help="Tournament name (with --record)")
    parser.add_argument("--report", action="store_true", help="Generate aggregate report")
    parser.add_argument("--roi", action="store_true", help="Show ROI analysis")
    args = parser.parse_args()

    if args.record:
        record_tournament_performance(args.record, args.name)
    elif args.report or args.roi:
        generate_report()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
