#!/usr/bin/env python3
"""
Model vs DataGolf Benchmark
===========================
Head-to-head comparison of our pre-tournament predictions against DataGolf's,
scored on settled results. Only uses DG snapshots saved BEFORE each tournament
(point-in-time, no lookahead) — the same standard our prediction_history holds.

For every tournament with both a dg_pre_tournament_R{tid}.csv snapshot and
graded rows in prediction_history.csv, joins on player name and scores each
market (win / top5 / top10 / top20) with:

  - Log loss   (lower = better; the standard probabilistic scoring rule)
  - Brier score (lower = better; mean squared error of probabilities)
  - Calibration ratio (actual rate / predicted rate; 1.00 = perfectly calibrated)
  - Spearman rank correlation of win prob vs actual finish position

Outputs:
  outputs/benchmark_vs_dg.csv          — per-event, per-market, per-model metrics
  outputs/benchmark_vs_dg_summary.json — overall summary (feeds the site)

Usage:
    python3 scripts/validation/benchmark_vs_datagolf.py
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DG_DIR       = PROJECT_ROOT / "data" / "datagolf"
PRED_HISTORY = PROJECT_ROOT / "data" / "prediction_tracking" / "prediction_history.csv"
OUT_CSV      = PROJECT_ROOT / "outputs" / "benchmark_vs_dg.csv"
OUT_JSON     = PROJECT_ROOT / "outputs" / "benchmark_vs_dg_summary.json"

MARKETS = {
    "win":   ("predicted_win_prob",   "actual_won",   "win"),
    "top5":  ("predicted_top5_prob",  "actual_top5",  "top_5"),
    "top10": ("predicted_top10_prob", "actual_top10", "top_10"),
    "top20": ("predicted_top20_prob", "actual_top20", "top_20"),
}

EPS = 1e-6


def _norm_name(name: str) -> str:
    """'Åberg, Ludvig' → 'aberg ludvig' — sorted lowercase ascii tokens."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    tokens = re.sub(r"[^a-z\s]", " ", s.lower()).split()
    return " ".join(sorted(tokens))


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def load_history() -> pd.DataFrame:
    hist = pd.read_csv(PRED_HISTORY)
    hist = hist[hist["result_recorded"] == True].copy()  # noqa: E712
    hist["_key"] = hist["player_name"].apply(_norm_name)
    return hist


def find_benchmark_events(hist: pd.DataFrame) -> list[str]:
    """Tournaments with both a DG snapshot and settled predictions."""
    settled = set(hist["tournament_id"].unique())
    events = []
    for f in sorted(DG_DIR.glob("dg_pre_tournament_R*.csv")):
        tid = f.stem.replace("dg_pre_tournament_", "")
        if tid in settled:
            events.append(tid)
    return events


