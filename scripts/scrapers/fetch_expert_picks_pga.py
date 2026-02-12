#!/usr/bin/env python3
"""
PGA Tour Expert Picks Scraper
=============================
Fetches expert picks from PGA Tour GraphQL API.

Can auto-discover the ep-table path or use a provided path.

Usage:
    python fetch_expert_picks_pga.py                          # Auto-discover latest
    python fetch_expert_picks_pga.py --tournament-id R2026005 # For specific tournament
    python fetch_expert_picks_pga.py --path /content/dam/...  # Manual path
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path("/Users/jacklegnon/Desktop/golf_data")
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "expert_picks"

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "x-pgat-platform": "web",
}

QUERY = """
query GetExpertPicksTable($path: String!) {
  getExpertPicksTable(path: $path) {
    tournamentName
    expertPicksTableRows {
      expertName
      expertTitle
      lineup { id firstName lastName countryFlag countryName headshot }
      winner { id firstName lastName countryFlag countryName headshot }
      comment {
        __typename
        ... on NewsArticleParagraph { segments { type value data } }
        ... on NewsArticleText { value }
        ... on NewsArticleLink { segments { type value data } }
        ... on NewsArticleLineBreak { breakValue }
        ... on NewsArticleImage { segments { type value data } }
      }
      percentSelected
      percentSelectedColor
    }
  }
}
"""


def discover_expert_picks_path(tournament_id: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Auto-discover the expert picks ep-table path from PGA Tour.

    Returns:
        Tuple of (ep_table_path, article_url) or (None, None) if not found
    """
    # First, find the latest expert picks article
    print("  Discovering expert picks article...")

    # Try the expert picks landing page
    listing_url = "https://www.pgatour.com/news/expert-picks"
    try:
        resp = requests.get(listing_url, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml"
        }, timeout=15)
        resp.raise_for_status()

        # Find article links
        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for article links containing "who-are-experts-picking"
        article_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "expert-picks" in href and "who-are-experts-picking" in href:
                if href.startswith("/"):
                    href = f"https://www.pgatour.com{href}"
                article_links.append(href)

        if not article_links:
            # Try finding any recent article link
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/article/news/expert-picks/" in href:
                    if href.startswith("/"):
                        href = f"https://www.pgatour.com{href}"
                    article_links.append(href)

        # Dedupe and take most recent (usually first)
        article_links = list(dict.fromkeys(article_links))

        if article_links:
            article_url = article_links[0]
            print(f"  Found article: {article_url}")

            # Now fetch the article and extract ep-table path
            resp2 = requests.get(article_url, headers={
                "User-Agent": HEADERS["User-Agent"],
                "Accept": "text/html,application/xhtml+xml"
            }, timeout=15)
            resp2.raise_for_status()

            # Find ep-table path in the HTML
            ep_paths = re.findall(r'/content/dam[^"\']*ep-table/ep-table[^"\']*', resp2.text)
            if not ep_paths:
                ep_paths = re.findall(r'/content/dam[^"\']*ep-table[^"\']*', resp2.text)

            if ep_paths:
                ep_path = ep_paths[0]
                print(f"  Found ep-table path: {ep_path}")
                return ep_path, article_url

    except Exception as e:
        print(f"  Warning: Could not discover from listing: {e}")

    # Fallback: Try to construct path based on current date
    today = datetime.now()
    base_path = f"/content/dam/pga-tour/fragments/tours/pga-tour/news/expert-picks/{today.year}/{today.month:02d}"

    # Try recent days
    for day_offset in range(0, 7):
        check_date = today.replace(day=today.day - day_offset) if today.day > day_offset else today
        try:
            test_path = f"{base_path}/{check_date.day:02d}/ep-table/ep-table"
            data = fetch_expert_picks(test_path)
            if data.get("data", {}).get("getExpertPicksTable", {}).get("expertPicksTableRows"):
                print(f"  Found via date probe: {test_path}")
                return test_path, None
        except Exception:
            continue

    return None, None


def _extract_comment(nodes: List[Dict]) -> str:
    parts: List[str] = []
    for node in nodes or []:
        t = node.get("__typename")
        if t in ("NewsArticleParagraph", "NewsArticleLink", "NewsArticleImage"):
            for seg in node.get("segments", []) or []:
                if seg.get("value"):
                    parts.append(seg["value"])
        elif t == "NewsArticleText" and node.get("value"):
            parts.append(node["value"])
        elif t == "NewsArticleLineBreak" and node.get("breakValue") is not None:
            parts.append("\n")
    return " ".join(parts).strip()


