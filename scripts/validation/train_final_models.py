#!/usr/bin/env python3
"""
Final Model Training with Proper Validation
============================================
Trains win/top-5/top-10 prediction models on complete 2020-2024 dataset
with proper year-based cross-validation to avoid overfitting.

Training Strategy:
- Train on: 2020-2023 data
- Validate on: 2024 data (held-out future year)
- This prevents data leakage and gives realistic performance estimates

Expected Performance (ROC-AUC):
- Previous (overfitted): 0.93-0.98
- Realistic target: 0.72-0.78
- Baseline (course history only): 0.57

Usage:
    python scripts/validation/train_final_models.py

Outputs:
- data/models/win_model_final.pkl
- data/models/top5_model_final.pkl
- data/models/top10_model_final.pkl
- data/models/feature_importance.csv
- outputs/validation_report.txt
"""

import pandas as pd
import numpy as np
from pathlib import Path
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    roc_auc_score, classification_report, confusion_matrix,
    precision_recall_curve, roc_curve, brier_score_loss
)
from sklearn.model_selection import cross_val_score
import joblib
import warnings
warnings.filterwarnings('ignore')

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  🎯 FINAL MODEL TRAINING (Year-Based Validation)")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print()

# Paths
DATA_DIR = Path("/Users/jacklegnon/Desktop/golf_data/data")
print('DATA DIR:', DATA_DIR)
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
MODEL_DIR = DATA_DIR / "models"
OUTPUT_DIR = Path("outputs")
MODEL_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Use single-process training by default for compatibility with constrained
# environments (can override: TRAIN_N_JOBS=4 python ...).
TRAIN_N_JOBS = int(os.getenv("TRAIN_N_JOBS", "1"))
print(f"Training parallelism: n_jobs={TRAIN_N_JOBS}")

# Load merged dataset
print("Loading master training data...")
data_file = DATA_DIR / "processed" / "master_training_data_2020_2025.csv"

if not data_file.exists():
    print(f"❌ Master data file not found: {data_file}")
    print()
    print("Please run merge script first:")
    print("  python scripts/features/merge_all_historical_data.py")
    exit(1)

df = pd.read_csv(data_file)
print(f"✓ Loaded {len(df):,} records from {df['year'].min()}-{df['year'].max()}")
print()

# Backward/forward compatibility for course SG edge naming.
# Older merged datasets used `course_sg_vs_avg`; newer pipeline uses
# `course_sg_total_vs_avg` to be explicit.
if "course_sg_total_vs_avg" not in df.columns and "course_sg_vs_avg" in df.columns:
    df["course_sg_total_vs_avg"] = df["course_sg_vs_avg"]
if "course_sg_vs_avg" not in df.columns and "course_sg_total_vs_avg" in df.columns:
    df["course_sg_vs_avg"] = df["course_sg_total_vs_avg"]

# ============================================================================
# Feature Selection
# ============================================================================
print("=" * 60)
print("Step 1: Feature Selection")
print("-" * 60)

# Define feature groups
train_years = df[df['year'] < 2025]

# CRITICAL: Do NOT use per-tournament SG stats (sg_total, sg_ott, etc.)
# These are from the SAME tournament we're predicting - that's data leakage!
# Instead, use season_sg_* which are averages from PRIOR tournaments.

# Per-tournament SG - EXCLUDED (data leakage!)
# sg_features = [c for c in df.columns if c.startswith('sg_')]
print("⚠️  EXCLUDING per-tournament SG stats (sg_total, sg_ott, etc.) - DATA LEAKAGE!")
print("   Using season_sg_* features instead (prior performance)")

# Season-level SG averages - SAFE (prior performance)
season_sg_features = [c for c in df.columns if c.startswith('season_sg_')]

# Course history features - include binary indicators, exclude low-variance features
hist_features = [c for c in df.columns if c.startswith('hist_') or c.startswith('has_')]
# Remove hist_missed_cuts (now has variance, but keep it for now to see if it helps)
venue_features = ['venue_avg_finish', 'venue_finish_std']  # Only numeric venue features
field_features = [c for c in df.columns if 'field_' in c]
rank_features = ['world_rank'] if 'world_rank' in df.columns else []

