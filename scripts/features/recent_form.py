#!/usr/bin/env python3
"""
Recent Form Feature Engineering
===============================

Computes recent form indicators from PGA Tour stats to supplement SG data.

FORM FEATURES:
--------------
1. Momentum indicators:
   - form_trend: SG total trend over last 5 events (positive = improving)
   - consistency: Std dev of finishes (lower = more consistent)
   - hot_streak: Count of top-10s in last 5 events

2. Scoring efficiency:
   - birdie_rate: Birdies per round (recent)
   - bogey_rate: Bogeys per round (recent)
   - scoring_vs_field: How much better/worse than field average

3. Clutch indicators:
   - bounce_back_rate: Recovery after bogey
   - final_round_scoring: Performance under Sunday pressure
   - scrambling_rate: Short game saves

4. Cut history:
   - cuts_made_pct: % of cuts made in last N events
   - consecutive_cuts: Streak of consecutive cuts

Usage:
    from scripts.features.recent_form import (
        calculate_form_features,
        get_player_form_stats
    )

    # For training data
    form_df = calculate_form_features(player_id, stats_df, leaderboard_df)

    # For predictions
    form_stats = get_player_form_stats(player_id, stats_2025, leaderboards_2025)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional, List


# ============================================================================
# Configuration
# ============================================================================

# How many recent events to consider
LOOKBACK_EVENTS = 5

# Stat IDs for form calculations
STAT_IDS = {
    # SG stats (already have these)
    'sg_total': 2567,
    'sg_ott': 2568,
    'sg_app': 2569,
    'sg_arg': 2570,
    'sg_putt': 2564,

    # Form stats (from fetch_form_stats.py)
    'scoring_avg': 120,
    'birdie_avg': 156,
    'bogey_avg': 352,
    'gir_pct': 103,
    'driving_dist': 101,
    'driving_acc': 102,
    'scrambling': 130,
    'sand_save': 111,
    'putts_per_round': 104,
    'three_putt_avoid': 413,
    'one_putt_pct': 119,
    'bounce_back': 160,
    'par_breakers': 2414,
    'final_round': 2419,
}

# Recency weighting (latest events matter more)
def _recency_weights(n: int, decay: float = 0.8) -> np.ndarray:
    """
    Generate recency weights for the last n events.
    Newest event gets weight 1.0, then decays by `decay`.
    """
    if n <= 0:
        return np.array([], dtype=float)
    weights = np.array([decay ** i for i in range(n)][::-1], dtype=float)
    return weights


# ============================================================================
# Core Form Calculations
# ============================================================================

def calculate_sg_trend(player_stats: pd.DataFrame, n_events: int = 5) -> float:
    """
    Calculate SG:Total trend over recent events.

    Positive trend = player is improving
    Negative trend = player is declining

    Uses linear regression slope over last N events.
    """
    # Filter to SG:Total
    sg_data = player_stats[player_stats['stat_id'] == STAT_IDS['sg_total']].copy()

    if len(sg_data) < 2:
        return 0.0

    # Sort by date/tournament order (assume tournament_id has chronological info)
    sg_data = sg_data.sort_values('tournament_id').tail(n_events)

    if len(sg_data) < 2:
        return 0.0

    # Parse values
    values = sg_data['stat_value'].apply(_parse_numeric).dropna().values

    if len(values) < 2:
        return 0.0

    # Calculate trend (simple linear regression slope)
    x = np.arange(len(values))
    slope = np.polyfit(x, values, 1)[0]

    return float(slope)


def calculate_finish_consistency(leaderboard_data: pd.DataFrame, n_events: int = 10) -> float:
    """
    Calculate consistency of finishes.

    Lower std dev = more consistent player.
    Returns normalized value where 0 = very consistent, 1 = very inconsistent.
    """
    if len(leaderboard_data) == 0:
        return 0.5  # Default middle value

    recent = leaderboard_data.sort_values('tournament_id').tail(n_events)

    # Handle both position_num and position columns
    if 'position_num' in recent.columns:
        positions = recent['position_num'].fillna(70).values
    elif 'position' in recent.columns:
        # Parse position string (e.g., "T5" -> 5, "CUT" -> 70)
        positions = recent['position'].apply(_parse_position).values
    else:
        return 0.5

    if len(positions) < 2:
        return 0.5

    std = np.std(positions)

    # Normalize: typical std ranges from 5 (consistent) to 30 (inconsistent)
    normalized = np.clip(std / 30, 0, 1)

    return float(normalized)


def calculate_hot_streak(leaderboard_data: pd.DataFrame, n_events: int = 5) -> Dict[str, float]:
    """
    Calculate hot streak indicators.

    Returns:
        - top10_count: Number of top-10s in last N events
        - top5_count: Number of top-5s in last N events
        - win_count: Number of wins in last N events
        - cuts_made: Number of cuts made in last N events
    """
    if len(leaderboard_data) == 0:
        return {
            'recent_top10s': 0,
            'recent_top5s': 0,
            'recent_wins': 0,
            'recent_cuts_made': 0,
            'recent_cuts_pct': 0.0
        }

    recent = leaderboard_data.sort_values('tournament_id').tail(n_events)

    # Handle both position_num and position columns
    if 'position_num' in recent.columns:
        positions = recent['position_num'].fillna(999)
    elif 'position' in recent.columns:
        positions = recent['position'].apply(_parse_position)
    else:
        positions = pd.Series([999] * len(recent))

    weights = _recency_weights(len(positions))
    recent_top10s_weighted = float(np.sum((positions <= 10).astype(float) * weights)) if len(weights) else 0.0

    return {
        'recent_top10s': recent_top10s_weighted,
        'recent_top5s': int((positions <= 5).sum()),
        'recent_wins': int((positions == 1).sum()),
        'recent_cuts_made': int((positions < 70).sum()),  # Missed cut coded as 70
        'recent_cuts_pct': float((positions < 70).sum() / len(positions)) if len(positions) > 0 else 0.0
    }


def calculate_momentum_features(leaderboard_data: pd.DataFrame, n_events: int = 5) -> Dict[str, any]:
    """
    Calculate momentum/hot hand features to detect players on hot streaks.

    A player is flagged as "hot" if they meet ANY of these criteria:
    - 3+ consecutive top-10 finishes
    - 2+ top-5 finishes in last 5 events
    - 1+ win in last 5 events
    - Weighted top-10 score >= 2.5 (recent bias)

    Returns:
        - consecutive_top10s: Current streak of consecutive top-10s
        - consecutive_cuts: Current streak of consecutive cuts made
        - hot_hand_flag: Boolean - player is on a hot streak
        - hot_hand_score: Numeric momentum score (0-10)
        - momentum_trend: 'HOT', 'WARM', 'NEUTRAL', 'COLD'
    """
    if len(leaderboard_data) == 0:
        return {
            'consecutive_top10s': 0,
            'consecutive_cuts': 0,
            'hot_hand_flag': False,
            'hot_hand_score': 0.0,
            'momentum_trend': 'NEUTRAL'
        }

    recent = leaderboard_data.sort_values('tournament_id').tail(n_events)

    # Get positions
    if 'position_num' in recent.columns:
        positions = recent['position_num'].fillna(999).values
    elif 'position' in recent.columns:
        positions = recent['position'].apply(_parse_position).values
    else:
        positions = np.array([999] * len(recent))

    # Calculate consecutive streaks (from most recent backwards)
    consecutive_top10s = 0
    consecutive_cuts = 0
    for pos in reversed(positions):
        if pos <= 10:
            consecutive_top10s += 1
        else:
            break

    for pos in reversed(positions):
        if pos < 70:  # Made cut
            consecutive_cuts += 1
        else:
            break

    # Calculate hot hand score (0-10)
    top10_count = int((positions <= 10).sum())
    top5_count = int((positions <= 5).sum())
    win_count = int((positions == 1).sum())

    # Weighted score: wins=3pts, top5=2pts, top10=1pt, streak bonus
    hot_hand_score = (
        win_count * 3.0 +
        top5_count * 2.0 +
        top10_count * 1.0 +
        consecutive_top10s * 0.5  # Streak bonus
    )
    hot_hand_score = min(10.0, hot_hand_score)  # Cap at 10

    # Hot hand flag - player is "on fire"
    hot_hand_flag = any([
        consecutive_top10s >= 3,
        top5_count >= 2,
        win_count >= 1,
        hot_hand_score >= 4.0
    ])

    # Momentum trend categorization
    if hot_hand_score >= 5.0:
        momentum_trend = 'HOT'
    elif hot_hand_score >= 3.0:
        momentum_trend = 'WARM'
    elif hot_hand_score >= 1.0:
        momentum_trend = 'NEUTRAL'
    else:
        momentum_trend = 'COLD'

    return {
        'consecutive_top10s': consecutive_top10s,
        'consecutive_cuts': consecutive_cuts,
        'hot_hand_flag': hot_hand_flag,
        'hot_hand_score': hot_hand_score,
        'momentum_trend': momentum_trend
    }


def calculate_scoring_efficiency(player_stats: pd.DataFrame, n_events: int = 5) -> Dict[str, float]:
    """
    Calculate scoring efficiency metrics from form stats.
    """
    result = {
        'recent_birdie_avg': np.nan,
        'recent_bogey_avg': np.nan,
        'recent_scoring_avg': np.nan,
        'recent_gir_pct': np.nan,
        'recent_scrambling': np.nan,
    }

    for stat_name, stat_id in [
        ('recent_birdie_avg', STAT_IDS.get('birdie_avg')),
        ('recent_bogey_avg', STAT_IDS.get('bogey_avg')),
        ('recent_scoring_avg', STAT_IDS.get('scoring_avg')),
        ('recent_gir_pct', STAT_IDS.get('gir_pct')),
        ('recent_scrambling', STAT_IDS.get('scrambling')),
    ]:
        if stat_id is None:
            continue

        stat_data = player_stats[player_stats['stat_id'] == stat_id]
        if len(stat_data) > 0:
            recent = stat_data.sort_values('tournament_id').tail(n_events)
            values = recent['stat_value'].apply(_parse_numeric).dropna()
            if len(values) > 0:
                weights = _recency_weights(len(values))
                result[stat_name] = float(np.average(values, weights=weights))

    return result


def calculate_clutch_indicators(player_stats: pd.DataFrame, n_events: int = 5) -> Dict[str, float]:
    """
    Calculate clutch performance indicators.
    """
    result = {
        'recent_bounce_back': np.nan,
        'recent_final_round': np.nan,
        'recent_sand_save': np.nan,
    }

    for stat_name, stat_id in [
        ('recent_bounce_back', STAT_IDS.get('bounce_back')),
        ('recent_final_round', STAT_IDS.get('final_round')),
        ('recent_sand_save', STAT_IDS.get('sand_save')),
    ]:
        if stat_id is None:
            continue

        stat_data = player_stats[player_stats['stat_id'] == stat_id]
        if len(stat_data) > 0:
            recent = stat_data.sort_values('tournament_id').tail(n_events)
            values = recent['stat_value'].apply(_parse_numeric).dropna()
            if len(values) > 0:
                weights = _recency_weights(len(values))
                result[stat_name] = float(np.average(values, weights=weights))

    return result


# ============================================================================
# Main Form Feature Functions
# ============================================================================

def get_player_form_stats(
    player_id: int,
    stats_df: pd.DataFrame,
    leaderboard_df: pd.DataFrame,
    n_events: int = LOOKBACK_EVENTS
) -> Dict[str, float]:
    """
    Calculate all form features for a single player.

    Args:
        player_id: PGA Tour player ID
        stats_df: Tournament stats data (from fetch_form_stats.py or tournament_stats)
        leaderboard_df: Leaderboard data with tournament results
        n_events: Number of recent events to consider

    Returns:
        Dict of form features
    """
    # Filter to player
    player_stats = stats_df[stats_df['player_id'] == player_id].copy()
    player_results = leaderboard_df[leaderboard_df['player_id'] == player_id].copy()

    # Calculate all form components
    form_features = {}

    # Momentum
    form_features['form_trend'] = calculate_sg_trend(player_stats, n_events)
    form_features['finish_consistency'] = calculate_finish_consistency(player_results, n_events * 2)

    # Hot streak (basic counts)
    hot_streak = calculate_hot_streak(player_results, n_events)
    form_features.update(hot_streak)

    # Hot hand / momentum detection (for usage optimizer bonus)
    momentum = calculate_momentum_features(player_results, n_events)
    form_features.update(momentum)

    # Scoring efficiency (if form stats available)
    scoring = calculate_scoring_efficiency(player_stats, n_events)
    form_features.update(scoring)

    # Clutch indicators
    clutch = calculate_clutch_indicators(player_stats, n_events)
    form_features.update(clutch)

    return form_features


def add_form_features_to_training_data(
    master_df: pd.DataFrame,
    stats_df: pd.DataFrame,
    leaderboard_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Add form features to training data.

    For each row (player-tournament), calculates form based on
    events BEFORE that tournament (to avoid leakage).

    Args:
        master_df: Training data with player_id, tournament_id
        stats_df: All tournament stats
        leaderboard_df: All leaderboard results

    Returns:
        master_df with form features added
    """
    print("  Calculating form features for training data...")

    # Get unique player-tournament combinations
    player_tournaments = master_df[['player_id', 'tournament_id', 'year']].drop_duplicates()

    form_records = []

    for idx, row in player_tournaments.iterrows():
        if idx % 1000 == 0:
            print(f"    Progress: {idx}/{len(player_tournaments)}")

        player_id = row['player_id']
        tournament_id = row['tournament_id']

        # Filter to data BEFORE this tournament (temporal ordering)
        prior_stats = stats_df[
            (stats_df['player_id'] == player_id) &
            (stats_df['tournament_id'] < tournament_id)
        ]
        prior_results = leaderboard_df[
            (leaderboard_df['player_id'] == player_id) &
            (leaderboard_df['tournament_id'] < tournament_id)
        ]

        # Calculate form
        form = get_player_form_stats(player_id, prior_stats, prior_results)
        form['player_id'] = player_id
        form['tournament_id'] = tournament_id

        form_records.append(form)

    form_df = pd.DataFrame(form_records)

    # Merge with master data
    result = master_df.merge(form_df, on=['player_id', 'tournament_id'], how='left')

    print(f"  ✓ Added {len(form_df.columns) - 2} form features")

    return result


