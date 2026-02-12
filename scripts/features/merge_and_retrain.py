"""
Merge Course History Features and Retrain Models
=================================================

This script:
1. Loads your current dataset (full_df.csv)
2. Merges course history features
3. Retrains models with enhanced features
4. Compares performance vs. baseline

Usage:
    python merge_and_retrain.py
"""

import pandas as pd
import numpy as np
import pickle
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, classification_report
import warnings
warnings.filterwarnings('ignore')


def load_and_merge_data():
    """Load current data and merge with course history."""
    print("="*70)
    print("LOADING DATA")
    print("="*70 + "\n")

    # Load current 2025 data
    print("Loading current dataset...")
    df = pd.read_csv('full_df.csv')
    print(f"  Current data: {len(df):,} records")

    # Load course history
    print("Loading course history features...")
    course_history = pd.read_csv('course_history_2026.csv')
    print(f"  Course history: {len(course_history):,} player-course combinations")

    # Add normalized tournament name to df for matching
    df['tournament_name_normalized'] = (
        df['tournament_name']
        .str.lower()
        .str.replace('championship', 'champ')
        .str.replace('invitational', 'invite')
        .str.replace('tournament', 'tourn')
        .str.replace('the ', '')
        .str.strip()
    )

    # Create course_id mapping from course_history
    # Map normalized names to course_ids
    course_mapping = course_history.groupby('course_id').agg({
        'player_name': 'first'  # Just to get the course_id list
    }).reset_index()

    # For merging, we need to match on tournament names
    # Since course_history doesn't have tournament names, we need to create a lookup
    # from the historical leaderboard data

    print("\nCreating course ID mapping...")

    # Load one year of historical leaderboards to get course mapping
    hist = pd.read_csv('historical_data/leaderboards_2024.csv')
    hist['tournament_name_normalized'] = (
        hist['tournament_name']
        .str.lower()
        .str.replace('championship', 'champ')
        .str.replace('invitational', 'invite')
        .str.replace('tournament', 'tourn')
        .str.replace('the ', '')
        .str.strip()
    )

    # Create course_id for historical data
    unique_courses = hist['tournament_name_normalized'].unique()
    course_id_mapping = {name: idx for idx, name in enumerate(sorted(unique_courses))}

    # Add course_id to current data
    df['course_id'] = df['tournament_name_normalized'].map(course_id_mapping)

    print(f"  Mapped {df['course_id'].notna().sum():,} records to courses")

    # Merge course history
    print("\nMerging course history features...")
    df_enhanced = df.merge(
        course_history[['player_id', 'course_id', 'avg_finish_at_course',
                       'best_finish_at_course', 'times_played_at_course',
                       'made_cut_rate_at_course', 'course_experience']],
        on=['player_id', 'course_id'],
        how='left'
    )

    # Fill missing values (player never played this course before)
    course_features = ['avg_finish_at_course', 'best_finish_at_course',
                      'times_played_at_course', 'made_cut_rate_at_course']

    for feat in course_features:
        if feat in df_enhanced.columns:
            # Use reasonable defaults for rookies at a course
            if feat == 'avg_finish_at_course':
                df_enhanced[feat] = df_enhanced[feat].fillna(50)  # Assume avg finish
            elif feat == 'best_finish_at_course':
                df_enhanced[feat] = df_enhanced[feat].fillna(80)  # Assume poor best
            elif feat == 'times_played_at_course':
                df_enhanced[feat] = df_enhanced[feat].fillna(0)  # Rookie
            elif feat == 'made_cut_rate_at_course':
                df_enhanced[feat] = df_enhanced[feat].fillna(0.5)  # Assume 50%

    df_enhanced['has_course_history'] = df_enhanced['times_played_at_course'] > 0

    print(f"\nEnhanced dataset: {len(df_enhanced):,} records")
    print(f"Records with course history: {df_enhanced['has_course_history'].sum():,} " +
          f"({df_enhanced['has_course_history'].mean()*100:.1f}%)")

    return df_enhanced


def prepare_features():
    """Define feature sets."""

    # Original features
    original_features = [
        'strokes_gained_total_avg_tz_roll3',
        'strokes_gained_tee_to_green_avg_tz_roll3',
        'strokes_gained_putting_avg_tz_roll3',
        'strokes_gained_off_the_tee_avg_tz_roll3',
        'strokes_gained_approach_the_green_avg_tz_roll3',
        'strokes_gained_around_the_green_avg_tz_roll3',
        'strokes_gained_total_avg_tz_vol3',
        'strokes_gained_putting_avg_tz_vol3',
        'strokes_gained_total_avg_tz_roll5',
        'field_strength',
        'birdie_to_bogey_ratio_value_tz_roll3',
        'cut_rate_r5'
    ]

    # New course history features
    course_features = [
        'avg_finish_at_course',
        'best_finish_at_course',
        'times_played_at_course',
        'made_cut_rate_at_course',
        'has_course_history'
    ]

    # Combined
    enhanced_features = original_features + course_features

    return original_features, course_features, enhanced_features


