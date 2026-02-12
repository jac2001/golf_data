#!/usr/bin/env python3
"""
Fetch Tournament Field from PGA TOUR (GraphQL)
=============================================

Uses the official PGA TOUR GraphQL leaderboard to pull the tournament field
with player IDs and basic metadata.

Usage (single event):
    python scripts/scrapers/fetch_field_from_pgatour.py \
        --pga-id R2026004 \
        --output data/fields/farmers_2026.csv

Usage (batch from schedule CSV):
    python scripts/scrapers/fetch_field_from_pgatour.py \
        --schedule data/schedule/upcoming_events.csv \
        --days 14 \
        --output-dir data/fields

Schedule CSV columns (minimal):
    pga_id,slug,start_date
        pga_id: PGA TOUR tournamentId (e.g., R2026004)
        slug: used to name the output file (e.g., farmers_2026)
        start_date: YYYY-MM-DD (filters by --days window)
"""

import argparse
import pandas as pd
import re
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

def build_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

SESSION = build_session()

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

FIELD_QUERY = """
query TournamentField($id: ID!) {
  field(id: $id) {
    tournamentName
    id
    lastUpdated
    players {
      id
      firstName
      lastName
      displayName
      country
      qualifier
      owgr
      status
      withdrawn
      alternate
    }
  }
}
"""

DEFAULT_OUTPUT_DIR = Path("data/fields")


def parse_r_id(rid: str):
    """Split RYYYYNNN into (year, event)."""
    m = re.match(r"R(\d{4})(\d{3})", rid)
    if not m:
        return None, None
    year = m.group(1)
    event = m.group(2)
    return year, event


# 1️⃣ ADD: slugify helper
def slugify_tournament_name(name: str) -> str:
    """
    Convert tournament name to PGA TOUR slug.
    Example: 'Farmers Insurance Open' -> 'farmers-insurance-open'
    """
    import re

    slug = name.lower()
    slug = slug.replace("&", "and")
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    return slug.strip("-")


def extract_field_rows_from_next_data(html: str) -> list:
    """
    Extract Field table rows (PLAYER, RANK, OWGR, HOW THEY QUALIFIED)
    from PGA TOUR Next.js (__NEXT_DATA__) state.
    """
    import json
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    print('Souped HTML:', soup.title.string if soup.title else 'No title found')
    next_data = soup.find("script", id="__NEXT_DATA__")
    if not next_data or not next_data.string:
        return []

    try:
        data = json.loads(next_data.string)
        print('Loaded JSON data from __NEXT_DATA__')
        print('Data keys:', list(data.keys()))
    except Exception:
        return []

    # Navigate Next.js / React Query cache
    props = data.get("props", {})
    page_props = props.get("pageProps", {})
    dehydrated = page_props.get("dehydratedState", {})
    queries = dehydrated.get("queries", [])
    print('Number of queries found:', len(queries))
    print('Sample query data:', queries[0] if queries else 'No queries available')

    # We are NOT looking for leaderboard.players
    # We are looking for the FIELD table backing data
    for q in queries:
        qdata = q.get("state", {}).get("data")
        # Field table data is an array of rows with displayName + qualification
        if isinstance(qdata, dict) and "field" in qdata:
            return qdata["field"]

        # Alternate shape (seen on some events)
        if isinstance(qdata, dict) and "players" in qdata and "howTheyQualified" in str(qdata):
            return qdata["players"]

    # Fallback: some events only expose a list of player IDs under 'players'
    for q in queries:
        qdata = q.get("state", {}).get("data")
        players = None
        if isinstance(qdata, dict) and "players" in qdata and isinstance(qdata["players"], list):
            players = qdata["players"]
        if players and all(isinstance(p, (int, str)) for p in players):
            # Wrap into field-like dicts with only id; names can be mapped later
            return [{"id": int(p)} for p in players if str(p).isdigit()]

    return []


