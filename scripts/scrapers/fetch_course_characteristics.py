#!/usr/bin/env python3
"""
Course Characteristics Scraper
==============================

Fetches course-level statistics (hole-by-hole data) from PGA Tour's GraphQL API.
This provides course characteristics like scoring averages, birdies, bogeys per hole.

This data helps identify course profiles:
- Easy/hard holes
- Birdie opportunities vs scoring risks
- Course difficulty ranking

Usage:
    # Fetch course stats for American Express 2025
    python scripts/scrapers/fetch_course_characteristics.py --tournament-id R2026005

    # Fetch for a specific tournament by name
    python scripts/scrapers/fetch_course_characteristics.py --tournament-name "The American Express" --year 2025

    # Fetch all tournaments for a year
    python scripts/scrapers/fetch_course_characteristics.py --all --year 2025

Output columns:
    - tournament_id: PGA Tour tournament ID
    - tournament_name: Tournament name
    - course_id: Course ID
    - course_name: Course name
    - course_par: Total course par
    - course_yardage: Total yardage
    - hole_num: Hole number (1-18)
    - hole_par: Par for hole
    - hole_yards: Yardage for hole
    - scoring_avg: Scoring average
    - scoring_diff: Difference from par (+ = harder, - = easier)
    - eagles: Eagle count
    - birdies: Birdie count
    - pars: Par count
    - bogeys: Bogey count
    - double_bogeys: Double bogey+ count
    - difficulty_rank: Hole difficulty rank (1 = hardest)
"""

import argparse
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
import time

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

# Query to get tournament list
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
    tournamentPills {
      tournamentId
      displayName
    }
  }
}
"""

# Query to get course hole-by-hole stats
COURSE_STATS_QUERY = """
query CourseStats($tournamentId: ID!) {
  courseStats(tournamentId: $tournamentId) {
    tournamentId
    courses {
      courseId
      courseName
      courseCode
      par
      yardage
      hostCourse
      roundHoleStats {
        roundHeader
        roundNum
        holeStats {
          ... on CourseHoleStats {
            courseHoleNum
            parValue
            yards
            scoringAverage
            scoringAverageDiff
            eagles
            birdies
            pars
            bogeys
            doubleBogey
            rank
          }
          ... on SummaryRow {
            rowType
            par
            scoringAverage
            scoringAverageDiff
            eagles
            birdies
            pars
            bogeys
            doubleBogey
          }
        }
      }
    }
  }
}
"""

# ============================================================================
# Functions
# ============================================================================

def safe_float(value, default=0.0):
    """Safely convert value to float, handling '-' and other non-numeric strings."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if value in ['-', '', 'N/A', 'n/a', '--']:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    return default


