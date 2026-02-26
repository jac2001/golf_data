"""
Lineup Optimizer — Constraint-Aware Combinatorial Selector
===========================================================
Objective:
    expected_value + ceiling_bonus + leverage_bonus - risk_penalty - usage_penalty

This keeps the search deterministic while letting the user tune risk/usage tradeoffs.
"""

import argparse
import itertools
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DATA_DIR = PROJECT_ROOT / "data"

# Import calendar utility from existing optimizer.
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))
from usage_optimizer import TournamentCalendar


# Defaults (kept moderate to avoid overfitting one profile)
DEFAULT_TOP_N = 40
DEFAULT_TOP_COMBOS = 10
DEFAULT_LINEUP_SIZE = 3

DEFAULT_CEILING_WEIGHT = 0.10
DEFAULT_LEVERAGE_WEIGHT = 0.08
DEFAULT_RISK_WEIGHT = 0.20
DEFAULT_USAGE_WEIGHT = 1.00
DEFAULT_LAST_USE_PENALTY = 15_000.0


def _norm(name: str) -> str:
    """Normalize player names across First/Last variants."""
    parts = str(name).split(",")
    if len(parts) == 2:
        name = f"{parts[1].strip()} {parts[0].strip()}"
    else:
        name = str(name).strip()
    name = name.lower()
    for suffix in [" jr.", " jr", " iii", " ii", " iv"]:
        name = name.replace(suffix, "")
    name = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in name)
    return " ".join(name.split())


def _split_names(values: list[str] | None) -> list[str]:
    """Split repeated/CSV name args into a clean list."""
    out = []
    for val in values or []:
        for token in str(val).split(","):
            t = token.strip()
            if t:
                out.append(t)
    return out


def _norm_01(series: pd.Series) -> pd.Series:
    """Min-max normalize to [0,1] with safe fallbacks."""
    s = pd.to_numeric(series, errors="coerce")
    if s.isna().all():
        return pd.Series(np.zeros(len(s)), index=s.index, dtype=float)
    mn = float(s.min())
    mx = float(s.max())
    if math.isclose(mx, mn):
        return pd.Series(np.full(len(s), 0.5), index=s.index, dtype=float)
    return ((s - mn) / (mx - mn)).fillna(0.5).clip(0.0, 1.0)


def _combination_count(n: int, k: int) -> int:
    if n < k or k <= 0:
        return 0
    return math.comb(n, k)


def load_usage_remaining(usage_path: Path) -> dict:
    """Return {normalized_player_name: remaining_uses} from usage tracker."""
    if not usage_path.exists():
        return {}
    with open(usage_path) as f:
        data = json.load(f)
    picks = data.get("picks", {}) if isinstance(data, dict) else {}
    return {_norm(name): int(info.get("remaining_uses", 3)) for name, info in picks.items()}


def _resolve_requested_players(requested: list[str], available_names: list[str]) -> tuple[list[str], list[str]]:
    """
    Resolve user-entered names to canonical player names in available pool.
    Returns (resolved, unresolved).
    """
    if not requested:
        return [], []
    by_norm = {_norm(n): n for n in available_names}
    resolved, unresolved = [], []
    for req in requested:
        key = _norm(req)
        if key in by_norm:
            resolved.append(by_norm[key])
            continue
        candidates = [name for nkey, name in by_norm.items() if key in nkey or nkey in key]
        if len(candidates) == 1:
            resolved.append(candidates[0])
        else:
            unresolved.append(req)
    # Keep order stable and unique.
    seen = set()
    deduped = []
    for n in resolved:
        if n not in seen:
            deduped.append(n)
            seen.add(n)
    return deduped, unresolved


