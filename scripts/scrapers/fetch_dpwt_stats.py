#!/usr/bin/env python3
"""
DP World Tour Stats Scraper
===========================

Fetches DP World Tour leaderboard stats from the european tour API.
Falls back to ESPN results only if needed.

Primary API:
    https://www.europeantour.com/api/sportdata/player/PlayersStatisticsBySeasonAndType/{year}/statType/{stat_type}

Example:
    /2026/statType/strokes-gained-total

Usage:
    python fetch_dpwt_stats.py --year 2026 --stat-type strokes-gained-total
    python fetch_dpwt_stats.py --year 2026 --stat-type sg_total
"""

import argparse
import json
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import time
import sys

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
HISTORICAL_DIR = DATA_DIR / "historical"
REFERENCE_DIR = DATA_DIR / "reference"

# DP World Tour API
DPWT_API_BASE = "https://www.europeantour.com"
DPWT_STATS_BY_SEASON = "/api/sportdata/player/PlayersStatisticsBySeasonAndType/{season}/statType/{stat_type}"

# ESPN URLs (fallback)
ESPN_RESULTS_URL = "https://www.espn.com/golf/player/results/_/id/{espn_id}"

# Request settings
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 0.5  # Be nice to APIs

# Headers for DPWT API
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.europeantour.com/dpworld-tour/stats/",
    "Origin": "https://www.europeantour.com",
    "X-Requested-With": "XMLHttpRequest",
}

# Stat type aliases (CLI-friendly)
STAT_TYPE_ALIASES = {
    "sg_total": "strokes-gained-total",
    "sg_ott": "strokes-gained-off-the-tee",
    "sg_app": "strokes-gained-approach-the-green",
    "sg_arg": "strokes-gained-around-the-green",
    "sg_putt": "strokes-gained-putting",
    "scoring_avg": "scoring-average",
    "driving_distance": "driving-distance",
    "gir": "greens-in-regulation",
}

# Fallback slugs for stats that differ from display labels
STAT_TYPE_FALLBACKS = {
    "scoring-average": [
        "scoring-average",
        "stroke-average",
        "scoring-average-per-round",
        "stroke-average-per-round",
    ],
    "greens-in-regulation": [
        "greens-in-regulation",
        "greens-in-regulation-percentage",
        "gir-percentage",
    ],
    "birdies": [
        "birdies",
        "birdies-per-round",
        "birdies-or-better",
        "birdies-per-round-average",
    ],
    "bogeys": [
        "bogeys",
        "bogeys-per-round",
        "bogey-avoidance",
        "bogeys-per-round-average",
    ],
}

# Default stat set to pull in batch mode
DEFAULT_STAT_TYPES = [
    "strokes-gained-total",
    "strokes-gained-off-the-tee",
    "strokes-gained-approach-the-green",
    "strokes-gained-around-the-green",
    "strokes-gained-putting",
    "scoring-average",
    "driving-distance",
    "greens-in-regulation",
    "birdies",
    "bogeys",
]


# =============================================================================
# Player ID Mapping (PGA Tour ID -> DP World Tour ID)
# =============================================================================

# Maps PGA Tour player_id to DP World Tour player_id
# DPWT IDs can be found in player profile URLs: europeantour.com/players/name-{DPWT_ID}/
PGA_TO_DPWT_IDS = {
    # Top players who play both tours
    28237: 34024,   # Rory McIlroy
    30911: 35371,   # Tommy Fleetwood
    33204: 34046,   # Shane Lowry (corrected PGA ID)
    22405: 33419,   # Justin Rose (corrected PGA ID)
    46717: 35881,   # Viktor Hovland (corrected PGA ID from field)
    52215: 48563,   # Robert MacIntyre (corrected PGA ID from field)
    40098: 35468,   # Matt Fitzpatrick (corrected PGA ID from field)
    33448: 35534,   # Tyrrell Hatton
    32150: 34606,   # Jon Rahm
    49960: 40498,   # Sepp Straka (corrected PGA ID from field)
    52955: 52428,   # Ludvig Åberg
    27349: 34127,   # Alex Noren (corrected PGA ID from field)
    30925: 35214,   # Patrick Reed
    29420: 33148,   # Billy Horschel (not Danny Willett)
    35532: 39644,   # Tom Hoge (not Thomas Pieters)
    28089: 27890,   # Jason Day
    33141: 33141,   # Keegan Bradley (corrected PGA ID from field)
    34098: 34693,   # Russell Henley (corrected PGA ID from field)
}


