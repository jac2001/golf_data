#!/usr/bin/env python3
"""
Course Fit Score Calculator
===========================

Calculates how well a player's strengths match a course's demands.

The score combines:
1. Course characteristics (from hole-by-hole data)
2. Player SG profile (OTT, APP, ARG, PUTT strengths)

A high score means the player's strengths align with what the course rewards.

Usage:
    from course_fit_score import calculate_course_fit
    
    fit_score = calculate_course_fit(
        player_sg={'sg_ott': 0.5, 'sg_app': 0.3, 'sg_putt': -0.1},
        course_profile={'birdie_pct': 25, 'bogey_pct': 12, 'avg_par5_scoring': -0.5}
    )
"""

import pandas as pd
import numpy as np
from pathlib import Path


def load_course_profile(tournament_id: str) -> dict:
    """
    Load course profile from characteristics data.
    
    Returns dict with course metrics like:
    - birdie_pct: Overall birdie percentage
    - bogey_pct: Overall bogey percentage  
    - scoring_diff: Average scoring vs par
    - par5_scoring: How much under par on par 5s (birdie opportunities)
    - par3_difficulty: How much over par on par 3s (requires accuracy)
    - long_hole_count: Number of holes > 450 yards (rewards length)
    """
    # Try to load from course characteristics file
    char_dir = Path("data/course_characteristics")

    if not char_dir.exists():
        print(f"  Course characteristics directory not found")
        return {}

    # Look for tournament-specific file (case-insensitive)
    tid_lower = tournament_id.lower()
    files = [f for f in char_dir.glob("*.csv") if tid_lower in f.name.lower() and "profile" not in f.name.lower()]

    if not files:
        # Try all courses file
        files = list(char_dir.glob("all_courses_*.csv"))

    if not files:
        print(f"  No course data found for {tournament_id}")
        return {}

    df = pd.read_csv(files[0])

    # Filter to this tournament if we have all courses (case-insensitive comparison)
    if 'tournament_id' in df.columns:
        df = df[df['tournament_id'].str.upper() == tournament_id.upper()]

    if len(df) == 0:
        return {}
    
    # Calculate course profile metrics
    profile = {
        # Scoring metrics
        'avg_scoring_diff': df['scoring_avg'].mean() - df['hole_par'].mean(),
        
        # Birdie/bogey rates (indicates course difficulty and opportunity)
        'birdie_pct': df['birdies'].sum() / (df['birdies'].sum() + df['pars'].sum() + 
                                              df['bogeys'].sum() + df['double_bogeys'].sum()) * 100,
        'bogey_pct': df['bogeys'].sum() / (df['birdies'].sum() + df['pars'].sum() + 
                                            df['bogeys'].sum() + df['double_bogeys'].sum()) * 100,
        
        # Par 5 scoring (birdie opportunities - rewards length + approach)
        'par5_scoring': df[df['hole_par'] == 5]['scoring_avg'].mean() - 5 if len(df[df['hole_par'] == 5]) > 0 else 0,
        
        # Par 3 difficulty (rewards iron accuracy)
        'par3_difficulty': df[df['hole_par'] == 3]['scoring_avg'].mean() - 3 if len(df[df['hole_par'] == 3]) > 0 else 0,
        
        # Long holes (rewards driving distance)
        'long_hole_pct': len(df[df['hole_yards'] > 450]) / len(df) * 100,
        
        # Short par 4s (rewards accuracy over distance)
        'short_par4_pct': len(df[(df['hole_par'] == 4) & (df['hole_yards'] < 400)]) / len(df) * 100,
    }
    
    return profile


