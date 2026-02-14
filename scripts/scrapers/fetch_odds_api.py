#!/usr/bin/env python3
"""
Multi-Sportsbook Golf Odds Scraper
===================================

Fetches golf betting odds from multiple sources:

1. The Odds API (free tier) - MAJORS ONLY
   - Masters, PGA Championship, US Open, The Open
   - 5+ sportsbooks: DraftKings, FanDuel, BetMGM, etc.

2. DraftKings Direct Scraper - ALL PGA EVENTS
   - Regular PGA Tour events (weekly tournaments)
   - Futures and tournament winner markets

Setup for Odds API:
1. Get free API key at https://the-odds-api.com/
2. Set environment variable: export ODDS_API_KEY="your_key_here"
   Or create file: data/odds/.odds_api_key

Usage:
    # For MAJORS (multi-book via Odds API):
    python fetch_odds_api.py --sport-key golf_masters_tournament_winner

    # For REGULAR PGA events (DraftKings):
    python fetch_odds_api.py --draftkings

    # List available events:
    python fetch_odds_api.py --list-events
"""

import argparse
import json
import os
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ODDS_DIR = DATA_DIR / "odds"

# The Odds API configuration
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "golf_pga_championship"  # PGA Tour events

# US Sportsbooks to include (regional availability varies)
US_BOOKMAKERS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "caesars",
    "pointsbetus",
    "betrivers",
    "unibet_us",
    "bovada",
    "betonlineag",
    "lowvig",
    "mybookieag",
]


def get_api_key() -> str:
    """Get API key from environment or file."""
    # Try environment variable first
    key = os.environ.get("ODDS_API_KEY")
    if key:
        return key

    # Try file
    key_file = ODDS_DIR / ".odds_api_key"
    if key_file.exists():
        return key_file.read_text().strip()

    raise ValueError(
        "No API key found. Set ODDS_API_KEY environment variable or "
        f"create {key_file} with your key from https://the-odds-api.com/"
    )


def get_available_events(api_key: str) -> List[Dict]:
    """Get list of available golf events."""
    # The Odds API uses different sport keys for different events
    sport_keys = [
        "golf_pga_championship",  # PGA Championship
        "golf_us_open",
        "golf_the_open_championship",
        "golf_masters_tournament",
        "golf_pga",  # General PGA Tour
    ]

    all_events = []

    for sport_key in sport_keys:
        url = f"{ODDS_API_BASE}/sports/{sport_key}/events"
        params = {"apiKey": api_key}

        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                events = resp.json()
                for event in events:
                    event["sport_key"] = sport_key
                    all_events.append(event)
        except Exception:
            continue

    return all_events


def fetch_odds(api_key: str, sport_key: str = "golf_pga", event_id: Optional[str] = None) -> Dict:
    """
    Fetch odds from The Odds API.

    Returns odds from all available US sportsbooks.
    """
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"

    params = {
        "apiKey": api_key,
        "regions": "us",  # US sportsbooks
        "markets": "outrights",  # Tournament winner market
        "oddsFormat": "american",
    }

    if event_id:
        params["eventIds"] = event_id

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    # Check remaining quota
    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")
    print(f"  API quota: {remaining} remaining ({used} used this month)")

    return resp.json()


