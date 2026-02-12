#!/usr/bin/env python3
"""
Season Usage Planner
=====================
Optimizes when to use your 3 uses per player across the season.

Key Features:
- Loads player qualification data (which tournaments they can play)
- Tournament calendar with purses, dates, courses
- Calculates expected value for each player × tournament combo
- Recommends optimal 3 tournaments for each player

Usage:
    # Get season plan for a player
    python scripts/planning/season_planner.py --player "Scottie Scheffler"

    # Get full season optimization
    python scripts/planning/season_planner.py --optimize

    # Show tournament calendar
    python scripts/planning/season_planner.py --calendar
"""

import argparse
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Import Tournament ROI data for historical fantasy value
try:
    from scripts.analysis.player_roi import (
        load_tournament_roi_data,
        get_tournament_roi_summary,
        TournamentROI,
    )
    TOURNAMENT_ROI_AVAILABLE = True
except ImportError:
    try:
        import sys
        project_root = Path(__file__).parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from scripts.analysis.player_roi import (
            load_tournament_roi_data,
            get_tournament_roi_summary,
            TournamentROI,
        )
        TOURNAMENT_ROI_AVAILABLE = True
    except ImportError:
        TOURNAMENT_ROI_AVAILABLE = False
        load_tournament_roi_data = None

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path("/Users/jacklegnon/Desktop/golf_data")
DATA_DIR = PROJECT_ROOT / "data"
SCHEDULE_PATH = DATA_DIR / "raw" / "schedule_2026.csv"

# Qualification codes
QUAL_CODES = {
    "SE": "Signature Events",
    "TPC": "THE PLAYERS Championship",
    "MAS": "Masters Tournament",
    "PGA": "PGA Championship",
    "US": "U.S. Open",
    "OPEN": "The Open Championship",
}

# ============================================================================
# 2026 Tournament Calendar - Loaded from CSV
# ============================================================================

def load_tournament_calendar() -> List[Dict]:
    """Load tournament calendar from schedule_2026.csv."""
    if not SCHEDULE_PATH.exists():
        print(f"  Warning: Schedule file not found at {SCHEDULE_PATH}")
        return []

    df = pd.read_csv(SCHEDULE_PATH)
    calendar = []

    for _, row in df.iterrows():
        # Parse purse (remove $ and commas)
        purse_str = str(row.get("purse", "0"))
        purse = int(float(purse_str.replace("$", "").replace(",", "")))

        # Map tournament type
        tourney_type = str(row.get("tournament_type", "Standard"))
        if tourney_type == "Playoff":
            tourney_type = "Playoffs"

        # Determine qualification requirements based on tournament type/name
        qual = []
        name = row.get("tournament_name", "")
        if tourney_type == "Signature":
            qual.append("SE")
        if "PLAYERS" in name.upper():
            qual.append("TPC")
        if "MASTERS" in name.upper():
            qual.append("MAS")
        if "PGA CHAMPIONSHIP" in name.upper():
            qual.append("PGA")
        if "U.S. OPEN" in name.upper():
            qual.append("US")
        if "OPEN CHAMPIONSHIP" in name.upper():
            qual.append("OPEN")

        calendar.append({
            "name": name,
            "date": row.get("start_date", ""),
            "purse": purse,
            "type": tourney_type,
            "course": row.get("location", ""),
            "tournament_id": row.get("tournament_id", ""),
            "qual": qual,
            "week": int(row.get("week", 0)) if pd.notna(row.get("week")) else 0,
        })

    return calendar

# Load calendar on module import
TOURNAMENT_CALENDAR_2026 = load_tournament_calendar()


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PlayerQualification:
    """Player's tournament qualifications."""
    name: str
    qualified_events: List[str]  # List of qual codes: SE, TPC, MAS, PGA, US, OPEN

    def can_play(self, tournament: Dict) -> bool:
        """Check if player can play this tournament."""
        # Standard events - anyone can play (if they have status)
        if not tournament.get("qual"):
            return True
        # Check if player has any of the required qualifications
        return any(q in self.qualified_events for q in tournament.get("qual", []))

    def can_play_majors(self) -> List[str]:
        """Return list of majors player is qualified for."""
        majors = []
        if "MAS" in self.qualified_events:
            majors.append("Masters")
        if "PGA" in self.qualified_events:
            majors.append("PGA Championship")
        if "US" in self.qualified_events:
            majors.append("U.S. Open")
        if "OPEN" in self.qualified_events:
            majors.append("The Open")
        return majors

    def can_play_signatures(self) -> bool:
        """Check if player can play Signature Events."""
        return "SE" in self.qualified_events


