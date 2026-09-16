#!/usr/bin/env python3
"""
Season Optimizer — the ILP at the heart of Strategy Mode
========================================================
Decision: which 3 players to use each week, each player at most 3 times,
maximizing total projected EV across the season. Solved as an Integer
Linear Program; in-season this re-solves every Tuesday over the REMAINING
weeks with live-model EV swapped in for the current week (rolling horizon:
only the current week is a commitment — Jack's rule, learned the hard way).

First mission (this script's default): the 2026 REGRET EVALUATION.
Build the EV grid using ONLY pre-2026 data (the backtest's projection),
solve the whole season, then score the chosen picks by what those players
ACTUALLY earned in 2026. Compare against Jack's real season: $37,933,002
(3rd of 10, and the bar is high — he won the league in 2024 and 2025).

Usage:
    python3 scripts/strategy/season_optimizer.py

────────────────────────────────────────────────────────────────────────────
YOUR PART: solve_season() — the ILP itself. Everything else is provided:
the EV grid assembly (reusing your backtest functions) and the evaluator.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "strategy"))

# Reuse the backtest's settled projection machinery — that work compounds.
from backtest_preseason_projection import (  # noqa: E402
    load_leaderboards, p_in_field, expected_earnings, TRAIN_YEARS, TARGET_YEAR,
)

JACK_ACTUAL_2026 = 37_933_002   # WineTime's real season total (3rd of 10)
USES_PER_PLAYER = 3
SLOTS_PER_WEEK = 3


# ── TODO(you): the ILP ────────────────────────────────────────────────────────

def solve_season(ev: pd.DataFrame,
                 uses_per_player: int = USES_PER_PLAYER,
                 slots_per_week: int = SLOTS_PER_WEEK,
                 uses_left: dict | None = None) -> pd.DataFrame:
    """Choose the EV-maximizing season assignment.

    ev: columns [player_id, event, projected_ev] — one row per allowed
        (player, week) pairing. A pairing absent from ev cannot be chosen
        (that's how attendance filtering enters: no row, no pick).

    Return: the CHOSEN subset of ev's rows (same columns).

    The pulp recipe — five steps, each 2-5 lines:
      1. prob = pulp.LpProblem("season", pulp.LpMaximize)
      2. One binary variable per row:
             x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in ev.index}
      3. Objective — add the EV-weighted sum of all variables to prob:
             prob += pulp.lpSum(x[i] * ev.at[i, "projected_ev"] for i in ev.index)
      4. Constraints — one lpSum per player (<= uses_per_player) and one
         per event (== slots_per_week). groupby(...).groups gives you
         {key: row_indices} ready-made for both.
      5. prob.solve(pulp.PULP_CBC_CMD(msg=0)); return rows where
         x[i].value() == 1.

    One thing to check before returning: prob.status should be 1
    (pulp.LpStatusOptimal). If a week has fewer than slots_per_week
    eligible players the == constraint is infeasible and the solver
    gives garbage silently — assert on status and we'll see it loudly.
    """
    prob = pulp.LpProblem("season", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in ev.index}
    prob += pulp.lpSum(x[i] * ev.at[i, "projected_ev"] for i in ev.index)
    
    for pid, idx in ev.groupby('player_id').groups.items():
        # Mid-season re-solves pass uses_left (3 minus uses already locked);
        # preseason solves leave it None -> everyone gets the full budget.
        cap = uses_left.get(pid, uses_per_player) if uses_left else uses_per_player
        prob += pulp.lpSum(x[i] for i in idx) <= cap
    for ev_id, idx in ev.groupby('event').groups.items():
        prob += pulp.lpSum(x[i] for i in idx) == slots_per_week
        
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    assert prob.status == pulp.LpStatusOptimal, f"Solver status: {pulp.LpStatus[prob.status]}"
    return ev[[x[i].value() == 1 for i in ev.index]]


# ── Provided: EV grid assembly (pre-2026 knowledge only) ─────────────────────

def build_ev_grid() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (ev_grid, actual_2026). Identical inputs to the backtest:
    attendance x expected earnings from TRAIN_YEARS only."""
    df = load_leaderboards()
    train = df[df["year"].isin(TRAIN_YEARS)]
    actual = df[df["year"] == TARGET_YEAR][["player_id", "player_name", "event", "earn"]]

    events = sorted(actual["event"].unique())
    active = train[train["year"].isin([2024, 2025])]["player_id"].unique()
    overall = train[train["year"] >= 2022].groupby("player_id")["earn"].mean().to_dict()

    rows = []
    for pid in active:
        p_rows = train[train["player_id"] == pid]
        avg = overall.get(pid, 0.0)
        for ev_ in events:
            p = p_in_field(p_rows, ev_)
            if p < 0.30:        # attendance gate: "likely plays" — v1 proxy for
                continue        # "played last year" (1/6 smoothing floor excluded)
            rows.append({"player_id": pid, "event": ev_,
                         "projected_ev": p * expected_earnings(p_rows, ev_, avg)})
    grid = pd.DataFrame(rows)
    print(f"EV grid: {len(grid):,} eligible (player, week) pairs, "
          f"{grid['event'].nunique()} weeks, {grid['player_id'].nunique()} players")
    return grid, actual


# ── Provided: the regret evaluation ──────────────────────────────────────────

