"""
Lineup Optimizer — Combinatorial Pick Selector
================================================
Finds the mathematically optimal 3-pick combination from all eligible
players this week.

WHAT THIS SOLVES
----------------
usage_optimizer.py scores players *individually* — it answers
"should I use Scheffler THIS week?"  But it never asks the joint question:
"given Scheffler + who else produces the highest expected total?"

This script answers that by brute-force searching every possible
3-pick combination from the top-N eligible players.

THE MATH (worth understanding)
-------------------------------
1. Expected Value is additive:
        E[X + Y + Z] = E[X] + E[Y] + E[Z]
    So for pure EV-max, the optimal combo is trivially the top 3 by EV.
    The interesting optimization comes from the CEILING BONUS and SAVE PENALTY.

2. Ceiling bonus — P(at least one top-5 finish):
        P(≥1 top-5) = 1 - P(none top-5)          ← complement rule
                    = 1 - ∏(1 - p_top5_i)         ← independence assumption
    Two players each with 10% top-5 prob give a combo P = 1-(0.9*0.9) = 19%.
    One player with 20% gives P = 20%.  Nearly identical — so stacking EV in
    one elite player is almost as good as spreading.  The bonus captures this
    nuance and slightly rewards diversity.

3. Last-use penalty:
    If a player has only 1 use remaining and this is a standard (low-purse)
    event, spending that use here has an opportunity cost: you could have saved
    it for a Major worth 3-5x more in winner's share.
    We convert that multi-week constraint into a single-week cost by applying
    a fixed penalty (default $15,000 EV-equivalent).

COMBINATORICS
-------------
For N=40 eligible players, C(40,3) = 9,880 combinations.
Python evaluates all in < 0.1 seconds using itertools.combinations.
C(50,3) = 19,600  ·  C(60,3) = 34,220  — all run in under a second.

Usage:
    python3 scripts/predictions/lineup_optimizer.py
    python3 scripts/predictions/lineup_optimizer.py --top-n 50 --top-combos 15
    python3 scripts/predictions/lineup_optimizer.py --save-csv
"""
import sys
import json
import argparse
import itertools
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"
DATA_DIR     = PROJECT_ROOT / "data"

# Import the calendar and tracker from the existing optimizer — no duplication.
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))
from usage_optimizer import TournamentCalendar, UsageTracker


# ── Tuning knobs ────────────────────────────────────────────────────────────
# How much weight to give the ceiling bonus relative to base EV.
# At 0.10, a combo with 50% P(top-5) gets a 5% EV boost over one with 0%.
CEILING_WEIGHT = 0.10

# EV-equivalent penalty for spending a player's LAST use in a standard event.
# Calibrated so a player with 1 use remaining will be preferred in a Major
# ($3M+ winner's share) over a standard event ($1.5M winner's share).
LAST_USE_PENALTY = 15_000

DEFAULT_TOP_N     = 40   # candidate pool (C(40,3) = 9,880 combos)
DEFAULT_TOP_COMBOS = 10  # results to show



# ── Name normalization ────────────────────────────────────────────────────────
def _norm(name: str) -> str:
    """Normalize 'Last, First' or 'First Last' → 'first last' for matching."""
    parts = str(name).split(",")
    if len(parts) == 2:
        return f"{parts[1].strip()} {parts[0].strip()}".lower()
    return str(name).strip().lower()







# ── Usage data ───────────────────────────────────────────────────────────────

def load_usage_remaining(usage_path: Path) -> dict:
    """
    Return {normalized_player_name: remaining_uses} from the tracker JSON.
    Players not yet in the tracker default to 3 remaining uses.
    """
    if not usage_path.exists():
        return {}
    with open(usage_path) as f:
        data = json.load(f)
    return {
        _norm(name): info.get("remaining_uses", 3)
        for name, info in data.get("picks", {}).items()
    }


