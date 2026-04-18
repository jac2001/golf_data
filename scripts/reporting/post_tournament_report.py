#!/usr/bin/env python3
"""
Post-Tournament Results Report

Grades model predictions and betting recommendations for completed tournaments.
Returns structured data for dashboard rendering OR prints a markdown summary.

Usage:
    python post_tournament_report.py                    # most recent completed
    python post_tournament_report.py --tid R2026475     # specific tournament
    python post_tournament_report.py --all              # season summary
    python post_tournament_report.py --list             # list completed tournaments
    python post_tournament_report.py --save             # save markdown to outputs/reports/
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA         = PROJECT_ROOT / "data"
OUTPUTS      = PROJECT_ROOT / "outputs"
REPORTS_DIR  = OUTPUTS / "reports"

PRED_HISTORY = DATA / "prediction_tracking" / "prediction_history.csv"
BET_RESULTS  = DATA / "odds" / "recommended_bets_results.csv"

# Markets that are part of our actual betting system (exclude API artifacts)
CLEAN_MARKETS = {
    "top5", "top10", "top20", "top30",
    "make_cut", "miss_cut",
    "group_winner", "h2h", "h2h_r1", "h2h_r2", "h2h_r3", "h2h_r4",
    "outright", "r2_leader",
}

_MARKET_LABELS = {
    "top5": "Top 5", "top10": "Top 10", "top20": "Top 20", "top30": "Top 30",
    "make_cut": "Make Cut", "miss_cut": "Miss Cut",
    "group_winner": "3-Ball Win", "h2h": "Matchup", "h2h_r1": "Rd1 Matchup",
    "h2h_r2": "R2 Matchup", "h2h_r3": "R3 Matchup", "h2h_r4": "R4 Matchup",
    "outright": "Win", "r2_leader": "R2 Leader",
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _fmt_pos(pos: float) -> str:
    if pd.isna(pos) or pos >= 999:
        return "MC/WD"
    return "WIN" if pos == 1 else f"T{int(pos)}"

def _fmt_odds(o: float) -> str:
    if pd.isna(o):
        return "—"
    return f"+{int(o)}" if o > 0 else str(int(o))

def _fmt_name(raw: str) -> str:
    """'Last, First' → 'First Last'"""
    parts = raw.replace(", ", " ").split()
    return f"{parts[-1]} {' '.join(parts[:-1])}" if len(parts) > 1 else raw

def _normalize_bools(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Convert string 'True'/'False' columns to actual booleans."""
    for col in cols:
        if col in df.columns:
            df[col] = df[col].map(lambda x: str(x).strip().lower() == "true")
    return df

def _spearman(pred: pd.Series, actual: pd.Series) -> float:
    mask = (actual < 999) & pred.notna()
    if mask.sum() < 10:
        return float("nan")
    r, _ = scipy_stats.spearmanr(-pred[mask], actual[mask])
    return round(float(r), 3)

def _brier(prob: pd.Series, outcome: pd.Series) -> float:
    mask = prob.notna() & outcome.notna()
    if mask.sum() < 5:
        return float("nan")
    return round(float(((prob[mask] - outcome[mask].astype(float)) ** 2).mean()), 4)

def _brier_baseline(outcome: pd.Series) -> float:
    """Naive baseline Brier score: predict the base rate for everyone."""
    mask = outcome.notna()
    if mask.sum() < 5:
        return float("nan")
    base_rate = float(outcome[mask].astype(float).mean())
    return round(float(((base_rate - outcome[mask].astype(float)) ** 2).mean()), 4)

