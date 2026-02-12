#!/usr/bin/env python3
"""
Enhanced Course Stats
=====================

Derives course-specific SG importance weights from hole-by-hole data.
Based on Data Golf methodology: estimates how much each skill (OTT, APP, ARG, PUTT)
matters at each course based on course characteristics.

Key metrics:
- sg_ott_importance: How much driving matters (length, fairway width proxy)
- sg_app_importance: How much approach play matters (GIR difficulty, par 3s)
- sg_arg_importance: How much short game matters (miss penalty, rough)
- sg_putt_importance: How much putting matters (green difficulty)

Usage:
    from enhanced_course_stats import get_course_sg_weights, calculate_weighted_fit

    weights = get_course_sg_weights('R2025002')
    fit_score = calculate_weighted_fit(player_sg, weights)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Tuple

# ============================================================================
# Manual Data Golf-style course profiles for known courses
# Values represent relative importance (0-1 scale) of each SG component
# Based on Data Golf course table research
# ============================================================================

COURSE_SG_PROFILES = {
    # American Express courses (2025)
    'pete dye stadium course': {
        'sg_ott_weight': 0.30,    # Medium-long, some water, rewards position
        'sg_app_weight': 0.35,    # Key at this course - tight targets, water
        'sg_arg_weight': 0.15,    # Pete Dye bunkers but lots of birdie looks
        'sg_putt_weight': 0.20,   # Poa annua greens, some slope
        'difficulty': 'medium',
        'notes': 'Pete Dye design, water hazards, island green 17th'
    },
    'la quinta country club': {
        'sg_ott_weight': 0.25,    # Shorter course, accuracy over distance
        'sg_app_weight': 0.30,    # Birdie-fest, need to attack pins
        'sg_ott_weight': 0.25,
        'sg_arg_weight': 0.20,    # Miss greens = need good scrambling
        'sg_putt_weight': 0.25,   # Lots of birdie putts to make
        'difficulty': 'easy',
        'notes': 'Birdie-fest course, very scoreable par 5s'
    },
    'nicklaus tournament course': {
        'sg_ott_weight': 0.28,    # Medium length, need to find fairways
        'sg_app_weight': 0.32,    # Target golf, good approach play rewarded
        'sg_arg_weight': 0.18,    # Some tricky short game situations
        'sg_putt_weight': 0.22,   # Nicklaus greens have contour
        'difficulty': 'medium',
        'notes': 'Jack Nicklaus design, strategic layout'
    },

    # Add more courses as needed...
    # Torrey Pines South (Farmers Insurance Open)
    'torrey pines south': {
        'sg_ott_weight': 0.35,    # Long course, need distance
        'sg_app_weight': 0.30,    # Long approaches, poa greens
        'sg_arg_weight': 0.15,    # Kikuyu rough is brutal
        'sg_putt_weight': 0.20,   # Poa annua greens
        'difficulty': 'hard',
        'notes': 'Major venue, long and demanding'
    },
    'torrey pines north': {
        'sg_ott_weight': 0.28,
        'sg_app_weight': 0.32,
        'sg_arg_weight': 0.18,
        'sg_putt_weight': 0.22,
        'difficulty': 'medium',
        'notes': 'Shorter but still demanding'
    },

    # Pebble Beach (AT&T Pro-Am)
    'pebble beach golf links': {
        'sg_ott_weight': 0.25,    # Accuracy > distance on tight holes
        'sg_app_weight': 0.35,    # Small greens, ocean wind
        'sg_arg_weight': 0.20,    # Miss green = tough up and downs
        'sg_putt_weight': 0.20,   # Poa annua, some sloped greens
        'difficulty': 'hard',
        'notes': 'Iconic coastal course, small greens, wind'
    },
    'spyglass hill': {
        'sg_ott_weight': 0.30,
        'sg_app_weight': 0.32,
        'sg_arg_weight': 0.18,
        'sg_putt_weight': 0.20,
        'difficulty': 'hard',
        'notes': 'Tough test in the trees'
    },

    # TPC Scottsdale (WM Phoenix Open)
    'tpc scottsdale stadium': {
        'sg_ott_weight': 0.32,    # Length helps on par 5s
        'sg_app_weight': 0.30,    # Need to attack for birdies
        'sg_arg_weight': 0.15,    # Desert course, some sand
        'sg_putt_weight': 0.23,   # Fast greens, lots of birdie putts
        'difficulty': 'medium',
        'notes': 'Birdie-fest, stadium atmosphere, fast greens'
    },

    # Riviera (Genesis Invitational)
    'riviera country club': {
        'sg_ott_weight': 0.28,    # Not super long but need position
        'sg_app_weight': 0.38,    # Kikuyu rough, small targets
        'sg_arg_weight': 0.18,    # Tough misses
        'sg_putt_weight': 0.16,   # Good putters thrive
        'difficulty': 'hard',
        'notes': 'Hogan Alley, kikuyu rough, small greens'
    },

    # Bay Hill (Arnold Palmer Invitational)
    'bay hill club': {
        'sg_ott_weight': 0.30,
        'sg_app_weight': 0.32,
        'sg_arg_weight': 0.18,
        'sg_putt_weight': 0.20,
        'difficulty': 'hard',
        'notes': 'Water everywhere, demanding finish'
    },

    # TPC Sawgrass (THE PLAYERS)
    'tpc sawgrass stadium': {
        'sg_ott_weight': 0.28,    # Position over distance
        'sg_app_weight': 0.35,    # Island green, target golf
        'sg_arg_weight': 0.17,    # Water hazards punish misses
        'sg_putt_weight': 0.20,   # TifEagle greens, firm
        'difficulty': 'hard',
        'notes': 'Fifth major, island 17th, water everywhere'
    },

    # Augusta National (Masters)
    'augusta national': {
        'sg_ott_weight': 0.32,    # Length matters on par 5s
        'sg_app_weight': 0.33,    # Approach to correct quadrant crucial
        'sg_arg_weight': 0.12,    # Tight lies around greens
        'sg_putt_weight': 0.23,   # Severe greens, speed matters
        'difficulty': 'hard',
        'notes': 'Masters, severe greens, slope and speed'
    },
}

# Optional course difficulty from PGA "toughest course" stats
TOUGHNESS_LATEST = Path("data/reference/course_toughness_latest.csv")


def load_course_toughness(path: Path = TOUGHNESS_LATEST) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        df["course_name_key"] = df["course_name"].astype(str).str.lower().str.strip()
        df["tournament_name_key"] = df["tournament_name"].astype(str).str.lower().str.strip()
        return df
    except Exception:
        return None


def get_course_toughness(course_name: str, tournament_name: str = None) -> Optional[Dict[str, Any]]:
    df = load_course_toughness()
    if df is None or df.empty or not course_name:
        return None
    ckey = course_name.lower().strip()
    if tournament_name:
        tkey = tournament_name.lower().strip()
        sub = df[(df["course_name_key"].str.contains(ckey, na=False)) &
                 (df["tournament_name_key"].str.contains(tkey, na=False))]
        if not sub.empty:
            row = sub.iloc[0]
            return row.to_dict()
    sub = df[df["course_name_key"].str.contains(ckey, na=False)]
    if sub.empty:
        return None
    return sub.iloc[0].to_dict()


def get_course_name_match(course_name: str) -> Optional[str]:
    """
    Find matching course in profiles using fuzzy matching.
    """
    if not course_name:
        return None

    course_lower = course_name.lower().strip()

    # Direct match
    if course_lower in COURSE_SG_PROFILES:
        return course_lower

    # Partial matching
    for profile_name in COURSE_SG_PROFILES.keys():
        # Check if profile name is contained in course name or vice versa
        if profile_name in course_lower or course_lower in profile_name:
            return profile_name

        # Check key words
        profile_words = set(profile_name.split())
        course_words = set(course_lower.split())
        if len(profile_words & course_words) >= 2:
            return profile_name

    return None


def derive_sg_weights_from_holes(hole_data: pd.DataFrame) -> Dict[str, float]:
    """
    Derive SG importance weights from hole-by-hole data.

    This uses heuristics based on:
    - Hole length distribution (OTT importance)
    - Par 3 difficulty (APP importance)
    - Bogey rate (ARG importance)
    - Birdie rate variance (PUTT importance)

    Args:
        hole_data: DataFrame with hole-level stats

    Returns:
        Dict with sg_*_weight values (sum to 1.0)
    """
    if hole_data.empty:
        return {
            'sg_ott_weight': 0.25,
            'sg_app_weight': 0.35,
            'sg_arg_weight': 0.20,
            'sg_putt_weight': 0.20,
        }

    # Parse hole_yards if string (remove commas)
    if hole_data['hole_yards'].dtype == object:
        hole_data = hole_data.copy()
        hole_data['hole_yards'] = hole_data['hole_yards'].astype(str).str.replace(',', '').astype(float)

    # 1. OTT importance: based on length and par 5 scoring
    avg_par4_length = hole_data[hole_data['hole_par'] == 4]['hole_yards'].mean()
    long_holes_pct = len(hole_data[hole_data['hole_yards'] > 450]) / len(hole_data)
    par5_eagle_rate = hole_data[hole_data['hole_par'] == 5]['eagles'].sum() / max(1, hole_data[hole_data['hole_par'] == 5]['birdies'].sum())

    # Longer courses and reachable par 5s = more OTT importance
    ott_score = 0.25 + (long_holes_pct * 0.15) + (par5_eagle_rate * 0.05)

    # 2. APP importance: based on GIR proxy (birdie rate on par 4s) and par 3 difficulty
    par3_data = hole_data[hole_data['hole_par'] == 3]
    par3_difficulty = par3_data['scoring_avg'].mean() - 3 if len(par3_data) > 0 else 0.1

    par4_birdie_rate = hole_data[hole_data['hole_par'] == 4]['birdies'].sum() / max(1,
        (hole_data[hole_data['hole_par'] == 4]['birdies'].sum() +
         hole_data[hole_data['hole_par'] == 4]['pars'].sum()))

    # Hard par 3s and lower birdie rate = more APP importance
    app_score = 0.30 + (par3_difficulty * 0.1) + ((0.25 - par4_birdie_rate) * 0.1)

    # 3. ARG importance: based on bogey/double rate (proxy for miss penalty)
    total_outcomes = (hole_data['birdies'].sum() + hole_data['pars'].sum() +
                     hole_data['bogeys'].sum() + hole_data['double_bogeys'].sum())
    bogey_plus_rate = (hole_data['bogeys'].sum() + hole_data['double_bogeys'].sum()) / max(1, total_outcomes)

    # Higher bogey rate = more ARG importance (need to scramble)
    arg_score = 0.15 + (bogey_plus_rate * 0.3)

    # 4. PUTT importance: based on birdie opportunity (more birdies = putting matters more)
    birdie_rate = hole_data['birdies'].sum() / max(1, total_outcomes)

    # Higher birdie rate = more putting importance (need to convert)
    putt_score = 0.18 + (birdie_rate * 0.2)

    # Normalize to sum to 1.0
    total = ott_score + app_score + arg_score + putt_score

    return {
        'sg_ott_weight': round(ott_score / total, 3),
        'sg_app_weight': round(app_score / total, 3),
        'sg_arg_weight': round(arg_score / total, 3),
        'sg_putt_weight': round(putt_score / total, 3),
    }


def get_course_sg_weights(
    tournament_id: str,
    course_name: str = None,
    use_manual_profiles: bool = True,
    tournament_name: str = None
) -> Dict[str, float]:
    """
    Get SG importance weights for a course.

    Priority:
    1. Manual Data Golf-style profiles (if available and use_manual_profiles=True)
    2. Derived from hole-by-hole data
    3. Default weights

    Args:
        tournament_id: Tournament ID to look up course data
        course_name: Optional course name for manual profile lookup
        use_manual_profiles: Whether to use manual profiles

    Returns:
        Dict with sg_*_weight values and metadata
    """
    result = {
        'sg_ott_weight': 0.25,
        'sg_app_weight': 0.35,
        'sg_arg_weight': 0.20,
        'sg_putt_weight': 0.20,
        'source': 'default',
        'course_name': course_name,
        'difficulty': 'medium',
    }

    # Try manual profile first
    if use_manual_profiles and course_name:
        profile_match = get_course_name_match(course_name)
        if profile_match:
            profile = COURSE_SG_PROFILES[profile_match]
            result.update({
                'sg_ott_weight': profile.get('sg_ott_weight', 0.25),
                'sg_app_weight': profile.get('sg_app_weight', 0.35),
                'sg_arg_weight': profile.get('sg_arg_weight', 0.20),
                'sg_putt_weight': profile.get('sg_putt_weight', 0.20),
                'source': 'manual_profile',
                'difficulty': profile.get('difficulty', 'medium'),
                'notes': profile.get('notes', ''),
            })
            return result

    # Try to derive from hole data
    char_dir = Path("data/course_characteristics")
    if char_dir.exists():
        # Look for tournament-specific file
        tid_lower = tournament_id.lower()
        files = [f for f in char_dir.glob("*.csv")
                if tid_lower in f.name.lower() and "profile" not in f.name.lower()]

        if not files:
            files = list(char_dir.glob("all_courses_*.csv"))

        if files:
            df = pd.read_csv(files[0])

            # Filter to tournament
            if 'tournament_id' in df.columns:
                df = df[df['tournament_id'].str.upper() == tournament_id.upper()]

            # If course name specified, filter further
            if course_name and 'course_name' in df.columns:
                course_match = df[df['course_name'].str.lower().str.contains(
                    course_name.lower().split()[0], na=False)]
                if len(course_match) > 0:
                    df = course_match

            if len(df) > 0:
                derived = derive_sg_weights_from_holes(df)
                result.update(derived)
                result['source'] = 'derived_from_holes'

                # Estimate difficulty from overall scoring
                avg_scoring_diff = df['scoring_avg'].mean() - df['hole_par'].mean()
                if avg_scoring_diff < -0.05:
                    result['difficulty'] = 'easy'
                elif avg_scoring_diff > 0.05:
                    result['difficulty'] = 'hard'
                else:
                    result['difficulty'] = 'medium'

    # If still default or derived, try toughness data for difficulty/notes
    toughness = None
    if course_name:
        toughness = get_course_toughness(course_name, tournament_name)
    if toughness and pd.notna(toughness.get("scoring_avg_to_par")):
        diff = float(toughness.get("scoring_avg_to_par"))
        if diff >= 1.0:
            result["difficulty"] = "hard"
        elif diff <= 0.2:
            result["difficulty"] = "easy"
        else:
            result["difficulty"] = "medium"
        result["notes"] = (result.get("notes", "") + f" | Toughness: {diff:+.2f}").strip(" |")
        result["source"] = result.get("source", "default") + "+toughness"

    return result


def get_tournament_sg_weights(tournament_id: str) -> Dict[str, Dict[str, float]]:
    """
    Get SG weights for all courses in a tournament.

    Returns:
        Dict mapping course_name -> weights dict
    """
    char_dir = Path("data/course_characteristics")
    result = {}

    if not char_dir.exists():
        return result

    # Load course data
    tid_lower = tournament_id.lower()
    files = [f for f in char_dir.glob("*.csv")
            if tid_lower in f.name.lower() and "profile" not in f.name.lower()]

    if not files:
        files = list(char_dir.glob("all_courses_*.csv"))

    if not files:
        return result

    df = pd.read_csv(files[0])

    if 'tournament_id' in df.columns:
        df = df[df['tournament_id'].str.upper() == tournament_id.upper()]

    if 'course_name' not in df.columns:
        return result

    # Get weights for each course
    for course_name in df['course_name'].unique():
        course_data = df[df['course_name'] == course_name]
        weights = get_course_sg_weights(tournament_id, course_name)
        result[course_name] = weights

    return result


def calculate_weighted_fit(
    player_sg: Dict[str, float],
    course_weights: Dict[str, float]
) -> float:
    """
    Calculate weighted course fit score.

    This multiplies player SG values by course-specific importance weights.
    A player who excels in areas the course rewards will score higher.

    Args:
        player_sg: Dict with sg_ott, sg_app, sg_arg, sg_putt values
        course_weights: Dict with sg_*_weight values

    Returns:
        Weighted fit score (can be negative, positive, or zero)
    """
    if not player_sg or not course_weights:
        return 0.0

    fit = 0.0

    # Map player SG to weights
    sg_mapping = {
        'sg_ott': 'sg_ott_weight',
        'sg_app': 'sg_app_weight',
        'sg_arg': 'sg_arg_weight',
        'sg_putt': 'sg_putt_weight',
    }

    for sg_col, weight_col in sg_mapping.items():
        sg_val = player_sg.get(sg_col, 0) or 0
        weight = course_weights.get(weight_col, 0.25)
        fit += sg_val * weight * 4  # Scale by 4 (since weights sum to 1)

    return round(fit, 3)


def calculate_fit_score_normalized(
    player_sg: Dict[str, float],
    course_weights: Dict[str, float]
) -> float:
    """
    Calculate normalized course fit score (0-100 scale).

    Converts raw weighted fit to a 0-100 scale where:
    - 50 = neutral fit (average player for course)
    - 70+ = strong fit
    - 30- = weak fit

    Args:
        player_sg: Dict with sg_ott, sg_app, sg_arg, sg_putt values
        course_weights: Dict with sg_*_weight values

    Returns:
        Normalized fit score (0-100)
    """
    raw_fit = calculate_weighted_fit(player_sg, course_weights)

    # Convert: raw_fit of -2 to +2 maps to 0-100
    # 0 raw -> 50 normalized
    # +1 raw -> 75 normalized
    # -1 raw -> 25 normalized
    normalized = 50 + (raw_fit * 25)

    return max(0, min(100, round(normalized, 1)))


def add_course_fit_features(
    df: pd.DataFrame,
    tournament_id: str,
    sg_cols: list = None
) -> pd.DataFrame:
    """
    Add course fit features to a DataFrame.

    Args:
        df: DataFrame with player data including SG columns
        tournament_id: Tournament ID to get course weights
        sg_cols: List of SG column names (default: ['sg_ott', 'sg_app', 'sg_arg', 'sg_putt'])

    Returns:
        DataFrame with added course_fit_* columns including:
        - fit_ott_contrib, fit_app_contrib, fit_arg_contrib, fit_putt_contrib
        - course_fit_total (sum of contributions)
        - course_fit_raw, course_fit_score (normalized 0-100)
    """
    if sg_cols is None:
        sg_cols = ['sg_ott', 'sg_app', 'sg_arg', 'sg_putt']

    # Get tournament course weights
    course_weights_all = get_tournament_sg_weights(tournament_id)

    if not course_weights_all:
        # Use default weights
        course_weights = get_course_sg_weights(tournament_id)
        course_weights_all = {'default': course_weights}

    # For multi-course tournaments, use average weights
    avg_weights = {
        'sg_ott_weight': np.mean([w.get('sg_ott_weight', 0.25) for w in course_weights_all.values()]),
        'sg_app_weight': np.mean([w.get('sg_app_weight', 0.35) for w in course_weights_all.values()]),
        'sg_arg_weight': np.mean([w.get('sg_arg_weight', 0.20) for w in course_weights_all.values()]),
        'sg_putt_weight': np.mean([w.get('sg_putt_weight', 0.20) for w in course_weights_all.values()]),
    }

    df = df.copy()

    # Calculate individual fit contributions (same formula as training in merge_all_historical_data.py)
    # These are player-specific: player's SG skill × course importance × 4
    df['fit_ott_contrib'] = df['sg_ott'].fillna(0) * avg_weights['sg_ott_weight'] * 4
    df['fit_app_contrib'] = df['sg_app'].fillna(0) * avg_weights['sg_app_weight'] * 4
    df['fit_arg_contrib'] = df.get('sg_arg', df.get('sg_t2g', pd.Series(0, index=df.index)) - df['sg_app'].fillna(0)).fillna(0) * avg_weights['sg_arg_weight'] * 4
    df['fit_putt_contrib'] = df['sg_putt'].fillna(0) * avg_weights['sg_putt_weight'] * 4

    # Total course fit (sum of all contributions)
    df['course_fit_total'] = (
        df['fit_ott_contrib'] +
        df['fit_app_contrib'] +
        df['fit_arg_contrib'] +
        df['fit_putt_contrib']
    )

    # Calculate fit for each player (legacy columns for display)
    fit_scores = []
    fit_raw = []

    for _, row in df.iterrows():
        player_sg = {col: row.get(col, 0) for col in sg_cols}

        raw = calculate_weighted_fit(player_sg, avg_weights)
        normalized = calculate_fit_score_normalized(player_sg, avg_weights)

        fit_raw.append(raw)
        fit_scores.append(normalized)

    df['course_fit_raw'] = fit_raw
    df['course_fit_score'] = fit_scores

    # Add the weights used
    for key, val in avg_weights.items():
        df[f'course_{key}'] = val

    return df


# ============================================================================
# Main / Testing
# ============================================================================

if __name__ == '__main__':
    print("Enhanced Course Stats Module")
    print("=" * 60)

    # Test with American Express
    print("\n1. Testing course weight derivation...")

    weights = get_tournament_sg_weights('R2025002')

    for course, w in weights.items():
        print(f"\n  {course}:")
        print(f"    OTT: {w['sg_ott_weight']:.1%} | APP: {w['sg_app_weight']:.1%}")
        print(f"    ARG: {w['sg_arg_weight']:.1%} | PUTT: {w['sg_putt_weight']:.1%}")
        print(f"    Source: {w['source']} | Difficulty: {w['difficulty']}")

    # Test manual profiles
    print("\n2. Testing manual profile lookup...")

    for test_course in ['Pete Dye Stadium Course', 'Torrey Pines South', 'Augusta National']:
        w = get_course_sg_weights('TEST', test_course)
        print(f"\n  {test_course}:")
        print(f"    OTT: {w['sg_ott_weight']:.1%} | APP: {w['sg_app_weight']:.1%}")
        print(f"    Source: {w['source']}")

    # Test fit calculation
    print("\n3. Testing fit calculation...")

    # Big hitter, good approach, weak short game
    bomber = {'sg_ott': 0.8, 'sg_app': 0.3, 'sg_arg': -0.2, 'sg_putt': 0.0}

    # Accurate, great putter, average distance
    scrambler = {'sg_ott': -0.1, 'sg_app': 0.2, 'sg_arg': 0.5, 'sg_putt': 0.6}

    long_course = {'sg_ott_weight': 0.35, 'sg_app_weight': 0.30, 'sg_arg_weight': 0.15, 'sg_putt_weight': 0.20}
    short_course = {'sg_ott_weight': 0.20, 'sg_app_weight': 0.35, 'sg_arg_weight': 0.25, 'sg_putt_weight': 0.20}

    print(f"\n  Bomber at long course: {calculate_fit_score_normalized(bomber, long_course)}")
    print(f"  Bomber at short course: {calculate_fit_score_normalized(bomber, short_course)}")
    print(f"  Scrambler at long course: {calculate_fit_score_normalized(scrambler, long_course)}")
    print(f"  Scrambler at short course: {calculate_fit_score_normalized(scrambler, short_course)}")

    print("\n✓ Module tests complete")
