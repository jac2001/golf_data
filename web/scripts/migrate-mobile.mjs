/**
 * migrate-mobile.mjs — tables for the mobile-first work (docs/MOBILE_FIRST_DESIGN.md).
 * ======================================================================================
 * Additive only (CREATE ... IF NOT EXISTS): safe to run more than once,
 * touches no existing table.
 *
 *   node --env-file=.env.local scripts/migrate-mobile.mjs
 *
 * app_events    — one row per thing worth measuring (joined_group, pick_made,
 *                 invite_opened, ...). The "before" for the mobile redesign:
 *                 invite → joined → first pick → back in week 2.
 * invite_links  — one-tap invites (decision A: multi-use, 7-day expiry,
 *                 max 20 uses, revocable).
 * invite_joins  — who joined through which link (the owner's view).
 */

import { neon } from "@neondatabase/serverless";

const sql = neon(process.env.DATABASE_URL);

await sql`
  CREATE TABLE IF NOT EXISTS app_events (
    id          bigserial PRIMARY KEY,
    user_id     text,                      -- null for signed-out events (invite_opened)
    event       text NOT NULL,
    group_id    int,
    props       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
  )`;
await sql`CREATE INDEX IF NOT EXISTS app_events_event_time ON app_events (event, created_at)`;
await sql`CREATE INDEX IF NOT EXISTS app_events_user ON app_events (user_id, created_at)`;

await sql`
  CREATE TABLE IF NOT EXISTS invite_links (
    id          serial PRIMARY KEY,
    token       text NOT NULL UNIQUE,      -- 128-bit random, base64url
    group_id    int  NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    max_uses    int  NOT NULL CHECK (max_uses > 0),
    uses        int  NOT NULL DEFAULT 0 CHECK (uses >= 0),
    revoked_at  timestamptz
  )`;
await sql`CREATE INDEX IF NOT EXISTS invite_links_group ON invite_links (group_id)`;

await sql`
  CREATE TABLE IF NOT EXISTS invite_joins (
    link_id     int  NOT NULL REFERENCES invite_links(id) ON DELETE CASCADE,
    user_id     text NOT NULL,
    user_name   text NOT NULL,
    joined_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (link_id, user_id)
  )`;

console.log("mobile tables ready: app_events, invite_links, invite_joins");
