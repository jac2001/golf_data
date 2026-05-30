-- Golf Data — Supabase Schema
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New query)

-- ── tournaments ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tournaments (
    tournament_id   text PRIMARY KEY,
    week            integer,
    start_date      date,
    end_date        date,
    tournament_name text,
    tournament_type text,
    location        text,
    purse           text,
    winner_share    text,
    power_slug      text,
    updated_at      timestamptz DEFAULT now()
);

-- ── predictions ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predictions (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    tournament_id   text NOT NULL,
    player_id       bigint,
    player_name     text NOT NULL,
    world_rank      float,
    win_prob        float,
    top5_prob       float,
    top10_prob      float,
    top20_prob      float,
    cut_prob        float,
    season_sg_total float,
    model_vs_vegas_edge float,
    form_trend      float,
    odds_to_win     float,
    dk_odds_direction text,
    recommendation  text,
    this_week_ev    integer,
    explanation     text,
    uses_remaining  integer,
    updated_at      timestamptz DEFAULT now(),
    UNIQUE (tournament_id, player_name)
);

-- ── live_leaderboard ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS live_leaderboard (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    tournament_id   text NOT NULL,
    position        text,
    position_change integer,
    player_id       bigint,
    player_name     text NOT NULL,
    country         text,
    total           text,
    total_numeric   float,
    thru            text,
    current_round   integer,
    r1              float,
    r2              float,
    r3              float,
    r4              float,
    total_strokes   integer,
    made_cut        boolean,
    status          text,
    movement        text,
    odds_to_win     float,
    tee_time        text,
    updated_at      timestamptz DEFAULT now(),
    UNIQUE (tournament_id, player_name)
);

-- ── bets ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bets (
    recommendation_id   text PRIMARY KEY,
    tournament_id       text,
    recommended_at      timestamptz,
    bet_type            text,
    market              text,
    book                text,
    player_name         text,
    selection_label     text,
    odds_american       integer,
    book_prob           float,
    model_prob          float,
    edge_pts            float,
    ev_per_1            float,
    confidence          float,
    outcome_status      text,
    outcome_win         boolean,
    pnl_per_1           float,
    roi_pct             float,
    reasoning           text,
    graded_at           timestamptz,
    updated_at          timestamptz DEFAULT now()
);

-- ── recaps ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recaps (
    tournament_id   text PRIMARY KEY,
    tournament_name text,
    narrative       text,
    generated_at    timestamptz,
    updated_at      timestamptz DEFAULT now()
);

-- ── indexes for common query patterns ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_predictions_tid    ON predictions (tournament_id);
CREATE INDEX IF NOT EXISTS idx_leaderboard_tid    ON live_leaderboard (tournament_id);
CREATE INDEX IF NOT EXISTS idx_bets_tid           ON bets (tournament_id);
CREATE INDEX IF NOT EXISTS idx_bets_status        ON bets (outcome_status);
