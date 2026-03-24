#!/usr/bin/env python3


""" 
Live In-Play Predictions Update
================================
After each round completes, this script blends the player's actual 
score with the pre-tournament model projection to produce a 
"live projection" - a running estimate of their 4-round total. 
WHY THIS MATTERS:
The pre-tournament model was trained on historical data.
It doesn't know what McIlroy shot in Round 1. Once R1 finishes,
we have real evidence. This script incorporates that evidence.

THE MATH:
A 4-round tournament is 4 equal slices of information.
After R1, we know 1 slice is real. We keep the model for the rest.

updated = actual_vs_field + (model_projection × rounds_remaining/4)

"vs field" means we subtract the field average so a score of 0.0
means exactly average. Negative = better than field, positive = worse.

EXAMPLE after Round 1:
McIlroy's model projected_score_vs_field = -2.5
He shot 72 (E). Field averaged 70.3 → actual_r1_vs_field = +1.7
updated = +1.7 + (-2.5 × 3/4)
        = +1.7 + (-1.875)
        = -0.175   ← now projected very close to field average
"""

import argparse
import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"
LIVE_DIR     = PROJECT_ROOT / "data" / "live"


def _to_float(series: pd.Series) -> pd.Series:
    """Safely convert any column to float — non-numeric values become NaN."""
    return pd.to_numeric(series, errors="coerce")



