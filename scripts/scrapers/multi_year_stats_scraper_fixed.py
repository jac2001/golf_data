"""
Fixed Multi-Year Stats Scraper
================================

This version is more robust with:
- Better error handling
- Progress tracking
- Checkpoint saving (resume if interrupted)
- Verbose logging

Usage:
    python multi_year_stats_scraper_fixed.py --year 2023
"""

import time
import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests

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

STAT_DETAILS_QUERY = """
query StatDetails(
  $tourCode: TourCode!
  $statId: String!
  $year: Int
  $eventQuery: StatDetailEventQuery
) {
  statDetails(
    tourCode: $tourCode
    statId: $statId
    year: $year
    eventQuery: $eventQuery
  ) {
    tourCode
    year
    statId
    statTitle
    tournamentPills {
      tournamentId
      displayName
    }
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

# Key stats to scrape (focus on most important)
KEY_STATS = {
    "02567": "Strokes Gained: Total",
    "02568": "Strokes Gained: Off-the-Tee",
    "02569": "Strokes Gained: Approach",
    "02570": "Strokes Gained: Around-the-Green",
    "02564": "Strokes Gained: Putting",
    "02674": "Strokes Gained: Tee-to-Green",
}

# ============================================================================
# Helper Functions
# ============================================================================

def post_graphql(payload: Dict, retries: int = 3, sleep: float = 1.0) -> Dict:
    """Execute GraphQL request with retries."""
    for attempt in range(retries):
        try:
            resp = requests.post(
                GRAPHQL_URL,
                headers=DEFAULT_HEADERS,
                json=payload,
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()

                if data.get("errors"):
                    # Some errors are OK (e.g., stat not available for this tournament)
                    error_messages = [e.get('message', '') for e in data.get('errors', [])]
                    if any('not found' in msg.lower() for msg in error_messages):
                        return {'data': {'statDetails': None}}  # Return empty
                    raise RuntimeError(f"GraphQL errors: {data['errors']}")

                return data

            if attempt < retries - 1:
                wait_time = sleep * (attempt + 1)
                print(f"    Retry {attempt + 1}/{retries} after {wait_time}s...")
                time.sleep(wait_time)
                continue

            raise RuntimeError(f"HTTP {resp.status_code}")

        except requests.RequestException as e:
            if attempt < retries - 1:
                wait_time = sleep * (attempt + 1)
                print(f"    Request error, retry {attempt + 1}/{retries} after {wait_time}s...")
                time.sleep(wait_time)
                continue
            raise

    raise RuntimeError("Request failed after all retries")


def get_tournaments_for_year(year: int, stat_id: str) -> List[Dict]:
    """Get list of tournaments for a year."""
    payload = {
        "operationName": "StatDetails",
        "variables": {
            "tourCode": "R",
            "statId": stat_id,
            "year": year,
        },
        "query": STAT_DETAILS_QUERY,
    }

    data = post_graphql(payload)

    if data.get('data') is None or data['data'].get('statDetails') is None:
        return []

    pills = data['data']['statDetails'].get('tournamentPills', [])

    return [
        {
            "tournament_id": p["tournamentId"],
            "tournament_name": p["displayName"],
        }
        for p in pills
    ]


def fetch_stat_for_tournament(
    stat_id: str,
    stat_name: str,
    tournament_id: str,
    tournament_name: str,
    year: int,
) -> pd.DataFrame:
    """Fetch one stat for one tournament."""
    payload = {
        "operationName": "StatDetails",
        "variables": {
            "tourCode": "R",
            "statId": stat_id,
            "year": year,
            "eventQuery": {
                "queryType": "EVENT_ONLY",
                "tournamentId": tournament_id
            }
        },
        "query": STAT_DETAILS_QUERY,
    }

    data = post_graphql(payload)

    if data.get('data') is None or data['data'].get('statDetails') is None:
        return pd.DataFrame()

    stat_details = data['data']['statDetails']
    rows = stat_details.get('rows', [])

    records = []
    for r in rows:
        if not r.get("stats"):
            continue

        for s in r["stats"]:
            records.append({
                "player_id": r["playerId"],
                "player_name": r["playerName"],
                "rank": r.get("rank"),
                "stat_id": stat_id,
                "stat_name": stat_name,
                "stat_component": s.get("statName"),
                "stat_value": s.get("statValue"),
                "tournament_id": tournament_id,
                "tournament_name": tournament_name,
                "year": year,
            })

    return pd.DataFrame(records)


def save_checkpoint(data: List[pd.DataFrame], checkpoint_path: Path):
    """Save progress checkpoint."""
    if data:
        df = pd.concat(data, ignore_index=True)
        df.to_csv(checkpoint_path, index=False)


# ============================================================================
# Main Scraping Logic
# ============================================================================

def scrape_stats_for_year(
    year: int,
    output_dir: Path,
    stats_to_scrape: Dict[str, str] = None,
    sleep_time: float = 0.6
):
    """
    Scrape tournament stats for a year with robust error handling.
    """
    if stats_to_scrape is None:
        stats_to_scrape = KEY_STATS

    print("\n" + "="*70)
    print(f"SCRAPING STATS FOR {year}")
    print("="*70)
    print(f"Stats to scrape: {len(stats_to_scrape)}")
    print(f"Output: {output_dir}")
    print()

    # Get tournament list using first stat
    first_stat_id = list(stats_to_scrape.keys())[0]
    print(f"Getting tournament list using stat {first_stat_id}...")

    tournaments = get_tournaments_for_year(year, first_stat_id)
    print(f"Found {len(tournaments)} tournaments\n")

    if not tournaments:
        print(f"⚠️  No tournaments found for {year}")
        return

    # Calculate total requests
    total_requests = len(stats_to_scrape) * len(tournaments)
    completed_requests = 0

    all_stats = []
    checkpoint_path = output_dir / f"checkpoint_stats_{year}.csv"

    # Try to resume from checkpoint
    if checkpoint_path.exists():
        print(f"📁 Found checkpoint file, loading...")
        checkpoint_df = pd.read_csv(checkpoint_path)
        all_stats.append(checkpoint_df)
        completed_requests = len(checkpoint_df['stat_id'].unique()) * len(tournaments)
        print(f"   Resuming from {completed_requests}/{total_requests} requests\n")

    # Scrape each stat
    for stat_idx, (stat_id, stat_name) in enumerate(stats_to_scrape.items(), 1):
        print(f"\n[{stat_idx}/{len(stats_to_scrape)}] Stat: {stat_name} ({stat_id})")
        print("-" * 70)

        stat_data = []

        for tourn_idx, tourn in enumerate(tournaments, 1):
            completed_requests += 1
            tid = tourn["tournament_id"]
            tname = tourn["tournament_name"]

            # Progress indicator
            pct = (completed_requests / total_requests) * 100
            print(f"  [{completed_requests}/{total_requests} ({pct:5.1f}%)] {tname[:40]:40s} ", end="")

            try:
                df = fetch_stat_for_tournament(stat_id, stat_name, tid, tname, year)

                if df.empty:
                    print("⊘")  # No data symbol
                else:
                    stat_data.append(df)
                    print(f"✓ {len(df):3d} rows")

            except Exception as e:
                print(f"✗ {str(e)[:50]}")

            time.sleep(sleep_time)

        # Add this stat's data to collection
        if stat_data:
            all_stats.extend(stat_data)
            print(f"\n  Collected {sum(len(d) for d in stat_data):,} records for this stat")

            # Save checkpoint
            save_checkpoint(all_stats, checkpoint_path)

    # Final save
    if all_stats:
        combined = pd.concat(all_stats, ignore_index=True)
        output_path = output_dir / f"tournament_stats_{year}.csv"
        combined.to_csv(output_path, index=False)

        # Remove checkpoint
        if checkpoint_path.exists():
            checkpoint_path.unlink()

        print("\n" + "="*70)
        print("✅ SCRAPING COMPLETE")
        print("="*70)
        print(f"Total records: {len(combined):,}")
        print(f"Saved to: {output_path}")
        print(f"\nBreakdown by stat:")
        print(combined.groupby('stat_name').size())

    else:
        print("\n⚠️  No data scraped")


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scrape PGA Tour tournament stats for a specific year"
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Year to scrape (e.g., 2023)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="historical_data",
        help="Output directory"
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.6,
        help="Sleep time between requests (seconds)"
    )
    parser.add_argument(
        "--all-stats",
        action="store_true",
        help="Scrape ALL stats (not just key SG stats)"
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    stats_to_scrape = KEY_STATS

    if args.all_stats:
        # Load full stat catalog
        try:
            catalog = pd.read_csv("pgatour_stat_id_catalog.csv")
            stats_to_scrape = {
                str(row['stat_id']).zfill(5): f"Stat {row['stat_id']}"
                for _, row in catalog.iterrows()
            }
            print(f"Using ALL stats from catalog: {len(stats_to_scrape)}")
        except FileNotFoundError:
            print("⚠️  Stat catalog not found, using KEY_STATS only")

    print("\n" + "#"*70)
    print("# MULTI-YEAR STATS SCRAPER (FIXED)")
    print("#"*70)
    print(f"\nYear: {args.year}")
    print(f"Stats: {len(stats_to_scrape)}")
    print(f"Sleep: {args.sleep}s between requests")
    print(f"Output: {output_dir}")

    scrape_stats_for_year(
        year=args.year,
        output_dir=output_dir,
        stats_to_scrape=stats_to_scrape,
        sleep_time=args.sleep
    )

    print("\n" + "#"*70)
    print("# DONE!")
    print("#"*70)
    print(f"\nNext steps:")
    print(f"1. Check the output file in {output_dir}/")
    print(f"2. Run for other years: --year 2022, 2021, etc.")
    print(f"3. Merge with leaderboard data for complete dataset")


if __name__ == "__main__":
    main()