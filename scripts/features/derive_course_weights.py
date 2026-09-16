#!/usr/bin/env python3
"""
Derive course-specific SG importance weights from real historical results,
for ONE course at a time — used for majors that rotate venues (U.S. Open,
Open Championship, PGA Championship), where pooling all historical rows
under one tournament_name would wrongly mix different courses' data.

For fixed-venue events (the vast majority of the Tour schedule), use
backfill_course_fit_weights.py instead — it batch-derives every course
in one pass since there's no venue-rotation ambiguity to worry about.

See scripts/features/course_weight_model.py for the regression methodology.

Writes results into DuckDB's course_fit_weights table (not a CSV) — that
table is the live source of truth read by the course-fit API endpoint.

Usage:
    # Single past edition
    python3 scripts/features/derive_course_weights.py \\
        --tournament-id R2018026 \\
        --tournament-name "U.S. Open" \\
        --course-name "Shinnecock Hills Golf Club"

    # Pool multiple editions of the same course (more data = more confidence)
    python3 scripts/features/derive_course_weights.py \\
        --tournament-id R2018026 R2004026 \\
        --tournament-name "U.S. Open" \\
        --course-name "Shinnecock Hills Golf Club"

    # Preview only, don't write to the database
    python3 scripts/features/derive_course_weights.py --tournament-id R2018026 \\
        --tournament-name "U.S. Open" --course-name "Shinnecock Hills Golf Club" --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "scripts" / "database"))
sys.path.insert(0, str(ROOT / "scripts" / "features"))

from db import get_conn  # noqa: E402
from course_weight_model import derive_weights, WEIGHT_COLS  # noqa: E402


def load_training_data() -> pd.DataFrame:
    """Load the newest master training CSV — same auto-detect pattern as train_final_models.py.

    This is a build artifact (refreshed whenever the feature merge runs), not a
    manually-curated lookup table — using it here for one-off historical
    derivation is fine. The live course-fit endpoint never reads it; it reads
    the course_fit_weights DB table this script writes to.
    """
    candidates = sorted(
        PROCESSED_DIR.glob("master_training_data_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No master_training_data_*.csv found in {PROCESSED_DIR}")
    return pd.read_csv(candidates[0], low_memory=False)


def upsert_weights(
    course_name: str,
    tournament_name: str,
    weights: dict,
    tournament_ids: list[str],
    dry_run: bool,
) -> None:
    """Add or update this course's row in DuckDB's course_fit_weights table."""
    record = {
        "course_name": course_name,
        "tournament_name": tournament_name,
        **{col: round(weights[col], 4) for col in WEIGHT_COLS},
        "n_players": weights["n_players"],
        "confidence": weights["confidence"],
        "source_tournament_ids": ",".join(tournament_ids),
        "is_default": False,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"  [DRY RUN] Would upsert into course_fit_weights: {record}")
        return

    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO course_fit_weights
                (course_name, tournament_name, ott_sg, app_sg, arg_sg, putt_sg,
                 n_players, confidence, source_tournament_ids, is_default, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record["course_name"], record["tournament_name"],
                record["ott_sg"], record["app_sg"], record["arg_sg"], record["putt_sg"],
                record["n_players"], record["confidence"],
                record["source_tournament_ids"], record["is_default"], record["computed_at"],
            ],
        )
    print(f"  Upserted '{course_name}' into course_fit_weights")


def main():
    parser = argparse.ArgumentParser(description="Derive course SG weights from historical results")
    parser.add_argument("--tournament-id", nargs="+", required=True,
                        help="One or more historical tournament_ids at this course (e.g. R2018026)")
    parser.add_argument("--tournament-name", required=True,
                        help="Tournament name as it appears in the schedule (e.g. 'U.S. Open')")
    parser.add_argument("--course-name", required=True,
                        help="Course name to store/match against (e.g. 'Shinnecock Hills Golf Club')")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to the DB")
    args = parser.parse_args()

    print("Loading training data...")
    df = load_training_data()

    print(f"Deriving weights for {args.course_name} from {args.tournament_id}...")
    sub = df[df["tournament_id"].isin(args.tournament_id)]
    weights = derive_weights(sub)

    print(f"  Players used: {weights['n_players']}  |  confidence: {weights['confidence']:.2f}")
    print(f"  Final weights: { {k: round(weights[k], 4) for k in WEIGHT_COLS} }")

    upsert_weights(args.course_name, args.tournament_name, weights, args.tournament_id, args.dry_run)


if __name__ == "__main__":
    main()
