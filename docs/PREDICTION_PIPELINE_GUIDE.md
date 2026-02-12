# 2026 Tournament Prediction Pipeline - Learning Guide

## Overview

This guide walks you through building a prediction system that takes a tournament field (list of players) and outputs ranked recommendations based on Expected Value (EV).

---

## The Pipeline Flow

```
Tournament Field (CSV)
         ↓
    [Step 1] Load player list
         ↓
    [Step 2] Get recent SG stats for each player (from 2025 data)
         ↓
    [Step 3] Look up course history for each player at this venue
         ↓
    [Step 4] Get venue difficulty stats
         ↓
    [Step 5] Build feature matrix (13 features per player)
         ↓
    [Step 6] Load trained models
         ↓
    [Step 7] Predict probabilities (win, top5, top10)
         ↓
    [Step 8] Calculate Expected Value
         ↓
    [Step 9] Rank and output recommendations
```

---

## Key Concepts

### 1. Feature Matrix (The "Stats Card")

For each player, you need to create a row with exactly 13 columns:

```python
# Example for Scottie Scheffler at The Masters
player_features = {
    'sg_t2g': 2.5,           # His recent tee-to-green performance
    'sg_putt': 0.8,          # His recent putting performance
    'sg_ott': 1.2,           # Off-the-tee
    'sg_total': 3.1,         # Total strokes gained
    'sg_app': 1.3,           # Approach shots
    'venue_avg_finish': 15.2,  # Average finish position at Augusta (all players)
    'venue_finish_std': 12.3,  # Variability at Augusta
    'hist_avg_finish': 5.0,    # Scottie's avg finish at Augusta
    'hist_best_finish': 1.0,   # His best finish (won in 2022)
    'hist_times_played': 6,    # Times he's played Augusta
    'hist_top10s': 5,          # Number of top-10s there
    'hist_top5s': 3,           # Number of top-5s
    'hist_wins': 1             # Number of wins
}
```

### 2. Recent SG Stats (Rolling Average)

**Problem**: Your model was trained on tournament-level SG stats, but you need to predict BEFORE the tournament happens.

**Solution**: Calculate rolling average of recent tournaments
- Option A: Simple average of last 5 tournaments
- Option B: Weighted average (more recent = more weight)
- Option C: Use season-to-date average

For simplicity, we'll use **last available stats from 2025** as a proxy.

### 3. Course History Lookup

**Important**: Tournament names need to be normalized the same way as training data.

```python
# Training data used this normalization:
venue_clean = (
    tournament_name
    .str.upper()
    .str.replace(r'[^\w\s]', '', regex=True)
    .str.strip()
)

# Examples:
# "The Masters" → "THE MASTERS"
# "AT&T Pebble Beach Pro-Am" → "ATT PEBBLE BEACH PROAM"
```

### 4. Handling Missing Data

What if a player has no course history?
- Set `hist_times_played = 0`
- Set `hist_avg_finish = NaN` (model was trained with NaN for no history)
- Set `hist_wins/top5s/top10s = 0`

**CRITICAL**: Your model was trained on data with NaN values. You need to either:
1. Fill NaN with a default value (e.g., median venue finish)
2. Train models that handle NaN (RandomForest can handle some NaN)

Let me check how your training data handled this:

```python
# From train_final_models.py line 116-117:
train_clean = train_df.dropna(subset=available_features + ['won', 'top5', 'top10'])
```

