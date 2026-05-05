#!/usr/bin/env python3
"""
DataGolf Player Decompositions Fetcher
=======================================

Fetches DG's per-player prediction decomposition for the current week's event.
This breaks down each player's predicted SG into its component parts:
  baseline (overall skill) + course history + course fit (driving acc/dist) +
  timing (recent form) + age/country adjustments = final prediction

All values are strokes-gained vs average PGA Tour field per round.

Unlike skill-ratings (all players, slow-moving), this is event-specific —
it updates each week and only covers the current field (~80-160 players).

Key columns:
  baseline_pred             — overall skill (course-neutral)
  final_pred                — full prediction for this event (use this as DG's pick)
  course_history_adjustment — how player has historically performed at this course
  driving_accuracy_adjustment — course fit: accuracy matters here → acc players boosted
  driving_distance_adjustment — course fit: distance matters here → long players boosted
  timing_adjustment         — recent form component
  std_deviation             — DG's uncertainty (high = boom-or-bust player)
  course_fit_delta          — computed: final_pred - baseline_pred (course uplift/drag)

Saves to:
  data/datagolf/dg_decompositions_{tid}.csv
  data/datagolf/dg_decompositions_latest.csv

Usage:
    python scripts/scrapers/fetch_dg_decompositions.py --tournament-id R2026041
    python scripts/scrapers/fetch_dg_decompositions.py --tournament-id R2026041 --no-save
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


def fetch_decompositions() -> dict:
    return dg_get("/preds/player-decompositions", {"tour": "pga"})


def parse_response(data: dict) -> pd.DataFrame:
    players = data.get("players", [])
    event_name  = data.get("event_name", "")
    course_name = data.get("course_name", "")
    last_updated = data.get("last_updated", "")
    fetched_at   = datetime.now(timezone.utc).isoformat()

    records = []
    for p in players:
        rec = {
            "player_name":    p.get("player_name", ""),
            "dg_id":          p.get("dg_id"),
            "age":            p.get("age"),
            "country":        p.get("country", ""),
            "am":             p.get("am", 0),
            # Core prediction
            "baseline_pred":  p.get("baseline_pred"),
            "final_pred":     p.get("final_pred"),
            "std_deviation":  p.get("std_deviation"),
            "sample_size":    p.get("sample_size"),
            # Adjustment components
            "course_history_adjustment":     p.get("course_history_adjustment"),
            "course_experience_adjustment":  p.get("course_experience_adjustment"),
            "total_course_history_adjustment": p.get("total_course_history_adjustment"),
            "driving_accuracy_adjustment":   p.get("driving_accuracy_adjustment"),
            "driving_distance_adjustment":   p.get("driving_distance_adjustment"),
            "timing_adjustment":             p.get("timing_adjustment"),
            "age_adjustment":                p.get("age_adjustment"),
            "country_adjustment":            p.get("country_adjustment"),
            "strokes_gained_category_adjustment": p.get("strokes_gained_category_adjustment"),
            "cf_approach_comp":   p.get("cf_approach_comp"),
            "cf_short_comp":      p.get("cf_short_comp"),
            "other_fit_adjustment": p.get("other_fit_adjustment"),
            "total_fit_adjustment": p.get("total_fit_adjustment"),
            "true_sg_adjustments":  p.get("true_sg_adjustments"),
            # Metadata
            "event_name":   event_name,
            "course_name":  course_name,
            "last_updated": last_updated,
            "fetched_at":   fetched_at,
        }
        # Derived: how much does this course help/hurt vs baseline
        if rec["final_pred"] is not None and rec["baseline_pred"] is not None:
            rec["course_fit_delta"] = round(
                float(rec["final_pred"]) - float(rec["baseline_pred"]), 5
            )
        else:
            rec["course_fit_delta"] = None
        records.append(rec)

    df = pd.DataFrame(records)
    return df.sort_values("final_pred", ascending=False).reset_index(drop=True)


def print_summary(df: pd.DataFrame, top_n: int = 20) -> None:
    event = df["event_name"].iloc[0] if not df.empty else ""
    course = df["course_name"].iloc[0] if not df.empty else ""
    print(f"\n{event} — {course}")
    print(f"{'Player':<28} {'Base':>6} {'Final':>6} {'Δ Fit':>6} {'DrAcc':>6} {'DrDst':>6} {'Time':>6} {'Hist':>6}  StdDev")
    print("─" * 90)
    for _, r in df.head(top_n).iterrows():
        name = str(r["player_name"])
        if "," in name:
            parts = name.split(",", 1)
            name = f"{parts[1].strip()} {parts[0].strip()}"

        def f(v): return f"{float(v):+.3f}" if v is not None and pd.notna(v) else "  —  "

        print(f"  {name:<26} {f(r['baseline_pred']):>6} {f(r['final_pred']):>6} "
              f"{f(r['course_fit_delta']):>6} {f(r['driving_accuracy_adjustment']):>6} "
              f"{f(r['driving_distance_adjustment']):>6} {f(r['timing_adjustment']):>6} "
              f"{f(r['course_history_adjustment']):>6}  {float(r['std_deviation']):.2f}")


def main():
    parser = argparse.ArgumentParser(description="Fetch DataGolf player decompositions")
    parser.add_argument("--tournament-id", required=True, help="e.g. R2026041")
    parser.add_argument("--no-save", action="store_true",
                        help="Fetch and print only, do not save CSV")
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()
    tid = args.tournament_id.upper()

    print(f"[INFO] Fetching DG player decompositions...")
    data = fetch_decompositions()

    event_name  = data.get("event_name", "unknown")
    course_name = data.get("course_name", "")
    last_updated = data.get("last_updated", "")
    print(f"[INFO] Event: {event_name} @ {course_name} | Updated: {last_updated}")

    df = parse_response(data)
    print(f"[INFO] {len(df)} players")

    if not args.no_save:
        out_path = DG_DIR / f"dg_decompositions_{tid}.csv"
        df.to_csv(out_path, index=False)
        print(f"[OK] Saved → {out_path}")

        latest_path = DG_DIR / "dg_decompositions_latest.csv"
        df.to_csv(latest_path, index=False)
        print(f"[OK] Latest → {latest_path}")

        meta = {
            "tournament_id": tid,
            "event_name": event_name,
            "course_name": course_name,
            "last_updated": last_updated,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "player_count": len(df),
        }
        meta_path = DG_DIR / f"dg_decompositions_{tid}_meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"[OK] Meta → {meta_path}")

    print_summary(df, top_n=args.top_n)

    if not args.no_save:
        try:
            from scripts.database.upsert_dg import upsert_table
            upsert_table("dg_decompositions")
            print("[OK] DB updated → dg_decompositions")
        except Exception as _e:
            print(f"[WARN] DB upsert skipped: {_e}")


if __name__ == "__main__":
    main()
