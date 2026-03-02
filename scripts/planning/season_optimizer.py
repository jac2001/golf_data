#!/usr/bin/env python3
"""
Season Usage Optimizer  —  Integer Linear Programming
======================================================
Solves the "Let It Ride" season allocation problem:
  Each player has ≤3 uses across a 30-tournament season.
  You pick exactly 3 players per week.
  Which 3 weeks should each player's uses be allocated to?

WHY NOT GREEDY?
---------------
Greedy (pick the 3 highest-EV players each week) is myopic. Because elite
players always rank highly, they get used in week 2, 3, 4 — before majors
even start. The ILP looks at all remaining tournaments simultaneously and
finds the globally optimal assignment.

Example: Ryan Gerard has a great course fit at Cognizant Classic (week 4)
AND at The Players (week 6). Greedy uses him at both immediately. ILP may
save one use for a higher-importance event if the marginal gain is larger.

THE MATH  (Integer Linear Program)
-----------------------------------
Variables:    x[p, t]  ∈  {0, 1}      "use player p in tournament t"

Maximize:     Σ_{p,t}  x[p,t] × value[p,t]

Subject to:
  (1) Σ_t  x[p,t]  ≤  remaining_uses[p]    each player's use budget
  (2) Σ_p  x[p,t]  =  3                     exactly 3 players per week
  (3) x[p,t]  ∈  {0, 1}                     binary decision

value[p,t]  =  player_ev[p]  ×  tournament_importance[t]  ×  course_fit[p,t]

  • player_ev[p]:            dollars expected from the current model run
  • tournament_importance[t]: purse-weighted scaler (major = ~2-3×, standard = ~1×)
  • course_fit[p,t]:          optional 0.7–1.3× from course_history.py

Usage:
    python3 scripts/planning/season_optimizer.py
    python3 scripts/planning/season_optimizer.py --course-fit
    python3 scripts/planning/season_optimizer.py --compare          # ILP vs greedy
    python3 scripts/planning/season_optimizer.py --top-n 30 --weeks 8
"""

import json
import sys
import unicodedata
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"
FANTASY_DIR  = DATA_DIR / "fantasy"

# ── Constants ────────────────────────────────────────────────────────────────

# Season-average purse used to normalize tournament importance to ~1.0.
# Majors/Signature events will score 2-3×; standard events ~0.8-1.2×.
AVG_PURSE = 9_600_000.0

# Tournament type boosts applied BEFORE purse scaling.
# These let known-important events rank higher even if purse data is missing.
TYPE_BOOST = {
    "Major":     2.5,
    "Signature": 1.8,
    "WGC":       2.0,
    "Playoff":   2.2,
    "Standard":  1.0,
}

# Maximum world rank allowed in each event type's field.
# Based on PGA Tour qualification criteria (approximate):
#   Signature:  top-70 FedEx Cup + exemptions ≈ world rank ≤ 125
#   Major:      broader via past champs + OWGR ≈ rank ≤ 200
#   Standard:   any tour card holder        ≈ rank ≤ 400
# Players outside these thresholds get value=0 for that tournament,
# so the ILP never assigns them there.
FIELD_RANK_THRESHOLD = {
    "Major":     200,
    "WGC":        80,
    "Signature": 125,
    "Playoff":   150,
    "Standard":  400,
}

# Piecewise world-rank → expected-value lookup (calibrated from 2026 predictions).
# Used for players NOT in the current week's field (e.g. Scheffler at a Standard event
# he skipped). Intervals: (max_rank, ev_dollars)
_RANK_EV_TABLE = [
    (10,  160_000),
    (25,  145_000),
    (50,  130_000),
    (100, 107_000),
    (200,  88_000),
    (400,  72_000),
]

def _rank_to_ev(rank) -> float:
    """Estimate a player's per-start EV from their world rank.

    Used for players absent from this week's field (they still exist and will
    play future events — we just don't have a current model prediction for them).
    Calibrated from the observed EV distribution in 2026 predictions.
    """
    try:
        r = float(rank)
    except (TypeError, ValueError):
        return 60_000.0
    for max_rank, ev in _RANK_EV_TABLE:
        if r <= max_rank:
            return float(ev)
    return 60_000.0  # rank > 400


# ── Name normalization (reused from usage_tracker) ───────────────────────────