def get_form_features_for_field(
    field_df: pd.DataFrame,
    stats_df: pd.DataFrame,
    leaderboard_df: pd.DataFrame,
    n_events: int = LOOKBACK_EVENTS
) -> pd.DataFrame:
    """
    Calculate form features for a tournament field (prediction mode).

    Args:
        field_df: DataFrame with player_id, player_name
        stats_df: Recent stats data (e.g., 2025)
        leaderboard_df: Recent results (e.g., 2025)
        n_events: Number of recent events

    Returns:
        field_df with form features added
    """
    print(f"  Calculating form features for {len(field_df)} players...")

    # Normalize player_id dtype to avoid join mismatches
    for df in (field_df, stats_df, leaderboard_df):
        if df is not None and 'player_id' in df.columns:
            df['player_id'] = pd.to_numeric(df['player_id'], errors='coerce').astype('Int64')

    form_records = []

    for idx, player in field_df.iterrows():
        player_id = player['player_id']
        if pd.isna(player_id):
            form = {k: 0.0 for k in ['form_trend', 'finish_consistency', 'recent_top10s', 'recent_top5s', 'recent_wins', 'recent_cuts_made', 'recent_cuts_pct']}
            form['player_id'] = player_id
            form_records.append(form)
            continue

        form = get_player_form_stats(
            player_id, stats_df, leaderboard_df, n_events
        )
        form['player_id'] = player_id
        form_records.append(form)

    form_df = pd.DataFrame(form_records)

    # Merge
    result = field_df.merge(form_df, on='player_id', how='left')

    # Fill missing values
    form_cols = [c for c in result.columns if c.startswith('recent_') or c in ['form_trend', 'finish_consistency']]
    for col in form_cols:
        if result[col].isna().any():
            median_val = result[col].median()
            if pd.isna(median_val):
                median_val = 0.0
            result[col] = result[col].fillna(median_val)

    print(f"  ✓ Added form features (coverage: {result['form_trend'].notna().mean()*100:.1f}%)")

    return result