def load_player_id_mapping() -> Dict[int, int]:
    """Load PGA to DPWT player ID mapping from file if exists."""
    mapping_file = REFERENCE_DIR / "pga_dpwt_player_ids.json"

    if mapping_file.exists():
        with open(mapping_file) as f:
            data = json.load(f)
            return {int(k): int(v) for k, v in data.items()}

    return PGA_TO_DPWT_IDS.copy()


def save_player_id_mapping(mapping: Dict[int, int]) -> None:
    """Save player ID mapping to file."""
    mapping_file = REFERENCE_DIR / "pga_espn_player_ids.json"
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    with open(mapping_file, 'w') as f:
        json.dump({str(k): v for k, v in mapping.items()}, f, indent=2)


def save_dpwt_stats(df: pd.DataFrame, year: int, stat_type: str) -> Path:
    """Save DPWT stats to data/historical."""
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    safe_stat = _normalize_stat_type(stat_type)
    filename = f"dpwt_stats_{year}_{safe_stat}.csv"
    out_path = HISTORICAL_DIR / filename
    df.to_csv(out_path, index=False)
    print(f"✓ Saved DPWT stats: {out_path}")
    return out_path


# =============================================================================
# ESPN Scraping Functions
# =============================================================================

def fetch_espn_results(espn_id: int) -> Optional[str]:
    """Fetch player results page from ESPN."""
    url = ESPN_RESULTS_URL.format(espn_id=espn_id)

    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text

    except requests.exceptions.RequestException as e:
        print(f"  Error fetching ESPN results: {e}")
        return None


def parse_espn_results(html: str, year: int = 2026) -> List[Dict]:
    """
    Parse ESPN results HTML to extract tournament results.

    Returns list of dicts with tournament results for the specified year.
    """
    soup = BeautifulSoup(html, 'html.parser')
    results = []

    # Find results tables
    tables = soup.find_all('table', class_='Table')

    for table in tables:
        # Check if this is a results table for the right season
        rows = table.find_all('tr')

        for row in rows[1:]:  # Skip header
            cells = row.find_all('td')

            if len(cells) >= 3:
                try:
                    # Tournament name
                    tournament_cell = cells[0]
                    tournament_name = tournament_cell.get_text(strip=True)

                    # Check if it's a DP World Tour event (not PGA)
                    # Look for common DPWT tournaments
                    dpwt_indicators = [
                        'Dubai', 'European', 'BMW PGA', 'Irish Open',
                        'Scottish Open', 'Italian Open', 'Spanish Open',
                        'DP World', 'Nedbank', 'Alfred Dunhill',
                        'Qatar', 'Bahrain', 'Australian', 'Mauritius'
                    ]

                    is_dpwt = any(ind.lower() in tournament_name.lower() for ind in dpwt_indicators)

                    # Position
                    pos_cell = cells[1] if len(cells) > 1 else None
                    position_text = pos_cell.get_text(strip=True) if pos_cell else ""

                    # Score/total
                    score_cell = cells[2] if len(cells) > 2 else None
                    score_text = score_cell.get_text(strip=True) if score_cell else ""

                    # Parse position
                    position = parse_position(position_text)

                    # Only include if it looks like a valid result
                    if tournament_name and position is not None:
                        results.append({
                            "tournament": tournament_name,
                            "position": position,
                            "position_text": position_text,
                            "score": score_text,
                            "is_dpwt": is_dpwt,
                        })

                except Exception as e:
                    continue

    return results


