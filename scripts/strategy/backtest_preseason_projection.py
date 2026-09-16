#!/usr/bin/env python3
"""
Preseason Projection Backtest — the gate for Strategy Mode
==========================================================
Question: using ONLY data through 2025, can we project — for each player —
which 2026 events would be their most valuable weeks? If yes, the season
optimizer has a real objective. If no, it would optimize noise and Strategy
Mode should stay heuristic.

For every (player, 2026 event):
    projected_ev = P(in field) × E[earnings | plays]

Scored against what actually happened in 2026, per player, as a rank
correlation across that player's events. The projection must beat the
PURSE-ONLY BASELINE — "big events pay more" is free knowledge, and any
projection that can't out-order it adds nothing.

Usage:
    python3 scripts/strategy/backtest_preseason_projection.py

────────────────────────────────────────────────────────────────────────────
YOUR PART: three functions marked TODO(you) — p_in_field, expected_earnings,
score_projection. Data loading, earnings parsing/imputation, and the driver
are provided. The driver self-checks each piece as you go.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "database"))
from db import get_conn  # noqa: E402

TRAIN_YEARS = range(2010, 2026)   # projection may use ONLY these
TARGET_YEAR = 2026                # scored against this — never an input

# Winner's share of purse under the standard distribution — used to infer an
# event's purse from its recorded winner earnings when no schedule purse exists.
WINNER_SHARE = 0.18


# ── Provided plumbing ─────────────────────────────────────────────────────────

def _parse_earnings(v) -> float | None:
    s = str(v).replace("$", "").replace(",", "").strip()
    try:
        f = float(s)
        return f if f >= 0 else None
    except ValueError:
        return None


def _parse_pos(v) -> int | None:
    s = str(v).strip().upper().lstrip("T")
    try:
        return int(float(s))
    except ValueError:
        return None      # CUT / WD / DQ / blank


def load_leaderboards() -> pd.DataFrame:
    """All leaderboard rows with: year, event (3-char id), player_id,
    player_name, pos (int|None), earnings (float, imputed when missing).

    Imputation: cut/WD rows -> $0. Finishers missing earnings (DG-sourced
    events) get position-share × purse, where purse comes from the event's
    winner earnings when recorded, else the event-number's median purse
    across other years. Positions beyond 20 use the standard curve's tail.
    """
    from scripts.predictions.prize_distributions import get_prize_for_position

    with get_conn(read_only=True) as conn:
        df = conn.execute("""
            SELECT tournament_id, year, player_id, player_name, position, earnings
            FROM leaderboards WHERE year BETWEEN 2010 AND 2026
        """).df()

    df["event"] = df["tournament_id"].str[5:]          # 'R2026060' -> '060'
    df["pos"] = df["position"].apply(_parse_pos)
    df["earn"] = df["earnings"].apply(_parse_earnings)

    # Purse per (event, year): winner's recorded earnings / winner share
    winners = df[(df["pos"] == 1) & df["earn"].notna()]
    purse_by_ey = (winners.set_index(["event", "year"])["earn"] / WINNER_SHARE).to_dict()
    purse_by_e = (winners.groupby("event")["earn"].median() / WINNER_SHARE).to_dict()

    def _impute(row):
        if pd.notna(row["earn"]):
            return row["earn"]
        if pd.isna(row['pos']):                        # cut/WD: no earnings
            return 0.0
        purse = purse_by_ey.get((row["event"], row["year"])) or purse_by_e.get(row["event"])
        if purse is None:
            return np.nan
        return get_prize_for_position(int(row["pos"]), purse)

    df["earn"] = df.apply(_impute, axis=1)
    df['pos_filled'] = df.groupby(['year', 'event'])['pos'].transform(
        lambda s: s.fillna(s.max() + 1)
    )
    df['finish_pct'] = 1 - df.groupby(['year', 'event'])['pos_filled'].rank(pct=True)
    
    
    
    
    df = df.dropna(subset=["earn"])
    print(f"Loaded {len(df):,} rows, {df['event'].nunique()} distinct events, "
          f"{df['year'].min()}–{df['year'].max()}")
    return df[["year", "event", "player_id", "player_name", "pos", "earn", "finish_pct"]]


def purse_of_event(df: pd.DataFrame, event: str) -> float:
    """Median inferred purse of an event across TRAIN years (baseline input)."""
    w = df[(df["event"] == event) & (df["pos"] == 1) & df["year"].isin(TRAIN_YEARS)]
    return float(w["earn"].median() / WINNER_SHARE) if len(w) else np.nan


# ── TODO(you) #1 ──────────────────────────────────────────────────────────────

def p_in_field(player_rows: pd.DataFrame, event: str) -> float:
    """Probability the player enters `event` in the target year.

    player_rows: this player's TRAIN-year rows (all events, cols as loaded).

    Baseline recipe (start here; refine later):
      - Look at the last 4 train years (2022-2025). In how many of them did
        the player tee it up at this event? played/4 is the raw rate.
      - Smooth it: (played + 1) / (4 + 2) keeps 0/4 from meaning "impossible"
        and 4/4 from meaning "certain" (players get injured; fields change).
      - A player with no 2024-2025 activity AT ALL anywhere is likely gone
        from the tour — return something near 0 for everyone in that case.

    Return a float in [0, 1].
    """
    recent = player_rows[player_rows['year'] >= 2022]
    # Gone from the tour entirely? 
    if recent[recent['year'].isin([2024, 2025])].empty:
        return 0.02
    # Attendance at this even over the last 4 years 
    played = recent[recent['event'] == event]['year'].nunique()
    
    # Laplace smoothing: (played + 1) / (4 + 2) instead of playing / 4
    # 4-for-4 five 5/6 ⋍ 0.83, not 1.0 - schedules change, players get hurt
    # 0-for-4 gives 1/6 ⋍ 0.17, not 0.0 - new signature events happened.
    return (played + 1) / (4 + 2)
    
    
    
    



# ── TODO(you) #2 ──────────────────────────────────────────────────────────────

def expected_earnings(player_rows: pd.DataFrame, event: str,
                      overall_avg: float) -> float:
    """E[earnings | plays] for this player at this event.

    player_rows: this player's TRAIN-year rows. overall_avg: the player's
    mean per-start earnings across ALL train-year starts (provided by the
    driver — this is the shrinkage target).

    Baseline recipe:
      - event_avg = mean earnings across this player's starts AT THIS EVENT
      - n = number of those starts
      - Shrink: (n * event_avg + K * overall_avg) / (n + K) with K ≈ 3.
        One lucky win at an event shouldn't dominate; with n=1 the estimate
        stays 3/4 anchored to who the player is overall.
      - No starts at the event → just overall_avg (scaled by the event's
        purse relative to an average purse, if you want the refinement —
        optional, note what you chose).

    Return a float (dollars).
    """
    at_event = player_rows[(player_rows['event'] == event) & 
                           (player_rows['year'] >= 2018)]
    n = len(at_event)
    if n == 0:
        return overall_avg # No starts at this event, return overall average
    event_avg = at_event['earn'].mean()
    # Shrinkage: blend the event specific average toward who the play is overall. 
    # K acts like k phantom starts at the player's usual levels:
    # n=1 -> 1/4 event evidence, 3/4 overall 
    # n=6 -> 2/3 event evidence, 1/3 overall
    
    K = 3
    return (n * event_avg + K * overall_avg) / (n + K)


# ── TODO(you) #3 ──────────────────────────────────────────────────────────────

def score_projection(proj: pd.DataFrame, actual: pd.DataFrame,
                     baseline_purse: dict[str, float], actual_2025: pd.DataFrame) -> None:
    """Score projected event ordering against actual 2026 earnings, per player.

    proj:   columns [player_id, event, projected_ev]
    actual: columns [player_id, event, earn]  (2026 truth, incl. $0 rows)
    baseline_purse: event -> train-year purse (the null model to beat)

    Recipe:
      - Join proj to actual on (player_id, event) — inner join: we score
        ordering among events the player actually entered.
      - For each player with >= 8 scored events: Spearman(projected_ev, earn)
        AND Spearman(purse_of_event, earn) — the purse-only baseline.
      - Report: n players scored, mean + median of both correlations, and
        the fraction of players where the projection beats the baseline.

    Print the comparison table. The verdict line to aim for:
        projection mean rho vs baseline mean rho — is the lift real?
    """
    
    merged = proj.merge(actual, on=['player_id', 'event'], how='inner')
    merged['purse'] = merged['event'].map(baseline_purse)
    proj_rhos, base_rhos = [], []
    for pid, group in merged.groupby('player_id'):
        if len(group) < 8 or group['earn'].nunique() < 2:
            continue
        rho_p, _ = spearmanr(group['projected_ev'], group['earn'])
        rho_b, _ = spearmanr(group['purse'], group['earn'])
        if np.isnan(rho_p) or np.isnan(rho_b):
            continue
        proj_rhos.append(rho_p)
        base_rhos.append(rho_b)
    
    proj_rhos, base_rhos = np.array(proj_rhos), np.array(base_rhos)
    beats = (proj_rhos > base_rhos).sum()
    
    print(f"\n{'='*60}")
    print(f" VERDICT - {len(proj_rhos)} players scored (>=8 events each)")
    print(f"{'='*60}")
    print(f" projection: mean rho = {proj_rhos.mean():.4f}, median rho = {np.median(proj_rhos):.4f}")
    print(f" purse-only: mean rho = {base_rhos.mean():.4f}, median rho = {np.median(base_rhos):.4f}")
    print(f" lift: {proj_rhos.mean() - base_rhos.mean():.4f} | "
          f"projection beats baseline for {beats:.0%} of players")
    
    prior = actual_2025.rename(columns={'earn': 'earn_prior', 'finish_pct': 'fp_prior'})
    yy = actual.merge(prior, on=['player_id', 'event'], how='inner')
    self_rhos = [spearmanr(g['earn_prior'], g['earn'])[0] 
                 for _, g in yy.groupby('player_id') 
                 if len(g) >= 8 and g['earn'].nunique() > 1 and g['earn_prior'].nunique() > 1]
    self_rhos = [r for r in self_rhos if not np.isnan(r)]
    fp_rhos = [spearmanr(g["fp_prior"], g["finish_pct"])[0]
               for _, g in yy.groupby("player_id")
               if len(g) >= 8 and g["finish_pct"].nunique() > 1 and g["fp_prior"].nunique() > 1]
    fp_rhos = [r for r in fp_rhos if not np.isnan(r)]
    print(f" year-over-year self-correlation: mean rho = {np.mean(self_rhos):.4f}, (n={len(self_rhos)})")
    print(f" self-corr, dollars: mean rho = {np.mean(self_rhos):.4f}, (n={len(self_rhos)})")
    print(f" self-corr, finish_pct: mean rho = {np.mean(fp_rhos):.4f}, (n={len(fp_rhos)})") 
       
    
    
    
    
    
    
    
    
    
    
# ── Driver (provided) ─────────────────────────────────────────────────────────

def main():
    df = load_leaderboards()
    train = df[df["year"].isin(TRAIN_YEARS)]
    target = df[df["year"] == TARGET_YEAR]

    events_2026 = sorted(target["event"].unique())
    print(f"2026 events to project: {len(events_2026)}")

    # Players worth projecting: anyone active in 2024-2025
    active = train[train["year"].isin([2024, 2025])]["player_id"].unique()
    print(f"Active players (2024-25): {len(active)}")

    overall = (train[train["year"] >= 2022].groupby("player_id")["earn"]
               .mean().to_dict())

    rows = []
    for pid in active:
        p_rows = train[train["player_id"] == pid]
        avg = overall.get(pid, 0.0)
        for ev in events_2026:
            p = p_in_field(p_rows, ev)
            if p < 0.05:
                continue
            e = expected_earnings(p_rows, ev, avg)
            rows.append({"player_id": pid, "event": ev,
                         "p_field": p, "projected_ev": p * e})
    proj = pd.DataFrame(rows)
    print(f"Projections built: {len(proj):,} (player, event) pairs")

    baseline_purse = {ev: purse_of_event(df, ev) for ev in events_2026}
    actual_2025 = df[df["year"] == 2025][["player_id", "event", "earn", "finish_pct"]]
    score_projection(proj, target[["player_id", "event", "earn", "finish_pct"]],
                     baseline_purse, actual_2025)
    
    
    
    
    
    
    


if __name__ == "__main__":
    main()