def _prepare_prediction_pool(preds: pd.DataFrame) -> pd.DataFrame:
    """Standardize key optimizer features from predictions output."""
    df = preds.copy()
    if "player_name" not in df.columns:
        raise ValueError("Predictions file missing required column 'player_name'.")
    df["player_name"] = df["player_name"].fillna("").astype(str).str.strip()
    df = df[df["player_name"] != ""].copy()
    if df.empty:
        return df

    df["expected_value"] = pd.to_numeric(df.get("expected_value"), errors="coerce").fillna(0.0)
    df["win_prob"] = pd.to_numeric(df.get("win_prob"), errors="coerce").fillna(0.0).clip(0.0, 1.0)
    top5_src = df.get("top5_prob")
    if top5_src is None:
        top5_src = df.get("top_5_prob")
    df["top5_prob"] = pd.to_numeric(top5_src, errors="coerce")
    top10_src = df.get("top10_prob")
    if top10_src is None:
        top10_src = df.get("top_10_prob")
    df["top10_prob"] = pd.to_numeric(top10_src, errors="coerce")

    df["top10_prob"] = df["top10_prob"].fillna((df["win_prob"] * 3.0).clip(0.0, 0.75))
    df["top5_prob"] = df["top5_prob"].fillna((df["top10_prob"] * 0.55).clip(0.0, 0.50))
    df["top5_prob"] = df["top5_prob"].clip(0.0, 1.0)
    df["top10_prob"] = df["top10_prob"].clip(0.0, 1.0)

    top20_src = df.get("top20_prob")
    if top20_src is None:
        top20_src = df.get("top_20_prob")
    df["top20_prob"] = pd.to_numeric(top20_src, errors="coerce")
    missing_top20 = df["top20_prob"].isna()
    df.loc[missing_top20, "top20_prob"] = (
        df.loc[missing_top20, "top10_prob"] +
        (df.loc[missing_top20, "top10_prob"] - df.loc[missing_top20, "top5_prob"]) * 1.2
    ).clip(0.0, 0.95)
    df["top20_prob"] = df["top20_prob"].fillna(0.0).clip(0.0, 1.0)

    df["cut_prob"] = pd.to_numeric(df.get("cut_prob"), errors="coerce")
    missing_cut = df["cut_prob"].isna()
    df.loc[missing_cut, "cut_prob"] = (df.loc[missing_cut, "top20_prob"] * 1.35 + 0.22).clip(0.0, 0.99)
    df["cut_prob"] = df["cut_prob"].fillna(0.5).clip(0.0, 1.0)
    df["miss_cut_prob"] = (1.0 - df["cut_prob"]).clip(0.0, 1.0)

    df["world_rank"] = pd.to_numeric(df.get("world_rank"), errors="coerce")
    vegas_prob = pd.to_numeric(df.get("vegas_prob"), errors="coerce")
    model_gap = pd.to_numeric(df.get("model_vs_vegas_edge"), errors="coerce")
    if model_gap.notna().any():
        df["leverage_raw"] = model_gap.fillna(model_gap.median())
    elif vegas_prob.notna().any():
        df["leverage_raw"] = (df["win_prob"] - vegas_prob.fillna(vegas_prob.median()))
    else:
        df["leverage_raw"] = df["win_prob"] - df["win_prob"].median()
    df["leverage_norm"] = _norm_01(df["leverage_raw"])
    df["cut_norm"] = _norm_01(df["cut_prob"])
    df["top10_norm"] = _norm_01(df["top10_prob"])
    df["ev_norm"] = _norm_01(df["expected_value"])
    df["candidate_blend"] = (
        0.52 * df["ev_norm"] +
        0.20 * df["top10_norm"] +
        0.18 * df["cut_norm"] +
        0.10 * df["leverage_norm"]
    )
    return df


