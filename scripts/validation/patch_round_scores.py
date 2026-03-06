#!/usr/bin/env python3
"""
Patch master_training_data to add r1-r4 per-round scores and to-par.
Joins updated leaderboard CSVs (which now have r1_score..r4_to_par)
back onto the training data on player_id + tournament_id.
"""
import glob, numpy as np, pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
HISTORICAL_DIR = PROJECT_ROOT / "data" / "historical"

ROUND_COLS = ['r1_score', 'r2_score', 'r3_score', 'r4_score',
              'r1_to_par', 'r2_to_par', 'r3_to_par', 'r4_to_par']


def main():
    # Load master training data
    files = sorted(glob.glob(str(PROCESSED_DIR / "master_training_data_*.csv")))
    path  = Path(files[-1])
    print(f"Loading: {path}")
    master = pd.read_csv(path)
    print(f"  {len(master):,} rows, {len(master.columns)} columns")

    # Check if already patched
    if all(c in master.columns for c in ROUND_COLS):
        non_null = master['r1_score'].notna().sum()
        print(f"  r1_score already present ({non_null:,} non-null). Re-patching to refresh.")

    # Load all updated leaderboard CSVs
    master_years = sorted(master['year'].astype(int).unique())
    lb_frames = []
    for yr in master_years:
        f = HISTORICAL_DIR / f"leaderboards_{yr}.csv"
        if not f.exists():
            print(f"  WARN: missing leaderboards_{yr}.csv")
            continue
        df = pd.read_csv(f, low_memory=False)
        if 'r1_score' not in df.columns:
            print(f"  WARN: leaderboards_{yr}.csv has no r1_score — skip")
            continue
        lb_frames.append(df[['player_id', 'tournament_id'] + ROUND_COLS])

    if not lb_frames:
        print("ERROR: No leaderboard files with round scores found.")
        return

    lb = pd.concat(lb_frames, ignore_index=True)
    lb['player_id']     = lb['player_id'].astype(str)
    lb['tournament_id'] = lb['tournament_id'].astype(str)
    # Keep one row per player-tournament (shouldn't be dupes, but just in case)
    lb = lb.drop_duplicates(subset=['player_id', 'tournament_id'])
    print(f"  Leaderboard rows loaded: {len(lb):,} across {len(lb_frames)} years")
    print(f"  r1_score non-null: {lb['r1_score'].notna().sum():,}")

    # Normalise join keys in master
    master['_pid'] = master['player_id'].astype(str)
    master['_tid'] = master['tournament_id'].astype(str)

    # Drop existing round columns to avoid _x/_y suffixes on re-patch
    for col in ROUND_COLS:
        if col in master.columns:
            master = master.drop(columns=[col])

    # Merge
    before = len(master)
    master = master.merge(
        lb.rename(columns={'player_id': '_pid', 'tournament_id': '_tid'}),
        on=['_pid', '_tid'],
        how='left'
    )
    master = master.drop(columns=['_pid', '_tid'])
    assert len(master) == before, "Row count changed after merge — investigate"

    # Coverage report
    print("\n  Coverage report:")
    for col in ROUND_COLS:
        nn = master[col].notna().sum()
        pct = nn / len(master) * 100
        print(f"    {col}: {nn:,}/{len(master):,} ({pct:.1f}%)")

    # Save
    master.to_csv(path, index=False)
    print(f"\nSaved -> {path}")
    print(f"Columns now: {len(master.columns)}")


if __name__ == "__main__":
    main()
