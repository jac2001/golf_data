"""
Course History Feature Engineering
===================================

Creates player-specific course history features from multi-year data.

These features are THE most predictive for golf:
- avg_finish_at_course
- best_finish_at_course
- times_played_at_course
- avg_sg_total_at_course
- made_cut_rate_at_course

Usage:
    python course_history_features.py --data-dir historical_data --output enhanced_data.csv
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def clean_position(pos_str):
    """
    Convert position string to numeric.
    Handles: '1', 'T5', 'CUT', 'W/D', 'DQ'
    """
    if pd.isna(pos_str):
        return np.nan

    pos_str = str(pos_str).strip()

    if pos_str in ['CUT', 'W/D', 'DQ']:
        return np.nan  # Treat as missing for averaging

    # Remove 'T' prefix
    pos_str = pos_str.replace('T', '')

    try:
        return int(pos_str)
    except ValueError:
        return np.nan


def clean_earnings(earnings_str):
    """Convert earnings string like '$1,260,000.00' to float."""
    if pd.isna(earnings_str):
        return 0.0

    earnings_str = str(earnings_str).replace('$', '').replace(',', '')

    try:
        return float(earnings_str)
    except ValueError:
        return 0.0


def match_courses_across_years(leaderboards_df):
    """
    Match tournaments across years to identify same courses.

    Returns:
        DataFrame with added 'course_id' column
    """
    print("\n" + "="*70)
    print("MATCHING COURSES ACROSS YEARS")
    print("="*70 + "\n")

    # Strategy: Group by normalized tournament name
    # Tournaments at same venue usually have similar names across years

    # Normalize tournament names
    leaderboards_df['tournament_name_normalized'] = (
        leaderboards_df['tournament_name']
        .str.lower()
        .str.replace('championship', 'champ')
        .str.replace('invitational', 'invite')
        .str.replace('tournament', 'tourn')
        .str.replace('the ', '')
        .str.strip()
    )

    # Create course ID from normalized name
    # Courses with same name = same venue
    unique_courses = leaderboards_df['tournament_name_normalized'].unique()

    course_mapping = {name: idx for idx, name in enumerate(sorted(unique_courses))}
    leaderboards_df['course_id'] = leaderboards_df['tournament_name_normalized'].map(course_mapping)

    print(f"Identified {len(unique_courses)} unique courses")
    print("\nSample course mapping:")

    sample = leaderboards_df.groupby('course_id')['tournament_name'].agg(
        lambda x: list(x.unique())[:3]  # Show first 3 years
    ).head(10)

    for course_id, names in sample.items():
        print(f"  Course {course_id}: {names}")

    return leaderboards_df


def create_course_history_features(
    leaderboards_df,
    target_year,
    lookback_years=5
):
    """
    Create course history features for target year predictions.

    Args:
        leaderboards_df: Combined leaderboards from multiple years
        target_year: Year we're predicting (e.g., 2026)
        lookback_years: How many years of history to use

    Returns:
        DataFrame with course history features
    """
    print("\n" + "="*70)
    print(f"CREATING COURSE HISTORY FEATURES (Target: {target_year})")
    print("="*70 + "\n")

    # Clean position and earnings
    leaderboards_df['position_clean'] = leaderboards_df['position'].apply(clean_position)
    leaderboards_df['earnings_clean'] = leaderboards_df['earnings'].apply(clean_earnings)

    # Made cut indicator
    leaderboards_df['made_cut'] = ~leaderboards_df['position'].isin(['CUT', 'W/D', 'DQ'])

    # Match courses across years
    leaderboards_df = match_courses_across_years(leaderboards_df)

    # Filter to historical years only (before target year)
    historical_years = range(target_year - lookback_years, target_year)
    historical_data = leaderboards_df[leaderboards_df['year'].isin(historical_years)].copy()

    print(f"\nUsing historical data from years: {list(historical_years)}")
    print(f"Historical records: {len(historical_data):,}")

    # Calculate course history features
    print("\nCalculating course history features...")

    course_history = historical_data.groupby(['player_id', 'player_name', 'course_id']).agg({
        'position_clean': ['mean', 'min', 'count'],  # avg finish, best finish, times played
        'earnings_clean': 'sum',  # total earnings at course
        'made_cut': 'mean',  # cut rate at course
        'year': 'max'  # most recent year played
    }).reset_index()

    # Flatten column names
    course_history.columns = [
        'player_id', 'player_name', 'course_id',
        'avg_finish_at_course',
        'best_finish_at_course',
        'times_played_at_course',
        'total_earnings_at_course',
        'made_cut_rate_at_course',
        'last_year_played_at_course'
    ]

    # Calculate recency factor (more recent = better predictor)
    course_history['years_since_played'] = target_year - course_history['last_year_played_at_course']

    # Add course experience tier
    def experience_tier(times):
        if times >= 5:
            return 'Veteran'
        elif times >= 3:
            return 'Experienced'
        elif times == 2:
            return 'Familiar'
        else:
            return 'Rookie'

    course_history['course_experience'] = course_history['times_played_at_course'].apply(experience_tier)

    print(f"\n✅ Created course history for {len(course_history):,} player-course combinations")

    # Summary stats
    print("\nCourse Experience Distribution:")
    print(course_history['course_experience'].value_counts())

    print("\nTimes Played Distribution:")
    print(course_history['times_played_at_course'].value_counts().sort_index())

    return course_history


def merge_with_current_data(current_df, course_history_df, year):
    """
    Merge course history features with current year tournament data.

    Args:
        current_df: DataFrame with current year player-tournament data
        course_history_df: DataFrame with course history features
        year: Current year

    Returns:
        Enhanced DataFrame with course history features
    """
    print("\n" + "="*70)
    print(f"MERGING COURSE HISTORY WITH {year} DATA")
    print("="*70 + "\n")

    print(f"Current data: {len(current_df):,} records")

    # Add course_id to current data (using same normalization)
    current_df['tournament_name_normalized'] = (
        current_df['tournament_name']
        .str.lower()
        .str.replace('championship', 'champ')
        .str.replace('invitational', 'invite')
        .str.replace('tournament', 'tourn')
        .str.replace('the ', '')
        .str.strip()
    )

    # Get course mapping from historical data
    course_mapping = course_history_df.groupby('course_id')['player_id'].count().index

    # Create lookup
    course_names = current_df['tournament_name_normalized'].unique()

    # Merge course history
    enhanced_df = current_df.merge(
        course_history_df,
        on=['player_id', 'course_id'],
        how='left',
        suffixes=('', '_history')
    )

    # Fill missing values (player never played this course)
    history_features = [
        'avg_finish_at_course',
        'best_finish_at_course',
        'times_played_at_course',
        'total_earnings_at_course',
        'made_cut_rate_at_course',
        'years_since_played'
    ]

    for feat in history_features:
        if feat in enhanced_df.columns:
            enhanced_df[feat] = enhanced_df[feat].fillna(0)

    # Add flags
    enhanced_df['has_course_history'] = enhanced_df['times_played_at_course'] > 0
    enhanced_df['course_veteran'] = enhanced_df['times_played_at_course'] >= 5

    print(f"Enhanced data: {len(enhanced_df):,} records")
    print(f"\nPlayers with course history: {enhanced_df['has_course_history'].sum():,} ({enhanced_df['has_course_history'].mean()*100:.1f}%)")

    return enhanced_df


def main():
    parser = argparse.ArgumentParser(
        description="Create course history features from multi-year data"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="historical",
        help="Directory with historical leaderboard CSVs"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="course_history_features.csv",
        help="Output file path"
    )
    parser.add_argument(
        "--target-year",
        type=int,
        default=2026,
        help="Year we're creating features for"
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=5,
        help="Years of history to use"
    )

    args = parser.parse_args()

    print("\n" + "="*70)
    print("COURSE HISTORY FEATURE ENGINEERING")
    print("="*70)
    print(f"\nData directory: {args.data_dir}")
    print(f"Target year: {args.target_year}")
    print(f"Lookback: {args.lookback} years")
    print(f"Output: {args.output}")

    # Load all historical leaderboards
    data_dir = Path(args.data_dir)
    print('Data directory resolved to:', data_dir.resolve())
    leaderboard_files = sorted(data_dir.glob("leaderboards_*.csv"))

    if not leaderboard_files:
        print(f"\n❌ No leaderboard files found in {data_dir}")
        print("Expected files like: leaderboards_2020.csv, leaderboards_2021.csv, etc.")
        return

    print(f"\nFound {len(leaderboard_files)} leaderboard files:")
    for f in leaderboard_files:
        print(f"  - {f.name}")

    # Load and combine all years
    print("\nLoading data...")
    all_leaderboards = []

    for file_path in leaderboard_files:
        df = pd.read_csv(file_path)
        all_leaderboards.append(df)
        print(f"  {file_path.name}: {len(df):,} records")

    combined_leaderboards = pd.concat(all_leaderboards, ignore_index=True)
    print(f"\nTotal records: {len(combined_leaderboards):,}")

    # Create course history features
    course_history = create_course_history_features(
        combined_leaderboards,
        target_year=args.target_year,
        lookback_years=args.lookback
    )

    # Save
    course_history.to_csv(args.output, index=False)
    print(f"\n✅ Course history features saved to: {args.output}")

    # Display sample
    print("\n" + "="*70)
    print("SAMPLE COURSE HISTORY FEATURES")
    print("="*70 + "\n")

    sample = course_history.nlargest(10, 'times_played_at_course')
    print(sample[[
        'player_name', 'course_id', 'times_played_at_course',
        'avg_finish_at_course', 'best_finish_at_course', 'made_cut_rate_at_course'
    ]].to_string(index=False))

    print("\n" + "="*70)
    print("✅ COMPLETE!")
    print("="*70)
    print("\nNext steps:")
    print("1. Merge these features with your current dataset")
    print("2. Retrain models with course history included")
    print("3. Compare ROC-AUC scores (expect +0.05 to +0.10 improvement)")


if __name__ == "__main__":
    main()
