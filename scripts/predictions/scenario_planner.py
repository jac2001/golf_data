#!/usr/bin/env python3
"""
Season Scenario Planner — Monte Carlo Fantasy Season Simulator
==============================================================
Simulates 5,000 fantasy seasons to compare three usage strategies.
Scoring = actual prize money earned based on finishing position.

  1. GREEDY      — Pick the 3 highest-EV players every single week.
                   Simple, locally optimal, but burns through elite players fast.

  2. MAJOR-SAVER — In Standard events, don't waste fresh top-15 players.
                   Save them for Signatures, Majors, and Playoffs where
                   the prize money (and upside) is highest.

  3. BALANCED    — Deliberately mix tiers: 1 star (rank 1–20) + 1 mid
                   (rank 21–50) + 1 value (rank 51+) per week.
                   Diversifies across player types and avoids early burnout.

SCORING MODEL
-------------
Your fantasy league scores by how much the player earns that week.
A win at The Masters (~$4.2M purse share) is worth much more than
a win at a standard event (~$1.7M). Missed cuts earn $0.

We approximate average earnings per finish bracket as a fraction of
the winner's share, derived from real PGA Tour payout tables:

  Win          → 1.000 × winner_share    (full winner's share)
  T2–T5 avg   → 0.372 × winner_share    (2nd ≈ 61%, 5th ≈ 23%)
  T6–T10 avg  → 0.173 × winner_share    (6th ≈ 20%, 10th ≈ 15%)
  T11–T20 avg → 0.090 × winner_share    (11th ≈ 13%, 20th ≈ 6%)
  T21–cut avg → 0.035 × winner_share    (bottom of field, made cut)
  MC           → $0

WHAT YOU'LL LEARN
-----------------
Monte Carlo simulation:
  Rather than computing exact expected totals, we run 5,000 independent
  random "seasons" and observe the distribution of results.
  The mean converges to the true expectation (Law of Large Numbers);
  percentiles reveal your realistic floor and ceiling.

Exclusive outcome probabilities:
  ML models output cumulative probabilities:
    top5_prob  = P(finish ≤ 5) — includes wins!
    top10_prob = P(finish ≤ 10) — includes top-5s!
  We convert to exclusive outcomes before sampling:
    P(win)       = win_prob
    P(T2–T5)     = top5_prob  - win_prob
    P(T6–T10)    = top10_prob - top5_prob
    ...etc.

Usage:
    python3 scripts/predictions/scenario_planner.py
    → prints summary report + writes outputs/scenario_plan.json
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

PROJECT_ROOT  = Path(__file__).parent.parent.parent
DATA_DIR      = PROJECT_ROOT / "data"
OUTPUTS_DIR   = PROJECT_ROOT / "outputs"
SCHEDULE_FILE = DATA_DIR / "raw" / "schedule_2026.csv"
USAGE_FILE    = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
PREDS_FILE    = OUTPUTS_DIR / "latest_predictions.csv"

N_SIMS       = 5_000
CURRENT_WEEK = 3           # Genesis Invitational is underway

# Average earnings as a fraction of winner's share per finish bracket.
# Derived from real PGA Tour payout tables (verified against Phoenix Open 2024).
# Outcomes are mutually exclusive and ordered: win → T2-T5 → T6-T10 → T11-T20 → cut → MC
EARNINGS_RATIO = np.array([
    1.000,   # Win           (full winner's share)
    0.372,   # T2–T5 avg    (2nd ≈ 60.6%, 3rd ≈ 38.3%, 4th ≈ 27.1%, 5th ≈ 22.6%)
    0.173,   # T6–T10 avg   (6th ≈ 19.9%, 10th ≈ 15.0%)
    0.090,   # T11–T20 avg
    0.035,   # T21–cut avg  (made cut but not top 20)
    0.000,   # MC           ($0)
])

# Tournament type → importance tier (used by Major-Saver strategy)
TYPE_TIER = {
    "Major":    "premium",
    "Signature":"premium",
    "Playoff":  "premium",
    "Standard": "standard",
    "Team":     "skip",    # Zurich Classic is 2-man teams — skip
}


# ── Data loaders ──────────────────────────────────────────────────────────────

def _parse_money(val) -> float:
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    return float(str(val).replace("$", "").replace(",", ""))


def load_schedule(current_week: int) -> pd.DataFrame:
    """Load upcoming weeks (strictly after current_week) from the schedule."""
    df = pd.read_csv(SCHEDULE_FILE)
    df["winner_share_val"] = df["winner_share"].apply(_parse_money)
    remaining = df[df["week"] > current_week].copy()
    return remaining.reset_index(drop=True)


def load_players() -> pd.DataFrame:
    """
    Load current week's predictions as player-strength proxies.

    We use this week's ML model output to approximate player ability for
    all future weeks. Known simplification — form changes — but it's the
    best signal we have right now.
    """
    df = pd.read_csv(PREDS_FILE)
    needed = [
        "player_name", "world_rank", "expected_value",
        "win_prob", "top5_prob", "top10_prob", "top20_prob",
        "cut_prob", "miss_cut_prob",
    ]
    df = df[[c for c in needed if c in df.columns]].copy()
    df["world_rank"] = pd.to_numeric(df["world_rank"], errors="coerce").fillna(200)
    # Tier labels based on world rank
    df["tier"] = pd.cut(
        df["world_rank"],
        bins=[0, 20, 50, 9999],
        labels=["star", "mid", "value"],
    )
    return df.reset_index(drop=True)


def load_usage() -> dict:
    """
    Load current season usage state.
    Returns {player_name: {remaining: int, times_used: int}}.
    """
    with open(USAGE_FILE) as f:
        data = json.load(f)
    usage = {}
    for name, info in data["picks"].items():
        usage[name] = {
            "remaining":  info["remaining_uses"],
            "times_used": info["times_used"],
        }
    return usage


# ── Probability helpers ───────────────────────────────────────────────────────

def outcome_probs(row: pd.Series) -> np.ndarray:
    """
    Convert cumulative ML probabilities → exclusive outcome probability vector
    aligned with EARNINGS_RATIO = [win, T2-T5, T6-T10, T11-T20, cut, mc].

    Cumulative → exclusive:
      p_win   = win_prob
      p_t5    = top5_prob  - p_win
      p_t10   = top10_prob - top5_prob
      p_t20   = top20_prob - top10_prob
      p_cut   = cut_prob   - top20_prob
      p_mc    = 1 - cut_prob

    Clip negatives (floating-point noise) then renormalize to sum = 1.0.
    """
    p_win  = float(row.get("win_prob",   0.01))
    p_t5   = float(row.get("top5_prob",  0.06)) - p_win
    p_t10  = float(row.get("top10_prob", 0.12)) - p_win - p_t5
    p_t20  = float(row.get("top20_prob", 0.22)) - p_win - p_t5 - p_t10
    p_cut  = float(row.get("cut_prob",   0.70)) - p_win - p_t5 - p_t10 - p_t20
    p_mc   = 1.0 - float(row.get("cut_prob", 0.70))

    probs = np.array([p_win, p_t5, p_t10, p_t20, p_cut, p_mc])
    probs = np.clip(probs, 0.0, 1.0)
    probs /= probs.sum()
    return probs


# ── Strategy selection functions ──────────────────────────────────────────────

def select_greedy(players: pd.DataFrame, remaining: dict, week_info: dict) -> list:
    """
    GREEDY: Pick the 3 players with highest expected_value who still have uses left.
    No lookahead. Locally optimal but burns through elite players without regard
    for tournament importance.
    """
    avail = players[players["player_name"].map(
        lambda n: remaining.get(n, 3) > 0
    )].copy()
    avail = avail.sort_values("expected_value", ascending=False)
    return avail["player_name"].head(3).tolist()


def select_major_saver(players: pd.DataFrame, remaining: dict, week_info: dict) -> list:
    """
    MAJOR-SAVER: Protect fresh top-15 players for high-purse events.

    Standard week  → skip world_rank ≤ 15 players who haven't been used
                     twice yet. Let the mid-tier carry the week.
    Premium week   → best 3 from the full pool (no restrictions).

    Exception: if a star player is on their 3rd use already, no point
    saving them — they're available in standard weeks too.
    """
    tier = week_info.get("tier", "standard")

    avail = players[players["player_name"].map(
        lambda n: remaining.get(n, 3) > 0
    )].copy()

    if tier == "standard":
        def _is_saveable_star(row) -> bool:
            name       = row["player_name"]
            rank       = float(row["world_rank"])
            times_used = 3 - remaining.get(name, 3)
            return rank <= 15 and times_used < 2

        pool = avail[~avail.apply(_is_saveable_star, axis=1)]
        if len(pool) < 3:
            pool = avail  # fallback if not enough non-stars
    else:
        pool = avail

    pool = pool.sort_values("expected_value", ascending=False)
    return pool["player_name"].head(3).tolist()


def select_balanced(players: pd.DataFrame, remaining: dict, week_info: dict) -> list:
    """
    BALANCED: Deliberately pick 1 star + 1 mid + 1 value player per week.

    Diversifies across world-rank tiers, preventing early burnout of any
    single tier. You always have a ceiling play (star), a solid floor play
    (mid), and a bonus upside play (value).
    """
    avail = players[players["player_name"].map(
        lambda n: remaining.get(n, 3) > 0
    )].copy()

    picks = []
    for tier_label in ["star", "mid", "value"]:
        tier_pool = avail[
            (avail["tier"] == tier_label)
            & ~avail["player_name"].isin(picks)
        ].sort_values("expected_value", ascending=False)

        if not tier_pool.empty:
            picks.append(tier_pool.iloc[0]["player_name"])

    if len(picks) < 3:
        rest = avail[~avail["player_name"].isin(picks)].sort_values(
            "expected_value", ascending=False
        )
        for name in rest["player_name"]:
            picks.append(name)
            if len(picks) == 3:
                break

    return picks[:3]


STRATEGIES = {
    "greedy":      select_greedy,
    "major_saver": select_major_saver,
    "balanced":    select_balanced,
}

STRATEGY_META = {
    "greedy": {
        "display_name": "Greedy (Max EV)",
        "description":  "Always picks 3 highest-EV players available. "
                        "Simple and locally optimal — never thinks ahead.",
        "color": "#3498db",
    },
    "major_saver": {
        "display_name": "Major-Saver",
        "description":  "Protects fresh top-15 players for Signature/Major events. "
                        "Uses mid-tier in Standard weeks, deploys stars in big spots.",
        "color": "#e67e22",
    },
    "balanced": {
        "display_name": "Balanced",
        "description":  "Deliberately mixes 1 star + 1 mid + 1 value per week. "
                        "Diversifies across tiers, avoids early burnout.",
        "color": "#2ecc71",
    },
}


# ── Season planner ────────────────────────────────────────────────────────────

def plan_season(strategy_fn, players: pd.DataFrame, schedule: pd.DataFrame,
                init_usage: dict) -> list:
    """
    Run one strategy over all remaining weeks to produce a full season plan.

    Returns list of week dicts:
      week, tournament, type, winner_share, picks (list of 3 names), skipped (bool)
    """
    remaining = {}
    for _, row in players.iterrows():
        name = row["player_name"]
        remaining[name] = init_usage.get(name, {}).get("remaining", 3)

    season_plan = []

    for _, week_row in schedule.iterrows():
        t_type       = str(week_row.get("tournament_type", "Standard"))
        tier         = TYPE_TIER.get(t_type, "standard")
        winner_share = float(week_row["winner_share_val"])

        if tier == "skip":
            season_plan.append({
                "week":         int(week_row["week"]),
                "tournament":   week_row["tournament_name"],
                "type":         t_type,
                "winner_share": winner_share,
                "picks":        [],
                "skipped":      True,
            })
            continue

        week_info = {
            "week":  int(week_row["week"]),
            "type":  t_type,
            "tier":  tier,
        }

        picks = strategy_fn(players, remaining, week_info)

        for p in picks:
            remaining[p] = max(0, remaining.get(p, 3) - 1)

        season_plan.append({
            "week":         int(week_row["week"]),
            "tournament":   week_row["tournament_name"],
            "type":         t_type,
            "winner_share": winner_share,
            "picks":        picks,
            "skipped":      False,
        })

    return season_plan


# ── Monte Carlo simulator ─────────────────────────────────────────────────────

def simulate_seasons(season_plan: list, players: pd.DataFrame,
                     n_sims: int = N_SIMS) -> np.ndarray:
    """
    Run n_sims independent fantasy seasons from the given plan.

    Scoring: for each player-week, sample an outcome index from the
    categorical distribution, then multiply EARNINGS_RATIO[outcome] by
    the tournament's winner_share to get dollars earned.

    Returns: np.ndarray of shape (n_sims,) — total $ earned per simulation.

    Why simulate rather than just compute E[earnings]?
    ---------------------------------------------------
    E[earnings] = Σ_weeks Σ_outcomes P(outcome) × earnings(outcome)
    is easy to compute analytically. But we'd only get one number (the mean).
    Monte Carlo gives us the full distribution: percentiles, standard deviation,
    probability of finishing above any threshold. In a competitive fantasy league,
    knowing your floor (5th pct) and ceiling (95th pct) often matters as much
    as the mean.
    """
    prob_cache = {}
    for _, row in players.iterrows():
        prob_cache[row["player_name"]] = outcome_probs(row)

    # EARNINGS_RATIO indexed [0..5] matching outcome_probs output order
    outcome_indices = np.arange(len(EARNINGS_RATIO))

    totals = np.zeros(n_sims)

    for week in season_plan:
        if week["skipped"] or not week["picks"]:
            continue

        winner_share = week["winner_share"]

        for player_name in week["picks"]:
            probs = prob_cache.get(player_name)
            if probs is None:
                continue
            # Sample outcome indices for all n_sims at once
            idx      = np.random.choice(outcome_indices, size=n_sims, p=probs)
            earnings = EARNINGS_RATIO[idx] * winner_share
            totals  += earnings

    return totals


# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> dict:
    np.random.seed(42)

    print("\n" + "=" * 66)
    print("  SEASON SCENARIO PLANNER — MONTE CARLO SIMULATION")
    print(f"  Remaining weeks: {CURRENT_WEEK + 1}–30  |  Simulations: {N_SIMS:,}")
    print("  Scoring: prize money earned (not FedEx points)")
    print("=" * 66)

    schedule = load_schedule(CURRENT_WEEK)
    players  = load_players()
    usage    = load_usage()

    playable = schedule[schedule["tournament_type"] != "Team"]
    print(f"\n  Player pool:     {len(players)} players (from latest predictions)")
    print(f"  Remaining weeks: {len(schedule)} total ({len(playable)} playable)")
    print(f"  Players tracked: {len(usage)} with usage history")
    print()

    results = {}

    for strategy_name, strategy_fn in STRATEGIES.items():
        meta = STRATEGY_META[strategy_name]
        print(f"  ── {meta['display_name']} ──")

        plan       = plan_season(strategy_fn, players, schedule, usage)
        sim_totals = simulate_seasons(plan, players, N_SIMS)

        mean_earn = float(sim_totals.mean())
        std_earn  = float(sim_totals.std())
        pctiles   = {str(p): float(np.percentile(sim_totals, p))
                     for p in [5, 10, 25, 50, 75, 90, 95]}

        print(f"    Mean:   ${mean_earn:>12,.0f}")
        print(f"    Median: ${pctiles['50']:>12,.0f}")
        print(f"    Std:    ${std_earn:>12,.0f}")
        print(f"    Range:  ${pctiles['5']:,.0f} – ${pctiles['95']:,.0f}  (5th–95th pct)")

        plan_summary = []
        for wk in plan:
            plan_summary.append({
                "week":         wk["week"],
                "tournament":   wk["tournament"],
                "type":         wk["type"],
                "winner_share": int(wk["winner_share"]),
                "picks":        wk["picks"],
                "skipped":      wk["skipped"],
            })

        hist_vals = sim_totals[::max(1, N_SIMS // 500)].tolist()

        results[strategy_name] = {
            **meta,
            "stats": {
                "mean": round(mean_earn),
                "std":  round(std_earn),
                **{f"p{k}": round(v) for k, v in pctiles.items()},
            },
            "histogram":   {"values": [round(x) for x in hist_vals]},
            "season_plan": plan_summary,
        }

    best = max(results, key=lambda k: results[k]["stats"]["mean"])
    print(f"\n  Best by mean earnings: {results[best]['display_name']}")
    print(f"  → ${results[best]['stats']['mean']:,.0f} expected")

    output = {
        "generated_at":     datetime.now().isoformat(),
        "n_simulations":    N_SIMS,
        "current_week":     CURRENT_WEEK,
        "weeks_remaining":  len(schedule),
        "player_pool_size": len(players),
        "scoring":          "prize_money",
        "best_strategy":    best,
        "strategies":       results,
    }

    out_path = OUTPUTS_DIR / "scenario_plan.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  ✅ Saved → {out_path}")
    print("=" * 66)
    return output


if __name__ == "__main__":
    run()
