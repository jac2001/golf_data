#!/usr/bin/env python3
"""
Consolidate Form Stats Into Player-Course Performance Features.

Builds two datasets:
1) Player-Tournament-Course rows (wide stats + outcomes)
2) Player-Course aggregates (how a player has actually performed on each course)

The aggregate table is intended for downstream prediction features and dashboard use.

Usage:
    python3 scripts/features/consolidate_course_form_stats.py --years 2024 2025 2026
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORM_PATTERN = "data/historical/form_stats_*.csv"
DEFAULT_LEADERBOARD_PATTERN = "data/historical/leaderboards_*.csv"
DEFAULT_TOURNAMENT_STATS_PATTERN = "data/historical/tournament_stats_*.csv"
DEFAULT_COURSE_MAP = "data/reference/tournament_courses.json"
DEFAULT_COURSE_CHARACTERISTICS_PATTERN = "data/course_characteristics/all_courses_*.csv"
DEFAULT_COURSE_TOUGHNESS = "data/reference/course_toughness_latest.csv"
DEFAULT_SCHEDULE = "data/raw/schedule_2026.csv"
DEFAULT_TOURNAMENT_OUT = "data/processed/player_tournament_course_form.csv"
DEFAULT_COURSE_OUT = "data/processed/player_course_performance.csv"

# Strokes Gained stat IDs from PGA Tour
SG_STAT_IDS = {
    "02567": "sg_total",
    "02568": "sg_ott",
    "02569": "sg_app",
    "02564": "sg_putt",
    "02674": "sg_t2g",
}


def normalize_text(value: object) -> str:
    """Normalize free text for stable matching."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    text = text.replace("&", "and")
    text = re.sub(r"\(\s*\d{4}\s*\)", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slugify_stat_name(value: str) -> str:
    text = normalize_text(value)
    return text.replace(" ", "_")


def parse_numeric(value: object) -> Optional[float]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return np.nan
    text = text.replace("%", "").replace("$", "")
    if text.upper() in {"E", "EVEN"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return np.nan


def clean_finish_position(value: object) -> Optional[float]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    text = str(value).strip().upper()
    if text in {"CUT", "MC", "DQ", "WD", "W/D"}:
        return np.nan
    text = text.replace("T", "")
    text = re.sub(r"[^0-9]", "", text)
    if not text:
        return np.nan
    try:
        return float(text)
    except ValueError:
        return np.nan


def clean_earnings(value: object) -> Optional[float]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text:
        return np.nan
    try:
        return float(text)
    except ValueError:
        return np.nan


def year_from_filename(path: Path, prefix: str) -> Optional[int]:
    match = re.search(rf"{re.escape(prefix)}_(\d{{4}})\.csv$", path.name)
    if not match:
        return None
    return int(match.group(1))


def resolve_years(pattern: str, prefix: str, years: Optional[List[int]]) -> List[int]:
    matches = sorted(PROJECT_ROOT.glob(pattern))
    available = sorted(
        {
            year
            for path in matches
            for year in [year_from_filename(path, prefix)]
            if year is not None
        }
    )
    if years:
        year_set = sorted(set(years))
        present = [y for y in year_set if y in available]
        missing = [y for y in year_set if y not in available]
        if missing:
            print(f"Warning: missing files for years: {missing}")
        return present
    return available


def read_form_stats(years: Iterable[int]) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for year in years:
        path = PROJECT_ROOT / f"data/historical/form_stats_{year}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue
        df["year"] = pd.to_numeric(df.get("year", year), errors="coerce").fillna(year).astype(int)
        df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
        df["stat_id"] = (
            df["stat_id"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.lstrip("0")
            .replace("", "0")
        )
        if "stat_value_numeric" not in df.columns:
            df["stat_value_numeric"] = df["stat_value"].map(parse_numeric)
        else:
            df["stat_value_numeric"] = df["stat_value_numeric"].map(parse_numeric)
            fallback = df["stat_value_numeric"].isna()
            if fallback.any():
                df.loc[fallback, "stat_value_numeric"] = df.loc[fallback, "stat_value"].map(parse_numeric)
        df["rank_numeric"] = pd.to_numeric(df.get("rank"), errors="coerce")
        frames.append(df)
        print(f"Loaded form stats {year}: {len(df):,} rows")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def pivot_form_stats(form_df: pd.DataFrame) -> pd.DataFrame:
    idx_cols = ["year", "tournament_id", "tournament_name", "player_id", "player_name"]
    work = form_df.copy()
    work["stat_slug"] = work["stat_name"].map(slugify_stat_name)
    work["stat_value_col"] = "stat_" + work["stat_id"] + "_" + work["stat_slug"]
    work["stat_rank_col"] = "rank_" + work["stat_id"]

    value_wide = (
        work.pivot_table(
            index=idx_cols,
            columns="stat_value_col",
            values="stat_value_numeric",
            aggfunc="mean",
        )
        .reset_index()
    )
    value_wide.columns.name = None

    rank_wide = (
        work.pivot_table(
            index=idx_cols,
            columns="stat_rank_col",
            values="rank_numeric",
            aggfunc="mean",
        )
        .reset_index()
    )
    rank_wide.columns.name = None

    merged = value_wide.merge(rank_wide, on=idx_cols, how="left")
    return merged


def read_tournament_stats(years: Iterable[int]) -> pd.DataFrame:
    """Read tournament-level Strokes Gained stats from tournament_stats files.

    Extracts SG metrics per player per tournament (using stat_component='Avg').
    Returns wide format with columns: year, tournament_id, tournament_name, player_id, player_name,
                                      sg_total, sg_ott, sg_app, sg_putt, sg_t2g
    """
    frames: List[pd.DataFrame] = []
    for year in years:
        path = PROJECT_ROOT / f"data/historical/tournament_stats_{year}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue

        # Normalize stat_id to match our SG_STAT_IDS keys
        df["stat_id"] = (
            df["stat_id"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.zfill(5)  # Pad to 5 digits (e.g., "2567" -> "02567")
        )

        # Filter to only SG stats and "Avg" component (the per-round average)
        sg_df = df[
            (df["stat_id"].isin(SG_STAT_IDS.keys())) &
            (df["stat_component"] == "Avg")
        ].copy()

        if sg_df.empty:
            continue

        sg_df["year"] = pd.to_numeric(sg_df.get("year", year), errors="coerce").fillna(year).astype(int)
        sg_df["player_id"] = pd.to_numeric(sg_df["player_id"], errors="coerce")
        sg_df["stat_value"] = pd.to_numeric(sg_df["stat_value"], errors="coerce")
        sg_df["sg_column"] = sg_df["stat_id"].map(SG_STAT_IDS)

        # Pivot to wide format
        idx_cols = ["year", "tournament_id", "tournament_name", "player_id", "player_name"]
        pivoted = sg_df.pivot_table(
            index=idx_cols,
            columns="sg_column",
            values="stat_value",
            aggfunc="mean"
        ).reset_index()
        pivoted.columns.name = None

        frames.append(pivoted)
        print(f"Loaded tournament SG stats {year}: {len(pivoted):,} player-tournaments")

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    # Ensure all SG columns exist
    for sg_col in SG_STAT_IDS.values():
        if sg_col not in result.columns:
            result[sg_col] = np.nan

    return result


def read_leaderboards(years: Iterable[int]) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for year in years:
        path = PROJECT_ROOT / f"data/historical/leaderboards_{year}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue
        df["year"] = pd.to_numeric(df.get("year", year), errors="coerce").fillna(year).astype(int)
        df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
        df["finish_position"] = df["position"].map(clean_finish_position)
        pos_upper = df["position"].astype(str).str.upper()
        df["made_cut"] = ~pos_upper.isin(["CUT", "MC", "DQ", "WD", "W/D"])
        df["top_10"] = df["finish_position"].le(10).fillna(False)
        df["top_20"] = df["finish_position"].le(20).fillna(False)
        df["win"] = df["finish_position"].eq(1).fillna(False)
        df["to_par_numeric"] = df["to_par"].map(parse_numeric)
        df["earnings_numeric"] = df["earnings"].map(clean_earnings)
        frames.append(
            df[
                [
                    "year",
                    "tournament_id",
                    "player_id",
                    "position",
                    "finish_position",
                    "made_cut",
                    "top_10",
                    "top_20",
                    "win",
                    "to_par_numeric",
                    "earnings_numeric",
                    "rounds_played",
                ]
            ]
        )
        print(f"Loaded leaderboards {year}: {len(df):,} rows")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


@dataclass
class CourseInfo:
    course_name: str
    course_full_name: str
    course_type: str
    course_location: str


def load_course_lookup(course_map_path: Path) -> Dict[str, CourseInfo]:
    if not course_map_path.exists():
        return {}
    with course_map_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    tournaments = payload.get("tournaments", {})
    lookup: Dict[str, CourseInfo] = {}
    for t_name, details in tournaments.items():
        info = CourseInfo(
            course_name=details.get("course", "Unknown"),
            course_full_name=details.get("course_full", details.get("course", "Unknown")),
            course_type=details.get("course_type", "Unknown"),
            course_location=details.get("location", "Unknown"),
        )
        candidates = [t_name] + list(details.get("aliases", []))
        for candidate in candidates:
            key = normalize_text(candidate)
            if key and key not in lookup:
                lookup[key] = info
    return lookup


def load_schedule_name_lookup(schedule_path: Path) -> Dict[str, str]:
    if not schedule_path.exists():
        return {}
    df = pd.read_csv(schedule_path)
    if "tournament_id" not in df.columns or "tournament_name" not in df.columns:
        return {}
    schedule = (
        df[["tournament_id", "tournament_name"]]
        .dropna(subset=["tournament_id", "tournament_name"])
        .drop_duplicates(subset=["tournament_id"], keep="first")
    )
    return dict(zip(schedule["tournament_id"].astype(str), schedule["tournament_name"].astype(str)))


def load_course_toughness_lookup(path: Path) -> Dict[str, CourseInfo]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    needed = {"tournament_name", "course_name"}
    if not needed.issubset(df.columns):
        return {}

    grouped = df.dropna(subset=["tournament_name", "course_name"]).groupby("tournament_name")
    lookup: Dict[str, CourseInfo] = {}
    for tournament_name, grp in grouped:
        courses = sorted(set(grp["course_name"].astype(str).str.strip()))
        if not courses:
            continue
        if len(courses) == 1:
            course_label = courses[0]
            course_type = "unknown"
        else:
            course_label = " | ".join(courses)
            course_type = "multi-course"
        lookup[normalize_text(tournament_name)] = CourseInfo(
            course_name=course_label,
            course_full_name=course_label,
            course_type=course_type,
            course_location="Unknown",
        )
    return lookup


def load_course_characteristics_lookup(pattern: str) -> Dict[str, CourseInfo]:
    paths = sorted(PROJECT_ROOT.glob(pattern))
    if not paths:
        return {}
    frames: List[pd.DataFrame] = []
    for path in paths:
        try:
            df = pd.read_csv(path, usecols=["tournament_name", "course_name"])
            frames.append(df)
        except Exception:
            continue
    if not frames:
        return {}

    merged = pd.concat(frames, ignore_index=True).dropna(subset=["tournament_name", "course_name"])
    lookup: Dict[str, CourseInfo] = {}
    for tournament_name, grp in merged.groupby("tournament_name"):
        courses = sorted(set(grp["course_name"].astype(str).str.strip()))
        if not courses:
            continue
        if len(courses) == 1:
            course_label = courses[0]
            course_type = "unknown"
        else:
            course_label = " | ".join(courses)
            course_type = "multi-course"
        lookup[normalize_text(tournament_name)] = CourseInfo(
            course_name=course_label,
            course_full_name=course_label,
            course_type=course_type,
            course_location="Unknown",
        )
    return lookup


def attach_course_metadata(
    df: pd.DataFrame,
    course_lookup: Dict[str, CourseInfo],
    schedule_name_lookup: Dict[str, str],
    fallback_lookups: List[Dict[str, CourseInfo]],
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["tournament_id"] = out["tournament_id"].astype(str)
    out["schedule_tournament_name"] = out["tournament_id"].map(schedule_name_lookup)

    def resolve_course(row: pd.Series) -> CourseInfo:
        primary_key = normalize_text(row.get("tournament_name"))
        schedule_key = normalize_text(row.get("schedule_tournament_name"))
        if primary_key in course_lookup:
            return course_lookup[primary_key]
        if schedule_key in course_lookup:
            return course_lookup[schedule_key]
        for fallback_lookup in fallback_lookups:
            if primary_key in fallback_lookup:
                return fallback_lookup[primary_key]
            if schedule_key in fallback_lookup:
                return fallback_lookup[schedule_key]
        return CourseInfo(
            course_name="Unknown",
            course_full_name="Unknown",
            course_type="Unknown",
            course_location="Unknown",
        )

    resolved = out.apply(resolve_course, axis=1)
    out["course_name"] = [r.course_name for r in resolved]
    out["course_full_name"] = [r.course_full_name for r in resolved]
    out["course_type"] = [r.course_type for r in resolved]
    out["course_location"] = [r.course_location for r in resolved]
    out["course_key"] = out["course_full_name"].map(normalize_text).replace("", "unknown")
    return out


def weighted_average(series: pd.Series, weights: pd.Series) -> Optional[float]:
    numeric = pd.to_numeric(series, errors="coerce")
    mask = numeric.notna() & weights.notna()
    if not mask.any():
        return np.nan
    return float(np.average(numeric[mask], weights=weights[mask]))


def aggregate_player_course(tournament_df: pd.DataFrame) -> pd.DataFrame:
    if tournament_df.empty:
        return pd.DataFrame()

    work = tournament_df.copy()
    work["start_key"] = work["year"].astype(str) + "_" + work["tournament_id"].astype(str)
    min_year = int(work["year"].min())
    work["recency_weight"] = work["year"].astype(int) - min_year + 1

    group_cols = [
        "player_id",
        "player_name",
        "course_key",
        "course_name",
        "course_full_name",
        "course_type",
        "course_location",
    ]

    # Basic aggregations
    agg_dict = {
        "starts": ("start_key", "nunique"),
        "seasons_tracked": ("year", "nunique"),
        "made_cut_rate": ("made_cut", "mean"),
        "top_10_rate": ("top_10", "mean"),
        "top_20_rate": ("top_20", "mean"),
        "win_rate": ("win", "mean"),
        "avg_finish": ("finish_position", "mean"),
        "best_finish": ("finish_position", "min"),
        "avg_to_par": ("to_par_numeric", "mean"),
        "avg_earnings": ("earnings_numeric", "mean"),
        "last_season": ("year", "max"),
    }

    # Add SG column aggregations if present
    sg_cols = [c for c in SG_STAT_IDS.values() if c in work.columns]
    for sg_col in sg_cols:
        agg_dict[f"course_{sg_col}_avg"] = (sg_col, "mean")
        agg_dict[f"course_{sg_col}_rounds"] = (sg_col, "count")

    base = work.groupby(group_cols, as_index=False).agg(**agg_dict)

    # Form stats columns (from original form_stats pivoting)
    stat_cols = sorted([c for c in work.columns if c.startswith("stat_")])
    if stat_cols:
        stat_mean = work.groupby(group_cols, as_index=False)[stat_cols].mean()
        stat_mean = stat_mean.rename(columns={c: f"{c}_avg" for c in stat_cols})
        base = base.merge(stat_mean, on=group_cols, how="left")

    # Calculate recency-weighted averages and trends
    weighted_rows = []
    for keys, grp in work.groupby(group_cols, sort=False):
        row = {col: val for col, val in zip(group_cols, keys)}
        row["finish_weighted"] = weighted_average(grp["finish_position"], grp["recency_weight"])

        # Weighted SG stats
        for sg_col in sg_cols:
            row[f"course_{sg_col}_weighted"] = weighted_average(grp[sg_col], grp["recency_weight"])

        # Weighted form stats
        for col in stat_cols:
            row[f"{col}_weighted"] = weighted_average(grp[col], grp["recency_weight"])

        # Calculate SG trend (if multiple years of data)
        if "sg_total" in sg_cols and len(grp) >= 2:
            # Group by year and get avg SG per year
            yearly_sg = grp.groupby("year")["sg_total"].mean().sort_index()
            if len(yearly_sg) >= 2:
                # Calculate trend (positive = improving)
                years = np.array(yearly_sg.index)
                values = np.array(yearly_sg.values)
                # Simple linear regression for trend
                if len(years) >= 2 and not np.all(np.isnan(values)):
                    valid_mask = ~np.isnan(values)
                    if valid_mask.sum() >= 2:
                        x = years[valid_mask] - years[valid_mask].min()
                        y = values[valid_mask]
                        if len(x) >= 2:
                            slope = np.polyfit(x, y, 1)[0]
                            row["course_sg_trend"] = slope  # SG change per year
                            # Recent vs early comparison
                            recent_years = yearly_sg.iloc[-2:].mean() if len(yearly_sg) >= 2 else np.nan
                            early_years = yearly_sg.iloc[:2].mean() if len(yearly_sg) >= 2 else np.nan
                            if not np.isnan(recent_years) and not np.isnan(early_years):
                                row["course_sg_recent_vs_early"] = recent_years - early_years

        weighted_rows.append(row)

    if weighted_rows:
        weighted_df = pd.DataFrame(weighted_rows)
        base = base.merge(weighted_df, on=group_cols, how="left")

    base["made_cut_rate"] = base["made_cut_rate"].fillna(0.0)
    base["top_10_rate"] = base["top_10_rate"].fillna(0.0)
    base["top_20_rate"] = base["top_20_rate"].fillna(0.0)
    base["win_rate"] = base["win_rate"].fillna(0.0)
    return base.sort_values(["starts", "top_10_rate"], ascending=[False, False]).reset_index(drop=True)


def calculate_sg_vs_average(course_df: pd.DataFrame, tournament_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate how player's course SG compares to their overall season average.

    Adds columns like course_sg_total_vs_avg: positive = player performs better at this course.
    """
    if course_df.empty or tournament_df.empty:
        return course_df

    # Calculate each player's overall season average SG
    sg_cols = [c for c in SG_STAT_IDS.values() if c in tournament_df.columns]
    if not sg_cols:
        return course_df

    player_season_avg = (
        tournament_df.groupby(["player_id", "year"], as_index=False)[sg_cols]
        .mean()
    )

    # Calculate overall player average across all seasons (weighted by recency)
    min_year = int(player_season_avg["year"].min()) if not player_season_avg.empty else 2020
    player_season_avg["recency_weight"] = player_season_avg["year"].astype(int) - min_year + 1

    player_overall = []
    for player_id, grp in player_season_avg.groupby("player_id"):
        row = {"player_id": player_id}
        for sg_col in sg_cols:
            row[f"overall_{sg_col}_avg"] = weighted_average(grp[sg_col], grp["recency_weight"])
        player_overall.append(row)

    overall_df = pd.DataFrame(player_overall)
    if overall_df.empty:
        return course_df

    # Merge with course performance and calculate deltas
    result = course_df.merge(overall_df, on="player_id", how="left")

    for sg_col in sg_cols:
        course_col = f"course_{sg_col}_weighted"
        overall_col = f"overall_{sg_col}_avg"
        delta_col = f"course_{sg_col}_vs_avg"

        if course_col in result.columns and overall_col in result.columns:
            result[delta_col] = result[course_col] - result[overall_col]

    return result


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate form stats into player-course performance tables.")
    parser.add_argument("--years", nargs="*", type=int, help="Years to process (default: all available form_stats_YYYY.csv)")
    parser.add_argument("--form-pattern", default=DEFAULT_FORM_PATTERN, help=f"Glob pattern for form stats (default: {DEFAULT_FORM_PATTERN})")
    parser.add_argument("--leaderboard-pattern", default=DEFAULT_LEADERBOARD_PATTERN, help=f"Glob pattern for leaderboards (default: {DEFAULT_LEADERBOARD_PATTERN})")
    parser.add_argument("--tournament-stats-pattern", default=DEFAULT_TOURNAMENT_STATS_PATTERN, help=f"Glob pattern for tournament SG stats (default: {DEFAULT_TOURNAMENT_STATS_PATTERN})")
    parser.add_argument("--course-map", default=DEFAULT_COURSE_MAP, help=f"Tournament-course mapping JSON (default: {DEFAULT_COURSE_MAP})")
    parser.add_argument("--course-characteristics-pattern", default=DEFAULT_COURSE_CHARACTERISTICS_PATTERN, help=f"Glob pattern for course characteristics fallback (default: {DEFAULT_COURSE_CHARACTERISTICS_PATTERN})")
    parser.add_argument("--course-toughness-path", default=DEFAULT_COURSE_TOUGHNESS, help=f"Course toughness CSV fallback for tournament->course mapping (default: {DEFAULT_COURSE_TOUGHNESS})")
    parser.add_argument("--schedule-path", default=DEFAULT_SCHEDULE, help=f"Schedule CSV for ID->name fallback (default: {DEFAULT_SCHEDULE})")
    parser.add_argument("--tournament-output", default=DEFAULT_TOURNAMENT_OUT, help=f"Output path for tournament-level table (default: {DEFAULT_TOURNAMENT_OUT})")
    parser.add_argument("--course-output", default=DEFAULT_COURSE_OUT, help=f"Output path for player-course aggregate table (default: {DEFAULT_COURSE_OUT})")
    args = parser.parse_args()

    years = resolve_years(args.form_pattern, "form_stats", args.years)
    if not years:
        raise SystemExit("No form stats files found for requested years.")
    print(f"Years selected: {years}")

    form_long = read_form_stats(years=years)
    if form_long.empty:
        raise SystemExit("No form stats rows loaded.")
    print(f"Form stats rows: {len(form_long):,}")

    form_wide = pivot_form_stats(form_long)
    print(f"Player-tournament stat rows: {len(form_wide):,}")

    leaderboard_years = resolve_years(args.leaderboard_pattern, "leaderboards", years)
    leaderboard_df = read_leaderboards(leaderboard_years)
    if leaderboard_df.empty:
        print("Warning: no leaderboard files found for selected years. Outcome columns will be empty.")
        merged = form_wide.copy()
    else:
        merged = form_wide.merge(
            leaderboard_df,
            on=["year", "tournament_id", "player_id"],
            how="left",
        )
        for col in ["made_cut", "top_10", "top_20", "win"]:
            if col in merged.columns:
                merged[col] = merged[col].astype("boolean").fillna(False).astype(bool)

    # Read tournament SG stats and merge
    tournament_stats_years = resolve_years(args.tournament_stats_pattern, "tournament_stats", years)
    sg_df = read_tournament_stats(tournament_stats_years)
    if not sg_df.empty:
        print(f"Tournament SG stats rows: {len(sg_df):,}")
        # Merge SG data with form data
        sg_cols = [c for c in SG_STAT_IDS.values() if c in sg_df.columns]
        merge_cols = ["year", "tournament_id", "player_id"]
        sg_subset = sg_df[merge_cols + sg_cols].drop_duplicates(subset=merge_cols)
        merged = merged.merge(sg_subset, on=merge_cols, how="left")
        print(f"Merged SG stats - players with SG data: {merged[sg_cols[0]].notna().sum():,}")
    else:
        print("Warning: no tournament SG stats found. SG columns will be empty.")

    course_lookup = load_course_lookup(PROJECT_ROOT / args.course_map)
    characteristics_lookup = load_course_characteristics_lookup(args.course_characteristics_pattern)
    fallback_lookup = load_course_toughness_lookup(PROJECT_ROOT / args.course_toughness_path)
    schedule_lookup = load_schedule_name_lookup(PROJECT_ROOT / args.schedule_path)
    merged = attach_course_metadata(
        merged,
        course_lookup=course_lookup,
        schedule_name_lookup=schedule_lookup,
        fallback_lookups=[characteristics_lookup, fallback_lookup],
    )

    tournament_out = PROJECT_ROOT / args.tournament_output
    course_out = PROJECT_ROOT / args.course_output
    ensure_parent(tournament_out)
    ensure_parent(course_out)

    merged.to_csv(tournament_out, index=False)
    print(f"Saved tournament-course table: {tournament_out} ({len(merged):,} rows)")

    course_df = aggregate_player_course(merged)

    # Calculate SG vs overall average (how player performs at this course vs their typical)
    if not sg_df.empty:
        course_df = calculate_sg_vs_average(course_df, merged)
        sg_cols_present = [c for c in course_df.columns if c.startswith("course_sg_") and "_vs_avg" in c]
        if sg_cols_present:
            print(f"Added course SG vs-average columns: {sg_cols_present}")

    course_df.to_csv(course_out, index=False)
    print(f"Saved player-course performance table: {course_out} ({len(course_df):,} rows)")

    # Summary stats for SG columns
    sg_course_cols = [c for c in course_df.columns if c.startswith("course_sg_")]
    if sg_course_cols:
        sg_data_count = course_df[sg_course_cols[0]].notna().sum()
        print(f"Players with course SG data: {sg_data_count:,}")

    unknown_courses = int((merged["course_name"] == "Unknown").sum()) if "course_name" in merged.columns else 0
    print(f"Unknown course mappings: {unknown_courses:,}")
    if unknown_courses:
        unknown_counts = (
            merged.loc[merged["course_name"] == "Unknown", "tournament_name"]
            .value_counts()
            .head(10)
        )
        print("Top unmapped tournaments:")
        for name, count in unknown_counts.items():
            print(f"  - {name}: {count}")


if __name__ == "__main__":
    main()