def safe_int(value, default=0):
    """Safely convert value to int, handling '-' and other non-numeric strings."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if value in ['-', '', 'N/A', 'n/a', '--']:
            return default
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default
    return default


def get_tournaments_for_year(year: int) -> list:
    """Get list of tournaments for a year."""
    payload = {
        "operationName": "StatDetails",
        "variables": {
            "tourCode": "R",
            "statId": "02567",  # SG Total - just to get tournament list
            "year": year,
        },
        "query": STAT_DETAILS_QUERY,
    }

    try:
        resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=30)
        if resp.status_code != 200:
            return []

        data = resp.json()
        stat_details = data.get('data', {}).get('statDetails', {})
        pills = stat_details.get('tournamentPills', [])

        return [
            {"tournament_id": p["tournamentId"], "tournament_name": p["displayName"]}
            for p in pills
        ]
    except Exception as e:
        print(f"Error getting tournaments: {e}")
        return []


def fetch_course_characteristics(tournament_id: str, tournament_name: str = None) -> pd.DataFrame:
    """
    Fetch course-level hole-by-hole statistics for a tournament.

    Args:
        tournament_id: PGA Tour tournament ID (e.g., "R2025002")
        tournament_name: Tournament name (optional, for labeling)

    Returns:
        DataFrame with hole-by-hole course statistics
    """
    print(f"  Fetching course characteristics for {tournament_name or tournament_id}...")

    payload = {
        "operationName": "CourseStats",
        "variables": {"tournamentId": tournament_id},
        "query": COURSE_STATS_QUERY,
    }

    try:
        resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"    HTTP Error: {resp.status_code}")
            return pd.DataFrame()

        data = resp.json()

        if data.get("errors"):
            print(f"    GraphQL errors: {data['errors']}")
            return pd.DataFrame()

        course_stats = data.get('data', {}).get('courseStats')
        if not course_stats:
            print(f"    No course stats data returned")
            return pd.DataFrame()

        courses = course_stats.get('courses', [])
        if not courses:
            print(f"    No courses found")
            return pd.DataFrame()

        records = []

        for course in courses:
            course_id = course.get('courseId')
            course_name = course.get('courseName')
            course_code = course.get('courseCode')
            course_par = course.get('par')
            course_yardage = course.get('yardage')
            is_host = course.get('hostCourse', False)

            # Get "All Rounds" stats (roundNum = null)
            for round_stats in course.get('roundHoleStats', []):
                # Focus on "All Rounds" aggregate
                if round_stats.get('roundNum') is not None:
                    continue

                for hole_stat in round_stats.get('holeStats', []):
                    # Skip summary rows (OUT, IN, TOTAL)
                    if 'rowType' in hole_stat:
                        continue

                    # Skip holes with no scoring data (API returns '-' for old tournaments)
                    scoring_avg_raw = hole_stat.get('scoringAverage')
                    if scoring_avg_raw in [None, '-', ''] or hole_stat.get('birdies') is None:
                        continue

                    # Extract hole-level stats using safe parsers
                    records.append({
                        'tournament_id': tournament_id,
                        'tournament_name': tournament_name,
                        'course_id': course_id,
                        'course_name': course_name,
                        'course_code': course_code,
                        'course_par': course_par,
                        'course_yardage': course_yardage,
                        'is_host_course': is_host,
                        'hole_num': safe_int(hole_stat.get('courseHoleNum')),
                        'hole_par': safe_int(hole_stat.get('parValue'), 4),
                        'hole_yards': hole_stat.get('yards'),
                        'scoring_avg': safe_float(hole_stat.get('scoringAverage')),
                        'scoring_diff': hole_stat.get('scoringAverageDiff'),
                        'eagles': safe_int(hole_stat.get('eagles')),
                        'birdies': safe_int(hole_stat.get('birdies')),
                        'pars': safe_int(hole_stat.get('pars')),
                        'bogeys': safe_int(hole_stat.get('bogeys')),
                        'double_bogeys': safe_int(hole_stat.get('doubleBogey')),
                        'difficulty_rank': safe_int(hole_stat.get('rank')),
                    })

        if not records:
            print(f"    No hole data extracted")
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df['fetched_date'] = datetime.now().strftime('%Y-%m-%d')

        print(f"    Found {len(df)} hole records across {df['course_name'].nunique()} course(s)")

        return df

    except requests.RequestException as e:
        print(f"    Request error: {e}")
        return pd.DataFrame()


def compute_course_profile(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute aggregate course profile metrics from hole-level data.

    Args:
        df: DataFrame with hole-level stats

    Returns:
        DataFrame with one row per course with aggregate metrics
    """
    if df.empty:
        return pd.DataFrame()

    # Group by course
    course_profiles = []

    for (tid, cid), group in df.groupby(['tournament_id', 'course_id']):
        total_holes = len(group)

        profile = {
            'tournament_id': tid,
            'tournament_name': group['tournament_name'].iloc[0],
            'course_id': cid,
            'course_name': group['course_name'].iloc[0],
            'course_par': group['course_par'].iloc[0],
            'course_yardage': group['course_yardage'].iloc[0],
            'is_host_course': group['is_host_course'].iloc[0],

            # Scoring metrics
            'total_scoring_avg': group['scoring_avg'].sum(),
            'avg_hole_difficulty': group['scoring_avg'].mean() - group['hole_par'].mean(),

            # Birdie/Bogey analysis
            'total_eagles': group['eagles'].sum(),
            'total_birdies': group['birdies'].sum(),
            'total_pars': group['pars'].sum(),
            'total_bogeys': group['bogeys'].sum(),
            'total_double_bogeys': group['double_bogeys'].sum(),

            # Percentages (rough - based on counts)
            'birdie_pct': group['birdies'].sum() / (group['birdies'].sum() + group['pars'].sum() + group['bogeys'].sum() + group['double_bogeys'].sum()) * 100 if group['birdies'].sum() > 0 else 0,
            'bogey_pct': group['bogeys'].sum() / (group['birdies'].sum() + group['pars'].sum() + group['bogeys'].sum() + group['double_bogeys'].sum()) * 100 if group['bogeys'].sum() > 0 else 0,

            # Par breakdown
            'par3_count': len(group[group['hole_par'] == 3]),
            'par4_count': len(group[group['hole_par'] == 4]),
            'par5_count': len(group[group['hole_par'] == 5]),

            # Difficulty distribution
            'hardest_holes': group.nsmallest(3, 'difficulty_rank')['hole_num'].tolist(),
            'easiest_holes': group.nlargest(3, 'difficulty_rank')['hole_num'].tolist(),
        }

        course_profiles.append(profile)

    return pd.DataFrame(course_profiles)