def fetch_field_from_html(year: str, slug: str, pga_id: str) -> Optional[pd.DataFrame]:
    headers = {"User-Agent": "Mozilla/5.0"}

    urls = [
        f"https://www.pgatour.com/tournaments/{year}/{slug}/{pga_id}",
        f"https://www.pgatour.com/tournaments/{year}/{slug}/{pga_id}",
    ]

    field_rows = []

    for url in urls:
        print(f"Fetching HTML page: {url}")
        try:
            resp = SESSION.get(url, headers=headers, timeout=30)
            print(f"  HTTP {resp.status_code}")
            resp.raise_for_status()
        except Exception as e:
            print(f"⚠️ HTML fetch failed: {e}")
            continue

        field_rows = extract_field_rows_from_next_data(resp.text)
        print(f"  Extracted {len(field_rows)} field rows from HTML")
        if field_rows:
            print("✓ Found field rows from Next.js data")
            break

    if not field_rows:
        print("❌ No field rows found in HTML (__NEXT_DATA__)")
        return None

    rows = []
    for r in field_rows:
        pid = r.get("id", "")
        name = (
            r.get("displayName")
            or f"{r.get('firstName','')} {r.get('lastName','')}".strip()
        )
        # Some fallback rows only have id (from players list)
        if not name and pid:
            name = f"Player {pid}"
        if not name:
            continue

        rows.append({
            "player_id": pid,
            "player_name": name,
            "rank": r.get("rank", ""),
            "owgr": r.get("owgr", ""),
            "how_qualified": r.get("howTheyQualified", ""),
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=["player_id", "player_name"])
    print(f"✓ Parsed {len(df)} field rows (player_id / name)")
    return df


def fetch_statdata_field(tournament_id: str) -> Optional[pd.DataFrame]:
    """
    Fallback to statdata.pgatour.com field.json, which often opens earlier than GraphQL.
    URL pattern: https://statdata.pgatour.com/r/<year>/<event>/field.json
    """
    year, event = parse_r_id(tournament_id)
    if not year or not event:
        print("❌ Could not parse tournament id for statdata fallback")
        return None
    url = f"https://statdata.pgatour.com/r/{year}/{event}/field.json"
    alt_url = url.replace("https://", "http://")
    print(f"Trying statdata field: {url}")
    try:
        resp = SESSION.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        if "NameResolutionError" in str(e):
            try:
                resp = SESSION.get(
                    alt_url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=20
                )
                resp.raise_for_status()
            except Exception as e2:
                print(f"⚠️ statdata fallback failed on alt_url: {e2}")
                return None
        else:
            print(f"⚠️ statdata fallback failed: {e}")
            return None
    except Exception as e:
        print(f"⚠️ statdata fallback failed: {e}")
        return None
    try:
        js = resp.json()
        players = js.get("Players") or js.get("players") or js.get("field") or []
        rows = []
        for p in players:
            pid = p.get("pid") or p.get("PlayerID") or p.get("playerId")
            if not pid:
                continue
            fn = p.get("fn") or p.get("FirstName") or ""
            ln = p.get("ln") or p.get("LastName") or ""
            name = (fn + " " + ln).strip() or p.get("name") or str(pid)
            country = p.get("ct") or p.get("country", "")
            rows.append({
                "player_id": int(pid),
                "player_name": name,
                "country": country,
                "owgr": p.get("owgr", ""),
                "how_qualified": "",
                "status": "",
            })
        if not rows:
            print("❌ statdata field had no players")
            return None
        df = pd.DataFrame(rows).drop_duplicates(subset=["player_id"])
        print(f"✓ Found {len(df)} players via statdata")
        return df
    except Exception as e:
        print(f"⚠️ statdata fallback failed parsing JSON: {e}")
        return None


from typing import Optional

def fetch_graphql(query: str, variables: dict) -> Optional[dict]:
    payload = {"query": query, "variables": variables}
    try:
        resp = SESSION.post(
            GRAPHQL_URL,
            headers=DEFAULT_HEADERS,
            json=payload,
            timeout=30
        )

        if resp.status_code != 200:
            print(f"❌ GraphQL HTTP {resp.status_code}")
            return None

        try:
            return resp.json()
        except Exception as e:
            print(f"❌ GraphQL response was not JSON: {e}")
            return None

    except requests.RequestException as e:
        print(f"❌ GraphQL request failed: {e}")
        return None


def fetch_field_from_graphql(tournament_id: str) -> Optional[pd.DataFrame]:
    """
    Fetch official tournament FIELD via PGA TOUR GraphQL.
    This is the same data backing the /field page.
    """
    print(f"Fetching FIELD via GraphQL... {tournament_id}")

    data = fetch_graphql(FIELD_QUERY, {"id": tournament_id})
    print("GraphQL data received:", data)

    if not data or not isinstance(data, dict):
        print("❌ GraphQL returned no usable data")
        return None

    graphql_data = data.get("data")
    if graphql_data is None:
        print(f"❌ GraphQL returned errors: {data.get('errors')}")
        return None

    field = graphql_data.get("field")

    if not field or not field.get("players"):
        print("❌ No FIELD data returned from GraphQL")
        return None

    rows = []
    for p in field["players"]:
        rows.append({
            "player_id": int(p["id"]),
            "player_name": p.get("displayName")
                or f"{p.get('firstName','')} {p.get('lastName','')}",
            "country": p.get("country"),
            "owgr": p.get("owgr"),
            "how_qualified": p.get("qualifier"),
            "status": p.get("status"),
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=["player_id"])
    print(f"✓ Found {len(df)} FIELD players via GraphQL")
    return df

def load_field_from_odds(odds_csv: Path) -> Optional[pd.DataFrame]:
    """Fallback: build field from existing odds CSV."""
    if not odds_csv.exists():
        return None
    try:
        df = pd.read_csv(odds_csv)
        if "player_id" not in df.columns or "player_name" not in df.columns:
            return None
        field = df[["player_id", "player_name"]].drop_duplicates()
        print(f"✓ Loaded field for {len(field)} players from odds cache {odds_csv.name}")
        return field
    except Exception as e:
        print(f"⚠️ Could not load odds cache {odds_csv}: {e}")
        return None




def match_players_to_database(field_df, master_data_path: Path) -> pd.DataFrame:
    """Match player names to IDs from historical master data (best effort)."""
    print("\nMatching players to historical database...")
    master_df = pd.read_csv(master_data_path)
    player_map = master_df[["player_id", "player_name"]].drop_duplicates()

    def clean(name: str) -> str:
        if pd.isna(name):
            return ""
        return re.sub(r"[^\w\s]", "", str(name).upper()).strip()

    player_map["name_clean"] = player_map["player_name"].apply(clean)
    field_df["name_clean"] = field_df["player_name"].apply(clean)

    matched = field_df.merge(player_map[["player_id", "name_clean"]], on="name_clean", how="left")

    # Handle overlapping column names (player_id_x / player_id_y)
    if "player_id_x" in matched.columns and "player_id_y" in matched.columns:
        matched["player_id"] = matched["player_id_x"].fillna(matched["player_id_y"])
    elif "player_id_x" in matched.columns:
        matched.rename(columns={"player_id_x": "player_id"}, inplace=True)
    elif "player_id_y" in matched.columns:
        matched.rename(columns={"player_id_y": "player_id"}, inplace=True)

    matched_count = matched["player_id"].notna().sum() if "player_id" in matched.columns else 0
    print(f"  Matched {matched_count}/{len(field_df)} players")
    unmatched = matched[matched["player_id"].isna()]["player_name"].tolist()
    if unmatched:
        print(f"  Unmatched: {len(unmatched)}")
    return matched[["player_id", "player_name"]]


def validate_field_df(field_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure field has required columns and clean ids/names."""
    required = {"player_id", "player_name"}
    if not required.issubset(field_df.columns):
        missing = required - set(field_df.columns)
        raise ValueError(f"Field data missing required columns: {missing}")

    df = field_df.copy()
    df = df[df["player_id"].notna()].copy()
    df["player_id"] = df["player_id"].astype(int)
    df["player_name"] = df["player_name"].fillna("").astype(str).str.strip()

    placeholder_count = df["player_name"].str.match(r"Player\\s+\\d+", na=False).sum()
    if placeholder_count > 0:
        print(f"⚠️ Field has {placeholder_count} placeholder names; consider name enrichment.")

    return df


def process_single_event(pga_id: str, tournament_name: str, output: Path, match_ids: bool, odds_csv: Path = None):
    # Infer year from PGA ID (RYYYYNNN)
    year, _ = parse_r_id(pga_id)
    if not year:
        print("❌ Could not infer year from PGA ID")
        return

    # Always use tournament_name for slug
    slug = slugify_tournament_name(tournament_name)
    print(f"Using slug: {slug}")

    # 1️⃣ PRIMARY: HTML Field Page
    # 1️⃣ PRIMARY: GraphQL FIELD (authoritative)
    field_df = fetch_field_from_graphql(pga_id)

    # 2️⃣ FALLBACK: HTML (__NEXT_DATA__)
    if field_df is None:
        field_df = fetch_field_from_html(year, slug, pga_id)

    # 3️⃣ FALLBACK: statdata
    if field_df is None:
        field_df = fetch_statdata_field(pga_id)

    # 4️⃣ FALLBACK: odds cache
    if field_df is None:
        cache_path = odds_csv or Path(f"data/odds/pga_odds_{pga_id}.csv")
        field_df = load_field_from_odds(cache_path)

    if field_df is None:
        print("❌ Could not build field from any source")
        return

    # Validate and normalize field
    try:
        field_df = validate_field_df(field_df)
    except Exception as e:
        print(f"❌ Field validation failed: {e}")
        return

    if match_ids:
        master_path = Path("data/processed/master_training_data_2020_2025.csv")
        if master_path.exists():
            field_df = match_players_to_database(field_df, master_path)
        else:
            print(f"⚠️ Master data not found at {master_path}, skipping ID matching")

    output.parent.mkdir(parents=True, exist_ok=True)
    field_df.to_csv(output, index=False)
    print(f"Saved {len(field_df)} players to {output}")

    # ALWAYS save a copy with tournament ID naming convention
    # This ensures predict_tournament.py can find the correct field file
    canonical_output = output.parent / f"field_{pga_id}.csv"
    if canonical_output != output:
        field_df.to_csv(canonical_output, index=False)
        print(f"✓ Also saved canonical field file: {canonical_output.name}")


def main():
    parser = argparse.ArgumentParser(description="Fetch tournament field from PGA TOUR")
    parser.add_argument("--pga-id", help="PGA TOUR tournament ID (e.g., R2026004)")
    parser.add_argument("--output", help="Output CSV file path")
    parser.add_argument("--schedule", help="CSV with upcoming events (pga_id, name, start_date)")
    parser.add_argument("--days", type=int, default=10, help="Look-ahead window (days) when using --schedule")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output dir for schedule mode")
    parser.add_argument("--match-ids", action="store_true", help="Match player names to historical IDs")
    parser.add_argument("--odds-csv", help="Optional odds CSV to use as fallback field source")
    parser.add_argument("--name", help="Tournament name (used to build slug)")
    args = parser.parse_args()

    print("=" * 70)
    print("  PGA TOUR FIELD SCRAPER")
    print("=" * 70)

    # Schedule (batch) mode
    if args.schedule:
        schedule_path = Path(args.schedule)
        if not schedule_path.exists():
            print(f"❌ Schedule file not found: {schedule_path}")
            return
        sched_df = pd.read_csv(schedule_path)
        required = {"pga_id", "name", "start_date"}
        if not required.issubset(sched_df.columns):
            print(f"❌ Schedule CSV must include columns: {required}")
            return
        cutoff = datetime.now().date() + timedelta(days=args.days)
        upcoming = sched_df[sched_df["start_date"].apply(lambda d: pd.to_datetime(d).date()) <= cutoff]
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for _, row in upcoming.iterrows():
            pga_id = str(row["pga_id"])
            tournament_name = row["name"]
            slug = slugify_tournament_name(tournament_name)
            start_date = pd.to_datetime(row["start_date"]).date().isoformat()

            print("\n" + "-" * 60)
            print(f"Event: {tournament_name} ({pga_id}) starting {start_date}")
            # Use tournament ID as the canonical filename
            outfile = out_dir / f"field_{pga_id}.csv"

            process_single_event(
                pga_id,
                tournament_name,
                outfile,
                args.match_ids,
                Path(args.odds_csv) if args.odds_csv else None
            )
        return

    # Single-event mode requires both pga-id and output and name
    if not args.pga_id or not args.output:
        parser.error("Either provide --schedule or both --pga-id and --output.")
    if not args.name:
        parser.error("--name is required for single-event mode")

    process_single_event(
        args.pga_id,
        args.name,
        Path(args.output),
        args.match_ids,
        Path(args.odds_csv) if args.odds_csv else None
    )


if __name__ == "__main__":
    main()
