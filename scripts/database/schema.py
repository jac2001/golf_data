"""
DuckDB schema creation for golf_data.db.
Run once (or idempotently) to ensure all tables exist.

Usage:
    python scripts/database/schema.py
"""
from db import get_conn


CREATE_STATEMENTS = [
    # -------------------------------------------------------------------------
    # tournament_stats: per-tournament per-player SG stat components
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS tournament_stats (
        player_id        VARCHAR,
        player_name      VARCHAR,
        tournament_id    VARCHAR,
        tournament_name  VARCHAR,
        year             INTEGER,
        stat_id          VARCHAR,
        stat_name        VARCHAR,
        stat_component   VARCHAR,
        stat_value       DOUBLE,
        PRIMARY KEY (player_id, tournament_id, stat_id, stat_component)
    )
    """,

    # -------------------------------------------------------------------------
    # form_stats: per-tournament per-player rolling/seasonal stats
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS form_stats (
        player_id        VARCHAR,
        player_name      VARCHAR,
        tournament_id    VARCHAR,
        tournament_name  VARCHAR,
        year             INTEGER,
        stat_id          VARCHAR,
        stat_name        VARCHAR,
        stat_value       DOUBLE,
        PRIMARY KEY (player_id, tournament_id, stat_id)
    )
    """,

    # -------------------------------------------------------------------------
    # leaderboards: final finishing positions per player per tournament
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS leaderboards (
        tournament_id    VARCHAR,
        tournament_name  VARCHAR,
        year             INTEGER,
        player_id        VARCHAR,
        player_name      VARCHAR,
        position         VARCHAR,
        total_score      DOUBLE,
        to_par           VARCHAR,
        earnings         VARCHAR,
        rounds_played    INTEGER,
        fedex_points     DOUBLE,
        PRIMARY KEY (player_id, tournament_id)
    )
    """,

    # -------------------------------------------------------------------------
    # players: current player roster + world rankings
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS players (
        player_id        VARCHAR PRIMARY KEY,
        player_name      VARCHAR,
        first_name       VARCHAR,
        last_name        VARCHAR,
        country          VARCHAR,
        world_rank       INTEGER,
        world_rank_points DOUBLE,
        is_active        BOOLEAN,
        updated_at       TIMESTAMP
    )
    """,

    # -------------------------------------------------------------------------
    # tournaments: tournament metadata by year
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS tournaments (
        tournament_id    VARCHAR,
        year             INTEGER,
        tournament_name  VARCHAR,
        course           VARCHAR,
        location         VARCHAR,
        purse            DOUBLE,
        tournament_type  VARCHAR,
        start_date       VARCHAR,
        PRIMARY KEY (tournament_id, year)
    )
    """,

    # -------------------------------------------------------------------------
    # picks: weekly fantasy lineup picks + results
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS picks (
        season              VARCHAR NOT NULL,
        week                INTEGER NOT NULL,
        tournament_id       VARCHAR,
        tournament          VARCHAR,
        pick_date           DATE,
        player_name         VARCHAR NOT NULL,
        result              VARCHAR,
        fedex_points        INTEGER,
        model_rank          INTEGER,
        opening_odds        VARCHAR,
        opening_implied_prob DOUBLE,
        updated_at          TIMESTAMP DEFAULT current_timestamp,
        PRIMARY KEY (season, week, player_name)
    )
    """,

    # -------------------------------------------------------------------------
    # conversation_log: assistant Q&A history for context injection
    # -------------------------------------------------------------------------
    """
    CREATE SEQUENCE IF NOT EXISTS conversation_log_id_seq;
    CREATE TABLE IF NOT EXISTS conversation_log (
        id               INTEGER DEFAULT nextval('conversation_log_id_seq'),
        timestamp        TIMESTAMP NOT NULL,
        tournament_id    VARCHAR,
        phase            VARCHAR,
        question         TEXT NOT NULL,
        response_short   VARCHAR(400),
        response_full    TEXT,
        PRIMARY KEY (id)
    )
    """,

    # -------------------------------------------------------------------------
    # course_performance: per-player per-course historical stats
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS course_performance (
        player_id              VARCHAR,
        player_name            VARCHAR,
        course_key             VARCHAR,
        course_name            VARCHAR,
        course_full_name       VARCHAR,
        course_type            VARCHAR,
        course_location        VARCHAR,
        starts                 INTEGER,
        seasons_tracked        INTEGER,
        made_cut_rate          DOUBLE,
        top_10_rate            DOUBLE,
        top_20_rate            DOUBLE,
        win_rate               DOUBLE,
        avg_finish             DOUBLE,
        best_finish            DOUBLE,
        avg_to_par             DOUBLE,
        avg_earnings           DOUBLE,
        last_season            INTEGER,
        sg_total_avg           DOUBLE,
        sg_ott_avg             DOUBLE,
        sg_app_avg             DOUBLE,
        sg_putt_avg            DOUBLE,
        sg_t2g_avg             DOUBLE,
        course_sg_total_vs_avg DOUBLE,
        course_sg_ott_vs_avg   DOUBLE,
        course_sg_app_vs_avg   DOUBLE,
        course_sg_putt_vs_avg  DOUBLE,
        course_sg_t2g_vs_avg   DOUBLE,
        PRIMARY KEY (player_id, course_key)
    )
    """,
]


def create_schema():
    with get_conn() as conn:
        for sql in CREATE_STATEMENTS:
            conn.execute(sql.strip())
    print("Schema created / verified in golf_data.db")


if __name__ == "__main__":
    create_schema()