def parse_position(pos_text: str) -> Optional[int]:
    """Parse position text to numeric value."""
    if not pos_text:
        return None

    pos_text = pos_text.strip().upper()

    # Handle ties (T5 -> 5)
    if pos_text.startswith('T'):
        pos_text = pos_text[1:]

    # Handle missed cuts, withdrawals
    if pos_text in ['CUT', 'MC', 'MDF', 'WD', 'W/D', 'DQ', '-']:
        return 70  # Treat as missed cut

    try:
        return int(pos_text)
    except ValueError:
        return None


def calculate_form_from_results(results: List[Dict], max_events: int = 5) -> Dict[str, float]:
    """
    Calculate form metrics from tournament results.

    Args:
        results: List of tournament result dicts
        max_events: Maximum recent events to consider

    Returns:
        Dict with form metrics
    """
    if not results:
        return {}

    # Use most recent results (already in order)
    recent = results[:max_events]

    form = {}

    # Count finishes
    positions = [r['position'] for r in recent if r['position'] is not None]

    if positions:
        # Recent performance metrics
        form['dpwt_events_played'] = len(positions)
        form['dpwt_avg_finish'] = sum(positions) / len(positions)
        form['dpwt_best_finish'] = min(positions)

        # Top 10s, Top 5s
        top10s = sum(1 for p in positions if p <= 10)
        top5s = sum(1 for p in positions if p <= 5)
        wins = sum(1 for p in positions if p == 1)
        cuts_made = sum(1 for p in positions if p < 70)

        form['dpwt_recent_top10s'] = top10s
        form['dpwt_recent_top5s'] = top5s
        form['dpwt_recent_wins'] = wins
        form['dpwt_recent_cuts_made'] = cuts_made
        form['dpwt_cuts_pct'] = cuts_made / len(positions) if positions else 0

        # Estimate form score (0-100)
        # Based on average finish and top 10 rate
        avg_finish = form['dpwt_avg_finish']
        top10_rate = top10s / len(positions)

        if avg_finish <= 10:
            form['dpwt_form_score'] = 80 + (10 - avg_finish) * 2
        elif avg_finish <= 25:
            form['dpwt_form_score'] = 60 + (25 - avg_finish)
        elif avg_finish <= 50:
            form['dpwt_form_score'] = 40 + (50 - avg_finish) * 0.8
        else:
            form['dpwt_form_score'] = max(20, 40 - (avg_finish - 50) * 0.4)

        # Boost for top 10s
        form['dpwt_form_score'] += top10_rate * 10

        # Estimate SG:Total from average finish
        # Roughly: Top 10 avg ≈ +1.5 SG, Top 25 ≈ +0.5 SG, etc.
        if avg_finish <= 5:
            form['dpwt_estimated_sg_total'] = 2.0 - (avg_finish - 1) * 0.2
        elif avg_finish <= 10:
            form['dpwt_estimated_sg_total'] = 1.2 - (avg_finish - 5) * 0.15
        elif avg_finish <= 25:
            form['dpwt_estimated_sg_total'] = 0.45 - (avg_finish - 10) * 0.05
        elif avg_finish <= 50:
            form['dpwt_estimated_sg_total'] = -0.3 - (avg_finish - 25) * 0.02
        else:
            form['dpwt_estimated_sg_total'] = -0.8

        # Hot hand detection
        if len(positions) >= 2 and positions[0] <= 10 and positions[1] <= 15:
            form['dpwt_hot_hand'] = 1
        else:
            form['dpwt_hot_hand'] = 0

        # Momentum (improving or declining)
        if len(positions) >= 3:
            recent_avg = sum(positions[:2]) / 2
            older_avg = sum(positions[2:min(4, len(positions))]) / len(positions[2:min(4, len(positions))])
            form['dpwt_momentum'] = older_avg - recent_avg  # Positive = improving

    return form