def score_combo(
    rows: list[dict],
    importance: float,
    ceiling_weight: float,
    leverage_weight: float,
    risk_weight: float,
    usage_weight: float,
    last_use_penalty: float,
) -> dict:
    """Score one lineup using the tuned objective."""
    base_ev = sum(float(r.get("expected_value", 0.0)) for r in rows)

    p_none_top5 = 1.0
    for r in rows:
        p_none_top5 *= max(0.0, 1.0 - float(r.get("top5_prob", 0.0)))
    p_top5_any = 1.0 - p_none_top5
    ceiling_bonus = p_top5_any * base_ev * float(ceiling_weight)

    avg_miss_cut = float(np.mean([float(r.get("miss_cut_prob", 0.5)) for r in rows])) if rows else 0.0
    risk_penalty = base_ev * float(risk_weight) * avg_miss_cut

    leverage_signal = float(np.mean([(float(r.get("leverage_norm", 0.5)) * 2.0) - 1.0 for r in rows])) if rows else 0.0
    leverage_bonus = base_ev * float(leverage_weight) * leverage_signal

    # Usage penalty scales down at majors/signatures because burning uses there is acceptable.
    if importance >= 9.0:
        importance_mult = 0.20
    elif importance >= 7.0:
        importance_mult = 0.45
    else:
        importance_mult = 1.00

    last_use_count = sum(1 for r in rows if int(r.get("remaining_uses", 3)) <= 1)
    two_use_count = sum(1 for r in rows if int(r.get("remaining_uses", 3)) == 2)

    last_use_cost = float(last_use_count) * float(last_use_penalty) * importance_mult
    two_use_cost = float(two_use_count) * float(last_use_penalty) * 0.35 * importance_mult
    usage_penalty = float(usage_weight) * (last_use_cost + two_use_cost)

    score = base_ev + ceiling_bonus + leverage_bonus - risk_penalty - usage_penalty
    return {
        "score": score,
        "base_ev": base_ev,
        "ceiling_bonus": ceiling_bonus,
        "leverage_bonus": leverage_bonus,
        "risk_penalty": risk_penalty,
        "usage_penalty": usage_penalty,
        "last_use_cost": last_use_cost,
        "p_top5_any": p_top5_any,
        "avg_miss_cut": avg_miss_cut,
        "leverage_signal": leverage_signal,
    }


