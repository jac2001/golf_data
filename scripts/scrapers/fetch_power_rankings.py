#!/usr/bin/env python3
"""
Power Rankings Scraper (robust, cached)
--------------------------------------
- Uses a config file for fragment paths (no more copying from DevTools each time).
- Falls back to cached JSON and cached CSV if live fetch fails.
- Retries with backoff and fails soft (never exits non-zero in normal mode).

Config file (CSV): data/power_rankings/paths.csv
    columns: slug,pga_id,fragment_path
Example row:
    farmers_2026,R2026004,/content/dam/pga-tour/fragments/tours/pga-tour/news/power-rankings/2026/01/26/pr-folder/pr-table

Outputs:
    data/power_rankings/<slug>.csv
    data/power_rankings/cache/<slug>.json (raw GraphQL)

Usage:
    python scripts/scrapers/fetch_power_rankings.py --slug farmers_2026

If --slug is not provided, you can still pass --path directly for ad-hoc use.
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import pandas as pd
import requests
from datetime import datetime, timezone

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.6 Safari/605.1.15"
    ),
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "x-pgat-platform": "web",
}

QUERY = """
query GetPowerRankingsTable($path: String!) {
  getPowerRankingsTable(path: $path) {
    tournamentName
    tableTitle
    powerRankingsTableRow {
      rank
      player {
        id
        firstName
        lastName
        countryFlag
        countryName
        headshot
      }
      comment
      commentNodes {
        __typename
        ... on NewsArticleParagraph { segments { value } }
        ... on NewsArticleText { value }
        ... on NewsArticleLink { segments { value } }
        ... on NewsArticleLineBreak { breakValue }
        ... on NewsArticleImage { segments { value } }
      }
    }
  }
}
"""

DATA_DIR = Path("data/power_rankings")
CACHE_DIR = DATA_DIR / "cache"
CONFIG_PATH = DATA_DIR / "paths.csv"


def load_path_config(slug: str) -> Optional[str]:
    if not CONFIG_PATH.exists():
        return None
    try:
        df = pd.read_csv(CONFIG_PATH)
        row = df[df["slug"] == slug]
        if row.empty:
            return None
        return row.iloc[0]["fragment_path"]
    except Exception:
        return None


def save_cache_json(slug: str, data: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{slug}.json"
    out.write_text(json.dumps(data, indent=2))


def load_cache_json(slug: str) -> Optional[dict]:
    path = CACHE_DIR / f"{slug}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def fetch_graphql_with_retry(path: str, retries: int = 3, backoff: float = 1.0) -> Optional[dict]:
    payload = {
        "operationName": "GetPowerRankingsTable",
        "query": QUERY,
        "variables": {"path": path},
    }
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.post(
                GRAPHQL_URL,
                headers=HEADERS,
                json=payload,
                timeout=30,
            )
            if resp.status_code != 200:
                last_err = RuntimeError(f"HTTP {resp.status_code}")
            else:
                data = resp.json()
                return data
        except Exception as e:
            last_err = e
        time.sleep(backoff * (attempt + 1))
    if last_err:
        print(f"⚠️ GraphQL failed after retries: {last_err}")
    return None


def _extract_comment(r: dict) -> str:
    if r.get("comment"):
        return r["comment"].strip()
    parts = []
    for node in r.get("commentNodes", []):
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


def parse_table(data: dict) -> pd.DataFrame:
    if not isinstance(data, dict):
        raise RuntimeError("Invalid response type (expected dict)")
    root = data.get("data") or {}
    table = root.get("getPowerRankingsTable")
    if not table:
        errors = data.get("errors") or []
        if errors:
            msg = "; ".join([e.get("message", "") for e in errors if isinstance(e, dict)])
            raise RuntimeError(f"No table in response (errors: {msg})")
        raise RuntimeError("No table in response")
    rows = table.get("powerRankingsTableRow", [])
    records = []
    for r in rows:
        player = r.get("player", {})
        pid = player.get("id")
        first = player.get("firstName", "")
        last = player.get("lastName", "")
        comment = _extract_comment(r)
        records.append({
            "rank": r.get("rank"),
            "player_id": int(pid) if pid else None,
            "player_name": f"{first} {last}".strip() or f"Player {pid}",
            "country": player.get("countryName", ""),
            "country_flag": player.get("countryFlag", ""),
            "analysis": comment,
        })
    df = pd.DataFrame(records)
    df["tournament_name"] = table.get("tournamentName", "")
    df["source"] = "graphql"
    df["scraped_at"] = datetime.now(timezone.utc).isoformat()
    return df


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    name = Path(path).name
    return name.replace("-", "_") or "power_rankings"


def _score_fragment(path: str) -> int:
    score = 0
    lowered = path.lower()
    if "power-rankings" in lowered:
        score += 2
    if "pr-table" in lowered or "pr_table" in lowered:
        score += 2
    if "pr-" in lowered or "pr_" in lowered:
        score += 1
    return score


def _extract_fragment_paths(html: str) -> list[str]:
    direct = re.findall(r"/content/dam/pga-tour/fragments/[^\"'\\s>]+", html)
    escaped = re.findall(r"\\/content\\/dam\\/pga-tour\\/fragments\\/[^\"'\\s>]+", html)
    escaped = [m.replace("\\/", "/") for m in escaped]
    return list(dict.fromkeys(direct + escaped))


def _extract_fragment_candidates_from_next_data(html: str) -> list[str]:
    m = re.search(r'__NEXT_DATA__\" type=\"application/json\">(.*?)</script>', html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    candidates: list[str] = []
    stack = [data]
    while stack:
        obj = stack.pop()
        if isinstance(obj, dict):
            stack.extend(obj.values())
        elif isinstance(obj, list):
            stack.extend(obj)
        elif isinstance(obj, str) and "/content/dam/pga-tour/fragments/" in obj:
            candidates.append(obj)
    return candidates


def _select_best_fragment(candidates: list[str]) -> Optional[str]:
    if not candidates:
        return None
    preferred = [
        c for c in candidates
        if "power-rankings" in c.lower() or "pr-table" in c.lower() or "pr_table" in c.lower()
    ]
    pool = preferred or candidates
    return max(pool, key=_score_fragment)


def _extract_fragment_candidates(html: str) -> list[str]:
    candidates = _extract_fragment_paths(html)
    candidates.extend(_extract_fragment_candidates_from_next_data(html))
    # De-dupe while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def resolve_fragment_path(path_or_url: str) -> str:
    if not _is_url(path_or_url):
        return path_or_url
    resp = requests.get(path_or_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    candidates = _extract_fragment_candidates(html)
    fragment = _select_best_fragment(candidates)
    if fragment:
        return fragment
    raise RuntimeError("Could not find power rankings fragment path in article HTML")


def main():
    parser = argparse.ArgumentParser(description="Fetch PGA TOUR power rankings")
    parser.add_argument("--slug", help="Slug matching paths.csv (recommended)")
    parser.add_argument("--path", help="Fragment path override")
    parser.add_argument("--allow-fail", action="store_true", help="Return success even if live fetch fails (uses cache if available)")
    args = parser.parse_args()

    # Resolve path
    fragment_path = args.path
    if not fragment_path and args.slug:
        fragment_path = load_path_config(args.slug)
    if not fragment_path:
        parser.error("Provide --path or a slug present in data/power_rankings/paths.csv")

    if fragment_path and _is_url(fragment_path):
        slug = args.slug or _slug_from_url(fragment_path)
        fragment_path = resolve_fragment_path(fragment_path)
        print(f"Resolved fragment path: {fragment_path}")
    else:
        slug = args.slug or Path(fragment_path).stem.replace("-", "_")

    data = fetch_graphql_with_retry(fragment_path)
    if data is None and args.allow_fail:
        data = load_cache_json(slug)
    if data is None:
        raise SystemExit("Power rankings unavailable (live + cache both failed)")

    # Cache raw JSON if live fetch succeeded
    if data:
        save_cache_json(slug, data)

    try:
        df = parse_table(data)
    except Exception as e:
        if args.allow_fail:
            cached = load_cache_json(slug)
            if cached:
                df = parse_table(cached)
            else:
                raise SystemExit(f"Parsing failed and no cache available: {e}")
        else:
            raise SystemExit(f"Parsing failed: {e}")

    out_dir = DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.csv"
    df.to_csv(out_path, index=False)
    print(f"✓ Saved power rankings → {out_path}")
    print(df.head(3))
    print(f"Total rows: {len(df)}")


if __name__ == "__main__":
    main()
