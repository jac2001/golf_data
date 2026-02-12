#!/usr/bin/env python3
"""
Season Dashboard - Full Season View & Player Allocation Planning
=================================================================

Shows:
1. All tournaments with importance scores
2. Recommended player allocations across the season
3. "When to use [Player]" type planning
4. Season overview with key strategic insights

Usage:
    # Show full season calendar with importance
    python scripts/planning/season_dashboard.py --calendar

    # When to use a specific player
    python scripts/planning/season_dashboard.py --player "Scottie Scheffler"

    # Show allocation plan for top players
    python scripts/planning/season_dashboard.py --top-players 10

    # Full dashboard
    python scripts/planning/season_dashboard.py --full
"""

import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json

# Import from season_planner
try:
    from scripts.planning.season_planner import (
        TOURNAMENT_CALENDAR_2026,
        load_tournament_calendar,
        load_player_qualifications,
        recommend_tournaments_for_player,
        load_course_history,
        PlayerQualification,
    )
except ImportError:
    import sys
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from scripts.planning.season_planner import (
        TOURNAMENT_CALENDAR_2026,
        load_tournament_calendar,
        load_player_qualifications,
        recommend_tournaments_for_player,
        load_course_history,
        PlayerQualification,
    )

# Reload calendar to ensure it's fresh
def get_tournament_calendar():
    """Get tournament calendar, reloading if needed."""
    global TOURNAMENT_CALENDAR_2026
    if not TOURNAMENT_CALENDAR_2026:
        TOURNAMENT_CALENDAR_2026 = load_tournament_calendar()
    return TOURNAMENT_CALENDAR_2026

PROJECT_ROOT = Path("/Users/jacklegnon/Desktop/golf_data")
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


# Tournament importance scores (1-10)
def calculate_tournament_importance(tournament: Dict) -> Tuple[int, str]:
    """Calculate importance score and reasoning for a tournament."""
    score = 5  # Base score
    reasons = []

    # Type-based scoring
    if tournament["type"] == "Major":
        score = 10
        reasons.append("MAJOR")
    elif tournament["type"] == "Playoffs":
        score = 9
        reasons.append("PLAYOFFS")
    elif tournament["type"] == "Signature":
        score = 8
        reasons.append("Signature Event")
    else:
        score = 5
        reasons.append("Standard")

    # Purse adjustment
    purse_m = tournament["purse"] / 1_000_000
    if purse_m >= 20:
        score = min(10, score + 1)
        reasons.append(f"${purse_m:.0f}M purse")
    elif purse_m >= 15:
        reasons.append(f"${purse_m:.0f}M purse")
    elif purse_m < 9:
        score = max(1, score - 1)
        reasons.append(f"${purse_m:.1f}M purse")

    return score, ", ".join(reasons)


def get_tournament_status(tournament: Dict) -> str:
    """Get status relative to current date."""
    today = datetime.now().date()
    tourney_date = datetime.strptime(tournament["date"], "%Y-%m-%d").date()

    if tourney_date < today:
        return "COMPLETED"
    elif tourney_date == today:
        return "IN PROGRESS"
    elif (tourney_date - today).days <= 7:
        return "THIS WEEK"
    elif (tourney_date - today).days <= 14:
        return "NEXT WEEK"
    else:
        return "UPCOMING"


