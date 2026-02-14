#!/usr/bin/env python3
"""
Odds Ensemble Module
====================

Integrates Vegas odds with model predictions to create ensemble probabilities.

WHY ENSEMBLE MODEL + ODDS?
--------------------------
1. Vegas odds contain valuable information:
   - Sharp money from professional bettors
   - Insider knowledge (injuries, form, etc.)
   - Consensus of thousands of opinions

2. Your model captures things Vegas might miss:
   - Course fit specifics
   - Recent SG trends
   - Historical venue performance

3. Combining both is often better than either alone:
   - Vegas is good at ranking favorites
   - Models can find undervalued mid-tier players

ENSEMBLE METHODS:
-----------------
1. "weighted_avg": Simple weighted average
   ensemble = (model_weight * model_prob) + (vegas_weight * vegas_prob)

2. "geometric": Geometric mean (multiplicative)
   ensemble = (model_prob^w1 * vegas_prob^w2)^(1/(w1+w2))

3. "log_odds": Average in log-odds space (more principled)
   log_odds = w1*log(p1/(1-p1)) + w2*log(p2/(1-p2))
   ensemble = 1 / (1 + exp(-log_odds))

Usage:
    from scripts.predictions.odds_ensemble import create_ensemble_predictions

    ensemble_df = create_ensemble_predictions(
        predictions_df,
        odds_df,
        model_weight=0.6,  # Trust model slightly more
        vegas_weight=0.4
    )
"""

import pandas as pd
import numpy as np
from pathlib import Path


def load_odds(odds_path: str) -> pd.DataFrame:
    """
    Load odds from CSV file.

    Expected columns: player_id, fair_prob (or implied_prob)
    """
    df = pd.read_csv(odds_path)

    # Ensure we have fair_prob
    if 'fair_prob' not in df.columns and 'implied_prob' in df.columns:
        # Normalize implied probs to sum to 1
        total = df['implied_prob'].sum()
        df['fair_prob'] = df['implied_prob'] / total

    return df


def weighted_average_ensemble(model_prob: float, vegas_prob: float,
                               model_weight: float = 0.6) -> float:
    """
    Simple weighted average of probabilities.

    This is the most straightforward approach but can produce
    probabilities that don't make sense if weights sum to >1.

    Args:
        model_prob: Model's win probability
        vegas_prob: Vegas implied probability
        model_weight: Weight for model (vegas_weight = 1 - model_weight)

    Returns:
        Ensemble probability
    """
    if pd.isna(model_prob) or pd.isna(vegas_prob):
        return model_prob if pd.notna(model_prob) else vegas_prob

    vegas_weight = 1 - model_weight
    return (model_weight * model_prob) + (vegas_weight * vegas_prob)


def geometric_mean_ensemble(model_prob: float, vegas_prob: float,
                            model_weight: float = 0.6) -> float:
    """
    Geometric mean of probabilities.

    Better for combining probabilities as it's scale-invariant
    and naturally handles the multiplicative nature of odds.

    Formula: (p1^w1 * p2^w2)^(1/(w1+w2))

    Args:
        model_prob: Model's win probability
        vegas_prob: Vegas implied probability
        model_weight: Weight for model

    Returns:
        Ensemble probability
    """
    if pd.isna(model_prob) or pd.isna(vegas_prob):
        return model_prob if pd.notna(model_prob) else vegas_prob

    # Avoid log(0) errors
    model_prob = max(model_prob, 1e-10)
    vegas_prob = max(vegas_prob, 1e-10)

    vegas_weight = 1 - model_weight
    total_weight = model_weight + vegas_weight

    # Geometric mean
    log_ensemble = (model_weight * np.log(model_prob) +
                   vegas_weight * np.log(vegas_prob)) / total_weight

    return np.exp(log_ensemble)


