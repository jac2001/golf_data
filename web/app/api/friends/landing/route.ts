/**
 * GET /api/friends/landing → { groupPicks: { ride, rounds, fades, college } }
 * ===========================================================================
 * How much this person's groups (everyone who shares a group with them,
 * plus themselves) have picked in each game over the last LOOKBACK_DAYS.
 * Feeds lib/landing.ts landingGame: a new member opens on the game their
 * group actually plays. Counts only — no names, no picks — so nothing
 * here reveals a locked pick.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";

const LOOKBACK_DAYS = 42;   // six weeks: recent enough to follow a group that switched games

export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const sql = getSql();
  const rows = await sql`
    WITH people AS (
      SELECT DISTINCT gm2.user_id FROM group_members gm1
      JOIN group_members gm2 ON gm2.group_id = gm1.group_id
      WHERE gm1.user_id = ${userId}
      UNION SELECT ${userId}
    ), since AS (SELECT now() - make_interval(days => ${LOOKBACK_DAYS}) AS t)
    SELECT 'ride' AS game, count(*)::int AS n FROM league_picks
      WHERE user_id IN (SELECT user_id FROM people) AND created_at > (SELECT t FROM since)
    UNION ALL
    SELECT 'rounds', count(*)::int FROM round_picks
      WHERE user_id IN (SELECT user_id FROM people) AND created_at > (SELECT t FROM since)
    UNION ALL
    SELECT 'fades', count(*)::int FROM fade_picks
      WHERE user_id IN (SELECT user_id FROM people) AND created_at > (SELECT t FROM since)
    UNION ALL
    SELECT 'college', count(*)::int FROM college_picks
      WHERE user_id IN (SELECT user_id FROM people) AND created_at > (SELECT t FROM since)
  ` as { game: string; n: number }[];

  const groupPicks = { ride: 0, rounds: 0, fades: 0, college: 0 };
  for (const r of rows) groupPicks[r.game as keyof typeof groupPicks] = r.n;
  return Response.json({ groupPicks });
}