def score_event(tid: str, hist: pd.DataFrame) -> list[dict]:
    """Score our model + both DG models on one event. Returns metric rows."""
    dg = pd.read_csv(DG_DIR / f"dg_pre_tournament_{tid}.csv")
    if "player_name" not in dg.columns:  # team events (e.g. Zurich) — no individual odds
        print(f"  {tid}: team-format snapshot, skipping")
        return []
    dg["_key"] = dg["player_name"].apply(_norm_name)

    ours = hist[hist["tournament_id"] == tid].copy()
    name = ours["tournament_name"].iloc[0] if len(ours) else tid

    rows = []
    for dg_model in ("baseline", "baseline_history_fit"):
        dgm = dg[dg["model"] == dg_model][["_key", "win", "top_5", "top_10", "top_20"]]
        merged = ours.merge(dgm, on="_key", how="inner")
        if len(merged) < 20:
            continue

        # Actual finish position for rank correlation (CUT → worst + 1)
        pos = pd.to_numeric(
            merged["actual_position"].astype(str).str.replace("T", "", regex=False),
            errors="coerce",
        )
        pos = pos.fillna(pos.max() + 1)

        for market, (our_col, actual_col, dg_col) in MARKETS.items():
            sub = merged.dropna(subset=[our_col, actual_col, dg_col])
            if len(sub) < 20:
                continue
            y = (sub[actual_col].astype(str).str.lower()
                 .map({"true": 1.0, "1": 1.0, "1.0": 1.0,
                       "false": 0.0, "0": 0.0, "0.0": 0.0}).values)

            for model_label, probs in ((f"dg_{dg_model}", sub[dg_col].values),
                                       ("ours", sub[our_col].values)):
                # Only score "ours" once (identical across dg_model loops)
                if model_label == "ours" and dg_model != "baseline":
                    continue
                probs = np.asarray(probs, dtype=float)
                rows.append({
                    "tournament_id":   tid,
                    "tournament_name": name,
                    "model":           model_label,
                    "market":          market,
                    "n":               len(sub),
                    "log_loss":        round(log_loss(y, probs), 5),
                    "brier":           round(brier(y, probs), 5),
                    "pred_rate":       round(float(np.mean(probs)), 5),
                    "actual_rate":     round(float(np.mean(y)), 5),
                })

        # Rank correlation: win prob vs finish position (per model, once each)
        for model_label, col in ((f"dg_{dg_model}", "win"), ("ours", "predicted_win_prob")):
            if model_label == "ours" and dg_model != "baseline":
                continue
            sub = merged.dropna(subset=[col])
            p = pos.loc[sub.index]
            rho, _ = spearmanr(sub[col], -p)  # higher prob should mean better (lower) finish
            rows.append({
                "tournament_id":   tid,
                "tournament_name": name,
                "model":           model_label,
                "market":          "rank_corr",
                "n":               len(sub),
                "log_loss":        None,
                "brier":           None,
                "pred_rate":       None,
                "actual_rate":     round(float(rho), 4),
            })

    return rows


def main():
    hist = load_history()
    events = find_benchmark_events(hist)
    print(f"Benchmarking {len(events)} settled tournaments with DG snapshots:")
    for tid in events:
        print(f"  {tid}")

    all_rows = []
    for tid in events:
        all_rows.extend(score_event(tid, hist))

    df = pd.DataFrame(all_rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nSaved per-event metrics → {OUT_CSV.relative_to(PROJECT_ROOT)}")

    # ── Overall summary: pooled across events, weighted by n ──────────────────
    summary: dict = {"events": len(events), "tournaments": events, "markets": {}}
    metrics_df = df[df["market"] != "rank_corr"]

    print(f"\n{'='*72}")
    print(f"  OVERALL — {len(events)} tournaments, pooled")
    print(f"{'='*72}")
    print(f"  {'market':<8} {'model':<24} {'log_loss':>9} {'brier':>8} {'calib':>7} {'n':>6}")
    print(f"  {'-'*68}")

    for market in MARKETS:
        mkt = metrics_df[metrics_df["market"] == market]
        summary["markets"][market] = {}
        for model in ("ours", "dg_baseline", "dg_baseline_history_fit"):
            m = mkt[mkt["model"] == model]
            if m.empty:
                continue
            w = m["n"]
            ll  = float(np.average(m["log_loss"], weights=w))
            br  = float(np.average(m["brier"], weights=w))
            pr  = float(np.average(m["pred_rate"], weights=w))
            ar  = float(np.average(m["actual_rate"], weights=w))
            calib = ar / pr if pr > 0 else None
            summary["markets"][market][model] = {
                "log_loss": round(ll, 5), "brier": round(br, 5),
                "pred_rate": round(pr, 4), "actual_rate": round(ar, 4),
                "calibration": round(calib, 3) if calib else None,
                "n": int(w.sum()),
            }
            print(f"  {market:<8} {model:<24} {ll:>9.5f} {br:>8.5f} {calib:>7.3f} {int(w.sum()):>6}")
        print()

    # Rank correlation summary
    rc = df[df["market"] == "rank_corr"]
    summary["rank_corr"] = {}
    print(f"  {'rank correlation (win prob vs finish)':<40}")
    for model in ("ours", "dg_baseline", "dg_baseline_history_fit"):
        m = rc[rc["model"] == model]
        if m.empty:
            continue
        avg = float(np.average(m["actual_rate"], weights=m["n"]))
        summary["rank_corr"][model] = round(avg, 4)
        print(f"    {model:<24} {avg:.4f}")

    with open(OUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary → {OUT_JSON.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
