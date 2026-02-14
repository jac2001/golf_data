#!/usr/bin/env python3
"""
Polymarket Golf Odds Scraper
=============================

Fetches golf betting odds from Polymarket prediction markets.
Converts prediction market probabilities to American odds.

Usage:
    python fetch_polymarket.py                    # Auto-find golf events
    python fetch_polymarket.py --event masters    # Specific event
    python fetch_polymarket.py --list             # List available events
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ODDS_DIR = DATA_DIR / "odds"

POLYMARKET_API = "https://gamma-api.polymarket.com"


def prob_to_american(prob: float) -> int:
    """Convert probability to American odds."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return int(-100 * prob / (1 - prob))
    else:
        return int(100 * (1 - prob) / prob)


def fetch_golf_events() -> List[Dict]:
    """Fetch all golf-related events from Polymarket."""
    url = f"{POLYMARKET_API}/events"
    golf_events = []
    seen_slugs = set()

    # Known golf event slug patterns to try directly
    known_golf_slugs = [
        "the-masters-winner",
        "2026-att-pebble-beach-pro-am-winner",
        "2026-pga-championship-winner",
        "2026-us-open-golf-winner",
        "2026-the-open-championship-winner",
        "2025-att-pebble-beach-pro-am-winner",
        "pga-championship-winner",
        "us-open-golf-winner",
        "the-open-championship-winner",
    ]

    # Try known slugs first
    for slug in known_golf_slugs:
        try:
            params = {"slug": slug}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                events = resp.json()
                for event in events:
                    event_slug = event.get("slug", "")
                    if event_slug and event_slug not in seen_slugs:
                        markets = event.get("markets", [])
                        if len(markets) > 10:  # Real golf events have many markets
                            seen_slugs.add(event_slug)
                            golf_events.append(event)
        except Exception:
            continue

    # Also scan recent events for golf keywords
    try:
        params = {"closed": "false", "limit": 200}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        events = resp.json()

        golf_keywords = ["golf", "pga tour", "masters", "pebble", "open championship",
                         "british open", "ryder cup", "lpga"]
        exclude_terms = ["nhl", "nba", "nfl", "fifa", "mlb", "hockey", "basketball", "football", "vct"]

        for event in events:
            slug = event.get("slug", "")
            if slug in seen_slugs:
                continue

            title = event.get("title", "").lower()
            if any(kw in title for kw in golf_keywords):
                if not any(ex in title for ex in exclude_terms):
                    markets = event.get("markets", [])
                    if len(markets) > 10:
                        seen_slugs.add(slug)
                        golf_events.append(event)
    except Exception:
        pass

    return golf_events


def fetch_event_markets(event_slug: str) -> List[Dict]:
    """Fetch all markets for a specific event."""
    url = f"{POLYMARKET_API}/events/{event_slug}"

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    event = resp.json()

    return event.get("markets", [])