# =============================================================================
# DPWT API Functions
# =============================================================================

def fetch_dpwt_api_results(dpwt_player_id: int, year: int = 2026) -> Optional[List[Dict]]:
    """
    Fetch tournament results from the DP World Tour API.

    Args:
        dpwt_player_id: DP World Tour player ID (not PGA ID)
        year: Season year

    Returns:
        List of tournament results or None if failed
    """
    url = f"{DPWT_API_BASE}{DPWT_RESULTS_ENDPOINT.format(player_id=dpwt_player_id, season=year)}"

    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        data = response.json()

        # Parse results from API response
        results = []

        # The API returns tournament results in a list
        # Each result has tournament info and position
        tournaments = data if isinstance(data, list) else data.get('results', data.get('tournaments', []))

        for t in tournaments:
            # Handle various API response formats
            tournament_name = t.get('tournament', t.get('tournamentName', t.get('name', '')))
            position = t.get('position', t.get('pos', t.get('finish')))

            # Parse position if it's a string
            if isinstance(position, str):
                position = parse_position(position)

            if tournament_name and position is not None:
                results.append({
                    'tournament': tournament_name,
                    'position': position,
                    'score': t.get('score', t.get('total', '')),
                    'is_dpwt': True,
                    'date': t.get('date', t.get('endDate', ''))
                })

        return results if results else None

    except requests.exceptions.RequestException as e:
        print(f"  DPWT API error: {e}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  DPWT API parse error: {e}")
        return None


def get_dpwt_form_from_api(pga_player_id: int, year: int = 2026) -> Optional[Dict]:
    """
    Get form data by fetching from DPWT API.

    Args:
        pga_player_id: PGA Tour player ID
        year: Season year

    Returns:
        Dict with form metrics or None
    """
    # Get DPWT player ID from mapping
    dpwt_id = PGA_TO_DPWT_IDS.get(pga_player_id)

    if not dpwt_id:
        return None

    results = fetch_dpwt_api_results(dpwt_id, year)

    if not results:
        return None

    form = calculate_form_from_results(results)

    if form:
        form['pga_player_id'] = pga_player_id
        form['dpwt_player_id'] = dpwt_id
        form['season'] = year
        form['source'] = 'dpwt_api'
        form['events'] = [r['tournament'] for r in results]

    return form


# =============================================================================
# Local Data Functions
# =============================================================================

def load_dpwt_results_file(year: int = 2026) -> Dict:
    """Load manually curated DPWT results from JSON file."""
    results_file = REFERENCE_DIR / f"dpwt_results_{year}.json"

    if results_file.exists():
        with open(results_file) as f:
            return json.load(f)

    return {"players": {}}


def save_dpwt_results_file(data: Dict, year: int = 2026) -> None:
    """Save DPWT results to JSON file."""
    results_file = REFERENCE_DIR / f"dpwt_results_{year}.json"
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    # Update metadata
    data['metadata'] = {
        'source': 'ESPN/DP World Tour',
        'last_updated': datetime.now().strftime('%Y-%m-%d'),
        'season': year
    }

    with open(results_file, 'w') as f:
        json.dump(data, f, indent=2)


def update_local_from_api(pga_player_ids: List[int], year: int = 2026) -> int:
    """
    Update local DPWT results file by fetching from API.

    Args:
        pga_player_ids: List of PGA Tour player IDs to update
        year: Season year

    Returns:
        Number of players successfully updated
    """
    data = load_dpwt_results_file(year)
    players = data.get('players', {})
    updated = 0

    for pga_id in pga_player_ids:
        dpwt_id = PGA_TO_DPWT_IDS.get(pga_id)
        if not dpwt_id:
            continue

        results = fetch_dpwt_api_results(dpwt_id, year)

        if results:
            # Convert to storage format
            stored_results = []
            for r in results:
                stored_results.append({
                    'tournament': r['tournament'],
                    'position': r['position'],
                    'score': r.get('score', ''),
                    'date': r.get('date', '')
                })

            # Get player name from existing data or API
            player_name = players.get(str(pga_id), {}).get('name', f'Player {pga_id}')

            players[str(pga_id)] = {
                'name': player_name,
                'pga_id': pga_id,
                'dpwt_id': dpwt_id,
                'results': stored_results
            }
            updated += 1

        time.sleep(REQUEST_DELAY)

    data['players'] = players
    save_dpwt_results_file(data, year)

    return updated