def run_optimizer(
    top_n: int = DEFAULT_TOP_N,
    top_combos: int = DEFAULT_TOP_COMBOS,
    tournament_name: str | None = None,
    verbose: bool = True,
    lineup_size: int = DEFAULT_LINEUP_SIZE,
    min_avg_cut_prob: float = 0.84,
    max_last_use_players: int = 1,
    min_leverage_players: int = 0,
    leverage_threshold: float = 0.65,
    ceiling_weight: float = DEFAULT_CEILING_WEIGHT,
    leverage_weight: float = DEFAULT_LEVERAGE_WEIGHT,
    risk_weight: float = DEFAULT_RISK_WEIGHT,
    usage_weight: float = DEFAULT_USAGE_WEIGHT,
    last_use_penalty: float = DEFAULT_LAST_USE_PENALTY,
    locked_players: list[str] | None = None,
    excluded_players: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, float, str | None]:
    """Run combinatorial optimizer with hard constraints + objective tuning."""
    if lineup_size < 2:
        raise ValueError("lineup_size must be >= 2")

    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    usage_path = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
    if not preds_path.exists():
        raise FileNotFoundError(f"No predictions at {preds_path}. Run the full pipeline first.")

    preds = pd.read_csv(preds_path)
    pool = _prepare_prediction_pool(preds)
    if pool.empty:
        return pd.DataFrame(), pool, 0.0, tournament_name

    if not tournament_name:
        sched_path = DATA_DIR / "raw" / "schedule_2026.csv"
        if sched_path.exists():
            sched = pd.read_csv(sched_path)
            today = datetime.now().strftime("%Y-%m-%d")
            active = sched[(sched["start_date"] <= today) & (sched["end_date"] >= today)]
            if not active.empty:
                tournament_name = str(active.iloc[0]["tournament_name"]).strip()
            else:
                upcoming = sched[sched["start_date"] > today].sort_values("start_date")
                if not upcoming.empty:
                    tournament_name = str(upcoming.iloc[0]["tournament_name"]).strip()

    importance = float(TournamentCalendar.get_importance(tournament_name) if tournament_name else 5.0)

    usage = load_usage_remaining(usage_path)
    pool["remaining_uses"] = pool["player_name"].apply(lambda n: int(usage.get(_norm(n), 3)))
    pool = pool[pool["remaining_uses"] > 0].copy()

    available_names = pool["player_name"].tolist()
    resolved_excluded, unresolved_excluded = _resolve_requested_players(excluded_players or [], available_names)
    if resolved_excluded:
        pool = pool[~pool["player_name"].isin(resolved_excluded)].copy()
    available_names = pool["player_name"].tolist()
    resolved_locked, unresolved_locked = _resolve_requested_players(locked_players or [], available_names)

    if len(resolved_locked) > lineup_size:
        raise ValueError(f"Locked players ({len(resolved_locked)}) exceed lineup size ({lineup_size}).")

    if pool.empty:
        meta = {
            "total_combos": 0,
            "scored_combos": 0,
            "skipped_by_cut": 0,
            "skipped_by_usage": 0,
            "skipped_by_leverage": 0,
            "resolved_locked": resolved_locked,
            "unresolved_locked": unresolved_locked,
            "resolved_excluded": resolved_excluded,
            "unresolved_excluded": unresolved_excluded,
        }
        out = pd.DataFrame()
        out.attrs["optimizer_meta"] = meta
        return out, pool, importance, tournament_name

    # Candidate pool: mix EV + stability + leverage (not just top EV chalk).
    target_pool = max(int(top_n), lineup_size * 8, 18)
    n_each = max(6, int(target_pool * 0.35))
    idx_set = set()
    for col in ["expected_value", "top10_prob", "cut_prob", "leverage_norm", "win_prob"]:
        idx_set.update(pool.nlargest(n_each, col).index.tolist())

    candidate = pool.loc[sorted(idx_set)].copy() if idx_set else pool.copy()
    if len(candidate) < target_pool:
        fill = pool.sort_values("candidate_blend", ascending=False)
        idx_set.update(fill.head(target_pool).index.tolist())
        candidate = pool.loc[sorted(idx_set)].copy()

    if len(candidate) > target_pool:
        candidate = candidate.sort_values("candidate_blend", ascending=False).head(target_pool).copy()

    # Always keep locked players in candidate set.
    if resolved_locked:
        locked_df = pool[pool["player_name"].isin(resolved_locked)]
        candidate = pd.concat([candidate, locked_df], ignore_index=True).drop_duplicates(subset=["player_name"], keep="first")

    candidate = candidate.reset_index(drop=True)
    if len(candidate) < lineup_size:
        raise ValueError(f"Not enough eligible players ({len(candidate)}) for lineup size {lineup_size}.")

    if verbose:
        print(f"\n  Tournament: {tournament_name or 'Unknown'}")
        print(f"  Importance: {importance:.0f}/10")
        print(f"  Player pool: {len(pool)} eligible, {len(candidate)} candidates")

    records = candidate[
        [
            "player_name",
            "expected_value",
            "win_prob",
            "top5_prob",
            "top10_prob",
            "top20_prob",
            "cut_prob",
            "miss_cut_prob",
            "leverage_raw",
            "leverage_norm",
            "world_rank",
            "remaining_uses",
        ]
    ].to_dict("records")

    locked_norms = {_norm(n) for n in resolved_locked}
    total_combos = _combination_count(len(records), lineup_size)
    skipped_by_cut = 0
    skipped_by_usage = 0
    skipped_by_leverage = 0

    results = []
    for combo in itertools.combinations(records, lineup_size):
        names = [str(r.get("player_name", "")).strip() for r in combo]
        name_norms = {_norm(n) for n in names}
        if locked_norms and not locked_norms.issubset(name_norms):
            continue

        avg_cut = float(np.mean([float(r.get("cut_prob", 0.5)) for r in combo]))
        if avg_cut < float(min_avg_cut_prob):
            skipped_by_cut += 1
            continue

        last_use_count = sum(1 for r in combo if int(r.get("remaining_uses", 3)) <= 1)
        if last_use_count > int(max_last_use_players):
            skipped_by_usage += 1
            continue

        lev_count = sum(1 for r in combo if float(r.get("leverage_norm", 0.0)) >= float(leverage_threshold))
        if lev_count < int(min_leverage_players):
            skipped_by_leverage += 1
            continue

        sc = score_combo(
            list(combo),
            importance=importance,
            ceiling_weight=ceiling_weight,
            leverage_weight=leverage_weight,
            risk_weight=risk_weight,
            usage_weight=usage_weight,
            last_use_penalty=last_use_penalty,
        )

        row = {
            "lineup": " | ".join(names),
            "score": round(sc["score"], 2),
            "base_ev": round(sc["base_ev"], 2),
            "ceiling_bonus": round(sc["ceiling_bonus"], 2),
            "leverage_bonus": round(sc["leverage_bonus"], 2),
            "risk_penalty": round(sc["risk_penalty"], 2),
            "usage_penalty": round(sc["usage_penalty"], 2),
            "last_use_cost": round(sc["last_use_cost"], 2),
            "p_top5_any": round(sc["p_top5_any"] * 100.0, 2),
            "avg_cut_prob": round(avg_cut * 100.0, 2),
            "avg_miss_cut_prob": round(sc["avg_miss_cut"] * 100.0, 2),
            "last_use_count": int(last_use_count),
            "leverage_count": int(lev_count),
            "leverage_signal": round(sc["leverage_signal"], 4),
        }

        for i in range(max(3, lineup_size)):
            if i < lineup_size:
                pr = combo[i]
                row[f"pick{i + 1}"] = pr["player_name"]
                row[f"ev{i + 1}"] = round(float(pr.get("expected_value", 0.0)), 2)
                row[f"uses{i + 1}"] = int(pr.get("remaining_uses", 3))
                wr = pr.get("world_rank")
                row[f"wr{i + 1}"] = "" if pd.isna(wr) else int(wr)
            else:
                row[f"pick{i + 1}"] = ""
                row[f"ev{i + 1}"] = np.nan
                row[f"uses{i + 1}"] = np.nan
                row[f"wr{i + 1}"] = ""
        results.append(row)

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = (
            results_df
            .sort_values(["score", "base_ev", "avg_cut_prob", "p_top5_any"], ascending=[False, False, False, False])
            .head(int(top_combos))
            .reset_index(drop=True)
        )
        results_df.index += 1

    meta = {
        "total_combos": int(total_combos),
        "scored_combos": int(len(results)),
        "skipped_by_cut": int(skipped_by_cut),
        "skipped_by_usage": int(skipped_by_usage),
        "skipped_by_leverage": int(skipped_by_leverage),
        "resolved_locked": resolved_locked,
        "unresolved_locked": unresolved_locked,
        "resolved_excluded": resolved_excluded,
        "unresolved_excluded": unresolved_excluded,
    }
    results_df.attrs["optimizer_meta"] = meta
    candidate.attrs["optimizer_meta"] = meta
    return results_df, candidate, importance, tournament_name