# ============================================================================
# Helpers
# ============================================================================

def _parse_numeric(value) -> Optional[float]:
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


def _parse_position(pos) -> float:
    """Parse position string to numeric value."""
    if pos is None or pd.isna(pos):
        return 70.0

    pos_str = str(pos).strip().upper()

    # Handle ties (e.g., "T5" -> 5)
    if pos_str.startswith('T'):
        try:
            return float(pos_str[1:])
        except (ValueError, TypeError):
            return 70.0

    # Handle missed cuts and withdrawals
    if pos_str in ['CUT', 'MDF', 'W/D', 'WD', 'DQ', 'MC']:
        return 70.0

    # Try direct conversion
    try:
        return float(pos_str)
    except (ValueError, TypeError):
        return 70.0


def load_form_stats(year: int) -> pd.DataFrame:
    """Load form stats for a year (DB-first, CSV fallback)."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "database"))
        from db import get_conn
        with get_conn(read_only=True) as conn:
            return conn.execute(
                "SELECT * FROM form_stats WHERE year = ?", [year]
            ).df()
    except Exception:
        pass
    path = Path(f"data/historical/form_stats_{year}.csv")
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def load_leaderboards(year: int) -> pd.DataFrame:
    """Load leaderboard data for a year (DB-first, CSV fallback)."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "database"))
        from db import get_conn
        with get_conn(read_only=True) as conn:
            return conn.execute(
                "SELECT * FROM leaderboards WHERE year = ?", [year]
            ).df()
    except Exception:
        pass
    path = Path(f"data/historical/leaderboards_{year}.csv")
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


