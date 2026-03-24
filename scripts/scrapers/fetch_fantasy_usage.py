#!/usr/bin/env python3
"""
Fetch Fantasy League Usage Data
=================================
Scrapes total golfer usage counts from the Pro Tour Fantasy Golf league tracker.
Saves to data/fantasy/league_total_usages.csv with player name, times used, and
utilization % across all 28 teams.

Usage:
    python3 scripts/scrapers/fetch_fantasy_usage.py
    python3 scripts/scrapers/fetch_fantasy_usage.py --verbose
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "fantasy"
OUT_FILE = DATA_DIR / "league_total_usages.csv"

BASE_URL = "https://connection.protourfantasygolf.com"
USAGES_URL = f"{BASE_URL}/golfers_used_compare/total_golfer_usages"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _norm_name(name: str) -> str:
    """Normalize player name for matching: strip accents, lowercase, remove punctuation."""
    s = unicodedata.normalize("NFD", str(name).strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s,]", "", s)
    return " ".join(s.split())


def fetch_total_usages(verbose: bool = False) -> pd.DataFrame:
    """Fetch the total golfer usages table and return as a DataFrame."""
    if verbose:
        print(f"Fetching: {USAGES_URL}")

    resp = requests.get(USAGES_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    # Parse with pandas (reads all HTML tables)
    try:
        tables = pd.read_html(resp.text)
    except ValueError:
        raise RuntimeError("No tables found on the page — site may have changed structure")

    # Find the table with golfer/usage data
    df = None
    for t in tables:
        cols_lower = [str(c).lower() for c in t.columns]
        if any("golfer" in c or "player" in c for c in cols_lower):
            df = t
            break

    if df is None:
        # Fallback: use the largest table
        df = max(tables, key=len)

    if verbose:
        print(f"  Raw table: {len(df)} rows, columns: {df.columns.tolist()}")

    # Standardize column names
    col_map = {}
    for c in df.columns:
        cl = str(c).lower()
        if "golfer" in cl or "player" in cl or "name" in cl:
            col_map[c] = "player_name"
        elif "all" in cl or "total" in cl or "count" in cl or "team" in cl:
            col_map[c] = "times_used"
        elif "util" in cl or "pct" in cl or "%" in cl:
            col_map[c] = "util_pct"
    df = df.rename(columns=col_map)

    # Keep only needed columns
    keep = [c for c in ["player_name", "times_used", "util_pct"] if c in df.columns]
    df = df[keep].copy()

    # Clean up
    df = df[df["player_name"].notna()].copy()
    df = df[~df["player_name"].astype(str).str.lower().str.contains("golfer|player|total|header", na=False)]
    df["times_used"] = pd.to_numeric(df.get("times_used", 0), errors="coerce").fillna(0).astype(int)
    if "util_pct" in df.columns:
        df["util_pct"] = pd.to_numeric(df["util_pct"], errors="coerce").round(1)
    df["_name_key"] = df["player_name"].apply(_norm_name)

    df = df.reset_index(drop=True)
    return df


def save(df: pd.DataFrame, verbose: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = df[[c for c in df.columns if not c.startswith("_")]].copy()
    out.to_csv(OUT_FILE, index=False)
    if verbose:
        print(f"Saved {len(out)} rows → {OUT_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch fantasy league usage data")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    df = fetch_total_usages(verbose=args.verbose)
    save(df, verbose=args.verbose)

    if args.verbose:
        print("\nTop 15 most-used players:")
        print(df.sort_values("times_used", ascending=False).head(15)[
            ["player_name", "times_used", "util_pct"]
        ].to_string(index=False))


if __name__ == "__main__":
    main()
