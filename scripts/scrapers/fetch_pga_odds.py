#!/usr/bin/env python3
"""
PGA Tour Odds Scraper
=====================

Fetches betting odds directly from PGA Tour's GraphQL API.

This is more reliable than third-party APIs because:
1. It's the official source shown on pgatour.com
2. No API key needed
3. Always has data for current/upcoming PGA Tour events

HOW BETTING ODDS WORK:
---------------------
American odds format:
  +500  = Underdog. Bet $100 to win $500 profit. Implied prob = 100/(500+100) = 16.7%
  +2000 = Long shot. Bet $100 to win $2000. Implied prob = 100/(2000+100) = 4.8%
  +350  = Favorite (in golf context). Bet $100 to win $350. Implied prob = 22.2%

Note: Golf rarely has negative odds since even favorites are long shots to win.

Usage:
    # Fetch odds for a specific tournament
    python3 scripts/scrapers/fetch_pga_odds.py --tournament-id R2026002

    # Fetch odds for current/upcoming tournament
    python scripts/scrapers/fetch_pga_odds.py --current

Output columns:
    - player_id: PGA Tour player ID
    - player_name: Player name
    - odds_to_win: American odds string (e.g., "+500")
    - odds_numeric: Numeric odds value (e.g., 500)
    - implied_prob: Probability implied by odds
    - fair_prob: Probability with vig removed (sums to 100%)
    - odds_swing: Movement indicator (UP, DOWN, CONSTANT)
"""

import argparse
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# ============================================================================
# Configuration
# ============================================================================

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

# Output directory
OUTPUT_DIR = Path("data/odds")

# GraphQL query for tournament odds
TOURNAMENT_ODDS_QUERY = """
query TournamentOddsToWin($tournamentId: ID!) {
  tournamentOddsToWin(tournamentId: $tournamentId) {
    tournamentId
    tournamentName
    players {
      playerId
      oddsToWin
      oddsSwing
      oddsSort
    }
  }
}
"""

# Query to get player names (since odds query only returns IDs)
PLAYER_INFO_QUERY = """
query LeaderboardV3($id: ID!) {
  leaderboardV3(id: $id) {
    players {
      ... on PlayerRowV3 {
        player {
          id
          firstName
          lastName
          displayName
        }
      }
    }
  }
}
"""


# ============================================================================
# Odds Conversion Functions
# ============================================================================

def parse_american_odds(odds_str: str) -> int:
    """
    Parse American odds string to numeric value.

    Args:
        odds_str: Odds string like "+500" or "-150"

    Returns:
        Numeric odds value (500 for "+500", -150 for "-150")
    """
    if not odds_str:
        return None
    try:
        # Remove "+" prefix if present
        return int(odds_str.replace("+", ""))
    except (ValueError, TypeError):
        return None


def american_to_implied_prob(american_odds: int) -> float:
    """
    Convert American odds to implied probability.

    Formula:
    - Positive: prob = 100 / (odds + 100)
    - Negative: prob = |odds| / (|odds| + 100)

    Examples:
        +500  -> 100 / 600 = 16.67%
        +2000 -> 100 / 2100 = 4.76%
        -150  -> 150 / 250 = 60%

    Args:
        american_odds: Numeric odds (e.g., 500, -150)

    Returns:
        Implied probability (0.0 to 1.0)
    """
    if american_odds is None:
        return None

    if american_odds >= 0:
        # Underdog (or slight favorite in golf context)
        return 100 / (american_odds + 100)
    else:
        # Heavy favorite
        return abs(american_odds) / (abs(american_odds) + 100)


def remove_vig(probabilities: list) -> list:
    """
    Remove the vigorish (vig) from implied probabilities.

    Sportsbooks build in a margin (vig) so probabilities sum to >100%.
    This normalizes them to sum to 100% for "fair" probabilities.

    Args:
        probabilities: List of implied probabilities (may sum to >1.0)

    Returns:
        List of fair probabilities (sums to 1.0)
    """
    # Filter out None values for calculation
    valid_probs = [p for p in probabilities if p is not None]
    total = sum(valid_probs)

    if total == 0:
        return probabilities

    # Normalize
    return [p / total if p is not None else None for p in probabilities]


# ============================================================================
# API Functions
# ============================================================================

