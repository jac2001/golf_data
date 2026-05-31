#!/usr/bin/env python3
"""
Tournament simulation engine (Monte Carlo).

WHY SIMULATION INSTEAD OF XGBOOST FOR WINS
-------------------------------------------
XGBoost predicts win probability by pattern-matching historical features.
It cannot distinguish between two players who have the same mean expected SG
but very different round-to-round consistency. A boom-or-bust player (high
variance) wins more often than their average skill predicts, because golf
rewards whoever happens to be hot that week.

Simulation models this correctly:
  1. Estimate each player's expected SG per round (mean)
  2. Estimate their round-to-round variance (sigma)
  3. Simulate 10,000 tournaments by drawing round scores from Normal(mean, sigma)
  4. Count how often each player wins / finishes top 10 / etc.

This is essentially what DataGolf does, minus their Shotlink shot-level data.

PLAYER MEAN (mu)
----------------
mu = predictive_sg_weighted * 0.70   (season-long skill, DataGolf-weighted)
   + recent_sg_weighted    * 0.30   (recent form)
   + dg_fit_total                   (course fit adjustment, per round)

Then field-normalised so that field_mean(mu) = 0. This ensures the simulation
produces realistic cut lines and finishing distributions.

PLAYER SIGMA
------------
Computed from historical round scores (field-normalised), stored in
data/processed/player_variance.csv.  Falls back to skill-tier defaults if
a player has insufficient history (< 20 rounds).

  Elite players (top 50 in field):     ~2.85 strokes/round
  Mid-tier (50-150):                   ~3.05 strokes/round
  Fringe (150+):                       ~3.20 strokes/round

CUT SIMULATION
--------------
After R1+R2, retain the top 65 players by cumulative SG.  Players outside
the cut get no R3/R4 contribution and finish last in that simulation.

ROUND AUTOCORRELATION
---------------------
DataGolf found that 1 stroke better in R1 APP -> +0.06 strokes in R2.
We use a single global carry-over of 0.06 between consecutive rounds.
This is small but real — a hot player stays slightly hotter.

Usage
-----
  # Standalone — runs against current predictions
  python3 scripts/predictions/simulate_tournament.py

  # Import API
  from scripts.predictions.simulate_tournament import run_simulation
  result = run_simulation(tournament_id="R2026021")
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR      = ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR   = ROOT / "outputs"

VARIANCE_CSV  = PROCESSED_DIR / "player_variance.csv"
PREDICTIONS_CSV = OUTPUTS_DIR / "latest_predictions.csv"

# ── Defaults ──────────────────────────────────────────────────────────────────
N_SIMS   = 10_000
CUT_SIZE = 65       # players surviving the cut (PGA Tour standard)
AUTOCORR = 0.06     # round-to-round carry-over (DataGolf finding)

# Field-rank-based sigma fallbacks (used when < 20 historical rounds)
_SIGMA_TIERS = [
    (50,  2.85),   # top-50 calibre
    (150, 3.05),   # mid-tier
    (999, 3.20),   # fringe
]


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — build player variance table from historical round scores
# ═══════════════════════════════════════════════════════════════════════════════

def build_player_variance(min_rounds: int = 20, force: bool = False) -> pd.DataFrame:
    """Compute per-player round SD from the master training CSV.

    Each round score is field-normalised (player_score - field_avg_score for that
    round/tournament), so course difficulty doesn't inflate a player's variance.
    Then we compute SD across all their normalised rounds.

    Returns a DataFrame with columns: player_name, n_rounds, mean_sg, round_sd.
    Result is cached in VARIANCE_CSV.
    """
    if VARIANCE_CSV.exists() and not force:
        return pd.read_csv(VARIANCE_CSV)

    training = PROCESSED_DIR / "master_training_data_2016_2026.csv"
    if not training.exists():
        raise FileNotFoundError(f"Training data not found: {training}")

    print("  Building player variance table from training data...")
    df = pd.read_csv(training, low_memory=False)

    for c in ["r1_score", "r2_score", "r3_score", "r4_score"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Field-normalise each round: SG = field_mean - player_score (higher = better)
    rounds_df = df[["player_name", "tournament_id",
                    "r1_score", "r2_score", "r3_score", "r4_score"]].copy()
    for r in ["r1_score", "r2_score", "r3_score", "r4_score"]:
        field_avg = rounds_df.groupby("tournament_id")[r].transform("mean")
        rounds_df[r.replace("score", "sg")] = field_avg - rounds_df[r]

    # Stack all per-round SG observations per player
    stacked = pd.concat([
        rounds_df[["player_name", r.replace("score", "sg")]]
        .dropna(subset=[r.replace("score", "sg")])
        .rename(columns={r.replace("score", "sg"): "round_sg"})
        for r in ["r1_score", "r2_score", "r3_score", "r4_score"]
    ], ignore_index=True)

    stats = (stacked.groupby("player_name")["round_sg"]
             .agg(n_rounds="count", mean_sg="mean", round_sd="std")
             .reset_index())

    stats = stats[stats["n_rounds"] >= min_rounds].copy()
    stats["round_sd"] = stats["round_sd"].round(4)
    stats["mean_sg"]  = stats["mean_sg"].round(4)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    stats.to_csv(VARIANCE_CSV, index=False)
    print(f"  Saved {len(stats)} player variance records → {VARIANCE_CSV.name}")
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — build player profiles (mu + sigma) from predictions
# ═══════════════════════════════════════════════════════════════════════════════

def _default_sigma(world_rank: float) -> float:
    """Fallback sigma for players without sufficient round history."""
    rank = float(world_rank) if pd.notna(world_rank) else 200
    for cutoff, sigma in _SIGMA_TIERS:
        if rank <= cutoff:
            return sigma
    return _SIGMA_TIERS[-1][1]


def _norm_name(name: str) -> str:
    """Normalise player name to 'first last' lowercase for matching.

    Handles 'Last, First' (predictions format) and 'First Last' (training data).
    Strips accents so 'Åberg' == 'Aberg'.
    """
    import unicodedata
    s = str(name).strip()
    if "," in s:
        parts = s.split(",", 1)
        s = f"{parts[1].strip()} {parts[0].strip()}"
    # Strip accents (NFD decompose, then drop combining characters)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


def build_player_profiles(preds_df: pd.DataFrame,
                          variance_df: pd.DataFrame) -> pd.DataFrame:
    """Merge predictions with variance data to produce mu + sigma per player.

    MU — expected SG per round relative to this week's field:
      Priority 1: DG's final_pred (full course-adjusted prediction) when available
      Priority 2: predictive_sg_weighted * 0.70 + recent_sg_weighted * 0.30 + dg_fit_total
    Field-normalised to mean = 0.

    SIGMA — round-to-round standard deviation:
      Priority 1: DG's std_deviation from decompositions (already per-round)
      Priority 2: our computed historical round SD from player_variance.csv
      Priority 3: world-rank-based tier default
    """
    df = preds_df.copy()

    def _col(name: str) -> pd.Series:
        """Return column as numeric Series, or all-NaN Series if missing."""
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce")
        return pd.Series(np.nan, index=df.index, dtype=float)

    # ── Compute mu ─────────────────────────────────────────────────────────────
    final_pred = _col("final_pred")
    pred_sg    = _col("predictive_sg_weighted")
    recent_sg  = _col("recent_sg_weighted")
    fit        = _col("dg_fit_total")

    # DG's final_pred is the best available signal; use it if >50% field covered
    use_final_pred = final_pred.notna().mean() > 0.50
    if use_final_pred:
        mu_raw = final_pred.fillna(
            (pred_sg.fillna(pred_sg.median()) * 0.70 +
             recent_sg.fillna(recent_sg.median()) * 0.30 +
             fit.fillna(0.0))
        )
        mu_source = "DG final_pred"
    else:
        pred_sg   = pred_sg.fillna(pred_sg.median())
        recent_sg = recent_sg.fillna(recent_sg.median())
        fit       = fit.fillna(0.0)
        mu_raw    = pred_sg * 0.70 + recent_sg * 0.30 + fit
        mu_source = "predictive_sg blend"

    df["mu"] = mu_raw - mu_raw.mean()   # field-normalise

    # ── Attach sigma ───────────────────────────────────────────────────────────
    # Priority 1: DG's std_deviation (per-round scoring SD from decompositions)
    dg_sd = _col("std_deviation")
    use_dg_sd = dg_sd.notna().mean() > 0.50
    sigma_source = "DG std_deviation" if use_dg_sd else "historical/tier"

    # Priority 2: our historical round SD lookup
    var_lookup = {_norm_name(n): sd
                  for n, sd in zip(variance_df["player_name"],
                                   variance_df["round_sd"])}
    world_ranks = _col("world_rank")

    sigmas = []
    sources = []
    for idx, row in df.iterrows():
        # 1. DG decomposition SD
        if use_dg_sd and pd.notna(dg_sd.iloc[idx] if hasattr(dg_sd, 'iloc') else dg_sd.get(idx)):
            try:
                val = float(dg_sd.iloc[idx] if hasattr(dg_sd, 'iloc') else dg_sd.get(idx))
                if 1.5 < val < 6.0:   # sanity bounds
                    sigmas.append(round(val, 4))
                    sources.append("dg")
                    continue
            except (TypeError, ValueError):
                pass

        # 2. Historical round SD from our computed variance table
        key = _norm_name(row.get("player_name", ""))
        if key in var_lookup:
            sigmas.append(var_lookup[key])
            sources.append("hist")
            continue

        # 3. Rank-tier default
        rank = world_ranks.iloc[idx] if hasattr(world_ranks, 'iloc') else world_ranks.get(idx, 200)
        sigmas.append(_default_sigma(rank))
        sources.append("tier")

    df["sigma"] = sigmas

    # Report source breakdown
    from collections import Counter
    src_counts = Counter(sources)
    print(f"  mu source: {mu_source}  |  sigma: "
          + "  ".join(f"{k}={v}" for k, v in sorted(src_counts.items())))

    return df[["player_name", "mu", "sigma"]].reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — Monte Carlo simulation
# ═══════════════════════════════════════════════════════════════════════════════

def simulate(profiles: pd.DataFrame,
             n_sims: int = N_SIMS,
             cut_size: int = CUT_SIZE,
             seed: int | None = 42) -> pd.DataFrame:
    """Run Monte Carlo tournament simulation.

    profiles: DataFrame with player_name, mu, sigma.
    Returns: same index + win/top5/top10/top20/make_cut probabilities.

    The simulation draws round scores from Normal(mu, sigma).  After R1+R2,
    the top cut_size players survive.  R3+R4 are simulated for survivors only.
    A small autocorrelation (AUTOCORR) carries hot/cold streaks between rounds.
    """
    rng = np.random.default_rng(seed)
    n   = len(profiles)
    mu  = profiles["mu"].values.astype(float)
    sig = profiles["sigma"].values.astype(float)

    wins   = np.zeros(n, dtype=np.int32)
    top5   = np.zeros(n, dtype=np.int32)
    top10  = np.zeros(n, dtype=np.int32)
    top20  = np.zeros(n, dtype=np.int32)
    cuts   = np.zeros(n, dtype=np.int32)

    # Clip cut size to field size
    cut_size = min(cut_size, n - 1)

    for _ in range(n_sims):
        # ── R1 ────────────────────────────────────────────────────────────────
        r1 = rng.normal(mu, sig)

        # ── R2 (small carry-over from R1) ─────────────────────────────────────
        r2 = rng.normal(mu, sig) + AUTOCORR * (r1 - mu)

        halfway = r1 + r2

        # ── Cut: keep top cut_size by cumulative SG ────────────────────────────
        # argsort descending → first cut_size indices are the survivors
        sorted_idx = np.argpartition(halfway, -cut_size)[-cut_size:]
        survived   = np.zeros(n, dtype=bool)
        survived[sorted_idx] = True
        cuts += survived

        # ── R3 + R4 for survivors ──────────────────────────────────────────────
        r3 = np.where(survived,
                      rng.normal(mu, sig) + AUTOCORR * (r2 - mu),
                      -1e9)
        r4 = np.where(survived,
                      rng.normal(mu, sig) + AUTOCORR * (r3 - mu),
                      -1e9)

        total = r1 + r2 + r3 + r4
        total[~survived] = -1e9   # missed-cut players ranked last

        # ── Leaderboard ────────────────────────────────────────────────────────
        # rank_of[i] = position of player i (0 = winner)
        rank_of         = np.empty(n, dtype=np.int32)
        rank_of[np.argsort(-total)] = np.arange(n)

        wins  += rank_of == 0
        top5  += rank_of < 5
        top10 += rank_of < 10
        top20 += rank_of < 20

    out = profiles[["player_name"]].copy()
    out["win_prob_sim"]      = (wins  / n_sims).round(4)
    out["top5_prob_sim"]     = (top5  / n_sims).round(4)
    out["top10_prob_sim"]    = (top10 / n_sims).round(4)
    out["top20_prob_sim"]    = (top20 / n_sims).round(4)
    out["make_cut_prob_sim"] = (cuts  / n_sims).round(4)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

class InsufficientDGDataError(RuntimeError):
    """Raised when DG final_pred coverage is too low to run the simulation."""


def run_simulation(tournament_id: str | None = None,
                   n_sims: int = N_SIMS,
                   verbose: bool = True) -> pd.DataFrame:
    """End-to-end: load predictions → build profiles → simulate → return results.

    Returns a DataFrame sorted by win_prob_sim (descending).

    Raises InsufficientDGDataError if DG final_pred coverage is ≤ 50%.
    The pipeline catches this and skips the simulation step without failing.
    """
    # ── Load predictions ───────────────────────────────────────────────────────
    if not PREDICTIONS_CSV.exists():
        raise FileNotFoundError(f"Predictions not found: {PREDICTIONS_CSV}")

    preds = pd.read_csv(PREDICTIONS_CSV)
    if tournament_id:
        tid = str(tournament_id).upper()
        preds = preds[preds["tournament_id"].astype(str).str.upper() == tid]
    if preds.empty:
        raise ValueError(f"No predictions found for tournament_id={tournament_id}")

    # ── Guard: require DG data ─────────────────────────────────────────────────
    # The simulation's mu is built from DG's final_pred. Without it, the fallback
    # (predictive_sg blend) produces ~9x compressed mu spread → unrealistic probs.
    # The pipeline always fetches DG data before simulating; this guard surfaces
    # clearly when that fetch was skipped or failed.
    if "final_pred" in preds.columns:
        fp_coverage = pd.to_numeric(preds["final_pred"], errors="coerce").notna().mean()
    else:
        fp_coverage = 0.0

    if fp_coverage <= 0.50:
        raise InsufficientDGDataError(
            f"DG simulation requires final_pred coverage >50% "
            f"(current: {fp_coverage:.0%} of {len(preds)} players). "
            "Run fetch_dg_odds.py first."
        )

    if verbose:
        print(f"  Field: {len(preds)} players  |  DG final_pred coverage: {fp_coverage:.0%}")

    # ── Load / build variance table ────────────────────────────────────────────
    variance_df = build_player_variance()
    var_names = set(variance_df["player_name"].apply(_norm_name))
    matched = sum(1 for n in preds["player_name"] if _norm_name(str(n)) in var_names)
    if verbose:
        print(f"  Variance lookup: {matched}/{len(preds)} players matched ({matched/len(preds):.0%})")

    # ── Build profiles ─────────────────────────────────────────────────────────
    profiles = build_player_profiles(preds, variance_df)

    if verbose:
        print(f"  mu range:    {profiles.mu.min():.2f}  →  {profiles.mu.max():.2f}")
        print(f"  sigma range: {profiles.sigma.min():.2f}  →  {profiles.sigma.max():.2f}")

    # ── Simulate ───────────────────────────────────────────────────────────────
    if verbose:
        print(f"  Running {n_sims:,} simulations...")

    results = simulate(profiles, n_sims=n_sims)
    results = results.sort_values("win_prob_sim", ascending=False).reset_index(drop=True)

    # ── Merge back the XGBoost win_prob for comparison ─────────────────────────
    if "win_prob" in preds.columns:
        xgb_probs = preds[["player_name", "win_prob", "top10_prob"]].copy()
        xgb_probs.columns = ["player_name", "win_prob_xgb", "top10_prob_xgb"]
        results = results.merge(xgb_probs, on="player_name", how="left")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def write_back(results: pd.DataFrame) -> None:
    """Merge simulation probabilities back into latest_predictions.csv.

    Adds win_prob_sim, top5_prob_sim, top10_prob_sim, top20_prob_sim,
    make_cut_prob_sim columns. Overwrites any previous simulation columns.
    """
    if not PREDICTIONS_CSV.exists():
        print(f"  [warn] Cannot write back — {PREDICTIONS_CSV.name} not found")
        return

    preds = pd.read_csv(PREDICTIONS_CSV)
    sim_cols = ["win_prob_sim", "top5_prob_sim", "top10_prob_sim",
                "top20_prob_sim", "make_cut_prob_sim"]

    # Drop old sim columns so we don't get duplicates on re-run
    preds = preds.drop(columns=[c for c in sim_cols if c in preds.columns],
                       errors="ignore")

    merge_df = results[["player_name"] + sim_cols].copy()
    preds = preds.merge(merge_df, on="player_name", how="left")
    preds.to_csv(PREDICTIONS_CSV, index=False)
    written = merge_df["win_prob_sim"].notna().sum()
    print(f"  Wrote simulation probs for {written}/{len(preds)} players → {PREDICTIONS_CSV.name}")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Monte Carlo tournament simulation")
    parser.add_argument("--tournament-id", default=None)
    parser.add_argument("--n-sims", type=int, default=N_SIMS)
    parser.add_argument("--top", type=int, default=20, help="Players to display")
    parser.add_argument("--rebuild-variance", action="store_true",
                        help="Force rebuild of player variance table")
    parser.add_argument("--no-write-back", action="store_true",
                        help="Skip writing sim probs back to latest_predictions.csv")
    args = parser.parse_args()

    if args.rebuild_variance:
        build_player_variance(force=True)

    print(f"\nRunning simulation (n={args.n_sims:,})...")
    try:
        results = run_simulation(tournament_id=args.tournament_id, n_sims=args.n_sims)
    except InsufficientDGDataError as e:
        print(f"\n[SKIP] {e}")
        print("  Simulation skipped — win_prob_xgb unchanged in latest_predictions.csv")
        return 0

    # ── Display ────────────────────────────────────────────────────────────────
    top = results.head(args.top).copy()
    top.index = range(1, len(top) + 1)

    cols = ["player_name", "win_prob_sim", "top10_prob_sim", "make_cut_prob_sim"]
    if "win_prob_xgb" in top.columns:
        cols += ["win_prob_xgb", "top10_prob_xgb"]

    # Format as percentages
    pct_cols = [c for c in cols if "prob" in c]
    display = top[cols].copy()
    for c in pct_cols:
        display[c] = display[c].apply(lambda x: f"{x:.1%}")

    print(f"\n{'─'*70}")
    print(f"  {'Player':<25}  {'Win(sim)':>9}  {'Top10(sim)':>10}  {'Cut(sim)':>8}", end="")
    if "win_prob_xgb" in cols:
        print(f"  {'Win(xgb)':>8}  {'T10(xgb)':>8}", end="")
    print()
    print(f"{'─'*70}")

    for i, row in display.iterrows():
        name = str(row["player_name"])[:25]
        print(f"  {name:<25}  {row['win_prob_sim']:>9}  {row['top10_prob_sim']:>10}  {row['make_cut_prob_sim']:>8}", end="")
        if "win_prob_xgb" in cols:
            print(f"  {row['win_prob_xgb']:>8}  {row['top10_prob_xgb']:>8}", end="")
        print()

    # ── Calibration check ─────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"  Calibration check (should sum to ~100%):")
    print(f"    Win probs sum:   {results['win_prob_sim'].sum():.1%}")
    print(f"    Top10 probs sum: {results['top10_prob_sim'].sum():.1%}  "
          f"(expect ~{min(10, len(results))/len(results)*len(results):.0f}  ≈ "
          f"{10/len(results)*100:.0f}% × {len(results)} players = ~10)")
    print(f"    Cut probs sum:   {results['make_cut_prob_sim'].sum():.1%}  "
          f"(expect ~{65})")

    # ── Write back to latest_predictions.csv ──────────────────────────────────
    if not args.no_write_back:
        write_back(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
