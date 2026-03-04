"""
Closing Line Value (CLV) Tracker
=================================
After each tournament closes (Thursday tee time), compare:
  - Model's implied probability at prediction time
  - Sportsbook's closing line (last odds snapshot before play starts)

Positive CLV = model was "smarter" than the market at close.
Beating the close consistently = real edge.

Run once per tournament, ideally just before Thursday tee time:
  python3 scripts/validation/track_clv.py --tournament-id R2026009 --tournament-name "Arnold Palmer Invitational"

Or called automatically from auto_record_results.py after results are recorded.
"""

import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "odds" / "snapshots"
PREDICTIONS_DIR = PROJECT_ROOT / "outputs"
TRACKING_DIR = PROJECT_ROOT / "data" / "prediction_tracking"
CLV_FILE = TRACKING_DIR / "clv_history.csv"


def american_to_implied(odds: float) -> float:
    """Convert American odds to implied probability (no vig removal)."""
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def _norm(name: str) -> str:
    return str(name).lower().strip()


def load_closing_line(tournament_id: str) -> pd.DataFrame:
    """
    Load the most recent odds snapshot for a tournament.
    This is the 'closing line' — last market price before play starts.

    Returns DataFrame with: player_name, closing_implied_prob, closing_odds, snapshot_at
    """
    # Prefer snapshots tagged with this tournament ID
    snapshots = sorted(SNAPSHOTS_DIR.glob(f"odds_snapshot_*{tournament_id}*.csv"))
    if not snapshots:
        # Fall back to all snapshots, take the latest
        snapshots = sorted(SNAPSHOTS_DIR.glob("odds_snapshot_*.csv"))

    if not snapshots:
        raise FileNotFoundError(f"No odds snapshots found in {SNAPSHOTS_DIR}")

    closing = pd.read_csv(snapshots[-1])
    snap_time = closing["snapshot_at"].iloc[0] if "snapshot_at" in closing.columns else "unknown"
    print(f"  Closing line: {snapshots[-1].name}  (t={snap_time})")

    closing["player_name_norm"] = closing["player_name"].apply(_norm)

    if "odds_numeric" in closing.columns:
        closing["closing_odds"] = pd.to_numeric(closing["odds_numeric"], errors="coerce")
        closing["closing_implied_prob"] = closing["closing_odds"].apply(
            lambda x: american_to_implied(x) if pd.notna(x) else np.nan
        )
    else:
        closing["closing_odds"] = np.nan
        closing["closing_implied_prob"] = np.nan

    return closing[["player_name", "player_name_norm", "closing_odds", "closing_implied_prob"]].dropna(
        subset=["closing_implied_prob"]
    )


def load_model_predictions(tournament_id: str) -> pd.DataFrame:
    """Load the model predictions for a tournament."""
    candidates = sorted(PREDICTIONS_DIR.glob(f"*{tournament_id.lower()}*predictions*.csv"))
    if not candidates:
        candidates = [PREDICTIONS_DIR / "latest_predictions.csv"]

    pred_file = candidates[0]
    if not pred_file.exists():
        raise FileNotFoundError(f"No prediction file found for {tournament_id}")

    preds = pd.read_csv(pred_file)
    print(f"  Predictions:  {pred_file.name} ({len(preds)} players)")

    # Prefer raw (pre-calibration/normalization) win_prob as model's true belief
    prob_col = "win_prob_raw" if "win_prob_raw" in preds.columns else "win_prob"
    preds["model_win_prob"] = pd.to_numeric(preds[prob_col], errors="coerce")
    preds["player_name_norm"] = preds["player_name"].apply(_norm)

    return preds[["player_name", "player_name_norm", "model_win_prob"]].dropna(subset=["model_win_prob"])


def compute_clv(tournament_id: str, tournament_name: str = "") -> pd.DataFrame:
    """
    Compute CLV for all players with both a model prediction and a closing line.

    clv_pp = (model_prob - closing_prob) * 100  [percentage points]
    Positive = model was higher than the market close
    log_clv  = log(model_prob / closing_prob)   [Kelly-style, sign matches clv_pp]
    """
    print(f"\nComputing CLV for {tournament_id} ({tournament_name})...")

    closing = load_closing_line(tournament_id)
    preds = load_model_predictions(tournament_id)

    merged = preds.merge(closing, on="player_name_norm", how="inner", suffixes=("_model", "_closing"))
    print(f"  Matched {len(merged)}/{len(preds)} players to closing line")

    if merged.empty:
        print("  No matches — CLV cannot be computed.")
        return pd.DataFrame()

    merged["clv_pp"] = (merged["model_win_prob"] - merged["closing_implied_prob"]) * 100
    merged["log_clv"] = np.log(
        (merged["model_win_prob"] + 1e-6) / (merged["closing_implied_prob"] + 1e-6)
    ).round(4)

    merged["tournament_id"] = tournament_id
    merged["tournament_name"] = tournament_name
    merged["computed_at"] = datetime.now().isoformat()

    out_cols = [
        "tournament_id", "tournament_name",
        "player_name_model",
        "model_win_prob", "closing_implied_prob", "closing_odds",
        "clv_pp", "log_clv", "computed_at",
    ]
    return merged[out_cols].sort_values("model_win_prob", ascending=False)


def save_clv(clv_df: pd.DataFrame) -> None:
    """Append CLV results to the history file, replacing any existing rows for this tournament."""
    TRACKING_DIR.mkdir(parents=True, exist_ok=True)

    tid = clv_df["tournament_id"].iloc[0]
    if CLV_FILE.exists():
        existing = pd.read_csv(CLV_FILE)
        existing = existing[existing["tournament_id"] != tid]
        combined = pd.concat([existing, clv_df], ignore_index=True)
    else:
        combined = clv_df

    combined.to_csv(CLV_FILE, index=False)
    print(f"  Saved → {CLV_FILE} ({len(combined)} total rows)")


def print_summary(clv_df: pd.DataFrame) -> None:
    print("\n" + "=" * 60)
    print("  CLOSING LINE VALUE REPORT")
    print("=" * 60)
    for _, row in clv_df.head(10).iterrows():
        arrow = "▲" if row["clv_pp"] > 0 else "▼"
        print(
            f"  {row['player_name_model']:<28} "
            f"model={row['model_win_prob']*100:.1f}%  "
            f"close={row['closing_implied_prob']*100:.1f}%  "
            f"CLV={arrow}{abs(row['clv_pp']):.1f}pp"
        )
    avg_clv = clv_df["clv_pp"].mean()
    pct_pos = (clv_df["clv_pp"] > 0).mean() * 100
    print(f"\n  Avg CLV (all matched): {avg_clv:+.2f} pp")
    print(f"  Players model > close: {pct_pos:.0f}%")
    print("=" * 60)


def run(tournament_id: str, tournament_name: str = "", save: bool = True) -> pd.DataFrame:
    """Entry point callable from other scripts."""
    try:
        clv_df = compute_clv(tournament_id, tournament_name)
        if clv_df.empty:
            return clv_df
        print_summary(clv_df)
        if save:
            save_clv(clv_df)
        return clv_df
    except FileNotFoundError as e:
        print(f"  CLV skipped: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute closing line value for a tournament")
    parser.add_argument("--tournament-id", required=True, help="e.g. R2026009")
    parser.add_argument("--tournament-name", default="", help="Display name")
    parser.add_argument("--no-save", action="store_true", help="Print only, don't save to clv_history.csv")
    args = parser.parse_args()

    run(args.tournament_id, args.tournament_name, save=not args.no_save)