def run_live_update(tournament_id: str = None) -> pd.DataFrame:
    """
    Main function: loads predictions + leaderboard, blends them, saves result.

    Args:
        tournament_id: e.g. "R2026009". If None, uses most recently modified leaderboard.

    Returns:
        Updated predictions DataFrame (also saved to latest_predictions.csv).
    """

    # ── STEP 1: Load pre-tournament predictions ────────────────────────────
    # latest_predictions.csv has one row per player with columns like:
    #   win_prob, projected_score_vs_field, player_id, player_name, etc.
    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not preds_path.exists():
        print("ERROR: outputs/latest_predictions.csv not found.")
        return pd.DataFrame()

    preds = pd.read_csv(preds_path)
    print(f"Loaded {len(preds)} pre-tournament predictions.")

    # ── STEP 2: Find the live leaderboard ─────────────────────────────────
    # The leaderboard CSV has actual scores in columns R1, R2, R3, R4.
    # R1=63 means the player shot 63 strokes in Round 1.
    if tournament_id:
        lb_path = LIVE_DIR / f"leaderboard_{tournament_id.lower()}.csv"
    else:
        # Use the most recently modified leaderboard file
        candidates = sorted(
            LIVE_DIR.glob("leaderboard_r*.csv"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        lb_path = candidates[0] if candidates else None

    if not lb_path or not lb_path.exists():
        print("ERROR: No leaderboard file found. Run the leaderboard scraper first.")
        return preds

    lb = pd.read_csv(lb_path)
    print(f"Loaded leaderboard: {lb_path.name} ({len(lb)} players)")

    # ── STEP 3: Determine how many rounds are complete ─────────────────────
    # A round is "complete" when more than 50% of the field has a score for it.
    # We use 50% because some players in a round may still be on the course.
    n = len(lb)
    r1_done = _to_float(lb["R1"]).notna().sum() / n > 0.5
    r2_done = _to_float(lb["R2"]).notna().sum() / n > 0.5
    r3_done = _to_float(lb["R3"]).notna().sum() / n > 0.5
    r4_done = _to_float(lb["R4"]).notna().sum() / n > 0.5

    rounds_complete = sum([r1_done, r2_done, r3_done, r4_done])
    print(f"Rounds complete: {rounds_complete}/4")

    if rounds_complete == 0:
        print("No rounds complete yet — pre-tournament projections unchanged.")
        return preds

    if rounds_complete == 4:
        print("Tournament complete — no projection update needed.")
        return preds

    # ── STEP 4: Compute field average per round ────────────────────────────
    # We subtract the field average to normalize for course/weather conditions.
    # A 66 on a day when the field averaged 70 is -4 vs field (excellent).
    # A 66 on a day when the field averaged 65 is +1 vs field (below average).
    # Players who missed cut or withdrew get assigned the field average (0 vs field).
    r1_avg = float(_to_float(lb["R1"]).mean()) if r1_done else 0.0
    r2_avg = float(_to_float(lb["R2"]).mean()) if r2_done else 0.0
    r3_avg = float(_to_float(lb["R3"]).mean()) if r3_done else 0.0
    r4_avg = float(_to_float(lb["R4"]).mean()) if r4_done else 0.0
    print(f"Field averages — R1: {r1_avg:.2f}  R2: {r2_avg:.2f}  R3: {r3_avg:.2f}  R4: {r4_avg:.2f}")

    # ── STEP 5: Compute each player's cumulative actual score vs field ─────
    # We sum (actual_score - field_avg) for each completed round.
    # Negative result = player is outperforming the field overall.
    lb["_actual_vs_field"] = 0.0  # running total, starts at zero

    if r1_done:
        r1 = _to_float(lb["R1"]).fillna(r1_avg)   # MC/WD players get field avg = 0 vs field
        lb["_actual_vs_field"] += (r1 - r1_avg)
    if r2_done:
        r2 = _to_float(lb["R2"]).fillna(r2_avg)
        lb["_actual_vs_field"] += (r2 - r2_avg)
    if r3_done:
        r3 = _to_float(lb["R3"]).fillna(r3_avg)
        lb["_actual_vs_field"] += (r3 - r3_avg)
    if r4_done:
        r4 = _to_float(lb["R4"]).fillna(r4_avg)
        lb["_actual_vs_field"] += (r4 - r4_avg)

    # ── STEP 6: Merge actual scores + status onto predictions ─────────────
    # Join on player_id. Convert both sides to string to avoid int/str mismatch.
    # "left" join keeps all prediction rows; anyone not in leaderboard gets NaN.
    lb["_pid"] = lb["player_id"].astype(str)
    preds["_pid"] = preds["player_id"].astype(str)

    # Pull made_cut and status for active-player detection
    lb_merge_cols = ["_pid", "_actual_vs_field"]
    if "made_cut" in lb.columns:
        lb_merge_cols.append("made_cut")
    if "status" in lb.columns:
        lb_merge_cols.append("status")

    # Drop any stale copies of these columns from preds before merging
    _pre_drop = [c for c in ["made_cut", "status"] if c in preds.columns]
    if _pre_drop:
        preds = preds.drop(columns=_pre_drop)

    preds = preds.merge(
        lb[lb_merge_cols],
        on="_pid",
        how="left"
    ).drop(columns=["_pid"])

    # ── STEP 6b: Determine active players ─────────────────────────────────
    # Active = eligible to win. Inactive = cut/WD players.
    # Pre-cut (rounds_complete <= 1): treat all as active (no cut yet).
    INACTIVE_STATUSES = {"cut", "wd", "CUT", "WD", "MC", "MDF"}

    if rounds_complete <= 1:
        preds["_is_active"] = True
    else:
        is_active = pd.Series(True, index=preds.index)
        if "made_cut" in preds.columns:
            mc = pd.to_numeric(preds["made_cut"], errors="coerce")
            # made_cut==0 or False means missed cut
            explicitly_missed = mc == 0
            is_active = is_active & ~explicitly_missed
        if "status" in preds.columns:
            in_bad_status = preds["status"].astype(str).isin(INACTIVE_STATUSES)
            is_active = is_active & ~in_bad_status
        preds["_is_active"] = is_active
    
    # ── STEP 7: Compute the blended updated projection ─────────────────────
    #
    # remaining_weight tells us how much of the tournament is left to model:
    #   After R1: 3 rounds remain → 3/4 = 0.75
    #   After R2: 2 rounds remain → 2/4 = 0.50
    #   After R3: 1 round remains → 1/4 = 0.25
    #
    # projected_score_vs_field is the pre-tournament model's prediction of
    # the player's 4-round total vs field. We scale it by remaining_weight
    # to represent only the remaining rounds.
    
    rounds_remaining = 4 - rounds_complete
    remaining_weight = rounds_remaining / 4.0 
    
    if "projected_score_vs_field" in preds.columns:
        pre_proj = _to_float(preds["projected_score_vs_field"]).fillna(0.0)
    else:
        print("WARN: projected_score_vs_field not found — using 0.0 for remaining rounds.")
        pre_proj = pd.Series(0.0, index=preds.index)

    actual = preds["_actual_vs_field"].fillna(0.0)
    
    # The key line: actual completed rounds + model's view of remaining rounds 
    preds['live_projected_score'] = (actual + pre_proj * remaining_weight).round(2)
 
    # ── STEP 8: Re-rank by live projection ────────────────────────────────
    # rank(ascending=True) means rank 1 = lowest (best) projected score.
    preds["live_score_rank"] = (
          preds["live_projected_score"].rank(method="min", ascending=True).astype(int)
      )
    
    # ── STEP 9: Monte Carlo win/top5/top10 probability estimation ─────────
    # We can't run the classification model mid-tournament (missing features),
    # so we simulate 10k tournaments by adding noise to each player's
    # live_projected_score. The noise magnitude shrinks each round as actual
    # scores replace model uncertainty.
    N_SIMS = 10_000

    # Player-specific variance: derived from Q10/Q90 quantile spread
    # proj_floor = Q10 (bad scenario), proj_ceiling = Q90 (good scenario)
    # std ≈ spread / (2 * 1.28) based on normal distribution quantile relationship
    if "proj_ceiling" in preds.columns and "proj_floor" in preds.columns:
        full_std = (
            pd.to_numeric(preds["proj_floor"], errors="coerce").fillna(5) -
            pd.to_numeric(preds["proj_ceiling"], errors="coerce").fillna(-10)
        ) / (2 * 1.28)
    else:
        full_std = pd.Series(4.9, index=preds.index)

    full_std = full_std.clip(lower=1.0)  # floor at 1 stroke std

    # Remaining noise scales down as rounds complete — less uncertainty remains
    noise_std = full_std * np.sqrt(rounds_remaining / 4.0)

    live_scores = pd.to_numeric(preds["live_projected_score"], errors="coerce").fillna(0.0).values
    active_mask = preds["_is_active"].fillna(True).values

    rng = np.random.default_rng(seed=42)
    noise = rng.normal(0, noise_std.values[:, None], size=(len(preds), N_SIMS))
    sim_finals = live_scores[:, None] + noise

    # Eliminated players can't win — assign a large score so they rank last
    sim_finals[~active_mask] = 999.0

    # Rank within each simulated tournament (1 = best score = lowest)
    # argsort twice gives dense ranks
    ranks = sim_finals.argsort(axis=0).argsort(axis=0) + 1

    preds["live_win_prob"]   = ((ranks == 1).sum(axis=1) / N_SIMS).round(4)
    preds["live_top5_prob"]  = ((ranks <= 5).sum(axis=1) / N_SIMS).round(4)
    preds["live_top10_prob"] = ((ranks <= 10).sum(axis=1) / N_SIMS).round(4)

    # Change vs pre-tournament model (positive = improved)
    preds["live_win_prob_change"] = (
        preds["live_win_prob"] - pd.to_numeric(preds.get("win_prob", pd.Series(np.nan, index=preds.index)), errors="coerce")
    ).round(4)
    preds["live_top10_prob_change"] = (
        preds["live_top10_prob"] - pd.to_numeric(preds.get("top10_prob", pd.Series(np.nan, index=preds.index)), errors="coerce")
    ).round(4)

    preds["rounds_complete"] = rounds_complete

    n_active = int(active_mask.sum())
    win_sum  = float(preds.loc[active_mask, "live_win_prob"].sum())
    print(f"\nMonte Carlo: {N_SIMS:,} sims | active players: {n_active} | win_prob sum: {win_sum:.3f}")

    # ── STEP 10: Save updated projections ────────────────────────────────
    matched = preds['_actual_vs_field'].notna().sum()
    preds = preds.drop(columns=['_actual_vs_field', '_is_active'], errors='ignore')
    if "made_cut" in preds.columns:
        preds = preds.drop(columns=["made_cut"], errors='ignore')
    if "status" in preds.columns:
        preds = preds.drop(columns=["status"], errors='ignore')
    
    print(f"\nBlended {matched}/{len(preds)} players with actual scores.")
    print(f"Rounds complete: {rounds_complete}  |  Remaining weight: {remaining_weight:.2f}")
    print(f"\nTop 10 by live projection:")
    show_cols = [c for c in [
        "player_name", "live_projected_score", "live_score_rank",
        "live_win_prob", "live_win_prob_change", "win_prob", "projected_score_vs_field"
    ] if c in preds.columns]
    print(preds.nsmallest(10, "live_projected_score")[show_cols].to_string(index=False))


    # ── STEP 11: Save ─────────────────────────────────────────────────────
    # Overwrites latest_predictions.csv with new columns:
    #   live_projected_score      — updated projection blending actual + model
    #   live_score_rank           — rank within field (1 = best)
    #   live_win_prob             — Monte Carlo win probability
    #   live_top5_prob            — Monte Carlo top-5 probability
    #   live_top10_prob           — Monte Carlo top-10 probability
    #   live_win_prob_change      — change vs pre-tournament win_prob
    #   live_top10_prob_change    — change vs pre-tournament top10_prob
    #   rounds_complete           — how many rounds are done
    preds.to_csv(preds_path, index=False)
    print(f"\nSaved → {preds_path}")

    return preds




if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Blend actual scores with pre-tournament projections.'
    )
    
    
    parser.add_argument(
        "--tournament_id", default=None, 
        help='Tournament ID e.g. "R2026009". Omit to auto-detect from most recent leaderboards'
    )
    args = parser.parse_args()
    run_live_update(tournament_id=args.tournament_id)
    
    
    
    





