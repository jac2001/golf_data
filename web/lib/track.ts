/**
 * track.ts — record a product event (app_events) without ever breaking
 * the request that triggered it.
 * ====================================================================
 * The mobile redesign is judged on: invite opened → joined → first pick →
 * back in week 2. These rows are the "before". A failed insert is logged
 * and swallowed: measurement must never cost a user their pick.
 *
 * Events in use:
 *   invite_opened  { token_prefix }                      (signed out, no user)
 *   joined_group   { source: "code" | "link", link_id? }
 *   pick_made      { game: "let_it_ride" | "round" | "college" | "fade", tournament_id? }
 */

import type { getSql } from "@/lib/db";

type Sql = ReturnType<typeof getSql>;

export async function track(
  sql: Sql,
  userId: string | null,
  event: string,
  props: Record<string, unknown> = {},
  groupId: number | null = null,
): Promise<void> {
  try {
    await sql`
      INSERT INTO app_events (user_id, event, group_id, props)
      VALUES (${userId}, ${event}, ${groupId}, ${JSON.stringify(props)}::jsonb)`;
  } catch (e) {
    console.error(`track(${event}) failed:`, e);
  }
}
