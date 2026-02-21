#!/usr/bin/env python3
"""
Weekly Fantasy Golf Recommendation
====================================
Usage-adjusted pick recommendations for the current tournament.

The core idea: Scheffler is the #1 pick by raw EV almost every week.
That does NOT mean you should use him every week. With only 3 uses per
player across 30 tournaments, elite players should be saved for high-value
events (Majors, Signatures) where the prize money justifies the spend.

Usage:
    python scripts/planning/weekly_recommendation.py --tournament "Cognizant Classic"
    python scripts/planning/weekly_recommendation.py --tournament "The Masters"
"""

import sys
import argparse
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))

from usage_optimizer import UsageOptimizer


TIER_EMOJI = {
    "MAJOR": "🏆",
    "ELITE": "⭐",
    "SIGNATURE": "💎",
    "STANDARD": "🔵",
    "OPPOSITE": "🟤",
}

REC_EMOJI = {
    "STRONG USE":     "✅✅",
    "USE":            "✅",
    "CONSIDER":       "🤔",
    "SAVE":           "💾",
    "DEFINITELY SAVE":"🛑",
    "CANNOT USE":     "❌",
}


def print_banner(tournament_name: str, tier: str, importance: int, winner_share: float):
    emoji = TIER_EMOJI.get(tier, "")
    print()
    print("=" * 70)
    print(f"  {emoji} WEEKLY PICK RECOMMENDATION")
    print(f"  {tournament_name}")
    print(f"  Tier: {tier}  |  Importance: {importance}/10  |  Winner Share: ${winner_share:,.0f}")
    print("=" * 70)


def print_picks(picks_df: pd.DataFrame):
    if picks_df.empty:
        print("\n  No clear USE picks found — consider re-evaluating or check usage data.")
        return

    print("\n  RECOMMENDED PICKS THIS WEEK:")
    print("  " + "-" * 66)
    print(f"  {'#':<3} {'Player':<24} {'WR':<5} {'EV Rank':<8} {'EV $':<10} {'Top10%':<8} {'Uses':<6} {'Rec'}")
    print("  " + "-" * 66)
    for i, row in picks_df.iterrows():
        rec_str = REC_EMOJI.get(row["recommendation"], row["recommendation"])
        wr = int(row["world_rank"]) if pd.notna(row.get("world_rank")) else "N/A"
        print(
            f"  {i+1:<3} {row['player_name']:<24} {str(wr):<5} #{row['ev_rank']:<7} "
            f"${row['expected_value']:>8,.0f} {row['top10_prob']*100:>5.1f}%   {row['uses_remaining']}/3   {rec_str}"
        )


def print_save_list(save_df: pd.DataFrame, show: int = 8):
    if save_df.empty:
        return

    print("\n\n  SAVE FOR BIGGER EVENTS:")
    print("  " + "-" * 66)
    print(f"  {'Player':<24} {'WR':<5} {'EV Rank':<8} {'Reason'}")
    print("  " + "-" * 66)
    for _, row in save_df.head(show).iterrows():
        wr = int(row["world_rank"]) if pd.notna(row.get("world_rank")) else "N/A"
        save_for = row.get("save_for", "upcoming events")
        rec_str = REC_EMOJI.get(row["recommendation"], row["recommendation"])
        print(f"  {row['player_name']:<24} {str(wr):<5} #{row['ev_rank']:<7} {rec_str}  → {save_for}")


def print_upcoming(upcoming: list):
    if not upcoming:
        return
    print("\n\n  UPCOMING HIGH-VALUE EVENTS:")
    print("  " + "-" * 50)
    for e in upcoming:
        emoji = TIER_EMOJI.get(e["tier"], "")
        print(f"  {emoji} {e['name']:<35} ${e['winner_share']:>10,.0f}  [{e['tier']}]")


def main():
    parser = argparse.ArgumentParser(description="Usage-adjusted weekly pick recommendation")
    parser.add_argument("--tournament", "-t", required=True, help="Tournament name (e.g. 'Cognizant Classic')")
    parser.add_argument("--top-n", type=int, default=40, help="Number of players to evaluate (default: 40)")
    parser.add_argument("--picks", type=int, default=3, help="Number of picks to recommend (default: 3)")
    parser.add_argument("--save-csv", action="store_true", help="Save recommendation to outputs/weekly_recommendation.csv")
    args = parser.parse_args()

    print(f"\nLoading optimizer for: {args.tournament}...")
    optimizer = UsageOptimizer()

    result = optimizer.get_weekly_picks(
        tournament_name=args.tournament,
        n_picks=args.picks,
        top_n=args.top_n,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)

    # Get winner share from calendar
    payout = optimizer.calendar.get_payout_info(args.tournament)
    winner_share = payout.get("winner_share", 0)

    print_banner(
        result["tournament"],
        result["tournament_tier"],
        result["tournament_importance"],
        winner_share,
    )
    print_picks(result["picks"])
    print_save_list(result["save_list"])
    print_upcoming(result["upcoming_events"])

    print("\n")
    print("  USAGE TRACKER:")
    summary = optimizer.get_season_usage_summary()
    print(f"  Players used this season: {summary['total_players_used']}")
    if summary['players_maxed_out']:
        print(f"  Maxed out (0 uses left): {', '.join(summary['players_maxed_out'])}")
    if summary['players_with_1_use']:
        print(f"  1 use left: {', '.join(summary['players_with_1_use'])}")
    print()

    if args.save_csv:
        out_path = PROJECT_ROOT / "outputs" / "weekly_recommendation.csv"
        result["full_ranking"].to_csv(out_path, index=False)
        print(f"  Saved full ranking to: {out_path}")

    print("=" * 70)


if __name__ == "__main__":
    main()