def _load_bets(tid: str | None = None) -> pd.DataFrame:
    """Load bet results filtered to clean markets, deduped to first recommendation."""
    if not BET_RESULTS.exists():
        return pd.DataFrame()
    df = pd.read_csv(BET_RESULTS)
    df = df[df["market"].isin(CLEAN_MARKETS)]
    df = df[df["outcome_status"].notna() & (df["outcome_status"] != "")]
    if tid:
        df = df[df["tournament_id"] == tid].copy()
    df["recommended_at"] = pd.to_datetime(df["recommended_at"], utc=True, errors="coerce")
    df = df.sort_values("recommended_at")
    df = df.drop_duplicates(subset=["tournament_id", "player_name", "market"], keep="first")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def _calibration_table(df: pd.DataFrame, prob_col: str, outcome_col: str,
                        base_rate: float | None = None) -> list[dict]:
    """
    Bucket players by predicted probability, compare to actual hit rate.
    Also computes what a naive model (predicting base_rate for everyone) would score
    in each bucket — this is the 'baseline' to beat.
    """
    buckets = [0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.01]
    labels  = ["<5%", "5–10%", "10–15%", "15–20%", "20–30%", "30–50%", ">50%"]
    rows = []
    for label, (lo, hi) in zip(labels, zip(buckets, buckets[1:])):
        mask = (df[prob_col] >= lo) & (df[prob_col] < hi) & df[outcome_col].notna()
        sub = df[mask]
        if len(sub) < 3:
            continue
        rows.append({
            "bucket":        label,
            "predicted_avg": round(sub[prob_col].mean() * 100, 1),
            "actual_rate":   round(sub[outcome_col].astype(float).mean() * 100, 1),
            "count":         len(sub),
            "baseline":      round((base_rate or 0) * 100, 1),
        })
    return rows


def aggregate_calibration(prob_col: str = "predicted_top10_prob",
                           outcome_col: str = "actual_top10") -> list[dict]:
    """
    Calibration across ALL completed tournaments combined.
    This gives a more statistically stable picture than single-tournament calibration.
    """
    if not PRED_HISTORY.exists():
        return []
    df = pd.read_csv(PRED_HISTORY)
    df = df[df["result_recorded"] == True].copy()
    df = _normalize_bools(df, ["actual_won", "actual_top5", "actual_top10", "actual_top20"])
    if prob_col not in df.columns or outcome_col not in df.columns:
        return []
    base_rate = float(df[outcome_col].astype(float).mean()) if outcome_col in df.columns else None
    return _calibration_table(df, prob_col, outcome_col, base_rate)


# ---------------------------------------------------------------------------
# Edge bucket analysis
# ---------------------------------------------------------------------------

def edge_bucket_analysis(tid: str | None = None) -> list[dict]:
    """
    Group bets by edge tier, show win rate per tier.
    If the model's edge signal is real, higher edge → higher win rate.
    Answers: 'Do our 15pp edge bets win more than our 5pp edge bets?'
    """
    df = _load_bets(tid)
    if df.empty:
        return []

    bins   = [0, 5, 10, 15, 25, 1000]
    labels = ["0–5pp", "5–10pp", "10–15pp", "15–25pp", ">25pp"]
    df["edge_tier"] = pd.cut(df["edge_pts"], bins=bins, labels=labels)

    rows = []
    for tier in labels:
        grp = df[df["edge_tier"] == tier]
        if len(grp) < 2:
            continue
        bets = len(grp)
        wins = int(grp["outcome_win"].astype(float).sum())
        pnl  = round(float(grp["pnl_per_1"].sum()), 2)
        rows.append({
            "tier":     tier,
            "bets":     bets,
            "wins":     wins,
            "hit_rate": round(wins / bets * 100, 1),
            "pnl":      pnl,
            "roi":      round(pnl / bets * 100, 1),
        })
    return rows


# ---------------------------------------------------------------------------
# Prediction analysis (single tournament)
# ---------------------------------------------------------------------------