def parse_markets_to_odds(markets: List[Dict], event_name: str = "") -> pd.DataFrame:
    """
    Convert Polymarket markets to odds format.

    Each market is "Will X win the tournament?" with Yes/No prices.
    """
    rows = []

    for market in markets:
        question = market.get("question", "")

        # Extract player name from question
        # Format: "Will [Player Name] win the [Tournament]?"
        match = re.search(r"Will (.+?) win", question, re.IGNORECASE)
        if not match:
            continue

        player_name = match.group(1).strip()

        # Get probability (first price is Yes probability)
        prices_raw = market.get("outcomePrices", "[]")
        # Handle both string JSON and list formats
        if isinstance(prices_raw, str):
            try:
                prices = json.loads(prices_raw)
            except json.JSONDecodeError:
                continue
        else:
            prices = prices_raw

        if not prices:
            continue

        try:
            win_prob = float(prices[0])
        except (ValueError, IndexError):
            continue

        if win_prob <= 0:
            continue

        # Convert to American odds
        american_odds = prob_to_american(win_prob)

        rows.append({
            "player_name": player_name,
            "win_prob": win_prob,
            "odds_polymarket": american_odds,
            "odds_consensus": american_odds,
            "odds_best": american_odds,
            "odds_worst": american_odds,
            "implied_prob_consensus": win_prob,
            "num_books": 1,
            "odds_spread": 0,
            "value_spread_pct": 0,
            "event_name": event_name,
            "source": "polymarket",
            "market_id": market.get("id", ""),
            "volume": market.get("volume", 0),
            "liquidity": market.get("liquidityClob", 0),
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("win_prob", ascending=False)
        df["rank"] = range(1, len(df) + 1)

        # Reorder columns
        priority_cols = ["rank", "player_name", "odds_polymarket", "win_prob", "implied_prob_consensus"]
        other_cols = [c for c in df.columns if c not in priority_cols]
        df = df[priority_cols + other_cols]

    return df


def main():
    parser = argparse.ArgumentParser(description="Fetch golf odds from Polymarket")
    parser.add_argument("--event", help="Event slug (e.g., 'the-masters-winner')")
    parser.add_argument("--list", action="store_true", help="List available golf events")
    parser.add_argument("--tournament-id", help="Tournament ID for output naming")
    parser.add_argument("--output", help="Output CSV path")
    args = parser.parse_args()

    ODDS_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching from Polymarket...")

    # List events mode
    if args.list:
        events = fetch_golf_events()
        print(f"\nFound {len(events)} golf events:")
        for e in events:
            markets = e.get("markets", [])
            print(f"  {e.get('title')}")
            print(f"    Slug: {e.get('slug')}")
            print(f"    Markets: {len(markets)} players")
        return

    # Find event
    if args.event:
        event_slug = args.event
    else:
        # Auto-find most relevant event
        events = fetch_golf_events()
        if not events:
            print("No golf events found on Polymarket")
            return

        # Pick the one with most markets (likely current/upcoming)
        events.sort(key=lambda e: len(e.get("markets", [])), reverse=True)
        event_slug = events[0].get("slug")
        print(f"  Auto-selected: {events[0].get('title')}")

    # Fetch markets
    print(f"  Fetching markets for: {event_slug}")

    try:
        # Get event details
        url = f"{POLYMARKET_API}/events?slug={event_slug}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        events = resp.json()

        if not events:
            print(f"  Event not found: {event_slug}")
            return

        event = events[0]
        event_name = event.get("title", event_slug)
        markets = event.get("markets", [])

    except Exception as e:
        print(f"  Error fetching event: {e}")
        return

    print(f"  Found {len(markets)} player markets")

    # Parse to odds format
    df = parse_markets_to_odds(markets, event_name)

    if df.empty:
        print("  No odds data parsed")
        return

    print(f"\n✓ Processed {len(df)} players from Polymarket")

    # Display top players
    print("\nTop 20 favorites:")
    print(f"{'Rank':<5} {'Player':<25} {'Odds':<10} {'Win Prob':<10}")
    print("-" * 55)
    for _, row in df.head(20).iterrows():
        odds_str = f"+{row['odds_polymarket']}" if row['odds_polymarket'] > 0 else str(row['odds_polymarket'])
        print(f"{row['rank']:<5} {row['player_name'][:24]:<25} {odds_str:<10} {row['win_prob']*100:.1f}%")

    # Save
    if args.output:
        out_path = Path(args.output)
    elif args.tournament_id:
        out_path = ODDS_DIR / f"polymarket_odds_{args.tournament_id}.csv"
    else:
        slug = event_slug.replace("-", "_")
        out_path = ODDS_DIR / f"polymarket_{slug}.csv"

    df.to_csv(out_path, index=False)
    print(f"\n✓ Saved to {out_path}")

    # Also save as multi_book_odds_latest for dashboard
    latest_path = ODDS_DIR / "multi_book_odds_latest.csv"
    df.to_csv(latest_path, index=False)
    print(f"✓ Also saved as {latest_path.name}")


if __name__ == "__main__":
    main()