@dataclass
class TournamentRecommendation:
    """Recommendation for using a player at a tournament."""
    tournament_name: str
    tournament_date: str
    purse: int
    tournament_type: str
    expected_value: float
    course_fit: float
    course_history: str
    rating: int  # 1-5 stars
    reasoning: str


# ============================================================================
# Data Loading
# ============================================================================

def load_player_qualifications() -> Dict[str, PlayerQualification]:
    """Load player qualification data from CSV."""
    qual_path = DATA_DIR / "raw" / "Event_Qualication.csv"

    if not qual_path.exists():
        print(f"  Warning: Qualification file not found at {qual_path}")
        return {}

    df = pd.read_csv(qual_path)

    qualifications = {}
    for _, row in df.iterrows():
        golfer = row.get("Golfer", "")
        qualified = row.get("Qualified", "")

        if not golfer or pd.isna(golfer):
            continue

        # Parse qualification codes
        if pd.isna(qualified):
            qual_codes = []
        else:
            qual_codes = [q.strip() for q in str(qualified).split(",")]

        qualifications[golfer.lower()] = PlayerQualification(
            name=golfer,
            qualified_events=qual_codes
        )

    return qualifications


def load_course_history(player_name: str) -> Dict[str, Dict]:
    """Load player's course history from betting profiles."""
    profiles_dir = DATA_DIR / "betting_profiles"

    course_history = {}

    for profile_file in profiles_dir.glob("betting_profiles_*.csv"):
        try:
            df = pd.read_csv(profile_file)
            matches = df[df["player_name"].str.lower().str.contains(player_name.lower(), na=False)]
            if len(matches) > 0:
                row = matches.iloc[0]
                history_json = row.get("course_history", "")
                if history_json and not pd.isna(history_json):
                    history = json.loads(history_json)
                    for course in history:
                        course_name = course.get("course_name", "")
                        if course_name:
                            course_history[course_name.lower()] = course
        except Exception:
            pass

    return course_history


def load_predictions() -> Optional[pd.DataFrame]:
    """Load latest predictions."""
    pred_path = PROJECT_ROOT / "outputs" / "latest_predictions.csv"
    if pred_path.exists():
        return pd.read_csv(pred_path)
    return None


# ============================================================================
# Season Planning
# ============================================================================

def get_player_tournament_schedule(
    player_name: str,
    qualifications: Dict[str, PlayerQualification]
) -> List[Dict]:
    """Get list of tournaments a player can play."""

    # Find player qualification
    player_qual = qualifications.get(player_name.lower())

    eligible_tournaments = []
    for tournament in TOURNAMENT_CALENDAR_2026:
        if player_qual is None:
            # No qualification data - assume can play standard events only
            if tournament["type"] == "Standard":
                eligible_tournaments.append(tournament)
        elif player_qual.can_play(tournament):
            eligible_tournaments.append(tournament)

    return eligible_tournaments


def calculate_tournament_value(
    player_name: str,
    tournament: Dict,
    course_history: Dict[str, Dict],
    predictions: Optional[pd.DataFrame] = None
) -> Tuple[float, float, str]:
    """
    Calculate expected value for a player at a tournament.

    Returns:
        Tuple of (expected_value, course_fit, history_summary)
    """
    purse = tournament["purse"]
    tournament_type = tournament["type"]
    course_name = tournament["course"].lower()

    # Base expected value based on tournament type
    # Assume elite player has ~5% win rate at standard events
    base_win_prob = 0.05
    if tournament_type == "Major":
        base_win_prob = 0.08  # Stronger fields but they're elite
    elif tournament_type == "Signature":
        base_win_prob = 0.06

    # Check course history
    course_fit = 0.0
    history_summary = "No history"

    for hist_course, hist_data in course_history.items():
        if any(word in hist_course for word in course_name.split()[:2]):
            tournaments = hist_data.get("tournaments", [])
            if tournaments:
                # Calculate average finish
                finishes = []
                for t in tournaments[:5]:
                    pos = t.get("position", "")
                    try:
                        if pos.startswith("T"):
                            finishes.append(int(pos[1:]))
                        elif pos.isdigit():
                            finishes.append(int(pos))
                    except ValueError:
                        pass

                if finishes:
                    avg_finish = sum(finishes) / len(finishes)
                    # Course fit bonus based on avg finish
                    if avg_finish <= 5:
                        course_fit = 0.5
                    elif avg_finish <= 10:
                        course_fit = 0.3
                    elif avg_finish <= 20:
                        course_fit = 0.1

                    # Check for wins
                    wins = sum(1 for f in finishes if f == 1)
                    if wins > 0:
                        course_fit += 0.3
                        history_summary = f"WON HERE ({wins}x), avg finish: {avg_finish:.0f}"
                    else:
                        history_summary = f"Played {len(finishes)}x, avg finish: {avg_finish:.0f}"
                break

    # Adjust win probability based on course fit
    adjusted_win_prob = base_win_prob * (1 + course_fit)

    # Expected value (simplified: win_prob * winner_share)
    # Winner typically gets 18% of purse
    expected_value = adjusted_win_prob * (purse * 0.18)

    # Add expected value from top-10 finishes
    # Assume ~30% top-10 rate for elite players
    top10_prob = 0.30 * (1 + course_fit * 0.5)
    avg_top10_payout = purse * 0.03  # ~3% of purse average for top-10
    expected_value += top10_prob * avg_top10_payout

    return expected_value, course_fit, history_summary


