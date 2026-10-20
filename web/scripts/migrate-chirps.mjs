/**
 * migrate-chirps.mjs — tables for group chirps (docs/CHIRPS_DESIGN.md).
 * ======================================================================
 * Additive only (CREATE ... IF NOT EXISTS): safe to run more than once,
 * touches no existing table. Approved by Jack 2026-10-20.
 *
 *   node --env-file=.env.local scripts/migrate-chirps.mjs
 *
 * chirps          — one message in a group's thread for one tournament.
 *                   `card` is the frozen matchup snapshot it reacts to (built
 *                   server-side from what the sender could see; never a
 *                   hidden pick). Removed chirps keep their row (removed_at).
 * chirp_reactions — one row per (chirp, person, reaction); toggled.
 * chirp_reports   — "report this"; the group owner sees them.
 * chirp_reads     — when each person last opened each group's thread
 *                   (the unread badge).
 */

import { neon } from "@neondatabase/serverless";

const sql = neon(process.env.DATABASE_URL);

await sql`
  CREATE TABLE IF NOT EXISTS chirps (
    id             bigserial PRIMARY KEY,
    group_id       int NOT NULL,
    tournament_id  text NOT NULL,
    user_id        text NOT NULL,
    user_name      text NOT NULL,
    preset_id      text,                      -- null for a custom message
    text           text NOT NULL,
    card           jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    removed_at     timestamptz,
    removed_by     text
  )`;
await sql`CREATE INDEX IF NOT EXISTS chirps_thread ON chirps (group_id, tournament_id, created_at)`;

await sql`
  CREATE TABLE IF NOT EXISTS chirp_reactions (
    chirp_id    bigint NOT NULL,
    user_id     text NOT NULL,
    emoji       text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chirp_id, user_id, emoji)
  )`;

await sql`
  CREATE TABLE IF NOT EXISTS chirp_reports (
    id          bigserial PRIMARY KEY,
    chirp_id    bigint NOT NULL,
    user_id     text NOT NULL,
    reason      text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
  )`;

await sql`
  CREATE TABLE IF NOT EXISTS chirp_reads (
    group_id      int NOT NULL,
    user_id       text NOT NULL,
    last_read_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, user_id)
  )`;

// 2026-10-20 (review items 6, 8, 9), still additive:
// chirp_thread_reads — the read marker per group AND tournament, as the id of
//   the last chirp actually shown (chirp_reads was per group, so reading one
//   tour's thread cleared the other's, and a chirp arriving between the query
//   and the mark could be skipped).
// chirp_reports.resolved_* — the group owner's review of a report.
// one report per person per chirp.
await sql`
  CREATE TABLE IF NOT EXISTS chirp_thread_reads (
    group_id       int NOT NULL,
    tournament_id  text NOT NULL,
    user_id        text NOT NULL,
    last_id        bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (group_id, tournament_id, user_id)
  )`;
await sql`ALTER TABLE chirp_reports ADD COLUMN IF NOT EXISTS resolved_at timestamptz`;
await sql`ALTER TABLE chirp_reports ADD COLUMN IF NOT EXISTS resolved_by text`;
await sql`ALTER TABLE chirp_reports ADD COLUMN IF NOT EXISTS resolution text`;
await sql`CREATE UNIQUE INDEX IF NOT EXISTS chirp_reports_once ON chirp_reports (chirp_id, user_id)`;

const t = await sql`
  SELECT table_name FROM information_schema.tables
  WHERE table_name IN ('chirps', 'chirp_reactions', 'chirp_reports', 'chirp_reads', 'chirp_thread_reads') ORDER BY 1`;
console.log("chirp tables:", t.map(r => r.table_name).join(", "));
