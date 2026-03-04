"""
Multi-Year Historical Data Scraper for PGA Tour
================================================

This scraper enhances your existing scrapers to collect data from 2020-2024.

Features:
- Scrapes tournament stats for multiple years
- Scrapes leaderboards for multiple years
- Organizes data by year for easy merging
- Creates course history features

Usage:
    python3 multi_year_scraper.py --years 2026 2021 2022 2023 2024

    Or for a single year:
    python multi_year_scraper.py --years 2023
"""

import time
import argparse
from typing import Dict, List
from pathlib import Path

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
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",  # May need updating if it rotates
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
    statType
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

TOURNAMENT_PAST_RESULTS_QUERY = """
query TournamentPastResults($tournamentId: ID!) {
  tournamentPastResults(id: $tournamentId) {
    id
    players {
      id
      position
      total
      parRelativeScore
      player {
        id
        displayName
        country
      }
      rounds {
        score
        parRelativeScore
      }
      additionalData
    }
  }
}
"""

# ============================================================================
# Utility Functions
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
                    raise RuntimeError(f"GraphQL errors: {data['errors']}")

                return data

            if attempt < retries - 1:
                time.sleep(sleep * (attempt + 1))
                continue

            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

        except requests.RequestException as e:
            if attempt < retries - 1:
                print(f"  [WARN] Request failed (attempt {attempt + 1}/{retries}): {e}")
                time.sleep(sleep * (attempt + 1))
                continue
            raise

    raise RuntimeError("GraphQL request failed after all retries")


# ============================================================================
# Tournament Leaderboard Scraping
# ============================================================================

def fetch_tournament_results(tournament_id: str, year: int) -> pd.DataFrame:
    """
    Fetch leaderboard results for a specific tournament.

    Args:
        tournament_id: Tournament ID (e.g., 'R2023493')
        year: Year for the tournament

    Returns:
        DataFrame with player results
    """
    payload = {
        "query": TOURNAMENT_PAST_RESULTS_QUERY,
        "variables": {"tournamentId": tournament_id},
        "operationName": "TournamentPastResults"
    }

    data = post_graphql(payload)
    tpr = data.get("data", {}).get("tournamentPastResults")

    if not tpr or not tpr.get("players"):
        return pd.DataFrame()  # Return empty instead of erroring

    rows = []
    for p in tpr["players"]:
        rows.append({
            "tournament_id": tournament_id,
            "year": year,
            "player_id": p["player"]["id"],
            "player_name": p["player"]["displayName"],
            "position": p["position"],
            "total_score": p["total"],
            "to_par": p["parRelativeScore"],
            "fedex_points": p["additionalData"][0] if len(p.get("additionalData", [])) > 0 else None,
            "earnings": p["additionalData"][1] if len(p.get("additionalData", [])) > 1 else None,
            "rounds_played": len(p.get("rounds", []))
        })

    return pd.DataFrame(rows)


def get_tournament_ids_for_year(year: int, stat_id: str = "02567") -> List[Dict]:
    """
    Get list of tournaments for a given year using stat query.

    Args:
        year: Year to query
        stat_id: Any stat ID (we just need the tournament list)

    Returns:
        List of dicts with tournament_id and tournament_name
    """
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
    pills = (
        data.get("data", {})
        .get("statDetails", {})
        .get("tournamentPills", [])
    )

    return [
        {
            "tournament_id": p["tournamentId"],
            "tournament_name": p["displayName"],
            "year": year
        }
        for p in pills
    ]


def scrape_leaderboards_for_year(year: int, sleep_time: float = 0.5) -> pd.DataFrame:
    """
    Scrape all tournament leaderboards for a given year.

    Args:
        year: Year to scrape
        sleep_time: Seconds to sleep between requests

    Returns:
        DataFrame with all leaderboards
    """
    print(f"\n{'='*70}")
    print(f"SCRAPING LEADERBOARDS FOR {year}")
    print(f"{'='*70}\n")

    # Get tournament list
    print(f"Fetching tournament list for {year}...")
    tournaments = get_tournament_ids_for_year(year)
    print(f"Found {len(tournaments)} tournaments\n")

    all_leaderboards = []

    for i, tourn in enumerate(tournaments, 1):
        tid = tourn["tournament_id"]
        name = tourn["tournament_name"]

        print(f"[{i}/{len(tournaments)}] Fetching {name} ({tid})...")

        try:
            df = fetch_tournament_results(tid, year)

            if df.empty:
                print(f"  [WARN] No results found")
                continue

            df["tournament_name"] = name
            all_leaderboards.append(df)
            print(f"  [OK] {len(df)} players")

        except Exception as e:
            print(f"  [ERROR] {e}")
            continue

        time.sleep(sleep_time)

    if not all_leaderboards:
        print(f"\n⚠️  No leaderboards scraped for {year}")
        return pd.DataFrame()

    combined = pd.concat(all_leaderboards, ignore_index=True)
    print(f"\n✅ Total records for {year}: {len(combined):,}")

    return combined


# ============================================================================
# Tournament Stats Scraping
# ============================================================================

