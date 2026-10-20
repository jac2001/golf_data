/**
 * GET /api/friends/pick-status?game=ride|rounds|fades|college&tournament_id=X&group_id=N[&round=R]
 * → { needed, members: [{ user_id, name, picked }] }
 * ===============================================================================================
 * The organizer's view (lib/whosIn.ts, Jack's): who in this group has a
 * full entry for this event and who doesn't yet. COUNTS ONLY: how many of
 * each member's picks are in, never which golfers or school, so it can't
 * reveal a hidden pick. Members only (lib/gameScope.ts: 403 otherwise).
 *   ride    → this group's active Let It Ride season; needed = players per week
 *   rounds  → `round` (the next open round); needed = 1
 *   fades   → needed = 3
 *   college → needed = 1
 */

import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { visibleUserIds } from "@/lib/gameScope";

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const game = url.searchParams.get("game");
  const tid = url.searchParams.get("tournament_id")?.toUpperCase();
  const groupId = Number(url.searchParams.get("group_id") || 0);
  if (!tid || !groupId || !["ride", "rounds", "fades", "college"].includes(game ?? "")) {
    return Response.json({ error: "game, tournament_id and group_id required" }, { status: 400 });
  }
  const ids = await visibleUserIds(userId, groupId);
  if (!ids) return Response.json({ error: "Not a member of this group." }, { status: 403 });

  const sql = getSql();
  const roster = await sql`
    SELECT user_id, user_name FROM group_members WHERE group_id = ${groupId} ORDER BY joined_at` as
    { user_id: string; user_name: string }[];

  let needed = 0;
  let counts: { user_id: string; n: number }[] = [];
  if (game === "ride") {
    const lg = await sql`SELECT id, players_per_week FROM leagues
      WHERE group_id = ${groupId} AND status = 'active' ORDER BY id DESC LIMIT 1` as { id: number; players_per_week: number }[];
    if (!lg.length) return Response.json({ needed: 0, members: [] });   // no season: nothing to show
    needed = lg[0].players_per_week;
    counts = await sql`SELECT user_id, count(*)::int AS n FROM league_picks
      WHERE league_id = ${lg[0].id} AND tournament_id = ${tid} GROUP BY 1` as typeof counts;
  } else if (game === "rounds") {
    const round = Number(url.searchParams.get("round") || 0);
    if (round < 1 || round > 4) return Response.json({ error: "round 1-4 required" }, { status: 400 });
    needed = 1;
    counts = await sql`SELECT user_id, count(*)::int AS n FROM round_picks
      WHERE tournament_id = ${tid} AND round = ${round} AND user_id = ANY(${ids}) GROUP BY 1` as typeof counts;
  } else if (game === "fades") {
    needed = 3;
    counts = await sql`SELECT user_id, count(*)::int AS n FROM fade_picks
      WHERE tournament_id = ${tid} AND user_id = ANY(${ids}) GROUP BY 1` as typeof counts;
  } else {
    needed = 1;
    counts = await sql`SELECT user_id, count(*)::int AS n FROM college_picks
      WHERE tournament_id = ${tid} AND user_id = ANY(${ids}) GROUP BY 1` as typeof counts;
  }

  const n = new Map(counts.map(c => [c.user_id, c.n]));
  return Response.json({
    needed,
    members: roster.map(r => ({ user_id: r.user_id, name: r.user_name || "Player", picked: n.get(r.user_id) ?? 0 })),
  });
}