def get_form_from_local_data(pga_player_id: int, year: int = 2026) -> Optional[Dict]:
    """Get form data from local DPWT results file."""
    data = load_dpwt_results_file(year)
    players = data.get("players", {})

    player_data = players.get(str(pga_player_id))

    if not player_data or not player_data.get("results"):
        return None

    # Convert results to expected format
    results = []
    for r in player_data["results"]:
        results.append({
            "tournament": r.get("tournament", ""),
            "position": r.get("position"),
            "score": r.get("score"),
            "is_dpwt": True
        })

    form = calculate_form_from_results(results)

    if form:
        form['pga_player_id'] = pga_player_id
        form['player_name'] = player_data.get("name", "")
        form['season'] = year
        form['source'] = 'dpwt_manual'
        form['events'] = [r["tournament"] for r in results]

    return form


# =============================================================================
# Main Functions
# =============================================================================

def fetch_player_dpwt_form(pga_player_id: int, year: int = 2026) -> Optional[Dict]:
    """
    Fetch DPWT form data for a single player.

    Tries sources in order:
    1. Local data file (manually curated - most reliable)
    2. DPWT API (official API - may be blocked by CDN)

    Args:
        pga_player_id: PGA Tour player ID
        year: Season year

    Returns:
        Dict with form metrics or None
    """
    # 1. Try local data first (most reliable)
    form = get_form_from_local_data(pga_player_id, year)
    if form:
        return form

    # 2. Try DPWT API (may be blocked)
    form = get_dpwt_form_from_api(pga_player_id, year)
    if form:
        return form

    return None


# =============================================================================
# DPWT Stats API Functions
# =============================================================================

def _normalize_stat_type(stat_type: str) -> str:
    if not stat_type:
        return "strokes-gained-total"
    key = stat_type.strip().lower().replace(" ", "-").replace("_", "-")
    return STAT_TYPE_ALIASES.get(key, key)