def load_stat_catalog(csv_path: str) -> pd.DataFrame:
    """Load stat catalog."""
    df = pd.read_csv(csv_path, dtype={"stat_id": str})
    df["stat_id"] = df["stat_id"].str.zfill(5)
    return df


def fetch_stat_by_tournament(
    stat_id: str,
    tournament_id: str,
    tournament_name: str,
    year: int,
) -> pd.DataFrame:
    """Fetch stats for one stat at one tournament."""
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

    if data.get("data") is None or data.get("data", {}).get("statDetails") is None:
        return pd.DataFrame()

    stat_details = data["data"]["statDetails"]
    rows = stat_details.get("rows", [])
    stat_title = stat_details.get("statTitle", f"Stat {stat_id}")

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
                "stat_name": stat_title,
                "stat_component": s.get("statName"),
                "stat_value": s.get("statValue"),
                "tournament_id": tournament_id,
                "tournament_name": tournament_name,
                "year": year,
            })

    return pd.DataFrame(records)


def scrape_stats_for_year(
    year: int,
    stat_catalog_path: str = "/Users/jacklegnon/Desktop/golf_data/data/raw/pgatour_stat_id_catalog.csv",
    sleep_time: float = 0.5
) -> pd.DataFrame:
    """
    Scrape all tournament stats for a given year.

    Args:
        year: Year to scrape
        stat_catalog_path: Path to stat catalog CSV
        sleep_time: Seconds between requests

    Returns:
        DataFrame with all stats
    """
    print(f"\n{'='*70}")
    print(f"SCRAPING TOURNAMENT STATS FOR {year}")
    print(f"{'='*70}\n")

    # Load stat catalog
    stat_catalog = load_stat_catalog(stat_catalog_path)
    stat_ids = stat_catalog["stat_id"].tolist()
    print(f"Loaded {len(stat_ids)} stats to scrape")

    # Get tournament list (using first stat)
    print(f"\nFetching tournament list for {year}...")
    tournaments = get_tournament_ids_for_year(year, stat_ids[0])
    print(f"Found {len(tournaments)} tournaments\n")

    all_stats = []
    total_requests = len(stat_ids) * len(tournaments)
    request_count = 0

    for stat_id in stat_ids:
        print(f"\nProcessing stat {stat_id}...")

        for tourn in tournaments:
            request_count += 1
            tid = tourn["tournament_id"]
            name = tourn["tournament_name"]

            print(f"  [{request_count}/{total_requests}] {name[:30]:30s}...", end=" ")

            try:
                df = fetch_stat_by_tournament(stat_id, tid, name, year)

                if df.empty:
                    print("(no data)")
                else:
                    all_stats.append(df)
                    print(f"✓ {len(df)} rows")

            except Exception as e:
                print(f"✗ {e}")
                continue

            time.sleep(sleep_time)

    if not all_stats:
        print(f"\n⚠️  No stats scraped for {year}")
        return pd.DataFrame()

    combined = pd.concat(all_stats, ignore_index=True)
    print(f"\n✅ Total stats records for {year}: {len(combined):,}")

    return combined


# ============================================================================
# Main Execution
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scrape multi-year PGA Tour data for course history modeling"
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2025],
        help="Years to scrape (default: 2020-2024)"
    )
    parser.add_argument(
        "--leaderboards-only",
        action="store_true",
        help="Only scrape leaderboards (faster)"
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only scrape tournament stats"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="historical_data",
        help="Directory to save output files"
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    print(f"\n{'='*70}")
    print(f"MULTI-YEAR PGA TOUR DATA SCRAPER")
    print(f"{'='*70}")
    print(f"\nYears: {args.years}")
    print(f"Output directory: {output_dir}")
    print(f"Mode: ", end="")

    if args.leaderboards_only:
        print("Leaderboards only")
    elif args.stats_only:
        print("Stats only")
    else:
        print("Both leaderboards and stats")

    # Scrape each year
    for year in sorted(args.years):
        print(f"\n\n{'#'*70}")
        print(f"# YEAR {year}")
        print(f"{'#'*70}")

        # Leaderboards
        if not args.stats_only:
            leaderboards_df = scrape_leaderboards_for_year(year)

            if not leaderboards_df.empty:
                output_path = output_dir / f"leaderboards_{year}.csv"
                leaderboards_df.to_csv(output_path, index=False)
                print(f"\n📁 Saved to: {output_path}")

        # Stats
        if not args.leaderboards_only:
            stats_df = scrape_stats_for_year(year)

            if not stats_df.empty:
                output_path = output_dir / f"tournament_stats_{year}.csv"
                stats_df.to_csv(output_path, index=False)
                print(f"\n📁 Saved to: {output_path}")

    print(f"\n\n{'='*70}")
    print("✅ SCRAPING COMPLETE!")
    print(f"{'='*70}")
    print(f"\nFiles saved to: {output_dir}/")
    print("\nNext steps:")
    print("1. Run course_history_features.py to create course history features")
    print("2. Retrain models with enhanced dataset")
    print("3. Validate on 2026 predictions")


if __name__ == "__main__":
    main()