**Uh oh!** Your model was trained ONLY on rows with complete data (no NaN). This means:
- For predictions, you MUST fill NaN values
- Use sensible defaults (we'll discuss below)

### 5. Expected Value Calculation

```python
# EV = Expected winnings based on predicted probabilities
# Simplified version (you can make this more sophisticated):

def calculate_ev(win_prob, top5_prob, top10_prob, purse):
    """
    Calculate expected value for a player

    Args:
        win_prob: Probability of winning (0.0 to 1.0)
        top5_prob: Probability of top-5 finish
        top10_prob: Probability of top-10 finish
        purse: Tournament purse (e.g., 20000000)

    Returns:
        Expected value in dollars
    """
    # Prize money percentages (approximate)
    winner_pct = 0.18      # Winner gets 18% of purse
    top5_avg_pct = 0.08    # Avg for 2nd-5th place
    top10_avg_pct = 0.04   # Avg for 6th-10th place

    # Simple EV calculation
    ev = (
        win_prob * (purse * winner_pct) +
        (top5_prob - win_prob) * (purse * top5_avg_pct) +
        (top10_prob - top5_prob) * (purse * top10_avg_pct)
    )

    return ev
```

**Note**: This is simplified! Real prize distributions are non-linear. You can make this more accurate by:
1. Loading actual prize money data from past tournaments
2. Using your payout model from notebook 01
3. Simulating finish position distribution

---

## Data Requirements

### Files You Need

1. **Trained Models** (already have):
   - `/data/models/win_model_final.pkl`
   - `/data/models/top5_model_final.pkl`
   - `/data/models/top10_model_final.pkl`

2. **Historical Data** (already have):
   - `/data/processed/master_training_data_2020_2025.csv` (for course history lookup)
   - Contains venue_clean mappings and venue difficulty stats

3. **Recent Performance** (already have):
   - `/data/historical/tournament_stats_2025.csv` (for recent SG stats)

4. **Tournament Info** (need to create):
   - Tournament name
   - Purse amount
   - Field list (players competing)

### Tournament Field Format

Create a CSV file for each tournament:

```csv
player_id,player_name
33410,Andrew Landry
45526,Abraham Ancer
46046,Scottie Scheffler
...
```

You can get this from:
- PGA Tour website (manual entry)
- PGA Tour API (scraping)
- ESPN or other sources

---

## Step-by-Step Coding Guide

### Step 0: Setup

```python
#!/usr/bin/env python3
"""
Tournament Prediction Script
============================
Generates win/top5/top10 predictions for a tournament field.

Usage:
    python scripts/predictions/predict_tournament.py \\
        --tournament "The Masters" \\
        --purse 18000000 \\
        --field data/fields/masters_2026.csv
"""

import pandas as pd
import numpy as np
import joblib
from pathlib import Path
import argparse

# Paths
DATA_DIR = Path("/Users/jacklegnon/Desktop/golf_data/data")
MODEL_DIR = DATA_DIR / "models"
PROCESSED_DIR = DATA_DIR / "processed"
HISTORICAL_DIR = DATA_DIR / "historical"
```

### Step 1: Load Models and Training Data

```python
def load_models():
    """Load trained win/top5/top10 models"""
    models = {
        'win': joblib.load(MODEL_DIR / 'win_model_final.pkl'),
        'top5': joblib.load(MODEL_DIR / 'top5_model_final.pkl'),
        'top10': joblib.load(MODEL_DIR / 'top10_model_final.pkl')
    }
    return models

def load_reference_data():
    """Load historical data for feature engineering"""
    # Master data (for course history lookup and venue stats)
    master_df = pd.read_csv(PROCESSED_DIR / 'master_training_data_2020_2025.csv')

    # Recent SG stats (2025 data)
    stats_2025 = pd.read_csv(HISTORICAL_DIR / 'tournament_stats_2025.csv')

    return master_df, stats_2025
```

### Step 2: Normalize Tournament Name

```python
def normalize_venue_name(tournament_name):
    """
    Normalize tournament name to match training data format

    Must match the normalization used in merge_all_historical_data.py
    """
    return (
        tournament_name
        .upper()
        .replace(r'[^\w\s]', '')  # Remove punctuation
        .strip()
    )

# Example usage:
venue_clean = normalize_venue_name("The Masters")
# Result: "THE MASTERS"
```

### Step 3: Calculate Recent SG Stats for Players

```python
def get_recent_sg_stats(player_id, stats_df):
    """
    Get most recent SG stats for a player from 2025 data

    Args:
        player_id: Player ID
        stats_df: DataFrame with 2025 tournament stats

    Returns:
        Dict with sg_total, sg_ott, sg_app, sg_putt, sg_t2g
    """
    # Filter to this player
    player_stats = stats_df[
        (stats_df['player_id'] == player_id) &
        (stats_df['stat_component'] == 'Avg')
    ].copy()

    if len(player_stats) == 0:
        # No recent stats - return NaN (will fill later)
        return {
            'sg_total': np.nan,
            'sg_ott': np.nan,
            'sg_app': np.nan,
            'sg_putt': np.nan,
            'sg_t2g': np.nan
        }

    # Pivot stats to wide format
    stats_pivot = player_stats.pivot_table(
        index='tournament_id',
        columns='stat_id',
        values='stat_value',
        aggfunc='first'
    )

    # Map stat IDs to names
    stat_mapping = {
        2567: 'sg_total',
        2568: 'sg_ott',
        2569: 'sg_app',
        2564: 'sg_putt',
        2674: 'sg_t2g'
    }

    # Calculate average across all 2025 tournaments
    recent_stats = {}
    for stat_id, stat_name in stat_mapping.items():
        if stat_id in stats_pivot.columns:
            recent_stats[stat_name] = stats_pivot[stat_id].mean()
        else:
            recent_stats[stat_name] = np.nan

    return recent_stats
```

**Your Task**: This calculates season average. Can you modify it to:
- Only use the **last 5 tournaments**?
- Weight recent tournaments more heavily?

**Hint**: Sort by tournament_id or date, then take `.tail(5)` or use exponential weighting.

### Step 4: Look Up Course History

```python
def get_course_history(player_id, venue_clean, master_df):
    """
    Get player's historical performance at this venue

    Args:
        player_id: Player ID
        venue_clean: Normalized venue name
        master_df: Master training data

    Returns:
        Dict with hist_* features
    """
    # Filter to this player at this venue (past years only)
    history = master_df[
        (master_df['player_id'] == player_id) &
        (master_df['venue_clean'] == venue_clean)
    ].copy()

    if len(history) == 0:
        # No history at this venue
        return {
            'hist_times_played': 0,
            'hist_avg_finish': np.nan,
            'hist_best_finish': np.nan,
            'hist_wins': 0,
            'hist_top5s': 0,
            'hist_top10s': 0
        }

    # Calculate historical stats
    return {
        'hist_times_played': len(history),
        'hist_avg_finish': history['position_num'].mean(),
        'hist_best_finish': history['position_num'].min(),
        'hist_wins': (history['position_num'] == 1).sum(),
        'hist_top5s': (history['position_num'] <= 5).sum(),
        'hist_top10s': (history['position_num'] <= 10).sum()
    }
```

### Step 5: Get Venue Difficulty Stats

```python
def get_venue_stats(venue_clean, master_df):
    """
    Get venue difficulty statistics

    Args:
        venue_clean: Normalized venue name
        master_df: Master training data

    Returns:
        Dict with venue_avg_finish, venue_finish_std
    """
    venue_data = master_df[master_df['venue_clean'] == venue_clean]

    if len(venue_data) == 0:
        # New venue (no history)
        return {
            'venue_avg_finish': np.nan,
            'venue_finish_std': np.nan
        }

    return {
        'venue_avg_finish': venue_data['venue_avg_finish'].iloc[0],  # Same for all rows
        'venue_finish_std': venue_data['venue_finish_std'].iloc[0]
    }
```

### Step 6: Build Feature Matrix

```python
def build_feature_matrix(field_df, tournament_name, master_df, stats_2025):
    """
    Build feature matrix for all players in the field

    Args:
        field_df: DataFrame with player_id, player_name
        tournament_name: Tournament name (e.g., "The Masters")
        master_df: Master training data
        stats_2025: Recent SG stats

    Returns:
        DataFrame with 13 features per player
    """
    venue_clean = normalize_venue_name(tournament_name)
    venue_stats = get_venue_stats(venue_clean, master_df)

    features_list = []

    for idx, player in field_df.iterrows():
        player_id = player['player_id']
        player_name = player['player_name']

        # Get features
        sg_stats = get_recent_sg_stats(player_id, stats_2025)
        course_hist = get_course_history(player_id, venue_clean, master_df)

        # Combine all features
        player_features = {
            'player_id': player_id,
            'player_name': player_name,
            **sg_stats,
            **venue_stats,
            **course_hist
        }

        features_list.append(player_features)

    features_df = pd.DataFrame(features_list)

    return features_df
```

### Step 7: Handle Missing Values

```python
def fill_missing_values(features_df):
    """
    Fill NaN values with sensible defaults

    CRITICAL: Model was trained only on complete data,
    so we must fill NaN for predictions
    """
    # SG stats: Fill with 0 (average performance)
    sg_cols = ['sg_total', 'sg_ott', 'sg_app', 'sg_putt', 'sg_t2g']
    for col in sg_cols:
        features_df[col] = features_df[col].fillna(0)

    # Course history: Fill avg_finish with venue average
    # (if they haven't played, assume they'll finish at venue average)
    if features_df['hist_avg_finish'].isna().any():
        venue_avg = features_df['venue_avg_finish'].iloc[0]  # Same for all players
        features_df['hist_avg_finish'] = features_df['hist_avg_finish'].fillna(venue_avg)
        features_df['hist_best_finish'] = features_df['hist_best_finish'].fillna(venue_avg)

    # Venue stats: Fill with median across all venues
    features_df['venue_avg_finish'] = features_df['venue_avg_finish'].fillna(35.0)
    features_df['venue_finish_std'] = features_df['venue_finish_std'].fillna(20.0)

    return features_df
```

**Your Task**: These defaults are arbitrary! Can you improve them?
- What's a better default for `sg_total`? (Hint: calculate median from 2025 data)
- Should rookies (no history) be penalized more than `venue_avg`?

### Step 8: Make Predictions

```python
def make_predictions(features_df, models):
    """
    Generate win/top5/top10 probabilities

    Args:
        features_df: DataFrame with features
        models: Dict with trained models

    Returns:
        DataFrame with predictions added
    """
    # Feature columns (must match training!)
    feature_cols = [
        'sg_t2g', 'sg_putt', 'sg_ott', 'sg_total', 'sg_app',
        'venue_avg_finish', 'venue_finish_std',
        'hist_avg_finish', 'hist_best_finish', 'hist_times_played',
        'hist_top10s', 'hist_top5s', 'hist_wins'
    ]

    X = features_df[feature_cols]

    # Predict probabilities
    features_df['win_prob'] = models['win'].predict_proba(X)[:, 1]
    features_df['top5_prob'] = models['top5'].predict_proba(X)[:, 1]
    features_df['top10_prob'] = models['top10'].predict_proba(X)[:, 1]

    return features_df
```

### Step 9: Calculate Expected Value

```python
def calculate_expected_value(predictions_df, purse):
    """
    Calculate EV for each player

    Args:
        predictions_df: DataFrame with win/top5/top10 probabilities
        purse: Tournament purse (e.g., 20000000)

    Returns:
        DataFrame with EV column added
    """
    # Simple EV calculation (you can improve this!)
    predictions_df['expected_value'] = (
        predictions_df['win_prob'] * (purse * 0.18) +
        (predictions_df['top5_prob'] - predictions_df['win_prob']) * (purse * 0.08) +
        (predictions_df['top10_prob'] - predictions_df['top5_prob']) * (purse * 0.04)
    )

    return predictions_df
```

### Step 10: Rank and Output

```python
def generate_recommendations(predictions_df, top_n=10):
    """
    Rank players by EV and format output

    Args:
        predictions_df: DataFrame with predictions and EV
        top_n: Number of top recommendations to show

    Returns:
        DataFrame sorted by EV
    """
    # Sort by expected value
    recommendations = predictions_df.sort_values('expected_value', ascending=False)

    # Format for display
    output_cols = [
        'player_name',
        'expected_value',
        'win_prob',
        'top5_prob',
        'top10_prob',
        'hist_times_played',
        'hist_avg_finish',
        'sg_total'
    ]

    return recommendations[output_cols].head(top_n)
```

### Step 11: Main Function

```python
def main():
    parser = argparse.ArgumentParser(description='Generate tournament predictions')
    parser.add_argument('--tournament', required=True, help='Tournament name')
    parser.add_argument('--purse', type=int, required=True, help='Tournament purse')
    parser.add_argument('--field', required=True, help='Path to field CSV')
    parser.add_argument('--output', default=None, help='Output file (optional)')

    args = parser.parse_args()

    print("Loading models and data...")
    models = load_models()
    master_df, stats_2025 = load_reference_data()

    print(f"Loading field from {args.field}...")
    field_df = pd.read_csv(args.field)

    print("Building feature matrix...")
    features_df = build_feature_matrix(
        field_df, args.tournament, master_df, stats_2025
    )

    print("Filling missing values...")
    features_df = fill_missing_values(features_df)

    print("Making predictions...")
    predictions_df = make_predictions(features_df, models)

    print(f"Calculating expected value (purse: ${args.purse:,})...")
    predictions_df = calculate_expected_value(predictions_df, args.purse)

    print("\nTop 10 Recommendations:")
    recommendations = generate_recommendations(predictions_df, top_n=10)
    print(recommendations.to_string(index=False))

    if args.output:
        predictions_df.to_csv(args.output, index=False)
        print(f"\nFull predictions saved to: {args.output}")

if __name__ == '__main__':
    main()
```

---

## Your Coding Challenges

Now that you have the template, here are some improvements to make:

### Challenge 1: Better SG Stats (Rolling Average)
Modify `get_recent_sg_stats()` to use only the last 5 tournaments instead of season average.

### Challenge 2: Weighted Recent Form
Weight recent tournaments more: last tournament = 40%, 2nd last = 30%, 3rd = 20%, 4th = 10%

### Challenge 3: Better Missing Value Handling
Calculate median SG stats from 2025 data instead of using 0.

### Challenge 4: More Accurate EV Calculation
Use your prize money model from notebook 01 instead of fixed percentages.

### Challenge 5: Field CSV Creator
Build a helper script that scrapes the field from PGA Tour website.

---

## Testing Your Script

### Test Case: The Masters 2026

1. Create a test field file:

```bash
cat > /Users/jacklegnon/Desktop/golf_data/data/fields/masters_2026_test.csv << EOF
player_id,player_name
46046,Scottie Scheffler
33448,Rory McIlroy
47959,Jon Rahm
EOF
```

2. Run the prediction:

```bash
python scripts/predictions/predict_tournament.py \\
    --tournament "The Masters" \\
    --purse 18000000 \\
    --field data/fields/masters_2026_test.csv \\
    --output outputs/masters_2026_predictions.csv
```

3. Expected output:
```
Top 10 Recommendations:
player_name         expected_value  win_prob  top5_prob  top10_prob
Scottie Scheffler   $524,000        0.15      0.35       0.48
Rory McIlroy        $398,000        0.09      0.28       0.42
Jon Rahm            $375,000        0.08      0.25       0.40
```

---

## Next Steps

Once you have the basic script working:

1. **Validate predictions**: Compare your 2026 predictions to actual 2025 results (backtest)
2. **Tune EV calculation**: Use actual prize distributions
3. **Add confidence intervals**: Show uncertainty in predictions
4. **Build weekly workflow**: Automate field collection and prediction generation

---

## Common Issues and Debugging

### Issue 1: "KeyError: 'sg_total'"
**Problem**: Feature name mismatch between training and prediction
**Solution**: Double-check feature column names match exactly

### Issue 2: "Model gives same probability to everyone"
**Problem**: Features not being populated correctly (all NaN or all 0)
**Solution**: Print `features_df` before prediction to inspect values

### Issue 3: "Predictions are way off"
**Problem**:
- Missing values filled incorrectly
- SG stats not recent enough
- Course history not matching (venue name mismatch)

**Solution**:
- Validate venue normalization matches training
- Check that you're using 2025 stats (not older)
- Inspect feature distributions

---

## Summary

You now have a complete blueprint for the prediction pipeline! The key learning points:

1. **Feature engineering**: Must match training data exactly
2. **Missing values**: Model can't handle NaN, so fill intelligently
3. **Recent performance**: SG stats need to be current
4. **Expected value**: Probability × Prize money = EV
5. **Testing**: Always validate on known results first

**Your turn!** Start building the script step by step. Code each function, test it, and ask questions when you get stuck.