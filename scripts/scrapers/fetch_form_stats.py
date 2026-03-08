#!/usr/bin/env python3
"""
PGA Tour Form Stats Scraper
===========================

Fetches additional stats beyond Strokes Gained that indicate recent form.

These stats complement SG by capturing:
1. Scoring efficiency (birdies, bogeys, scoring average)
2. Ball-striking consistency (GIR, driving accuracy, proximity)
3. Clutch performance (scrambling, sand saves, bounce back)
4. Putting under pressure (3-putt avoidance, putts per round)

Usage:
    # Scrape form stats for 2025
    python scripts/scrapers/fetch_form_stats.py --year 2025

    # Scrape multiple years
    python scripts/scrapers/fetch_form_stats.py --year 2024 --year 2025
"""

import time
import argparse
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

# ============================================================================
# Form Stats Definition
# ============================================================================

# Stats that indicate recent form beyond SG
# Format: stat_id -> (stat_name, description, higher_is_better)
FORM_STATS = {
    # Scoring Stats (most directly predictive)
    "120": ("Scoring Average", "Actual scoring average", False),
    "156": ("Birdie Average", "Birdies per round", True),
    "352": ("Bogey Avoidance", "Bogeys per round (inverse)", False),

    # Ball Striking
    "103": ("GIR Percentage", "Greens in regulation %", True),
    "101": ("Driving Distance", "Average driving distance", True),
    "102": ("Driving Accuracy", "Fairways hit %", True),
    "331": ("Proximity to Hole", "Avg distance from hole on approach", False),

    # Scrambling / Short Game
    "130": ("Scrambling", "Up and down % when missing GIR", True),
    "111": ("Sand Save Percentage", "Sand save %", True),
    "02570": ("SG Around Green", "Strokes gained around green", True),

    # Putting
    "104": ("Putts Per Round", "Average putts per round", False),
    "413": ("3-Putt Avoidance", "3-putt avoidance %", True),
    "119": ("1-Putt Percentage", "1-putt %", True),

    # Clutch / Consistency
    "160": ("Bounce Back", "Birdie+ after bogey+ %", True),
    "02414": ("Bogey Avoidance", "% of holes where bogey is made (lower = better)", False),
    "02419": ("Bogey Average", "Average bogeys per round (lower = better)", False),

    # Additional valuable stats
    "108": ("Birdie or Better %", "% of holes with birdie+", True),
    "299": ("Par 3 Scoring", "Scoring average on par 3s", False),
    "142": ("Par 4 Scoring", "Scoring average on par 4s", False),
    "143": ("Par 5 Scoring", "Scoring average on par 5s", False),
}

# Output directory
OUTPUT_DIR = Path("data/historical")


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
                    error_messages = [e.get('message', '') for e in data.get('errors', [])]
                    if any('not found' in msg.lower() for msg in error_messages):
                        return {'data': {'statDetails': None}}
                    # Don't raise for other errors, just return empty
                    return {'data': {'statDetails': None}}

                return data

            if attempt < retries - 1:
                wait_time = sleep * (attempt + 1)
                time.sleep(wait_time)
                continue

            return {'data': {'statDetails': None}}

        except requests.RequestException as e:
            if attempt < retries - 1:
                wait_time = sleep * (attempt + 1)
                time.sleep(wait_time)
                continue
            return {'data': {'statDetails': None}}

    return {'data': {'statDetails': None}}


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

        # Get the primary stat value (usually "Avg" or the main component)
        primary_value = None
        for s in r["stats"]:
            component = s.get("statName", "")
            value = s.get("statValue")

            # Prefer "Avg" or "%" or first numeric value
            if component.lower() in ["avg", "average", "%", "total"]:
                primary_value = value
                break
            elif primary_value is None and value is not None:
                primary_value = value

        if primary_value is not None:
            records.append({
                "player_id": int(r["playerId"]),
                "player_name": r["playerName"],
                "rank": r.get("rank"),
                "stat_id": stat_id,
                "stat_name": stat_name,
                "stat_value": primary_value,
                "tournament_id": tournament_id,
                "tournament_name": tournament_name,
                "year": year,
            })

    return pd.DataFrame(records)


def parse_stat_value(value_str) -> float:
    """Parse stat value string to float."""
    if value_str is None:
        return None
    if isinstance(value_str, (int, float)):
        return float(value_str)

    # Remove common suffixes
    cleaned = str(value_str).replace('%', '').replace("'", '').replace('"', '')
    cleaned = cleaned.replace(',', '').strip()

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


# ============================================================================
# Main Scraping Logic
# ============================================================================

