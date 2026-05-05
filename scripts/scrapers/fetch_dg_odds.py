#!/usr/bin/env python3
"""
DataGolf Betting Tools Odds Fetcher
=====================================

Fetches live odds from DataGolf's betting tools endpoints:
  - Outrights: win, top_5, top_10, top_20, make_cut
  - Matchups:  round_matchups

Saves to:
  data/datagolf/dg_odds_{tid}.json          combined raw JSON, all markets
  data/datagolf/dg_outrights_{tid}.csv      flat: one row per player × book × market
  data/datagolf/dg_matchups_{tid}.csv       flat: one row per matchup × book

DG model probs are included as book="datagolf" with baseline_history_fit preferred.

Usage:
    python scripts/scrapers/fetch_dg_odds.py --tournament-id R2026012
    python scripts/scrapers/fetch_dg_odds.py --tournament-id R2026012 --market matchups
    python scripts/scrapers/fetch_dg_odds.py --tournament-id R2026012 --market top_10
    python scripts/scrapers/fetch_dg_odds.py --tournament-id R2026012 --market all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DG_DIR = DATA_DIR / "datagolf"
DG_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.scrapers.dg_client import dg_get, DG_BASE

# US-accessible books we care about for betting recommendations
US_BOOKS = {"draftkings", "fanduel", "betmgm", "caesars", "pointsbet", "betonline", "bovada", "unibet"}
# Sharp reference books (most efficient markets, use for true-price edge calculation)
SHARP_BOOKS = {"pinnacle", "betcris", "bet365"}
ALL_BOOKS = US_BOOKS | SHARP_BOOKS

OUTRIGHT_MARKETS = ["win", "top_5", "top_10", "top_20", "make_cut"]


# ── API helpers ───────────────────────────────────────────────────────────────


def american_to_prob(odds_str) -> float | None:
    """Convert American odds string (e.g. '-138', '+240') to implied probability."""
    if odds_str is None or str(odds_str).strip().lower() in ("null", "nan", ""):
        return None
    try:
        o = int(str(odds_str).replace("+", "").strip())
    except ValueError:
        return None
    if o == 0:
        return None
    if o > 0:
        return 100.0 / (o + 100.0)
    return abs(o) / (abs(o) + 100.0)


def no_vig_prob(prob_a: float, prob_b: float) -> tuple[float, float]:
    """Remove vig from a two-way market."""
    total = prob_a + prob_b
    if total <= 0:
        return 0.5, 0.5
    return prob_a / total, prob_b / total


# ── Fetchers ──────────────────────────────────────────────────────────────────

def fetch_outrights(market: str) -> dict:
    """Fetch outright odds for a single market (win/top_5/top_10/top_20/make_cut)."""
    return dg_get("/betting-tools/outrights", {"tour": "pga", "market": market, "odds_format": "american"})


def fetch_matchups(market: str = "round_matchups") -> dict:
    """Fetch matchup odds. market: 'round_matchups' or 'tournament_matchups'."""
    return dg_get("/betting-tools/matchups", {"tour": "pga", "market": market, "odds_format": "american"})


# ── Flatteners ────────────────────────────────────────────────────────────────

def flatten_outrights(raw: dict, market: str) -> pd.DataFrame:
    """Flatten raw outright JSON into one row per player × book.

    Columns: market, player_name, dg_id, book, odds_american, implied_prob, is_dg_model, is_sharp
    """
    rows = []
    event_name = raw.get("event_name", "")
    last_updated = raw.get("last_updated", "")

    odds_data = raw.get("odds", [])
    if not isinstance(odds_data, list):
        return pd.DataFrame()  # e.g. tournament is live → "No make_cut bets offered"
    for player in odds_data:
        name = player.get("player_name", "")
        dg_id = player.get("dg_id")

        # Regular sportsbooks
        for book in ALL_BOOKS:
            val = player.get(book)
            if val is None or str(val).strip().lower() in ("null", ""):
                continue
            prob = american_to_prob(val)
            if prob is None:
                continue
            rows.append({
                "market": market,
                "player_name": name,
                "dg_id": dg_id,
                "book": book,
                "odds_american": str(val),
                "implied_prob": round(prob, 6),
                "is_dg_model": False,
                "is_sharp": book in SHARP_BOOKS,
                "event_name": event_name,
                "last_updated": last_updated,
            })

        # DataGolf model (baseline_history_fit preferred, fallback to baseline)
        dg_obj = player.get("datagolf")
        if isinstance(dg_obj, dict):
            dg_odds = dg_obj.get("baseline_history_fit") or dg_obj.get("baseline")
            if dg_odds:
                prob = american_to_prob(dg_odds)
                if prob:
                    rows.append({
                        "market": market,
                        "player_name": name,
                        "dg_id": dg_id,
                        "book": "datagolf",
                        "odds_american": str(dg_odds),
                        "implied_prob": round(prob, 6),
                        "is_dg_model": True,
                        "is_sharp": False,
                        "event_name": event_name,
                        "last_updated": last_updated,
                    })

    return pd.DataFrame(rows)


def flatten_matchups(raw: dict) -> pd.DataFrame:
    """Flatten raw matchup JSON into one row per matchup × book.

    Columns: p1_name, p2_name, p1_dg_id, p2_dg_id, ties, book,
             p1_odds, p2_odds, p1_prob, p2_prob, p1_novig, p2_novig, is_dg_model, is_sharp
    """
    rows = []
    event_name = raw.get("event_name", "")
    last_updated = raw.get("last_updated", "")

    for m in raw.get("match_list", []):
        p1 = m.get("p1_player_name", "")
        p2 = m.get("p2_player_name", "")
        p1_id = m.get("p1_dg_id")
        p2_id = m.get("p2_dg_id")
        ties = m.get("ties", "void")
        odds_dict = m.get("odds", {})

        for book, book_odds in odds_dict.items():
            if not isinstance(book_odds, dict):
                continue
            o1 = book_odds.get("p1")
            o2 = book_odds.get("p2")
            if o1 is None or o2 is None:
                continue
            pr1 = american_to_prob(o1)
            pr2 = american_to_prob(o2)
            if pr1 is None or pr2 is None:
                continue
            nv1, nv2 = no_vig_prob(pr1, pr2)
            is_dg = (book == "datagolf")
            rows.append({
                "p1_name": p1,
                "p2_name": p2,
                "p1_dg_id": p1_id,
                "p2_dg_id": p2_id,
                "ties": ties,
                "book": book,
                "p1_odds": str(o1),
                "p2_odds": str(o2),
                "p1_prob": round(pr1, 6),
                "p2_prob": round(pr2, 6),
                "p1_novig": round(nv1, 6),
                "p2_novig": round(nv2, 6),
                "is_dg_model": is_dg,
                "is_sharp": book in SHARP_BOOKS,
                "event_name": event_name,
                "last_updated": last_updated,
            })

    return pd.DataFrame(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

MARKET_CHOICES = OUTRIGHT_MARKETS + ["matchups", "tournament_matchups", "all"]


def main():
    parser = argparse.ArgumentParser(description="Fetch DataGolf betting odds")
    parser.add_argument("--tournament-id", required=True, help="e.g. R2026012")
    parser.add_argument(
        "--market", default="all",
        choices=MARKET_CHOICES,
        help="Which market(s) to fetch. Default: all",
    )
    args = parser.parse_args()
    tid = args.tournament_id.upper()

    fetch_outrights_flag          = args.market in OUTRIGHT_MARKETS or args.market == "all"
    fetch_round_matchups_flag     = args.market in ("matchups", "all")
    fetch_tourn_matchups_flag     = args.market in ("tournament_matchups", "all")
    specific_market               = args.market if args.market in OUTRIGHT_MARKETS else None

    combined: dict = {"tournament_id": tid, "fetched_at": datetime.now(timezone.utc).isoformat()}
    outright_frames: list[pd.DataFrame] = []

    # ── Outrights ──
    markets_to_fetch = [specific_market] if specific_market else OUTRIGHT_MARKETS
    if fetch_outrights_flag:
        for mkt in markets_to_fetch:
            print(f"[INFO] Fetching outrights: {mkt}...")
            try:
                raw = fetch_outrights(mkt)
                combined[f"outrights_{mkt}"] = raw
                df = flatten_outrights(raw, mkt)
                if df.empty:
                    print(f"  → No data for {mkt}: {raw.get('notes', raw.get('odds', ''))}")
                    continue
                outright_frames.append(df)
                n_players = df["player_name"].nunique()
                n_books = df[~df["is_dg_model"]]["book"].nunique()
                print(f"  → {n_players} players × {n_books} books  (event: {raw.get('event_name')})")
            except Exception as e:
                print(f"  [WARN] {mkt} failed: {e}")

    # ── Round Matchups (3-ball pairings) ──
    df_m = pd.DataFrame()
    if fetch_round_matchups_flag:
        print("[INFO] Fetching round matchups (3-ball)...")
        try:
            raw_m = fetch_matchups("round_matchups")
            combined["matchups"] = raw_m
            match_list = raw_m.get("match_list", [])
            if not isinstance(match_list, list):
                print(f"  → No round matchups: {raw_m.get('notes', match_list)}")
            else:
                df_m = flatten_matchups(raw_m)
                n_matchups = df_m[df_m["is_dg_model"]]["p1_name"].nunique() if not df_m.empty else 0
                book_counts = df_m[~df_m["is_dg_model"]]["book"].value_counts().to_dict() if not df_m.empty else {}
                print(f"  → {n_matchups} round matchups | Books: {book_counts}")
        except Exception as e:
            print(f"  [WARN] round matchups failed: {e}")

    # ── Tournament Matchups (head-to-head, full tournament) ──
    df_tm = pd.DataFrame()
    if fetch_tourn_matchups_flag:
        print("[INFO] Fetching tournament matchups (H2H)...")
        try:
            raw_tm = fetch_matchups("tournament_matchups")
            combined["tournament_matchups"] = raw_tm
            match_list_tm = raw_tm.get("match_list", [])
            if not isinstance(match_list_tm, list):
                print(f"  → No tournament matchups: {raw_tm.get('notes', match_list_tm)}")
            else:
                df_tm = flatten_matchups(raw_tm)
                n_tm = df_tm[df_tm["is_dg_model"]]["p1_name"].nunique() if not df_tm.empty else 0
                book_counts_tm = df_tm[~df_tm["is_dg_model"]]["book"].value_counts().to_dict() if not df_tm.empty else {}
                print(f"  → {n_tm} tournament matchups | Books: {book_counts_tm}")
        except Exception as e:
            print(f"  [WARN] tournament matchups failed: {e}")

    # ── Save ──
    combined_path = DG_DIR / f"dg_odds_{tid}.json"
    with open(combined_path, "w") as f:
        json.dump(combined, f, indent=2, default=str)
    print(f"\n[OK] Raw JSON → {combined_path}")

    if outright_frames:
        out_df = pd.concat(outright_frames, ignore_index=True)
        out_path = DG_DIR / f"dg_outrights_{tid}.csv"
        out_df.to_csv(out_path, index=False)
        print(f"[OK] Outrights CSV → {out_path}  ({len(out_df)} rows)")

    if not df_m.empty:
        m_path = DG_DIR / f"dg_matchups_{tid}.csv"
        df_m.to_csv(m_path, index=False)
        print(f"[OK] Round Matchups CSV → {m_path}  ({len(df_m)} rows)")

    if not df_tm.empty:
        tm_path = DG_DIR / f"dg_tourn_matchups_{tid}.csv"
        df_tm.to_csv(tm_path, index=False)
        print(f"[OK] Tournament Matchups CSV → {tm_path}  ({len(df_tm)} rows)")

    # ── Summary ──
    if not df_m.empty:
        dg_m = df_m[df_m["is_dg_model"]]
        pin_m = df_m[df_m["book"] == "pinnacle"]
        print(f"\nRound matchup coverage:  DG model={len(dg_m)}  Pinnacle={len(pin_m)}")
    if not df_tm.empty:
        dg_tm = df_tm[df_tm["is_dg_model"]]
        pin_tm = df_tm[df_tm["book"] == "pinnacle"]
        print(f"Tourn matchup coverage:  DG model={len(dg_tm)}  Pinnacle={len(pin_tm)}")

    if outright_frames:
        _all_outrights = pd.concat(outright_frames, ignore_index=True)
        if not _all_outrights.empty and "market" in _all_outrights.columns:
            for mkt in (markets_to_fetch if specific_market else OUTRIGHT_MARKETS):
                sub = _all_outrights[_all_outrights["market"] == mkt]
                if sub.empty:
                    continue
                fd_n  = sub[sub["book"] == "fanduel"]["player_name"].nunique()
                pin_n = sub[sub["book"] == "pinnacle"]["player_name"].nunique()
                dg_n  = sub[sub["is_dg_model"]]["player_name"].nunique()
                print(f"  {mkt:<10} FanDuel={fd_n}  Pinnacle={pin_n}  DG model={dg_n}")


if __name__ == "__main__":
    main()