def train_and_compare(df):
    """Train models with and without course history, compare performance."""

    print("\n" + "="*70)
    print("TRAINING AND COMPARISON")
    print("="*70 + "\n")

    # Get feature sets
    original_features, course_features, enhanced_features = prepare_features()

    # Create target
    df['won'] = df['finish_position_num'] == 1
    df['top5'] = df['finish_position_num'] <= 5

    # Clean data - only keep records with all features
    df_clean = df.dropna(subset=enhanced_features + ['won']).copy()

    print(f"Clean dataset: {len(df_clean):,} records")
    print(f"Wins: {df_clean['won'].sum()} ({df_clean['won'].mean()*100:.2f}%)")
    print(f"Top-5: {df_clean['top5'].sum()} ({df_clean['top5'].mean()*100:.2f}%)\n")

    # Split data
    y = df_clean['won']

    # Baseline model (original features only)
    X_baseline = df_clean[original_features]
    X_train_base, X_test_base, y_train, y_test = train_test_split(
        X_baseline, y, test_size=0.2, random_state=42, stratify=y
    )

    # Enhanced model (with course history)
    X_enhanced = df_clean[enhanced_features]
    X_train_enh, X_test_enh, _, _ = train_test_split(
        X_enhanced, y, test_size=0.2, random_state=42, stratify=y
    )

    print("Training BASELINE model (no course history)...")
    rf_baseline = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_leaf=10,
        random_state=42
    )
    rf_baseline.fit(X_train_base, y_train)
    y_pred_base = rf_baseline.predict_proba(X_test_base)[:, 1]
    auc_baseline = roc_auc_score(y_test, y_pred_base)

    print("Training ENHANCED model (with course history)...")
    rf_enhanced = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_leaf=10,
        random_state=42
    )
    rf_enhanced.fit(X_train_enh, y_train)
    y_pred_enh = rf_enhanced.predict_proba(X_test_enh)[:, 1]
    auc_enhanced = roc_auc_score(y_test, y_pred_enh)

    # Compare
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70 + "\n")

    print(f"BASELINE MODEL ({len(original_features)} features):")
    print(f"  ROC-AUC: {auc_baseline:.4f}\n")

    print(f"ENHANCED MODEL ({len(enhanced_features)} features):")
    print(f"  ROC-AUC: {auc_enhanced:.4f}\n")

    improvement = auc_enhanced - auc_baseline
    pct_improvement = (improvement / auc_baseline) * 100

    print(f"{'🎉' if improvement > 0 else '⚠️'} Improvement: {improvement:+.4f} ({pct_improvement:+.2f}%)")

    # Feature importance comparison
    print("\n" + "="*70)
    print("FEATURE IMPORTANCE (Enhanced Model)")
    print("="*70 + "\n")

    feature_importance = pd.DataFrame({
        'feature': enhanced_features,
        'importance': rf_enhanced.feature_importances_
    }).sort_values('importance', ascending=False)

    print("Top 15 Features:")
    print(feature_importance.head(15).to_string(index=False))

    # Highlight course history features
    course_in_top10 = [
        f for f in feature_importance.head(10)['feature'].values
        if f in course_features
    ]

    if course_in_top10:
        print(f"\n✅ Course history features in top 10: {len(course_in_top10)}")
        for f in course_in_top10:
            imp = feature_importance[feature_importance['feature'] == f]['importance'].values[0]
            rank = feature_importance[feature_importance['feature'] == f].index[0] + 1
            print(f"  #{rank}. {f}: {imp:.4f}")

    # Save enhanced model
    print("\n" + "="*70)
    print("SAVING MODELS")
    print("="*70 + "\n")

    with open('rf_win_model_enhanced.pkl', 'wb') as f:
        pickle.dump(rf_enhanced, f)

    with open('enhanced_features_list.pkl', 'wb') as f:
        pickle.dump(enhanced_features, f)

    print("✅ Saved:")
    print("  - rf_win_model_enhanced.pkl")
    print("  - enhanced_features_list.pkl")

    return rf_baseline, rf_enhanced, feature_importance


def main():
    print("\n" + "#"*70)
    print("# MERGE COURSE HISTORY & RETRAIN MODELS")
    print("#"*70 + "\n")

    # Load and merge
    df_enhanced = load_and_merge_data()

    # Save enhanced dataset
    print("\nSaving enhanced dataset...")
    df_enhanced.to_csv('full_df_with_course_history.csv', index=False)
    print("✅ Saved to: full_df_with_course_history.csv")

    # Train and compare
    rf_baseline, rf_enhanced, feature_importance = train_and_compare(df_enhanced)

    print("\n" + "#"*70)
    print("# ✅ COMPLETE!")
    print("#"*70)
    print("\nNext steps:")
    print("1. Review feature importance - are course features in top 10?")
    print("2. Update your Phase 2 notebook to use enhanced features")
    print("3. Update weekly recommendation engine with new model")
    print("4. Test predictions on upcoming 2026 tournaments!")


if __name__ == "__main__":
    main()
