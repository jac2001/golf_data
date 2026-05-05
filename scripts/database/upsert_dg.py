#!/usr/bin/env python3
"""
Upsert all DataGolf CSV files into DuckDB.

Reads from data/datagolf/ and inserts (or replaces on conflict) into:
  dg_players, dg_rankings, dg_decompositions, dg_pre_tournament,
  dg_fantasy, dg_matchups, dg_hole_stats

Usage:
    python scripts/database/upsert_dg.py           # all tables
    python scripts/database/upsert_dg.py --table dg_rankings
"""
from pathlib import Path
import sys
import argparse
import pandas as pd
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.database.db import get_conn

DG_DIR = PROJECT_ROOT / "data" / "datagolf"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _upsert(conn, table: str, df: pd.DataFrame, pk_cols: list[str]) -> int:
    """Register df as a temp view, then INSERT OR REPLACE into table."""
    conn.register("_upsert_src", df)
    cols = ", ".join(df.columns)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({cols}) SELECT {cols} FROM _upsert_src")
    conn.unregister("_upsert_src")
    return len(df)


def _load(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"  [SKIP] {path.name} not found")
        return None
    df = pd.read_csv(path)
    return df


# ---------------------------------------------------------------------------
# per-table upsert functions
# ---------------------------------------------------------------------------

def upsert_players(conn):
    df = _load(DG_DIR / "dg_player_list.csv")
    if df is None:
        return
    df = df[["dg_id", "player_name", "country", "country_code", "amateur"]].copy()
    n = _upsert(conn, "dg_players", df, ["dg_id"])
    print(f"  dg_players: {n} rows upserted")


def upsert_rankings(conn):
    rankings = _load(DG_DIR / "dg_rankings_latest.csv")
    skills   = _load(DG_DIR / "dg_skill_ratings_latest.csv")
    if rankings is None:
        return

    today = str(date.today())
    # Extract snapshot_date from last_updated (date portion)
    if "last_updated" in rankings.columns:
        rankings["snapshot_date"] = rankings["last_updated"].str[:10].fillna(today)
    else:
        rankings["snapshot_date"] = today

    # Merge skill ratings if available
    if skills is not None:
        skill_cols = {
            "dg_skill_total": "sg_total",
            "dg_skill_ott":   "sg_ott",
            "dg_skill_app":   "sg_app",
            "dg_skill_arg":   "sg_arg",
            "dg_skill_putt":  "sg_putt",
            "dg_skill_dist":  "driving_dist",
            "dg_skill_acc":   "driving_acc",
        }
        skills_renamed = skills[["dg_id"] + list(skill_cols)].rename(columns=skill_cols)
        rankings = rankings.merge(skills_renamed, on="dg_id", how="left")
    else:
        for col in ["sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt", "driving_dist", "driving_acc"]:
            rankings[col] = None

    keep = [
        "dg_id", "snapshot_date", "player_name", "datagolf_rank", "dg_skill_estimate",
        "owgr_rank", "country", "am", "primary_tour",
        "sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt",
        "driving_dist", "driving_acc", "last_updated",
    ]
    df = rankings[[c for c in keep if c in rankings.columns]].copy()
    # Add any missing columns as None
    for c in keep:
        if c not in df.columns:
            df[c] = None
    df = df[keep]

    n = _upsert(conn, "dg_rankings", df, ["dg_id", "snapshot_date"])
    print(f"  dg_rankings: {n} rows upserted")