def recommend_tournaments_for_player(
    player_name: str,
    num_uses: int = 3,
    qualifications: Dict[str, PlayerQualification] = None
) -> List[TournamentRecommendation]:
    """
    Recommend the best tournaments to use a player.

    Args:
        player_name: Player name
        num_uses: Number of uses to optimize (default 3)
        qualifications: Pre-loaded qualifications (optional)

    Returns:
        List of TournamentRecommendation objects, sorted by value
    """
    if qualifications is None:
        qualifications = load_player_qualifications()

    # Get eligible tournaments
    eligible = get_player_tournament_schedule(player_name, qualifications)

    # Load course history
    course_history = load_course_history(player_name)

    # Load predictions
    predictions = load_predictions()

    # Load historical tournament ROI data
    tournament_roi = {}
    if TOURNAMENT_ROI_AVAILABLE and load_tournament_roi_data:
        try:
            tournament_roi = load_tournament_roi_data()
        except Exception:
            pass

    # Calculate value for each tournament
    recommendations = []
    for tournament in eligible:
        ev, course_fit, history = calculate_tournament_value(
            player_name, tournament, course_history, predictions
        )

        # Apply historical ROI boost/penalty
        historical_roi_tier = None
        historical_roi_bonus = ""
        if tournament_roi:
            # Look up this tournament in historical data
            tourn_lower = tournament["name"].lower()
            matched_roi = None
            for key, roi in tournament_roi.items():
                if tourn_lower in key or key in tourn_lower:
                    matched_roi = roi
                    historical_roi_tier = roi.roi_tier
                    break

            if matched_roi:
                # Boost EV based on historical performance
                if matched_roi.roi_tier == "elite":
                    ev *= 1.15  # 15% boost for historically elite tournaments
                    historical_roi_bonus = "📈 Historically ELITE for fantasy"
                elif matched_roi.roi_tier == "good":
                    ev *= 1.08  # 8% boost
                    historical_roi_bonus = "📈 Historically GOOD for fantasy"
                elif matched_roi.roi_tier == "below_avg":
                    ev *= 0.92  # 8% penalty
                    historical_roi_bonus = "⚠️ Historically below avg for fantasy"

        # Rating based on EV and tournament importance
        rating = 3  # Default
        if tournament["type"] == "Major":
            rating = 5 if ev > 200000 else 4
        elif tournament["type"] == "Signature":
            rating = 4 if ev > 150000 else 3
        elif ev > 100000:
            rating = 3
        else:
            rating = 2

        # Boost rating for course fit
        if "WON" in history:
            rating = min(5, rating + 1)

        # Boost rating for elite historical ROI
        if historical_roi_tier == "elite":
            rating = min(5, rating + 1)

        # Build reasoning
        reasons = []
        if tournament["type"] == "Major":
            reasons.append(f"MAJOR - ${tournament['purse']/1000000:.0f}M purse")
        elif tournament["type"] == "Signature":
            reasons.append(f"Signature Event - ${tournament['purse']/1000000:.0f}M purse")
        else:
            reasons.append(f"${tournament['purse']/1000000:.1f}M purse")

        if course_fit > 0.3:
            reasons.append("Strong course fit")
        if "WON" in history:
            reasons.append("Previous winner!")
        if historical_roi_bonus:
            reasons.append(historical_roi_bonus)

        recommendations.append(TournamentRecommendation(
            tournament_name=tournament["name"],
            tournament_date=tournament["date"],
            purse=tournament["purse"],
            tournament_type=tournament["type"],
            expected_value=ev,
            course_fit=course_fit,
            course_history=history,
            rating=rating,
            reasoning="; ".join(reasons)
        ))

    # Sort by expected value
    recommendations.sort(key=lambda x: x.expected_value, reverse=True)

    return recommendations