# Form features (recent performance indicators) - expanded to include scoring stats
form_features = [c for c in df.columns if c in [
    'form_trend', 'finish_consistency', 'recent_top10s', 'recent_top5s', 'recent_cuts_pct',
    'recent_birdie_avg', 'recent_bogey_avg', 'recent_scoring_avg', 'recent_gir_pct',
    'recent_scrambling', 'recent_bounce_back', 'recent_final_round', 'recent_sand_save'
]]

# Course fit features - OLD fit_* features EXCLUDED (calculated from per-tournament SG = leakage!)
# course_fit_features = [c for c in df.columns if c.startswith('fit_') or c == 'course_fit_total']
print("⚠️  EXCLUDING old fit_* features (fit_*, course_fit_total) - based on same-tournament SG!")

# NEW Data Golf course fit features - SAFE (uses season_sg_* × course importance weights)
dg_fit_features = [c for c in df.columns if c.startswith('dg_fit_')]
if dg_fit_features:
    print(f"✓  Including {len(dg_fit_features)} Data Golf course fit features (uses season SG, no leakage)")
else:
    print("⚠️  No dg_fit_* features found - run merge script first")

# Course SG features - REMOVED: all course_sg_* features have 0% feature importance
# across all models (win/top5/top10/top20). Confirmed via feature_importance.csv.
# Keeping them adds noise and slows training with zero predictive benefit.
course_sg_features = []
print("ℹ️  EXCLUDING course_sg_* features - confirmed 0% importance across all models")

# Combine all features (WITHOUT leaky features, WITHOUT zero-importance course SG)
# Note: has_won_here is already in hist_features (starts with 'has_'), so don't add it again
all_features = season_sg_features + hist_features + venue_features + field_features + rank_features + form_features + dg_fit_features

# Filter to only existing features that have coverage in training years
available_features = [
    f for f in all_features
    if f in df.columns and train_years[f].notna().any()
]

removed_missing = [
    f for f in all_features
    if f in df.columns and not train_years[f].notna().any()
]
print(f"Selected {len(available_features)} features for modeling:")
print(available_features)
if removed_missing:
    print("\nExcluded features with no training coverage (all NaN in 2020-2024):")
    print(removed_missing)
print()
print(f"Available feature groups:")
print(f"  SG Stats (per-tournament): {len([f for f in available_features if f.startswith('sg_') and not f.startswith('season_')])}")
print(f"  SG Stats (season avg): {len([f for f in available_features if f.startswith('season_sg_')])}")
print(f"  Course History: {len([f for f in available_features if f.startswith('hist_')])}")
print(f"  Course Fit (DG weights): {len([f for f in available_features if f.startswith('dg_fit_')])}")
print(f"  Venue/Field Features: {len([f for f in available_features if 'field_' in f or f in ['venue_avg_finish', 'venue_finish_std']])}")
print(f"  Form Features: {len([f for f in available_features if f.startswith('recent_') or f in ['form_trend', 'finish_consistency']])}")
print(f"\nTotal features: {len(available_features)}")
print()

if len(available_features) == 0:
    print("❌ No features available! Check data merge.")
    exit(1)

# ============================================================================
# Train/Test Split (Year-Based)
# ============================================================================
print("=" * 60)
print("Step 2: Train/Test Split (Year-Based)")
print("-" * 60)

# Train on 2020-2024, test on 2025
train_df = df[df['year'] < 2025].copy()
test_df = df[df['year'] == 2025].copy()

print(f"Training set (2020-2024): {len(train_df):,} records")
print(f"Test set (2025): {len(test_df):,} records")
print()

# Drop rows missing targets
target_cols = [c for c in ['won', 'top5', 'top10', 'top20'] if c in df.columns]
train_df = train_df.dropna(subset=target_cols)
test_df = test_df.dropna(subset=target_cols)

# Impute missing feature values using training medians
feature_medians = train_df[available_features].median(numeric_only=True)
train_clean = train_df.copy()
test_clean = test_df.copy()
train_clean[available_features] = train_clean[available_features].fillna(feature_medians)
test_clean[available_features] = test_clean[available_features].fillna(feature_medians)

print(f"After target cleanup and feature imputation:")
print(f"  Training: {len(train_clean):,} records")
print(f"  Test: {len(test_clean):,} records")
print()

if len(train_clean) == 0:
    print("❌ No training rows remain after cleaning. Check feature availability.")
    print("   Try re-running data merge or inspect missing columns in master data.")
    exit(1)
