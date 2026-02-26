#!/usr/bin/env python3
"""
Cut Probability Model
=====================
Predicts the probability of a player making the cut.

Key insight: ~45% of tournament entries miss the cut. A player who misses
the cut returns $0 and wastes a fantasy pick. This model helps avoid
selecting high-risk players.

Features used:
- SG stats (sg_total, sg_ott, sg_app, sg_putt, sg_t2g)
- Recent form (recent_cuts_pct, recent_top10s)
- Course history (hist_cut_rate, hist_times_played)
- World rank
- Field strength

Usage:
    # Train the model
    python cut_model.py train

    # Get cut probability for predictions DataFrame
    from scripts.predictions.cut_model import add_cut_probability
    predictions_df = add_cut_probability(predictions_df)
"""

import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report
import warnings
warnings.filterwarnings('ignore')

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = DATA_DIR / "models"
PROCESSED_DIR = DATA_DIR / "processed"

# Features for cut prediction
# IMPORTANT: Only use features available BEFORE the tournament (no leakage)
# - season_sg_* are prior-only averages (fixed in merge_all_historical_data.py)
# - hist_* are historical course stats
# - recent_* are from previous tournaments
# - world_rank and field context are pre-tournament
CUT_FEATURES = [
    # Season averages (prior-only, no current tournament)
    'season_sg_total',
    'season_sg_ott',
    'season_sg_app',
    'season_sg_putt',
    'season_sg_t2g',
    # Field-adjusted SG: player vs this week's specific field
    # (added Phase 2 — player below field level is higher cut risk)
    'season_sg_total_vs_field',
    # Course history (known before tournament)
    'hist_cut_rate',
    'hist_times_played',
    'hist_avg_finish',
    # Recent performance (from prior tournaments)
    'recent_cuts_pct',
    'recent_top10s',
    # Recent form: exponential decay avg (added Phase 2)
    # A player in poor recent form misses cuts more than their season avg suggests
    'recent_sg_weighted',
    # Context (known before tournament)
    'world_rank',
    'field_avg_rank',
]