_LATIN_MAP = str.maketrans({
    "ø": "o", "ö": "o", "ó": "o", "ô": "o", "õ": "o",
    "æ": "ae", "å": "a", "ä": "a", "á": "a", "à": "a", "â": "a",
    "ð": "d", "þ": "th", "ñ": "n",
    "ü": "u", "ú": "u", "ù": "u", "û": "u",
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "í": "i", "ì": "i", "î": "i", "ï": "i",
    "ç": "c", "ß": "ss",
})

def _norm(name: str) -> str:
    """Accent-strip + lowercase + canonical 'first last' order.

    Handles both 'Last, First' (predictions CSV) and 'First Last' (tracker)
    so lookups succeed across data sources.
    """
    s = str(name).strip().lower()
    # "gerard, ryan" → "ryan gerard"
    if "," in s:
        parts = s.split(",", 1)
        s = f"{parts[1].strip()} {parts[0].strip()}"
    s = s.translate(_LATIN_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


# ── Data loaders ─────────────────────────────────────────────────────────────

def _parse_purse(raw) -> float:
    """'$9,600,000.00' → 9600000.0"""
    try:
        return float(str(raw).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return AVG_PURSE


def load_schedule(from_date: Optional[str] = None) -> pd.DataFrame:
    """
    Load remaining tournaments from schedule_2026.csv.

    Filters to events whose end_date >= today (includes in-progress events).
    Adds an 'importance' column: the value multiplier used in the ILP objective.
    """
    path = DATA_DIR / "raw" / "schedule_2026.csv"
    if not path.exists():
        raise FileNotFoundError(f"Schedule not found: {path}")

    sched = pd.read_csv(path)

    if from_date is None:
        from_date = date.today().isoformat()

    # Keep only future / current events
    future = sched[sched["end_date"] >= from_date].copy().reset_index(drop=True)

    # Build importance multiplier for each tournament.
    # Formula: blend of type boost (how significant is this event category?)
    #          and purse ratio (how big is the prize pool vs. average?).
    def _importance(row: pd.Series) -> float:
        t_type  = str(row.get("tournament_type", "Standard"))
        boost   = TYPE_BOOST.get(t_type, 1.0)
        purse   = _parse_purse(row.get("purse", AVG_PURSE))
        purse_r = purse / AVG_PURSE  # 1.0 = average week
        # 60% type-based, 40% purse-based so Majors always rank high
        # even if their purse isn't dramatically larger
        return round(0.6 * boost + 0.4 * purse_r, 3)

    future["importance"] = future.apply(_importance, axis=1)
    return future


def load_all_players(top_n: int = 150) -> pd.DataFrame:
    """
    Build the full player pool for season optimization.

    WHY NOT JUST USE THIS WEEK'S FIELD?
    The current predictions file only has players in THIS week's field (~123).
    Elite players like Scheffler skip weaker Standard events but will appear
    at THE PLAYERS, majors, and signature events. If we only use this week's
    field, the optimizer never considers them — badly undervaluing those events.

    APPROACH:
    1. Load all ~1000 active PGA Tour members from pga_players_2026.csv.
    2. For players IN this week's predictions: use the actual model EV
       (captures their current form, course fit, odds, etc.)
    3. For players NOT in this week's field: estimate EV from world rank
       using a table calibrated from 2026 prediction data.
    4. Return top-N by estimated EV — keeps the ILP tractable.

    The world_rank column is preserved on every row so the value matrix
    can later apply field qualification filters per tournament type.
    """
    # ── All tour members ─────────────────────────────────────────────────────
    all_path = DATA_DIR / "players" / "pga_players_2026.csv"
    if not all_path.exists():
        raise FileNotFoundError(f"Player list not found: {all_path}")

    all_pl = pd.read_csv(all_path)
    # player_id stored as float (e.g. 46046.0) — normalize to int string
    all_pl["player_id"] = all_pl["player_id"].dropna().astype(int).astype(str)
    all_pl = all_pl[["player_id", "player_name", "world_rank"]].copy()

    # ── Current-week model predictions ───────────────────────────────────────
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if pred_path.exists():
        preds = pd.read_csv(pred_path)
        preds["player_id"] = preds["player_id"].astype(str)
        keep = ["player_id", "expected_value", "win_prob", "top10_prob"]
        keep = [c for c in keep if c in preds.columns]
        preds = preds[keep].copy()
    else:
        preds = pd.DataFrame(columns=["player_id", "expected_value"])

    # ── Merge: actual EV for field players, estimated EV for everyone else ───
    merged = all_pl.merge(preds, on="player_id", how="left")

    # For players without a model prediction, estimate from world rank
    missing = merged["expected_value"].isna()
    merged.loc[missing, "expected_value"] = merged.loc[missing, "world_rank"].apply(_rank_to_ev)

    # Drop players with no usable rank or EV
    merged = merged.dropna(subset=["expected_value"])
    merged["world_rank"] = pd.to_numeric(merged["world_rank"], errors="coerce").fillna(999)

    # Return top-N by EV so ILP stays fast (N=150 → 150×27 = 4050 variables)
    merged = (merged
              .sort_values("expected_value", ascending=False)
              .head(top_n)
              .reset_index(drop=True))
    return merged


def load_remaining_uses() -> Dict[str, int]:
    """
    Load each tracked player's remaining uses from usage_tracker_2026.json.

    Players not yet tracked default to 3 (never used).
    Uses accent-normalized name matching so "Hojgaard" finds "Højgaard".
    Returns {normalized_name: remaining_uses}.
    """
    path = FANTASY_DIR / "usage_tracker_2026.json"
    if not path.exists():
        return {}

    with open(path) as f:
        data = json.load(f)

    return {
        _norm(name): int(info.get("remaining_uses", 3))
        for name, info in data.get("picks", {}).items()
    }


# ── Value matrix ─────────────────────────────────────────────────────────────

def build_value_matrix(
    players:     pd.DataFrame,   # shape (P,)  — result of load_player_ev()
    tournaments: pd.DataFrame,   # shape (T,)  — result of load_schedule()
    course_fit:  Optional[Dict] = None,
) -> np.ndarray:
    """
    Build the P × T expected-value matrix.

    value[p, t]  =  base_ev[p]  ×  importance[t]  ×  fit_mult[p, t]

    base_ev[p]     — player's expected_value from the ML model this week.
                     Represents player quality / form right now.

    importance[t]  — tournament multiplier (1.0 = avg standard event).
                     Major ≈ 2.5×, Signature ≈ 1.8×, Standard ≈ 1.0×.
                     Makes the optimizer naturally want to save elite players
                     for high-importance events.

    fit_mult[p,t]  — course fit adjustment (optional).
                     Maps a 0-100 fit score onto a 0.7–1.3× multiplier.
                     Neutral (score=50) → 1.0× (no change).
                     Great fit (score=90) → 1.24× bonus.
                     Poor fit (score=10) → 0.76× penalty.
    """
    P = len(players)
    T = len(tournaments)
    V = np.zeros((P, T))

    importances  = tournaments["importance"].values           # length T
    event_types  = tournaments["tournament_type"].fillna("Standard").values  # length T

    for p_idx in range(P):
        base_ev    = float(players.at[p_idx, "expected_value"] or 0)
        pname      = players.at[p_idx, "player_name"]
        world_rank = float(players.at[p_idx, "world_rank"] or 999)

        for t_idx in range(T):
            # ── Field qualification filter ────────────────────────────────
            # If this player's world rank exceeds the event's typical field
            # size, set value to 0 — they won't qualify, so don't allocate
            # a use there. This is the key improvement over using only this
            # week's field: Scheffler (rank 1) gets value at Majors and
            # Signature events but not necessarily at Standard events he skips.
            threshold = FIELD_RANK_THRESHOLD.get(str(event_types[t_idx]), 400)
            if world_rank > threshold:
                V[p_idx, t_idx] = 0.0
                continue

            val = base_ev * importances[t_idx]

            # ── Optional course fit multiplier ────────────────────────────
            # Maps [0,100] → [0.7, 1.3]: fit_mult = 0.7 + score/100 * 0.6
            if course_fit is not None:
                tname    = tournaments.at[t_idx, "tournament_name"]
                score    = course_fit.get((_norm(pname), _norm(tname)), 50.0)
                fit_mult = 0.7 + (score / 100.0) * 0.6
                val     *= fit_mult

            V[p_idx, t_idx] = val

    return V


# ── ILP solver ───────────────────────────────────────────────────────────────

def solve_ilp(
    value_matrix:   np.ndarray,  # shape (P, T)
    remaining_uses: np.ndarray,  # shape (P,)  — max uses per player
    lineup_size:    int = 3,
) -> Optional[np.ndarray]:
    """
    Solve the integer linear program using scipy.optimize.milp.

    Variables:   x[p, t] ∈ {0,1}  →  flattened to x[p*T + t]
    Minimize:    -value_matrix.flatten() @ x     (negated because milp minimizes)

    Constraints are built as a sparse matrix A where:
      Row group 1 (P rows): player use budgets   — Σ_t x[p,t] ≤ budget[p]
      Row group 2 (T rows): lineup size          — Σ_p x[p,t] = lineup_size

    The LinearConstraint object accepts (lb, A, ub) so:
      Budget rows:  lb = -∞,            ub = remaining_uses[p]
      Lineup rows:  lb = lineup_size,   ub = lineup_size   (equality)

    Returns binary assignment matrix shape (P, T), or None if infeasible.
    """
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import csr_matrix

    P, T   = value_matrix.shape
    n_vars = P * T

    # ── Objective: minimize the NEGATIVE of expected value ───────────────────
    # (scipy.optimize.milp always minimizes; negate to convert to maximization)
    c = -value_matrix.flatten()

    # ── Build constraint matrix A (sparse for speed) ─────────────────────────
    rows, cols, vals = [], [], []

    # Constraint group 1: for each player p, Σ_t x[p,t] ≤ budget[p]
    # Each row p has 1s at columns p*T, p*T+1, ..., p*T+(T-1)
    for p in range(P):
        for t in range(T):
            rows.append(p)
            cols.append(p * T + t)
            vals.append(1.0)

    # Constraint group 2: for each tournament t, Σ_p x[p,t] = lineup_size
    # Each row (P+t) has 1s at columns 0*T+t, 1*T+t, ..., (P-1)*T+t
    for t in range(T):
        for p in range(P):
            rows.append(P + t)   # offset by P — below the budget rows
            cols.append(p * T + t)
            vals.append(1.0)

    A = csr_matrix((vals, (rows, cols)), shape=(P + T, n_vars))

    # ── Constraint bounds ─────────────────────────────────────────────────────
    lb = np.concatenate([
        np.full(P, -np.inf),              # budget: no lower bound
        np.full(T, float(lineup_size)),   # lineup: exactly lineup_size (lower)
    ])
    ub = np.concatenate([
        remaining_uses.astype(float),     # budget upper bound
        np.full(T, float(lineup_size)),   # lineup: exactly lineup_size (upper)
    ])

    constraints  = LinearConstraint(A, lb, ub)
    bounds       = Bounds(lb=0, ub=1)      # each x[p,t] ∈ [0,1]
    integrality  = np.ones(n_vars)         # 1 = integer (binary since bounds [0,1])

    result = milp(c, constraints=constraints, integrality=integrality, bounds=bounds)

    if result.status != 0:
        print(f"  ILP solver status {result.status}: {result.message}")
        return None

    return np.round(result.x).astype(int).reshape(P, T)


# ── Greedy fallback / comparison baseline ────────────────────────────────────

def solve_greedy(
    value_matrix:   np.ndarray,
    remaining_uses: np.ndarray,
    lineup_size:    int = 3,
) -> np.ndarray:
    """
    Greedy season planner: for each tournament (highest-importance first),
    pick the top-N available players by expected value.

    This is the naive baseline that ILP improves on.
    Suboptimal because it's myopic — it can't "look ahead" to save elite
    player uses for bigger events coming later in the season.
    """
    P, T = value_matrix.shape
    x      = np.zeros((P, T), dtype=int)
    budget = remaining_uses.copy()

    # Process tournaments from most to least important so greedy at least
    # prefers the better events (slightly better than week-order greedy)
    importance_order = np.argsort(-value_matrix.max(axis=0))

    for t in importance_order:
        eligible = np.where(budget > 0)[0]
        if len(eligible) < lineup_size:
            break

        # Pick top players by value for this tournament, from eligible pool
        ev_eligible  = value_matrix[eligible, t]
        top_local    = np.argsort(-ev_eligible)[:lineup_size]
        top_players  = eligible[top_local]

        x[top_players, t] = 1
        budget[top_players] -= 1

    return x


# ── Output formatting ─────────────────────────────────────────────────────────

def format_plan(
    x:           np.ndarray,
    players:     pd.DataFrame,
    tournaments: pd.DataFrame,
    V:           np.ndarray,
    method:      str,
) -> dict:
    """Convert binary (P×T) assignment matrix to a structured plan dict."""
    lineups     = []
    allocations: Dict[str, List[str]] = {}
    total_ev    = 0.0

    for t_idx in range(len(tournaments)):
        tourn      = tournaments.iloc[t_idx]
        p_indices  = np.where(x[:, t_idx] == 1)[0]
        picked     = players.iloc[p_indices]
        week_ev    = float(V[p_indices, t_idx].sum())
        total_ev  += week_ev

        lineups.append({
            "week":        int(tourn.get("week", t_idx + 1)),
            "tournament":  tourn["tournament_name"],
            "start_date":  str(tourn.get("start_date", "")),
            "importance":  float(tourn["importance"]),
            "players":     picked["player_name"].tolist(),
            "ev":          round(week_ev, 0),
        })

        for pname in picked["player_name"]:
            allocations.setdefault(pname, []).append(tourn["tournament_name"])

    return {
        "method":           method,
        "total_ev":         round(total_ev, 0),
        "n_players":        len(players),
        "n_tournaments":    len(tournaments),
        "generated_at":     datetime.now().isoformat(timespec="seconds"),
        "lineups":          lineups,
        "allocations":      allocations,
    }


def print_plan(plan: dict, max_weeks: int = 10):
    """Print a readable season strategy summary."""
    stars = lambda imp: "★" * min(5, round(imp * 1.5))  # visual importance

    print(f"\n{'='*70}")
    print(f"  SEASON STRATEGY PLAN  [{plan['method']}]")
    print(f"{'='*70}")
    print(f"  Player pool:        {plan['n_players']} players")
    print(f"  Remaining events:   {plan['n_tournaments']} tournaments")
    print(f"  Projected total EV: ${plan['total_ev']:,.0f}")

    # ── Week-by-week lineups ─────────────────────────────────────────────────
    print(f"\n  {'─'*68}")
    print(f"  WEEK-BY-WEEK LINEUPS  (showing next {max_weeks} weeks)")
    print(f"  {'─'*68}")

    for entry in plan["lineups"][:max_weeks]:
        imp_label = stars(entry["importance"])
        print(f"\n  Wk {entry['week']:2}  {entry['tournament']:<38} {imp_label}")
        print(f"       {entry['start_date']}   EV: ${entry['ev']:,.0f}")
        print(f"       → {', '.join(entry['players'])}")

    n_remaining = len(plan["lineups"]) - max_weeks
    if n_remaining > 0:
        print(f"\n  ... and {n_remaining} more weeks (use --weeks N to see more)")

    # ── Player allocations ───────────────────────────────────────────────────
    print(f"\n  {'─'*68}")
    print(f"  PLAYER USE ALLOCATIONS")
    print(f"  {'─'*68}")
    for player, events in sorted(plan["allocations"].items(),
                                  key=lambda kv: -len(kv[1])):
        slots = "  ".join([f"Wk{plan['lineups'][i]['week']}"
                           for i, e in enumerate(plan["lineups"])
                           if player in e["players"]])
        print(f"  {player:<35}  {len(events)} uses  [{slots}]")


def compare_plans(ilp_plan: dict, greedy_plan: dict):
    """Show side-by-side EV difference between ILP and greedy."""
    diff      = ilp_plan["total_ev"] - greedy_plan["total_ev"]
    diff_pct  = 100 * diff / greedy_plan["total_ev"] if greedy_plan["total_ev"] else 0

    print(f"\n  {'─'*68}")
    print(f"  ILP vs GREEDY COMPARISON")
    print(f"  {'─'*68}")
    print(f"  Greedy total EV:  ${greedy_plan['total_ev']:>12,.0f}")
    print(f"  ILP    total EV:  ${ilp_plan['total_ev']:>12,.0f}")
    print(f"  ILP improvement:  ${diff:>12,.0f}  (+{diff_pct:.1f}%)")

    # Show weeks where allocations differ
    greedy_by_week = {e["week"]: set(e["players"]) for e in greedy_plan["lineups"]}
    print(f"\n  Weeks where ILP differs from greedy:")
    shown = 0
    for entry in ilp_plan["lineups"]:
        greedy_picks = greedy_by_week.get(entry["week"], set())
        ilp_picks    = set(entry["players"])
        swapped_in   = ilp_picks - greedy_picks
        swapped_out  = greedy_picks - ilp_picks
        if swapped_in or swapped_out:
            print(f"    Wk {entry['week']:2} {entry['tournament'][:30]:<30}")
            if swapped_in:
                print(f"         ILP adds:    {', '.join(sorted(swapped_in))}")
            if swapped_out:
                print(f"         Greedy had:  {', '.join(sorted(swapped_out))}")
            shown += 1
    if shown == 0:
        print("    (No differences — ILP and greedy agree this season)")


# ── Main optimizer class ──────────────────────────────────────────────────────

class SeasonOptimizer:
    """
    Season-long lineup optimizer for "Let It Ride" fantasy golf.

    Quick start:
        opt  = SeasonOptimizer(top_n=40)
        plan = opt.run()
        opt.save(plan)
    """

    def __init__(self, top_n: int = 50, lineup_size: int = 3):
        """
        top_n:        Player pool size. Larger = more options but slower.
                      50 players × 26 tournaments = 1300 ILP variables (very fast).
        lineup_size:  Players per weekly lineup (the league uses 3).
        """
        self.top_n       = top_n
        self.lineup_size = lineup_size

    def run(self, use_course_fit: bool = False, method: str = "ilp") -> dict:
        """
        Load data, build value matrix, solve, return plan dict.

        use_course_fit: load course_history.py and apply fit multipliers to V.
        method:         "ilp" (optimal) or "greedy" (fast baseline).
        """
        players    = load_all_players(top_n=self.top_n)
        tournaments = load_schedule()
        uses_map   = load_remaining_uses()

        # Map remaining uses onto the player list.
        # Players not yet tracked (never used) default to max_uses (3).
        uses_arr = np.array([
            uses_map.get(_norm(name), self.lineup_size)
            for name in players["player_name"]
        ])

        # Optional: load course fit scores for all (player, tournament) pairs
        course_fit = self._load_course_fit(players, tournaments) if use_course_fit else None

        V = build_value_matrix(players, tournaments, course_fit=course_fit)

        if method == "greedy":
            x = solve_greedy(V, uses_arr, self.lineup_size)
            label = "greedy"
        else:
            x = solve_ilp(V, uses_arr, self.lineup_size)
            if x is None:
                print("  ILP infeasible — falling back to greedy")
                x     = solve_greedy(V, uses_arr, self.lineup_size)
                label = "greedy (fallback)"
            else:
                label = "ILP"

        return format_plan(x, players, tournaments, V, label)

    def _load_course_fit(self, players: pd.DataFrame, tournaments: pd.DataFrame) -> dict:
        """
        Load course fit scores for all (player, tournament) pairs.
        Returns {(_norm(player_name), _norm(tournament_name)): fit_score_0_to_100}.
        """
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "planning"))
            from course_history import CourseHistoryDB  # noqa: PLC0415
            db  = CourseHistoryDB()
            fit = {}
            for _, tourn in tournaments.iterrows():
                tname = tourn["tournament_name"]
                for _, player in players.iterrows():
                    pname = player["player_name"]
                    try:
                        score = db.calculate_course_fit_score(pname, tname) or 50.0
                    except Exception:
                        score = 50.0
                    fit[(_norm(pname), _norm(tname))] = float(score)
            print(f"  Course fit loaded for {len(players)} players × {len(tournaments)} events")
            return fit
        except Exception as exc:
            print(f"  Course fit unavailable ({exc}) — using neutral values")
            return {}

    def save(self, plan: dict, path: Optional[str] = None):
        """Save plan JSON for dashboard consumption."""
        out = Path(path) if path else OUTPUTS_DIR / "season_plan_latest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(plan, f, indent=2)
        print(f"\n  Saved → {out}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(
        description="Season-long lineup optimizer (ILP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--top-n",     type=int, default=50,
                   help="Player pool size (default 50)")
    p.add_argument("--weeks",     type=int, default=10,
                   help="Weeks to display (default 10)")
    p.add_argument("--course-fit", action="store_true",
                   help="Include course fit multiplier in value (slower)")
    p.add_argument("--compare",   action="store_true",
                   help="Run both ILP and greedy, show difference")
    p.add_argument("--greedy",    action="store_true",
                   help="Use greedy only (skip ILP)")
    p.add_argument("--output",    default=None,
                   help="Output JSON path (default: outputs/season_plan_latest.json)")
    args = p.parse_args()

    opt = SeasonOptimizer(top_n=args.top_n)

    if args.compare:
        print("\n  Running ILP optimizer...")
        ilp_plan = opt.run(use_course_fit=args.course_fit, method="ilp")
        print("  Running greedy baseline...")
        greedy_plan = opt.run(use_course_fit=args.course_fit, method="greedy")
        print_plan(ilp_plan, max_weeks=args.weeks)
        compare_plans(ilp_plan, greedy_plan)
        opt.save(ilp_plan, args.output)

    else:
        method = "greedy" if args.greedy else "ilp"
        print(f"\n  Running {method} season optimizer...")
        if args.course_fit:
            print("  Loading course fit scores (may take 20s)...")
        plan = opt.run(use_course_fit=args.course_fit, method=method)
        print_plan(plan, max_weeks=args.weeks)
        opt.save(plan, args.output)


if __name__ == "__main__":
    main()