def evaluate(chosen: pd.DataFrame, actual: pd.DataFrame) -> None:
    m = chosen.merge(actual, on=["player_id", "event"], how="left")
    m["earn"] = m["earn"].fillna(0.0)   # picked someone who didn't play -> $0
    played = m["earn"].gt(0) | m["player_name"].notna()

    total = m["earn"].sum()
    print(f"\n{'='*62}")
    print("  2026 REGRET EVALUATION — optimizer with pre-2026 knowledge")
    print(f"{'='*62}")
    print(f"  optimizer picks:     {len(m)} ({m['player_id'].nunique()} distinct players)")
    print(f"  no-show picks:       {(~played).sum()} (projected to play, didn't)")
    print(f"  optimizer earnings:  ${total:,.0f}")
    print(f"  Jack actual (3rd):   ${JACK_ACTUAL_2026:,.0f}")
    print(f"  difference:          ${total - JACK_ACTUAL_2026:+,.0f}")
    print("\n  Optimizer's boldest calls (top 10 by projected EV):")
    top = m.nlargest(10, "projected_ev")
    for _, r in top.iterrows():
        nm = r.get("player_name") or f"pid {r['player_id']}"
        print(f"    wk {r['event']}: {nm:<24} proj ${r['projected_ev']:>10,.0f}  "
              f"actual ${r['earn']:>10,.0f}")


# ── Provided: rolling replay + hindsight bound ───────────────────────────────

PRED_HISTORY = PROJECT_ROOT / "data" / "prediction_tracking" / "prediction_history.csv"


def _canon(v) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v)


def load_model_weeks() -> list[dict]:
    """The 30 league weeks in date order, each with the live model's
    predicted_ev per player — exactly what was knowable that Tuesday."""
    ph = pd.read_csv(PRED_HISTORY)
    ph["player_id"] = ph["player_id"].apply(_canon)
    ph["event"] = ph["tournament_id"].str[5:]
    # One week per TOURNAMENT: predictions were saved on multiple dates per
    # event, and grouping by (tid, date) minted 32 phantom weeks from 30
    # tournaments — duplicate weeks then consumed tracker entries downstream.
    # Keep each player's latest prediction; the week's date is the earliest.
    ph = ph.sort_values("tournament_date")
    weeks = []
    for tid, g in ph.groupby("tournament_id"):
        g_last = g.drop_duplicates("player_id", keep="last")
        weeks.append({"tid": tid, "event": g["event"].iloc[0],
                      "date": g["tournament_date"].min(),
                      "model_ev": dict(zip(g_last["player_id"], g_last["predicted_ev"]))})
    weeks.sort(key=lambda w: w["date"])
    return weeks


def rolling_replay(grid: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    """Replay 2026 week by week: current week priced by the live model over
    its ACTUAL field (fields are public on Tuesday — not lookahead), future
    weeks priced by the preseason projection. Lock 3 picks, decrement uses,
    advance. Only information available at each Tuesday is used."""
    weeks = load_model_weeks()
    league_events = {w["event"] for w in weeks}
    future_grid = grid[grid["event"].isin(league_events)].copy()

    uses_left: dict = {}
    locked = []
    for k, wk in enumerate(weeks):
        cur = pd.DataFrame({"player_id": list(wk["model_ev"]),
                            "event": wk["event"],
                            "projected_ev": list(wk["model_ev"].values())})
        remaining_events = {w["event"] for w in weeks[k + 1:]}
        fut = future_grid[future_grid["event"].isin(remaining_events)]
        ev = pd.concat([cur, fut], ignore_index=True)
        ev = ev[ev["projected_ev"] > 0]

        chosen = solve_season(ev, uses_left=uses_left)
        picks = chosen[chosen["event"] == wk["event"]]
        for pid in picks["player_id"]:
            uses_left[pid] = uses_left.get(pid, USES_PER_PLAYER) - 1
        locked.append(picks.assign(tid=wk["tid"]))

    return pd.concat(locked, ignore_index=True)


def hindsight_optimal(actual: pd.DataFrame, league_events: set) -> float:
    """Perfect-knowledge ceiling: same ILP, objective = actual earnings."""
    ev = actual[actual["event"].isin(league_events)].rename(
        columns={"earn": "projected_ev"})[["player_id", "event", "projected_ev"]]
    chosen = solve_season(ev)
    return float(chosen["projected_ev"].sum())


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["static", "replay", "all"], default="all")
    args = ap.parse_args()

    grid, actual = build_ev_grid()
    league_events = {w["event"] for w in load_model_weeks()}

    if args.mode in ("static", "all"):
        static = solve_season(grid[grid["event"].isin(league_events)])
        s = static.merge(actual, on=["player_id", "event"], how="left")["earn"].fillna(0).sum()
    if args.mode in ("replay", "all"):
        replay = rolling_replay(grid, actual)
        r = replay.merge(actual, on=["player_id", "event"], how="left")["earn"].fillna(0).sum()
    ceiling = hindsight_optimal(actual, league_events)

    print(f"\n{'='*62}")
    print("  THE LADDER — 2026 season, same 30 league weeks")
    print(f"{'='*62}")
    if args.mode in ("static", "all"):
        print(f"  static preseason plan:   ${s:,.0f}")
    print(f"  Jack actual (3rd of 10): ${JACK_ACTUAL_2026:,.0f}")
    if args.mode in ("replay", "all"):
        print(f"  rolling replay:          ${r:,.0f}")
    print(f"  hindsight-optimal:       ${ceiling:,.0f}")


def main_static_legacy():
    grid, actual = build_ev_grid()
    chosen = solve_season(grid)
    per_week = chosen.groupby("event").size()
    assert (per_week == SLOTS_PER_WEEK).all(), f"bad week sizes: {per_week[per_week != SLOTS_PER_WEEK]}"
    uses = chosen.groupby("player_id").size()
    assert (uses <= USES_PER_PLAYER).all(), "a player exceeds allowed uses"
    print(f"Solved: {len(chosen)} picks across {chosen['event'].nunique()} weeks")
    evaluate(chosen, actual)


if __name__ == "__main__":
    main()
