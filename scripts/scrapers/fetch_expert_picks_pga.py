#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

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


def _find_json_ld(html: str) -> Optional[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string)
            if isinstance(data, dict) and data.get("@type") in {"NewsArticle", "Article"}:
                return data
        except Exception:
            continue
    return None


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
    tournament = table.get("tournamentName", "")
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
    parser.add_argument("--path", required=True, help="Content fragment path, e.g. /content/dam/.../ep-table")
    parser.add_argument("--url", help="Article URL (optional, for metadata)")
    parser.add_argument("--output", help="Output CSV path (optional)")
    args = parser.parse_args()

    data = fetch_expert_picks(args.path)
    df = parse_expert_picks(data, source_url=args.url)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.output:
        out_path = Path(args.output)
    else:
        slug = Path(args.path).name.replace("-", "_")
        out_path = OUTPUT_DIR / f"expert_picks_{slug}.csv"

    df.to_csv(out_path, index=False)
    print(f"✓ Saved expert picks → {out_path} ({len(df)} rows)")


if __name__ == "__main__":
    main()