def print_results(results_df: pd.DataFrame, importance: float, tournament: str | None):
    """CLI report output."""
    print()
    print("=" * 96)
    print("  OPTIMAL LINEUP COMBINATIONS")
    print(f"  {tournament or 'Current tournament'}")
    print(f"  Tournament importance: {importance:.0f}/10")
    print("=" * 96)

    if results_df.empty:
        print("  No combinations satisfied constraints. Relax min-cut/max-last-use/leverage filters.")
        print("=" * 96)
        return

    hdr = (
        f"  {'#':<4} {'Pick 1':<21} {'Pick 2':<21} {'Pick 3':<21} "
        f"{'Score':>9} {'Base EV':>10} {'Cut%':>7} {'Top5%':>7}"
    )
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for rank, row in results_df.iterrows():
        uses_str = f"uses:{int(row['uses1'])}/{int(row['uses2'])}/{int(row['uses3'])}"
        print(
            f"  {rank:<4} "
            f"{str(row.get('pick1', ''))[:19]:<21} "
            f"{str(row.get('pick2', ''))[:19]:<21} "
            f"{str(row.get('pick3', ''))[:19]:<21} "
            f"${float(row['score']):>8,.0f} "
            f"${float(row['base_ev']):>9,.0f} "
            f"{float(row['avg_cut_prob']):>6.1f}% "
            f"{float(row['p_top5_any']):>6.1f}% "
            f"({uses_str})"
        )
    print("=" * 96)