def print_season_calendar():
    """Print full season calendar with importance scores."""
    calendar = get_tournament_calendar()

    print("\n" + "=" * 90)
    print("  2026 PGA TOUR SEASON - TOURNAMENT IMPORTANCE RANKINGS")
    print("=" * 90)
    print()
    print(f"{'#':<3} {'Tournament':<35} {'Date':<12} {'Type':<10} {'Purse':<12} {'Score':<6} {'Status'}")
    print("-" * 90)

    for i, tourney in enumerate(calendar, 1):
        score, _ = calculate_tournament_importance(tourney)
        status = get_tournament_status(tourney)
        purse_str = f"${tourney['purse']/1_000_000:.0f}M"

        # Importance indicator
        if score >= 9:
            indicator = "🏆"
        elif score >= 7:
            indicator = "⭐"
        else:
            indicator = "  "

        # Status color indicator
        status_str = status
        if status == "THIS WEEK":
            status_str = ">>> THIS WEEK <<<"
        elif status == "COMPLETED":
            status_str = "✓ Done"

        print(f"{i:<3} {indicator} {tourney['name']:<33} {tourney['date']:<12} {tourney['type']:<10} {purse_str:<12} {score}/10   {status_str}")

    # Summary
    print("-" * 90)
    majors = sum(1 for t in calendar if t["type"] == "Major")
    signatures = sum(1 for t in calendar if t["type"] == "Signature")
    playoffs = sum(1 for t in calendar if t["type"] == "Playoffs")
    standards = sum(1 for t in calendar if t["type"] == "Standard")

    print(f"\n  Total: {len(calendar)} tournaments")
    print(f"  🏆 Majors: {majors} | ⭐ Signatures: {signatures} | Playoffs: {playoffs} | Standard: {standards}")
    print()


def print_player_usage_plan(player_name: str, num_uses: int = 3):
    """Print when to use a specific player."""
    calendar = get_tournament_calendar()

    print("\n" + "=" * 80)
    print(f"  WHEN TO USE: {player_name.upper()}")
    print("=" * 80)

    qualifications = load_player_qualifications()
    recommendations = recommend_tournaments_for_player(player_name, num_uses, qualifications)

    if not recommendations:
        print(f"\n  No tournament data available for {player_name}")
        return

    # Show top recommendations
    print(f"\n  RECOMMENDED USAGE (Best {num_uses} tournaments):")
    print("-" * 80)

    total_ev = 0
    for i, rec in enumerate(recommendations[:num_uses], 1):
        stars = "★" * rec.rating + "☆" * (5 - rec.rating)
        matching = [t for t in calendar if t["name"] == rec.tournament_name]
        score = 5  # default
        if matching:
            score, _ = calculate_tournament_importance(matching[0])

        total_ev += rec.expected_value

        print(f"\n  USE #{i}: {rec.tournament_name}")
        print(f"          Date: {rec.tournament_date} | Type: {rec.tournament_type}")
        print(f"          Tournament Importance: {score}/10")
        print(f"          Expected Value: ${rec.expected_value:,.0f}")
        print(f"          Course History: {rec.course_history}")
        print(f"          Rating: {stars}")
        print(f"          Why: {rec.reasoning}")

    print("-" * 80)
    print(f"\n  TOTAL EXPECTED VALUE (3 uses): ${total_ev:,.0f}")

    # Show what to skip
    if len(recommendations) > num_uses:
        print(f"\n  TOURNAMENTS TO SKIP (for {player_name}):")
        print("-" * 80)

        skip_list = recommendations[num_uses:num_uses+5]
        for rec in skip_list:
            matching = [t for t in calendar if t["name"] == rec.tournament_name]
            score = 5
            if matching:
                score, _ = calculate_tournament_importance(matching[0])
            print(f"  - {rec.tournament_name} ({rec.tournament_date})")
            print(f"    Importance: {score}/10 | EV: ${rec.expected_value:,.0f} | {rec.course_history}")

    # Show majors status
    player_qual = qualifications.get(player_name.lower())
    if player_qual:
        print(f"\n  MAJOR CHAMPIONSHIP STATUS:")
        print("-" * 80)
        # Map display names to search patterns that match schedule_2026.csv
        majors = [
            ("The Masters", ["masters"]),
            ("PGA Championship", ["pga championship"]),
            ("U.S. Open", ["u.s. open"]),
            ("The Open Championship", ["open championship"]),
        ]
        for major_name, patterns in majors:
            can_play = any(
                any(p in rec.tournament_name.lower() for p in patterns)
                for rec in recommendations
            )
            status = "✓ QUALIFIED" if can_play else "✗ Not qualified"
            in_top3 = any(
                any(p in rec.tournament_name.lower() for p in patterns)
                for rec in recommendations[:3]
            )
            if can_play and in_top3:
                status += " (RECOMMENDED USE)"
            print(f"  {major_name}: {status}")

    print()


