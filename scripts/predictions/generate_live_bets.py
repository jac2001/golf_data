#!/usr/bin/env python3
"""
Live Bet Recommendations Generator
====================================
Mid-tournament equivalent of recommend_bets.py.

Uses live_update_predictions.py's Monte Carlo simulation to get
current finish probabilities (win/top5/top10) based on leaderboard
position + rounds remaining, then compares against current sportsbook
odds to find edges.

Output: data/odds/recommended_bets_live_R{tid}.csv
  — same schema as recommended_bets_latest.csv so the chatbot and
    dashboard can read it with the same code.

Usage:
    python scripts/predictions/generate_live_bets.py
    python scripts/predictions/generate_live_bets.py --tid R2026011
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR  = PROJECT_ROOT / "data"
ODDS_DIR  = DATA_DIR / "odds"
LIVE_DIR  = DATA_DIR / "live"
OUTPUTS   = PROJECT_ROOT / "outputs"

sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))
from live_update_predictions import run_live_update  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_name(name) -> str:
    if pd.isna(name):
        return ""
    s = str(name).strip().lower()
    # "Last, First" → "First Last"
    if "," in s:
        parts = s.split(",", 1)
        s = f"{parts[1].strip()} {parts[0].strip()}"
    for suffix in [" jr.", " jr", " iii", " ii", " iv"]:
        s = s.replace(suffix, "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def _american_to_prob(odds) -> float:
    try:
        o = int(float(str(odds).replace(",", "").replace("+", "").strip()))
    except Exception:
        return float("nan")
    if o == 0:
        return float("nan")
    if o > 0:
        return 100.0 / (o + 100.0)
    return abs(o) / (abs(o) + 100.0)


def _american_to_decimal(odds) -> float:
    try:
        o = int(float(str(odds).replace(",", "").replace("+", "").strip()))
    except Exception:
        return float("nan")
    if o > 0:
        return 1.0 + o / 100.0
    return 1.0 + 100.0 / abs(o)


def _rec_id(player: str, market: str, book: str) -> str:
    raw = f"live|{player}|{market}|{book}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _detect_tid() -> str | None:
    candidates = sorted(
        LIVE_DIR.glob("leaderboard_r*_meta.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for mf in candidates:
        try:
            with open(mf) as f:
                meta = json.load(f)
            rs = meta.get("round_status", "").lower()
            if not (rs in {"official", "complete", "final"} and int(meta.get("current_round", 0)) == 4):
                return meta.get("tournament_id")
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _load_prop_odds(tid: str) -> pd.DataFrame:
    """Load top5/top10 odds from dg_outrights_{tid}.csv, normalise per-book.

    DG outrights are the primary source — fresher than DK prop_lines scraper
    and include 10+ books (Pinnacle, Betcris, Bet365, etc.).
    Falls back to prop_lines_{tid}.csv if DG file is missing.
    """
    _MKT_MAP = {"top_5": "top5", "top_10": "top10", "win": "outright"}
    dg_path = DATA_DIR / "datagolf" / f"dg_outrights_{tid}.csv"

    if dg_path.exists():
        try:
            df = pd.read_csv(dg_path)
            # Filter to top5/top10, exclude DG model rows
            df = df[
                df["market"].isin(["top_5", "top_10"]) &
                (df["is_dg_model"].astype(str).str.lower() != "true")
            ].copy()
            if not df.empty:
                df["market"] = df["market"].map(_MKT_MAP).fillna(df["market"])
                # Normalise "Last, First" → "First Last"
                def _flip(n):
                    s = str(n).strip()
                    return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s
                df["player_name"] = df["player_name"].apply(_flip)
                df["name_key"] = df["player_name"].apply(_norm_name)
                df["raw_prob"] = df["odds_american"].apply(_american_to_prob)
                df = df[df["raw_prob"].notna() & (df["raw_prob"] > 0)].copy()
                df = df.rename(columns={"odds_american": "odds"})
                rows = []
                for (book, market), grp in df.groupby(["book", "market"]):
                    spots = 5.0 if market == "top5" else 10.0
                    total_raw = grp["raw_prob"].sum()
                    if total_raw <= 0:
                        continue
                    grp = grp.copy()
                    grp["book_prob_nv"] = grp["raw_prob"] / total_raw * spots
                    rows.append(grp)
                if rows:
                    out = pd.concat(rows, ignore_index=True)
                    print(f"  DG outrights: {len(out)} top5/top10 rows, {out['book'].nunique()} books")
                    return out[["name_key", "player_name", "market", "book", "odds", "book_prob_nv"]].copy()
        except Exception as e:
            print(f"  DG outrights load error: {e}")

    # Fallback: prop_lines (DK only)
    path = ODDS_DIR / f"prop_lines_{tid}.csv"
    if not path.exists():
        print(f"  No odds source available (tried DG outrights + {path.name})")
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        df = df[df["market"].isin(["top5", "top10"])].copy()
        df["name_key"] = df["player_name"].apply(_norm_name)
        df["raw_prob"] = df["odds"].apply(_american_to_prob)
        df = df[df["raw_prob"].notna() & (df["raw_prob"] > 0)].copy()
        rows = []
        for (book, market), grp in df.groupby(["book", "market"]):
            spots = 5.0 if market == "top5" else 10.0
            total_raw = grp["raw_prob"].sum()
            if total_raw <= 0:
                continue
            grp = grp.copy()
            grp["book_prob_nv"] = grp["raw_prob"] / total_raw * spots
            rows.append(grp)
        if not rows:
            return pd.DataFrame()
        out = pd.concat(rows, ignore_index=True)
        return out[["name_key", "player_name", "market", "book", "odds", "book_prob_nv"]].copy()
    except Exception as e:
        print(f"  Prop odds load error: {e}")
        return pd.DataFrame()


def _load_live_win_odds(tid: str) -> pd.DataFrame:
    """Load live win odds from the leaderboard (odds_to_win column)."""
    path = LIVE_DIR / f"leaderboard_{tid.lower()}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        lb = pd.read_csv(path)
        if "odds_to_win" not in lb.columns:
            return pd.DataFrame()
        lb = lb[lb["odds_to_win"].notna()].copy()
        lb["name_key"] = lb["player_name"].apply(_norm_name)
        lb["raw_prob"]  = lb["odds_to_win"].apply(_american_to_prob)
        lb = lb[lb["raw_prob"].notna() & (lb["raw_prob"] > 0)].copy()
        total = lb["raw_prob"].sum()
        if total <= 0:
            return pd.DataFrame()
        lb["book_prob_nv"] = lb["raw_prob"] / total
        lb["market"] = "win"
        lb["book"]   = "DK"
        lb["odds"]   = lb["odds_to_win"]
        return lb[["name_key", "player_name", "market", "book", "odds", "book_prob_nv"]].copy()
    except Exception as e:
        print(f"  Live win odds load error: {e}")
        return pd.DataFrame()


def _live_top20_prob(preds: pd.DataFrame) -> pd.Series:
    """Estimate live top-20 prob from simulation (not stored — recompute from rank distribution).

    We don't have top20 in live_update, so we proxy it as:
      top20_prob ≈ live_top10_prob * (top20_prob_calibrated / top10_prob_calibrated)
    with a floor of live_top10_prob.
    """
    t10 = pd.to_numeric(preds.get("live_top10_prob", pd.Series(0.0, index=preds.index)), errors="coerce").fillna(0.0)
    t20_pre = pd.to_numeric(preds.get("top20_prob", pd.Series(0.0, index=preds.index)), errors="coerce").fillna(0.0)
    t10_pre = pd.to_numeric(preds.get("top10_prob", pd.Series(0.0, index=preds.index)), errors="coerce").fillna(0.01)
    ratio = (t20_pre / t10_pre.clip(lower=0.01)).clip(upper=3.0)
    return (t10 * ratio).clip(upper=0.98)


def generate(tid: str) -> pd.DataFrame:
    print(f"\n=== Live Bet Recommendations: {tid} ===")

    # Step 1: Run live update to get live_win_prob, live_top5_prob, live_top10_prob
    print("\nStep 1: Running live update predictions...")
    preds = run_live_update(tournament_id=tid)
    if preds.empty:
        print("ERROR: live_update returned empty DataFrame.")
        return pd.DataFrame()

    rounds_complete = int(preds["rounds_complete"].iloc[0]) if "rounds_complete" in preds.columns else 0
    print(f"  Rounds complete: {rounds_complete}")

    if rounds_complete == 0:
        print("No rounds complete yet — live bet recommendations not meaningful pre-tournament.")
        return pd.DataFrame()

    # Step 2: Build model prob lookup by name_key
    preds["name_key"] = preds["player_name"].apply(_norm_name)
    live_top20 = _live_top20_prob(preds)
    model_probs: dict[str, dict[str, float]] = {}
    for _, row in preds.iterrows():
        key = row["name_key"]
        if not key:
            continue
        model_probs[key] = {
            "win":   float(pd.to_numeric(row.get("live_win_prob",  0), errors="coerce") or 0),
            "top5":  float(pd.to_numeric(row.get("live_top5_prob", 0), errors="coerce") or 0),
            "top10": float(pd.to_numeric(row.get("live_top10_prob",0), errors="coerce") or 0),
            "top20": float(live_top20.loc[row.name] if row.name in live_top20.index else 0),
            "live_score_rank": int(pd.to_numeric(row.get("live_score_rank", 999), errors="coerce") or 999),
        }

    # Step 3: Load odds
    print("\nStep 2: Loading current odds...")
    win_odds   = _load_live_win_odds(tid)
    prop_odds  = _load_prop_odds(tid)
    all_odds   = pd.concat([win_odds, prop_odds], ignore_index=True) if not prop_odds.empty else win_odds
    print(f"  Win odds: {len(win_odds)} players")
    print(f"  Prop odds (T5/T10): {len(prop_odds)} rows")

    if all_odds.empty:
        print("ERROR: No odds data available.")
        return pd.DataFrame()

    # Step 4: Compute edge per row
    print("\nStep 3: Computing edge...")
    records = []
    for _, row in all_odds.iterrows():
        key     = row["name_key"]
        market  = row["market"]
        book    = row["book"]
        odds    = row["odds"]
        book_prob_nv = float(row["book_prob_nv"])

        mp = model_probs.get(key, {})
        model_prob = mp.get(market, None)
        if model_prob is None or model_prob <= 0:
            continue

        edge_pts = (model_prob - book_prob_nv) * 100.0
        if edge_pts <= 3.0:  # Skip thin or negative edge
            continue

        dec_odds = _american_to_decimal(odds)
        ev = model_prob * dec_odds - 1.0 if not np.isnan(dec_odds) else np.nan
        confidence = min(0.95, 0.5 + edge_pts / 200.0)

        records.append({
            "recommendation_id":  _rec_id(key, market, book),
            "run_id":             _now(),
            "recommended_at":     _now(),
            "tournament_id":      tid,
            "recommendation_rank": 0,  # will fill after sort
            "bet_type":           "single",
            "market":             market,
            "book":               book,
            "player_name":        row["player_name"],
            "selection_label":    f"{row['player_name']} {market.replace('_', ' ').title()}",
            "card_id":            "",
            "title":              "",
            "selection_count":    1,
            "priced_legs":        1,
            "unpriced_legs":      0,
            "selection_labels":   "",
            "selection_labels_json": f'["{row["player_name"]} {market}"]',
            "odds_american":      int(odds) if not np.isnan(float(odds or 0)) else None,
            "book_prob":          round(book_prob_nv, 6),
            "model_prob":         round(model_prob, 6),
            "edge_pts":           round(edge_pts, 4),
            "ev_per_1":           round(ev, 4) if not np.isnan(ev) else None,
            "confidence":         round(confidence, 4),
            "corroboration_score": 0,
            "corroborated":       False,
            "group_members":      "",
            "status":             "priced",
            "stake_units":        1.0,
            "kelly_fraction":     0.0,
            "outcome_status":     "pending",
            "outcome_win":        "",
            "pnl_per_1":          "",
            "roi_pct":            "",
            "closing_odds_american": "",
            "closing_implied_prob":  "",
            "clv_pts":            "",
            "graded_at":          "",
            # Live extras for display
            "live_score_rank":    mp.get("live_score_rank", 999),
            "rounds_complete":    rounds_complete,
            "is_live_rec":        True,
        })

    if not records:
        print("No edges found above threshold.")
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.sort_values("edge_pts", ascending=False).reset_index(drop=True)
    df["recommendation_rank"] = range(1, len(df) + 1)

    print(f"\nTop live bets ({len(df)} total with edge > 3pp):")
    show = ["player_name", "market", "book", "odds_american", "book_prob", "model_prob", "edge_pts"]
    print(df.head(10)[show].to_string(index=False))

    return df


def save(df: pd.DataFrame, tid: str) -> Path:
    out_path = ODDS_DIR / f"recommended_bets_live_{tid}.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved → {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tid", default=None, help="Tournament ID e.g. R2026011")
    args = parser.parse_args()

    tid = args.tid or _detect_tid()
    if not tid:
        print("Could not detect active tournament. Use --tid.")
        return

    df = generate(tid)
    if not df.empty:
        save(df, tid)
    else:
        print("No live bet file written.")


if __name__ == "__main__":
    main()
