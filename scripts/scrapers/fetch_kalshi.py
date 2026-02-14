#!/usr/bin/env python3
"""
Kalshi Golf Odds Scraper
========================

Fetches golf betting odds from Kalshi prediction markets.
Converts prediction market probabilities to American odds.

Usage:
    python fetch_kalshi.py                    # Auto-find golf events
    python fetch_kalshi.py --event ATPBP26    # Specific event
    python fetch_kalshi.py --list             # List available events
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ODDS_DIR = DATA_DIR / "odds"

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"


def prob_to_american(prob: float) -> int:
    """Convert probability to American odds."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return int(-100 * prob / (1 - prob))
    else:
        return int(100 * (1 - prob) / prob)


def fetch_golf_events() -> List[Dict]:
    """Fetch all golf-related events from Kalshi."""
    url = f"{KALSHI_API}/events"
    headers = {"accept": "application/json"}

    golf_events = []
    cursor = None

    # Golf series tickers to look for
    golf_series = ["KXPGATOUR", "KXPGA", "KXLPGATOUR", "KXPGAMAJORWIN"]

    for series in golf_series:
        try:
            params = {"series_ticker": series, "status": "open", "limit": 50}
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            events = data.get("events", [])

            for event in events:
                # Check if event has active markets
                event_ticker = event.get("event_ticker", "")
                markets_url = f"{KALSHI_API}/markets"
                markets_resp = requests.get(
                    markets_url,
                    params={"event_ticker": event_ticker, "limit": 5},
                    headers=headers,
                    timeout=10
                )
                if markets_resp.status_code == 200:
                    markets_data = markets_resp.json()
                    market_count = len(markets_data.get("markets", []))
                    if market_count > 0:
                        event["market_count"] = market_count
                        event["series"] = series
                        golf_events.append(event)
        except Exception as e:
            print(f"  Error fetching {series}: {e}")
            continue

    return golf_events


def fetch_event_markets(event_ticker: str) -> List[Dict]:
    """Fetch all markets for a specific event."""
    url = f"{KALSHI_API}/markets"
    headers = {"accept": "application/json"}

    all_markets = []
    cursor = None

    while True:
        params = {"event_ticker": event_ticker, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        markets = data.get("markets", [])
        all_markets.extend(markets)

        cursor = data.get("cursor")
        if not cursor or not markets:
            break

    return all_markets


def parse_markets_to_odds(markets: List[Dict], event_name: str = "") -> pd.DataFrame:
    """Convert Kalshi markets to odds format."""
    rows = []

    for market in markets:
        # Get player name from yes_sub_title or parse from title
        player_name = market.get("yes_sub_title", "")
        if not player_name:
            title = market.get("title", "")
            match = re.search(r"Will (.+?) win", title, re.IGNORECASE)
            if match:
                player_name = match.group(1).strip()
            else:
                continue

        # Get probability from yes_ask (in cents, 0-100)
        yes_ask = market.get("yes_ask", 0)
        yes_bid = market.get("yes_bid", 0)

        # Use midpoint of bid/ask or just ask
        if yes_bid > 0:
            win_prob = (yes_ask + yes_bid) / 2 / 100
        else:
            win_prob = yes_ask / 100

        if win_prob <= 0:
            continue

        # Convert to American odds
        american_odds = prob_to_american(win_prob)

        rows.append({
            "player_name": player_name,
            "win_prob": win_prob,
            "odds_kalshi": american_odds,
            "odds_consensus": american_odds,
            "odds_best": american_odds,
            "odds_worst": american_odds,
            "implied_prob_consensus": win_prob,
            "num_books": 1,
            "odds_spread": 0,
            "value_spread_pct": 0,
            "event_name": event_name,
            "source": "kalshi",
            "market_ticker": market.get("ticker", ""),
            "volume": market.get("volume", 0),
            "liquidity": market.get("liquidity", 0),
            "yes_ask": yes_ask,
            "yes_bid": yes_bid,
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("win_prob", ascending=False)
        df["rank"] = range(1, len(df) + 1)

        # Reorder columns
        priority_cols = ["rank", "player_name", "odds_kalshi", "win_prob", "implied_prob_consensus"]
        other_cols = [c for c in df.columns if c not in priority_cols]
        df = df[priority_cols + other_cols]

    return df


def main():
    parser = argparse.ArgumentParser(description="Fetch golf odds from Kalshi")
    parser.add_argument("--event", help="Event ticker (e.g., 'KXPGATOUR-ATPBP26')")
    parser.add_argument("--list", action="store_true", help="List available golf events")
    parser.add_argument("--output", help="Output CSV path")
    args = parser.parse_args()

    ODDS_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching from Kalshi...")

    # List events mode
    if args.list:
        events = fetch_golf_events()
        print(f"\nFound {len(events)} golf events:")
        for e in events:
            print(f"  {e.get('title', e.get('event_ticker'))}")
            print(f"    Ticker: {e.get('event_ticker')}")
            print(f"    Markets: {e.get('market_count', '?')} players")
        return

    # Find event
    if args.event:
        event_ticker = args.event
        event_name = event_ticker
    else:
        # Auto-find most relevant event
        events = fetch_golf_events()
        if not events:
            print("No golf events found on Kalshi")
            return

        # Pick the first active event
        event_ticker = events[0].get("event_ticker")
        event_name = events[0].get("title", event_ticker)
        print(f"  Auto-selected: {event_name}")

    # Fetch markets
    print(f"  Fetching markets for: {event_ticker}")

    try:
        markets = fetch_event_markets(event_ticker)
    except Exception as e:
        print(f"  Error fetching markets: {e}")
        return

    print(f"  Found {len(markets)} player markets")

    # Parse to odds format
    df = parse_markets_to_odds(markets, event_name)

    if df.empty:
        print("  No odds data parsed")
        return

    print(f"\n✓ Processed {len(df)} players from Kalshi")

    # Display top players
    print("\nTop 20 favorites:")
    print(f"{'Rank':<5} {'Player':<25} {'Odds':<10} {'Win Prob':<10}")
    print("-" * 55)
    for _, row in df.head(20).iterrows():
        odds_str = f"+{row['odds_kalshi']}" if row['odds_kalshi'] > 0 else str(row['odds_kalshi'])
        print(f"{row['rank']:<5} {row['player_name'][:24]:<25} {odds_str:<10} {row['win_prob']*100:.1f}%")

    # Save
    if args.output:
        out_path = Path(args.output)
    else:
        slug = event_ticker.lower().replace("-", "_")
        out_path = ODDS_DIR / f"kalshi_{slug}.csv"

    df.to_csv(out_path, index=False)
    print(f"\n✓ Saved to {out_path}")


if __name__ == "__main__":
    main()
