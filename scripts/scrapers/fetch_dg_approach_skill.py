#!/usr/bin/env python3
"""
DataGolf Approach-Skill Fetcher
================================

Fetches per-player approach shot skill data from DataGolf's approach-skill endpoint.
Each player has SG-per-shot, proximity, GIR rate, good/poor shot rates broken down by
distance range (50-100, 100-150, 150-200, 200+) and lie type (fairway, rough).

Saves to:
    data/datagolf/dg_approach_skill_{period}.csv   — full detail, all segments
    data/datagolf/dg_approach_skill_latest.csv     — canonical copy for pipeline

Key derived column:
    approach_skill_sg   — shot-count-weighted SG/shot across all approach segments
                          (only segments with low_data_indicator == 0 are included)
    approach_skill_proximity — shot-count-weighted avg proximity (feet)

Usage:
    python scripts/scrapers/fetch_dg_approach_skill.py
    python scripts/scrapers/fetch_dg_approach_skill.py --period l12
    python scripts/scrapers/fetch_dg_approach_skill.py --period l24 --no-save
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

# ── Distance×lie segments DG exposes ─────────────────────────────────────────
# Each contributes a set of columns: {seg}_sg_per_shot, {seg}_shot_count, etc.
SEGMENTS = [
    "50_100_fw",
    "100_150_fw",
    "150_200_fw",
    "over_200_fw",
    "under_150_rgh",
    "over_150_rgh",
]

# Metrics available per segment
SEG_METRICS = [
    "sg_per_shot",
    "shot_count",
    "gir_rate",
    "good_shot_rate",
    "poor_shot_avoid_rate",
    "proximity_per_shot",
    "low_data_indicator",
]

# Valid period values per DG docs
VALID_PERIODS = ["l12", "l24", "ytd", "calendar_year"]


# ── API fetch ─────────────────────────────────────────────────────────────────

def fetch_approach_skill(period: str = "l24") -> dict:
    """Fetch approach-skill data from DataGolf."""
    return dg_get("/preds/approach-skill", {"period": period})


# ── Parse + flatten ───────────────────────────────────────────────────────────

def parse_response(data: dict) -> pd.DataFrame:
    """Flatten raw JSON to one row per player, computing composite metrics.

    Output columns:
        dg_id, player_name, time_period, last_updated, fetched_at
        {seg}_{metric} for each segment × metric combination
        approach_skill_sg          — shot-count-weighted avg SG/shot (reliable segs only)
        approach_skill_proximity   — shot-count-weighted avg proximity in feet
        approach_skill_shot_total  — total shots across reliable segments
    """
    rows = data.get("data", [])
    last_updated = data.get("last_updated", "")
    time_period = data.get("time_period", "")
    fetched_at = datetime.now(timezone.utc).isoformat()

    records = []
    for p in rows:
        rec: dict = {
            "dg_id":        p.get("dg_id"),
            "player_name":  p.get("player_name", ""),
            "time_period":  time_period,
            "last_updated": last_updated,
            "fetched_at":   fetched_at,
        }

        # Flatten all segment metrics
        for seg in SEGMENTS:
            for metric in SEG_METRICS:
                col = f"{seg}_{metric}"
                rec[col] = p.get(col)

        # ── Composite: shot-count-weighted SG/shot + proximity ──
        total_shots    = 0.0
        weighted_sg    = 0.0
        weighted_prox  = 0.0

        for seg in SEGMENTS:
            low_data = p.get(f"{seg}_low_data_indicator", 1)
            if low_data:          # skip segments flagged as low-data
                continue
            sg_ps  = p.get(f"{seg}_sg_per_shot")
            prox   = p.get(f"{seg}_proximity_per_shot")
            cnt    = p.get(f"{seg}_shot_count") or 0

            if sg_ps is not None and cnt > 0:
                weighted_sg   += sg_ps * cnt
                total_shots   += cnt
            if prox is not None and cnt > 0:
                weighted_prox += prox * cnt

        if total_shots > 0:
            rec["approach_skill_sg"]         = round(weighted_sg / total_shots, 5)
            rec["approach_skill_proximity"]  = round(weighted_prox / total_shots, 3)
        else:
            rec["approach_skill_sg"]         = None
            rec["approach_skill_proximity"]  = None

        rec["approach_skill_shot_total"] = int(total_shots) if total_shots > 0 else None

        records.append(rec)

    return pd.DataFrame(records)


# ── Print summary ─────────────────────────────────────────────────────────────

def print_top(df: pd.DataFrame, top_n: int = 20) -> None:
    """Print top players by composite approach skill SG."""
    print(f"\nTop {top_n} by Approach Skill SG (shot-count weighted, reliable segs only):")
    sub = df.dropna(subset=["approach_skill_sg"]).copy()
    sub = sub.sort_values("approach_skill_sg", ascending=False).head(top_n)

    header = f"  {'Player':<28} {'Skill SG':>10} {'Proximity':>10} {'Shots':>6}"
    print(header)
    print("  " + "-" * 58)
    for _, r in sub.iterrows():
        name = str(r["player_name"])
        if "," in name:
            parts = name.split(",", 1)
            name = f"{parts[1].strip()} {parts[0].strip()}"
        sg_str   = f"{r['approach_skill_sg']:+.4f}" if r["approach_skill_sg"] is not None else "—"
        prox_str = f"{r['approach_skill_proximity']:.1f} ft" if r["approach_skill_proximity"] is not None else "—"
        shots    = str(int(r["approach_skill_shot_total"])) if r["approach_skill_shot_total"] else "—"
        print(f"  {name:<28} {sg_str:>10} {prox_str:>10} {shots:>6}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch DataGolf approach-skill data")
    parser.add_argument(
        "--period", default="l24",
        choices=VALID_PERIODS,
        help="Time window for approach skill (default: l24 = last 24 months)",
    )
    parser.add_argument("--no-save", action="store_true",
                        help="Fetch and print only, do not save CSV")
    parser.add_argument("--top-n", type=int, default=20,
                        help="How many players to print in summary (default: 20)")
    args = parser.parse_args()

    print(f"[INFO] Fetching DG approach-skill (period={args.period})...")
    data = fetch_approach_skill(args.period)

    last_updated = data.get("last_updated", "")
    time_period  = data.get("time_period", "")
    n_players    = len(data.get("data", []))
    print(f"[INFO] {n_players} players | period: {time_period} | updated: {last_updated}")

    df = parse_response(data)

    # Stats
    reliable = df["approach_skill_sg"].notna().sum()
    print(f"[INFO] {reliable}/{len(df)} players have reliable approach skill data")

    if not args.no_save:
        period_slug = args.period  # e.g. "l24"
        out_path = DG_DIR / f"dg_approach_skill_{period_slug}.csv"
        df.to_csv(out_path, index=False)
        print(f"[OK] Saved → {out_path}  ({len(df)} rows)")

        latest_path = DG_DIR / "dg_approach_skill_latest.csv"
        df.to_csv(latest_path, index=False)
        print(f"[OK] Latest → {latest_path}")

        # Save metadata
        meta = {
            "period":       args.period,
            "time_period":  time_period,
            "last_updated": last_updated,
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "player_count": len(df),
            "reliable_count": int(reliable),
        }
        meta_path = DG_DIR / f"dg_approach_skill_{period_slug}_meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"[OK] Metadata → {meta_path}")

    print_top(df, top_n=args.top_n)


if __name__ == "__main__":
    main()