def fetch_tournament_odds(tournament_id: str) -> pd.DataFrame:
    """
    Fetch betting odds for a tournament.

    Args:
        tournament_id: PGA Tour tournament ID (e.g., "R2026002")

    Returns:
        DataFrame with odds for all players
    """
    print(f"  Fetching odds for tournament {tournament_id}...")

    payload = {
        "operationName": "TournamentOddsToWin",
        "variables": {"tournamentId": tournament_id},
        "query": TOURNAMENT_ODDS_QUERY,
    }

    try:
        resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=30)

        if resp.status_code != 200:
            print(f"    Error: HTTP {resp.status_code}")
            return pd.DataFrame()

        data = resp.json()

        if data.get("errors"):
            print(f"    GraphQL errors: {data['errors']}")
            return pd.DataFrame()

        odds_data = data.get("data", {}).get("tournamentOddsToWin")
        if not odds_data:
            print(f"    No odds data found")
            return pd.DataFrame()

        tournament_name = odds_data.get("tournamentName", tournament_id)
        players = odds_data.get("players", [])

        if not players:
            print(f"    No player odds found")
            return pd.DataFrame()

        # Build DataFrame
        records = []
        for p in players:
            odds_str = p.get("oddsToWin", "")
            odds_numeric = parse_american_odds(odds_str)
            implied_prob = american_to_implied_prob(odds_numeric)

            records.append({
                "tournament_id": tournament_id,
                "tournament_name": tournament_name,
                "player_id": int(p.get("playerId", 0)),
                "odds_to_win": odds_str,
                "odds_numeric": odds_numeric,
                "implied_prob": implied_prob,
                "odds_swing": p.get("oddsSwing", ""),
                "odds_sort": p.get("oddsSort", 0),
            })

        df = pd.DataFrame(records)

        # Calculate fair probabilities (remove vig)
        df["fair_prob"] = remove_vig(df["implied_prob"].tolist())

        print(f"    Found odds for {len(df)} players")

        return df

    except requests.RequestException as e:
        print(f"    Request error: {e}")
        return pd.DataFrame()


def fetch_player_names(tournament_id: str) -> dict:
    """
    Fetch player names from the leaderboard.

    Args:
        tournament_id: PGA Tour tournament ID

    Returns:
        Dict mapping player_id to player_name
    """
    print(f"  Fetching player names...")

    payload = {
        "operationName": "LeaderboardV3",
        "variables": {"id": tournament_id},
        "query": PLAYER_INFO_QUERY,
    }

    try:
        resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=30)

        if resp.status_code != 200:
            return {}

        data = resp.json()
        players = data.get("data", {}).get("leaderboardV3", {}).get("players", [])

        name_map = {}
        for p in players:
            player_info = p.get("player", {})
            player_id = int(player_info.get("id", 0))
            display_name = player_info.get("displayName", "")
            if player_id and display_name:
                name_map[player_id] = display_name

        print(f"    Found {len(name_map)} player names")
        return name_map

    except requests.RequestException:
        return {}


def fetch_and_merge_odds(tournament_id: str) -> pd.DataFrame:
    """
    Fetch odds and merge with player names.

    Args:
        tournament_id: PGA Tour tournament ID

    Returns:
        DataFrame with odds and player names
    """
    # Fetch odds
    odds_df = fetch_tournament_odds(tournament_id)

    if len(odds_df) == 0:
        return pd.DataFrame()

    # Fetch player names
    name_map = fetch_player_names(tournament_id)

    # Merge names
    odds_df["player_name"] = odds_df["player_id"].map(name_map)

    # Fill missing names with "Unknown (ID)"
    odds_df["player_name"] = odds_df.apply(
        lambda row: row["player_name"] if pd.notna(row["player_name"])
        else f"Unknown ({row['player_id']})",
        axis=1
    )

    # Sort by odds (favorites first)
    odds_df = odds_df.sort_values("odds_sort")

    # Add rank
    odds_df["odds_rank"] = range(1, len(odds_df) + 1)

    return odds_df


# ============================================================================
# Main Function
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fetch golf betting odds from PGA Tour",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Fetch odds for American Express 2026
    python scripts/scrapers/fetch_pga_odds.py --tournament-id R2026002

    # Fetch and save to specific file
    python scripts/scrapers/fetch_pga_odds.py --tournament-id R2026002 --output data/odds/amex_2026.csv

Tournament IDs:
    Format: R{year}{number} (e.g., R2026002 for American Express 2026)
    Find IDs on pgatour.com tournament URLs
        """
    )

    parser.add_argument("--tournament-id", required=True,
                       help="PGA Tour tournament ID (e.g., R2026002)")
    parser.add_argument("--output", type=str, default=None,
                       help="Output CSV path")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  PGA TOUR ODDS SCRAPER")
    print("=" * 60)

    # Fetch odds with player names
    df = fetch_and_merge_odds(args.tournament_id)

    if len(df) == 0:
        print("\n  No odds data found!")
        return 1

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"pga_odds_{args.tournament_id}.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save
    df.to_csv(output_path, index=False)

    # Print summary
    print("\n" + "=" * 60)
    print("  ODDS SUMMARY")
    print("=" * 60)

    print(f"\n  Tournament: {df['tournament_name'].iloc[0]}")
    print(f"  Players: {len(df)}")

    # Total implied probability (shows vig)
    total_implied = df["implied_prob"].sum() * 100
    print(f"  Total implied prob: {total_implied:.1f}% (vig = {total_implied - 100:.1f}%)")

    print(f"\n  Top 15 Favorites:")
    print("-" * 60)

    top15 = df.head(15)
    for _, row in top15.iterrows():
        name = row["player_name"][:22].ljust(22)
        odds = row["odds_to_win"]
        prob = row["fair_prob"] * 100 if row["fair_prob"] else 0
        swing = row["odds_swing"]
        swing_icon = "↑" if swing == "UP" else "↓" if swing == "DOWN" else "→"
        print(f"    {name}  {odds:>8}  ({prob:5.2f}%)  {swing_icon}")

    print(f"\n  Saved to: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())