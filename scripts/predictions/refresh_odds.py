"""                                                                                
  Refresh Odds — Lightweight odds-only update
  ============================================
  Updates odds columns in latest_predictions.csv without re-running
  the full ML pipeline. Takes ~30 seconds vs several minutes for a full run.

  What changes:   odds_to_win, vegas_prob, model_vs_vegas_edge,
                  is_value_bet, odds_drift_level
  What stays:     win_prob, top5_prob, top10_prob, expected_value
                  (those require a full model rerun)

  Usage:
      python3 scripts/predictions/refresh_odds.py
      python3 scripts/predictions/refresh_odds.py --tournament-id R2026007
"""

import sys 
import argparse 
import pandas as pd 
from pathlib import Path   
from datetime import datetime 


PROJECT_ROOT = Path(__file__).parent.parent.parent

# Add scrapers dir to path — same pattern used across all scripts in this project.
# This lets us import fetch_pga_odds by filename rather than as a package path,
# which avoids the "No module named 'scripts'" error when scripts/ has no __init__.py
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "scrapers"))
from fetch_pga_odds import fetch_and_merge_odds


def get_current_tournament_id() -> str | None:
    """Read this week's tournament ID from the schedule CSV."""
    sched_path = PROJECT_ROOT / "data" / "raw" / "schedule_2026.csv"
    if not sched_path.exists():
        return None

    sched = pd.read_csv(sched_path)
    today = datetime.now().strftime("%Y-%m-%d")

    # Active = tournament has started but not finished
    active = sched[(sched["start_date"] <= today) & (sched["end_date"] >= today)]
    if not active.empty:
        return str(active.iloc[0]["tournament_id"])

    # Not in a tournament week — grab the next upcoming one
    upcoming = sched[sched["start_date"] > today].sort_values("start_date")
    if not upcoming.empty:
        return str(upcoming.iloc[0]["tournament_id"])

    return None


def _norm(name: str) -> str:
    """Normalize 'Last, First' or 'First Last' → 'first last' for matching."""
    parts = str(name).split(",")
    if len(parts) == 2:
        return f"{parts[1].strip()} {parts[0].strip()}".lower()
    return str(name).strip().lower()


def _odds_to_prob(odds_numeric) -> float:
    """Convert American odds integer to implied probability (0–1)."""
    try:
        o = float(odds_numeric)
        return 100 / (o + 100) if o >= 0 else abs(o) / (abs(o) + 100)
    except Exception:
        return 0.0


def _drift_label(edge: float) -> str:
    """Classify model-vs-market edge into a readable label."""
    if edge > 0.05:   return "MODEL>>VEGAS"
    if edge > 0.02:   return "SIGNIFICANT"
    if edge > 0.01:   return "MODERATE"
    if edge < -0.05:  return "VEGAS>>MODEL"
    return "OK"




def refresh_odds(tournament_id: str) -> bool:
    preds_path = PROJECT_ROOT / 'outputs' / 'latest_predictions.csv'
    
    if not preds_path.exists():
        print(f"Error: {preds_path} not found. Run the full pipeline first.")
        return False
    
    print(f"  Fetching fresh odds for {tournament_id} ...")
    odds_df = fetch_and_merge_odds(tournament_id)

    if odds_df.empty:
        print("ERROR: No odds data returned from API.")
        return False

    print(f"  Got odds for {len(odds_df)} players.")

    preds = pd.read_csv(preds_path)

    # ── Match odds → predictions by player_id (most reliable) ──────────
    preds["player_id"]   = preds["player_id"].astype(str)
    odds_df["player_id"] = odds_df["player_id"].astype(str)

    # Keep only the columns we need from odds_df
    odds_slim = odds_df[["player_id", "odds_to_win", "odds_numeric"]].copy()
    odds_slim.columns = ["player_id", "new_odds_to_win", "new_odds_numeric"]

    merged = preds.merge(odds_slim, on="player_id", how="left")

    # Fill in new odds where available, keep old value where not
    merged["odds_to_win"]  = merged["new_odds_to_win"].combine_first(merged["odds_to_win"])
    merged["odds_numeric"] = merged["new_odds_numeric"].combine_first(merged["odds_numeric"])
    merged = merged.drop(columns=["new_odds_to_win", "new_odds_numeric"])
    
    
    
    # ------------- Recompute derived odds columns ----------------
    
    merged["vegas_prob"] = merged["odds_numeric"].apply(_odds_to_prob)
    if "win_prob" in merged.columns:
          merged["model_vs_vegas_edge"] = merged["win_prob"] - merged["vegas_prob"]
          merged["is_value_bet"]        = merged["model_vs_vegas_edge"] > 0
          merged["odds_drift_level"]    = merged["model_vs_vegas_edge"].apply(_drift_label)

      # ── Timestamp ────────────────────────────────────────────────────────
    merged["odds_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    merged.to_csv(preds_path, index=False)

    n_value  = int(merged["is_value_bet"].sum()) if "is_value_bet" in merged.columns else "—"
    n_edge   = int((merged["model_vs_vegas_edge"].abs() > 0.03).sum()) if "model_vs_vegas_edge" in merged.columns else "—"
    print(f"  ✅ Saved. Value bets: {n_value}  |  Players with edge >3pts: {n_edge}")

    # Auto-save a drift snapshot so the dashboard can track odds movement
    try:
        _snap_script = PROJECT_ROOT / "scripts" / "predictions" / "save_odds_snapshot.py"
        import subprocess as _sp
        _sp.run(["python3", str(_snap_script)], capture_output=True, cwd=PROJECT_ROOT)
    except Exception:
        pass  # Non-fatal; dashboard will just show no movement data

    return True
    

def main():
    parser = argparse.ArgumentParser(description="Refresh odds without full model rerun")
    parser.add_argument("--tournament-id", "-t", default=None,
                        help="Tournament ID (e.g. R2026007). Auto-detects if omitted.")
    args = parser.parse_args()

    t_id = args.tournament_id or get_current_tournament_id()
    if not t_id:
        print("ERROR: Could not determine current tournament ID.")
        sys.exit(1)

    print(f"\n🔄 Refreshing odds for tournament: {t_id}")
    ok = refresh_odds(t_id)
    print()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()