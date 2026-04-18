#!/usr/bin/env python3
"""
Closing Line Logger
====================
Snapshots current odds for all active bet recommendations so we can
compute Closing Line Value (CLV) after the tournament.

Should be run:
  1. Immediately after recommend_bets.py (logs "open" line)
  2. Once more ~1 hour before R1 tee time (logs "closing" line)

CLV = (closing_implied_prob - open_implied_prob) * 100 pp
Positive CLV = we beat the closing line = our edge was real.

Output: data/odds/closing_lines_{tid}.csv
  - One row per (recommendation_id, snapshot_type)
  - snapshot_type: "open" | "closing"

Usage:
    python log_closing_line.py --tournament-id R2026014 --type open
    python log_closing_line.py --tournament-id R2026014 --type closing
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA = PROJECT_ROOT / "data"
ODDS_DIR = DATA / "odds"


def _american_to_implied(odds: float) -> float:
    if pd.isna(odds):
        return np.nan
    o = float(odds)
    if o > 0:
        return 100 / (o + 100)
    return abs(o) / (abs(o) + 100)


def load_current_odds(tid: str) -> pd.DataFrame:
    """
    Build a lookup of (player_name_lower, market) → current odds_american
    by merging DK prop_lines + FD pga_market_odds.
    """
    rows = []

    # DK prop lines
    dk_path = ODDS_DIR / f"prop_lines_{tid}.csv"
    if dk_path.exists():
        dk = pd.read_csv(dk_path)
        for _, r in dk.iterrows():
            mkt = str(r.get("market", "")).lower().strip()
            pname = str(r.get("player_name", r.get("player", ""))).strip().lower()
            odds = pd.to_numeric(r.get("odds", r.get("odds_american")), errors="coerce")
            book = str(r.get("book", "DRAFTKINGS")).upper()
            if pname and pd.notna(odds):
                rows.append({"player_key": pname, "market": mkt, "book": book, "odds_american": odds})

    # FD pga_market_odds
    fd_path = ODDS_DIR / f"pga_market_odds_{tid}.csv"
    if fd_path.exists():
        fd = pd.read_csv(fd_path)
        _mkt_map = {
            "ODDS_TO_WIN": "outright",
            "PLAYER_PROPS": "make_cut",  # approximation; submarket_name refines
        }
        for _, r in fd.iterrows():
            raw_mkt = str(r.get("market_type", "")).upper()
            sub = str(r.get("submarket_name", "")).lower()
            # Resolve market name
            if "make" in sub and "cut" in sub:
                mkt = "make_cut"
            elif "top 5" in sub or "top5" in sub:
                mkt = "top5"
            elif "top 10" in sub or "top10" in sub:
                mkt = "top10"
            elif "top 20" in sub or "top20" in sub:
                mkt = "top20"
            elif "wire" in sub:
                mkt = "wire_to_wire"
            elif "1st round leader" in sub or "first round leader" in sub:
                mkt = "h2h_r1"
            elif raw_mkt == "ODDS_TO_WIN":
                mkt = "outright"
            else:
                mkt = raw_mkt.lower()
            pname = str(r.get("player_name", "")).strip().lower()
            odds = pd.to_numeric(r.get("odds_numeric"), errors="coerce")
            if pname and pd.notna(odds):
                rows.append({"player_key": pname, "market": mkt, "book": "FANDUEL", "odds_american": odds})

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def snapshot_recs(tid: str, snapshot_type: str) -> pd.DataFrame:
    """
    For each rec in recommended_bets_latest.csv, look up current odds
    and return a snapshot dataframe.
    """
    recs_path = ODDS_DIR / "recommended_bets_latest.csv"
    if not recs_path.exists():
        print("No recommended_bets_latest.csv found.")
        return pd.DataFrame()

    recs = pd.read_csv(recs_path)
    recs = recs[recs["tournament_id"].astype(str).str.upper() == tid.upper()].copy()
    recs = recs[recs["bet_type"].astype(str) != "content_card"]
    if recs.empty:
        print(f"No single recs found for {tid}.")
        return pd.DataFrame()

    current_odds = load_current_odds(tid)
    if current_odds.empty:
        print("No current odds found — cannot snapshot.")
        return pd.DataFrame()

    # Build fast lookup: (player_key, market, book) → odds
    odds_lookup: dict[tuple, float] = {}
    for _, r in current_odds.iterrows():
        key = (r["player_key"], r["market"], r["book"])
        odds_lookup[key] = float(r["odds_american"])

    snapped_at = datetime.now(timezone.utc).isoformat()
    snap_rows = []

    for _, rec in recs.iterrows():
        pname = str(rec.get("player_name", "")).strip().lower()
        # Normalize "Last, First" → "first last" for matching
        if ", " in pname:
            parts = pname.split(", ", 1)
            pname_norm = f"{parts[1]} {parts[0]}"
        else:
            pname_norm = pname
        mkt = str(rec.get("market", "")).lower().strip()
        book = str(rec.get("book", "DRAFTKINGS")).upper()

        # Try exact match first, then last-name match
        current_o = (
            odds_lookup.get((pname_norm, mkt, book))
            or odds_lookup.get((pname, mkt, book))
        )
        if current_o is None:
            last = pname_norm.split()[-1] if pname_norm.split() else ""
            for k, v in odds_lookup.items():
                if k[0].endswith(last) and k[1] == mkt and k[2] == book:
                    current_o = v
                    break

        rec_odds = pd.to_numeric(rec.get("odds_american"), errors="coerce")
        rec_implied = _american_to_implied(rec_odds) if pd.notna(rec_odds) else np.nan
        curr_implied = _american_to_implied(current_o) if current_o is not None else np.nan

        snap_rows.append({
            "recommendation_id": str(rec.get("recommendation_id", "")),
            "tournament_id": tid.upper(),
            "snapshot_type": snapshot_type,
            "snapped_at": snapped_at,
            "player_name": str(rec.get("player_name", "")),
            "market": mkt,
            "book": book,
            "rec_odds_american": rec_odds,
            "rec_implied_prob": round(rec_implied, 6) if pd.notna(rec_implied) else None,
            "current_odds_american": current_o,
            "current_implied_prob": round(curr_implied, 6) if pd.notna(curr_implied) else None,
            "model_prob": pd.to_numeric(rec.get("model_prob"), errors="coerce"),
            "edge_pts_at_rec": pd.to_numeric(rec.get("edge_pts"), errors="coerce"),
            "confidence": pd.to_numeric(rec.get("confidence"), errors="coerce"),
            # CLV computed only on "closing" snapshots vs rec odds
            "clv_pts": round((curr_implied - rec_implied) * 100, 3)
                       if (snapshot_type == "closing" and pd.notna(curr_implied) and pd.notna(rec_implied))
                       else None,
        })

    return pd.DataFrame(snap_rows)


def save_snapshot(snap_df: pd.DataFrame, tid: str) -> Path:
    out_path = ODDS_DIR / f"closing_lines_{tid}.csv"
    ODDS_DIR.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        existing = pd.read_csv(out_path)
        combined = pd.concat([existing, snap_df], ignore_index=True)
        # Deduplicate: keep latest per (recommendation_id, snapshot_type)
        combined = combined.sort_values("snapped_at", ascending=False)
        combined = combined.drop_duplicates(subset=["recommendation_id", "snapshot_type"], keep="first")
    else:
        combined = snap_df

    combined.to_csv(out_path, index=False)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Snapshot odds for CLV tracking")
    parser.add_argument("--tournament-id", required=True)
    parser.add_argument("--type", dest="snap_type", choices=["open", "closing"], default="open",
                        help="open = at rec time, closing = before R1 tee time")
    args = parser.parse_args()

    tid = args.tournament_id.upper().strip()
    print(f"Snapping {args.snap_type} line for {tid} ...")

    snap_df = snapshot_recs(tid, args.snap_type)
    if snap_df.empty:
        sys.exit(1)

    out = save_snapshot(snap_df, tid)
    matched = snap_df["current_odds_american"].notna().sum()
    print(f"Snapped {len(snap_df)} recs ({matched} odds matched) → {out.name}")

    if args.snap_type == "closing":
        clv_rows = snap_df[snap_df["clv_pts"].notna()]
        if not clv_rows.empty:
            pos = (clv_rows["clv_pts"] > 0).sum()
            avg = clv_rows["clv_pts"].mean()
            print(f"CLV summary: {pos}/{len(clv_rows)} positive | avg {avg:+.2f}pp")
        else:
            print("CLV: no matched closing lines to compute.")


if __name__ == "__main__":
    main()