def main():
    parser = argparse.ArgumentParser(description='Fetch course-level hole statistics')
    parser.add_argument('--tournament-id', type=str, default=None,
                       help='Tournament ID (e.g., R2025002)')
    parser.add_argument('--tournament-name', type=str, default=None,
                       help='Tournament name (will search for matching ID)')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                       help='Year (default: current year)')
    parser.add_argument('--all', action='store_true',
                       help='Fetch all tournaments for the year')
    parser.add_argument('--historical', action='store_true',
                       help='Fetch all tournaments for multiple years (2023-current, API limitation)')
    parser.add_argument('--start-year', type=int, default=2023,
                       help='Start year for historical fetch (default: 2023, API has no data before this)')
    parser.add_argument('--end-year', type=int, default=None,
                       help='End year for historical fetch (default: current year)')
    parser.add_argument('--output', type=str, default=None,
                       help='Output CSV path')
    parser.add_argument('--profile', action='store_true',
                       help='Also output aggregate course profile')

    args = parser.parse_args()

    if args.historical:
        # Fetch all tournaments for multiple years
        end_year = args.end_year or datetime.now().year
        years = list(range(args.start_year, end_year + 1))

        print(f"\n{'='*60}")
        print(f"  HISTORICAL COURSE CHARACTERISTICS FETCH")
        print(f"  Years: {args.start_year} - {end_year}")
        print(f"{'='*60}\n")

        all_data = []
        total_tournaments = 0

        for year in years:
            print(f"\n[Year {year}]")
            print("-" * 40)

            tournaments = get_tournaments_for_year(year)
            print(f"  Found {len(tournaments)} tournaments")

            year_data = []
            for i, t in enumerate(tournaments):
                print(f"  [{i+1}/{len(tournaments)}] {t['tournament_name']}", end="")
                df = fetch_course_characteristics(t['tournament_id'], t['tournament_name'])
                if len(df) > 0:
                    df['year'] = year
                    year_data.append(df)
                    print(f" ✓ ({len(df)} holes)")
                else:
                    print(f" ✗ (no data)")
                time.sleep(0.3)  # Rate limiting

            if year_data:
                year_df = pd.concat(year_data, ignore_index=True)
                all_data.append(year_df)
                total_tournaments += len(year_data)
                print(f"  Year {year}: {len(year_data)} tournaments, {len(year_df)} hole records")

                # Save per-year file
                year_output = Path(f"data/course_characteristics/all_courses_{year}.csv")
                year_output.parent.mkdir(parents=True, exist_ok=True)
                year_df.to_csv(year_output, index=False)
                print(f"  Saved: {year_output}")

        if not all_data:
            print("\nNo course data fetched!")
            return

        # Combine all years
        df = pd.concat(all_data, ignore_index=True)
        default_output = f"data/course_characteristics/all_courses_historical_{args.start_year}_{end_year}.csv"

        # Output combined file
        output_path = Path(args.output) if args.output else Path(default_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)

        print(f"\n{'='*60}")
        print(f"  HISTORICAL FETCH COMPLETE!")
        print(f"{'='*60}")
        print(f"  Years: {args.start_year} - {end_year}")
        print(f"  Total Tournaments: {total_tournaments}")
        print(f"  Total Hole Records: {len(df):,}")
        print(f"  Unique Courses: {df['course_name'].nunique()}")
        print(f"\n  Combined file: {output_path}")
        return

    elif args.all:
        # Fetch all tournaments
        print(f"\nFetching course characteristics for all {args.year} tournaments...")
        tournaments = get_tournaments_for_year(args.year)
        print(f"Found {len(tournaments)} tournaments\n")

        all_data = []
        for i, t in enumerate(tournaments):
            print(f"[{i+1}/{len(tournaments)}] {t['tournament_name']}")
            df = fetch_course_characteristics(t['tournament_id'], t['tournament_name'])
            if len(df) > 0:
                all_data.append(df)
            time.sleep(0.5)  # Rate limiting

        if not all_data:
            print("\nNo course data fetched!")
            return

        df = pd.concat(all_data, ignore_index=True)
        default_output = f"data/course_characteristics/all_courses_{args.year}.csv"

    elif args.tournament_id:
        # Fetch specific tournament by ID
        tournament_name = args.tournament_name or args.tournament_id
        df = fetch_course_characteristics(args.tournament_id, tournament_name)
        safe_name = tournament_name.lower().replace(' ', '_').replace('-', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')
        default_output = f"data/course_characteristics/{safe_name}_{args.year}.csv"

    elif args.tournament_name:
        # Search for tournament by name
        tournaments = get_tournaments_for_year(args.year)
        matches = [t for t in tournaments if args.tournament_name.lower() in t['tournament_name'].lower()]

        if not matches:
            print(f"No tournament found matching '{args.tournament_name}'")
            print("Available tournaments:")
            for t in tournaments[:20]:
                print(f"  {t['tournament_id']}: {t['tournament_name']}")
            return

        if len(matches) > 1:
            print(f"Multiple matches found for '{args.tournament_name}':")
            for t in matches:
                print(f"  {t['tournament_id']}: {t['tournament_name']}")
            print("Please use --tournament-id to specify")
            return

        t = matches[0]
        df = fetch_course_characteristics(t['tournament_id'], t['tournament_name'])
        safe_name = t['tournament_name'].lower().replace(' ', '_').replace('-', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')
        default_output = f"data/course_characteristics/{safe_name}_{args.year}.csv"
    else:
        parser.print_help()
        return

    if len(df) == 0:
        print("\nNo course characteristics data fetched!")
        return

    # Output path
    output_path = Path(args.output) if args.output else Path(default_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save hole-level data
    df.to_csv(output_path, index=False)

    print(f"\n{'='*60}")
    print(f"Course Characteristics Fetched Successfully!")
    print(f"{'='*60}")
    print(f"  Hole Records: {len(df)}")
    print(f"  Tournaments: {df['tournament_name'].nunique()}")
    print(f"  Courses: {df['course_name'].nunique()}")
    print(f"\n  Saved to: {output_path}")

    # Optionally compute and save course profiles
    if args.profile:
        profile_df = compute_course_profile(df)
        if len(profile_df) > 0:
            profile_path = output_path.with_name(output_path.stem + '_profiles.csv')
            profile_df.to_csv(profile_path, index=False)
            print(f"\n  Course Profile Summary:")
            for _, row in profile_df.iterrows():
                print(f"    {row['course_name']}:")
                print(f"      Scoring Avg: {row['total_scoring_avg']:.1f} (Par {row['course_par']})")
                print(f"      Birdie %: {row['birdie_pct']:.1f}% | Bogey %: {row['bogey_pct']:.1f}%")
            print(f"\n  Profile saved to: {profile_path}")


if __name__ == '__main__':
    main()