# ── Scoring ──────────────────────────────────────────────────────────────────
def score_combo(rows: list, importance: float) -> dict:
    """
    Score a 3-player combination and return a breakdown.

    Parameters
    ----------
    rows : list of 3 dicts, each a row from the predictions DataFrame
    importance : TournamentCalendar importance score (1-10)

    Returns a dict with: score, base_ev, ceiling_bonus, last_use_cost, p_top5_any
    """
    
    
    
    #1. Base EV = additive expectation 
    base_ev = sum(float(r.get("expected_value", 0)) for r in rows)
    
    #2. Celing bonus - P(at least one top-5) via complement rule 
    # Assumes player finishes are independent {reasonable approximation}.
    
    
    p_none_top5 = 1.0 
    for r in rows:
        p_none_top5 *= max(0.0, 1.0 - float(r.get("top5_prob", 0)))
    p_at_least_one = 1.0 - p_none_top5
    ceiling_bonus = p_at_least_one * base_ev * CEILING_WEIGHT 
     # 3. Last-use penalty — only applies in standard (importance < 7) events.
      #    A Major or Signature event (importance >= 7) justifies spending last uses.
    last_use_cost = 0.0
    if importance < 7.0:
        for r in rows:
            if int(r.get("remaining_uses", 3)) == 1:
                last_use_cost += LAST_USE_PENALTY

    total = base_ev + ceiling_bonus - last_use_cost

    return {
        "score":          total,
        "base_ev":        base_ev,
        "ceiling_bonus":  ceiling_bonus,
        "last_use_cost":  last_use_cost,
        "p_top5_any":     p_at_least_one,
    }
 # ── Core optimizer ────────────────────────────────────────────────────────────
def run_optimizer(
    top_n: int = DEFAULT_TOP_N,
    top_combos: int = DEFAULT_TOP_COMBOS,
    tournament_name: str = None,
    verbose: bool = True,
) -> tuple:
    """
    Run the combinatorial optimizer.

    Returns
    -------
    results_df  : DataFrame of top combinations, ranked by score
    eligible_df : DataFrame of eligible players considered
    importance  : tournament importance score used
    tournament  : tournament name resolved from calendar
    """
    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    usage_path = DATA_DIR / "fantasy" / "usage_tracker_2026.json"

    if not preds_path.exists():
        raise FileNotFoundError(
            f"No predictions at {preds_path}. Run the full pipeline first."
        )

    preds = pd.read_csv(preds_path)
    
    # ── Resolve tournament name & importance ──────────────────────────────
    if not tournament_name:
        # Auto-detect from schedule: active > next upcoming
        sched_path = DATA_DIR / "raw" / "schedule_2026.csv"
        if sched_path.exists():
            sched = pd.read_csv(sched_path)
            today = datetime.now().strftime("%Y-%m-%d")
            active = sched[
                (sched["start_date"] <= today) & (sched["end_date"] >= today)
            ]
            if not active.empty:
                tournament_name = active.iloc[0]["tournament_name"]
            else:
                upcoming = sched[sched["start_date"] > today].sort_values("start_date")
                if not upcoming.empty:
                    tournament_name = upcoming.iloc[0]["tournament_name"]

    importance = (
        TournamentCalendar.get_importance(tournament_name)
        if tournament_name else 5
    )

    if verbose:
        print(f"\n  Tournament: {tournament_name or 'Unknown'}")
        print(f"  Importance: {importance}/10")
        print(f"  Predictions loaded: {len(preds)} players")
