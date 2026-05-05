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
    # -------------------------------------------------------------------------
    # dg_players: DataGolf master player list (static, all tours)
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dg_players (
        dg_id        INTEGER PRIMARY KEY,
        player_name  VARCHAR,
        country      VARCHAR,
        country_code VARCHAR,
        amateur      INTEGER
    )
    """,

    # -------------------------------------------------------------------------
    # dg_rankings: weekly snapshot of DG rankings + skill ratings combined
    # One row per player per snapshot date — tracks skill drift over time
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dg_rankings (
        dg_id              INTEGER,
        snapshot_date      VARCHAR,
        player_name        VARCHAR,
        datagolf_rank      INTEGER,
        dg_skill_estimate  DOUBLE,
        owgr_rank          INTEGER,
        country            VARCHAR,
        am                 INTEGER,
        primary_tour       VARCHAR,
        sg_total           DOUBLE,
        sg_ott             DOUBLE,
        sg_app             DOUBLE,
        sg_arg             DOUBLE,
        sg_putt            DOUBLE,
        driving_dist       DOUBLE,
        driving_acc        DOUBLE,
        last_updated       VARCHAR,
        PRIMARY KEY (dg_id, snapshot_date)
    )
    """,

    # -------------------------------------------------------------------------
    # dg_decompositions: per-tournament prediction breakdown
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dg_decompositions (
        dg_id                              INTEGER,
        event_name                         VARCHAR,
        last_updated                       VARCHAR,
        player_name                        VARCHAR,
        baseline_pred                      DOUBLE,
        final_pred                         DOUBLE,
        course_fit_delta                   DOUBLE,
        std_deviation                      DOUBLE,
        course_history_adjustment          DOUBLE,
        course_experience_adjustment       DOUBLE,
        total_course_history_adjustment    DOUBLE,
        driving_accuracy_adjustment        DOUBLE,
        driving_distance_adjustment        DOUBLE,
        cf_approach_comp                   DOUBLE,
        cf_short_comp                      DOUBLE,
        other_fit_adjustment               DOUBLE,
        total_fit_adjustment               DOUBLE,
        timing_adjustment                  DOUBLE,
        strokes_gained_category_adjustment DOUBLE,
        true_sg_adjustments                DOUBLE,
        age_adjustment                     DOUBLE,
        country_adjustment                 DOUBLE,
        PRIMARY KEY (dg_id, event_name, last_updated)
    )
    """,

    # -------------------------------------------------------------------------
    # dg_pre_tournament: pre-tournament win/top10/cut probabilities
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dg_pre_tournament (
        dg_id        INTEGER,
        player_name  VARCHAR,
        country      VARCHAR,
        model        VARCHAR,
        event_name   VARCHAR,
        win          DOUBLE,
        top_5        DOUBLE,
        top_10       DOUBLE,
        top_20       DOUBLE,
        make_cut     DOUBLE,
        sample_size  INTEGER,
        last_updated VARCHAR,
        PRIMARY KEY (dg_id, model, event_name)
    )
    """,

    # -------------------------------------------------------------------------
    # dg_fantasy: DFS salary + projected points per event per site
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dg_fantasy (
        dg_id                INTEGER,
        site                 VARCHAR,
        event_name           VARCHAR,
        player_name          VARCHAR,
        salary               INTEGER,
        proj_points_total    DOUBLE,
        proj_points_scoring  DOUBLE,
        proj_points_finish   DOUBLE,
        proj_ownership       DOUBLE,
        std_dev              DOUBLE,
        value                DOUBLE,
        r1_teetime           VARCHAR,
        last_updated         VARCHAR,
        PRIMARY KEY (dg_id, site, event_name)
    )
    """,

    # -------------------------------------------------------------------------
    # dg_matchups: round pairings + tee times + matchup odds
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dg_matchups (
        event_name   VARCHAR,
        round        INTEGER,
        group_num    INTEGER,
        teetime      VARCHAR,
        start_hole   INTEGER,
        p1_dg_id     INTEGER,
        p1_name      VARCHAR,
        p1_odds      VARCHAR,
        p2_dg_id     INTEGER,
        p2_name      VARCHAR,
        p2_odds      VARCHAR,
        p3_dg_id     INTEGER,
        p3_name      VARCHAR,
        p3_odds      VARCHAR,
        last_update  VARCHAR,
        PRIMARY KEY (event_name, round, group_num)
    )
    """,

    # -------------------------------------------------------------------------
    # dg_hole_stats: per-hole scoring distributions during live tournaments
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dg_hole_stats (
        event_name       VARCHAR,
        round_num        VARCHAR,
        course_key       VARCHAR,
        hole             INTEGER,
        par              INTEGER,
        yardage          INTEGER,
        avg_score        DOUBLE,
        vs_par           DOUBLE,
        birdies          INTEGER,
        pars             INTEGER,
        bogeys           INTEGER,
        doubles_or_worse INTEGER,
        eagles_or_better INTEGER,
        players_thru     INTEGER,
        last_update      VARCHAR,
        PRIMARY KEY (event_name, round_num, course_key, hole)
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
