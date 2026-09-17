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

  const bets = await sql`
    SELECT user_name, description, odds_american, stake_units, outcome, tournament_id, created_at
    FROM user_bets
    WHERE shared = true AND user_id = ANY(${memberIds})
    ORDER BY created_at DESC LIMIT 50`;

  // Picks stay hidden until the event locks.
  let picks: unknown[] = [];
  let event: { tid: string; name: string; locked: boolean } | null = null;
  try {
    const res = await fetch(`${MODEL_API}/api/tournament`, { cache: "no-store" });
    if (res.ok) {
      const t = await res.json();
      const startDate = String(t.start_date ?? "");
      const locked = !!startDate && new Date() >= new Date(`${startDate.slice(0, 10)}T00:00:00`);
      event = { tid: String(t.tournament_id ?? ""), name: String(t.name ?? ""), locked };
      if (locked && event.tid) {
        picks = await sql`
          SELECT user_name, player_name FROM picks
          WHERE tournament_id = ${event.tid} AND user_id = ANY(${memberIds})
          ORDER BY user_name, created_at` as { user_name: string; player_name: string }[];
      }
    }
  } catch { /* feed still shows bets */ }

  return Response.json({ event, bets, picks });
}