def print_top_players_allocation(num_players: int = 10):
    """Print allocation plan for top players."""
    print("\n" + "=" * 90)
    print("  TOP PLAYER ALLOCATION MATRIX")
    print("=" * 90)

    # Load player list - prefer OWGR for accurate world rankings
    players = []

    # Try OWGR first (has "Scottie Scheffler" format)
    owgr_path = DATA_DIR / "rankings" / "owgr_2026.csv"
    if owgr_path.exists():
        df = pd.read_csv(owgr_path)
        if "world_rank" in df.columns:
            top = df.nsmallest(num_players, "world_rank")
            players = top["player_name"].tolist()

    # Fallback to predictions if no OWGR
    if not players:
        pred_path = OUTPUTS_DIR / "latest_predictions.csv"
        if pred_path.exists():
            df = pd.read_csv(pred_path)
            if "world_rank" in df.columns:
                top = df.nsmallest(num_players, "world_rank")
                # Convert "Last, First" to "First Last" format
                raw_names = top["player_name"].tolist()
                for name in raw_names:
                    if "," in name:
                        parts = name.split(",")
                        players.append(f"{parts[1].strip()} {parts[0].strip()}")
                    else:
                        players.append(name)

    # Fallback to hardcoded elite players
    if not players:
        players = [
            "Scottie Scheffler", "Xander Schauffele", "Rory McIlroy",
            "Jon Rahm", "Collin Morikawa", "Viktor Hovland",
            "Patrick Cantlay", "Ludvig Aberg", "Wyndham Clark",
            "Tommy Fleetwood"
        ][:num_players]

    qualifications = load_player_qualifications()

    print(f"\n  Showing recommended tournaments for top {len(players)} players\n")

    # Header - show key tournaments
    key_tournaments = [
        ("Masters", "MAS"),
        ("PGA Champ", "PGA"),
        ("US Open", "US"),
        ("Open Champ", "OPEN"),
        ("PLAYERS", "TPC"),
        ("Memorial", "MEM"),
    ]

    # Build allocation matrix
    print(f"{'Player':<25} {'Use 1':<20} {'Use 2':<20} {'Use 3':<20}")
    print("-" * 90)

    for player in players:
        recs = recommend_tournaments_for_player(player, 3, qualifications)
        if recs:
            use1 = recs[0].tournament_name[:18] if len(recs) > 0 else "-"
            use2 = recs[1].tournament_name[:18] if len(recs) > 1 else "-"
            use3 = recs[2].tournament_name[:18] if len(recs) > 2 else "-"

            # Add score indicator
            score1 = f"({recs[0].rating}★)" if len(recs) > 0 else ""
            score2 = f"({recs[1].rating}★)" if len(recs) > 1 else ""
            score3 = f"({recs[2].rating}★)" if len(recs) > 2 else ""

            print(f"{player:<25} {use1:<16}{score1:<4} {use2:<16}{score2:<4} {use3:<16}{score3:<4}")
        else:
            print(f"{player:<25} {'No data':<20} {'':<20} {'':<20}")

    print()

    # Show tournament concentration
    print("\n  TOURNAMENT DEMAND (how many top players should use here):")
    print("-" * 90)

    tournament_demand = {}
    for player in players:
        recs = recommend_tournaments_for_player(player, 3, qualifications)
        for rec in recs[:3]:
            tournament_demand[rec.tournament_name] = tournament_demand.get(rec.tournament_name, 0) + 1

    sorted_demand = sorted(tournament_demand.items(), key=lambda x: x[1], reverse=True)
    for tourney, count in sorted_demand[:10]:
        bar = "█" * count + "░" * (num_players - count)
        print(f"  {tourney:<35} {bar} {count}/{num_players}")

    print()