def log_odds_ensemble(model_prob: float, vegas_prob: float,
                      model_weight: float = 0.6) -> float:
    """
    Combine probabilities in log-odds (logit) space.

    This is the most principled approach for combining probabilities.
    Log-odds averaging is common in ensemble methods because:
    - It properly handles the bounded nature of probabilities
    - Equal weights = geometric mean of odds ratios
    - More stable for extreme probabilities

    Formula:
        log_odds = w1*logit(p1) + w2*logit(p2)
        ensemble = sigmoid(log_odds)

    Args:
        model_prob: Model's win probability
        vegas_prob: Vegas implied probability
        model_weight: Weight for model

    Returns:
        Ensemble probability
    """
    if pd.isna(model_prob) or pd.isna(vegas_prob):
        return model_prob if pd.notna(model_prob) else vegas_prob

    # Clip to avoid log(0) or log(inf)
    model_prob = np.clip(model_prob, 1e-10, 1 - 1e-10)
    vegas_prob = np.clip(vegas_prob, 1e-10, 1 - 1e-10)

    # Convert to log-odds
    model_logit = np.log(model_prob / (1 - model_prob))
    vegas_logit = np.log(vegas_prob / (1 - vegas_prob))

    # Weighted average in log-odds space
    vegas_weight = 1 - model_weight
    ensemble_logit = model_weight * model_logit + vegas_weight * vegas_logit

    # Convert back to probability
    return 1 / (1 + np.exp(-ensemble_logit))


def create_ensemble_predictions(predictions_df: pd.DataFrame,
                                 odds_df: pd.DataFrame,
                                 model_weight: float = 0.6,
                                 method: str = 'log_odds') -> pd.DataFrame:
    """
    Combine model predictions with Vegas odds.

    Args:
        predictions_df: DataFrame with model predictions (win_prob, top5_prob, etc.)
        odds_df: DataFrame with Vegas odds (player_id, fair_prob)
        model_weight: Weight for model predictions (0-1)
        method: Ensemble method ('weighted_avg', 'geometric', 'log_odds')

    Returns:
        DataFrame with ensemble predictions added
    """
    # Select ensemble function
    ensemble_funcs = {
        'weighted_avg': weighted_average_ensemble,
        'geometric': geometric_mean_ensemble,
        'log_odds': log_odds_ensemble
    }

    if method not in ensemble_funcs:
        raise ValueError(f"Unknown method: {method}. Use one of {list(ensemble_funcs.keys())}")

    ensemble_func = ensemble_funcs[method]

    # Merge predictions with odds
    df = predictions_df.copy()

    # Get relevant odds columns
    odds_cols = ['player_id', 'fair_prob', 'odds_to_win', 'odds_numeric', 'odds_rank']
    odds_subset = odds_df[[c for c in odds_cols if c in odds_df.columns]]

    # Rename fair_prob to vegas_prob for clarity
    odds_subset = odds_subset.rename(columns={'fair_prob': 'vegas_prob'})

    # Merge
    df = df.merge(odds_subset, on='player_id', how='left')

    # Create ensemble win probability
    df['ensemble_win_prob'] = df.apply(
        lambda row: ensemble_func(row['win_prob'], row['vegas_prob'], model_weight),
        axis=1
    )

    # For players without odds, use model probability
    df['ensemble_win_prob'] = df['ensemble_win_prob'].fillna(df['win_prob'])

    # Normalize ensemble probabilities to sum to 1 (like a proper distribution)
    total_prob = df['ensemble_win_prob'].sum()
    if total_prob > 0:
        df['ensemble_win_prob_normalized'] = df['ensemble_win_prob'] / total_prob

    # Calculate edge (model vs vegas)
    df['model_vs_vegas_edge'] = df['win_prob'] - df['vegas_prob']

    # Calculate value metrics
    df['is_value_bet'] = df['model_vs_vegas_edge'] > 0.01  # >1% edge

    # Flag large disagreements (model vs vegas drift)
    drift_threshold = 0.02  # 2% absolute edge
    df['odds_drift_flag'] = df['model_vs_vegas_edge'].abs() >= drift_threshold
    df['odds_drift_level'] = np.where(
        df['model_vs_vegas_edge'] >= drift_threshold,
        'MODEL>>VEGAS',
        np.where(df['model_vs_vegas_edge'] <= -drift_threshold, 'VEGAS>>MODEL', 'OK')
    )

    return df


