#!/usr/bin/env python3
"""
Patch master_training_data to add real scoring efficiency features.
These were all-zero due to a silent merge failure. Overwrites in-place.
"""
import glob, numpy as np, pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
HISTORICAL_DIR = PROJECT_ROOT / "data" / "historical"

STAT_IDS = {
    'recent_birdie_avg':   156,
    'recent_bogey_avg':    352,
    'recent_scoring_avg':  120,
    'recent_gir_pct':      103,
    'recent_scrambling':   130,
    'recent_bounce_back':  160,
    'recent_final_round':  299,
    'recent_sand_save':    111,
}
N_EVENTS = 5
DECAY    = 0.8


def recency_avg(values: list) -> float:
    """Recency-weighted average: newest value gets weight 1.0, decays by 0.8."""
    n = len(values)
    weights = np.array([DECAY ** i for i in range(n)][::-1])
    return float(np.average(values, weights=weights))


def main():
    # Load master training data
    files = sorted(glob.glob(str(PROCESSED_DIR / "master_training_data_*.csv")))
    path  = Path(files[-1])
    print(f"Loading: {path}")
    master = pd.read_csv(path)
    print(f"  {len(master)} rows, {len(master.columns)} columns")

    # Load all form_stats CSVs for years in training data
    master_years = sorted(master['year'].astype(int).unique())
    fs_frames = []
    for yr in master_years:
        f = HISTORICAL_DIR / f"form_stats_{yr}.csv"
        if f.exists():
            fs_frames.append(pd.read_csv(f, low_memory=False))
            print(f"  Loaded form_stats_{yr}.csv")
    if not fs_frames:
        print("ERROR: No form_stats files found")
        return
    fs = pd.concat(fs_frames, ignore_index=True)
    fs['player_id'] = fs['player_id'].astype(int)
    fs['stat_id']   = fs['stat_id'].astype(int)
    print(f"  form_stats total: {len(fs):,} rows, {fs['player_id'].nunique()} players")

    # Build lookup: player_id -> DataFrame sorted by tournament_id
    # Group once upfront to avoid re-filtering 46K times
    fs_by_player = {
        pid: grp.sort_values('tournament_id').reset_index(drop=True)
        for pid, grp in fs.groupby('player_id')
    }
    print(f"  Built player lookup for {len(fs_by_player)} players")

    # Compute features for every master row
    print(f"\n  Computing scoring efficiency features ({len(master):,} rows)...")
    results = {col: np.full(len(master), np.nan) for col in STAT_IDS}

    master_pid = master['player_id'].astype(int).values
    master_tid = master['tournament_id'].astype(str).values

    for i, (pid, tid) in enumerate(zip(master_pid, master_tid)):
        if i % 10000 == 0:
            print(f"    {i:,}/{len(master):,}")
        if pid not in fs_by_player:
            continue
        player_fs = fs_by_player[pid]
        # All form_stats entries BEFORE this tournament
        prior = player_fs[player_fs['tournament_id'] < tid]
        if prior.empty:
            continue
        for col, stat_id in STAT_IDS.items():
            rows = prior[prior['stat_id'] == stat_id].tail(N_EVENTS)
            vals = pd.to_numeric(rows['stat_value'], errors='coerce').dropna().tolist()
            if vals:
                results[col][i] = recency_avg(vals)

    # Fill NaN with field median, update master columns
    print("\n  Coverage report:")
    for col, arr in results.items():
        series = pd.Series(arr)
        non_null = series.notna().sum()
        median = series.median()
        if pd.isna(median):
            median = 0.0
        master[col] = series.fillna(median).values
        pct = non_null / len(master) * 100
        print(f"    {col}: {non_null:,}/{len(master):,} from data ({pct:.1f}%), median fill={median:.3f}")

    # Save
    master.to_csv(path, index=False)
    print(f"\nSaved -> {path}")
    print("Next: run train_score_model.py to retrain with real birdie features")


if __name__ == "__main__":
    main()
