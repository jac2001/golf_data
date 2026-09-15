#!/usr/bin/env python3
"""
DataGolf Accuracy Trend Check
=============================
Our walk-forward CV found a monotonic decline in top-10 ranking accuracy:

    ours (within-event AUC): 2023: 0.765 → 2024: 0.742 → 2025: 0.717 → 2026: 0.684

Question: did DataGolf — a completely independent model — decline over the same
span? If yes: the game itself got harder to predict (parity), and our decline is
absolved. If their accuracy held flat: the problem is ours after all.

Data:
  data/datagolf/dg_archive_all.csv        — DG probs + actual finish, 2020-2025
  data/datagolf/dg_pre_tournament_R2026*  — 2026 snapshots (joined to results)

Usage:
    python3 scripts/validation/dg_trend_check.py

────────────────────────────────────────────────────────────────────────────
YOUR PART: two functions marked TODO(you). The 2026 assembly join is fiddly
name-matching plumbing, so it's provided. Suggested order: parse_finish first
(run the script — it self-tests parse_finish before anything else).
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DG_DIR       = PROJECT_ROOT / "data" / "datagolf"
PRED_HISTORY = PROJECT_ROOT / "data" / "prediction_tracking" / "prediction_history.csv"

# Our walk-forward within-event top10 AUC, for the final comparison table
OURS = {2023: 0.765, 2024: 0.742, 2025: 0.717, 2026: 0.684}


# ── TODO(you) #1 ──────────────────────────────────────────────────────────────

def parse_finish(fin_text: str) -> int | None:
    """Convert a finish string to a top-10 label: 1, 0, or None (exclude row).

    Real values in the data: "1", "3", "T12", "T4", "CUT", "WD", "DQ", "MDF",
    and occasionally blank/NaN.

    Rules:
      - numeric finishes (with or without the "T"): 1 if position <= 10 else 0
      - "CUT" and "MDF" (made cut, didn't finish): 0 — they played and did
        not crack the top 10
      - "WD" / "DQ" / blank / unparseable: None — they didn't complete the
        tournament under normal conditions; scoring them either way would
        bias the metric. Callers drop None rows.

    Hint: str(fin_text).strip().upper(), handle the sentinel strings first,
    then strip a leading "T" and try int(). Wrap the int in try/except.
    """
    fin_text = str(fin_text).strip().upper()
    if fin_text in {"CUT", "MDF"}:
        return 0
    if fin_text in {"WD", "DQ", ""}:
        return None
    if fin_text.startswith("T"):
        fin_text = fin_text[1:]
    try:
        pos = int(fin_text)
        return 1 if pos <= 10 else 0
    except ValueError:
        return None
    


# ── TODO(you) #2 ──────────────────────────────────────────────────────────────

def yearly_auc(df: pd.DataFrame) -> dict:
    """Per-year DG top-10 accuracy, both ways we've learned to measure it.

    Input df columns: year, event_id, dg_top10 (probability), y (0/1 label).
    Return {year: {"pooled": float, "within": float, "events": int}}.

    - pooled: roc_auc_score over all the year's rows at once
    - within: mean of per-event AUCs (skip events with < 3 positives or
      all-one-class — remember the same guard from the pooling investigation)

    Why both: our decline showed up in BOTH pooled and within-event AUC.
    If DG's does too, the parallel is exact.
    """
    return {year: {"pooled": roc_auc_score(df_year["y"], df_year["dg_top10"]),
                   "within": np.mean([roc_auc_score(g["y"], g["dg_top10"]) for _, g in df_year.groupby("event_id")
                                      if len(g["y"].unique()) > 1 and g["y"].sum() >= 3]),
                   "events": df_year["event_id"].nunique()}
            for year, df_year in df.groupby("year")}


# ── Provided plumbing ─────────────────────────────────────────────────────────

def _norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return " ".join(sorted(re.sub(r"[^a-z\s]", " ", s.lower()).split()))


def load_archive() -> pd.DataFrame:
    """2020-2025 DG archive → year, event_id, dg_top10, y (via parse_finish)."""
    df = pd.read_csv(DG_DIR / "dg_archive_all.csv")
    df["y"] = df["fin_text"].apply(parse_finish)
    df = df.dropna(subset=["y", "dg_top10"]).copy()
    df["y"] = df["y"].astype(int)
    return df[["year", "event_id", "dg_top10", "y"]]


def load_2026() -> pd.DataFrame:
    """2026 snapshots joined to settled results by normalized name → same shape."""
    hist = pd.read_csv(PRED_HISTORY)
    hist = hist[hist["result_recorded"] == True].copy()  # noqa: E712
    hist["_key"] = hist["player_name"].apply(_norm_name)
    top10 = hist["actual_top10"].astype(str).str.lower().map(
        {"true": 1, "1": 1, "1.0": 1, "false": 0, "0": 0, "0.0": 0})
    hist["y"] = top10

    frames = []
    for f in sorted(DG_DIR.glob("dg_pre_tournament_R2026*.csv")):
        tid = f.stem.replace("dg_pre_tournament_", "")
        dg = pd.read_csv(f)
        if "player_name" not in dg.columns:      # team events
            continue
        dg = dg[dg["model"] == "baseline_history_fit"].copy()
        dg["_key"] = dg["player_name"].apply(_norm_name)
        ours = hist[hist["tournament_id"] == tid][["_key", "y"]].dropna()
        m = dg.merge(ours, on="_key", how="inner")
        if len(m) < 20:
            continue
        frames.append(pd.DataFrame({
            "year": 2026, "event_id": tid,
            "dg_top10": m["top_10"], "y": m["y"].astype(int),
        }))
    return pd.concat(frames, ignore_index=True)


def main():
    # Self-test parse_finish before touching real data
    checks = [("1", 1), ("T4", 1), ("10", 1), ("T10", 1), ("T11", 0),
              ("57", 0), ("CUT", 0), ("MDF", 0), ("WD", None), ("DQ", None)]
    for raw, want in checks:
        got = parse_finish(raw)
        assert got == want, f"parse_finish({raw!r}) = {got!r}, expected {want!r}"
    print("parse_finish: all self-tests pass")

    df = pd.concat([load_archive(), load_2026()], ignore_index=True)
    print(f"{len(df):,} DG predictions across {df['year'].nunique()} years\n")

    stats = yearly_auc(df)
    print("year | events | DG pooled | DG within | ours within")
    for year in sorted(stats):
        s = stats[year]
        ours = f"{OURS[year]:.3f}" if year in OURS else "  —  "
        print(f"{year} |   {s['events']:3d}  |   {s['pooled']:.3f}   |   {s['within']:.3f}   |   {ours}")


if __name__ == "__main__":
    main()