def american_to_prob(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def parse_odds_data(data: List[Dict]) -> pd.DataFrame:
    """
    Parse odds data into a structured DataFrame.

    Returns one row per player with:
    - Odds from each sportsbook
    - Consensus (average) odds
    - Best odds available
    - Implied probabilities
    """
    if not data:
        return pd.DataFrame()

    rows = []

    for event in data:
        event_name = event.get("sport_title", "PGA Tour")
        commence_time = event.get("commence_time", "")

        # Get outrights market
        bookmakers = event.get("bookmakers", [])

        # Collect all player odds
        player_odds: Dict[str, Dict[str, int]] = {}

        for book in bookmakers:
            book_key = book.get("key", "")
            book_name = book.get("title", book_key)

            for market in book.get("markets", []):
                if market.get("key") != "outrights":
                    continue

                for outcome in market.get("outcomes", []):
                    player_name = outcome.get("name", "")
                    odds = outcome.get("price", 0)

                    if player_name not in player_odds:
                        player_odds[player_name] = {}

                    player_odds[player_name][book_key] = odds

        # Build rows
        for player_name, books in player_odds.items():
            row = {
                "player_name": player_name,
                "event_name": event_name,
                "commence_time": commence_time,
                "num_books": len(books),
            }

            # Add each book's odds
            odds_values = []
            for book_key in US_BOOKMAKERS:
                col_name = f"odds_{book_key}"
                if book_key in books:
                    row[col_name] = books[book_key]
                    odds_values.append(books[book_key])
                else:
                    row[col_name] = None

            # Calculate consensus and best odds
            if odds_values:
                row["odds_best"] = max(odds_values)  # Best payout
                row["odds_worst"] = min(odds_values)
                row["odds_consensus"] = int(np.mean(odds_values))
                row["odds_spread"] = max(odds_values) - min(odds_values)

                # Implied probabilities
                row["implied_prob_best"] = american_to_prob(row["odds_best"])
                row["implied_prob_worst"] = american_to_prob(row["odds_worst"])
                row["implied_prob_consensus"] = american_to_prob(row["odds_consensus"])

                # Value indicator: spread as % of consensus
                if row["odds_consensus"] > 0:
                    row["value_spread_pct"] = row["odds_spread"] / row["odds_consensus"] * 100
                else:
                    row["value_spread_pct"] = 0

            rows.append(row)

    df = pd.DataFrame(rows)

    if not df.empty:
        # Sort by consensus probability (favorites first)
        df = df.sort_values("implied_prob_consensus", ascending=False)
        df["rank"] = range(1, len(df) + 1)

        # Reorder columns
        priority_cols = [
            "rank", "player_name", "odds_consensus", "odds_best", "odds_worst",
            "implied_prob_consensus", "num_books", "odds_spread", "value_spread_pct"
        ]
        other_cols = [c for c in df.columns if c not in priority_cols]
        df = df[priority_cols + other_cols]

    return df


def find_value_plays(df: pd.DataFrame, min_spread_pct: float = 10.0) -> pd.DataFrame:
    """
    Find players with significant odds variation across books.

    These represent potential value opportunities where one book
    has significantly better odds than others.
    """
    if df.empty:
        return df

    value_df = df[df["value_spread_pct"] >= min_spread_pct].copy()
    value_df = value_df.sort_values("value_spread_pct", ascending=False)

    return value_df


# ============================================================================
# DraftKings Direct Scraper (for regular PGA events)
# ============================================================================

def fetch_draftkings_golf_odds() -> pd.DataFrame:
    """
    Fetch golf odds directly from DraftKings Sportsbook.

    Works for regular PGA Tour events (not just majors).
    """
    print("  Fetching from DraftKings Sportsbook...")

    # DraftKings API endpoint for golf
    dk_url = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/88808"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    try:
        resp = requests.get(dk_url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Error fetching DraftKings: {e}")
        # Try alternate endpoint
        try:
            alt_url = "https://sportsbook.draftkings.com/api/odds/v1/leagues/88808/offers/gamelines"
            resp = requests.get(alt_url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e2:
            print(f"  Alternate endpoint also failed: {e2}")
            return pd.DataFrame()

    rows = []
    events = data.get("events", []) or data.get("eventGroup", {}).get("events", [])

    for event in events:
        event_name = event.get("name", "")

        # Look for outright/winner markets
        for market in event.get("offers", []) or event.get("displayGroups", []):
            market_name = market.get("label", "") or market.get("name", "")

            if "winner" not in market_name.lower() and "outright" not in market_name.lower():
                continue

            outcomes = market.get("outcomes", [])
            for outcome in outcomes:
                player_name = outcome.get("label", "") or outcome.get("name", "")
                odds = outcome.get("oddsAmerican", "") or outcome.get("odds", "")

                if not player_name or not odds:
                    continue

                try:
                    odds_numeric = int(str(odds).replace("+", ""))
                except:
                    continue

                rows.append({
                    "player_name": player_name,
                    "event_name": event_name,
                    "odds_draftkings": odds_numeric,
                    "odds_consensus": odds_numeric,
                    "odds_best": odds_numeric,
                    "odds_worst": odds_numeric,
                    "implied_prob_consensus": american_to_prob(odds_numeric),
                    "num_books": 1,
                    "odds_spread": 0,
                    "value_spread_pct": 0,
                    "source": "draftkings",
                })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("implied_prob_consensus", ascending=False)
        df["rank"] = range(1, len(df) + 1)

    return df


def load_manual_odds(csv_path: str = None) -> pd.DataFrame:
    """
    Load manually entered multi-book odds from CSV.

    CSV format (from OddsChecker):
    player_name,odds_draftkings,odds_fanduel,odds_betmgm,odds_caesars,odds_pointsbet

    Usage:
    1. Go to https://www.oddschecker.com/golf/pebble-beach/winner
    2. Copy odds for each player from each book
    3. Save to data/odds/multi_book_manual.csv
    4. Run: python fetch_odds_api.py --manual
    """
    if csv_path:
        path = Path(csv_path)
    else:
        path = ODDS_DIR / "multi_book_manual.csv"

    if not path.exists():
        print(f"  Manual odds file not found: {path}")
        print(f"  Create it from OddsChecker data or use template: {ODDS_DIR / 'multi_book_template.csv'}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    print(f"  Loaded {len(df)} players from {path.name}")

    # Find odds columns
    odds_cols = [c for c in df.columns if c.startswith("odds_") and c != "odds_consensus"]

    if not odds_cols:
        print("  No odds columns found (expected: odds_draftkings, odds_fanduel, etc.)")
        return df

    rows = []
    for _, row in df.iterrows():
        odds_values = []
        for col in odds_cols:
            val = row.get(col)
            if pd.notna(val):
                # Parse odds string like "+300" or "300"
                try:
                    odds_num = int(str(val).replace("+", "").replace("-", ""))
                    if str(val).startswith("-"):
                        odds_num = -odds_num
                    odds_values.append(odds_num)
                except:
                    pass

        if odds_values:
            new_row = {
                "player_name": row["player_name"],
                "odds_consensus": int(np.mean(odds_values)),
                "odds_best": max(odds_values),
                "odds_worst": min(odds_values),
                "odds_spread": max(odds_values) - min(odds_values),
                "num_books": len(odds_values),
                "implied_prob_consensus": american_to_prob(int(np.mean(odds_values))),
                "source": "manual_oddschecker",
            }

            # Add individual book odds
            for col in odds_cols:
                val = row.get(col)
                if pd.notna(val):
                    try:
                        new_row[col] = int(str(val).replace("+", ""))
                    except:
                        pass

            # Value spread percentage
            if new_row["odds_consensus"] > 0:
                new_row["value_spread_pct"] = new_row["odds_spread"] / new_row["odds_consensus"] * 100
            else:
                new_row["value_spread_pct"] = 0

            rows.append(new_row)

    result_df = pd.DataFrame(rows)

    if not result_df.empty:
        result_df = result_df.sort_values("implied_prob_consensus", ascending=False)
        result_df["rank"] = range(1, len(result_df) + 1)

    return result_df


def fetch_espn_odds() -> pd.DataFrame:
    """
    Fetch golf odds from ESPN (aggregates multiple books).
    """
    print("  Fetching from ESPN...")

    espn_url = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/odds"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    try:
        resp = requests.get(espn_url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Error fetching ESPN: {e}")
        return pd.DataFrame()

    rows = []

    # ESPN structure varies, try to parse
    items = data.get("items", []) or data.get("events", [])
    for item in items:
        competitions = item.get("competitions", [])
        for comp in competitions:
            odds_list = comp.get("odds", [])
            for odds_item in odds_list:
                player = odds_item.get("athlete", {}).get("displayName", "")
                odds_val = odds_item.get("value", 0)

                if player and odds_val:
                    rows.append({
                        "player_name": player,
                        "odds_consensus": int(odds_val),
                        "implied_prob_consensus": american_to_prob(int(odds_val)),
                        "num_books": 1,
                        "source": "espn",
                    })

    return pd.DataFrame(rows)


def merge_with_pga_odds(multi_book_df: pd.DataFrame, tournament_id: str) -> pd.DataFrame:
    """
    Merge multi-book odds with existing PGA Tour odds data.

    This combines our single-source PGA odds with multi-book consensus.
    """
    pga_odds_file = ODDS_DIR / f"pga_odds_{tournament_id}.csv"

    if not pga_odds_file.exists():
        print(f"  No PGA odds file found: {pga_odds_file}")
        return multi_book_df

    pga_df = pd.read_csv(pga_odds_file)

    # Normalize names for matching
    def normalize_name(name):
        return name.lower().strip().replace(".", "").replace("-", " ")

    multi_book_df["name_normalized"] = multi_book_df["player_name"].apply(normalize_name)
    pga_df["name_normalized"] = pga_df["player_name"].apply(normalize_name)

    # Merge
    merged = pd.merge(
        pga_df,
        multi_book_df[["name_normalized", "odds_consensus", "odds_best", "odds_worst",
                       "implied_prob_consensus", "num_books", "odds_spread", "value_spread_pct"]],
        on="name_normalized",
        how="left",
        suffixes=("_pga", "_multi")
    )

    merged = merged.drop(columns=["name_normalized"])

    return merged


def main():
    parser = argparse.ArgumentParser(description="Fetch golf odds from multiple sportsbooks")
    parser.add_argument("--tournament-id", help="Tournament ID (e.g., R2026005)")
    parser.add_argument("--list-events", action="store_true", help="List available events")
    parser.add_argument("--sport-key", help="Sport key for The Odds API (majors only)")
    parser.add_argument("--draftkings", action="store_true", help="Fetch from DraftKings (all PGA events)")
    parser.add_argument("--manual", action="store_true", help="Load manual odds from CSV (from OddsChecker)")
    parser.add_argument("--manual-file", help="Path to manual odds CSV")
    parser.add_argument("--output", help="Output CSV path")
    parser.add_argument("--merge-pga", action="store_true", help="Merge with PGA Tour odds")
    args = parser.parse_args()

    ODDS_DIR.mkdir(parents=True, exist_ok=True)

    # DraftKings mode (for regular PGA events)
    if args.draftkings:
        print("\nFetching from DraftKings Sportsbook...")
        df = fetch_draftkings_golf_odds()

        if df.empty:
            print("No odds data from DraftKings")
            return

        print(f"\n✓ Found odds for {len(df)} players")

        # Show top players
        print("\nTop 15 favorites:")
        display_cols = ["rank", "player_name", "odds_draftkings", "implied_prob_consensus"]
        display_cols = [c for c in display_cols if c in df.columns]
        print(df[display_cols].head(15).to_string(index=False))

        # Save
        if args.output:
            out_path = Path(args.output)
        elif args.tournament_id:
            out_path = ODDS_DIR / f"draftkings_odds_{args.tournament_id}.csv"
        else:
            out_path = ODDS_DIR / "draftkings_odds_latest.csv"

        df.to_csv(out_path, index=False)
        print(f"\n✓ Saved to {out_path}")

        # Also save as multi_book_latest for dashboard compatibility
        df.to_csv(ODDS_DIR / "multi_book_odds_latest.csv", index=False)
        return

    # Manual mode (from OddsChecker CSV)
    if args.manual:
        print("\nLoading manual multi-book odds...")
        df = load_manual_odds(args.manual_file)

        if df.empty:
            print("\nTo use manual mode:")
            print("1. Go to https://www.oddschecker.com/golf/pebble-beach/winner")
            print("2. Copy odds into: data/odds/multi_book_manual.csv")
            print("   Format: player_name,odds_draftkings,odds_fanduel,odds_betmgm,...")
            print(f"3. Or use template: {ODDS_DIR / 'multi_book_template.csv'}")
            return

        print(f"\n✓ Processed {len(df)} players from {df['num_books'].max()} sportsbooks")

        # Show results
        print("\nTop 15 by consensus odds:")
        display_cols = ["rank", "player_name", "odds_consensus", "odds_best", "odds_worst", "num_books", "value_spread_pct"]
        display_cols = [c for c in display_cols if c in df.columns]
        print(df[display_cols].head(15).to_string(index=False))

        # Value plays
        value_df = df[df["value_spread_pct"] >= 10].sort_values("value_spread_pct", ascending=False)
        if not value_df.empty:
            print(f"\n⚡ Line Shopping Value (>10% spread):")
            print(value_df[["player_name", "odds_best", "odds_worst", "value_spread_pct"]].head(10).to_string(index=False))

        # Save
        if args.output:
            out_path = Path(args.output)
        elif args.tournament_id:
            out_path = ODDS_DIR / f"multi_book_odds_{args.tournament_id}.csv"
        else:
            out_path = ODDS_DIR / "multi_book_odds_latest.csv"

        df.to_csv(out_path, index=False)
        print(f"\n✓ Saved to {out_path}")
        return

    # Get API key
    try:
        api_key = get_api_key()
        print(f"✓ API key loaded")
    except ValueError as e:
        print(f"ERROR: {e}")
        return

    # List events mode
    if args.list_events:
        print("\nAvailable golf events (Odds API - Majors Only):")
        print("  - golf_masters_tournament_winner: Masters")
        print("  - golf_pga_championship_winner: PGA Championship")
        print("  - golf_us_open_winner: US Open")
        print("  - golf_the_open_championship_winner: The Open")
        print("\nFor regular PGA events, use: --draftkings")
        return

    # Default sport key if not provided
    sport_key = args.sport_key or "golf_masters_tournament_winner"

    # Fetch odds
    print(f"\nFetching odds from The Odds API...")
    print(f"  Sport: {sport_key}")
    print("  Note: Free tier only has majors. Use --draftkings for regular events.")

    try:
        data = fetch_odds(api_key, sport_key=sport_key)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("ERROR: Invalid API key")
        elif e.response.status_code == 429:
            print("ERROR: API quota exceeded")
        else:
            print(f"ERROR: {e}")
        return

    if not data:
        print("No odds data available for this event")
        return

    # Parse odds
    df = parse_odds_data(data)

    if df.empty:
        print("No odds data parsed")
        return

    print(f"\n✓ Found odds for {len(df)} players from {df['num_books'].max()} sportsbooks")

    # Show top players
    print("\nTop 10 by consensus odds:")
    display_cols = ["rank", "player_name", "odds_consensus", "odds_best", "implied_prob_consensus", "num_books"]
    print(df[display_cols].head(10).to_string(index=False))

    # Show value plays
    value_df = find_value_plays(df, min_spread_pct=15)
    if not value_df.empty:
        print(f"\n⚡ Value Plays (>15% odds spread across books):")
        print(value_df[["rank", "player_name", "odds_best", "odds_worst", "odds_spread", "value_spread_pct"]].head(10).to_string(index=False))

    # Merge with PGA odds if requested
    if args.merge_pga and args.tournament_id:
        df = merge_with_pga_odds(df, args.tournament_id)
        print(f"\n✓ Merged with PGA Tour odds")

    # Save output
    if args.output:
        out_path = Path(args.output)
    elif args.tournament_id:
        out_path = ODDS_DIR / f"multi_book_odds_{args.tournament_id}.csv"
    else:
        out_path = ODDS_DIR / "multi_book_odds_latest.csv"

    df.to_csv(out_path, index=False)
    print(f"\n✓ Saved to {out_path}")

    # Also save as latest
    latest_path = ODDS_DIR / "multi_book_odds_latest.csv"
    if out_path != latest_path:
        df.to_csv(latest_path, index=False)


if __name__ == "__main__":
    main()
