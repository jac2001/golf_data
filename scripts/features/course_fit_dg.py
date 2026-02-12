#!/usr/bin/env python3
"""
Course Fit Calculation using Data Golf Weights
==============================================

Uses empirical course SG importance weights from Data Golf to calculate
how well a player's game fits a specific course.

IMPORTANT: This uses SEASON SG stats (prior performance) - NOT per-tournament SG.
This avoids data leakage.

Course Fit Formula:
    fit_ott = player_season_sg_ott × course_ott_importance
    fit_app = player_season_sg_app × course_app_importance
    fit_arg = player_season_sg_arg × course_arg_importance
    fit_putt = player_season_sg_putt × course_putt_importance

    course_fit_total = fit_ott + fit_app + fit_arg + fit_putt

Higher course_fit_total = player's strengths align with course demands.

Usage:
    from scripts.features.course_fit_dg import add_course_fit_features

    df = add_course_fit_features(df)

Data Sources:
- Course weights: data/course_sg_weights.csv (from Data Golf)
- Player SG: season_sg_* columns in training data
"""

import pandas as pd
import numpy as np
import re
from pathlib import Path


# -----------------------------------------------------------------------------
# Tournament name normalization
# -----------------------------------------------------------------------------

# Map common tournament name variants to a canonical, normalized key
ALIAS_MAP = {
    # Sponsor/branding changes
    "shriners hospitals for children open": "shriners children s open",
    "mexico open at vidantaworld": "mexico open at vidanta",
    "oneflight myrtle beach classic": "myrtle beach classic",
    "atandt byron nelson": "the cj cup byron nelson",
    "rocket classic": "rocket mortgage classic",
    "safeway open": "fortinet championship",
    "sentry tournament of champions": "the sentry",
    "texas children s houston open": "cadence bank houston open",
    "hewlett packard enterprise houston open": "cadence bank houston open",
    "vivint houston open": "cadence bank houston open",
    "waste management phoenix open": "wm phoenix open",
    "the honda classic": "cognizant classic in the palm beaches",
    "the memorial tournament presented by nationwide": "the memorial tournament",
    # Alternate/shortened labels
    "houston open": "cadence bank houston open",
}


def normalize_tournament_name(name: str) -> str:
    """
    Normalize tournament names so course weight lookups handle variants.

    Steps:
    - Lowercase
    - Remove year-only parentheses (e.g., "(2021)")
    - Replace non-alphanumeric with spaces, collapse whitespace
    - Apply alias map for known sponsor/label variants
    """
    if not isinstance(name, str):
        return ""

    cleaned = re.sub(r"\(\s*\d{4}\s*\)", "", name)  # drop year suffixes
    cleaned = cleaned.replace("&", "and").lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return ""

    return ALIAS_MAP.get(cleaned, cleaned)


# Default weights for courses not in our mapping (average of all courses)
DEFAULT_WEIGHTS = {
    'ott_sg': 0.020,  # Average OTT importance
    'app_sg': 0.020,  # Average APP importance
    'arg_sg': 0.025,  # Average ARG importance
    'putt_sg': 0.005,  # Average putting importance
}


def load_course_weights() -> pd.DataFrame:
    """Load course SG weights from Data Golf mapping."""
    weights_path = Path("/Users/jacklegnon/Desktop/golf_data/data/course_sg_weights.csv")

    if not weights_path.exists():
        print(f"  ⚠️  Course weights file not found: {weights_path}")
        return pd.DataFrame()

    df = pd.read_csv(weights_path)
    print(f"  ✓ Loaded course weights for {len(df)} tournaments")
    return df


