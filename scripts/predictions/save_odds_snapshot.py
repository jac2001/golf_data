"""
Save Odds Snapshot
==================
Saves a lightweight timestamped CSV of current odds from latest_predictions.csv.
Called automatically by refresh_odds.py after each odds refresh so the dashboard
can compute movement (drift) between successive snapshots.

Schema saved:
    player_id, player_name, odds_to_win, odds_numeric, snapshot_at

Usage:
    python3 scripts/predictions/save_odds_snapshot.py
"""

import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

PROJECT_ROOT  = Path(__file__).parent.parent.parent
OUTPUTS_DIR   = PROJECT_ROOT / "outputs"
SNAPSHOT_DIR  = PROJECT_ROOT / "data" / "odds" / "snapshots"
PREDS_FILE    = OUTPUTS_DIR / "latest_predictions.csv"


def save_snapshot() -> Path | None:
    if not PREDS_FILE.exists():
        print(f"  ⚠  {PREDS_FILE} not found — skipping snapshot")
        return None

    df = pd.read_csv(PREDS_FILE)

    # Keep only the columns we need for drift tracking
    cols = [c for c in ["player_id", "player_name", "odds_to_win", "odds_numeric"] if c in df.columns]
    if "odds_numeric" not in cols:
        print("  ⚠  odds_numeric column missing — skipping snapshot")
        return None

    snap = df[cols].copy()
    snap["snapshot_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M")
    out  = SNAPSHOT_DIR / f"odds_snapshot_{ts}.csv"
    snap.to_csv(out, index=False)
    print(f"  ✅ Odds snapshot saved → {out.name}  ({len(snap)} players)")
    return out


def _prune_old_snapshots(keep: int = 20):
    """Keep only the N most recent snapshot CSVs to avoid bloat."""
    snaps = sorted(SNAPSHOT_DIR.glob("odds_snapshot_*.csv"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snaps[keep:]:
        old.unlink()


if __name__ == "__main__":
    result = save_snapshot()
    _prune_old_snapshots()
    sys.exit(0 if result else 1)
