"""
One-time (and re-runnable) CSV → DuckDB migration.

Loads all available year-based historical CSVs into data/golf_data.db.
Safe to re-run: each table is truncated and reloaded from scratch.

Usage:
    python scripts/database/migrate.py [--years 2020,2021,2022,2023,2024,2025,2026]
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

# Allow running directly from project root or scripts/database/
sys.path.insert(0, str(Path(__file__).parent))
from db import get_conn, DB_PATH

HISTORICAL_DIR = DB_PATH.parent / "historical"
PROCESSED_DIR  = DB_PATH.parent / "processed"
PLAYERS_DIR    = DB_PATH.parent / "players"
RANKINGS_DIR   = DB_PATH.parent / "rankings"

DEFAULT_YEARS = list(range(2016, 2027))


def migrate_tournament_stats(conn, years):
    print("\n[1/5] tournament_stats")
    conn.execute("DELETE FROM tournament_stats")
    loaded = 0
    for year in years:
        f = HISTORICAL_DIR / f"tournament_stats_{year}.csv"
        if not f.exists():
            print(f"  skip {year}: {f.name} not found")
            continue
        df = pd.read_csv(f)
        df["player_id"] = df["player_id"].astype(str)
        df["stat_id"]   = df["stat_id"].astype(str)
        df = df[["player_id", "player_name", "tournament_id", "tournament_name",
                 "year", "stat_id", "stat_name", "stat_component", "stat_value"]]
        conn.execute("INSERT INTO tournament_stats SELECT * FROM df")
        print(f"  {year}: {len(df):,} rows")
        loaded += len(df)
    print(f"  total: {loaded:,} rows")


def migrate_form_stats(conn, years):
    print("\n[2/5] form_stats")
    conn.execute("DELETE FROM form_stats")
    loaded = 0
    for year in years:
        f = HISTORICAL_DIR / f"form_stats_{year}.csv"
        if not f.exists():
            print(f"  skip {year}: {f.name} not found")
            continue
        df = pd.read_csv(f)
        df["player_id"] = df["player_id"].astype(str)
        df["stat_id"]   = df["stat_id"].astype(str)
        # Use stat_value_numeric (float) when available; drop the string stat_value
        if "stat_value_numeric" in df.columns:
            df = df.drop(columns=["stat_value"], errors="ignore")
            df = df.rename(columns={"stat_value_numeric": "stat_value"})
        keep = ["player_id", "player_name", "tournament_id", "tournament_name",
                "year", "stat_id", "stat_name", "stat_value"]
        df = df[keep]
        conn.execute("INSERT INTO form_stats SELECT * FROM df")
        print(f"  {year}: {len(df):,} rows")
        loaded += len(df)
    print(f"  total: {loaded:,} rows")


def migrate_leaderboards(conn, years):
    print("\n[3/5] leaderboards")
    conn.execute("DELETE FROM leaderboards")
    loaded = 0
    for year in years:
        f = HISTORICAL_DIR / f"leaderboards_{year}.csv"
        if not f.exists():
            print(f"  skip {year}: {f.name} not found")
            continue
        df = pd.read_csv(f)
        df["player_id"]   = df["player_id"].astype(str)
        df["total_score"] = pd.to_numeric(df["total_score"], errors="coerce")
        if "fedex_points" not in df.columns:
            df["fedex_points"] = None
        else:
            df["fedex_points"] = pd.to_numeric(df["fedex_points"], errors="coerce")
        cols = ["tournament_id", "tournament_name", "year", "player_id", "player_name",
                "position", "total_score", "to_par", "earnings", "rounds_played", "fedex_points"]
        df = df[cols]
        conn.execute("INSERT INTO leaderboards SELECT * FROM df")
        print(f"  {year}: {len(df):,} rows")
        loaded += len(df)
    print(f"  total: {loaded:,} rows")


def migrate_players(conn):
    print("\n[4/5] players")
    conn.execute("DELETE FROM players")

    # Load PGA players
    pf = next(PLAYERS_DIR.glob("pga_players_*.csv"), None)
    rf = next(RANKINGS_DIR.glob("owgr_*.csv"), None)

    if pf is None:
        print("  WARNING: no pga_players_*.csv found")
        return

    players_df = pd.read_csv(pf)
    players_df["player_id"] = players_df["player_id"].astype(str)

    # Merge in OWGR ranking points if available
    if rf is not None:
        owgr = pd.read_csv(rf)[["player_id", "world_rank_points"]].copy()
        owgr["player_id"] = owgr["player_id"].astype(str)
        players_df = players_df.merge(owgr, on="player_id", how="left", suffixes=("", "_owgr"))
    else:
        players_df["world_rank_points"] = None

    players_df["updated_at"] = pd.Timestamp.now()

    cols = ["player_id", "player_name", "first_name", "last_name", "country",
            "world_rank", "world_rank_points", "is_active", "updated_at"]
    for c in cols:
        if c not in players_df.columns:
            players_df[c] = None

    out = players_df[cols]
    conn.execute("INSERT INTO players SELECT * FROM out")
    print(f"  {len(players_df):,} players")


def migrate_course_performance(conn):
    print("\n[5/5] course_performance")
    conn.execute("DELETE FROM course_performance")

    cp_file = PROCESSED_DIR / "player_course_performance.csv"
    if not cp_file.exists():
        print(f"  skip: {cp_file.name} not found")
        return

    df = pd.read_csv(cp_file)
    df["player_id"] = df["player_id"].astype(str)

    col_map = {
        "course_sg_total_avg": "sg_total_avg",
        "course_sg_ott_avg":   "sg_ott_avg",
        "course_sg_app_avg":   "sg_app_avg",
        "course_sg_putt_avg":  "sg_putt_avg",
        "course_sg_t2g_avg":   "sg_t2g_avg",
    }
    df = df.rename(columns=col_map)

    target_cols = [
        "player_id", "player_name", "course_key", "course_name", "course_full_name",
        "course_type", "course_location", "starts", "seasons_tracked",
        "made_cut_rate", "top_10_rate", "top_20_rate", "win_rate",
        "avg_finish", "best_finish", "avg_to_par", "avg_earnings", "last_season",
        "sg_total_avg", "sg_ott_avg", "sg_app_avg", "sg_putt_avg", "sg_t2g_avg",
        "course_sg_total_vs_avg", "course_sg_ott_vs_avg", "course_sg_app_vs_avg",
        "course_sg_putt_vs_avg", "course_sg_t2g_vs_avg",
    ]
    for c in target_cols:
        if c not in df.columns:
            df[c] = None

    out = df[target_cols].drop_duplicates(subset=["player_id", "course_key"], keep="last")
    conn.execute("INSERT OR REPLACE INTO course_performance SELECT * FROM out")
    print(f"  {len(df):,} rows")


def main():
    parser = argparse.ArgumentParser(description="Migrate CSVs into DuckDB")
    parser.add_argument(
        "--years",
        default=",".join(str(y) for y in DEFAULT_YEARS),
        help="Comma-separated list of years to migrate (default: 2020-2026)",
    )
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",")]

    print(f"Migrating years: {years}")
    print(f"DB path: {DB_PATH}")

    with get_conn() as conn:
        # Ensure schema exists
        import schema as _schema
        for sql in _schema.CREATE_STATEMENTS:
            conn.execute(sql.strip())

        migrate_tournament_stats(conn, years)
        migrate_form_stats(conn, years)
        migrate_leaderboards(conn, years)
        migrate_players(conn)
        migrate_course_performance(conn)

    print("\nMigration complete.")
    print("\nVerification:")
    with get_conn(read_only=True) as conn:
        for t in ["tournament_stats", "form_stats", "leaderboards", "players", "course_performance"]:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n:,} rows")


if __name__ == "__main__":
    main()