# ============================================================================
# CLI for testing
# ============================================================================

def main():
    """Test form feature calculation."""
    import argparse

    parser = argparse.ArgumentParser(description="Calculate form features")
    parser.add_argument("--player-id", type=int, help="Test for specific player")
    parser.add_argument("--year", type=int, default=2025, help="Year for data")

    args = parser.parse_args()

    # Load data
    stats = load_form_stats(args.year)
    if stats.empty:
        # Fall back to tournament stats
        stats_path = Path(f"data/historical/tournament_stats_{args.year}.csv")
        if stats_path.exists():
            stats = pd.read_csv(stats_path)

    leaderboards = load_leaderboards(args.year)
    if leaderboards.empty:
        lb_path = Path(f"data/historical/leaderboards_{args.year}.csv")
        if lb_path.exists():
            leaderboards = pd.read_csv(lb_path)

    if stats.empty or leaderboards.empty:
        print("Could not load data. Run scrapers first.")
        return

    if args.player_id:
        form = get_player_form_stats(args.player_id, stats, leaderboards)
        print(f"\nForm features for player {args.player_id}:")
        for k, v in form.items():
            print(f"  {k}: {v}")
    else:
        # Test with sample
        sample_players = leaderboards['player_id'].drop_duplicates().head(5)
        for pid in sample_players:
            name = leaderboards[leaderboards['player_id'] == pid]['player_name'].iloc[0]
            form = get_player_form_stats(pid, stats, leaderboards)
            print(f"\n{name} ({pid}):")
            print(f"  trend={form['form_trend']:.3f}, consistency={form['finish_consistency']:.2f}")
            print(f"  top10s={form['recent_top10s']}, cuts={form['recent_cuts_pct']:.1%}")


if __name__ == "__main__":
    main()
