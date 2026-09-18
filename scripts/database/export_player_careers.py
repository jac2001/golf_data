#!/usr/bin/env python3
"""
Export every player's career rows to one committed CSV
=======================================================
Runs the same join the /api/players/career endpoint runs in DuckDB —
leaderboards + pivoted SG stats + scoring averages — but for ALL players
at once, and writes data/processed/player_careers.csv (one row per
player-event, ~46K rows).

Why: the cloud has no golf_data.db, so career pages either showed
nothing or (bare-CSV fallback) showed results without any SG columns.
This file makes the full career — SG included — a repo artifact the
Render deploy carries, no runtime DB needed.

Freshness: post_tournament.py calls this after every Sunday settle, so
the Monday push updates it automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "player_careers.csv"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_conn  # noqa: E402


def main() -> None:
    with get_conn(read_only=True) as conn:
        df = conn.execute("""
            WITH sg AS (
                SELECT player_id, tournament_id,
                    AVG(CASE WHEN stat_id = '2567' THEN stat_value END) AS sg_total,
                    AVG(CASE WHEN stat_id = '2568' THEN stat_value END) AS sg_ott,
                    AVG(CASE WHEN stat_id = '2569' THEN stat_value END) AS sg_app,
                    AVG(CASE WHEN stat_id = '2570' THEN stat_value END) AS sg_arg,
                    AVG(CASE WHEN stat_id = '2564' THEN stat_value END) AS sg_putt,
                    AVG(CASE WHEN stat_id = '2674' THEN stat_value END) AS sg_t2g,
                    AVG(CASE WHEN stat_id = '101'  THEN stat_value END) AS driving_dist,
                    AVG(CASE WHEN stat_id = '102'  THEN stat_value END) AS driving_acc,
                    AVG(CASE WHEN stat_id = '103'  THEN stat_value END) AS gir_pct,
                    AVG(CASE WHEN stat_id = '130'  THEN stat_value END) AS scrambling
                FROM tournament_stats
                GROUP BY player_id, tournament_id
            ),
            form AS (
                SELECT player_id, tournament_id,
                    AVG(CASE WHEN stat_id = '120' THEN stat_value END) AS scoring_avg,
                    AVG(CASE WHEN stat_id = '108' THEN stat_value END) AS birdie_pct
                FROM form_stats
                GROUP BY player_id, tournament_id
            )
            SELECT
                l.player_id, l.player_name,
                l.tournament_id, l.tournament_name, l.year,
                l.position, l.to_par, l.total_score, l.earnings, l.rounds_played,
                l.r1, l.r2, l.r3, l.r4,
                sg.sg_total, sg.sg_ott, sg.sg_app, sg.sg_arg, sg.sg_putt, sg.sg_t2g,
                sg.driving_dist, sg.driving_acc, sg.gir_pct, sg.scrambling,
                form.scoring_avg, form.birdie_pct
            FROM leaderboards l
            LEFT JOIN sg   ON sg.player_id = l.player_id AND sg.tournament_id = l.tournament_id
            LEFT JOIN form ON form.player_id = l.player_id AND form.tournament_id = l.tournament_id
            -- Ascending so each week's settle APPENDS rows: git stores the
            -- weekly update as a small text delta instead of rewriting 18MB.
            ORDER BY l.year ASC, l.tournament_id ASC, l.player_name
        """).fetchdf()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    sg_cov = df["sg_total"].notna().mean() * 100
    print(f"Wrote {len(df):,} player-event rows -> {OUT_PATH.relative_to(PROJECT_ROOT)} "
          f"({OUT_PATH.stat().st_size / 1e6:.1f} MB, SG coverage {sg_cov:.0f}%)")


if __name__ == "__main__":
    main()