def calculate_course_fit(
    player_sg_ott: float,
    player_sg_app: float,
    player_sg_arg: float,
    player_sg_putt: float,
    course_ott_weight: float,
    course_app_weight: float,
    course_arg_weight: float,
    course_putt_weight: float
) -> dict:
    """
    Calculate course fit components and total.

    Player SG values are multiplied by course importance weights.
    Positive SG × positive weight = positive fit (good match).

    The weights from Data Golf indicate how much each SG component
    affects scoring at that course. Higher weight = more important.

    We normalize by scaling weights so they sum to ~1 for interpretability.
    """
    # Handle missing values
    if pd.isna(player_sg_ott):
        player_sg_ott = 0.0
    if pd.isna(player_sg_app):
        player_sg_app = 0.0
    if pd.isna(player_sg_arg):
        player_sg_arg = 0.0
    if pd.isna(player_sg_putt):
        player_sg_putt = 0.0

    # Scale weights (Data Golf weights are small, typically 0.01-0.10)
    # We multiply by 10 for more interpretable values
    scale = 10.0

    fit_ott = player_sg_ott * course_ott_weight * scale
    fit_app = player_sg_app * course_app_weight * scale
    fit_arg = player_sg_arg * course_arg_weight * scale
    fit_putt = player_sg_putt * course_putt_weight * scale

    fit_total = fit_ott + fit_app + fit_arg + fit_putt

    return {
        'dg_fit_ott': fit_ott,
        'dg_fit_app': fit_app,
        'dg_fit_arg': fit_arg,
        'dg_fit_putt': fit_putt,
        'dg_fit_total': fit_total
    }


