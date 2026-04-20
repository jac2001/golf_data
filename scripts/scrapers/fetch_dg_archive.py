#!/usr/bin/env python3
"""
DataGolf Pre-Tournament Predictions Archive Fetcher
=====================================================

Fetches DG's historical pre-tournament predictions for completed PGA Tour events.
Each record includes the DG model probabilities AND the player's actual finish —
making this directly usable as training data.

Process:
  1. Fetch schedule for each year to get event_id → event_name mapping
  2. For each completed event, fetch archive predictions (baseline_history_fit)
  3. Save per-year CSVs + a combined all-years archive

Key columns in output:
  event_id, event_name, year, event_completed   — event metadata
  dg_id, player_name                            — player identity
  dg_win, dg_top5, dg_top10, dg_top20,
  dg_make_cut, dg_top3, dg_top30, dg_frl        — DG model probabilities (0-1)
  fin_text                                      — actual finish ("1", "T4", "CUT", etc.)

Caches per-event files so re-runs only fetch missing events.

Usage:
    python scripts/scrapers/fetch_dg_archive.py --year 2024
    python scripts/scrapers/fetch_dg_archive.py --years 2019 2020 2021 2022 2023 2024 2025
    python scripts/scrapers/fetch_dg_archive.py --years 2016 2025 --combine
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DG_DIR = DATA_DIR / "datagolf"
ARCHIVE_DIR = DG_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.scrapers.dg_client import dg_get

MODEL = "baseline_history_fit"


# ── Schedule ──────────────────────────────────────────────────────────────────

def fetch_schedule(year: int) -> list[dict]:
    """Return list of events for a given year from DG schedule."""
    data = dg_get("/get-schedule", {"tour": "pga", "year": str(year), "file_format": "json"})
    return data.get("schedule", [])


# ── Archive ───────────────────────────────────────────────────────────────────

def fetch_event_archive(event_id: str, year: int) -> dict:
    """Fetch archive predictions for one event+year."""
    return dg_get("/preds/pre-tournament-archive", {
        "event_id": event_id,
        "year":     str(year),
        "odds_format": "percent",
        "file_format": "json",
    })


def parse_archive(data: dict, event_id: str, year: int) -> pd.DataFrame:
    """Flatten one event's archive response to a DataFrame."""
    players = data.get(MODEL) or data.get("baseline", [])
    if not players:
        return pd.DataFrame()

    event_name      = data.get("event_name", "")
    event_completed = data.get("event_completed", "")
    fetched_at      = datetime.now(timezone.utc).isoformat()

    records = []
    for p in players:
        records.append({
            "event_id":         event_id,
            "event_name":       event_name,
            "year":             year,
            "event_completed":  event_completed,
            "dg_id":            p.get("dg_id"),
            "player_name":      p.get("player_name", ""),
            "fin_text":         p.get("fin_text", ""),          # actual finish
            "dg_win":           p.get("win"),
            "dg_top3":          p.get("top_3"),
            "dg_top5":          p.get("top_5"),
            "dg_top10":         p.get("top_10"),
            "dg_top20":         p.get("top_20"),
            "dg_top30":         p.get("top_30"),
            "dg_make_cut":      p.get("make_cut"),
            "dg_frl":           p.get("first_round_leader"),    # first round leader prob
            "dg_model":         MODEL,
            "fetched_at":       fetched_at,
        })

    return pd.DataFrame(records)


# ── Per-year fetch ────────────────────────────────────────────────────────────

def fetch_year(year: int, force: bool = False) -> pd.DataFrame:
    """Fetch all completed events for a year. Uses per-event cache files."""
    print(f"\n[{year}] Fetching schedule...")
    events = fetch_schedule(year)
    completed = [e for e in events if e.get("status") == "completed"]
    print(f"[{year}] {len(completed)} completed events out of {len(events)}")

    year_frames: list[pd.DataFrame] = []

    for evt in completed:
        eid  = str(evt.get("event_id", ""))
        name = evt.get("event_name", "unknown")

        # Cache path: one file per event × year
        cache_path = ARCHIVE_DIR / f"dg_archive_{year}_{eid}.csv"

        if cache_path.exists() and not force:
            df = pd.read_csv(cache_path)
            year_frames.append(df)
            print(f"  [cache] {name} ({eid}): {len(df)} players")
            continue

        # Fetch from API
        try:
            raw = fetch_event_archive(eid, year)
            if not raw:
                print(f"  [skip]  {name} ({eid}): no data for this year")
                continue
            df  = parse_archive(raw, eid, year)
            if df.empty:
                print(f"  [skip]  {name} ({eid}): no players in response")
                continue
            df.to_csv(cache_path, index=False)
            year_frames.append(df)
            n_completed = (df["fin_text"] != "").sum()
            print(f"  [ok]    {name} ({eid}): {len(df)} players, {n_completed} with results")
        except Exception as e:
            print(f"  [warn]  {name} ({eid}): {e}")

    if not year_frames:
        return pd.DataFrame()

    year_df = pd.concat(year_frames, ignore_index=True)
    year_path = DG_DIR / f"dg_archive_{year}.csv"
    year_df.to_csv(year_path, index=False)
    print(f"[{year}] Saved {len(year_df)} rows → {year_path.name}")
    return year_df


# ── Combine ───────────────────────────────────────────────────────────────────

def combine_years(years: list[int]) -> pd.DataFrame:
    """Load per-year CSVs and concatenate into one master archive."""
    frames = []
    for y in years:
        p = DG_DIR / f"dg_archive_{y}.csv"
        if p.exists():
            frames.append(pd.read_csv(p))
        else:
            print(f"[warn] dg_archive_{y}.csv not found — run with --year {y} first")

    if not frames:
        print("[warn] No archive CSVs found to combine")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    out_path = DG_DIR / "dg_archive_all.csv"
    combined.to_csv(out_path, index=False)
    print(f"\n[ok] Combined archive: {len(combined):,} rows across {len(frames)} years → {out_path.name}")

    # Summary stats
    events = combined.groupby(["year", "event_name"]).size().reset_index(name="players")
    print(f"     {events['year'].nunique()} years, {len(events)} events, {combined['player_name'].nunique()} unique players")
    return combined


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch DataGolf pre-tournament archive")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year",  type=int, help="Single year to fetch")
    group.add_argument("--years", type=int, nargs=2, metavar=("FROM", "TO"),
                       help="Year range to fetch, e.g. --years 2016 2025")
    parser.add_argument("--combine", action="store_true",
                        help="After fetching, combine all years into dg_archive_all.csv")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if cache file exists")
    args = parser.parse_args()

    if args.year:
        years = [args.year]
    else:
        years = list(range(args.years[0], args.years[1] + 1))

    all_frames = []
    for y in years:
        df = fetch_year(y, force=args.force)
        if not df.empty:
            all_frames.append(df)

    if args.combine or len(years) > 1:
        combine_years(years)


if __name__ == "__main__":
    main()