def analyze_predictions(tid: str) -> dict:
    df = pd.read_csv(PRED_HISTORY)
    df = df[df["tournament_id"] == tid].copy()
    df = df[df["result_recorded"] == True]
    df = _normalize_bools(df, ["actual_won", "actual_top5", "actual_top10", "actual_top20"])

    if df.empty:
        return {"error": f"No results recorded for {tid}"}

    t_name     = df["tournament_name"].iloc[0]
    t_date     = df["tournament_date"].iloc[0] if "tournament_date" in df.columns else ""
    field_size = len(df)

    # Winner — fall back to position=1
    winner_rows = df[df["actual_won"] == True]
    if winner_rows.empty:
        winner_rows = df[df["actual_position"] == 1]

    winner_name          = _fmt_name(winner_rows["player_name"].iloc[0]) if not winner_rows.empty else "Unknown"
    winner_pred_win_pct  = round(winner_rows["predicted_win_prob"].iloc[0] * 100, 1) if not winner_rows.empty else None
    winner_world_rank    = int(winner_rows["world_rank"].iloc[0]) if not winner_rows.empty and "world_rank" in df.columns else None

    # Winner model rank
    if not winner_rows.empty:
        win_prob = winner_rows["predicted_win_prob"].iloc[0]
        winner_model_rank = int((df["predicted_win_prob"] >= win_prob).sum())
    else:
        winner_model_rank = None

    # Rank correlation (how well does model rank correlate with actual finish?)
    # Baseline: random model has r≈0; perfect model has r=1.0; market is ~0.35–0.45
    spearman = _spearman(df["predicted_win_prob"], df["actual_position"])

    # Brier scores — lower is better; baseline = naive model predicting field average for everyone
    brier_top10      = _brier(df["predicted_top10_prob"], df["actual_top10"].astype(float)) if "actual_top10" in df.columns else None
    brier_top10_base = _brier_baseline(df["actual_top10"].astype(float)) if "actual_top10" in df.columns else None
    brier_top20      = _brier(df.get("predicted_top20_prob", pd.Series(dtype=float)), df["actual_top20"].astype(float)) if "predicted_top20_prob" in df.columns and "actual_top20" in df.columns else None
    brier_top20_base = _brier_baseline(df["actual_top20"].astype(float)) if "actual_top20" in df.columns else None

    # Top-N coverage: of our top-N picks, how many actually hit?
    df_sorted = df.sort_values("predicted_win_prob", ascending=False).reset_index(drop=True)
    df_sorted["model_rank"] = df_sorted.index + 1

    def _top_n_coverage(n: int, outcome_col: str) -> dict:
        if outcome_col not in df_sorted.columns:
            return {}
        top_n = df_sorted.head(n)
        hits  = int(top_n[outcome_col].astype(float).sum())
        # Random baseline: n players randomly chosen from field_size, expected hits = n*(n/field_size)
        random_expected = round(n * n / field_size, 1)
        return {"top_n": n, "hits": hits, "pct": round(hits / n * 100, 0), "random_expected": random_expected}

    top5_cover  = _top_n_coverage(5,  "actual_top5")
    top10_cover = _top_n_coverage(10, "actual_top10")
    top20_cover = _top_n_coverage(20, "actual_top20")

    # Calibration
    base_rate_t10 = float(df["actual_top10"].astype(float).mean()) if "actual_top10" in df.columns else None
    cal_top10 = _calibration_table(df, "predicted_top10_prob", "actual_top10", base_rate_t10) if "actual_top10" in df.columns else []

    # Top model picks
    top_picks = []
    for _, row in df_sorted.head(10).iterrows():
        top_picks.append({
            "rank":       int(row["model_rank"]),
            "player":     _fmt_name(row["player_name"]),
            "win_prob":   round(row["predicted_win_prob"] * 100, 1),
            "top10_prob": round(row["predicted_top10_prob"] * 100, 1),
            "actual_pos": _fmt_pos(row["actual_position"]),
            "won":        bool(row["actual_won"]),
            "top10":      bool(row.get("actual_top10", False)),
        })

    return {
        "tournament_id":        tid,
        "tournament_name":      t_name,
        "tournament_date":      t_date,
        "field_size":           field_size,
        "winner_name":          winner_name,
        "winner_model_rank":    winner_model_rank,
        "winner_pred_win_pct":  winner_pred_win_pct,
        "winner_world_rank":    winner_world_rank,
        "spearman_r":           spearman,
        "brier_top10":          brier_top10,
        "brier_top10_baseline": brier_top10_base,
        "brier_top20":          brier_top20,
        "brier_top20_baseline": brier_top20_base,
        "top5_coverage":        top5_cover,
        "top10_coverage":       top10_cover,
        "top20_coverage":       top20_cover,
        "calibration_top10":    cal_top10,
        "top_model_picks":      top_picks,
    }


# ---------------------------------------------------------------------------
# Bet analysis (single tournament)
# ---------------------------------------------------------------------------

