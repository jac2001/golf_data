"""
Player ROI Analytics Module

Analyzes historical fantasy pick results to calculate ROI metrics for each player.
Uses fantasy_results files from 2022-2025 to identify:
- Overperformers: Players who consistently beat expectations
- Underperformers: "Trap" players who look good but underdeliver
- Consistency: Boom/bust vs reliable floor players
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class PlayerROI:
    """ROI metrics for a single player."""
    player_name: str
    times_picked: int
    total_earnings: float
    avg_earnings_per_pick: float
    median_earnings: float
    std_dev: float
    max_earnings: float
    min_earnings: float
    zero_earnings_pct: float  # % of picks that earned $0
    big_week_pct: float  # % of picks earning > $200k
    consistency_score: float  # Higher = more consistent
    roi_tier: str  # "elite", "good", "average", "below_avg", "avoid"

    def to_dict(self) -> Dict:
        return {
            "player_name": self.player_name,
            "times_picked": self.times_picked,
            "total_earnings": self.total_earnings,
            "avg_earnings_per_pick": self.avg_earnings_per_pick,
            "median_earnings": self.median_earnings,
            "std_dev": self.std_dev,
            "max_earnings": self.max_earnings,
            "min_earnings": self.min_earnings,
            "zero_earnings_pct": self.zero_earnings_pct,
            "big_week_pct": self.big_week_pct,
            "consistency_score": self.consistency_score,
            "roi_tier": self.roi_tier,
        }


def normalize_player_name(name: str) -> str:
    """Normalize player names for matching across files."""
    if not name or pd.isna(name):
        return ""

    name = str(name).strip()

    # Handle "Last, First" format
    if "," in name:
        parts = name.split(",")
        if len(parts) == 2:
            name = f"{parts[1].strip()} {parts[0].strip()}"

    # Remove asterisks and other markers
    name = re.sub(r'\*+$', '', name)

    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    # Convert to lowercase
    name = name.lower()

    # Normalize special characters to ASCII equivalents
    import unicodedata
    # Decompose and remove diacritics
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))

    return name


def parse_earnings(value) -> float:
    """Parse earnings value, handling various formats."""
    if pd.isna(value) or value == "" or value == "$0":
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    # Remove $ and commas
    cleaned = str(value).replace("$", "").replace(",", "").strip()

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def load_fantasy_results(data_dir: Path = None) -> pd.DataFrame:
    """
    Load all fantasy results files and combine into a single DataFrame.

    Returns DataFrame with columns:
    - year, week, tournament, player_name, earnings, starter_position
    """
    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent / "data" / "historical"

    # Find all fantasy results files (handle different naming conventions)
    patterns = ["fantasy_results_*.csv", "Fantasy_Results_*.csv", "Fanatasy_Results_*.csv"]
    files = []
    for pattern in patterns:
        files.extend(data_dir.glob(pattern))

    if not files:
        print(f"No fantasy results files found in {data_dir}")
        return pd.DataFrame()

    all_picks = []

    for file in sorted(files):
        try:
            df = pd.read_csv(file)

            # Normalize column names (handle slight variations)
            df.columns = [c.strip() for c in df.columns]

            # Extract year from filename or column
            if "year" in [c.lower() for c in df.columns]:
                year_col = [c for c in df.columns if c.lower() == "year"][0]
            elif "Year" in df.columns:
                year_col = "Year"
            else:
                # Try to extract from filename
                match = re.search(r'(\d{4})', file.name)
                year = int(match.group(1)) if match else 2022
                df["year"] = year
                year_col = "year"

            # Process each row (each tournament week)
            for _, row in df.iterrows():
                week = row.get("Week", 0)
                tournament = row.get("Tournament", "")
                year = row.get(year_col, row.get("year", 2022))

                # Extract the 3 starters and their earnings
                # Column pattern: "Starter #1", "Earnings", "Starter #2", "Earnings", ...
                cols = list(df.columns)

                for i in range(1, 4):
                    starter_col = f"Starter #{i}"

                    if starter_col in cols:
                        idx = cols.index(starter_col)
                        player_name = row[starter_col]

                        # Earnings is typically the next column
                        if idx + 1 < len(cols):
                            earnings_col = cols[idx + 1]
                            earnings = parse_earnings(row[earnings_col])
                        else:
                            earnings = 0.0

                        if player_name and str(player_name).upper() != "VACANT":
                            all_picks.append({
                                "year": int(year),
                                "week": int(week) if pd.notna(week) else 0,
                                "tournament": tournament,
                                "player_name": player_name,
                                "player_name_normalized": normalize_player_name(player_name),
                                "earnings": earnings,
                                "starter_position": i,
                            })

        except Exception as e:
            print(f"Error loading {file}: {e}")
            continue

    if not all_picks:
        return pd.DataFrame()

    return pd.DataFrame(all_picks)


def calculate_player_roi(picks_df: pd.DataFrame, min_picks: int = 3) -> Dict[str, PlayerROI]:
    """
    Calculate ROI metrics for each player.

    Args:
        picks_df: DataFrame from load_fantasy_results()
        min_picks: Minimum number of picks to include player

    Returns:
        Dict mapping normalized player name to PlayerROI
    """
    if picks_df.empty:
        return {}

    # Group by normalized player name
    player_stats = {}

    for name, group in picks_df.groupby("player_name_normalized"):
        if len(group) < min_picks:
            continue

        earnings = group["earnings"].values

        # Calculate metrics
        times_picked = len(group)
        total_earnings = earnings.sum()
        avg_earnings = earnings.mean()
        median_earnings = np.median(earnings)
        std_dev = earnings.std() if len(earnings) > 1 else 0
        max_earnings = earnings.max()
        min_earnings = earnings.min()

        # Calculate percentages
        zero_count = (earnings == 0).sum()
        zero_pct = (zero_count / times_picked) * 100

        big_week_count = (earnings >= 200000).sum()
        big_week_pct = (big_week_count / times_picked) * 100

        # Consistency score: higher median relative to mean = more consistent
        # Also penalize high zero-earnings percentage
        if avg_earnings > 0:
            consistency_ratio = median_earnings / avg_earnings
        else:
            consistency_ratio = 0

        # Penalize for zero earnings and reward for big weeks
        consistency_score = (
            consistency_ratio * 40 +  # Median/mean ratio (max ~40)
            (100 - zero_pct) * 0.3 +   # Reward for non-zero (max 30)
            big_week_pct * 0.3         # Reward for big weeks (max ~30)
        )

        # Determine ROI tier based on average earnings and consistency
        if avg_earnings >= 400000 and consistency_score >= 50:
            roi_tier = "elite"
        elif avg_earnings >= 250000 or (avg_earnings >= 150000 and consistency_score >= 45):
            roi_tier = "good"
        elif avg_earnings >= 100000 or (avg_earnings >= 75000 and consistency_score >= 40):
            roi_tier = "average"
        elif avg_earnings >= 50000:
            roi_tier = "below_avg"
        else:
            roi_tier = "avoid"

        # Get display name (most common original name)
        display_name = group["player_name"].mode().iloc[0] if len(group) > 0 else name

        player_stats[name] = PlayerROI(
            player_name=display_name,
            times_picked=times_picked,
            total_earnings=total_earnings,
            avg_earnings_per_pick=avg_earnings,
            median_earnings=median_earnings,
            std_dev=std_dev,
            max_earnings=max_earnings,
            min_earnings=min_earnings,
            zero_earnings_pct=zero_pct,
            big_week_pct=big_week_pct,
            consistency_score=consistency_score,
            roi_tier=roi_tier,
        )

    return player_stats


def get_player_roi_summary(player_name: str, roi_data: Dict[str, PlayerROI]) -> Optional[str]:
    """
    Get a human-readable ROI summary for a player.

    Args:
        player_name: Player name to look up
        roi_data: Dict from calculate_player_roi()

    Returns:
        Summary string or None if player not found
    """
    normalized = normalize_player_name(player_name)

    if normalized not in roi_data:
        # Try partial/last-name match
        # Extract last name from normalized (e.g., "ludvig aberg" -> "aberg")
        last_name = normalized.split()[-1] if normalized else ""

        matches = []
        for k in roi_data.keys():
            # Full name contains the key or vice versa
            if normalized in k or k in normalized:
                matches.append(k)
            # Last name match (e.g., "aberg" matches "ludvig aberg")
            elif last_name and (k == last_name or k.endswith(f" {last_name}")):
                matches.append(k)
            # Key is just a last name that matches
            elif " " not in k and k == last_name:
                matches.append(k)

        if matches:
            normalized = matches[0]
        else:
            return None

    roi = roi_data[normalized]

    # Build summary
    tier_emoji = {
        "elite": "🌟",
        "good": "✅",
        "average": "➡️",
        "below_avg": "⚠️",
        "avoid": "❌",
    }

    tier_desc = {
        "elite": "Elite performer - consistently delivers",
        "good": "Solid pick - good ROI history",
        "average": "Average performer - acceptable",
        "below_avg": "Below average - use cautiously",
        "avoid": "Poor history - consider alternatives",
    }

    emoji = tier_emoji.get(roi.roi_tier, "")
    desc = tier_desc.get(roi.roi_tier, "")

    lines = [
        f"{emoji} **Historical ROI: {roi.roi_tier.upper()}** - {desc}",
        f"- Picked {roi.times_picked}x over 4 seasons",
        f"- Avg earnings: ${roi.avg_earnings_per_pick:,.0f}/pick",
        f"- Total earnings: ${roi.total_earnings:,.0f}",
        f"- Best week: ${roi.max_earnings:,.0f}",
        f"- Zero earnings: {roi.zero_earnings_pct:.0f}% of picks",
        f"- Big weeks (>$200k): {roi.big_week_pct:.0f}% of picks",
    ]

    # Add boom/bust assessment
    if roi.std_dev > roi.avg_earnings_per_pick * 1.5:
        lines.append("- **BOOM/BUST profile** - high variance player")
    elif roi.std_dev < roi.avg_earnings_per_pick * 0.7:
        lines.append("- **Consistent** - reliable floor")

    return "\n".join(lines)


def get_top_roi_players(roi_data: Dict[str, PlayerROI],
                        tier: str = None,
                        limit: int = 10) -> List[PlayerROI]:
    """
    Get top players by ROI, optionally filtered by tier.
    """
    players = list(roi_data.values())

    if tier:
        players = [p for p in players if p.roi_tier == tier]

    # Sort by average earnings
    players.sort(key=lambda x: x.avg_earnings_per_pick, reverse=True)

    return players[:limit]


def get_boom_bust_players(roi_data: Dict[str, PlayerROI],
                          min_picks: int = 5) -> Tuple[List[PlayerROI], List[PlayerROI]]:
    """
    Identify boom/bust vs consistent players.

    Returns:
        (boom_bust_players, consistent_players)
    """
    boom_bust = []
    consistent = []

    for roi in roi_data.values():
        if roi.times_picked < min_picks:
            continue

        # Coefficient of variation (std/mean)
        if roi.avg_earnings_per_pick > 0:
            cv = roi.std_dev / roi.avg_earnings_per_pick
        else:
            cv = float('inf')

        if cv > 1.5:
            boom_bust.append(roi)
        elif cv < 0.8:
            consistent.append(roi)

    # Sort by avg earnings
    boom_bust.sort(key=lambda x: x.avg_earnings_per_pick, reverse=True)
    consistent.sort(key=lambda x: x.avg_earnings_per_pick, reverse=True)

    return boom_bust, consistent


# Global cache for ROI data
_roi_cache: Dict[str, PlayerROI] = {}
_picks_df_cache: pd.DataFrame = None


def load_roi_data(force_reload: bool = False) -> Dict[str, PlayerROI]:
    """Load and cache ROI data."""
    global _roi_cache, _picks_df_cache

    if not force_reload and _roi_cache:
        return _roi_cache

    picks_df = load_fantasy_results()
    if picks_df.empty:
        return {}

    _picks_df_cache = picks_df
    _roi_cache = calculate_player_roi(picks_df)

    return _roi_cache


def print_roi_report():
    """Print a summary ROI report."""
    roi_data = load_roi_data()

    if not roi_data:
        print("No ROI data available")
        return

    print("=" * 70)
    print("  PLAYER ROI REPORT (2022-2025)")
    print("=" * 70)

    # Count by tier
    tier_counts = {}
    for roi in roi_data.values():
        tier_counts[roi.roi_tier] = tier_counts.get(roi.roi_tier, 0) + 1

    print(f"\nPlayers analyzed: {len(roi_data)}")
    print(f"Tier breakdown: {tier_counts}")

    print("\n" + "-" * 70)
    print("TOP 10 BY AVERAGE EARNINGS:")
    print("-" * 70)

    top_players = get_top_roi_players(roi_data, limit=10)
    for i, p in enumerate(top_players, 1):
        print(f"{i:2}. {p.player_name:25} ${p.avg_earnings_per_pick:>12,.0f}/pick  "
              f"({p.times_picked}x picked, {p.roi_tier})")

    print("\n" + "-" * 70)
    print("BOOM/BUST PLAYERS (high variance):")
    print("-" * 70)

    boom_bust, consistent = get_boom_bust_players(roi_data)
    for p in boom_bust[:5]:
        print(f"  {p.player_name:25} ${p.avg_earnings_per_pick:>10,.0f} avg  "
              f"(zero {p.zero_earnings_pct:.0f}%, big {p.big_week_pct:.0f}%)")

    print("\n" + "-" * 70)
    print("CONSISTENT PERFORMERS (reliable floor):")
    print("-" * 70)

    for p in consistent[:5]:
        print(f"  {p.player_name:25} ${p.avg_earnings_per_pick:>10,.0f} avg  "
              f"(zero {p.zero_earnings_pct:.0f}%, big {p.big_week_pct:.0f}%)")


# ============================================================================
# Tournament ROI Analysis - Best Weeks to Use Picks
# ============================================================================

@dataclass
class TournamentROI:
    """ROI metrics for a tournament."""
    tournament_name: str
    times_played: int  # How many years we have data for
    total_earnings: float
    avg_earnings_per_week: float
    avg_earnings_per_pick: float  # Per individual pick (3 per week)
    best_week_earnings: float
    worst_week_earnings: float
    consistency_score: float
    tournament_type: str  # major, signature, playoff, standard
    roi_tier: str  # elite, good, average, below_avg

    def to_dict(self) -> Dict:
        return {
            "tournament_name": self.tournament_name,
            "times_played": self.times_played,
            "total_earnings": self.total_earnings,
            "avg_earnings_per_week": self.avg_earnings_per_week,
            "avg_earnings_per_pick": self.avg_earnings_per_pick,
            "best_week_earnings": self.best_week_earnings,
            "worst_week_earnings": self.worst_week_earnings,
            "consistency_score": self.consistency_score,
            "tournament_type": self.tournament_type,
            "roi_tier": self.roi_tier,
        }


def classify_tournament_type(name: str) -> str:
    """Classify tournament into type based on name."""
    name_lower = name.lower()

    # Majors
    if any(m in name_lower for m in ["masters", "pga championship", "u.s. open", "open championship", "the open"]):
        return "major"

    # Playoffs
    if any(p in name_lower for p in ["fedex", "tour championship", "bmw championship", "st. jude"]):
        return "playoff"

    # Signature Events (2024+)
    signature_events = [
        "sentry", "at&t pebble", "genesis invitational", "arnold palmer",
        "rbc heritage", "wells fargo", "memorial", "travelers",
        "players championship"
    ]
    if any(s in name_lower for s in signature_events):
        return "signature"

    return "standard"


def calculate_tournament_roi(picks_df: pd.DataFrame) -> Dict[str, TournamentROI]:
    """
    Calculate ROI metrics for each tournament.

    Args:
        picks_df: DataFrame from load_fantasy_results()

    Returns:
        Dict mapping tournament name to TournamentROI
    """
    if picks_df.empty:
        return {}

    # Normalize tournament names
    def normalize_tournament(name: str) -> str:
        name = str(name).strip()
        # Remove year suffixes
        name = re.sub(r'\s+\d{4}$', '', name)
        return name

    picks_df = picks_df.copy()
    picks_df["tournament_normalized"] = picks_df["tournament"].apply(normalize_tournament)

    tournament_stats = {}

    # Group by tournament and year to get weekly totals
    for (tournament, year), group in picks_df.groupby(["tournament_normalized", "year"]):
        if tournament not in tournament_stats:
            tournament_stats[tournament] = {
                "weeks": [],
                "all_picks": [],
            }

        week_total = group["earnings"].sum()
        tournament_stats[tournament]["weeks"].append(week_total)
        tournament_stats[tournament]["all_picks"].extend(group["earnings"].tolist())

    # Calculate metrics for each tournament
    results = {}
    for tournament, data in tournament_stats.items():
        weeks = data["weeks"]
        all_picks = data["all_picks"]

        if len(weeks) < 2:  # Need at least 2 years of data
            continue

        weeks_arr = np.array(weeks)
        picks_arr = np.array(all_picks)

        avg_week = weeks_arr.mean()
        avg_pick = picks_arr.mean() if len(picks_arr) > 0 else 0
        best_week = weeks_arr.max()
        worst_week = weeks_arr.min()

        # Consistency: ratio of worst to best (higher = more consistent)
        if best_week > 0:
            consistency = (worst_week / best_week) * 100
        else:
            consistency = 0

        # Classify tournament type
        tourn_type = classify_tournament_type(tournament)

        # Determine ROI tier based on average weekly earnings
        if avg_week >= 2000000:
            roi_tier = "elite"
        elif avg_week >= 1000000:
            roi_tier = "good"
        elif avg_week >= 500000:
            roi_tier = "average"
        else:
            roi_tier = "below_avg"

        results[tournament.lower()] = TournamentROI(
            tournament_name=tournament,
            times_played=len(weeks),
            total_earnings=sum(weeks),
            avg_earnings_per_week=avg_week,
            avg_earnings_per_pick=avg_pick,
            best_week_earnings=best_week,
            worst_week_earnings=worst_week,
            consistency_score=consistency,
            tournament_type=tourn_type,
            roi_tier=roi_tier,
        )

    return results


def get_best_tournaments(tournament_roi: Dict[str, TournamentROI],
                         tournament_type: str = None,
                         limit: int = 10) -> List[TournamentROI]:
    """
    Get best tournaments for fantasy picks.

    Args:
        tournament_roi: Dict from calculate_tournament_roi()
        tournament_type: Optional filter (major, signature, playoff, standard)
        limit: Max results to return

    Returns:
        List of TournamentROI sorted by avg weekly earnings
    """
    tournaments = list(tournament_roi.values())

    if tournament_type:
        tournaments = [t for t in tournaments if t.tournament_type == tournament_type]

    # Sort by average weekly earnings
    tournaments.sort(key=lambda x: x.avg_earnings_per_week, reverse=True)

    return tournaments[:limit]


def get_tournament_roi_summary(tournament_name: str,
                               tournament_roi: Dict[str, TournamentROI]) -> Optional[str]:
    """
    Get a human-readable ROI summary for a tournament.
    """
    normalized = tournament_name.lower().strip()

    # Try exact match first
    if normalized not in tournament_roi:
        # Try partial match
        matches = [k for k in tournament_roi.keys()
                   if normalized in k or k in normalized]
        if matches:
            normalized = matches[0]
        else:
            return None

    roi = tournament_roi[normalized]

    tier_emoji = {
        "elite": "🏆",
        "good": "✅",
        "average": "➡️",
        "below_avg": "⚠️",
    }

    emoji = tier_emoji.get(roi.roi_tier, "")
    type_label = roi.tournament_type.upper()

    lines = [
        f"{emoji} **Tournament ROI: {roi.roi_tier.upper()}** ({type_label})",
        f"- Historical data: {roi.times_played} years",
        f"- Avg earnings/week: ${roi.avg_earnings_per_week:,.0f}",
        f"- Best week: ${roi.best_week_earnings:,.0f}",
        f"- Worst week: ${roi.worst_week_earnings:,.0f}",
        f"- Consistency: {roi.consistency_score:.0f}%",
    ]

    return "\n".join(lines)


def get_optimal_pick_weeks(tournament_roi: Dict[str, TournamentROI],
                           num_weeks: int = 10) -> List[Tuple[str, TournamentROI]]:
    """
    Identify the optimal weeks to use picks based on historical ROI.

    Returns list of (tournament_name, TournamentROI) sorted by value.
    """
    # Weight factors for ranking
    # - Avg earnings is primary
    # - Bonus for majors/signature events
    # - Bonus for consistency

    def score_tournament(roi: TournamentROI) -> float:
        base_score = roi.avg_earnings_per_week

        # Type multiplier
        type_mult = {
            "major": 1.3,
            "playoff": 1.2,
            "signature": 1.15,
            "standard": 1.0,
        }
        base_score *= type_mult.get(roi.tournament_type, 1.0)

        # Consistency bonus (up to 10%)
        consistency_bonus = (roi.consistency_score / 100) * 0.1
        base_score *= (1 + consistency_bonus)

        return base_score

    scored = [(t.tournament_name, t, score_tournament(t))
              for t in tournament_roi.values()]

    scored.sort(key=lambda x: x[2], reverse=True)

    return [(name, roi) for name, roi, _ in scored[:num_weeks]]


# Global cache for tournament ROI
_tournament_roi_cache: Dict[str, TournamentROI] = {}


def load_tournament_roi_data(force_reload: bool = False) -> Dict[str, TournamentROI]:
    """Load and cache tournament ROI data."""
    global _tournament_roi_cache, _picks_df_cache

    if not force_reload and _tournament_roi_cache:
        return _tournament_roi_cache

    # Ensure picks data is loaded
    if _picks_df_cache is None:
        load_roi_data()

    if _picks_df_cache is not None and not _picks_df_cache.empty:
        _tournament_roi_cache = calculate_tournament_roi(_picks_df_cache)

    return _tournament_roi_cache


def print_tournament_roi_report():
    """Print tournament ROI summary."""
    tournament_roi = load_tournament_roi_data()

    if not tournament_roi:
        print("No tournament ROI data available")
        return

    print("=" * 70)
    print("  TOURNAMENT ROI REPORT (2022-2025)")
    print("=" * 70)

    print(f"\nTournaments analyzed: {len(tournament_roi)}")

    print("\n" + "-" * 70)
    print("TOP 10 TOURNAMENTS BY FANTASY VALUE:")
    print("-" * 70)

    optimal = get_optimal_pick_weeks(tournament_roi, 10)
    for i, (name, roi) in enumerate(optimal, 1):
        print(f"{i:2}. {name:35} ${roi.avg_earnings_per_week:>10,.0f}/week  "
              f"({roi.tournament_type}, {roi.times_played}yr)")

    print("\n" + "-" * 70)
    print("BY TOURNAMENT TYPE:")
    print("-" * 70)

    for ttype in ["major", "playoff", "signature", "standard"]:
        best = get_best_tournaments(tournament_roi, ttype, limit=3)
        if best:
            print(f"\n  {ttype.upper()}:")
            for t in best:
                print(f"    - {t.tournament_name}: ${t.avg_earnings_per_week:,.0f}/week")


if __name__ == "__main__":
    print_roi_report()
    print("\n\n")
    print_tournament_roi_report()