def load_training_data():
    """Load master training data and create cut target."""
    # Auto-detect the most recently written master training file
    _candidates = sorted(PROCESSED_DIR.glob("master_training_data_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    master_path = _candidates[0] if _candidates else (PROCESSED_DIR / "master_training_data_2020_2025.csv")
    print(f"Using training data: {master_path.name}")
    df = pd.read_csv(master_path)

    # Create target: 1 = made cut, 0 = missed cut
    df['made_cut'] = (~df['position'].str.upper().str.contains('CUT|W/D', na=False)).astype(int)

    print(f"Loaded {len(df)} rows")
    print(f"Made cut: {df['made_cut'].sum()} ({df['made_cut'].mean()*100:.1f}%)")
    print(f"Missed cut: {(1-df['made_cut']).sum()} ({(1-df['made_cut'].mean())*100:.1f}%)")

    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare feature matrix for training or prediction."""
    # Select features that exist
    available_features = [f for f in CUT_FEATURES if f in df.columns]
    X = df[available_features].copy()

    # Fill missing values with reasonable defaults
    defaults = {
        'sg_total': 0.0,
        'sg_ott': 0.0,
        'sg_app': 0.0,
        'sg_putt': 0.0,
        'sg_t2g': 0.0,
        'season_sg_total': 0.0,
        'hist_cut_rate': 0.5,  # Assume 50% if unknown
        'hist_times_played': 0,
        'recent_cuts_pct': 0.5,  # Assume 50% if unknown
        'world_rank': 200,  # Middle of pack
        'field_avg_rank': 150,
    }

    for col in X.columns:
        if col in defaults:
            X[col] = X[col].fillna(defaults[col])
        else:
            X[col] = X[col].fillna(0)

    return X, available_features


def train_cut_model():
    """Train the cut probability model."""
    print("=" * 60)
    print("  TRAINING CUT PROBABILITY MODEL")
    print("=" * 60)

    # Load data
    df = load_training_data()

    # Prepare features
    X, feature_names = prepare_features(df)
    y = df['made_cut']

    print(f"\nFeatures used: {feature_names}")

    # Time-based split: train on 2020-2024, test on 2025
    train_mask = df['year'] < 2025
    X_train, X_test = X[train_mask], X[~train_mask]
    y_train, y_test = y[train_mask], y[~train_mask]

    print(f"\nTrain size: {len(X_train)} (2020-2024)")
    print(f"Test size: {len(X_test)} (2025)")

    # Train model with balanced classes
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_leaf=20,
        class_weight='balanced_subsample',
        random_state=42,
        n_jobs=-1
    )

    print("\nTraining Random Forest...")
    model.fit(X_train, y_train)

    # Evaluate
    train_proba = model.predict_proba(X_train)[:, 1]
    test_proba = model.predict_proba(X_test)[:, 1]

    train_auc = roc_auc_score(y_train, train_proba)
    test_auc = roc_auc_score(y_test, test_proba)

    print(f"\nModel Performance:")
    print(f"  Train AUC: {train_auc:.3f}")
    print(f"  Test AUC:  {test_auc:.3f}")

    # Feature importance
    importance = pd.DataFrame({
        'feature': feature_names,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\nFeature Importance:")
    for _, row in importance.iterrows():
        print(f"  {row['feature']}: {row['importance']*100:.1f}%")

    # Calibration check
    print("\nCalibration Check (Test Set):")
    for bucket_min in [0.0, 0.3, 0.5, 0.7, 0.9]:
        bucket_max = bucket_min + 0.1 if bucket_min < 0.9 else 1.0
        mask = (test_proba >= bucket_min) & (test_proba < bucket_max)
        if mask.sum() > 0:
            actual = y_test[mask].mean()
            predicted = test_proba[mask].mean()
            print(f"  {bucket_min*100:.0f}-{bucket_max*100:.0f}%: Predicted {predicted*100:.1f}%, Actual {actual*100:.1f}%, N={mask.sum()}")

    # Save model
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "cut_model.pkl"
    joblib.dump(model, model_path)
    print(f"\nModel saved to: {model_path}")

    # Save feature list for inference
    feature_path = MODEL_DIR / "cut_model_features.txt"
    feature_path.write_text("\n".join(feature_names))

    return model, feature_names


def load_cut_model():
    """Load trained cut model."""
    model_path = MODEL_DIR / "cut_model.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"Cut model not found at {model_path}. Run: python cut_model.py train")

    model = joblib.load(model_path)

    # Load feature list
    feature_path = MODEL_DIR / "cut_model_features.txt"
    if feature_path.exists():
        features = feature_path.read_text().strip().split("\n")
    else:
        features = CUT_FEATURES

    return model, features


def add_cut_probability(predictions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add cut probability to predictions DataFrame.

    Args:
        predictions_df: DataFrame with player predictions

    Returns:
        DataFrame with cut_prob and cut_risk columns added
    """
    try:
        model, features = load_cut_model()
    except FileNotFoundError as e:
        print(f"  ⚠️ Cut model not available: {e}")
        predictions_df['cut_prob'] = 0.5
        predictions_df['cut_risk'] = 'UNKNOWN'
        return predictions_df

    # Prepare features (handle missing columns)
    X = predictions_df.copy()
    for col in features:
        if col not in X.columns:
            X[col] = 0.0

    X = X[features].fillna(0)

    # Predict
    cut_proba = model.predict_proba(X)[:, 1]
    predictions_df['cut_prob'] = cut_proba

    # Risk categories
    def get_risk(prob):
        if prob >= 0.85:
            return 'LOW'
        elif prob >= 0.65:
            return 'MEDIUM'
        elif prob >= 0.45:
            return 'ELEVATED'
        else:
            return 'HIGH'

    predictions_df['cut_risk'] = predictions_df['cut_prob'].apply(get_risk)

    # Miss probability (inverse of cut prob)
    predictions_df['miss_cut_prob'] = 1 - predictions_df['cut_prob']

    return predictions_df


def get_cut_risk_summary(predictions_df: pd.DataFrame) -> str:
    """Get summary of cut risks in field."""
    if 'cut_risk' not in predictions_df.columns:
        return "Cut risk not calculated"

    lines = ["Cut Risk Summary:"]
    for risk in ['HIGH', 'ELEVATED', 'MEDIUM', 'LOW']:
        count = (predictions_df['cut_risk'] == risk).sum()
        if count > 0:
            lines.append(f"  {risk}: {count} players")

    # High risk players with high EV (potential traps)
    if 'expected_value' in predictions_df.columns and 'cut_risk' in predictions_df.columns:
        traps = predictions_df[
            (predictions_df['cut_risk'].isin(['HIGH', 'ELEVATED'])) &
            (predictions_df['expected_value'] > predictions_df['expected_value'].median())
        ].nsmallest(5, 'cut_prob')

        if len(traps) > 0:
            lines.append("\n  ⚠️ High EV but High Cut Risk (Traps):")
            for _, row in traps.iterrows():
                lines.append(f"    - {row['player_name']}: EV ${row['expected_value']:,.0f}, Cut Prob {row['cut_prob']*100:.0f}%")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train_cut_model()
    else:
        print("Usage:")
        print("  python cut_model.py train    # Train the cut model")
        print()
        print("Or import in code:")
        print("  from scripts.predictions.cut_model import add_cut_probability")
        print("  predictions_df = add_cut_probability(predictions_df)")
