#!/usr/bin/env python3
"""
Course Similarity Analysis

Calculates similarity between golf courses based on:
- Course characteristics (par, yardage, scoring difficulty)
- Hole composition (par 3/4/5 distribution)
- Course type from tournament_courses.json

Used to predict player performance at courses they haven't played
by using their performance at similar courses.

Usage:
    python scripts/features/course_similarity.py
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from scipy.spatial.distance import cosine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class CourseProfile:
    """Aggregated course characteristics for similarity matching."""
    course_name: str
    course_key: str
    course_type: str
    total_par: float
    total_yardage: float
    avg_scoring_diff: float  # Avg strokes over par per round
    par3_count: int
    par4_count: int
    par5_count: int
    avg_par3_yards: float
    avg_par4_yards: float
    avg_par5_yards: float
    hardest_hole_par: int
    easiest_hole_par: int
    # Derived features
    birdie_opportunity_score: float  # Based on par 5s and short par 4s
    accuracy_demand_score: float  # Based on tight fairways / small greens (proxy)


def load_course_characteristics(years: List[int] = None) -> pd.DataFrame:
    """Load and combine course characteristics from multiple years."""
    if years is None:
        years = [2023, 2024, 2025, 2026]

    frames = []
    for year in years:
        path = DATA_DIR / "course_characteristics" / f"all_courses_{year}.csv"
        if path.exists():
            df = pd.read_csv(path)
            df["year"] = year
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def load_tournament_course_mapping() -> Dict:
    """Load tournament-to-course mapping with course types."""
    path = DATA_DIR / "reference" / "tournament_courses.json"
    if not path.exists():
        return {}

    with open(path, "r") as f:
        data = json.load(f)

    return data.get("tournaments", {})


def normalize_course_key(name: str) -> str:
    """Normalize course name to a key."""
    import re
    if not name:
        return "unknown"
    text = str(name).strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def aggregate_course_profiles(char_df: pd.DataFrame, course_mapping: Dict) -> Dict[str, CourseProfile]:
    """Aggregate hole-level data to course profiles."""
    if char_df.empty:
        return {}

    # Build course type lookup from mapping
    course_type_lookup = {}
    for tournament_name, details in course_mapping.items():
        course_name = details.get("course", "")
        course_type = details.get("course_type", "unknown")
        course_type_lookup[normalize_course_key(course_name)] = course_type
        # Also add full name
        course_full = details.get("course_full", "")
        if course_full:
            course_type_lookup[normalize_course_key(course_full)] = course_type

    profiles = {}

    # Group by course
    for course_name, course_df in char_df.groupby("course_name"):
        course_key = normalize_course_key(course_name)

        # Get course type from mapping
        course_type = course_type_lookup.get(course_key, "unknown")

        # Use most recent year's data
        latest_year = course_df["year"].max()
        recent_df = course_df[course_df["year"] == latest_year]

        # Aggregate hole data
        total_par = recent_df["hole_par"].sum() if "hole_par" in recent_df else 72
        total_yardage = recent_df["hole_yards"].sum() if "hole_yards" in recent_df else 7200

        # Scoring difficulty
        if "scoring_diff" in recent_df.columns:
            avg_scoring_diff = recent_df["scoring_diff"].mean()
        else:
            avg_scoring_diff = 0.0

        # Par distribution
        par3_holes = recent_df[recent_df["hole_par"] == 3]
        par4_holes = recent_df[recent_df["hole_par"] == 4]
        par5_holes = recent_df[recent_df["hole_par"] == 5]

        par3_count = len(par3_holes)
        par4_count = len(par4_holes)
        par5_count = len(par5_holes)

        avg_par3_yards = par3_holes["hole_yards"].mean() if len(par3_holes) > 0 else 180
        avg_par4_yards = par4_holes["hole_yards"].mean() if len(par4_holes) > 0 else 430
        avg_par5_yards = par5_holes["hole_yards"].mean() if len(par5_holes) > 0 else 550

        # Hardest/easiest holes
        if "scoring_diff" in recent_df.columns and len(recent_df) > 0:
            hardest_idx = recent_df["scoring_diff"].idxmax()
            easiest_idx = recent_df["scoring_diff"].idxmin()
            hardest_hole_par = int(recent_df.loc[hardest_idx, "hole_par"])
            easiest_hole_par = int(recent_df.loc[easiest_idx, "hole_par"])
        else:
            hardest_hole_par = 4
            easiest_hole_par = 5

        # Birdie opportunity score (more par 5s + shorter par 4s = more birdies)
        birdie_opportunity = par5_count * 2 + max(0, (450 - avg_par4_yards) / 20)

        # Accuracy demand (longer par 3s, tighter scoring = more accuracy needed)
        accuracy_demand = (avg_par3_yards - 160) / 30 + abs(avg_scoring_diff) * 2

        profiles[course_key] = CourseProfile(
            course_name=course_name,
            course_key=course_key,
            course_type=course_type,
            total_par=total_par,
            total_yardage=total_yardage,
            avg_scoring_diff=avg_scoring_diff,
            par3_count=par3_count,
            par4_count=par4_count,
            par5_count=par5_count,
            avg_par3_yards=avg_par3_yards,
            avg_par4_yards=avg_par4_yards,
            avg_par5_yards=avg_par5_yards,
            hardest_hole_par=hardest_hole_par,
            easiest_hole_par=easiest_hole_par,
            birdie_opportunity_score=birdie_opportunity,
            accuracy_demand_score=accuracy_demand,
        )

    return profiles


def profile_to_vector(profile: CourseProfile) -> np.ndarray:
    """Convert course profile to feature vector for similarity calculation."""
    # Normalize features to similar scales
    return np.array([
        profile.total_yardage / 7500,  # Normalized yardage
        profile.avg_scoring_diff,  # Already small scale
        profile.par3_count / 4,  # Typically 4 par 3s
        profile.par4_count / 10,  # Typically 10 par 4s
        profile.par5_count / 4,  # Typically 4 par 5s
        profile.avg_par3_yards / 200,
        profile.avg_par4_yards / 450,
        profile.avg_par5_yards / 550,
        profile.birdie_opportunity_score / 10,
        profile.accuracy_demand_score / 5,
    ])


# Course type similarity weights (1.0 = same type, lower = less similar)
COURSE_TYPE_SIMILARITY = {
    ("links", "links"): 1.0,
    ("links", "links-style"): 0.8,
    ("links-style", "links-style"): 1.0,
    ("parkland", "parkland"): 1.0,
    ("parkland", "classic parkland"): 0.9,
    ("parkland", "florida parkland"): 0.8,
    ("parkland", "modern parkland"): 0.9,
    ("florida parkland", "florida parkland"): 1.0,
    ("desert", "desert"): 1.0,
    ("stadium", "stadium"): 1.0,
    ("parkland", "stadium"): 0.6,
    ("links", "desert"): 0.4,
    ("links", "parkland"): 0.5,
}


def get_type_similarity(type1: str, type2: str) -> float:
    """Get similarity score between two course types."""
    if type1 == type2:
        return 1.0

    # Check both orderings
    key1 = (type1.lower(), type2.lower())
    key2 = (type2.lower(), type1.lower())

    if key1 in COURSE_TYPE_SIMILARITY:
        return COURSE_TYPE_SIMILARITY[key1]
    if key2 in COURSE_TYPE_SIMILARITY:
        return COURSE_TYPE_SIMILARITY[key2]

    # Default moderate similarity
    return 0.5


def calculate_similarity(profile1: CourseProfile, profile2: CourseProfile) -> float:
    """Calculate similarity score between two courses (0-1, higher = more similar)."""
    # Vector-based similarity (characteristics)
    vec1 = profile_to_vector(profile1)
    vec2 = profile_to_vector(profile2)

    # Cosine similarity (1 - cosine distance)
    try:
        char_similarity = 1 - cosine(vec1, vec2)
    except:
        char_similarity = 0.5

    # Course type similarity
    type_similarity = get_type_similarity(profile1.course_type, profile2.course_type)

    # Combined score (70% characteristics, 30% type)
    return 0.7 * char_similarity + 0.3 * type_similarity


def find_similar_courses(
    target_course_key: str,
    profiles: Dict[str, CourseProfile],
    top_n: int = 5,
    min_similarity: float = 0.6,
) -> List[Tuple[str, float, CourseProfile]]:
    """Find courses most similar to the target course."""
    if target_course_key not in profiles:
        return []

    target_profile = profiles[target_course_key]
    similarities = []

    for course_key, profile in profiles.items():
        if course_key == target_course_key:
            continue

        sim = calculate_similarity(target_profile, profile)
        if sim >= min_similarity:
            similarities.append((course_key, sim, profile))

    # Sort by similarity descending
    similarities.sort(key=lambda x: x[1], reverse=True)

    return similarities[:top_n]


def get_player_similar_course_performance(
    player_id: int,
    target_course_key: str,
    course_perf_df: pd.DataFrame,
    profiles: Dict[str, CourseProfile],
    top_n_similar: int = 3,
) -> Optional[Dict]:
    """
    Estimate player's expected performance at a course using similar courses.

    Returns estimated SG stats based on weighted average of similar course performance.
    """
    similar_courses = find_similar_courses(target_course_key, profiles, top_n=top_n_similar)

    if not similar_courses:
        return None

    player_perf = course_perf_df[course_perf_df["player_id"] == player_id]

    if player_perf.empty:
        return None

    # Collect performance at similar courses
    weighted_sg_total = 0.0
    weighted_sg_ott = 0.0
    weighted_sg_app = 0.0
    weighted_sg_putt = 0.0
    total_weight = 0.0
    courses_used = []

    for course_key, similarity, profile in similar_courses:
        perf_at_course = player_perf[player_perf["course_key"] == course_key]

        if perf_at_course.empty:
            continue

        row = perf_at_course.iloc[0]

        sg_total = row.get("course_sg_total_weighted")
        if pd.isna(sg_total):
            continue

        # Weight by similarity and experience (more starts = more reliable)
        starts = row.get("starts", 1)
        weight = similarity * min(starts, 3) / 3  # Cap at 3 starts

        weighted_sg_total += sg_total * weight
        weighted_sg_ott += (row.get("course_sg_ott_weighted", 0) or 0) * weight
        weighted_sg_app += (row.get("course_sg_app_weighted", 0) or 0) * weight
        weighted_sg_putt += (row.get("course_sg_putt_weighted", 0) or 0) * weight
        total_weight += weight
        courses_used.append((profile.course_name, similarity, starts))

    if total_weight == 0:
        return None

    return {
        "estimated_sg_total": weighted_sg_total / total_weight,
        "estimated_sg_ott": weighted_sg_ott / total_weight,
        "estimated_sg_app": weighted_sg_app / total_weight,
        "estimated_sg_putt": weighted_sg_putt / total_weight,
        "similar_courses_used": courses_used,
        "confidence": min(total_weight / 2, 1.0),  # 0-1 confidence score
    }


def build_course_similarity_matrix(profiles: Dict[str, CourseProfile]) -> pd.DataFrame:
    """Build full similarity matrix between all courses."""
    course_keys = list(profiles.keys())
    n = len(course_keys)

    matrix = np.zeros((n, n))

    for i, key1 in enumerate(course_keys):
        for j, key2 in enumerate(course_keys):
            if i == j:
                matrix[i, j] = 1.0
            elif i < j:
                sim = calculate_similarity(profiles[key1], profiles[key2])
                matrix[i, j] = sim
                matrix[j, i] = sim

    return pd.DataFrame(matrix, index=course_keys, columns=course_keys)


def save_course_profiles(profiles: Dict[str, CourseProfile], output_path: Path):
    """Save course profiles to CSV."""
    rows = []
    for key, profile in profiles.items():
        rows.append({
            "course_key": key,
            "course_name": profile.course_name,
            "course_type": profile.course_type,
            "total_par": profile.total_par,
            "total_yardage": profile.total_yardage,
            "avg_scoring_diff": profile.avg_scoring_diff,
            "par3_count": profile.par3_count,
            "par4_count": profile.par4_count,
            "par5_count": profile.par5_count,
            "avg_par3_yards": profile.avg_par3_yards,
            "avg_par4_yards": profile.avg_par4_yards,
            "avg_par5_yards": profile.avg_par5_yards,
            "birdie_opportunity_score": profile.birdie_opportunity_score,
            "accuracy_demand_score": profile.accuracy_demand_score,
        })

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} course profiles to {output_path}")


def main():
    """Build course profiles and similarity data."""
    print("Loading course characteristics...")
    char_df = load_course_characteristics()
    print(f"  Loaded {len(char_df)} hole records")

    print("Loading tournament-course mapping...")
    course_mapping = load_tournament_course_mapping()
    print(f"  Loaded {len(course_mapping)} tournament mappings")

    print("Aggregating course profiles...")
    profiles = aggregate_course_profiles(char_df, course_mapping)
    print(f"  Built {len(profiles)} course profiles")

    # Save profiles
    output_path = DATA_DIR / "processed" / "course_profiles.csv"
    save_course_profiles(profiles, output_path)

    # Build and save similarity matrix
    print("Building similarity matrix...")
    sim_matrix = build_course_similarity_matrix(profiles)
    sim_path = DATA_DIR / "processed" / "course_similarity_matrix.csv"
    sim_matrix.to_csv(sim_path)
    print(f"  Saved similarity matrix to {sim_path}")

    # Show example similar courses
    print("\nExample similar courses:")
    test_courses = ["riviera country club", "tpc sawgrass stadium course", "augusta national golf club"]
    for course_key in test_courses:
        if course_key in profiles:
            similar = find_similar_courses(course_key, profiles, top_n=3)
            print(f"\n  {profiles[course_key].course_name}:")
            for sim_key, sim_score, sim_profile in similar:
                print(f"    - {sim_profile.course_name}: {sim_score:.2f} ({sim_profile.course_type})")


if __name__ == "__main__":
    main()
