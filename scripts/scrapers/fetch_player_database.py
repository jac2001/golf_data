#!/usr/bin/env python3
"""
PGA Tour Player Database Scraper
=================================
Fetches a comprehensive list of all PGA Tour players with their IDs,
names, and current world rankings.

This master list is used for:
1. Player ID matching when scraping fields
2. Name normalization across different sources
3. Quick lookup of world rankings
4. Filtering active vs inactive players

Usage:
    python scripts/scrapers/fetch_player_database.py
    python scripts/scrapers/fetch_player_database.py --output data/players/pga_players_2026.csv

Output columns:
    - player_id: PGA Tour player ID
    - player_name: Full name
    - first_name: First name
    - last_name: Last name
    - world_rank: Current OWGR ranking (if available)
    - country: Country of origin
    - is_active: Whether player is currently active on tour
    - fetched_date: When the data was fetched
"""

import argparse
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

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

# Query to get all players from a stat leaderboard (covers most active players)
STAT_DETAILS_QUERY = """
query StatDetails(
  $tourCode: TourCode!
  $statId: String!
  $year: Int
) {
  statDetails(
    tourCode: $tourCode
    statId: $statId
    year: $year
  ) {
    tourCode
    year
    statId
    statTitle
    rows {
      ... on StatDetailsPlayer {
        playerId
        playerName
        rank
        country
        stats {
          statName
          statValue
        }
      }
    }
  }
}
"""

# Alternative: Player search query (can search by name)
PLAYER_SEARCH_QUERY = """
query PlayerSearch($searchTerm: String!) {
  playerSearch(searchTerm: $searchTerm) {
    players {
      playerId
      displayName
      firstName
      lastName
      country
      countryFlag
      isActive
    }
  }
}
"""

# ============================================================================
# Functions
# ============================================================================

def fetch_players_from_stat(stat_id: str, year: int = None) -> pd.DataFrame:
    """
    Fetch players from a stat leaderboard.

    Different stats cover different player pools:
    - 186: World Ranking (most comprehensive)
    - 120: Scoring Average
    - 02675: Strokes Gained Total

    Args:
        stat_id: PGA Tour stat ID
        year: Year to fetch

    Returns:
        DataFrame with player info
    """
    if year is None:
        year = datetime.now().year

    payload = {
        "operationName": "StatDetails",
        "variables": {
            "tourCode": "R",
            "statId": stat_id,
            "year": year,
        },
        "query": STAT_DETAILS_QUERY,
    }

    try:
        resp = requests.post(
            GRAPHQL_URL,
            headers=DEFAULT_HEADERS,
            json=payload,
            timeout=30,
        )

        if resp.status_code != 200:
            print(f"  Warning: HTTP {resp.status_code} for stat {stat_id}")
            return pd.DataFrame()

        data = resp.json()

        if data.get("errors"):
            return pd.DataFrame()

        stat_details = data.get('data', {}).get('statDetails')
        if not stat_details:
            return pd.DataFrame()

        rows = stat_details.get('rows', [])

        records = []
        for r in rows:
            player_id = r.get("playerId")
            player_name = r.get("playerName", "")

            # Split name into first/last
            name_parts = player_name.split()
            first_name = name_parts[0] if name_parts else ""
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

            records.append({
                "player_id": player_id,
                "player_name": player_name,
                "first_name": first_name,
                "last_name": last_name,
                "country": r.get("country", ""),
                "world_rank": r.get("rank") if stat_id == "186" else None,
            })

        return pd.DataFrame(records)

    except Exception as e:
        print(f"  Error fetching stat {stat_id}: {e}")
        return pd.DataFrame()


def fetch_player_database(year: int = None) -> pd.DataFrame:
    """
    Fetch comprehensive player database from multiple sources.

    Combines:
    1. World Rankings stat (covers top ~500 players)
    2. Scoring Average stat (covers all who played enough rounds)
    3. SG Total stat (covers all with strokes gained data)

    Args:
        year: Year to fetch (defaults to current)

    Returns:
        DataFrame with all unique players
    """
    if year is None:
        year = datetime.now().year

    print(f"Fetching PGA Tour player database for {year}...")

    # Fetch from multiple stats to get comprehensive coverage
    stats_to_fetch = [
        ("186", "World Ranking"),
        ("120", "Scoring Average"),
        ("02675", "Strokes Gained Total"),
    ]

    all_players = []

    for stat_id, stat_name in stats_to_fetch:
        print(f"  Fetching {stat_name} (stat {stat_id})...")
        df = fetch_players_from_stat(stat_id, year)
        if len(df) > 0:
            print(f"    Found {len(df)} players")
            all_players.append(df)

    if not all_players:
        print("No players found!")
        return pd.DataFrame()

    # Combine all sources
    combined = pd.concat(all_players, ignore_index=True)

    # Remove duplicates, keeping first occurrence (which has world rank if available)
    combined = combined.drop_duplicates(subset=['player_id'], keep='first')

    # Sort by world rank (nulls at end)
    combined['world_rank'] = pd.to_numeric(combined['world_rank'], errors='coerce')
    combined = combined.sort_values('world_rank', na_position='last')

    # Add metadata
    combined['is_active'] = True
    combined['fetched_date'] = datetime.now().strftime('%Y-%m-%d')

    print(f"\nTotal unique players: {len(combined)}")
    print(f"  With world ranking: {combined['world_rank'].notna().sum()}")

    return combined


