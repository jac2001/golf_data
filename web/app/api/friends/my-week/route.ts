/**
 * GET /api/friends/my-week?group_id=N&tournament_ids=A,B
 * → { ride: { needed, tours } | null, events: { [tid]: { ride, rounds: {1..4}, fades, college } } }
 * ==============================================================================================
 * The signed-in member's OWN pick counts per game for this week's events,
 * for the "Also this week" checklist (lib/weekChecklist.ts, Jack's).
 * Counts only, and only the caller's: nothing here reveals anyone's picks.
 * Members only (lib/gameScope.ts: 403 otherwise).
 */

import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { visibleUserIds } from "@/lib/gameScope";

type Counts = { ride: number; rounds: Record<string, number>; fades: number; college: number };

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const groupId = Number(url.searchParams.get("group_id") || 0);
  const tids = (url.searchParams.get("tournament_ids") ?? "")
    .split(",").map(t => t.trim().toUpperCase()).filter(t => /^[RE]\d{7}$/.test(t)).slice(0, 6);
  if (!groupId || !tids.length) {
    return Response.json({ error: "group_id and tournament_ids required" }, { status: 400 });
  }
  if (!(await visibleUserIds(userId, groupId))) {
    return Response.json({ error: "Not a member of this group." }, { status: 403 });
  }

  const sql = getSql();
  const lg = await sql`SELECT id, players_per_week, tours FROM leagues
    WHERE group_id = ${groupId} AND status = 'active' ORDER BY id DESC LIMIT 1` as
    { id: number; players_per_week: number; tours: string[] | null }[];
  const league = lg[0] ?? null;

  const [ride, rounds, fades, college] = await Promise.all([
    league
      ? sql`SELECT tournament_id, count(*)::int AS n FROM league_picks
          WHERE league_id = ${league.id} AND user_id = ${userId} AND tournament_id = ANY(${tids}) GROUP BY 1`
      : Promise.resolve([]),
    sql`SELECT tournament_id, round, count(*)::int AS n FROM round_picks
      WHERE user_id = ${userId} AND tournament_id = ANY(${tids}) GROUP BY 1, 2`,
    sql`SELECT tournament_id, count(*)::int AS n FROM fade_picks
      WHERE user_id = ${userId} AND tournament_id = ANY(${tids}) GROUP BY 1`,
    sql`SELECT tournament_id, count(*)::int AS n FROM college_picks
      WHERE user_id = ${userId} AND tournament_id = ANY(${tids}) GROUP BY 1`,
  ]) as { tournament_id: string; n: number; round?: number }[][];

  const events: Record<string, Counts> = {};
  for (const t of tids) events[t] = { ride: 0, rounds: {}, fades: 0, college: 0 };
  for (const r of ride) events[r.tournament_id].ride = r.n;
  for (const r of rounds) events[r.tournament_id].rounds[String(r.round)] = r.n;
  for (const r of fades) events[r.tournament_id].fades = r.n;
  for (const r of college) events[r.tournament_id].college = r.n;

  return Response.json({
    ride: league ? { needed: league.players_per_week, tours: league.tours ?? ["pga"] } : null,
    events,
  });
}