def analyze_model_vs_vegas(df: pd.DataFrame) -> str:
    """
    Generate analysis comparing model to Vegas.

    Returns formatted string with insights.
    """
    lines = []
    lines.append("\n" + "=" * 70)
    lines.append("  MODEL vs VEGAS ANALYSIS")
    lines.append("=" * 70)

    # Players with odds
    has_odds = df['vegas_prob'].notna().sum()
    lines.append(f"\n  Players with Vegas odds: {has_odds}/{len(df)}")

    if has_odds == 0:
        lines.append("  No Vegas odds available for comparison")
        return "\n".join(lines)

    # Correlation between model and vegas
    valid = df[df['vegas_prob'].notna()]
    corr = valid['win_prob'].corr(valid['vegas_prob'])
    lines.append(f"  Model-Vegas correlation: {corr:.3f}")

    # Value bets
    value_bets = df[df['is_value_bet'] == True]
    lines.append(f"  Value bets (>1% edge): {len(value_bets)}")

    # Top disagreements (model likes more than Vegas)
    lines.append("\n  TOP MODEL PICKS vs VEGAS:")
    lines.append("-" * 70)
    lines.append(f"  {'Player':<25} {'Model':>7} {'Vegas':>7} {'Edge':>7} {'Odds':>8}")

    top_edge = df.nlargest(10, 'model_vs_vegas_edge')
    for _, row in top_edge.iterrows():
        name = str(row['player_name'])[:24]
        model = row['win_prob'] * 100 if pd.notna(row['win_prob']) else 0
        vegas = row['vegas_prob'] * 100 if pd.notna(row['vegas_prob']) else 0
        edge = row['model_vs_vegas_edge'] * 100 if pd.notna(row['model_vs_vegas_edge']) else 0
        odds = row.get('odds_to_win', 'N/A')
        lines.append(f"  {name:<25} {model:>6.2f}% {vegas:>6.2f}% {edge:>+6.2f}% {odds:>8}")

    # Biggest fades (Vegas likes more than model)
    lines.append("\n  BIGGEST FADES (Vegas > Model):")
    lines.append("-" * 70)

    bottom_edge = df.nsmallest(5, 'model_vs_vegas_edge')
    for _, row in bottom_edge.iterrows():
        if pd.notna(row['vegas_prob']):
            name = str(row['player_name'])[:24]
            model = row['win_prob'] * 100
            vegas = row['vegas_prob'] * 100
            edge = row['model_vs_vegas_edge'] * 100
            odds = row.get('odds_to_win', 'N/A')
            lines.append(f"  {name:<25} {model:>6.2f}% {vegas:>6.2f}% {edge:>+6.2f}% {odds:>8}")

    return "\n".join(lines)


def print_ensemble_rankings(df: pd.DataFrame, top_n: int = 15) -> None:
    """
    Print ensemble rankings comparing model, vegas, and ensemble.
    """
    print("\n" + "=" * 80)
    print("  ENSEMBLE RANKINGS")
    print("=" * 80)

    # Sort by ensemble probability
    ranked = df.sort_values('ensemble_win_prob', ascending=False).head(top_n)

    print(f"\n  {'Rank':<5} {'Player':<25} {'Ensemble':>9} {'Model':>8} {'Vegas':>8} {'Odds':>8}")
    print("-" * 80)

    for i, (_, row) in enumerate(ranked.iterrows(), 1):
        name = str(row['player_name'])[:24]
        ensemble = row['ensemble_win_prob'] * 100
        model = row['win_prob'] * 100 if pd.notna(row['win_prob']) else 0
        vegas = row['vegas_prob'] * 100 if pd.notna(row['vegas_prob']) else 0
        odds = row.get('odds_to_win', 'N/A')

        print(f"  {i:<5} {name:<25} {ensemble:>8.2f}% {model:>7.2f}% {vegas:>7.2f}% {odds:>8}")


# ============================================================================
# Integration with predict_tournament.py
# ============================================================================

def add_odds_to_predictions(predictions_df: pd.DataFrame,
                             tournament_id: str = None,
                             odds_path: str = None,
                             model_weight: float = 0.6,
                             method: str = 'log_odds') -> pd.DataFrame:
    """
    Add Vegas odds and create ensemble predictions.

    This function can be called from predict_tournament.py to add odds integration.

    Args:
        predictions_df: DataFrame with model predictions
        tournament_id: Tournament ID to auto-find odds file
        odds_path: Explicit path to odds CSV
        model_weight: Weight for model in ensemble (0-1)
        method: Ensemble method

    Returns:
        DataFrame with odds and ensemble predictions added
    """
    # Find odds file
    if odds_path:
        odds_file = Path(odds_path)
    elif tournament_id:
        odds_dir = Path("data/odds")
        matches = list(odds_dir.glob(f"*{tournament_id}*.csv"))
        if matches:
            odds_file = matches[0]
        else:
            print(f"  No odds file found for {tournament_id}")
            print(f"  Run: python scripts/scrapers/fetch_pga_odds.py --tournament-id {tournament_id}")
            return predictions_df
    else:
        print("  No odds file specified")
        return predictions_df

    if not odds_file.exists():
        print(f"  Odds file not found: {odds_file}")
        return predictions_df

    print(f"\n  Loading odds from {odds_file}...")
    odds_df = load_odds(str(odds_file))
    print(f"  Found odds for {len(odds_df)} players")

    # Create ensemble
    print(f"  Creating ensemble (method={method}, model_weight={model_weight})...")
    ensemble_df = create_ensemble_predictions(
        predictions_df, odds_df,
        model_weight=model_weight,
        method=method
    )

    # Print analysis
    analysis = analyze_model_vs_vegas(ensemble_df)
    print(analysis)

    # Print ensemble rankings
    print_ensemble_rankings(ensemble_df)

    return ensemble_df


