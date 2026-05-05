#!/usr/bin/env python3
"""
DataGolf Pre-Tournament Predictions
=====================================
Fetches win/top5/top10/top20/make_cut probabilities for both models:
  - baseline            : skill + course fit only
  - baseline_history_fit: skill + course fit + course history (better model)

Usage:
    python scripts/scrapers/fetch_dg_pre_tournament.py --tournament-id R2026013
"""
from pathlib import Path
import pandas as pd
import sys
import argparse
import json
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.scrapers.dg_client import dg_get

DATA_DIR = PROJECT_ROOT / "data"
DG_DIR   = DATA_DIR / "datagolf"


def fetch_pre_tournament():
    return dg_get("/preds/pre-tournament", {"odds_format": "percent"})


def parse_response(data) -> pd.DataFrame:
    event_name   = data.get("event_name", "")
    last_updated = data.get("last_updated", "")
    fetched_at   = datetime.now(timezone.utc).isoformat()
    records = []

    for model_key in ("baseline", "baseline_history_fit"):
        rows = data.get(model_key, [])
        for p in rows:
            records.append({
                "event_name":   event_name,
                "model":        model_key,
                "dg_id":        p.get("dg_id"),
                "player_name":  p.get("player_name", ""),
                "country":      p.get("country", ""),
                "win":          p.get("win"),
                "top_5":        p.get("top_5"),
                "top_10":       p.get("top_10"),
                "top_20":       p.get("top_20"),
                "make_cut":     p.get("make_cut"),
                "sample_size":  p.get("sample_size"),
                "last_updated": last_updated,
                "fetched_at":   fetched_at,
            })
    return pd.DataFrame(records)


def compute_course_fit_delta(df: pd.DataFrame) -> pd.DataFrame:                                                       
    """                                                   
    Pivot baseline vs baseline_history_fit rows and compute course_fit_delta.
    delta > 0  → course suits this player more than their raw skill predicts                                          
    delta < 0  → course hurts them relative to their baseline
    """
    
    
    base = (
        df[df['model'] == 'baseline'][['player_name', 'dg_id', 'win']]
        .rename(columns={'win': 'baseline_win'})
    )

    bhf = (
        df[df['model'] == 'baseline_history_fit']
        [['player_name', 'dg_id', 'win', 'top_10', 'make_cut']]
        .rename(columns={"win": "bhf_win", "top_10": "bhf_top10", "make_cut": "bhf_make_cut"})
      )

    out = bhf.merge(base, on=['player_name', 'dg_id'], how='left')
    out['course_fit_delta'] = (out['bhf_win'] - out['baseline_win']).round(4)
    out['course_fit_delta_pct'] = (out['course_fit_delta'] / out['baseline_win']).round(3)
    return out.sort_values('course_fit_delta_pct', ascending=False).reset_index(drop=True)





def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tournament-id", default="latest", help="e.g. R2026013")
    args = parser.parse_args()
    tid = args.tournament_id.upper()

    DG_DIR.mkdir(parents=True, exist_ok=True)
    print("[INFO] Fetching DG pre-tournament predictions...")
    data = fetch_pre_tournament()

    event_name = data.get("event_name", "unknown")
    print(f"[INFO] Event: {event_name} | Updated: {data.get('last_updated', '')}")

    df = parse_response(data)
    print(f"[INFO] {len(df)} rows ({len(df)//2} players × 2 models)")

    # Save tournament-scoped + latest
    if tid != "LATEST":
        out_path = DG_DIR / f"dg_pre_tournament_{tid}.csv"
        df.to_csv(out_path, index=False)
        print(f"[OK] Saved → {out_path}")

    latest_path = DG_DIR / "dg_pre_tournament_latest.csv"
    df.to_csv(latest_path, index=False)
    print(f"[OK] Latest → {latest_path}")

    # --- Course Fit Delta -----
    fit_df = compute_course_fit_delta(df)
    fit_path = DG_DIR / "dg_course_fit_latest.csv"
    fit_df.to_csv(fit_path, index=False)
    print(f"[OK] Course fit delta → {fit_path}")
    
    
    cols = ['player_name', 'baseline_win', 'bhf_win', 'course_fit_delta', 'course_fit_delta_pct']
    print("\nBiggest course fit winners (% boost vs raw skill):")
    print(fit_df.head(8)[cols].to_string(index=False))
    print("\nBiggest course fit losers (% drag vs raw skill):")
    print(fit_df.tail(5)[cols].to_string(index=False))

    # Print top 10 by baseline_history_fit win prob
    top = (
        df[df["model"] == "baseline_history_fit"]
        .sort_values("win", ascending=False)
        .head(10)[["player_name", "win", "top_10", "make_cut"]]
    )
    print("\nTop 10 (baseline_history_fit):")
    print(top.to_string(index=False))

    try:
        from scripts.database.upsert_dg import upsert_table
        upsert_table("dg_pre_tournament")
        print("[OK] DB updated → dg_pre_tournament")
    except Exception as _e:
        print(f"[WARN] DB upsert skipped: {_e}")


if __name__ == "__main__":
    main()
