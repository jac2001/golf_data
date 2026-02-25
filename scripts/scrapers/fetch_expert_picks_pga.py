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
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.tournament_context import (
    resolve_tournament_context as resolve_shared_tournament_context,
    tournament_name_match as shared_tournament_name_match,
)

DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "expert_picks"
SCHEDULE_PATH = DATA_DIR / "raw" / "schedule_2026.csv"

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


def _normalize_name(value: str) -> str:
    if not value:
        return ""
    s = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    return re.sub(r"\s+", " ", s)


def _name_tokens(value: str) -> set:
    s = _normalize_name(value)
    if not s:
        return set()
    stop = {
        "the", "and", "of", "at", "in", "to", "open", "championship",
        "classic", "invitational", "pro", "am", "presented", "by",
    }
    return {t for t in s.split() if t and t not in stop}


def _tournament_name_match(actual: str, expected: str) -> bool:
    return shared_tournament_name_match(actual, expected)


def _resolve_tournament_context(tournament_id: Optional[str]) -> Dict[str, str]:
    """
    Resolve expected tournament metadata from schedule by tournament_id.
    Returns keys: tournament_name, power_slug, start_date (may be empty strings).
    """
    if not tournament_id:
        return {"tournament_name": "", "power_slug": "", "start_date": ""}
    row = resolve_shared_tournament_context(
        tournament_id=str(tournament_id).strip().upper(),
        schedule_path=SCHEDULE_PATH,
    )
    return {
        "tournament_name": str(row.get("tournament_name", "")).strip(),
        "power_slug": str(row.get("power_slug", "")).strip(),
        "start_date": str(row.get("start_date", "")).strip(),
    }


def _extract_ep_paths(html: str) -> List[str]:
    ep_paths = re.findall(r'/content/dam[^"\']*ep-table/ep-table[^"\']*', html)
    if not ep_paths:
        ep_paths = re.findall(r'/content/dam[^"\']*ep-table[^"\']*', html)
    # ordered unique
    seen = set()
    out = []
    for p in ep_paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _extract_article_links_from_listing(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    article_links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if not href:
            continue
        if "expert-picks" not in href:
            continue
        if href.startswith("/"):
            href = f"https://www.pgatour.com{href}"
        if href.startswith("https://www.pgatour.com/"):
            article_links.append(href)
    # keep likely target rows first
    article_links = [u for u in article_links if "/article/news/expert-picks/" in u]
    return list(dict.fromkeys(article_links))


def discover_expert_picks_path(tournament_id: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Auto-discover the expert picks ep-table path from PGA Tour.

    Returns:
        Tuple of (ep_table_path, article_url) or (None, None) if not found
    """
    context = _resolve_tournament_context(tournament_id)
    expected_name = context.get("tournament_name", "")
    expected_slug = context.get("power_slug", "")

    # First, find expert picks article candidates.
    print("  Discovering expert picks article...")
    if tournament_id and expected_name:
        print(f"  Target tournament: {expected_name} ({tournament_id})")

    # Try the expert picks landing page
    listing_url = "https://www.pgatour.com/news/expert-picks"
    try:
        resp = requests.get(listing_url, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml"
        }, timeout=15)
        resp.raise_for_status()

        article_links = _extract_article_links_from_listing(resp.text)

        # Prioritize URLs that look like the target tournament.
        if expected_slug:
            slug_hint = expected_slug.lower().replace("_", "-")
            scored = []
            for u in article_links:
                score = 0
                ul = u.lower()
                if slug_hint and slug_hint in ul:
                    score += 3
                if "who-are-experts-picking" in ul:
                    score += 1
                scored.append((score, u))
            article_links = [u for _, u in sorted(scored, key=lambda x: x[0], reverse=True)]

        for article_url in article_links[:12]:
            print(f"  Checking article: {article_url}")
            try:
                resp2 = requests.get(article_url, headers={
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept": "text/html,application/xhtml+xml"
                }, timeout=15)
                resp2.raise_for_status()
            except Exception:
                continue

            ep_paths = _extract_ep_paths(resp2.text)
            if not ep_paths:
                continue

            # Validate discovered path against requested tournament when available.
            for ep_path in ep_paths:
                try:
                    data = fetch_expert_picks(ep_path)
                    table = data.get("data", {}).get("getExpertPicksTable", {})
                    rows = table.get("expertPicksTableRows", []) or []
                    found_tournament = str(table.get("tournamentName", "")).strip()
                    if not rows:
                        continue
                    if expected_name:
                        if not _tournament_name_match(found_tournament, expected_name):
                            continue
                    print(f"  Found ep-table path: {ep_path}")
                    return ep_path, article_url
                except Exception:
                    continue

    except Exception as e:
        print(f"  Warning: Could not discover from listing: {e}")

    # Fallback: probe date-based ep-table paths.
    # If tournament start date is known, anchor probes around that week; otherwise use today.
    base_dt = datetime.now()
    if context.get("start_date"):
        try:
            base_dt = datetime.strptime(context["start_date"], "%Y-%m-%d")
        except Exception:
            pass

    probe_dates = []
    for delta in range(-10, 11):
        probe_dates.append(base_dt + timedelta(days=delta))

    for check_date in probe_dates:
        try:
            test_path = (
                f"/content/dam/pga-tour/fragments/tours/pga-tour/news/expert-picks/"
                f"{check_date.year}/{check_date.month:02d}/{check_date.day:02d}/ep-table/ep-table"
            )
            data = fetch_expert_picks(test_path)
            table = data.get("data", {}).get("getExpertPicksTable", {})
            rows = table.get("expertPicksTableRows", []) or []
            found_tournament = str(table.get("tournamentName", "")).strip()
            if rows and (not expected_name or _tournament_name_match(found_tournament, expected_name)):
                print(f"  Found via date probe: {test_path}")
                return test_path, None
        except Exception:
            continue

    if expected_name:
        print("  Could not find expert picks matching requested tournament.")
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

    # Final safety check: never write mismatched tournament picks for a requested ID.
    if args.tournament_id:
        context = _resolve_tournament_context(args.tournament_id)
        expected_name = context.get("tournament_name", "")
        found_name = str(df["tournament_name"].iloc[0]).strip() if "tournament_name" in df.columns and not df.empty else ""
        if expected_name and found_name and not _tournament_name_match(found_name, expected_name):
            raise SystemExit(
                "ERROR: Expert picks tournament mismatch.\n"
                f"  Requested: {args.tournament_id} ({expected_name})\n"
                f"  Found: {found_name}\n"
                "  Refusing to save mismatched picks."
            )

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