def calculate_course_fit(player_sg: dict, course_profile: dict) -> float:
    """
    Calculate how well a player fits a course based on their SG profile.
    
    Args:
        player_sg: Dict with player's SG metrics (sg_ott, sg_app, sg_arg, sg_putt, sg_t2g)
        course_profile: Dict with course characteristics from load_course_profile()
    
    Returns:
        Fit score from 0-100 (higher = better fit)
    
    Logic:
    - Long courses (high long_hole_pct) reward sg_ott
    - High bogey_pct courses reward sg_arg and sg_putt (scrambling)
    - High birdie_pct courses reward sg_app (attack pins)
    - Par 5 birdie courses reward sg_ott + sg_app combo
    """
    if not player_sg or not course_profile:
        return 50.0  # Neutral score if missing data
    
    # Get player SG values (default to 0 if missing)
    sg_ott = player_sg.get('sg_ott', 0) or 0
    sg_app = player_sg.get('sg_app', 0) or 0
    sg_arg = player_sg.get('sg_arg', 0) or 0
    sg_putt = player_sg.get('sg_putt', 0) or 0
    
    fit_score = 50.0  # Start at neutral
    
    # FACTOR 1: Long holes favor big hitters
    # If course has many long holes, weight OTT more heavily
    long_pct = course_profile.get('long_hole_pct', 0)
    if long_pct > 40:  # More than 40% long holes
        fit_score += sg_ott * 10  # Big bonus for good drivers
    elif long_pct < 20:  # Short course
        fit_score += sg_app * 8  # Approach matters more
    
    # FACTOR 2: High bogey courses need scrambling
    # If course is difficult (high bogey %), reward ARG and putting
    bogey_pct = course_profile.get('bogey_pct', 10)
    if bogey_pct > 12:  # Tough course
        fit_score += (sg_arg + sg_putt) * 6  # Scrambling crucial
    
    # FACTOR 3: Birdie-fest courses reward attacking
    # If course gives up lots of birdies, reward approach play
    birdie_pct = course_profile.get('birdie_pct', 20)
    if birdie_pct > 25:  # Birdie-friendly
        fit_score += sg_app * 8  # Attack pins
        fit_score += sg_ott * 4  # Get in position
    
    # FACTOR 4: Par 5 scoring
    # If par 5s are very scoreable, reward length + approach
    par5_scoring = course_profile.get('par5_scoring', -0.3)
    if par5_scoring < -0.4:  # Very birdieable par 5s
        fit_score += (sg_ott + sg_app) * 5
    
    # FACTOR 5: Difficult par 3s
    # If par 3s play hard, reward iron play
    par3_diff = course_profile.get('par3_difficulty', 0.1)
    if par3_diff > 0.15:  # Hard par 3s
        fit_score += sg_app * 6
    
    # Normalize to 0-100 range
    fit_score = max(0, min(100, fit_score))
    
    return round(fit_score, 1)


def add_course_fit_to_predictions(predictions_df: pd.DataFrame, tournament_id: str) -> pd.DataFrame:
    """
    Add course fit scores to a predictions DataFrame.
    
    Args:
        predictions_df: DataFrame with player predictions and SG columns
        tournament_id: Tournament ID to load course profile
    
    Returns:
        DataFrame with added 'course_fit_score' column
    """
    # Load course profile
    course_profile = load_course_profile(tournament_id)
    
    if not course_profile:
        predictions_df['course_fit_score'] = 50.0  # Neutral if no data
        return predictions_df
    
    # Calculate fit score for each player
    fit_scores = []
    
    for _, row in predictions_df.iterrows():
        player_sg = {
            'sg_ott': row.get('sg_ott'),
            'sg_app': row.get('sg_app'),
            'sg_arg': row.get('sg_arg'),
            'sg_putt': row.get('sg_putt'),
        }
        
        fit = calculate_course_fit(player_sg, course_profile)
        fit_scores.append(fit)
    
    predictions_df['course_fit_score'] = fit_scores
    
    return predictions_df


# ============================================================================
# Example usage and testing
# ============================================================================

if __name__ == '__main__':
    print("Course Fit Score Calculator")
    print("=" * 60)
    
    # Test with sample data
    sample_player = {
        'sg_ott': 0.8,   # Elite driver
        'sg_app': 0.3,   # Good approach
        'sg_arg': -0.1,  # Weak around green
        'sg_putt': 0.0,  # Average putting
    }
    
    # Long course favoring bombers
    long_course = {
        'long_hole_pct': 50,
        'birdie_pct': 22,
        'bogey_pct': 10,
        'par5_scoring': -0.5,
        'par3_difficulty': 0.1,
    }
    
    # Short, tight course favoring accuracy
    tight_course = {
        'long_hole_pct': 15,
        'birdie_pct': 18,
        'bogey_pct': 15,
        'par5_scoring': -0.3,
        'par3_difficulty': 0.2,
    }
    
    fit_long = calculate_course_fit(sample_player, long_course)
    fit_tight = calculate_course_fit(sample_player, tight_course)
    
    print(f"\nSample Player (elite driver, weak scrambling):")
    print(f"  Fit at long course: {fit_long}")
    print(f"  Fit at tight course: {fit_tight}")
    print(f"\nExpected: Higher fit at long course")
