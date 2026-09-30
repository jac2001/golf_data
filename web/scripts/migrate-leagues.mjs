/**
 * Phase 2 schema — Let It Ride leagues (docs/PHASE2_DESIGN.md).
 * Idempotent: safe to re-run. Run from web/:
 *   node --env-file=.env.local scripts/migrate-leagues.mjs
 */
import { neon } from "@neondatabase/serverless";

const sql = neon(process.env.DATABASE_URL);

await sql`
  CREATE TABLE IF NOT EXISTS leagues (
    id               serial PRIMARY KEY,
    group_id         int  NOT NULL REFERENCES groups(id),
    name             text NOT NULL,
    season_start     date NOT NULL,
    season_end       date,
    tours            text[] NOT NULL DEFAULT '{pga,euro}',
    uses_per_player  int  NOT NULL DEFAULT 3 CHECK (uses_per_player > 0),
    players_per_week int  NOT NULL DEFAULT 3 CHECK (players_per_week > 0),
    status           text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'complete')),
    created_by       text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
  )`;

// One active season per group — the database refuses a second, so no
// race between two owners' clicks can create one.
await sql`
  CREATE UNIQUE INDEX IF NOT EXISTS one_active_league
  ON leagues (group_id) WHERE status = 'active'`;

await sql`
  CREATE TABLE IF NOT EXISTS league_picks (
    id            serial PRIMARY KEY,
    league_id     int  NOT NULL REFERENCES leagues(id),
    user_id       text NOT NULL,
    user_name     text NOT NULL DEFAULT '',
    tournament_id text NOT NULL,
    player_name   text NOT NULL,
    player_key    text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (league_id, user_id, tournament_id, player_key)
  )`;

// The two budget checks both filter on these — uses (per golfer, across
// tours) and golfers per slate (per tournament).
await sql`
  CREATE INDEX IF NOT EXISTS league_picks_uses
  ON league_picks (league_id, user_id, player_key)`;
await sql`
  CREATE INDEX IF NOT EXISTS league_picks_slate
  ON league_picks (league_id, user_id, tournament_id)`;

const tables = await sql`
  SELECT table_name FROM information_schema.tables
  WHERE table_name IN ('leagues', 'league_picks') ORDER BY table_name`;
console.log("ok:", tables.map(t => t.table_name).join(", "));
