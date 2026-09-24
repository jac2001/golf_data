"""Derive committed euro course-history tables from local DuckDB.

The DB is local-only, so anything the cloud needs must be derived here
and committed — same pattern as pred_R*.csv. Two outputs, keyed by
NORMALIZED COURSE NAME (DG's course_num is NOT stable: Le Golf National
has six different numbers across six editions; the name is the only
key that survives):

  data/euro_course_history/course_years.csv   one row per course-edition
  data/euro_course_history/player_course.csv  one row per (player, course)

Course history moves once a year per course, so a local run after
settling events keeps these fresh; the API only ever reads them.

Run: python3 scripts/features/build_euro_course_history.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "euro_course_history"


def main() -> None:
    con = duckdb.connect(str(PROJECT_ROOT / "data" / "golf_data.db"), read_only=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    years = con.execute("""
        with r as (
            select trim(lower(course_name)) as course_key, course_name,
                   calendar_year, event_name, course_par, score, sg_total,
                   player_name, fin_text
            from euro_rounds
            where course_name is not null and course_name != ''
        )
        select course_key, any_value(course_name) as course_name,
               calendar_year, any_value(event_name) as event_name,
               max(course_par) as par,
               round(avg(score), 2) as avg_score,
               count(*) as rounds,
               any_value(champion) as champion
        from r
        left join (
            select trim(lower(course_name)) as ck, calendar_year as cy,
                   any_value(player_name) as champion
            from euro_rounds where fin_text = '1'
            group by 1, 2
        ) c on c.ck = r.course_key and c.cy = r.calendar_year
        group by course_key, calendar_year
        order by course_key, calendar_year desc
    """).df()
    years.to_csv(OUT_DIR / "course_years.csv", index=False)

    players = con.execute("""
        select trim(lower(course_name)) as course_key,
               dg_id, any_value(player_name) as player_name,
               count(*) as rounds,
               round(avg(score - course_par), 2) as avg_vs_par,
               round(avg(sg_total), 2) as avg_sg,
               min(try_cast(replace(fin_text, 'T', '') as int)) as best_finish,
               max(calendar_year) as last_year
        from euro_rounds
        where course_name is not null and course_name != '' and dg_id is not null
        group by course_key, dg_id
    """).df()
    players.to_csv(OUT_DIR / "player_course.csv", index=False)

    print(f"{years['course_key'].nunique()} courses, {len(years)} editions -> course_years.csv")
    print(f"{len(players)} (player, course) rows -> player_course.csv")


if __name__ == "__main__":
    main()