# ── Attach remaining uses ─────────────────────────────────────────────
    usage = load_usage_remaining(usage_path)
    preds["remaining_uses"] = preds["player_name"].apply(
        lambda n: usage.get(_norm(n), 3)
    )

    # ── Filter & rank eligible players ───────────────────────────────────
    eligible = (
        preds[preds["remaining_uses"] > 0]
        .copy()
        .sort_values("expected_value", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

    if verbose:
        total_eligible = int((preds["remaining_uses"] > 0).sum())
        n_combos = len(eligible) * (len(eligible) - 1) * (len(eligible) - 2) // 6
        print(f"  Eligible players (uses > 0): {total_eligible}")
        print(f"  Evaluating top {len(eligible)} → {n_combos:,} combinations")

    # ── Brute-force all C(n,3) combinations ──────────────────────────────
    cols = [
        "player_name", "expected_value", "win_prob",
        "top5_prob", "top10_prob", "world_rank",
        "odds_to_win", "remaining_uses",
    ]
    cols = [c for c in cols if c in eligible.columns]
    records = eligible[cols].to_dict("records")

    results = []
    for trio in itertools.combinations(records, 3):
        sc = score_combo(list(trio), importance)
        results.append({
            "pick1":         trio[0]["player_name"],
            "pick2":         trio[1]["player_name"],
            "pick3":         trio[2]["player_name"],
            "score":         round(sc["score"]),
            "base_ev":       round(sc["base_ev"]),
            "ceiling_bonus": round(sc["ceiling_bonus"]),
            "last_use_cost": round(sc["last_use_cost"]),
            "p_top5_any":    round(sc["p_top5_any"] * 100, 1),
            "ev1":           round(float(trio[0].get("expected_value", 0))),
            "ev2":           round(float(trio[1].get("expected_value", 0))),
            "ev3":           round(float(trio[2].get("expected_value", 0))),
            "uses1":         int(trio[0].get("remaining_uses", 3)),
            "uses2":         int(trio[1].get("remaining_uses", 3)),
            "uses3":         int(trio[2].get("remaining_uses", 3)),
            "wr1":           trio[0].get("world_rank", ""),
            "wr2":           trio[1].get("world_rank", ""),
            "wr3":           trio[2].get("world_rank", ""),
        })

    results_df = (
        pd.DataFrame(results)
        .sort_values("score", ascending=False)
        .head(top_combos)
        .reset_index(drop=True)
    )
    results_df.index += 1  # 1-based rank

    return results_df, eligible, importance, tournament_name


# ── CLI output ───────────────────────────────────────────────────────────────
def print_results(results_df: pd.DataFrame, importance: float, tournament: str):
    penalty_active = importance < 7.0
    print()
    print("=" * 76)
    print("  OPTIMAL LINEUP COMBINATIONS")
    print(f"  {tournament or 'Current tournament'}")
    print(
        f"  Importance: {importance}/10  ·  "
        f"Last-use penalty: {'ACTIVE (standard event)' if penalty_active else 'OFF (major/elite)'}"
    )
    print("=" * 76)

    hdr = f"  {'#':<4} {'Pick 1':<23} {'Pick 2':<23} {'Pick 3':<23} {'Score':>8} {'Base EV':>9} {'P(top5)':>8}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for rank, row in results_df.iterrows():
        uses_str = f"uses:{row['uses1']}/{row['uses2']}/{row['uses3']}"
        penalty_str = f"  ⚠ -${row['last_use_cost']:,}" if row["last_use_cost"] > 0 else ""
        print(
            f"  {rank:<4} "
            f"{str(row['pick1'])[:21]:<23} "
            f"{str(row['pick2'])[:21]:<23} "
            f"{str(row['pick3'])[:21]:<23} "
            f"${row['score']:>7,} "
            f"${row['base_ev']:>8,} "
            f"{row['p_top5_any']:>7.1f}%"
            f"  ({uses_str}){penalty_str}"
        )

    print()
    if results_df["last_use_cost"].sum() > 0:
        print("  ⚠  Last-use penalty applied to some combinations.")
        print("     Those players have only 1 use left — consider saving for a Major.")
    print("=" * 76)


def main():
    parser = argparse.ArgumentParser(
        description="Combinatorial lineup optimizer — finds optimal 3-pick combination"
    )
    parser.add_argument(
        "--top-n", type=int, default=DEFAULT_TOP_N,
        help=f"Candidate pool size (default: {DEFAULT_TOP_N}). C(40,3)=9,880 combos."
    )
    parser.add_argument(
        "--top-combos", type=int, default=DEFAULT_TOP_COMBOS,
        help=f"Combinations to display (default: {DEFAULT_TOP_COMBOS})"
    )
    parser.add_argument(
        "--tournament", "-t", default=None,
        help="Tournament name (auto-detects from schedule if omitted)"
    )
    parser.add_argument(
        "--save-csv", action="store_true",
        help="Save results to outputs/optimal_lineups.csv"
    )
    args = parser.parse_args()

    results_df, eligible, importance, tournament = run_optimizer(
        top_n=args.top_n,
        top_combos=args.top_combos,
        tournament_name=args.tournament,
    )

    print_results(results_df, importance, tournament)

    if args.save_csv:
        out = OUTPUTS_DIR / "optimal_lineups.csv"
        results_df.to_csv(out)
        print(f"\n  Saved to {out}")


if __name__ == "__main__":
    main()