def _name_from_player(p: Optional[Dict]) -> str:
    if not p:
        return ""
    return f"{p.get('firstName','')} {p.get('lastName','')}".strip()


def _split_lineup(players: List[Dict], lineup_size: int = 4) -> Dict[str, List[Dict]]:
    lineup = players[:lineup_size]
    bench = players[lineup_size:] if len(players) > lineup_size else []
    return {"lineup": lineup, "bench": bench}


def fetch_expert_picks(path: str) -> Dict:
    payload = {
        "operationName": "GetExpertPicksTable",
        "query": QUERY,
        "variables": {"path": path},
    }
    resp = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data


def parse_expert_picks(data: Dict, source_url: Optional[str] = None) -> pd.DataFrame:
    table = data.get("data", {}).get("getExpertPicksTable", {})
    rows = table.get("expertPicksTableRows", [])
    tournament = table.get("tournamentName", "").strip()
    scraped_at = datetime.now(timezone.utc).isoformat()

    out_rows = []
    for row in rows:
        expert = row.get("expertName", "")
        title = row.get("expertTitle", "")
        lineup = row.get("lineup") or []
        split = _split_lineup(lineup, lineup_size=4)
        winner = row.get("winner")
        comment = _extract_comment(row.get("comment"))

        out_rows.append({
            "tournament_name": tournament,
            "expert_name": expert,
            "expert_title": title,
            "lineup_player_ids": json.dumps([p.get("id") for p in split["lineup"]]),
            "lineup_player_names": json.dumps([_name_from_player(p) for p in split["lineup"]]),
            "bench_player_ids": json.dumps([p.get("id") for p in split["bench"]]),
            "bench_player_names": json.dumps([_name_from_player(p) for p in split["bench"]]),
            "winner_id": winner.get("id") if winner else "",
            "winner_name": _name_from_player(winner),
            "percent_selected": row.get("percentSelected"),
            "percent_selected_color": row.get("percentSelectedColor"),
            "comment": comment,
            "source_url": source_url or "",
            "scraped_at": scraped_at,
        })

    return pd.DataFrame(out_rows)


def main():
    parser = argparse.ArgumentParser(description="Fetch PGA TOUR expert picks table (GraphQL)")
    parser.add_argument("--path", help="Content fragment path (auto-discovered if not provided)")
    parser.add_argument("--tournament-id", help="Tournament ID (e.g., R2026005) for naming output")
    parser.add_argument("--url", help="Article URL (optional, for metadata)")
    parser.add_argument("--output", help="Output CSV path (optional)")
    args = parser.parse_args()

    # Auto-discover path if not provided
    path = args.path
    article_url = args.url

    if not path:
        print("No --path provided, auto-discovering...")
        path, article_url = discover_expert_picks_path(args.tournament_id)
        if not path:
            print("ERROR: Could not discover expert picks path. Try providing --path manually.")
            return

    # Fetch and parse
    print(f"Fetching expert picks from: {path}")
    data = fetch_expert_picks(path)
    df = parse_expert_picks(data, source_url=article_url)

    if df.empty:
        print("WARNING: No expert picks found in response")
        return

    # Determine output path
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.output:
        out_path = Path(args.output)
    elif args.tournament_id:
        out_path = OUTPUT_DIR / f"expert_picks_{args.tournament_id}.csv"
    else:
        # Use tournament name from data
        tournament = df["tournament_name"].iloc[0] if not df.empty else "unknown"
        slug = re.sub(r'[^\w\s-]', '', tournament).strip().lower().replace(' ', '_')
        out_path = OUTPUT_DIR / f"expert_picks_{slug}.csv"

    df.to_csv(out_path, index=False)
    print(f"✓ Saved expert picks → {out_path} ({len(df)} rows)")

    # Also save as latest
    latest_path = OUTPUT_DIR / "expert_picks_latest.csv"
    df.to_csv(latest_path, index=False)
    print(f"✓ Also saved as → {latest_path.name}")


if __name__ == "__main__":
    main()