def create_name_lookup(players_df: pd.DataFrame) -> Dict[str, str]:
    """
    Create a name -> player_id lookup dictionary.

    Handles common name variations:
    - "Scottie Scheffler" -> 46046
    - "SCHEFFLER, SCOTTIE" -> 46046
    - "S. Scheffler" -> 46046

    Returns:
        Dict mapping normalized names to player_id
    """
    import re

    lookup = {}

    for _, row in players_df.iterrows():
        player_id = row['player_id']
        player_name = row['player_name']
        first_name = row.get('first_name', '')
        last_name = row.get('last_name', '')

        if not player_id or not player_name:
            continue

        # Normalize: uppercase, remove special chars
        def normalize(name):
            return re.sub(r'[^\w\s]', '', str(name).upper()).strip()

        # Add various name formats
        name_variations = [
            normalize(player_name),  # "SCOTTIE SCHEFFLER"
            normalize(f"{last_name}, {first_name}"),  # "SCHEFFLER, SCOTTIE"
            normalize(f"{first_name[0]}. {last_name}" if first_name else ""),  # "S. SCHEFFLER"
            normalize(f"{first_name[0]} {last_name}" if first_name else ""),  # "S SCHEFFLER"
        ]

        for var in name_variations:
            if var:
                lookup[var] = player_id

    return lookup


def match_names_to_ids(names: List[str], players_df: pd.DataFrame) -> pd.DataFrame:
    """
    Match a list of player names to their IDs.

    Args:
        names: List of player names to match
        players_df: Player database DataFrame

    Returns:
        DataFrame with player_id, player_name, matched (bool)
    """
    import re

    lookup = create_name_lookup(players_df)

    results = []
    for name in names:
        normalized = re.sub(r'[^\w\s]', '', str(name).upper()).strip()

        player_id = lookup.get(normalized)

        # Try fuzzy match if exact match fails
        if not player_id:
            # Try just last name
            parts = normalized.split()
            if parts:
                last_name = parts[-1]
                matches = [k for k in lookup.keys() if last_name in k]
                if len(matches) == 1:
                    player_id = lookup[matches[0]]

        results.append({
            'player_name': name,
            'player_id': player_id,
            'matched': player_id is not None,
        })

    return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description='Fetch PGA Tour player database')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                       help='Year to fetch (default: current year)')
    parser.add_argument('--output', type=str, default=None,
                       help='Output CSV path (default: data/players/pga_players_{year}.csv)')
    parser.add_argument('--match-names', type=str, default=None,
                       help='CSV file with names to match to IDs')

    args = parser.parse_args()

    # Fetch player database
    players_df = fetch_player_database(args.year)

    if len(players_df) == 0:
        print("No players fetched!")
        return

    # Default output path
    if args.output is None:
        output_dir = Path("data/players")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"pga_players_{args.year}.csv"
    else:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save
    players_df.to_csv(output_path, index=False)

    print(f"\n{'='*60}")
    print(f"PGA Tour Player Database")
    print(f"{'='*60}")
    print(f"  Total players: {len(players_df)}")
    print(f"  With world rank: {players_df['world_rank'].notna().sum()}")
    print(f"\n  Top 10 by world ranking:")
    for _, row in players_df.head(10).iterrows():
        rank = int(row['world_rank']) if pd.notna(row['world_rank']) else 'N/A'
        print(f"    {rank:>4}. {row['player_name']} ({row['player_id']})")
    print(f"\n  Saved to: {output_path}")

    # Match names if requested
    if args.match_names:
        print(f"\n  Matching names from {args.match_names}...")
        names_df = pd.read_csv(args.match_names)

        if 'player_name' in names_df.columns:
            names = names_df['player_name'].tolist()
        else:
            names = names_df.iloc[:, 0].tolist()

        matched_df = match_names_to_ids(names, players_df)

        match_rate = matched_df['matched'].mean() * 100
        print(f"    Match rate: {match_rate:.1f}%")

        # Save matched results
        match_output = output_path.parent / f"matched_{Path(args.match_names).name}"
        matched_df.to_csv(match_output, index=False)
        print(f"    Saved to: {match_output}")


if __name__ == '__main__':
    main()