# ============================================================================
# Multi-Book Odds Integration
# ============================================================================

def load_multi_book_odds(tournament_id: str = None) -> pd.DataFrame:
    """
    Load multi-book odds data from The Odds API scraper output.

    Returns DataFrame with consensus odds across multiple sportsbooks.
    """
    odds_dir = Path(__file__).parent.parent.parent / "data" / "odds"

    # Try tournament-specific file first
    if tournament_id:
        multi_file = odds_dir / f"multi_book_odds_{tournament_id}.csv"
        if multi_file.exists():
            return pd.read_csv(multi_file)

    # Fall back to latest
    latest_file = odds_dir / "multi_book_odds_latest.csv"
    if latest_file.exists():
        return pd.read_csv(latest_file)

    return pd.DataFrame()


def add_multi_book_odds_to_predictions(predictions_df: pd.DataFrame,
                                        tournament_id: str = None) -> pd.DataFrame:
    """
    Enhance predictions with multi-book odds data.

    Adds:
    - Consensus odds from multiple sportsbooks
    - Best available odds
    - Value spread (odds variance across books)
    - Sharp vs recreational book comparison
    """
    multi_df = load_multi_book_odds(tournament_id)

    if multi_df.empty:
        print("  No multi-book odds available")
        return predictions_df

    # Normalize names for matching
    def normalize_name(name):
        if pd.isna(name):
            return ""
        return str(name).lower().strip().replace(".", "").replace("-", " ")

    predictions_df = predictions_df.copy()
    predictions_df["name_norm"] = predictions_df["player_name"].apply(normalize_name)
    multi_df["name_norm"] = multi_df["player_name"].apply(normalize_name)

    # Columns to merge
    merge_cols = ["name_norm", "odds_consensus", "odds_best", "odds_worst",
                  "implied_prob_consensus", "num_books", "odds_spread", "value_spread_pct"]
    merge_cols = [c for c in merge_cols if c in multi_df.columns]

    # Merge
    merged = predictions_df.merge(
        multi_df[merge_cols],
        on="name_norm",
        how="left",
        suffixes=("", "_multi")
    )

    merged = merged.drop(columns=["name_norm"])

    # Calculate multi-book edge (model vs multi-book consensus)
    if "implied_prob_consensus" in merged.columns:
        merged["multi_book_edge"] = merged["win_prob"] - merged["implied_prob_consensus"]
        merged["is_multi_book_value"] = merged["multi_book_edge"] > 0.01

    books_found = merged["num_books"].notna().sum()
    print(f"  ✓ Added multi-book odds for {books_found} players")

    return merged


def find_best_odds_opportunities(predictions_df: pd.DataFrame,
                                  min_edge: float = 0.01,
                                  min_spread: float = 10.0) -> pd.DataFrame:
    """
    Find the best betting opportunities based on multi-book odds.

    Returns players where:
    1. Model gives positive edge vs consensus
    2. Significant odds spread exists across books (value opportunity)

    Args:
        predictions_df: DataFrame with predictions and multi-book odds
        min_edge: Minimum edge (model - market) to consider
        min_spread: Minimum odds spread % to consider

    Returns:
        DataFrame of value opportunities sorted by edge
    """
    if "multi_book_edge" not in predictions_df.columns:
        return pd.DataFrame()

    # Filter for value opportunities
    value_df = predictions_df[
        (predictions_df["multi_book_edge"] >= min_edge) &
        (predictions_df["value_spread_pct"] >= min_spread)
    ].copy()

    value_df = value_df.sort_values("multi_book_edge", ascending=False)

    return value_df[["player_name", "win_prob", "implied_prob_consensus",
                     "multi_book_edge", "odds_best", "odds_consensus",
                     "value_spread_pct", "num_books"]]
