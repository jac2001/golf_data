#!/usr/bin/env python3
"""
Master Historical Data Merger
==============================
Combines all scraped historical data (2020-2024) into a unified dataset:
- Leaderboards (finish positions)
- Tournament stats (SG metrics)
- Course history features

Output: Complete training dataset with all features for final model training

Usage:
    python scripts/features/merge_all_historical_data.py

Expected improvements over current model:
- More training data (5 years vs 1 year)
- Course history features (player-venue performance)
- Tournament-level SG stats
- Proper year-based validation possible

Target performance: 0.72-0.78 ROC-AUC (realistic for golf prediction)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
import re
from course_fit_dg import normalize_tournament_name

warnings.filterwarnings('ignore')

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  📊 MASTER HISTORICAL DATA MERGER")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print()

# Define paths
DATA_DIR = Path("/Users/jacklegnon/Desktop/golf_data/data")
HISTORICAL_DIR = DATA_DIR / "historical"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(exist_ok=True)
# Years with available data (adjust based on what you've scraped)
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

# Configuration options
DROP_MISSED_CUTS = True  # Drop missed cuts from training (better SG coverage, cleaner signal)
     # Add season-level SG averages as additional features
ADD_FORM_FEATURES = True # Add recent form indicators (trend, consistency, hot streak)

# ============================================================================
# STEP 1: Load and combine all leaderboard data
# ============================================================================
print("Step 1: Loading leaderboard data...")
print("-" * 60)

all_leaderboards = []
for year in YEARS:
    lb_file = HISTORICAL_DIR / f"leaderboards_{year}.csv"
    if lb_file.exists():
        df = pd.read_csv(lb_file)
        df['year'] = year
        all_leaderboards.append(df)
        print(f"  ✓ {year}: {len(df):,} records")
    else:
        print(f"  ⚠️  {year}: File not found - {lb_file}")

if not all_leaderboards:
    print("\n❌ No leaderboard files found! Cannot proceed.")
    exit(1)

leaderboards = pd.concat(all_leaderboards, ignore_index=True)
print(f"\n📊 Combined leaderboards: {len(leaderboards):,} total records")
print(f"   Years: {sorted(leaderboards['year'].unique())}")
print(f"   Tournaments: {leaderboards['tournament_id'].nunique()}")
print(f"   Players: {leaderboards['player_name'].nunique()}")

# ============================================================================
# STEP 2: Load and combine all tournament stats
# ============================================================================
print("\n" + "="*60)
print("Step 2: Loading tournament stats (SG metrics)...")
print("-" * 60)

all_stats = []
for year in YEARS:
    stats_file = HISTORICAL_DIR / f"tournament_stats_{year}.csv"
    if stats_file.exists():
        df = pd.read_csv(stats_file)
        all_stats.append(df)
        print(f"  ✓ {year}: {len(df):,} stat records")
    else:
        print(f"  ⚠️  {year}: File not found - {stats_file}")

if not all_stats:
    print("\n⚠️  No tournament stats files found!")
    print("   Will proceed with leaderboard data only (limited features)")
    tournament_stats = None
else:
    tournament_stats = pd.concat(all_stats, ignore_index=True)
    print(f"\n📊 Combined stats: {len(tournament_stats):,} total records")

    # Filter to just "Avg" component for SG stats
    print("\n   Filtering to 'Avg' stat components...")
    stats_avg = tournament_stats[tournament_stats['stat_component'] == 'Avg'].copy()
    print(f"   Filtered to {len(stats_avg):,} records")

    # Pivot stats to wide format
    print("\n   Pivoting stats to wide format...")
    stats_pivot = stats_avg.pivot_table(
        index=['tournament_id', 'player_id', 'player_name'],
        columns='stat_id',
        values='stat_value',
        aggfunc='first'
    ).reset_index()

    # Rename stat columns to readable names (stat_id is int, not string)
    stat_mapping = {
        2567: 'sg_total',
        2568: 'sg_ott',
        2569: 'sg_app',
        2570: 'sg_arg',
        2564: 'sg_putt',
        2674: 'sg_t2g'
    }
    stats_pivot.columns = [stat_mapping.get(col, str(col)) for col in stats_pivot.columns]

    # Calculate sg_arg (Around the Green) from sg_t2g - sg_app
    # Note: stat_id 2570 (sg_arg) is not in API data, must be derived
    if 'sg_t2g' in stats_pivot.columns and 'sg_app' in stats_pivot.columns:
        stats_pivot['sg_arg'] = stats_pivot['sg_t2g'] - stats_pivot['sg_app']
        print(f"   ✓ Calculated sg_arg = sg_t2g - sg_app")
    else:
        print(f"   ⚠️ Cannot calculate sg_arg: missing sg_t2g or sg_app")

    print(f"   Stats columns: {[c for c in stats_pivot.columns if c.startswith('sg_')]}")

# ============================================================================
# STEP 2.5: Load and Merge world rankings
# ============================================================================
print("\n" + "="*60)
print("Step 2.5: Loading and merging world rankings....")
print("-" * 60)

rankings_dir = Path(__file__).resolve().parent.parent / "data" / "rankings"
all_rankings = []


for year in YEARS:
    rankings_file = rankings_dir / f"owgr_{year}.csv"
    if rankings_file.exists():
        rdf = pd.read_csv(rankings_file)
        rdf['year'] = year 
        all_rankings.append(rdf)
        print(f"  ✓ {year}: {len(rdf):,} records")
    else:
        print(f"  ⚠️  {year}: File not found - {rankings_file}")
    
if all_rankings:
    rankings_df = pd.concat(all_rankings, ignore_index=True)
    print(f"\n📊 Combined rankings: {len(rankings_df):,} records")
    
    # Keep only needed columns
    rankings_df = rankings_df[['player_id', 'world_rank', 'year']].copy()
    # Merge rankings into leaderboards (before merge with stats)
    # This adds world rank at the time of the tournament
    leaderboards = leaderboards.merge(
        rankings_df,
        on=['player_id', 'year'],
        how='left'
    )
    coverage = leaderboards['world_rank'].notna().mean() * 100
    print(f"  ✓ Merged world rankings into leaderboards (coverage: {coverage:.1f}%)")
else:
    print("  ℹ️  No rankings data available, skipping rankings merge.")
    leaderboards['world_rank'] = np.nan


# ============================================================================
# STEP 3: Merge leaderboards with tournament stats
# ============================================================================
print("\n" + "="*60)
print("Step 3: Merging leaderboards with tournament stats...")
print("-" * 60)

if tournament_stats is not None:
    # Merge on tournament_id and player_id
    print("  Merging leaderboards with stats...")
    print(f"    Leaderboards: {len(leaderboards):,} records")
    print(leaderboards.columns)
    print(f"    Stats pivot: {len(stats_pivot):,} records")
    print(stats_pivot.columns)
    merged = leaderboards.merge(
        stats_pivot,
        on=['tournament_id', 'player_id'],
        how='left',
        suffixes=('', '_stats')
    )
    if 'tournament_id' not in merged.columns:
        if 'tournament_id_x' in merged.columns:
            merged['tournament_id'] = merged['tournament_id_x']
        elif 'tournament_id_y' in merged.columns:
            merged['tournament_id'] = merged['tournament_id_y']
    print(f"  ✓ Merged leaderboards with stats: {len(merged):,} records")
    
        
        
    # Check merge quality
    stats_cols = [c for c in merged.columns if c.startswith('sg_')]
    if stats_cols:
        coverage = merged[stats_cols[0]].notna().mean() * 100
        print(f"  ✓ Merge complete: {len(merged):,} records")
        print(f"  ✓ Stats coverage: {coverage:.1f}%")

        # Show missing stats by year
        print("\n  Stats coverage by year:")
        for year in sorted(merged['year'].unique()):
            year_data = merged[merged['year'] == year]
            year_coverage = year_data[stats_cols[0]].notna().mean() * 100
            print(f"    {year}: {year_coverage:.1f}%")
    else:
        print("  ⚠️  No SG stats found after merge")
        merged = leaderboards.copy()
else:
    print("  ℹ️  Skipping stats merge (no stats data available)")
    merged = leaderboards.copy()

# ============================================================================
# STEP 3.5: Add season-level SG averages (player's overall form that year)
# ============================================================================
ADD_SEASON_SG = True
if ADD_SEASON_SG and tournament_stats is not None:
    print("\n" + "="*60)
    print("Step 3.5: Adding season-level SG averages...")
    print("-" * 60)
    
    stats_avg = tournament_stats[tournament_stats['stat_component'] == 'Avg'].copy()
    stats_avg = stats_avg.sort_values(['player_id', 'year', 'tournament_id'])

    stats_avg['season_sg_prior'] = (
        stats_avg.groupby(['player_id', 'year', 'stat_id'])['stat_value']
        .transform(lambda s: s.shift(1).expanding().mean())
        .fillna(0.0)
    )
    
  
    

    
    season_sg_pivot = stats_avg.pivot_table(
        index=['player_id', 'year', 'tournament_id'],
        columns='stat_id',
        values='season_sg_prior',
        aggfunc='first'
    ).reset_index()

    # Rename with season_ prefix
    season_stat_mapping = {
        2567: 'season_sg_total',
        2568: 'season_sg_ott',
        2569: 'season_sg_app',
        2570: 'season_sg_arg',
        2564: 'season_sg_putt',
        2674: 'season_sg_t2g'
    }
    season_sg_pivot.columns = [season_stat_mapping.get(col, col) for col in season_sg_pivot.columns]

    # Merge season SG into main data
    merged = merged.merge(
        season_sg_pivot,
        on=['player_id', 'year', 'tournament_id'],
        how='left'
    )

    season_cols = [c for c in merged.columns if c.startswith('season_sg_')]
    if season_cols:
        coverage = merged[season_cols[0]].notna().mean() * 100
        print(f"  ✓ Season SG features added: {season_cols}")
        print(f"  ✓ Coverage: {coverage:.1f}%")

# ============================================================================
# STEP 4: Add course history features
# ============================================================================
print("\n" + "="*60)
print("Step 4: Adding course history features...")
print("-" * 60)

# Generate fresh course history from the complete dataset
print("  Generating course history features from tournament history...")

# Sort by year+tournament to ensure proper temporal ordering
merged = merged.sort_values(['year', 'tournament_id'])

# Normalize tournament names (as proxy for venue) with aliases
def _normalize_venue_name(name: str) -> str:
    if pd.isna(name):
        return ""
    cleaned = (
        str(name).upper()
        .replace("&", "AND")
        .replace("'", "")
    )
    cleaned = re.sub(r'[^\w\s]', '', cleaned).strip()

    alias_map = {
        "WM PHOENIX OPEN": "WASTE MANAGEMENT PHOENIX OPEN",
        "WASTE MANAGEMENT PHOENIX OPEN": "WASTE MANAGEMENT PHOENIX OPEN",
        "ATT PEBBLE BEACH PRO AM": "ATT PEBBLE BEACH PROAM",
        "AT T PEBBLE BEACH PRO AM": "ATT PEBBLE BEACH PROAM",
        "THE AMERICAN EXPRESS": "THE AMERICAN EXPRESS",
        "AMERICAN EXPRESS": "THE AMERICAN EXPRESS",
        "THE RSM CLASSIC": "THE RSM CLASSIC",
        "RSM CLASSIC": "THE RSM CLASSIC",
    }
    return alias_map.get(cleaned, cleaned)

merged['venue_clean'] = merged['tournament_name'].apply(_normalize_venue_name)

# Create course history features
print("  Calculating player-venue history (this may take a minute)...")
course_history_features = []

for idx, row in merged.iterrows():
    if idx % 1000 == 0:
        print(f"    Progress: {idx:,}/{len(merged):,} ({idx/len(merged)*100:.1f}%)")

    player = row['player_id']
    venue = row['venue_clean']
    current_year = row['year']

    # Get all previous performances at this venue for this player
    history = merged[
        (merged['player_id'] == player) &
        (merged['venue_clean'] == venue) &
        (merged['year'] < current_year)
    ].copy()

    if len(history) > 0:
        # Convert position to numeric for stats
        # Handle ties like "T5" -> 5, and missed cuts like "CUT" -> NaN
        def parse_position(pos):
            if pd.isna(pos):
                return np.nan
            pos_str = str(pos).upper().strip()
            if pos_str in ['CUT', 'MC', 'W/D', 'WD', 'DQ', 'MDF']:
                return 999  # Mark as missed cut
            if pos_str.startswith('T'):
                try:
                    return float(pos_str[1:])
                except:
                    return np.nan
            try:
                return float(pos_str)
            except:
                return np.nan

        history['pos_num'] = history['position'].apply(parse_position)

        # Separate made cuts vs missed cuts
        made_cuts = history[history['pos_num'] < 100]  # Made cut finishes
        missed_cuts = history[history['pos_num'] >= 100]  # CUT/WD/DQ = 999

        # Count wins at venue
        wins_at_venue = (history['pos_num'] == 1).sum()

        # Calculate cut rate
        total_starts = len(history)
        cuts_made = len(made_cuts)
        cut_rate = cuts_made / total_starts if total_starts > 0 else 0

        # Calculate historical stats (avg finish ONLY for made cuts)
        hist_features = {
            'hist_times_played': len(history),
            'hist_avg_finish': made_cuts['pos_num'].mean() if len(made_cuts) > 0 else np.nan,
            'hist_best_finish': made_cuts['pos_num'].min() if len(made_cuts) > 0 else np.nan,
            'hist_wins': wins_at_venue,
            'hist_top5s': (history['pos_num'] <= 5).sum(),
            'hist_top10s': (history['pos_num'] <= 10).sum(),
            'hist_cut_rate': cut_rate,  # NEW: % of cuts made at venue
            'hist_missed_cuts': len(missed_cuts),  # NEW: count of MCs
            'has_won_here': 1 if wins_at_venue > 0 else 0,
        }
    else:
        # No history at this venue
        hist_features = {
            'hist_times_played': 0,
            'hist_avg_finish': np.nan,
            'hist_best_finish': np.nan,
            'hist_wins': 0,
            'hist_top5s': 0,
            'hist_top10s': 0,
            'hist_cut_rate': np.nan,  # NEW
            'hist_missed_cuts': 0,  # NEW
            'has_won_here': 0,
        }


    course_history_features.append(hist_features)

# Add course history to merged data
print("\n  Adding course history columns...")
hist_df = pd.DataFrame(course_history_features, index=merged.index)
merged = pd.concat([merged, hist_df], axis=1)

# Report coverage
coverage = (merged['hist_times_played'] > 0).mean() * 100
print(f"  ✓ Course history coverage: {coverage:.1f}%")
if coverage > 0:
    print(f"  ✓ Average times played (when >0): {merged[merged['hist_times_played']>0]['hist_times_played'].mean():.1f}")

# Fill NaN values in course history with sensible defaults
# For players with no course history or only missed cuts
print("\n  Filling course history NaN values...")

# Create binary indicator for whether player has meaningful course history
merged['has_course_history'] = (merged['hist_times_played'] > 0).astype(int)
merged['has_made_cut_here'] = ((merged['hist_times_played'] > 0) &
                                (merged['hist_times_played'] > merged['hist_missed_cuts'])).astype(int)

# hist_avg_finish: Use 40 as default (middle of typical field, worse than making cut)
# For players who played but missed all cuts, use 70 (typical MC position)
has_history_no_finish = (merged['hist_times_played'] > 0) & (merged['hist_avg_finish'].isna())
n_mc_only = has_history_no_finish.sum()
merged.loc[has_history_no_finish, 'hist_avg_finish'] = 70.0  # MC position
merged.loc[has_history_no_finish, 'hist_best_finish'] = 70.0

# For players with no history at all, use field average
no_history = merged['hist_times_played'] == 0
n_no_history = no_history.sum()
merged.loc[no_history, 'hist_avg_finish'] = 40.0  # Middle of field
merged.loc[no_history, 'hist_best_finish'] = 40.0

# hist_cut_rate: Use 0.5 for no history (neutral assumption)
merged.loc[no_history, 'hist_cut_rate'] = 0.5

print(f"  ✓ Created has_course_history and has_made_cut_here binary features")
print(f"  ✓ Filled {n_mc_only} players with MC-only history (hist_avg_finish=70)")
print(f"  ✓ Filled {n_no_history} players with no history (hist_avg_finish=40, cut_rate=0.5)")

# ============================================================================
# STEP 5: Feature engineering
# ============================================================================
print("\n" + "="*60)
print("Step 5: Creating engineered features...")
print("-" * 60)

# Extract finish position as numeric (handle 'CUT', 'W/D', etc.)
def extract_position(pos_str):
    """Convert position string to numeric, handling special cases"""
    if pd.isna(pos_str):
        return np.nan

    pos_str = str(pos_str).upper().strip()

    # Handle ties (e.g., "T5" -> 5)
    if pos_str.startswith('T'):
        try:
            return int(pos_str[1:])
        except:
            return np.nan

    # Handle special cases
    if pos_str in ['CUT', 'MDF', 'W/D', 'DQ', 'WD']:
        return 999  # Large number to indicate missed cut/withdrawal

    # Try direct conversion
    try:
        return int(pos_str)
    except:
        return np.nan

merged['position_num'] = merged['position'].apply(extract_position)

# Create binary targets
merged['won'] = (merged['position_num'] == 1).astype(int)
merged['top5'] = (merged['position_num'] <= 5).astype(int)
merged['top10'] = (merged['position_num'] <= 10).astype(int)
merged['top20'] = (merged['position_num'] <= 20).astype(int)

print(f"  ✓ Binary targets created:")
print(f"    Wins: {merged['won'].sum():,} ({merged['won'].mean()*100:.2f}%)")
print(f"    Top-5: {merged['top5'].sum():,} ({merged['top5'].mean()*100:.2f}%)")
print(f"    Top-10: {merged['top10'].sum():,} ({merged['top10'].mean()*100:.2f}%)")
print(f"    Top-20: {merged['top20'].sum():,} ({merged['top20'].mean()*100:.2f}%)")

# Venue difficulty features
print("\n  Creating venue/field strength features...")

# Average finish at venue (lower = harder/more competitive)
print("\n Creating venue/field strength features (prior years only)....")
venue_stats = []
for yr in sorted(merged['year'].unique()):
    prior = merged[merged['year'] < yr]
    if prior.empty:
        continue
    vs = prior.groupby("venue_clean")['position_num'].agg(['mean', 'std']).reset_index()
    vs['year'] = yr
    venue_stats.append(vs)
    
if venue_stats:
    venue_stats = pd.concat(venue_stats, ignore_index=True)
    venue_stats.columns = ['venue_clean', 'venue_avg_finish', 'venue_finish_std', 'year']
    merged = merged.merge(venue_stats, on=['venue_clean', 'year'], how='left')
    merged['venue_avg_finish'] = merged['venue_avg_finish'].fillna(40.0)
    merged['venue_finish_std'] = merged['venue_finish_std'].fillna(10.0)
else:
    merged['venue_avg_finish'] = 40.0
    merged['venue_finish_std'] = 10.0





# Field strength (average world ranking of field)
if 'world_rank' in merged.columns:
    field_strength = merged.groupby('tournament_id')['world_rank'].agg(['mean', 'median']).reset_index()
    field_strength.columns = ['tournament_id', 'field_avg_rank', 'field_median_rank']
    merged = merged.merge(field_strength, on='tournament_id', how='left')
    print(f"    ✓ Field strength features added")

print(f"  ✓ Feature engineering complete")

# ============================================================================
# STEP 5.25: Add form features (recent performance indicators)
# ============================================================================
ADD_FORM_FEATURES = True
if ADD_FORM_FEATURES:
    print("\n" + "="*60)
    print("Step 5.25: Adding form features...")
    print("-" * 60)

    try:
        # Load all form_stats files for detailed per-tournament stats
        print("  Loading form_stats files...")
        all_form_stats = []
        for year in YEARS:
            form_file = HISTORICAL_DIR / f"form_stats_{year}.csv"
            if form_file.exists():
                fs = pd.read_csv(form_file)
                all_form_stats.append(fs)
                print(f"    Loaded form_stats_{year}.csv: {len(fs):,} records")

        if all_form_stats:
            form_stats_df = pd.concat(all_form_stats, ignore_index=True)
            print(f"  ✓ Total form_stats records: {len(form_stats_df):,}")
        else:
            form_stats_df = pd.DataFrame()
            print("  ⚠️ No form_stats files found")

        # Stat IDs for form calculations (matching recent_form.py)
        STAT_IDS = {
            'sg_total': 2567,
            'scoring_avg': 120,
            'birdie_avg': 156,
            'bogey_avg': 352,
            'gir_pct': 103,
            'scrambling': 130,
            'bounce_back': 160,
            'final_round': 299,
            'sand_save': 111,
        }

        def parse_numeric(value):
            """Parse stat value to float."""
            if value is None or pd.isna(value):
                return None
            if isinstance(value, (int, float)):
                return float(value)
            cleaned = str(value).replace('%', '').replace("'", '').replace('"', '')
            cleaned = cleaned.replace(',', '').strip()
            try:
                return float(cleaned)
            except (ValueError, TypeError):
                return None

        def get_recent_stat_avg(player_stats, stat_id, n_events=5):
            """Get average of recent stat values for a player."""
            stat_data = player_stats[player_stats['stat_id'] == stat_id]
            if len(stat_data) == 0:
                return np.nan
            recent = stat_data.sort_values('tournament_id').tail(n_events)
            values = recent['stat_value'].apply(parse_numeric).dropna()
            if len(values) > 0:
                return float(values.mean())
            return np.nan

        # For each player-tournament, calculate form based on PRIOR events
        print("  Calculating form features for each player-tournament...")
        print("  (This may take a few minutes for large datasets)")

        form_features_list = []

        # Sort by tournament_id to ensure temporal ordering
        merged_sorted = merged.sort_values(['player_id', 'tournament_id'])

        # Get unique player-tournament pairs
        unique_pairs = merged_sorted[['player_id', 'tournament_id']].drop_duplicates()

        for idx, (player_id, tournament_id) in enumerate(unique_pairs.itertuples(index=False)):
            if idx % 5000 == 0 and idx > 0:
                print(f"    Progress: {idx:,}/{len(unique_pairs):,}")

            # Get prior tournaments for this player from merged data
            prior_data = merged_sorted[
                (merged_sorted['player_id'] == player_id) &
                (merged_sorted['tournament_id'] < tournament_id)
            ]

            # Get prior form_stats for this player
            prior_form_stats = pd.DataFrame()
            if len(form_stats_df) > 0:
                prior_form_stats = form_stats_df[
                    (form_stats_df['player_id'] == player_id) &
                    (form_stats_df['tournament_id'] < tournament_id)
                ]

            # Calculate basic form metrics from prior performance
            if len(prior_data) >= 2:
                recent_5 = prior_data.tail(5)

                form_trend = 0.0
                if 'sg_total' in recent_5.columns and len(recent_5) >= 2:
                    sg_values = recent_5['sg_total'].dropna().values
                    if len(sg_values) >= 2:
                        x = np.arange(len(sg_values))
                        form_trend = float(np.polyfit(x, sg_values, 1)[0])

                finish_consistency = recent_5['position_num'].std() if len(recent_5) > 1 else 20.0
                recent_top10s = int((recent_5['position_num'] <= 10).sum())
                recent_top5s = int((recent_5['position_num'] <= 5).sum())
                recent_cuts_pct = float((recent_5['position_num'] < 100).mean())
            else:
                form_trend = 0.0
                finish_consistency = 20.0
                recent_top10s = 0
                recent_top5s = 0
                recent_cuts_pct = 0.5

            # Calculate scoring efficiency from form_stats
            recent_birdie_avg = np.nan
            recent_bogey_avg = np.nan
            recent_scoring_avg = np.nan
            recent_gir_pct = np.nan
            recent_scrambling = np.nan
            recent_bounce_back = np.nan
            recent_final_round = np.nan
            recent_sand_save = np.nan

            if len(prior_form_stats) > 0:
                recent_birdie_avg = get_recent_stat_avg(prior_form_stats, STAT_IDS['birdie_avg'])
                recent_bogey_avg = get_recent_stat_avg(prior_form_stats, STAT_IDS['bogey_avg'])
                recent_scoring_avg = get_recent_stat_avg(prior_form_stats, STAT_IDS['scoring_avg'])
                recent_gir_pct = get_recent_stat_avg(prior_form_stats, STAT_IDS['gir_pct'])
                recent_scrambling = get_recent_stat_avg(prior_form_stats, STAT_IDS['scrambling'])
                recent_bounce_back = get_recent_stat_avg(prior_form_stats, STAT_IDS['bounce_back'])
                recent_final_round = get_recent_stat_avg(prior_form_stats, STAT_IDS['final_round'])
                recent_sand_save = get_recent_stat_avg(prior_form_stats, STAT_IDS['sand_save'])

            form_features_list.append({
                'player_id': player_id,
                'tournament_id': tournament_id,
                'form_trend': form_trend,
                'finish_consistency': min(finish_consistency / 30.0, 1.0),  # Normalize
                'recent_top10s': recent_top10s,
                'recent_top5s': recent_top5s,
                'recent_cuts_pct': recent_cuts_pct,
                # Scoring efficiency (from form_stats)
                'recent_birdie_avg': recent_birdie_avg,
                'recent_bogey_avg': recent_bogey_avg,
                'recent_scoring_avg': recent_scoring_avg,
                'recent_gir_pct': recent_gir_pct,
                'recent_scrambling': recent_scrambling,
                # Clutch indicators (from form_stats)
                'recent_bounce_back': recent_bounce_back,
                'recent_final_round': recent_final_round,
                'recent_sand_save': recent_sand_save,
            })

        form_df = pd.DataFrame(form_features_list)
        merged = merged.merge(form_df, on=['player_id', 'tournament_id'], how='left')

        # Define all form columns and their defaults
        form_cols_defaults = {
            'form_trend': 0.0,
            'finish_consistency': 0.5,
            'recent_top10s': 0.0,
            'recent_top5s': 0.0,
            'recent_cuts_pct': 0.5,
            'recent_birdie_avg': np.nan,  # Will fill with median
            'recent_bogey_avg': np.nan,
            'recent_scoring_avg': np.nan,
            'recent_gir_pct': np.nan,
            'recent_scrambling': np.nan,
            'recent_bounce_back': np.nan,
            'recent_final_round': np.nan,
            'recent_sand_save': np.nan,
        }

        # Fill NaN with median for stats columns, defaults for others
        for col, default in form_cols_defaults.items():
            if col in merged.columns:
                if col.startswith('recent_') and col not in ['recent_top10s', 'recent_top5s', 'recent_cuts_pct']:
                    # Use median for scoring/clutch stats
                    median_val = merged[col].median()
                    if pd.isna(median_val):
                        median_val = default if not pd.isna(default) else 0.0
                    merged[col] = merged[col].fillna(median_val)
                else:
                    merged[col] = merged[col].fillna(default)

        form_cols = list(form_cols_defaults.keys())
        print(f"  ✓ Form features added: {form_cols}")
        print(f"  ✓ Basic form coverage: {merged['form_trend'].notna().mean()*100:.1f}%")
        print(f"  ✓ Scoring stats coverage: {merged['recent_birdie_avg'].notna().mean()*100:.1f}%")

    except Exception as e:
        print(f"  ⚠️ Could not add form features: {e}")
        import traceback
        traceback.print_exc()
        print("  Continuing without form features...")

# ============================================================================
# STEP 5.3: Add course fit features using Data Golf weights
# ============================================================================
# IMPORTANT: Uses SEASON SG stats (prior performance) × course importance
# This avoids data leakage from using same-tournament SG stats
ADD_COURSE_FIT = True

if ADD_COURSE_FIT:
    print("\n" + "="*60)
    print("Step 5.3: Adding course fit features (Data Golf weights)...")
    print("-" * 60)
    print("  Using season_sg_* (prior performance) × course importance weights")
    print("  NOT using per-tournament SG (that would be data leakage)")

    try:
        # Load Data Golf course weights
        dg_weights_file = DATA_DIR / "course_sg_weights.csv"

        if dg_weights_file.exists():
            course_weights_df = pd.read_csv(dg_weights_file)
            print(f"  ✓ Loaded Data Golf weights for {len(course_weights_df)} tournaments")

            # Create lookup dict keyed by normalized tournament name
            weight_lookup = {}
            for _, row in course_weights_df.iterrows():
                normalized = normalize_tournament_name(row['tournament_name'])

                weight_lookup[normalized] = {
                    'ott_sg': row['ott_sg'],
                    'app_sg': row['app_sg'],
                    'arg_sg': row['arg_sg'],
                    'putt_sg': row['putt_sg']
                }

            # Default weights for tournaments not in our mapping
            default_weights = {'ott_sg': 0.020, 'app_sg': 0.020, 'arg_sg': 0.025, 'putt_sg': 0.005}

            # Calculate season_sg_arg if not present (T2G - APP)
            if 'season_sg_arg' not in merged.columns:
                if 'season_sg_t2g' in merged.columns and 'season_sg_app' in merged.columns:
                    merged['season_sg_arg'] = merged['season_sg_t2g'].fillna(0) - merged['season_sg_app'].fillna(0)
                    print("  ✓ Calculated season_sg_arg = season_sg_t2g - season_sg_app")
                else:
                    merged['season_sg_arg'] = 0.0
                    print("  ⚠️ season_sg_arg set to 0 (missing season_sg_t2g or season_sg_app)")

            # Initialize course fit columns
            fit_cols = ['dg_fit_ott', 'dg_fit_app', 'dg_fit_arg', 'dg_fit_putt', 'dg_fit_total']
            weight_cols = ['course_ott_weight', 'course_app_weight', 'course_arg_weight', 'course_putt_weight']

            for col in fit_cols + weight_cols:
                merged[col] = np.nan

            # Track matching statistics
            matched_count = 0
            unmatched_tournaments = set()

            # Calculate fit for each row using SEASON SG stats
            print("  Calculating player × course fit scores...")
            for idx, row in merged.iterrows():
                if idx % 5000 == 0:
                    print(f"    Progress: {idx:,}/{len(merged):,}")

                tournament = row.get('tournament_name', '')
                normalized = normalize_tournament_name(tournament)

                # Get course weights
                if normalized in weight_lookup:
                    weights = weight_lookup[normalized]
                    matched_count += 1
                else:
                    weights = default_weights
                    unmatched_tournaments.add(tournament)

                # Store course weights
                merged.at[idx, 'course_ott_weight'] = weights['ott_sg']
                merged.at[idx, 'course_app_weight'] = weights['app_sg']
                merged.at[idx, 'course_arg_weight'] = weights['arg_sg']
                merged.at[idx, 'course_putt_weight'] = weights['putt_sg']

                # Get player SEASON SG stats (NOT per-tournament!)
                sg_ott = row.get('season_sg_ott', 0.0) if pd.notna(row.get('season_sg_ott')) else 0.0
                sg_app = row.get('season_sg_app', 0.0) if pd.notna(row.get('season_sg_app')) else 0.0
                sg_arg = row.get('season_sg_arg', 0.0) if pd.notna(row.get('season_sg_arg')) else 0.0
                sg_putt = row.get('season_sg_putt', 0.0) if pd.notna(row.get('season_sg_putt')) else 0.0

                # Calculate fit scores (scaled by 10 for interpretability)
                scale = 10.0
                fit_ott = sg_ott * weights['ott_sg'] * scale
                fit_app = sg_app * weights['app_sg'] * scale
                fit_arg = sg_arg * weights['arg_sg'] * scale
                fit_putt = sg_putt * weights['putt_sg'] * scale
                fit_total = fit_ott + fit_app + fit_arg + fit_putt

                merged.at[idx, 'dg_fit_ott'] = fit_ott
                merged.at[idx, 'dg_fit_app'] = fit_app
                merged.at[idx, 'dg_fit_arg'] = fit_arg
                merged.at[idx, 'dg_fit_putt'] = fit_putt
                merged.at[idx, 'dg_fit_total'] = fit_total

            # Report coverage
            total = len(merged)
            print(f"  ✓ Course fit calculated:")
            print(f"    - Matched tournaments: {matched_count:,} ({matched_count/total*100:.1f}%)")
            print(f"    - Unmatched (using defaults): {total - matched_count:,}")

            if unmatched_tournaments:
                print(f"    - Unmatched tournament examples: {list(unmatched_tournaments)}")

            # Report fit statistics
            fit_total = merged['dg_fit_total']
            print(f"  ✓ Course fit statistics:")
            print(f"    - Mean: {fit_total.mean():.4f}")
            print(f"    - Std:  {fit_total.std():.4f}")
            print(f"    - Range: {fit_total.min():.4f} to {fit_total.max():.4f}")

        else:
            print(f"  ⚠️ Data Golf weights file not found: {dg_weights_file}")
            print("  Skipping course fit features.")

    except Exception as e:
        print(f"  ⚠️ Could not add course fit features: {e}")
        import traceback
        traceback.print_exc()

# ============================================================================
# STEP 5.5: Optionally drop missed cuts for cleaner training data
# ============================================================================

# ============================================================================
# STEP 6: Save processed dataset
# ============================================================================
print("\n" + "="*60)
print("Step 6: Saving processed dataset...")
print("-" * 60)

output_file = PROCESSED_DIR / "master_training_data_2020_2025.csv"
merged.to_csv(output_file, index=False)

print(f"  ✓ Saved to: {output_file}")
print(f"  ✓ Records: {len(merged):,}")
print(f"  ✓ Features: {len(merged.columns)}")
print(f"  ✓ Size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")

# ============================================================================
# STEP 7: Data quality report
# ============================================================================
print("\n" + "="*60)
print("Step 7: Data Quality Report")
print("-" * 60)

print("\n📊 Dataset Summary:")
print(f"  Records: {len(merged):,}")
print(f"  Years: {merged['year'].min()} - {merged['year'].max()}")
print(f"  Tournaments: {merged['tournament_id'].nunique()}")
print(f"  Players: {merged['player_id'].nunique()}")
print(f"  Venues: {merged['venue_clean'].nunique()}")

print("\n📈 Feature Availability:")
feature_groups = {
    'SG Stats': [c for c in merged.columns if c.startswith('sg_')],
    'Course History': [c for c in merged.columns if c.startswith('hist_')],
    'Course Fit (player×course)': [c for c in merged.columns if c.startswith('fit_') or c == 'course_fit_total'],
    'Venue/Field': ['venue_avg_finish', 'venue_finish_std'] + [c for c in merged.columns if 'field_' in c],
    'Form Features': [c for c in merged.columns if c.startswith('recent_') or c in ['form_trend', 'finish_consistency']],
    'Targets': ['won', 'top5', 'top10', 'top20']
}

for group, cols in feature_groups.items():
    available_cols = [c for c in cols if c in merged.columns]
    if available_cols:
        # Calculate coverage
        coverage = merged[available_cols[0]].notna().mean() * 100
        print(f"  {group}: {len(available_cols)} features ({coverage:.1f}% coverage)")

print("\n🎯 Target Distribution:")
for target in ['won', 'top5', 'top10', 'top20']:
    if target in merged.columns:
        count = merged[target].sum()
        pct = merged[target].mean() * 100
        print(f"  {target}: {count:,} ({pct:.2f}%)")

print("\n⚠️  Missing Values (top 10):")
missing = merged.isnull().sum().sort_values(ascending=False).head(10)
for col, count in missing.items():
    if count > 0:
        pct = count / len(merged) * 100
        print(f"  {col}: {count:,} ({pct:.1f}%)")

# ============================================================================
# Final summary
# ============================================================================
print("\n" + "="*60)
print("  ✅ MERGE COMPLETE!")
print("="*60)
print()
print("Next steps:")
print("  1. Train models: python scripts/validation/train_final_models.py")
print("  2. Validate: python scripts/validation/proper_validation.py")
print("  3. Generate 2026 predictions")
print()
print(f"Output file: {output_file}")
print()