def print_strategic_insights():
    """Print key strategic insights for the season."""
    print("\n" + "=" * 80)
    print("  SEASON STRATEGY INSIGHTS")
    print("=" * 80)

    # Find highest value periods
    print("\n  KEY STRETCHES TO TARGET:")
    print("-" * 80)

    # April (Masters + RBC Heritage)
    print("  📅 April 9-20: Masters → RBC Heritage")
    print("     Two elite events back-to-back. Consider using top players here.")

    # May-June (PGA + Memorial + US Open)
    print("\n  📅 May 14 - June 18: PGA Championship → Memorial → US Open")
    print("     Three major/signature events. Peak usage period for elite players.")

    # August Playoffs
    print("\n  📅 August 13-27: FedEx Playoffs")
    print("     Season-ending stretch. Save 1 use for playoff performers.")

    # Elite player strategy
    print("\n  ELITE PLAYER STRATEGY (Top 5 OWGR):")
    print("-" * 80)
    print("  - Save uses for Majors + highest-purse Signatures")
    print("  - Don't waste on standard $8M events")
    print("  - Exception: If player dominates a course (e.g., Scheffler at Bay Hill)")

    # Value player strategy
    print("\n  VALUE PLAYER STRATEGY (Rank 20-50):")
    print("-" * 80)
    print("  - Target weaker-field events where they can compete")
    print("  - Look for course history advantages")
    print("  - Standard events with $9M+ purses are good value")

    # Course specialist strategy
    print("\n  COURSE SPECIALIST STRATEGY:")
    print("-" * 80)
    print("  - Use players at courses where they've won or consistently finished top-10")
    print("  - Example: Hideki Matsuyama at TPC Scottsdale (Phoenix Open)")
    print("  - Example: Harris English at Waialae (Sony Open)")

    print()


def print_full_dashboard():
    """Print the complete season dashboard."""
    print_season_calendar()
    print_strategic_insights()
    print_top_players_allocation(10)


def generate_markdown_report(output_path: Path = None):
    """Generate a markdown report of the season plan."""
    if output_path is None:
        output_path = OUTPUTS_DIR / "season_plan_2026.md"

    calendar = get_tournament_calendar()

    lines = []
    lines.append("# 2026 PGA Tour Season Plan")
    lines.append(f"\n*Generated: {datetime.now().strftime('%B %d, %Y')}*\n")

    # Tournament calendar
    lines.append("## Tournament Calendar\n")
    lines.append("| # | Tournament | Date | Type | Purse | Importance |")
    lines.append("|---|------------|------|------|-------|------------|")

    for i, tourney in enumerate(calendar, 1):
        score, reason = calculate_tournament_importance(tourney)
        purse_str = f"${tourney['purse']/1_000_000:.0f}M"
        stars = "★" * min(score // 2, 5)
        lines.append(f"| {i} | {tourney['name']} | {tourney['date']} | {tourney['type']} | {purse_str} | {score}/10 {stars} |")

    lines.append("\n## Key Tournament Tiers\n")
    lines.append("- **Tier 1 (9-10)**: Majors & Playoffs - Must-use for elite players")
    lines.append("- **Tier 2 (7-8)**: Signature Events - High value, use strategically")
    lines.append("- **Tier 3 (5-6)**: Standard Events - Save for course specialists")
    lines.append("- **Tier 4 (3-4)**: Opposite Field - Only if desperate")

    # Write file
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Season Dashboard - Full Season Planning View")
    parser.add_argument("--calendar", action="store_true", help="Show tournament calendar with importance scores")
    parser.add_argument("--player", "-p", help="Show when to use a specific player")
    parser.add_argument("--top-players", "-t", type=int, help="Show allocation for top N players")
    parser.add_argument("--insights", action="store_true", help="Show strategic insights")
    parser.add_argument("--full", action="store_true", help="Show full dashboard")
    parser.add_argument("--export", action="store_true", help="Export to markdown report")

    args = parser.parse_args()

    # Default to calendar if no args
    if not any([args.calendar, args.player, args.top_players, args.insights, args.full, args.export]):
        args.calendar = True

    if args.full:
        print_full_dashboard()
    else:
        if args.calendar:
            print_season_calendar()
        if args.player:
            print_player_usage_plan(args.player)
        if args.top_players:
            print_top_players_allocation(args.top_players)
        if args.insights:
            print_strategic_insights()
        if args.export:
            generate_markdown_report()


if __name__ == "__main__":
    main()