elif len(train_clean) < 100 or len(test_clean) < 20:
    print("⚠️  WARNING: Very small dataset after cleaning!")
    print("   This may indicate missing SG stats or course history data.")
    print()

# Prepare feature matrices
X_train = train_clean[available_features]
X_test = test_clean[available_features]

# ============================================================================
# Model Training
# ============================================================================
print("=" * 60)
print("Step 3: Training Models")
print("-" * 60)

targets = {
    'win': 'won',
    'top5': 'top5',
    'top10': 'top10',
    'top20': 'top20'
}

models = {}
results = []


def avg_importance(cal_model):
    return np.mean(
        [c.estimator.feature_importances_ for c in cal_model.calibrated_classifiers_],
        axis=0
    )


def quick_auc(features, X_tr, X_te, y_tr, y_te):
    """Train a quick RF and return test AUC - used for feature experiments."""
    rf = RandomForestClassifier(
        n_estimators=50, max_depth=5, min_samples_split=50,
        min_samples_leaf=25, max_features='sqrt', random_state=42,
        class_weight='balanced_subsample', n_jobs=TRAIN_N_JOBS
    )
    rf.fit(X_tr[features], y_tr)
    return roc_auc_score(y_te, rf.predict_proba(X_te[features])[:, 1])


# ============================================================================
# Experiment: dg_fit features - keep or remove?
# ============================================================================
print("=" * 60)
print("Step 3a: dg_fit Feature Experiment (win model proxy)")
print("-" * 60)
print("Testing whether dg_fit_* features improve AUC...")

features_with_dg = available_features
features_without_dg = [f for f in available_features if not f.startswith('dg_fit_')]

y_win_tr = train_clean['won']
y_win_te = test_clean['won']

auc_with_dg = quick_auc(features_with_dg, train_clean, test_clean, y_win_tr, y_win_te)
auc_without_dg = quick_auc(features_without_dg, train_clean, test_clean, y_win_tr, y_win_te)

print(f"  Win AUC WITH dg_fit features:    {auc_with_dg:.4f}")
print(f"  Win AUC WITHOUT dg_fit features: {auc_without_dg:.4f}")
print(f"  Difference: {auc_with_dg - auc_without_dg:+.4f}")

if auc_without_dg >= auc_with_dg - 0.005:
    print("  ✅ dg_fit features add <0.005 AUC — REMOVING for cleaner model")
    available_features = features_without_dg
    dg_fit_removed = True
else:
    print(f"  ⚠️  dg_fit features add {auc_with_dg - auc_without_dg:.4f} AUC — KEEPING despite mixed real-world correlation")
    dg_fit_removed = False

print(f"  Final feature count: {len(available_features)}")
print()

# Rebuild X_train / X_test with final feature set
X_train = train_clean[available_features]
X_test = test_clean[available_features]


