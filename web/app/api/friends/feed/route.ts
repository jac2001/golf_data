/**
 * /api/friends/feed?group_id=N — what your group is up to.
 * =========================================================
 * Members' SHARED bets, plus everyone's picks for the current event —
 * but picks only appear once the event is locked, so nobody can copy a
 * pick before tee-off. Membership is checked server-side.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const groupId = Number(new URL(req.url).searchParams.get("group_id"));
  if (!groupId) return Response.json({ error: "group_id required" }, { status: 400 });

  const sql = getSql();
  const membership = await sql`
    SELECT user_id FROM group_members WHERE group_id = ${groupId}` as { user_id: string }[];
  const memberIds = membership.map(m => m.user_id);
  if (!memberIds.includes(userId)) {
    return Response.json({ error: "Not a member of this group." }, { status: 403 });
  }
  memberIds.push("model");  // its picks reveal at lock like anyone's

  const bets = await sql`
    SELECT user_name, description, odds_american, stake_units, outcome, tournament_id, created_at
    FROM user_bets
    WHERE shared = true AND user_id = ANY(${memberIds})
    ORDER BY created_at DESC LIMIT 50`;

  // Picks stay hidden until an event locks; multiple events can be live
  // the same week (PGA + DP World Tour), so reveal per locked event.
  let picks: { event: string; user_name: string; player_name: string }[] = [];
  let openNames: string[] = [];
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (res.ok) {
      const { events } = await res.json();
      const locked = (events ?? []).filter((e: { locked: boolean }) => e.locked);
      openNames = (events ?? []).filter((e: { locked: boolean }) => !e.locked)
        .map((e: { name: string }) => e.name);
      if (locked.length) {
        const tids = locked.map((e: { tournament_id: string }) => e.tournament_id);
        const rows = await sql`
          SELECT tournament_id, user_name, player_name FROM picks
          WHERE tournament_id = ANY(${tids}) AND user_id = ANY(${memberIds})
          ORDER BY user_name, created_at` as
          { tournament_id: string; user_name: string; player_name: string }[];
        const nameByTid = new Map(locked.map((e: { tournament_id: string; name: string }) => [e.tournament_id, e.name]));
        picks = rows.map(r => ({
          event: String(nameByTid.get(r.tournament_id) ?? r.tournament_id),
          user_name: r.user_name, player_name: r.player_name,
        }));
      }
    }
  } catch { /* feed still shows bets */ }

  return Response.json({ openNames, bets, picks });
}
