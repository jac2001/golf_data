/**
 * GET /api/admin/scorecard → { scorecard, events, perEvent } — the pilot's weekly scorecard.
 * ==========================================================================================
 * Feeds every app_events row and group membership to lib/scorecard.ts
 * (Jack's). Pilot events = tournaments with a pick_made, in date order:
 * ordered by each event's FIRST pick, since picks are made the week
 * before it plays (tournament ids are not calendar order). Admins are
 * excluded from every count. Admins only (403 otherwise).
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { ADMIN_USER_IDS, isAdmin } from "@/lib/admin";
import { scorecard } from "@/lib/scorecard";
import type { EventRow, Membership } from "@/lib/scorecard";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  if (!isAdmin(userId)) return Response.json({ error: "Admins only." }, { status: 403 });

  const sql = getSql();
  const rows = await sql`
    SELECT user_id, event, group_id, props, created_at::text
    FROM app_events
    WHERE event IN ('joined_group', 'pick_made', 'match_viewed', 'invite_shared', 'nudge_shared')` as EventRow[];
  const members = await sql`SELECT group_id, user_id FROM group_members` as Membership[];

  const firstPick = new Map<string, string>();
  const pickers = new Map<string, Set<string>>();
  for (const r of rows) {
    const tid = r.event === "pick_made" ? String(r.props?.tournament_id ?? "") : "";
    if (!tid) continue;
    if (!firstPick.has(tid) || r.created_at < firstPick.get(tid)!) firstPick.set(tid, r.created_at);
    if (r.user_id && r.user_id !== "model" && !ADMIN_USER_IDS.includes(r.user_id)) {
      pickers.set(tid, (pickers.get(tid) ?? new Set()).add(r.user_id));
    }
  }
  const events = [...firstPick.keys()].sort((a, b) => firstPick.get(a)!.localeCompare(firstPick.get(b)!));
  const perEvent = events.map(tid => ({ tid, players: pickers.get(tid)?.size ?? 0 }));

  try {
    return Response.json({ scorecard: scorecard(rows, members, events, [...ADMIN_USER_IDS]), events, perEvent });
  } catch (e) {
    // Until lib/scorecard.ts is written, still show the raw per-event counts.
    return Response.json({ scorecard: null, error: (e as Error).message, events, perEvent });
  }
}
