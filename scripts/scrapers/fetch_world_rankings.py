#!/usr/bin/env python3
"""
World Rankings Scraper
======================

Fetches Official World Golf Rankings from PGA Tour's GraphQL API.
Stat ID 186 = World Ranking

Usage:
    python scripts/scrapers/fetch_world_rankings.py
    python scripts/scrapers/fetch_world_rankings.py --output data/rankings/owgr_2026.csv

Output columns:
    - player_id: PGA Tour player ID
    - player_name: Full name
    - world_rank: Current OWGR ranking
    - world_rank_points: OWGR points (if available)
    - fetched_date: When the data was fetched
"""

import argparse
import requests
import pandas as pd
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

# Stat ID for World Ranking
WORLD_RANK_STAT_ID = "186"

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
        stats {
          statName
          statValue
        }
      }
    }
  }
}
"""

# ============================================================================
# Functions
# ============================================================================

def fetch_world_rankings(year: int = None) -> pd.DataFrame:
    """
    Fetch current world rankings from PGA Tour API.

    Args:
        year: Optional year filter (defaults to current year)

    Returns:
        DataFrame with player_id, player_name, world_rank, world_rank_points
    """
    if year is None:
        year = datetime.now().year

    print(f"Fetching world rankings for {year}...")

    payload = {
        "operationName": "StatDetails",
        "variables": {
            "tourCode": "R",
            "statId": WORLD_RANK_STAT_ID,
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
            print(f"Error: HTTP {resp.status_code}")
            return pd.DataFrame()

        data = resp.json()

        if data.get("errors"):
            print(f"GraphQL errors: {data['errors']}")
            return pd.DataFrame()

        stat_details = data.get('data', {}).get('statDetails')
        if not stat_details:
            print("No stat details returned")
            return pd.DataFrame()

        rows = stat_details.get('rows', [])
        print(f"Found {len(rows)} players with rankings")

        records = []
        for r in rows:
            player_record = {
                "player_id": r.get("playerId"),
                "player_name": r.get("playerName"),
                "world_rank": r.get("rank"),
            }

            # Extract additional stats if available
            for s in r.get("stats", []):
                stat_name = s.get("statName", "").lower()
                stat_value = s.get("statValue")

                if "points" in stat_name or "avg" in stat_name:
                    try:
                        player_record["world_rank_points"] = float(stat_value)
                    except (ValueError, TypeError):
                        pass

            records.append(player_record)

        df = pd.DataFrame(records)
        df['fetched_date'] = datetime.now().strftime('%Y-%m-%d')

        # Ensure world_rank is numeric
        df['world_rank'] = pd.to_numeric(df['world_rank'], errors='coerce')

        # Sort by rank
        df = df.sort_values('world_rank')

        return df

    except requests.RequestException as e:
        print(f"Request error: {e}")
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description='Fetch world golf rankings')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                       help='Year to fetch (default: current year)')
    parser.add_argument('--output', type=str, default=None,
                       help='Output CSV path (default: data/rankings/owgr_{year}.csv)')

    args = parser.parse_args()

    # Fetch rankings
    df = fetch_world_rankings(args.year)

    if len(df) == 0:
        print("No rankings data fetched!")
        return

    # Default output path
    if args.output is None:
        output_dir = Path("data/rankings")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"owgr_{args.year}.csv"
    else:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save CSV
    df.to_csv(output_path, index=False)

    # Upsert into DuckDB players table
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent / "database"))
        from db import get_conn
        _df = df.copy()
        _df["player_id"] = _df["player_id"].astype(str)
        _df["updated_at"] = pd.Timestamp.now()
        for c in ["first_name", "last_name", "country", "is_active",
                  "world_rank_points", "first_name", "last_name"]:
            if c not in _df.columns:
                _df[c] = None
        _cols = ["player_id", "player_name", "first_name", "last_name", "country",
                 "world_rank", "world_rank_points", "is_active", "updated_at"]
        _out = _df[[c for c in _cols if c in _df.columns]]
        with get_conn() as _conn:
            for _, row in _out.iterrows():
                _conn.execute(
                    "INSERT OR REPLACE INTO players VALUES (?,?,?,?,?,?,?,?,?)",
                    [row.get("player_id"), row.get("player_name"),
                     row.get("first_name"), row.get("last_name"),
                     row.get("country"), row.get("world_rank"),
                     row.get("world_rank_points"), row.get("is_active"),
                     row.get("updated_at")]
                )
        print(f"  DB: upserted {len(_out):,} players")
    except Exception as _e:
        print(f"  DB upsert skipped: {_e}")

    print(f"\n{'='*60}")
    print(f"World Rankings Fetched Successfully!")
    print(f"{'='*60}")
    print(f"  Players: {len(df)}")
    print(f"  Top 10:")
    for _, row in df.head(10).iterrows():
        print(f"    {int(row['world_rank']):3d}. {row['player_name']}")
    print(f"\n  Saved to: {output_path}")


if __name__ == '__main__':
    main()