def analyze_bets(tid: str) -> dict:
    df = _load_bets(tid)
    if df.empty:
        return {"error": f"No graded clean-market bets for {tid}"}

    total_bets = len(df)
    total_wins = int(df["outcome_win"].astype(float).sum())
    total_pnl  = round(float(df["pnl_per_1"].sum()), 2)
    roi_pct    = round(total_pnl / total_bets * 100, 1) if total_bets else 0
    avg_edge   = round(float(df["edge_pts"].mean()), 1)
    hit_rate   = round(total_wins / total_bets * 100, 1) if total_bets else 0

    clv_rows = df[df["clv_pts"].notna()]
    avg_clv  = round(float(clv_rows["clv_pts"].mean()), 2) if not clv_rows.empty else None

    by_market = []
    for market, grp in df.groupby("market"):
        wins = int(grp["outcome_win"].astype(float).sum())
        bets = len(grp)
        pnl  = round(float(grp["pnl_per_1"].sum()), 2)
        by_market.append({
            "market":   _MARKET_LABELS.get(market, market),
            "bets":     bets,
            "wins":     wins,
            "hit_rate": round(wins / bets * 100, 0) if bets else 0,
            "pnl":      pnl,
            "roi":      round(pnl / bets * 100, 1) if bets else 0,
            "avg_edge": round(float(grp["edge_pts"].mean()), 1),
        })
    by_market.sort(key=lambda x: -x["bets"])

    df["label"] = df["player_name"].apply(_fmt_name)
    winners = df[df["outcome_win"] == True].nlargest(3, "pnl_per_1")
    losers  = df[df["outcome_win"] == False].nsmallest(3, "pnl_per_1")

    best_bets = [
        {"player": r["label"], "market": _MARKET_LABELS.get(r["market"], r["market"]),
         "odds": _fmt_odds(r["odds_american"]), "edge": round(float(r["edge_pts"]), 1),
         "pnl": round(float(r["pnl_per_1"]), 2)}
        for _, r in winners.iterrows()
    ]
    missed_bets = [
        {"player": r["label"], "market": _MARKET_LABELS.get(r["market"], r["market"]),
         "odds": _fmt_odds(r["odds_american"]), "edge": round(float(r["edge_pts"]), 1)}
        for _, r in losers.iterrows()
    ]

    return {
        "tournament_id": tid,
        "total_bets":    total_bets,
        "total_wins":    total_wins,
        "hit_rate":      hit_rate,
        "total_pnl":     total_pnl,
        "roi_pct":       roi_pct,
        "avg_edge":      avg_edge,
        "avg_clv":       avg_clv,
        "by_market":     by_market,
        "best_bets":     best_bets,
        "missed_bets":   missed_bets,
    }


# ---------------------------------------------------------------------------
# Season summary + trend
# ---------------------------------------------------------------------------

def get_completed_tids() -> list[str]:
    if not PRED_HISTORY.exists():
        return []
    df = pd.read_csv(PRED_HISTORY)
    graded = df[df["result_recorded"] == True]
    # Sort by date
    dates = graded.groupby("tournament_id")["tournament_date"].first()
    return list(dates.sort_values().index)


def get_most_recent_completed() -> Optional[str]:
    tids = get_completed_tids()
    return tids[-1] if tids else None


def tournament_trend() -> list[dict]:
    """Per-tournament metrics for trend charts — sorted chronologically."""
    rows = []
    for tid in get_completed_tids():
        p = analyze_predictions(tid)
        b = analyze_bets(tid)
        if "error" in p:
            continue
        rows.append({
            "tid":         tid,
            "name":        p["tournament_name"],
            "short_name":  p["tournament_name"].split()[-1],  # last word for chart labels
            "date":        p.get("tournament_date", ""),
            "winner":      p["winner_name"],
            "winner_rank": p["winner_model_rank"],
            "spearman":    p["spearman_r"],
            "brier_top10": p["brier_top10"],
            "brier_base":  p["brier_top10_baseline"],
            "bet_roi":     b.get("roi_pct") if "error" not in b else None,
            "bet_pnl":     b.get("total_pnl") if "error" not in b else None,
            "total_bets":  b.get("total_bets", 0) if "error" not in b else 0,
            "top10_hits":  p.get("top10_coverage", {}).get("hits"),
        })
    return rows


