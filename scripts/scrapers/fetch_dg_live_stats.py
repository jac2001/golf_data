#!/usr/bin/env python3
"""
DataGolf Live Tournament Stats Fetcher
=======================================

Fetches real-time strokes-gained data from DataGolf during a tournament.
Saves a clean CSV per round (and event_avg) to data/datagolf/.

Usage:
    python scripts/scrapers/fetch_dg_live_stats.py --tournament-id R2026012
    python scripts/scrapers/fetch_dg_live_stats.py --tournament-id R2026012 --round 1
    python scripts/scrapers/fetch_dg_live_stats.py --tournament-id R2026012 --round event_avg
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DG_DIR = DATA_DIR / "datagolf"
DG_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.scrapers.dg_client import dg_get

SG_STATS = "sg_putt,sg_arg,sg_app,sg_ott,sg_t2g,sg_total,driving_dist,driving_acc"


def fetch_live_stats(round_param: str = "event_avg") -> dict:
    return dg_get("/preds/live-tournament-stats", {
        "stats": SG_STATS,
        "round": round_param,
        "tour": "pga",
    })


def flatten(raw: dict, round_param: str) -> pd.DataFrame:
    rows = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    event_name = raw.get("event_name", "")
    last_updated = raw.get("last_updated", "")

    for p in raw.get("live_stats", []):
        rows.append({
            "player_name":  p.get("player_name", ""),
            "dg_id":        p.get("dg_id"),
            "position":     p.get("position"),
            "total":        p.get("total"),
            "thru":         p.get("thru"),
            "round":        p.get("round"),
            "sg_ott":       p.get("sg_ott"),
            "sg_app":       p.get("sg_app"),
            "sg_arg":       p.get("sg_arg"),
            "sg_putt":      p.get("sg_putt"),
            "sg_t2g":       p.get("sg_t2g"),
            "sg_total":     p.get("sg_total"),
            "driving_dist": p.get("driving_dist"),
            "driving_acc":  p.get("driving_acc"),
            "round_param":  round_param,
            "event_name":   event_name,
            "last_updated": last_updated,
            "fetched_at":   fetched_at,
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Fetch DataGolf live tournament SG stats")
    parser.add_argument("--tournament-id", required=True, help="e.g. R2026012")
    parser.add_argument(
        "--round", default="event_avg",
        help="Round to fetch: 1/2/3/4 or 'event_avg' (default: event_avg)",
    )
    args = parser.parse_args()
    tid = args.tournament_id.upper()
    round_param = args.round

    print(f"[INFO] Fetching DG live stats (round={round_param})...")
    raw = fetch_live_stats(round_param)

    event_name = raw.get("event_name", "unknown")
    last_updated = raw.get("last_updated", "")
    print(f"[INFO] Event: {event_name}  |  Last updated: {last_updated}")

    df = flatten(raw, round_param)
    n = len(df)
    print(f"[INFO] {n} players")

    if df.empty:
        print("[WARN] No player data returned.")
        return

    # Sort by sg_total descending (best SG at top)
    df = df.sort_values("sg_total", ascending=False, na_position="last").reset_index(drop=True)

    out_path = DG_DIR / f"dg_live_stats_{tid}_{round_param}.csv"
    df.to_csv(out_path, index=False)
    print(f"[OK] Saved → {out_path}  ({n} rows)")

    # Also save as canonical "latest" for the dashboard to pick up easily
    latest_path = DG_DIR / f"dg_live_stats_{tid}_latest.csv"
    df.to_csv(latest_path, index=False)
    print(f"[OK] Latest → {latest_path}")

    # Print top 10 by sg_total
    print(f"\nTop 10 by SG Total ({round_param}):")
    print(f"  {'Player':<28} {'Pos':>4}  {'Score':>5}  {'SG Tot':>6}  {'OTT':>5}  {'APP':>5}  {'ARG':>5}  {'PUTT':>5}  {'Thru':>4}")
    print("  " + "-" * 80)
    for _, r in df.head(10).iterrows():
        def fmt(v): return f"{float(v):+.2f}" if v is not None and str(v) not in ("None", "nan", "") else "  —  "
        pos = str(r.get("position", "—"))
        score = str(r.get("total", "—"))
        thru = str(r.get("thru", "—"))
        print(f"  {str(r['player_name']):<28} {pos:>4}  {score:>5}  {fmt(r.get('sg_total')):>6}  "
              f"{fmt(r.get('sg_ott')):>5}  {fmt(r.get('sg_app')):>5}  "
              f"{fmt(r.get('sg_arg')):>5}  {fmt(r.get('sg_putt')):>5}  {thru:>4}")


if __name__ == "__main__":
    main()