def add_course_fit_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Data Golf course fit features to a DataFrame.

    Requires columns:
    - tournament_name: to look up course weights
    - season_sg_ott, season_sg_app, season_sg_t2g, season_sg_putt: player SG stats

    Note: We use season_sg_t2g - season_sg_app to estimate ARG since
    T2G = APP + ARG.

    Returns DataFrame with new columns:
    - dg_fit_ott, dg_fit_app, dg_fit_arg, dg_fit_putt, dg_fit_total
    - course_ott_weight, course_app_weight, course_arg_weight, course_putt_weight
    """
    print("  Calculating Data Golf course fit features...")

    # Load course weights
    course_weights = load_course_weights()

    if course_weights.empty:
        print("  ⚠️  No course weights available - using defaults")
        for col in ['dg_fit_ott', 'dg_fit_app', 'dg_fit_arg', 'dg_fit_putt', 'dg_fit_total']:
            df[col] = 0.0
        return df

    # Create weight lookup dict keyed by normalized tournament name
    weight_lookup = {}
    for _, row in course_weights.iterrows():
        normalized = normalize_tournament_name(row['tournament_name'])

        weight_lookup[normalized] = {
            'ott_sg': row['ott_sg'],
            'app_sg': row['app_sg'],
            'arg_sg': row['arg_sg'],
            'putt_sg': row['putt_sg']
        }

    # Calculate ARG from T2G - APP if we don't have direct ARG
    if 'season_sg_arg' not in df.columns:
        if 'season_sg_t2g' in df.columns and 'season_sg_app' in df.columns:
            df['season_sg_arg'] = df['season_sg_t2g'] - df['season_sg_app']
        else:
            df['season_sg_arg'] = 0.0

    # Initialize result columns
    fit_cols = ['dg_fit_ott', 'dg_fit_app', 'dg_fit_arg', 'dg_fit_putt', 'dg_fit_total']
    weight_cols = ['course_ott_weight', 'course_app_weight', 'course_arg_weight', 'course_putt_weight']

    for col in fit_cols + weight_cols:
        df[col] = np.nan

    # Track coverage
    matched = 0
    unmatched = set()

    # Calculate fit for each row
    for idx, row in df.iterrows():
        tournament = row.get('tournament_name', '')
        normalized = normalize_tournament_name(tournament)

        # Get weights for this tournament
        if normalized in weight_lookup:
            weights = weight_lookup[normalized]
            matched += 1
        else:
            weights = DEFAULT_WEIGHTS
            unmatched.add(tournament)

        # Store weights
        df.at[idx, 'course_ott_weight'] = weights['ott_sg']
        df.at[idx, 'course_app_weight'] = weights['app_sg']
        df.at[idx, 'course_arg_weight'] = weights['arg_sg']
        df.at[idx, 'course_putt_weight'] = weights['putt_sg']

        # Get player season SG stats
        sg_ott = row.get('season_sg_ott', 0.0)
        sg_app = row.get('season_sg_app', 0.0)
        sg_arg = row.get('season_sg_arg', 0.0)
        sg_putt = row.get('season_sg_putt', 0.0)

        # Calculate fit
        fit = calculate_course_fit(
            sg_ott, sg_app, sg_arg, sg_putt,
            weights['ott_sg'], weights['app_sg'],
            weights['arg_sg'], weights['putt_sg']
        )

        # Store results
        for col, val in fit.items():
            df.at[idx, col] = val

    # Report coverage
    total = len(df)
    print(f"  ✓ Course fit calculated:")
    print(f"    - Matched tournaments: {matched:,} ({matched/total*100:.1f}%)")
    print(f"    - Unmatched (using defaults): {total - matched:,}")

    if unmatched and len(unmatched) <= 10:
        print(f"    - Unmatched tournaments: {list(unmatched)[:5]}")

    return df


def get_course_fit_for_prediction(
    tournament_name: str,
    player_sg_ott: float,
    player_sg_app: float,
    player_sg_arg: float,
    player_sg_putt: float
) -> dict:
    """
    Calculate course fit for a single player-tournament prediction.

    Use this for real-time predictions where you need fit scores
    for a specific player at a specific tournament.
    """
    course_weights = load_course_weights()

    # Look up weights
    weights = DEFAULT_WEIGHTS.copy()
    if not course_weights.empty:
        normalized = normalize_tournament_name(tournament_name)

        # Rebuild lookup once to avoid repeated normalization in filters
        course_weights['normalized_name'] = course_weights['tournament_name'].apply(normalize_tournament_name)
        match = course_weights[course_weights['normalized_name'] == normalized]
        if len(match) > 0:
            row = match.iloc[0]
            weights = {
                'ott_sg': row['ott_sg'],
                'app_sg': row['app_sg'],
                'arg_sg': row['arg_sg'],
                'putt_sg': row['putt_sg']
            }

    return calculate_course_fit(
        player_sg_ott, player_sg_app, player_sg_arg, player_sg_putt,
        weights['ott_sg'], weights['app_sg'], weights['arg_sg'], weights['putt_sg']
    )


# ============================================================================
# CLI for testing
# ============================================================================

def main():
    """Test course fit calculation."""
    import argparse

    parser = argparse.ArgumentParser(description="Calculate course fit features")
    parser.add_argument("--test", action="store_true", help="Run test calculation")
    parser.add_argument("--tournament", type=str, help="Tournament name to test")

    args = parser.parse_args()

    if args.test:
        print("Testing course fit calculation...\n")

        # Load course weights
        weights = load_course_weights()
        print(f"\nCourse weight samples:")
        print(weights.head(10).to_string())

        # Test with a hypothetical player
        print("\n\nTest player (good ball striker, average putter):")
        print("  season_sg_ott = 0.5")
        print("  season_sg_app = 0.4")
        print("  season_sg_arg = 0.2")
        print("  season_sg_putt = -0.1")

        test_tournaments = [
            "The RSM Classic",  # Seaside - easier course
            "U.S. Open",        # Pinehurst - demands precision
            "Valspar Championship"  # Copperhead - tight fairways
        ]

        for tourney in test_tournaments:
            fit = get_course_fit_for_prediction(
                tourney,
                player_sg_ott=0.5,
                player_sg_app=0.4,
                player_sg_arg=0.2,
                player_sg_putt=-0.1
            )
            print(f"\n  {tourney}:")
            print(f"    fit_ott={fit['dg_fit_ott']:.3f}, fit_app={fit['dg_fit_app']:.3f}")
            print(f"    fit_arg={fit['dg_fit_arg']:.3f}, fit_putt={fit['dg_fit_putt']:.3f}")
            print(f"    TOTAL FIT: {fit['dg_fit_total']:.3f}")


if __name__ == "__main__":
    main()
