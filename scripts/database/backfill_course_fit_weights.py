#!/usr/bin/env python3
"""
Batch-derive course SG importance weights for every FIXED-VENUE tournament
in our historical leaderboard data, and write them into DuckDB's
course_fit_weights table.

Run once to populate the table; safe to re-run (INSERT OR REPLACE).

Why this is safe to do in bulk (and derive_course_weights.py is not)
---------------------------------------------------------------------
For a fixed-venue event (Memorial, Colonial, Genesis, ...), every historical
row under that tournament_name really is the same course — pooling years
together is exactly the right thing to do, and it's fully automatic.

Majors that rotate venues (U.S. Open, Open Championship, PGA Championship)
are explicitly skipped here — pooling all their historical rows would mix
different courses' data together. Those need one-at-a-time derivation via
derive_course_weights.py, pointed at the specific historical tournament_id(s)
played at the SAME course.

Tournament names get resolved to their actual course name first (via
tournament_courses.json — the same resolution the API endpoint uses), then
GROUPED by course before deriving. This matters because sponsor-renamed
events (e.g. "Waste Management Phoenix Open" / "WM Phoenix Open") are the
same physical course under different names across years — pooling them
gives one larger, more confident estimate instead of two smaller, splintered
ones, and guarantees the stored key matches what the API looks up by.

Usage:
    python3 scripts/database/backfill_course_fit_weights.py
    python3 scripts/database/backfill_course_fit_weights.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "scripts" / "database"))
sys.path.insert(0, str(ROOT / "scripts" / "features"))

from db import get_conn  # noqa: E402
from course_weight_model import (  # noqa: E402
    derive_weights, is_rotating_venue, load_course_mapping,
    resolve_course_name, WEIGHT_COLS,
)


def load_training_data() -> pd.DataFrame:
    candidates = sorted(
        PROCESSED_DIR.glob("master_training_data_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No master_training_data_*.csv found in {PROCESSED_DIR}")
    return pd.read_csv(candidates[0], low_memory=False)


def main():
    parser = argparse.ArgumentParser(description="Batch-derive course SG weights for fixed-venue events")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Loading training data...")
    df = load_training_data()

    print("Loading distinct tournament names from DuckDB leaderboards...")
    with get_conn(read_only=True) as conn:
        names = conn.execute(
            "SELECT DISTINCT tournament_name FROM leaderboards WHERE tournament_name IS NOT NULL"
        ).df()["tournament_name"].tolist()

    print(f"Found {len(names)} distinct tournament names")

    # Group tournament names by their RESOLVED course — this is what makes
    # sponsor-renamed events pool together instead of splintering.
    course_mapping = load_course_mapping()
    names_by_course: dict[str, list[str]] = defaultdict(list)
    skipped_rotating = 0

    for name in names:
        if is_rotating_venue(name):
            skipped_rotating += 1
            continue
        resolved = resolve_course_name(name, course_mapping) or name
        names_by_course[resolved].append(name)

    print(f"Resolved into {len(names_by_course)} distinct courses "
          f"(skipped {skipped_rotating} rotating-venue major names)\n")

    derived, skipped_thin = 0, 0
    conn = None if args.dry_run else get_conn()

    for course_name, tournament_names in sorted(names_by_course.items()):
        sub = df[df["tournament_name"].isin(tournament_names)]
        if sub.empty:
            continue

        try:
            weights = derive_weights(sub)
        except ValueError:
            skipped_thin += 1
            continue

        # Use whichever tournament name is most common in the data as the
        # display label (sponsor names rotate; pick the dominant one).
        display_name = sub["tournament_name"].value_counts().idxmax()

        record = {
            "course_name": course_name,
            "tournament_name": display_name,
            **{col: round(weights[col], 4) for col in WEIGHT_COLS},
            "n_players": weights["n_players"],
            "confidence": weights["confidence"],
            "source_tournament_ids": ",".join(sorted(sub["tournament_id"].astype(str).unique())),
            "is_default": False,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

        if args.dry_run:
            names_note = f" (pooled: {tournament_names})" if len(tournament_names) > 1 else ""
            print(f"  [DRY RUN] {course_name}: n={weights['n_players']} conf={weights['confidence']:.2f} "
                  f"{ {k: round(weights[k], 4) for k in WEIGHT_COLS} }{names_note}")
        else:
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
        derived += 1

    if conn is not None:
        conn.close()

    print(f"\nDone — derived {derived} courses, skipped {skipped_rotating} rotating-venue "
          f"majors (derive those individually), skipped {skipped_thin} with too little data.")


if __name__ == "__main__":
    main()
