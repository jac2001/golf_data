/**
 * migrate-pick-player-ids.mjs: add a nullable player_id to the pick tables.
 * ==========================================================================
 * Approved by Jack 2026-10-20 (audit finding 5). Additive only: existing
 * rows get NULL, nothing is updated or deleted. New picks store the PGA
 * TOUR player_id from the event's predictions, so scoring matches by id
 * first (two golfers can share a name: the two Zach Johnsons at the 2018
 * and 2020 PGA Championships) and by name only as a fallback.
 *
 * Run: node --env-file=.env.local scripts/migrate-pick-player-ids.mjs
 */
import { neon } from "@neondatabase/serverless";

const sql = neon(process.env.DATABASE_URL);

for (const table of ["league_picks", "fade_picks", "round_picks"]) {
  // Identifiers can't be bind parameters; the names come from the list above.
  await sql.query(`ALTER TABLE ${table} ADD COLUMN IF NOT EXISTS player_id TEXT`);
  const [{ n, with_id }] = await sql.query(
    `SELECT count(*)::int AS n, count(player_id)::int AS with_id FROM ${table}`);
  console.log(`${table}: player_id column ready (${n} rows, ${with_id} with an id)`);
}