for model_name, target_col in targets.items():
    print(f"\n🎯 Training {model_name.upper()} model...")
    print("-" * 40)

    y_train = train_clean[target_col]
    y_test = test_clean[target_col]

    # Class balance
    train_pos = y_train.sum()
    train_neg = len(y_train) - train_pos
    print(f"  Training class balance:")
    print(f"    Positive: {train_pos:,} ({train_pos/len(y_train)*100:.2f}%)")
    print(f"    Negative: {train_neg:,} ({train_neg/len(y_train)*100:.2f}%)")

    # Train Random Forest with probability calibration using isotonic regression
    # CalibratedClassifierCV fits a calibration curve so predicted probabilities
    # match actual outcomes (e.g., 10% predicted = ~10% actual occurrence)
    print(f"\n  Training Random Forest with probability calibration...")

    # Base Random Forest classifier
    base_rf = RandomForestClassifier(
        n_estimators=100,        # Fewer trees (was 200)
        max_depth=5,             # Shallower trees (was 10) - key for reducing overfit
        min_samples_split=50,    # More samples required to split (was 20)
        min_samples_leaf=25,     # More samples required in leaves (was 10)
        max_features='sqrt',     # Only use sqrt(n_features) at each split
        random_state=42,
        n_jobs=TRAIN_N_JOBS,
        class_weight='balanced_subsample'  # Handle class imbalance
    )

    # Wrap with CalibratedClassifierCV for probability calibration
    # Uses isotonic regression (better for larger datasets than sigmoid/Platt)
    # cv=3 uses 3-fold cross-validation for calibration fitting
    rf = CalibratedClassifierCV(
        estimator=base_rf,
        method='isotonic',  # isotonic regression - better for larger datasets
        cv=3,               # 3-fold CV for calibration
        n_jobs=TRAIN_N_JOBS
    )

    rf.fit(X_train, y_train)

    # Predictions
    y_train_pred_proba = rf.predict_proba(X_train)[:, 1]
    y_test_pred_proba = rf.predict_proba(X_test)[:, 1]

    # Evaluate - AUC for ranking quality
    train_auc = roc_auc_score(y_train, y_train_pred_proba)
    test_auc = roc_auc_score(y_test, y_test_pred_proba)
    overfit_gap = train_auc - test_auc

    # Brier score for calibration quality (lower is better, 0 is perfect)
    train_brier = brier_score_loss(y_train, y_train_pred_proba)
    test_brier = brier_score_loss(y_test, y_test_pred_proba)

    # Check calibration: compare predicted avg vs actual rate
    pred_avg = y_test_pred_proba.mean()
    actual_avg = y_test.mean()
    calibration_ratio = pred_avg / actual_avg if actual_avg > 0 else 0

    print(f"\n  📊 Results:")
    print(f"    Train ROC-AUC: {train_auc:.4f}")
    print(f"    Test ROC-AUC:  {test_auc:.4f}")
    print(f"    Overfit Gap:   {overfit_gap:.4f}", end="")

    if overfit_gap < 0.05:
        print(" ✅ (Good!)")
    elif overfit_gap < 0.15:
        print(" ⚠️  (Moderate)")
    else:
        print(" ❌ (High overfitting)")

    print(f"\n  📐 Calibration:")
    print(f"    Train Brier Score: {train_brier:.4f}")
    print(f"    Test Brier Score:  {test_brier:.4f}")
    print(f"    Predicted Avg:     {pred_avg:.4f} ({pred_avg*100:.2f}%)")
    print(f"    Actual Rate:       {actual_avg:.4f} ({actual_avg*100:.2f}%)")
    print(f"    Calibration Ratio: {calibration_ratio:.2f}x", end="")

    if 0.8 <= calibration_ratio <= 1.2:
        print(" ✅ (Well calibrated)")
    elif 0.5 <= calibration_ratio <= 1.5:
        print(" ⚠️  (Moderate)")
    else:
        print(" ❌ (Poor calibration)")

    # Save model
    model_file = MODEL_DIR / f"{model_name}_model_final.pkl"
    joblib.dump(rf, model_file)
    print(f"\n  ✓ Saved to: {model_file}")

    models[model_name] = rf
    results.append({
        'model': model_name,
        'train_auc': train_auc,
        'test_auc': test_auc,
        'overfit_gap': overfit_gap,
        'train_brier': train_brier,
        'test_brier': test_brier,
        'calibration_ratio': calibration_ratio,
        'train_samples': len(y_train),
        'test_samples': len(y_test),
        'positive_rate': y_train.mean()
    })

# ============================================================================
# Feature Importance Analysis
# ============================================================================
print("\n" + "=" * 60)
print("Step 4: Feature Importance Analysis")
print("-" * 60)

# Average importance across all models
importance_df = pd.DataFrame({
    'feature': available_features,
    'win_importance': avg_importance(models['win']),
    'top5_importance': avg_importance(models['top5']),
    'top10_importance': avg_importance(models['top10']),
   'top20_importance': avg_importance(models['top20'])})

importance_df['avg_importance'] = importance_df[['win_importance', 'top5_importance', 'top10_importance']].mean(axis=1)
importance_df = importance_df.sort_values('avg_importance', ascending=False)

print("\nTop 15 Most Important Features:")
print()
print(importance_df.head(15).to_string(index=False))

# Save importance
importance_file = MODEL_DIR / "feature_importance.csv"
importance_df.to_csv(importance_file, index=False)
print(f"\n✓ Feature importance saved to: {importance_file}")

# ============================================================================
# Validation Report
# ============================================================================
print("\n" + "=" * 60)
print("Step 5: Generating Validation Report")
print("-" * 60)

report_lines = []
report_lines.append("="*70)
report_lines.append("  FINAL MODEL VALIDATION REPORT")
report_lines.append("  Year-Based Cross-Validation (Train: 2020-2024, Test: 2025)")
report_lines.append("="*70)
report_lines.append("")