def main():
    parser = argparse.ArgumentParser(description="Constraint-aware combinatorial lineup optimizer")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N, help=f"Candidate pool size (default: {DEFAULT_TOP_N})")
    parser.add_argument("--top-combos", type=int, default=DEFAULT_TOP_COMBOS, help=f"Lineups to show (default: {DEFAULT_TOP_COMBOS})")
    parser.add_argument("--lineup-size", type=int, default=DEFAULT_LINEUP_SIZE, help=f"Players per lineup (default: {DEFAULT_LINEUP_SIZE})")
    parser.add_argument("--tournament", "-t", default=None, help="Tournament name (auto-detect if omitted)")

    parser.add_argument("--min-avg-cut", type=float, default=0.84, help="Minimum average cut probability (0-1)")
    parser.add_argument("--max-last-use", type=int, default=1, help="Max players with 1 use remaining")
    parser.add_argument("--min-leverage-players", type=int, default=0, help="Minimum leverage players required in lineup")
    parser.add_argument("--leverage-threshold", type=float, default=0.65, help="Leverage threshold for leverage-player count")

    parser.add_argument("--ceiling-weight", type=float, default=DEFAULT_CEILING_WEIGHT)
    parser.add_argument("--leverage-weight", type=float, default=DEFAULT_LEVERAGE_WEIGHT)
    parser.add_argument("--risk-weight", type=float, default=DEFAULT_RISK_WEIGHT)
    parser.add_argument("--usage-weight", type=float, default=DEFAULT_USAGE_WEIGHT)
    parser.add_argument("--last-use-penalty", type=float, default=DEFAULT_LAST_USE_PENALTY)

    parser.add_argument("--lock", action="append", default=[], help="Lock player(s), comma-separated or repeat flag")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude player(s), comma-separated or repeat flag")
    parser.add_argument("--save-csv", action="store_true", help="Save results to outputs/optimal_lineups.csv")
    args = parser.parse_args()

    results_df, eligible, importance, tournament = run_optimizer(
        top_n=max(8, int(args.top_n)),
        top_combos=max(1, int(args.top_combos)),
        tournament_name=args.tournament,
        lineup_size=max(2, int(args.lineup_size)),
        min_avg_cut_prob=float(args.min_avg_cut),
        max_last_use_players=max(0, int(args.max_last_use)),
        min_leverage_players=max(0, int(args.min_leverage_players)),
        leverage_threshold=float(args.leverage_threshold),
        ceiling_weight=float(args.ceiling_weight),
        leverage_weight=float(args.leverage_weight),
        risk_weight=float(args.risk_weight),
        usage_weight=float(args.usage_weight),
        last_use_penalty=float(args.last_use_penalty),
        locked_players=_split_names(args.lock),
        excluded_players=_split_names(args.exclude),
    )

    print_results(results_df, importance, tournament)

    meta = results_df.attrs.get("optimizer_meta", {})
    if meta:
        print(
            f"  Combos: {meta.get('scored_combos', 0):,}/{meta.get('total_combos', 0):,} passed "
            f"(cut-filtered={meta.get('skipped_by_cut', 0):,}, usage-filtered={meta.get('skipped_by_usage', 0):,}, "
            f"leverage-filtered={meta.get('skipped_by_leverage', 0):,})"
        )
        if meta.get("unresolved_locked"):
            print(f"  Unresolved lock names: {', '.join(meta['unresolved_locked'])}")
        if meta.get("unresolved_excluded"):
            print(f"  Unresolved exclude names: {', '.join(meta['unresolved_excluded'])}")

    if args.save_csv:
        out = OUTPUTS_DIR / "optimal_lineups.csv"
        results_df.to_csv(out, index=True)
        print(f"\n  Saved to {out}")


if __name__ == "__main__":
    main()