def print_season_plan(player_name: str, recommendations: List[TournamentRecommendation], num_uses: int = 3):
    """Print formatted season plan for a player."""
    print()
    print("=" * 70)
    print(f"  SEASON USAGE PLAN: {player_name.upper()}")
    print("=" * 70)

    # Top recommendations
    print(f"\n  TOP {num_uses} RECOMMENDED TOURNAMENTS TO USE:")
    print("-" * 70)

    for i, rec in enumerate(recommendations[:num_uses], 1):
        stars = "★" * rec.rating + "☆" * (5 - rec.rating)
        print(f"\n  {i}. {rec.tournament_name} ({rec.tournament_date})")
        print(f"     Type: {rec.tournament_type} | Purse: ${rec.purse:,}")
        print(f"     Expected Value: ${rec.expected_value:,.0f}")
        print(f"     Course History: {rec.course_history}")
        print(f"     Rating: {stars}")
        print(f"     Reasoning: {rec.reasoning}")

    # Also show next best options
    if len(recommendations) > num_uses:
        print(f"\n  BACKUP OPTIONS (if skipping above):")
        print("-" * 70)
        for rec in recommendations[num_uses:num_uses+3]:
            print(f"  • {rec.tournament_name} - ${rec.expected_value:,.0f} EV ({rec.tournament_type})")

    # Show tournaments to skip
    if len(recommendations) > num_uses + 3:
        print(f"\n  TOURNAMENTS TO SKIP (save uses for above):")
        print("-" * 70)
        skip_list = recommendations[num_uses+3:]
        for rec in skip_list[:5]:
            print(f"  • {rec.tournament_name} - ${rec.expected_value:,.0f} EV")

    print()


def print_calendar():
    """Print full tournament calendar."""
    print()
    print("=" * 80)
    print("  2026 PGA TOUR CALENDAR")
    print("=" * 80)

    current_month = ""
    for t in TOURNAMENT_CALENDAR_2026:
        date = datetime.strptime(t["date"], "%Y-%m-%d")
        month = date.strftime("%B")

        if month != current_month:
            print(f"\n  {month.upper()}")
            print("-" * 80)
            current_month = month

        type_badge = ""
        if t["type"] == "Major":
            type_badge = "[MAJOR]"
        elif t["type"] == "Signature":
            type_badge = "[SIG]"
        elif t["type"] == "Playoffs":
            type_badge = "[PLAYOFF]"

        purse_str = f"${t['purse']/1000000:.0f}M" if t['purse'] >= 1000000 else f"${t['purse']:,}"

        print(f"  {date.strftime('%b %d')}  {t['name'][:35]:<35} {purse_str:>8}  {type_badge}")

    print()


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Season Usage Planner - Optimize your 3 uses per player",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--player", type=str, help="Get season plan for a specific player")
    parser.add_argument("--calendar", action="store_true", help="Show full tournament calendar")
    parser.add_argument("--uses", type=int, default=3, help="Number of uses per player (default: 3)")
    parser.add_argument("--list-qualified", type=str, help="List tournaments a player is qualified for")

    args = parser.parse_args()

    if args.calendar:
        print_calendar()
        return 0

    # Load qualifications
    print("  Loading player qualifications...")
    qualifications = load_player_qualifications()
    print(f"  Loaded qualifications for {len(qualifications)} players")

    if args.list_qualified:
        player_qual = qualifications.get(args.list_qualified.lower())
        if player_qual:
            print(f"\n  {player_qual.name} is qualified for:")
            print(f"  - Signature Events: {'Yes' if player_qual.can_play_signatures() else 'No'}")
            print(f"  - Majors: {', '.join(player_qual.can_play_majors()) or 'None'}")
            eligible = get_player_tournament_schedule(args.list_qualified, qualifications)
            print(f"\n  Can play {len(eligible)} tournaments in 2026:")
            for t in eligible[:10]:
                print(f"    • {t['name']} ({t['type']}) - ${t['purse']:,}")
        else:
            print(f"  Player '{args.list_qualified}' not found in qualification data")
        return 0

    if args.player:
        recommendations = recommend_tournaments_for_player(
            args.player,
            num_uses=args.uses,
            qualifications=qualifications
        )

        if not recommendations:
            print(f"  No tournaments found for {args.player}")
            print("  (Player may not be in qualification database or has no eligible events)")
            return 1

        print_season_plan(args.player, recommendations, num_uses=args.uses)
        return 0

    # Default: show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    exit(main())
