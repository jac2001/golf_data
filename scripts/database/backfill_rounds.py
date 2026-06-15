"""
Backfill r1/r2/r3/r4 round scores into the DuckDB leaderboards table.

Run once after adding the new columns to the schema. Safe to re-run —
uses INSERT OR REPLACE so existing rows get overwritten with correct values.

Usage:
    python scripts/database/backfill_rounds.py
"""
import sys
from pathlib import Path

# Allow running from any directory
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "database"))
sys.path.insert(0, str(ROOT / "scripts"))

from db import get_conn

DATA_DIR = ROOT / "data" / "historical"


def add_columns(conn) -> None:
    """Add round-score columns if they don't already exist."""
    for col in ("r1", "r2", "r3", "r4"):
        try:
            conn.execute(f"ALTER TABLE leaderboards ADD COLUMN IF NOT EXISTS {col} DOUBLE")
            print(f"  column {col}: ready")
        except Exception as e:
            print(f"  column {col}: {e}")


def backfill_year(conn, csv_path: Path) -> int:
    """
    Update leaderboards rows for one year using DuckDB's inline CSV reader.

    DuckDB can treat a CSV file as a table directly in SQL via read_csv_auto().
    We join it to the existing leaderboards table on the primary key
    (player_id, tournament_id) and set the four round columns.

    Returns the number of rows updated.
    """
    # Validate the CSV has the columns we need before touching DuckDB
    import pandas as pd
    sample = pd.read_csv(csv_path, nrows=0)
    required = {"player_id", "tournament_id", "r1_score", "r2_score", "r3_score", "r4_score"}
    if not required.issubset(set(sample.columns)):
        missing = required - set(sample.columns)
        print(f"  {csv_path.name}: skipping — missing columns {missing}")
        return 0

    csv_str = str(csv_path)

    # DuckDB UPDATE ... FROM lets us join a source table/view to set values.
    # read_csv_auto() streams the CSV as a virtual table — no temp tables needed.
    # TRY_CAST converts '-', 'nan', empty strings to NULL instead of erroring
    conn.execute(f"""
        UPDATE leaderboards
        SET
            r1 = TRY_CAST(src.r1_score AS DOUBLE),
            r2 = TRY_CAST(src.r2_score AS DOUBLE),
            r3 = TRY_CAST(src.r3_score AS DOUBLE),
            r4 = TRY_CAST(src.r4_score AS DOUBLE)
        FROM read_csv_auto('{csv_str}', header=true, all_varchar=true) AS src
        WHERE leaderboards.player_id    = src.player_id
          AND leaderboards.tournament_id = src.tournament_id
    """)

    # Count how many rows in this CSV matched existing leaderboard rows
    count = conn.execute(f"""
        SELECT COUNT(*)
        FROM leaderboards l
        JOIN read_csv_auto('{csv_str}', header=true, all_varchar=true) src
          ON l.player_id    = src.player_id
         AND l.tournament_id = src.tournament_id
        WHERE l.r1 IS NOT NULL
    """).fetchone()[0]

    return count


def main():
    csv_files = sorted(DATA_DIR.glob("leaderboards_20*.csv"))
    if not csv_files:
        print(f"No leaderboard CSVs found in {DATA_DIR}")
        return

    print(f"Found {len(csv_files)} leaderboard CSV files\n")

    with get_conn() as conn:
        print("Adding round-score columns to leaderboards table…")
        add_columns(conn)
        print()

        total = 0
        for csv_path in csv_files:
            print(f"  {csv_path.name}…", end=" ", flush=True)
            n = backfill_year(conn, csv_path)
            print(f"{n} rows updated")
            total += n

        print(f"\nDone — {total} total rows updated across {len(csv_files)} files")

        # Verify
        sample = conn.execute("""
            SELECT year, COUNT(*) as total,
                   SUM(CASE WHEN r1 IS NOT NULL THEN 1 ELSE 0 END) as with_rounds
            FROM leaderboards
            GROUP BY year ORDER BY year DESC LIMIT 5
        """).fetchdf()
        print("\nVerification (recent years):")
        print(sample.to_string(index=False))


if __name__ == "__main__":
    main()