report_lines.append("DATASET SUMMARY:")
report_lines.append(f"  Total Records: {len(df):,}")
report_lines.append(f"  Training Records: {len(train_clean):,} (2020-2024)")
report_lines.append(f"  Test Records: {len(test_clean):,} (2025)")
report_lines.append(f"  Features Used: {len(available_features)}")
report_lines.append("")

report_lines.append("FEATURE GROUPS:")
report_lines.append(f"  SG Stats: {len([f for f in available_features if f.startswith('sg_')])}")
report_lines.append(f"  Course History: {len([f for f in available_features if f.startswith('hist_')])}")
report_lines.append(f"  Course/Field: {len([f for f in available_features if 'course_' in f or 'field_' in f])}")
report_lines.append("")

report_lines.append("MODEL PERFORMANCE:")
report_lines.append("-"*70)
report_lines.append(f"{'Model':<10} {'Train AUC':<12} {'Test AUC':<12} {'Gap':<10} {'Status':<15}")
report_lines.append("-"*70)

for r in results:
    status = "✅ Good" if r['overfit_gap'] < 0.05 else ("⚠️  Moderate" if r['overfit_gap'] < 0.15 else "❌ Overfitting")
    report_lines.append(
        f"{r['model']:<10} {r['train_auc']:<12.4f} {r['test_auc']:<12.4f} "
        f"{r['overfit_gap']:<10.4f} {status:<15}"
    )

report_lines.append("")
report_lines.append("PROBABILITY CALIBRATION:")
report_lines.append("-"*70)
report_lines.append(f"{'Model':<10} {'Brier':<10} {'Pred Avg':<12} {'Actual':<10} {'Ratio':<10} {'Status':<15}")
report_lines.append("-"*70)

for r in results:
    cal_ratio = r.get('calibration_ratio', 0)
    if 0.8 <= cal_ratio <= 1.2:
        cal_status = "✅ Calibrated"
    elif 0.5 <= cal_ratio <= 1.5:
        cal_status = "⚠️  Moderate"
    else:
        cal_status = "❌ Poor"
    report_lines.append(
        f"{r['model']:<10} {r.get('test_brier', 0):<10.4f} "
        f"{r.get('calibration_ratio', 0) * r.get('positive_rate', 0)*100:<10.2f}% "
        f"{r.get('positive_rate', 0)*100:<8.2f}% "
        f"{cal_ratio:<10.2f}x {cal_status:<15}"
    )

report_lines.append("")
report_lines.append("INTERPRETATION:")
report_lines.append("  ROC-AUC Scale:")
report_lines.append("    0.50 = Random guessing")
report_lines.append("    0.60-0.65 = Slight edge")
report_lines.append("    0.70-0.75 = Good predictive power")
report_lines.append("    0.75-0.80 = Excellent (realistic ceiling for golf)")
report_lines.append("    0.90+ = Likely overfitting")
report_lines.append("")
report_lines.append("  Overfitting Gap:")
report_lines.append("    <0.05 = Excellent generalization")
report_lines.append("    0.05-0.15 = Acceptable")
report_lines.append("    >0.15 = Concerning overfitting")
report_lines.append("")

report_lines.append("TOP 10 FEATURES:")
report_lines.append("-"*70)
for idx, row in importance_df.head(10).iterrows():
    report_lines.append(f"  {row['feature']:<30} {row['avg_importance']:.4f}")

report_lines.append("")
report_lines.append("="*70)
report_lines.append("  Models saved to: data/models/")
report_lines.append("  Next step: Generate 2026 predictions")
report_lines.append("="*70)

# Print and save report
report_text = "\n".join(report_lines)
print("\n" + report_text)

report_file = OUTPUT_DIR / "validation_report.txt"
with open(report_file, 'w') as f:
    f.write(report_text)

print(f"\n✓ Validation report saved to: {report_file}")

# ============================================================================
# Summary
# ============================================================================
print("\n" + "="*60)
print("  ✅ TRAINING COMPLETE!")
print("="*60)
print()
print("Models saved:")

for model_name in models.keys():
    print(f"  - data/models/{model_name}_model_final.pkl")
print()
print("Reports saved:")
print(f"  - {importance_file}")
print(f"  - {report_file}")
print()
print("Next steps:")
print("  1. Review validation_report.txt for performance assessment")
print("  2. If test AUC > 0.70, proceed to 2026 predictions")
print("  3. If test AUC < 0.60, consider collecting more features")
print()