def scrape_form_stats_for_year(
    year: int,
    output_dir: Path = OUTPUT_DIR,
    stats_to_scrape: Dict = None,
    sleep_time: float = 0.5
):
    """
    Scrape form stats for a year.
    """
    if stats_to_scrape is None:
        stats_to_scrape = FORM_STATS

    print("\n" + "=" * 70)
    print(f"SCRAPING FORM STATS FOR {year}")
    print("=" * 70)
    print(f"Stats to scrape: {len(stats_to_scrape)}")
    print()

    # Get tournament list using a common stat
    print("Getting tournament list...")
    tournaments = get_tournaments_for_year(year, "120")  # Scoring Average

    if not tournaments:
        # Try alternate stat
        tournaments = get_tournaments_for_year(year, "156")  # Birdie Average

    print(f"Found {len(tournaments)} tournaments\n")

    if not tournaments:
        print(f"No tournaments found for {year}")
        return pd.DataFrame()

    total_requests = len(stats_to_scrape) * len(tournaments)
    completed_requests = 0
    all_stats = []

    # Scrape each stat
    for stat_idx, (stat_id, stat_info) in enumerate(stats_to_scrape.items(), 1):
        stat_name = stat_info[0]
        print(f"\n[{stat_idx}/{len(stats_to_scrape)}] {stat_name} ({stat_id})")
        print("-" * 50)

        stat_data = []

        for tourn_idx, tourn in enumerate(tournaments, 1):
            completed_requests += 1
            tid = tourn["tournament_id"]
            tname = tourn["tournament_name"]

            pct = (completed_requests / total_requests) * 100
            print(f"  [{pct:5.1f}%] {tname[:35]:35s} ", end="", flush=True)

            try:
                df = fetch_stat_for_tournament(stat_id, stat_name, tid, tname, year)

                if df.empty:
                    print("⊘")
                else:
                    stat_data.append(df)
                    print(f"✓ {len(df):3d}")

            except Exception as e:
                print(f"✗ {str(e)[:30]}")

            time.sleep(sleep_time)

        if stat_data:
            combined = pd.concat(stat_data, ignore_index=True)
            all_stats.append(combined)
            print(f"  Collected {len(combined):,} records")

    # Combine all stats
    if all_stats:
        final_df = pd.concat(all_stats, ignore_index=True)

        # Parse numeric values
        final_df['stat_value_numeric'] = final_df['stat_value'].apply(parse_stat_value)

        # Save CSV
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"form_stats_{year}.csv"
        final_df.to_csv(output_path, index=False)

        # Upsert into DuckDB
        try:
            import sys as _sys
            _db_path = Path(__file__).parent.parent.parent / "scripts" / "database"
            _sys.path.insert(0, str(_db_path))
            from db import get_conn
            _db_df = final_df.copy()
            _db_df["player_id"] = _db_df["player_id"].astype(str)
            _db_df["stat_id"]   = _db_df["stat_id"].astype(str)
            if "stat_value_numeric" in _db_df.columns:
                _db_df = _db_df.drop(columns=["stat_value"], errors="ignore")
                _db_df = _db_df.rename(columns={"stat_value_numeric": "stat_value"})
            _keep = ["player_id", "player_name", "tournament_id", "tournament_name",
                     "year", "stat_id", "stat_name", "stat_value"]
            _db_df = _db_df[[c for c in _keep if c in _db_df.columns]]
            with get_conn() as _conn:
                _conn.execute(f"DELETE FROM form_stats WHERE year = {year}")
                _conn.execute("INSERT INTO form_stats SELECT * FROM _db_df")
            print(f"  DB: upserted {len(_db_df):,} form_stats rows for {year}")
        except Exception as _e:
            print(f"  DB upsert skipped: {_e}")

        print("\n" + "=" * 70)
        print("SCRAPING COMPLETE")
        print("=" * 70)
        print(f"Total records: {len(final_df):,}")
        print(f"Saved to: {output_path}")
        print(f"\nBreakdown by stat:")
        print(final_df.groupby('stat_name').size().sort_values(ascending=False))

        return final_df

    return pd.DataFrame()


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scrape PGA Tour form stats (beyond SG)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Form stats captured:
  - Scoring: Scoring avg, birdie avg, bogey avoidance
  - Ball-striking: GIR%, driving distance/accuracy, proximity
  - Short game: Scrambling, sand saves, SG:ARG
  - Putting: Putts/round, 3-putt avoidance, 1-putt %
  - Clutch: Bounce back, par breakers, final round scoring

Examples:
    # Scrape 2025 form stats
    python scripts/scrapers/fetch_form_stats.py --year 2025

    # Scrape 2024 and 2025
    python scripts/scrapers/fetch_form_stats.py --year 2024 --year 2025
        """
    )

    parser.add_argument(
        "--year",
        type=int,
        action="append",
        required=True,
        help="Year(s) to scrape (can specify multiple)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/historical",
        help="Output directory"
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Sleep between requests (seconds)"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: only scrape most important stats"
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    # Quick mode uses fewer stats
    if args.quick:
        quick_stats = {
            "120": FORM_STATS["120"],  # Scoring Average
            "156": FORM_STATS["156"],  # Birdie Average
            "103": FORM_STATS["103"],  # GIR %
            "130": FORM_STATS["130"],  # Scrambling
            "104": FORM_STATS["104"],  # Putts Per Round
            "160": FORM_STATS["160"],  # Bounce Back
        }
        stats_to_scrape = quick_stats
        print("Quick mode: scraping 6 key form stats")
    else:
        stats_to_scrape = FORM_STATS

    for year in args.year:
        scrape_form_stats_for_year(
            year=year,
            output_dir=output_dir,
            stats_to_scrape=stats_to_scrape,
            sleep_time=args.sleep
        )

    print("\n" + "=" * 70)
    print("ALL YEARS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