def _parse_stat_types(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return [_normalize_stat_type(p) for p in parts]


def _stat_type_candidates(stat_type: str) -> List[str]:
    base = _normalize_stat_type(stat_type)
    candidates = STAT_TYPE_FALLBACKS.get(base, [base])
    # Ensure base first and unique order
    out = []
    for c in [base] + candidates:
        if c not in out:
            out.append(c)
    return out


def fetch_dpwt_stats(year: int, stat_type: str, headers: Optional[Dict[str, str]] = None, debug: bool = False) -> Optional[Dict]:
    """Fetch DPWT stats leaderboard for a season/stat type."""
    stat_type = _normalize_stat_type(stat_type)
    url = DPWT_API_BASE + DPWT_STATS_BY_SEASON.format(season=year, stat_type=stat_type)
    try:
        merged = REQUEST_HEADERS.copy()
        if headers:
            merged.update(headers)
        response = requests.get(url, headers=merged, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            if debug:
                snippet = response.text[:200].replace("\n", " ")
                print(f"  Non-JSON response for {stat_type}: {snippet}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching DPWT stats: {e}")
        return None


def parse_dpwt_stats(data: Dict, year: int, stat_type: str) -> pd.DataFrame:
    """Parse DPWT stats JSON into DataFrame."""
    if not data or "statsData" not in data:
        return pd.DataFrame()
    rows = []
    for r in data.get("statsData", []):
        first = r.get("firstName", "")
        last = r.get("lastName", "")
        rows.append({
            "year": year,
            "stat_type": _normalize_stat_type(stat_type),
            "player_id": r.get("id"),
            "player_name": f"{first} {last}".strip(),
            "rank": r.get("rank"),
            "country": r.get("country"),
            "average": r.get("average"),
            "total_rounds": r.get("totalRounds"),
        })
    return pd.DataFrame(rows)


def fetch_stats_for_field(
    field_path: Path,
    year: int = 2026,
    only_missing: bool = True
) -> pd.DataFrame:
    """
    Fetch DPWT form data for players in a PGA Tour field.

    Args:
        field_path: Path to field CSV
        year: Season year
        only_missing: Only fetch for players without PGA Tour stats

    Returns:
        DataFrame with form data
    """
    field_df = pd.read_csv(field_path)

    if 'player_id' not in field_df.columns:
        raise ValueError("Field CSV must have player_id column")

    id_mapping = load_player_id_mapping()
    pga_ids = field_df['player_id'].tolist()

    # Filter to players without PGA 2026 stats if requested
    if only_missing:
        pga_stats_path = HISTORICAL_DIR / f"tournament_stats_{year}.csv"
        if pga_stats_path.exists():
            pga_stats = pd.read_csv(pga_stats_path)
            players_with_stats = set(pga_stats['player_id'].unique())
            pga_ids = [p for p in pga_ids if p not in players_with_stats]
            print(f"  {len(pga_ids)} players missing PGA {year} stats")

    # Filter to players we have ESPN mappings for
    pga_ids = [p for p in pga_ids if p in id_mapping]
    print(f"  {len(pga_ids)} players have ESPN ID mappings")

    results = []

    for pga_id in pga_ids:
        # Get player name from field
        player_row = field_df[field_df['player_id'] == pga_id]
        player_name = player_row['player_name'].iloc[0] if len(player_row) > 0 else f"ID:{pga_id}"

        print(f"  Fetching: {player_name} (PGA ID {pga_id})...", end=" ")

        form = fetch_player_dpwt_form(pga_id, year)

        if form:
            form['player_name'] = player_name
            results.append(form)
            print(f"✓ avg_finish={form.get('dpwt_avg_finish', 'N/A'):.1f}, "
                  f"top10s={form.get('dpwt_recent_top10s', 0)}")
        else:
            print("✗ no results")

        time.sleep(REQUEST_DELAY)

    return pd.DataFrame(results) if results else pd.DataFrame()


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fetch DP World Tour form data from ESPN"
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        default=2026,
        help="Season year (default: 2026)"
    )
    parser.add_argument(
        "--field", "-f",
        type=str,
        help="Path to field CSV"
    )
    parser.add_argument(
        "--player-id", "-p",
        type=int,
        help="Single PGA Tour player ID"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output CSV path"
    )
    parser.add_argument(
        "--all-players",
        action="store_true",
        help="Fetch all mapped players, not just missing"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh local data from DPWT API for all mapped players"
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Only use API, skip local data file"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Fetch DPWT leaderboard stats for a stat type and exit"
    )
    parser.add_argument(
        "--stat-type",
        type=str,
        default="strokes-gained-total",
        help="DPWT stat type (e.g., strokes-gained-total, sg_total)"
    )
    parser.add_argument(
        "--stat-types",
        type=str,
        default="",
        help="Comma-separated stat types to fetch (batch mode)"
    )
    parser.add_argument(
        "--all-stats",
        action="store_true",
        help="Fetch a default set of stat types"
    )
    parser.add_argument(
        "--cookie",
        type=str,
        default="",
        help="Cookie header from browser (optional, for 403 issues)"
    )
    parser.add_argument(
        "--headers-json",
        type=str,
        default="",
        help="Path to JSON file with headers to use (optional)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print non-JSON response snippets for failing stat types"
    )

    args = parser.parse_args()

    if args.stats:
        extra_headers = {}
        if args.headers_json:
            try:
                with open(args.headers_json) as f:
                    extra_headers.update(json.load(f))
            except Exception as e:
                raise SystemExit(f"Failed to read headers JSON: {e}")
        if args.cookie:
            extra_headers["Cookie"] = args.cookie

        stat_types = []
        if args.all_stats:
            stat_types = DEFAULT_STAT_TYPES.copy()
        if args.stat_types:
            stat_types.extend(_parse_stat_types(args.stat_types))
        if not stat_types:
            stat_types = [_normalize_stat_type(args.stat_type)]

        for st in stat_types:
            candidates = _stat_type_candidates(st)
            data = None
            used_slug = None
            for slug in candidates:
                data = fetch_dpwt_stats(args.year, slug, headers=extra_headers, debug=args.debug)
                if data and data.get("statsData"):
                    used_slug = slug
                    break

            if not data or not data.get("statsData"):
                print(f"✗ No data returned for {st}")
                continue

            df = parse_dpwt_stats(data, args.year, used_slug or st)
            if df.empty:
                print(f"✗ Empty response for {st}")
                continue

            if args.output and len(stat_types) == 1:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(out_path, index=False)
                print(f"✓ Saved DPWT stats: {out_path}")
            else:
                save_dpwt_stats(df, args.year, used_slug or st)
        return

    print(f"\n{'='*60}")
    print(f"  DP WORLD TOUR FORM SCRAPER")
    print(f"  Season: {args.year}")
    print(f"{'='*60}\n")

    # Handle --refresh: update local data from API
    if args.refresh:
        print("Refreshing local data from DPWT API...\n")
        pga_ids = list(PGA_TO_DPWT_IDS.keys())
        print(f"  Updating {len(pga_ids)} players...")

        updated = update_local_from_api(pga_ids, args.year)
        print(f"\n✓ Updated {updated} players in local data file")
        return

    if args.player_id:
        # Single player mode
        print(f"Fetching form for PGA player ID: {args.player_id}")
        result = fetch_player_dpwt_form(args.player_id, args.year)

        if result:
            print(f"\n✓ Form data found:")
            for k, v in result.items():
                if isinstance(v, float):
                    print(f"  {k}: {v:.2f}")
                else:
                    print(f"  {k}: {v}")
        else:
            print("✗ No form data found")

    elif args.field:
        # Field mode
        field_path = Path(args.field)
        if not field_path.exists():
            print(f"Field file not found: {field_path}")
            sys.exit(1)

        print(f"Fetching form for field: {field_path.name}\n")

        results_df = fetch_stats_for_field(
            field_path,
            args.year,
            only_missing=not args.all_players
        )

        if not results_df.empty:
            output_path = Path(args.output) if args.output else HISTORICAL_DIR / f"dpwt_form_{args.year}.csv"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            results_df.to_csv(output_path, index=False)
            print(f"\n✓ Saved {len(results_df)} players to: {output_path}")

            # Summary
            print(f"\nSummary:")
            print(f"  Players with DPWT form: {len(results_df)}")
            if 'dpwt_avg_finish' in results_df.columns:
                print(f"  Avg finish: {results_df['dpwt_avg_finish'].mean():.1f}")
            if 'dpwt_estimated_sg_total' in results_df.columns:
                print(f"  Avg estimated SG: {results_df['dpwt_estimated_sg_total'].mean():.3f}")
        else:
            print("\n✗ No DPWT form data found")

    else:
        # Test mode - fetch a few known players
        print("Testing with known players...\n")

        test_players = [
            (28237, "Rory McIlroy"),
            (30911, "Tommy Fleetwood"),
        ]

        for pga_id, name in test_players:
            print(f"Fetching: {name}...", end=" ")
            form = fetch_player_dpwt_form(pga_id, args.year)

            if form:
                print(f"✓ avg_finish={form.get('dpwt_avg_finish', 'N/A'):.1f}, "
                      f"est_sg={form.get('dpwt_estimated_sg_total', 'N/A'):.2f}")
            else:
                print("✗")

            time.sleep(REQUEST_DELAY)


if __name__ == "__main__":
    main()