def upsert_decompositions(conn):
    df = _load(DG_DIR / "dg_decompositions_latest.csv")
    if df is None:
        return

    keep = [
        "dg_id", "event_name", "last_updated", "player_name",
        "baseline_pred", "final_pred", "course_fit_delta", "std_deviation",
        "course_history_adjustment", "course_experience_adjustment",
        "total_course_history_adjustment",
        "driving_accuracy_adjustment", "driving_distance_adjustment",
        "cf_approach_comp", "cf_short_comp", "other_fit_adjustment",
        "total_fit_adjustment", "timing_adjustment",
        "strokes_gained_category_adjustment", "true_sg_adjustments",
        "age_adjustment", "country_adjustment",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in keep:
        if c not in df.columns:
            df[c] = None
    df = df[keep]

    n = _upsert(conn, "dg_decompositions", df, ["dg_id", "event_name", "last_updated"])
    print(f"  dg_decompositions: {n} rows upserted")


def upsert_pre_tournament(conn):
    df = _load(DG_DIR / "dg_pre_tournament_latest.csv")
    if df is None:
        return

    keep = [
        "dg_id", "player_name", "country", "model", "event_name",
        "win", "top_5", "top_10", "top_20", "make_cut",
        "sample_size", "last_updated",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in keep:
        if c not in df.columns:
            df[c] = None
    df = df[keep]

    n = _upsert(conn, "dg_pre_tournament", df, ["dg_id", "model", "event_name"])
    print(f"  dg_pre_tournament: {n} rows upserted")


def upsert_fantasy(conn):
    df = _load(DG_DIR / "dg_fantasy_draftkings_latest.csv")
    if df is None:
        return

    keep = [
        "dg_id", "site", "event_name", "player_name",
        "salary", "proj_points_total", "proj_points_scoring", "proj_points_finish",
        "proj_ownership", "std_dev", "value", "r1_teetime", "last_updated",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in keep:
        if c not in df.columns:
            df[c] = None
    df = df[keep]

    n = _upsert(conn, "dg_fantasy", df, ["dg_id", "site", "event_name"])
    print(f"  dg_fantasy: {n} rows upserted")


def upsert_matchups(conn):
    df = _load(DG_DIR / "dg_matchups_latest.csv")
    if df is None:
        return

    # CSV uses 'group', schema uses 'group_num'
    if "group" in df.columns:
        df = df.rename(columns={"group": "group_num"})

    keep = [
        "event_name", "round", "group_num", "teetime", "start_hole",
        "p1_dg_id", "p1_name", "p1_odds",
        "p2_dg_id", "p2_name", "p2_odds",
        "p3_dg_id", "p3_name", "p3_odds",
        "last_update",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in keep:
        if c not in df.columns:
            df[c] = None
    df = df[keep]

    n = _upsert(conn, "dg_matchups", df, ["event_name", "round", "group_num"])
    print(f"  dg_matchups: {n} rows upserted")


def upsert_hole_stats(conn):
    df = _load(DG_DIR / "dg_live_hole_stats_latest.csv")
    if df is None:
        return

    keep = [
        "event_name", "round_num", "course_key", "hole",
        "par", "yardage", "avg_score", "vs_par",
        "birdies", "pars", "bogeys", "doubles_or_worse", "eagles_or_better",
        "players_thru", "last_update",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in keep:
        if c not in df.columns:
            df[c] = None
    df = df[keep]

    n = _upsert(conn, "dg_hole_stats", df, ["event_name", "round_num", "course_key", "hole"])
    print(f"  dg_hole_stats: {n} rows upserted")


# ---------------------------------------------------------------------------
# convenience — called from fetch scripts after saving CSV
# ---------------------------------------------------------------------------

def upsert_table(table: str) -> None:
    """Open a connection and upsert a single table. Safe to call from any script."""
    fn = TABLE_MAP.get(table)
    if fn is None:
        raise ValueError(f"Unknown table: {table}. Valid: {list(TABLE_MAP)}")
    with get_conn() as conn:
        fn(conn)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

TABLE_MAP = {
    "dg_players":       upsert_players,
    "dg_rankings":      upsert_rankings,
    "dg_decompositions": upsert_decompositions,
    "dg_pre_tournament": upsert_pre_tournament,
    "dg_fantasy":       upsert_fantasy,
    "dg_matchups":      upsert_matchups,
    "dg_hole_stats":    upsert_hole_stats,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", choices=list(TABLE_MAP), help="Only upsert this table")
    args = parser.parse_args()

    targets = [args.table] if args.table else list(TABLE_MAP)

    print(f"Upserting {len(targets)} table(s) into golf_data.db...")
    with get_conn() as conn:
        for tbl in targets:
            TABLE_MAP[tbl](conn)

    print("Done.")


if __name__ == "__main__":
    main()