def season_summary() -> dict:
    tids = get_completed_tids()
    pred_rows, bet_rows = [], []

    for tid in tids:
        p = analyze_predictions(tid)
        b = analyze_bets(tid)
        if "error" not in p:
            pred_rows.append(p)
        if "error" not in b:
            bet_rows.append(b)

    if not pred_rows:
        return {"error": "No completed tournaments found"}

    winner_ranks  = [p["winner_model_rank"] for p in pred_rows if p["winner_model_rank"]]
    spearman_vals = [p["spearman_r"] for p in pred_rows if p["spearman_r"] and not np.isnan(p["spearman_r"])]
    brier_vals    = [p["brier_top10"] for p in pred_rows if p["brier_top10"] and not np.isnan(p["brier_top10"])]
    brier_base    = [p["brier_top10_baseline"] for p in pred_rows if p.get("brier_top10_baseline") and not np.isnan(p["brier_top10_baseline"])]

    total_bets = sum(b["total_bets"] for b in bet_rows)
    total_wins = sum(b["total_wins"] for b in bet_rows)
    total_pnl  = round(sum(b["total_pnl"] for b in bet_rows), 2)
    roi_pct    = round(total_pnl / total_bets * 100, 1) if total_bets else 0

    # Aggregate by market
    market_agg: dict = {}
    for b in bet_rows:
        for m in b["by_market"]:
            k = m["market"]
            if k not in market_agg:
                market_agg[k] = {"bets": 0, "wins": 0, "pnl": 0.0}
            market_agg[k]["bets"] += m["bets"]
            market_agg[k]["wins"] += m["wins"]
            market_agg[k]["pnl"]  += m["pnl"]

    season_by_market = sorted([
        {"market": k, "bets": v["bets"], "wins": v["wins"],
         "hit_rate": round(v["wins"] / v["bets"] * 100, 0) if v["bets"] else 0,
         "pnl": round(v["pnl"], 2),
         "roi": round(v["pnl"] / v["bets"] * 100, 1) if v["bets"] else 0}
        for k, v in market_agg.items()
    ], key=lambda x: -x["bets"])

    # Season-level calibration (all tournaments pooled)
    cal_season = aggregate_calibration()

    # Edge bucket analysis (all tournaments)
    edge_buckets = edge_bucket_analysis()

    # Cumulative PnL trend
    cum_pnl = 0.0
    cum_trend = []
    for b in bet_rows:
        cum_pnl += b["total_pnl"]
        cum_trend.append(round(cum_pnl, 2))

    return {
        "tournaments_graded":    len(pred_rows),
        "tournaments_with_bets": len(bet_rows),
        "per_tournament":        pred_rows,
        # Prediction
        "avg_winner_rank":       round(np.mean(winner_ranks), 1) if winner_ranks else None,
        "pct_winner_top5":       round(sum(r <= 5 for r in winner_ranks) / len(winner_ranks) * 100, 0) if winner_ranks else None,
        "pct_winner_top10":      round(sum(r <= 10 for r in winner_ranks) / len(winner_ranks) * 100, 0) if winner_ranks else None,
        "avg_spearman":          round(np.mean(spearman_vals), 3) if spearman_vals else None,
        "avg_brier_top10":       round(np.mean(brier_vals), 4) if brier_vals else None,
        "avg_brier_baseline":    round(np.mean(brier_base), 4) if brier_base else None,
        # Betting
        "total_bets":            total_bets,
        "total_wins":            total_wins,
        "season_hit_rate":       round(total_wins / total_bets * 100, 1) if total_bets else 0,
        "season_pnl":            total_pnl,
        "season_roi":            roi_pct,
        "season_by_market":      season_by_market,
        "calibration_season":    cal_season,
        "edge_buckets":          edge_buckets,
        "cumulative_pnl_trend":  cum_trend,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Post-tournament results report")
    parser.add_argument("--tid",  help="Tournament ID (e.g. R2026475)")
    parser.add_argument("--all",  action="store_true", help="Season summary")
    parser.add_argument("--list", action="store_true", help="List completed tournaments")
    parser.add_argument("--save", action="store_true", help="Save to outputs/reports/")
    args = parser.parse_args()

    if args.list:
        df = pd.read_csv(PRED_HISTORY)
        graded = df[df["result_recorded"] == True].groupby("tournament_id")
        for tid, grp in graded:
            name = grp["tournament_name"].iloc[0]
            print(f"  {tid}  {name}")
        return

    if args.all:
        s = season_summary()
        if "error" in s:
            print(s["error"]); return
        _print_season(s)
    else:
        tid = args.tid or get_most_recent_completed()
        if not tid:
            print("No completed tournaments found."); return
        p = analyze_predictions(tid)
        b = analyze_bets(tid)
        _print_tournament(p, b)
        if args.save:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"post_tournament_{tid}_{datetime.now().strftime('%Y%m%d')}.md"
            path = REPORTS_DIR / fname
            # Simple markdown dump
            import io, sys
            buf = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = buf
            _print_tournament(p, b)
            sys.stdout = old_stdout
            path.write_text(buf.getvalue())
            print(f"\nSaved to: {path}")


def _print_tournament(p: dict, b: dict):
    if "error" in p:
        print(f"Error: {p['error']}"); return
    print(f"\n# {p['tournament_name']}  ({p['tournament_date']})")
    print(f"Field: {p['field_size']} players\n")
    print(f"WINNER: {p['winner_name']}")
    print(f"  Model rank:  #{p['winner_model_rank']} of {p['field_size']}")
    print(f"  Pre-tourney win prob: {p['winner_pred_win_pct']}%\n")
    print(f"PREDICTION ACCURACY")
    print(f"  Spearman r:     {p['spearman_r']}  (random=0, perfect=1)")
    if p['brier_top10']:
        improvement = round((1 - p['brier_top10'] / p['brier_top10_baseline']) * 100, 1) if p['brier_top10_baseline'] else None
        imp_str = f"  ({improvement}% better than naive)" if improvement else ""
        print(f"  Brier Top-10:   {p['brier_top10']}  baseline={p['brier_top10_baseline']}{imp_str}")
    tc = p.get("top10_coverage", {})
    if tc:
        print(f"  Top-10 hits:    {tc['hits']}/{tc['top_n']}  (random expected: {tc['random_expected']})")
    print()
    if "error" not in b:
        print(f"BETTING  ({b['total_bets']} bets, clean markets only)")
        print(f"  Win rate: {b['hit_rate']}%   P&L: {b['total_pnl']:+.1f} units   ROI: {b['roi_pct']}%")
        if b["avg_clv"] is not None:
            print(f"  Avg CLV: {b['avg_clv']:+.2f}pp")


def _print_season(s: dict):
    print(f"\n# 2026 Season Summary — {s['tournaments_graded']} Tournaments\n")
    print(f"PREDICTION")
    print(f"  Avg winner rank:     #{s['avg_winner_rank']}  (random=#{round(150/2)})")
    print(f"  Winner in top 5:     {s['pct_winner_top5']}%")
    print(f"  Winner in top 10:    {s['pct_winner_top10']}%")
    print(f"  Avg Spearman r:      {s['avg_spearman']}  (random≈0)")
    if s['avg_brier_top10']:
        imp = round((1 - s['avg_brier_top10'] / s['avg_brier_baseline']) * 100, 1) if s['avg_brier_baseline'] else None
        print(f"  Avg Brier Top-10:    {s['avg_brier_top10']}  baseline={s['avg_brier_baseline']}" + (f"  ({imp}% better)" if imp else ""))
    print(f"\nBETTING  (clean markets, {s['total_bets']} bets)")
    print(f"  Win rate:  {s['season_hit_rate']}%")
    print(f"  P&L:       {s['season_pnl']:+.1f} units")
    print(f"  ROI:       {s['season_roi']}%")
    print(f"\nBy market:")
    for m in s["season_by_market"]:
        print(f"  {m['market']:<15}  {m['bets']:>3} bets  {m['hit_rate']:>3.0f}%  {m['pnl']:>+7.1f}u  {m['roi']:>+6.1f}%")
    print(f"\nEdge bucket analysis:")
    for e in s.get("edge_buckets", []):
        print(f"  {e['tier']:<10}  {e['bets']:>3} bets  win={e['hit_rate']}%  ROI={e['roi']:+.1f}%")


if __name__ == "__main__":
    main()
