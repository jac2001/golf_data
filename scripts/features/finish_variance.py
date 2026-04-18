"""
Finish Variance — player boom-or-bust profiling from historical leaderboard data.

What this computes and why:
  Players have characteristic finish distributions. Some players (DJ, Morikawa)
  win regularly but also miss cuts — boom or bust. Others (like a consistent
  T20 grinder) never win but rarely miss cuts either. The model has no concept
  of this. It sees SG stats and world rank but not finish spread.

  Three metrics per player, all derived from their 2016-present PGA Tour results:

  cut_miss_rate:
    What fraction of starts ended in a missed cut.
    High = risky (often out by Friday). Low = reliable weekend player.

  top10_rate:
    What fraction of starts ended in a top-10 finish.
    High = regularly contends. Low = rarely threatens the leaderboard.

  boom_bust_score:
    top10_rate * cut_miss_rate * 100
    The product of the two rates — only truly high if BOTH are high simultaneously.
    A player who makes every cut but never wins scores near zero.
    A player who wins 15% of the time but also misses 20% of cuts scores high.
    This is the "lottery ticket" metric: high upside, high downside.

  finish_std:
    Standard deviation of numeric finishes among made-cut starts only.
    High = finishes swing widely (T2 one week, T55 the next).
    Low = consistent mid-pack or consistently elite.
    We exclude missed cuts here because including them inflates the number for
    everyone — we want to measure variability *when they do make the cut*.

How it's used:
  Merged into the prediction feature matrix before model scoring.
  Also used as a post-processing signal to adjust top-10/top-20 probabilities:
    - High boom_bust → slightly boost win_prob, reduce top10/top20
    - Low boom_bust  → slightly reduce win_prob, boost top10/top20

  This corrects a known model bias: it treats all players at a given SG level
  as equally likely to finish top-10. In reality, a boom-or-bust player at
  +1.5 SG is less reliable for a top-10 bet than a grinder at +1.5 SG.

Usage:
  from scripts.features.finish_variance import compute_finish_variance
  variance_df = compute_finish_variance()   # returns DataFrame, player_name as index
"""

from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HIST_DIR     = PROJECT_ROOT / "data" / "historical"

# Sentinel value we assign to missed-cut finishes for numeric calculations.
# We don't use 999 because that would mean a player who goes CUT every week
# has an enormous mean finish — we just flag them separately.
_CUT_SENTINEL = 100

# Minimum starts required to trust the computed stats.
# Below this, we return neutral/median values rather than noisy extremes.
_MIN_STARTS = 15


def _parse_position(pos: str) -> float | None:
    """Convert a position string to a numeric finish.

    'T13' → 13, '1' → 1, 'CUT' → _CUT_SENTINEL, 'W/D' → _CUT_SENTINEL.
    Returns None for anything unparseable (excluded from calculations).
    """
    s = str(pos).strip().upper()
    if s in ("CUT", "W/D", "WD", "DQ", "MDF"):
        return float(_CUT_SENTINEL)
    s = s.lstrip("T")
    try:
        return float(s)
    except ValueError:
        return None


def compute_finish_variance(
    min_year: int = 2019,
    min_starts: int = _MIN_STARTS,
) -> pd.DataFrame:
    """
    Load all historical leaderboard CSVs and compute per-player finish variance stats.

    min_year: only use results from this year onward. 2019 is a good default —
              going back to 2016 includes players whose games have changed a lot.
              More recent data is more predictive.

    min_starts: players with fewer starts than this get neutral values.
                We don't want to call a player a "boom-or-bust" based on 5 starts.

    Returns a DataFrame with one row per player:
        player_name       — matches leaderboard/predictions CSV format (First Last)
        career_starts     — total starts in the window
        cut_miss_rate     — fraction of starts ending in missed cut
        top10_rate        — fraction of starts with top-10 finish
        boom_bust_score   — top10_rate * cut_miss_rate * 100 (0–25 scale roughly)
        finish_std        — std dev of numeric finishes (made cuts only)
        low_variance      — bool: std < 15 AND cut_miss_rate < 0.2 (consistent player)
    """
    # ── Load all leaderboard CSVs ────────────────────────────────────────────
    files = sorted(glob.glob(str(HIST_DIR / "leaderboards_*.csv")))
    if not files:
        raise FileNotFoundError(f"No leaderboard CSVs found in {HIST_DIR}")

    dfs = []
    for f in files:
        df = pd.read_csv(f)
        # Filter by year if year column exists
        if "year" in df.columns:
            df = df[df["year"] >= min_year]
        dfs.append(df)

    lb = pd.concat(dfs, ignore_index=True)
    lb["finish_num"] = lb["position"].apply(_parse_position)
    lb = lb[lb["finish_num"].notna()].copy()

    # ── Per-player aggregation ───────────────────────────────────────────────
    records = []
    for name, group in lb.groupby("player_name"):
        starts      = len(group)
        cuts_missed = int((group["finish_num"] == _CUT_SENTINEL).sum())
        top10s      = int((group["finish_num"] <= 10).sum())
        wins        = int((group["finish_num"] == 1).sum())

        # Std dev only on made-cut finishes
        made_cut_finishes = group.loc[group["finish_num"] < _CUT_SENTINEL, "finish_num"]
        finish_std = float(made_cut_finishes.std()) if len(made_cut_finishes) >= 5 else np.nan

        cut_miss_rate = cuts_missed / starts
        top10_rate    = top10s / starts
        boom_bust     = top10_rate * cut_miss_rate * 100

        records.append({
            "player_name":     name,
            "career_starts":   starts,
            "wins":            wins,
            "cut_miss_rate":   round(cut_miss_rate, 4),
            "top10_rate":      round(top10_rate, 4),
            "boom_bust_score": round(boom_bust, 4),
            "finish_std":      round(finish_std, 2) if not np.isnan(finish_std) else np.nan,
        })

    df_out = pd.DataFrame(records)

    # ── Mark low-variance (consistent) players ──────────────────────────────
    # A consistent player: tight finish spread AND rarely misses cuts.
    # These are the players whose top-10/top-20 probabilities are most reliable.
    df_out["low_variance"] = (
        (df_out["finish_std"] < 15)
        & (df_out["cut_miss_rate"] < 0.20)
    ).astype(int)

    # ── Neutral fill for low-sample players ─────────────────────────────────
    # Players with < min_starts get field-median values so they don't distort
    # post-processing adjustments in either direction.
    low_sample = df_out["career_starts"] < min_starts
    for col in ("cut_miss_rate", "top10_rate", "boom_bust_score", "finish_std"):
        median_val = df_out.loc[~low_sample, col].median()
        df_out.loc[low_sample, col] = median_val
    df_out.loc[low_sample, "low_variance"] = 0

    print(f"  Finish variance: computed stats for {len(df_out):,} players "
          f"({int(low_sample.sum())} below {min_starts}-start threshold → neutral values)")

    return df_out.set_index("player_name")


if __name__ == "__main__":
    df = compute_finish_variance()
    print("\nTop boom-or-bust players (min 30 starts):")
    top = df[df["career_starts"] >= 30].nlargest(10, "boom_bust_score")
    print(top[["career_starts", "wins", "top10_rate", "cut_miss_rate", "boom_bust_score", "finish_std"]].to_string())
    print("\nMost consistent players (low_variance=1, min 30 starts):")
    cons = df[(df["low_variance"] == 1) & (df["career_starts"] >= 30)].nlargest(10, "top10_rate")
    print(cons[["career_starts", "wins", "top10_rate", "cut_miss_rate", "boom_bust_score", "finish_std"]].to_string())
